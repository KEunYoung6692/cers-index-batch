"""
Normalize extracted pages and build retrieval chunks.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ci_batch.chunk.build import build_retrieval_chunks
from ci_batch.common.jsonl import read_jsonl, write_jsonl
from ci_batch.common.run_context import make_run_context, write_manifest
from ci_batch.common.settings import load_settings
from ci_batch.common.storage import chunks_dir, manifests_dir, run_partition_dir
from ci_batch.normalize.text import normalize_page_texts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build normalized pages and retrieval chunks")
    parser.add_argument("--documents-manifest", required=True, help="Path to extracted documents manifest JSONL")
    parser.add_argument("--run-date", default=None, help="Run date in YYYY-MM-DD format")
    parser.add_argument("--registrar", default=None, help="Registrar override")
    parser.add_argument("--document-key", default=None, help="Build chunks for a single document")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of documents to process")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = load_settings()
    registrar = args.registrar or settings.registrar
    context = make_run_context(
        batch_name="build_chunks",
        ci_batch_root=settings.ci_batch_root,
        run_date=args.run_date,
    )

    manifest_path = Path(args.documents_manifest)
    documents = read_jsonl(manifest_path)
    if args.document_key:
        documents = [row for row in documents if row.get("document_key") == args.document_key]
    if args.limit is not None:
        documents = documents[: args.limit]

    target_chars = settings.chunk_target_tokens * 4
    overlap_chars = settings.chunk_overlap_tokens * 4
    chunks_manifest_rows: list[dict] = []
    summary = {
        "requested_documents": len(documents),
        "processed_documents": 0,
        "chunk_count": 0,
    }

    base_chunks_dir = chunks_dir(settings.ci_batch_root)
    parsed_root = settings.storage_dir / "parsed" / context.run_date

    for document in documents:
        document_key = document["document_key"]
        parsed_document_dir = parsed_root / document_key
        pages_path = parsed_document_dir / "document_pages.jsonl"
        evidence_path = parsed_document_dir / "extracted_evidence.jsonl"
        if not pages_path.exists() or not evidence_path.exists():
            continue

        page_rows = read_jsonl(pages_path)
        evidence_rows = read_jsonl(evidence_path)
        normalized_pages = normalize_page_texts([row.get("raw_text") or "" for row in page_rows])
        normalized_page_rows = []
        for page_row, normalized in zip(page_rows, normalized_pages, strict=False):
            normalized_page_rows.append(
                {
                    "page_key": page_row["page_key"],
                    "document_key": document_key,
                    "page_no": page_row["page_no"],
                    **normalized,
                }
            )

        chunks = build_retrieval_chunks(
            document_key=document_key,
            company_name=document.get("company_name"),
            report_year=document.get("report_year"),
            normalized_pages=normalized_page_rows,
            evidence_rows=evidence_rows,
            target_chars=target_chars,
            overlap_chars=overlap_chars,
            registrar=registrar,
        )

        document_chunk_dir = run_partition_dir(base_chunks_dir, context.run_date, document_key)
        write_jsonl(document_chunk_dir / "normalized_pages.jsonl", normalized_page_rows)
        write_jsonl(document_chunk_dir / "retrieval_chunks.jsonl", (chunk.to_dict() for chunk in chunks))

        chunks_manifest_rows.extend(chunk.to_dict() for chunk in chunks)
        summary["processed_documents"] += 1
        summary["chunk_count"] += len(chunks)

    manifests_partition = run_partition_dir(manifests_dir(settings.ci_batch_root), context.run_date)
    chunk_manifest_path = manifests_partition / f"{context.run_id}_retrieval_chunks.jsonl"
    write_jsonl(chunk_manifest_path, chunks_manifest_rows)

    write_manifest(
        context,
        extra={
            "documents_manifest_path": str(manifest_path.resolve()),
            "chunk_manifest_path": str(chunk_manifest_path),
            **summary,
        },
    )

    print(
        json.dumps(
            {
                "run_id": context.run_id,
                "run_date": context.run_date,
                "chunk_manifest_path": str(chunk_manifest_path),
                **summary,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
