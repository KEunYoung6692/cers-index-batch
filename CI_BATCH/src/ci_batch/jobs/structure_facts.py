"""
Structure schema-aligned fact drafts from retrieval chunks.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ci_batch.common.jsonl import read_jsonl, write_jsonl
from ci_batch.common.run_context import make_run_context, write_manifest
from ci_batch.common.settings import load_settings
from ci_batch.common.storage import manifests_dir, rag_dir, run_partition_dir
from ci_batch.contracts import StructuredFactRecord
from ci_batch.embed.openai_embeddings import OpenAIChunkEmbedder
from ci_batch.rag.openai_structurer import OpenAIFactStructurer
from ci_batch.rag.profiles import FACT_PROFILES
from ci_batch.rag.retriever import retrieve_chunks
from ci_batch.rag.schema import extract_table_fields, extract_table_section, load_schema_text
from ci_batch.vectordb.qdrant_store import LocalQdrantChunkStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Structure schema-aligned fact drafts from retrieval chunks")
    parser.add_argument("--documents-manifest", required=True, help="Path to extracted documents manifest JSONL")
    parser.add_argument("--chunks-manifest", required=True, help="Path to retrieval chunks manifest JSONL")
    parser.add_argument("--run-date", default=None, help="Run date in YYYY-MM-DD format")
    parser.add_argument("--registrar", default=None, help="Registrar override")
    parser.add_argument("--document-key", default=None, help="Process a single document")
    parser.add_argument("--table", default=None, help="Process a single target table")
    parser.add_argument("--dry-run", action="store_true", help="Write retrieval candidates only without OpenAI call")
    return parser.parse_args()


def _normalize_record(
    *,
    document: dict,
    table_name: str,
    record_index: int,
    target_fields: list[str],
    raw_record: dict,
    registrar: str,
    retrieval_mode: str,
) -> StructuredFactRecord:
    fact_payload = raw_record.get("fact_payload") or {}
    normalized_payload = {field: fact_payload.get(field) for field in target_fields}
    if "data_status" in normalized_payload and normalized_payload["data_status"] is None:
        normalized_payload["data_status"] = "reported"

    return StructuredFactRecord(
        structured_record_key=f"{document['document_key']}_{table_name}_{record_index:04d}",
        table_name=table_name,
        document_key=document["document_key"],
        company_name=document.get("company_name"),
        report_year=document.get("report_year"),
        fact_payload=normalized_payload,
        source_chunk_ids=raw_record.get("source_chunk_ids") or [],
        source_page_numbers=raw_record.get("source_page_numbers") or [],
        source_evidence_keys=raw_record.get("source_evidence_keys") or [],
        source_evidence_excerpt=raw_record.get("source_evidence_excerpt"),
        registrar=registrar,
        metadata={
            "retrieval_mode": retrieval_mode,
        },
    )


def main() -> int:
    args = parse_args()
    settings = load_settings()
    registrar = args.registrar or settings.registrar
    context = make_run_context(
        batch_name="structure_facts",
        ci_batch_root=settings.ci_batch_root,
        run_date=args.run_date,
    )

    documents = read_jsonl(Path(args.documents_manifest))
    if args.document_key:
        documents = [row for row in documents if row.get("document_key") == args.document_key]
    chunks = read_jsonl(Path(args.chunks_manifest))
    schema_text = load_schema_text(settings.schema_doc_path)

    selected_profiles = FACT_PROFILES
    if args.table:
        selected_profiles = [profile for profile in FACT_PROFILES if profile.table_name == args.table]

    embedder = None
    fact_structurer = None
    qdrant_store = None
    if not args.dry_run:
        embedder = OpenAIChunkEmbedder(
            api_key_env=settings.openai_api_key_env,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
        fact_structurer = OpenAIFactStructurer(
            api_key_env=settings.openai_api_key_env,
            model=settings.structuring_model,
        )
        qdrant_store = LocalQdrantChunkStore(
            storage_path=settings.storage_dir / "qdrant",
            collection_name=settings.vector_db_collection,
        )

    base_rag_dir = rag_dir(settings.ci_batch_root)
    manifest_rows: list[dict] = []
    summary = {
        "requested_documents": len(documents),
        "processed_documents": 0,
        "structured_record_count": 0,
        "table_count": len(selected_profiles),
    }

    for document in documents:
        document_key = document["document_key"]
        document_rag_dir = run_partition_dir(base_rag_dir, context.run_date, document_key)

        for profile in selected_profiles:
            retrieved = retrieve_chunks(
                chunks=chunks,
                profile=profile,
                document_key=document_key,
                store=qdrant_store,
                embedder=embedder,
            )
            retrieved_chunks = [item.chunk for item in retrieved]
            retrieval_mode = retrieved[0].retrieval_mode if retrieved else "keyword"

            schema_section = extract_table_section(schema_text, profile.table_name)
            target_fields = extract_table_fields(schema_section)

            if args.dry_run:
                dry_run_path = document_rag_dir / f"{profile.table_name}.preview.json"
                dry_run_path.write_text(
                    json.dumps(
                        {
                            "table_name": profile.table_name,
                            "retrieval_mode": retrieval_mode,
                            "target_fields": target_fields,
                            "retrieved_chunks": retrieved_chunks,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                continue

            assert fact_structurer is not None
            result, usage = fact_structurer.structure(
                profile=profile,
                schema_section=schema_section,
                target_fields=target_fields,
                company_name=document.get("company_name"),
                report_year=document.get("report_year"),
                document_key=document_key,
                retrieved_chunks=retrieved_chunks,
            )
            raw_records = result.get("records") or []
            structured_records = [
                _normalize_record(
                    document=document,
                    table_name=profile.table_name,
                    record_index=index,
                    target_fields=target_fields,
                    raw_record=raw_record,
                    registrar=registrar,
                    retrieval_mode=retrieval_mode,
                )
                for index, raw_record in enumerate(raw_records, start=1)
            ]

            write_jsonl(
                document_rag_dir / f"{profile.table_name}.jsonl",
                (record.to_dict() for record in structured_records),
            )
            manifest_rows.extend(record.to_dict() for record in structured_records)
            summary["structured_record_count"] += len(structured_records)

            (document_rag_dir / f"{profile.table_name}.usage.json").write_text(
                json.dumps(usage, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        summary["processed_documents"] += 1

    manifests_partition = run_partition_dir(manifests_dir(settings.ci_batch_root), context.run_date)
    manifest_path = manifests_partition / f"{context.run_id}_structured_facts.jsonl"
    write_jsonl(manifest_path, manifest_rows)

    write_manifest(
        context,
        extra={
            "documents_manifest_path": str(Path(args.documents_manifest).resolve()),
            "chunks_manifest_path": str(Path(args.chunks_manifest).resolve()),
            "structured_manifest_path": str(manifest_path),
            "dry_run": args.dry_run,
            **summary,
        },
    )

    print(
        json.dumps(
            {
                "run_id": context.run_id,
                "run_date": context.run_date,
                "structured_manifest_path": str(manifest_path),
                "dry_run": args.dry_run,
                **summary,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
