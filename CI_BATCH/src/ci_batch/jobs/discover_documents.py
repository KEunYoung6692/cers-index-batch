"""
Create a document manifest from a directory of PDF reports.

Usage:
  PYTHONPATH=CI_BATCH/src python -m ci_batch.jobs.discover_documents \
    --input-dir CI_BATCH/docs/samples/reports
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ci_batch.common.jsonl import write_jsonl
from ci_batch.common.run_context import make_run_context, write_manifest
from ci_batch.common.settings import load_settings
from ci_batch.common.storage import manifests_dir, run_partition_dir
from ci_batch.intake.discovery import discover_documents


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover PDF documents and create a manifest")
    parser.add_argument("--input-dir", required=True, help="Directory containing PDF reports")
    parser.add_argument("--run-date", default=None, help="Run date in YYYY-MM-DD format")
    parser.add_argument("--registrar", default=None, help="Registrar override")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = load_settings()
    registrar = args.registrar or settings.registrar
    input_dir = Path(args.input_dir)

    context = make_run_context(
        batch_name="discover_documents",
        ci_batch_root=settings.ci_batch_root,
        run_date=args.run_date,
    )
    results = discover_documents(input_dir, registrar=registrar)

    partition_dir = run_partition_dir(manifests_dir(settings.ci_batch_root), context.run_date)
    documents_path = partition_dir / f"{context.run_id}_documents.jsonl"
    write_jsonl(documents_path, (result.document.to_dict() for result in results))

    write_manifest(
        context,
        extra={
            "input_dir": str(input_dir.resolve()),
            "document_count": len(results),
            "documents_manifest_path": str(documents_path),
        },
    )

    print(
        json.dumps(
            {
                "run_id": context.run_id,
                "run_date": context.run_date,
                "documents_manifest_path": str(documents_path),
                "document_count": len(results),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
