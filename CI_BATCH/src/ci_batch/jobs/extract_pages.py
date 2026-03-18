"""
Extract page text and evidence blocks from discovered PDF documents.

Usage:
  PYTHONPATH=CI_BATCH/src python -m ci_batch.jobs.extract_pages \
    --documents-manifest CI_BATCH/storage/manifests/2026-03-18/<manifest>.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ci_batch.common.jsonl import read_jsonl, write_jsonl
from ci_batch.common.run_context import make_run_context, write_manifest
from ci_batch.common.settings import load_settings
from ci_batch.common.storage import manifests_dir, parsed_dir, run_partition_dir
from ci_batch.contracts import DocumentRecord
from ci_batch.extract.pdf import extract_document


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract page text and evidence blocks from PDF documents")
    parser.add_argument("--documents-manifest", required=True, help="Path to discovered document manifest JSONL")
    parser.add_argument("--run-date", default=None, help="Run date in YYYY-MM-DD format")
    parser.add_argument("--registrar", default=None, help="Registrar override")
    parser.add_argument("--document-key", default=None, help="Extract a single document by document_key")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of documents to extract")
    return parser.parse_args()


def document_from_row(row: dict) -> DocumentRecord:
    metadata = row.get("metadata") or {}
    return DocumentRecord(
        document_key=row["document_key"],
        title=row["title"],
        company_name=row.get("company_name"),
        company_id=row.get("company_id"),
        source_id=row.get("source_id"),
        document_type=row.get("document_type") or "sustainability_report",
        report_year=row.get("report_year"),
        published_at=None,
        file_path=row.get("file_path"),
        file_hash=row.get("file_hash"),
        language=row.get("language"),
        page_count=row.get("page_count"),
        ingestion_status=row.get("ingestion_status") or "pending",
        registrar=row.get("registrar") or "ci_batch",
        metadata=metadata,
        document_id=row.get("document_id"),
    )


def main() -> int:
    args = parse_args()
    settings = load_settings()
    registrar = args.registrar or settings.registrar

    context = make_run_context(
        batch_name="extract_pages",
        ci_batch_root=settings.ci_batch_root,
        run_date=args.run_date,
    )

    manifest_path = Path(args.documents_manifest)
    rows = read_jsonl(manifest_path)
    documents = [document_from_row(row) for row in rows]
    if args.document_key:
        documents = [document for document in documents if document.document_key == args.document_key]
    if args.limit is not None:
        documents = documents[: args.limit]

    extraction_run_rows: list[dict] = []
    extracted_documents: list[dict] = []
    summary = {
        "requested_documents": len(documents),
        "succeeded_documents": 0,
        "failed_documents": 0,
        "page_count": 0,
        "evidence_count": 0,
    }

    base_parsed_dir = parsed_dir(settings.ci_batch_root)
    for document in documents:
        enriched_document, extraction_run, page_records, evidence_records = extract_document(
            document,
            run_id=context.run_id,
            extractor_version=settings.extractor_version,
            registrar=registrar,
        )

        report_dir = run_partition_dir(base_parsed_dir, context.run_date, document.document_key)
        (report_dir / "document.json").write_text(
            json.dumps(enriched_document.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (report_dir / "extraction_run.json").write_text(
            json.dumps(extraction_run.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        write_jsonl(report_dir / "document_pages.jsonl", (record.to_dict() for record in page_records))
        write_jsonl(report_dir / "extracted_evidence.jsonl", (record.to_dict() for record in evidence_records))

        extraction_run_rows.append(extraction_run.to_dict())
        extracted_documents.append(enriched_document.to_dict())

        if extraction_run.status == "succeeded":
            summary["succeeded_documents"] += 1
            summary["page_count"] += len(page_records)
            summary["evidence_count"] += len(evidence_records)
        else:
            summary["failed_documents"] += 1

    manifests_partition = run_partition_dir(manifests_dir(settings.ci_batch_root), context.run_date)
    extraction_runs_path = manifests_partition / f"{context.run_id}_extraction_runs.jsonl"
    extracted_documents_path = manifests_partition / f"{context.run_id}_documents_extracted.jsonl"
    write_jsonl(extraction_runs_path, extraction_run_rows)
    write_jsonl(extracted_documents_path, extracted_documents)

    write_manifest(
        context,
        extra={
            "documents_manifest_path": str(manifest_path.resolve()),
            "extraction_runs_path": str(extraction_runs_path),
            "extracted_documents_path": str(extracted_documents_path),
            **summary,
        },
    )

    print(
        json.dumps(
            {
                "run_id": context.run_id,
                "run_date": context.run_date,
                "extraction_runs_path": str(extraction_runs_path),
                "extracted_documents_path": str(extracted_documents_path),
                **summary,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
