"""
Materialize structured fact drafts into table-ready load artifacts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ci_batch.common.jsonl import read_jsonl, write_jsonl
from ci_batch.common.run_context import make_run_context, write_manifest
from ci_batch.common.settings import load_settings
from ci_batch.common.storage import load_dir, manifests_dir, run_partition_dir
from ci_batch.load.materialize import materialize_structured_fact
from ci_batch.rag.schema import extract_table_field_specs, extract_table_section, load_schema_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize structured fact drafts into table-ready load artifacts")
    parser.add_argument("--structured-manifest", required=True, help="Path to structured facts manifest JSONL")
    parser.add_argument("--run-date", default=None, help="Run date in YYYY-MM-DD format")
    parser.add_argument("--registrar", default=None, help="Registrar override")
    parser.add_argument("--table", default=None, help="Materialize a single table")
    parser.add_argument("--status", default=None, choices=["ready", "needs_resolution", "invalid"], help="Filter output status")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = load_settings()
    registrar = args.registrar or settings.registrar
    context = make_run_context(
        batch_name="materialize_loads",
        ci_batch_root=settings.ci_batch_root,
        run_date=args.run_date,
    )

    structured_rows = read_jsonl(Path(args.structured_manifest))
    if args.table:
        structured_rows = [row for row in structured_rows if row.get("table_name") == args.table]

    schema_text = load_schema_text(settings.schema_doc_path)
    base_load_dir = load_dir(settings.ci_batch_root)
    table_groups: dict[str, list[dict]] = {}
    for row in structured_rows:
        table_groups.setdefault(row["table_name"], []).append(row)

    summary_rows: list[dict] = []
    manifest_rows: list[dict] = []
    totals = {
        "structured_record_count": len(structured_rows),
        "materialized_record_count": 0,
        "ready_count": 0,
        "needs_resolution_count": 0,
        "invalid_count": 0,
        "table_count": len(table_groups),
    }

    for table_name, rows in sorted(table_groups.items()):
        table_section = extract_table_section(schema_text, table_name)
        field_specs = extract_table_field_specs(table_section)
        materialized = [
            materialize_structured_fact(
                structured_record=row,
                field_specs=field_specs,
                registrar=registrar,
            )
            for row in rows
        ]
        if args.status:
            materialized = [row for row in materialized if row.load_status == args.status]

        table_dir = run_partition_dir(base_load_dir, context.run_date, table_name)
        all_rows_path = table_dir / "rows.jsonl"
        ready_rows_path = table_dir / "ready_rows.jsonl"
        needs_resolution_path = table_dir / "needs_resolution_rows.jsonl"
        invalid_rows_path = table_dir / "invalid_rows.jsonl"

        write_jsonl(all_rows_path, (row.to_dict() for row in materialized))
        write_jsonl(ready_rows_path, (row.to_dict() for row in materialized if row.load_status == "ready"))
        write_jsonl(
            needs_resolution_path,
            (row.to_dict() for row in materialized if row.load_status == "needs_resolution"),
        )
        write_jsonl(invalid_rows_path, (row.to_dict() for row in materialized if row.load_status == "invalid"))

        table_summary = {
            "table_name": table_name,
            "row_count": len(materialized),
            "ready_count": sum(1 for row in materialized if row.load_status == "ready"),
            "needs_resolution_count": sum(1 for row in materialized if row.load_status == "needs_resolution"),
            "invalid_count": sum(1 for row in materialized if row.load_status == "invalid"),
            "rows_path": str(all_rows_path),
        }
        (table_dir / "summary.json").write_text(
            json.dumps(table_summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        summary_rows.append(table_summary)
        manifest_rows.extend(row.to_dict() for row in materialized)

        totals["materialized_record_count"] += len(materialized)
        totals["ready_count"] += table_summary["ready_count"]
        totals["needs_resolution_count"] += table_summary["needs_resolution_count"]
        totals["invalid_count"] += table_summary["invalid_count"]

    manifests_partition = run_partition_dir(manifests_dir(settings.ci_batch_root), context.run_date)
    materialized_manifest_path = manifests_partition / f"{context.run_id}_load_rows.jsonl"
    summary_manifest_path = manifests_partition / f"{context.run_id}_load_summary.json"
    write_jsonl(materialized_manifest_path, manifest_rows)
    summary_manifest_path.write_text(
        json.dumps(
            {
                "tables": summary_rows,
                **totals,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    write_manifest(
        context,
        extra={
            "structured_manifest_path": str(Path(args.structured_manifest).resolve()),
            "materialized_manifest_path": str(materialized_manifest_path),
            "summary_manifest_path": str(summary_manifest_path),
            "status_filter": args.status,
            **totals,
        },
    )

    print(
        json.dumps(
            {
                "run_id": context.run_id,
                "run_date": context.run_date,
                "materialized_manifest_path": str(materialized_manifest_path),
                "summary_manifest_path": str(summary_manifest_path),
                "status_filter": args.status,
                **totals,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
