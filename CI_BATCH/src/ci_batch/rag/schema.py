"""
Helpers for extracting table-specific schema sections from schema.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


EXCLUDED_FIELDS = {
    "company_id",
    "period_id",
    "source_document_id",
    "evidence_id",
    "reg_date",
    "registrar",
    "update_date",
    "updater",
}


@dataclass(frozen=True)
class TableFieldSpec:
    name: str
    data_type: str
    nullable: bool
    key: str | None
    description: str


def load_schema_text(schema_doc_path: Path) -> str:
    return schema_doc_path.read_text(encoding="utf-8")


def extract_table_section(schema_text: str, table_name: str) -> str:
    pattern = re.compile(
        rf"^### `{re.escape(table_name)}`\n(?P<section>.*?)(?=^### `|^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(schema_text)
    if not match:
        raise KeyError(f"Table section not found in schema.md: {table_name}")
    return f"### `{table_name}`\n" + match.group("section").strip()


def extract_table_fields(table_section: str) -> list[str]:
    fields: list[str] = []
    for spec in extract_table_field_specs(table_section):
        field_name = spec.name
        if not field_name or field_name.endswith("_id") or field_name in EXCLUDED_FIELDS:
            continue
        fields.append(field_name)
    return fields


def extract_table_field_specs(table_section: str) -> list[TableFieldSpec]:
    specs: list[TableFieldSpec] = []
    for line in table_section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("| `"):
            continue
        parts = [part.strip() for part in stripped.split("|")]
        if len(parts) < 6:
            continue
        specs.append(
            TableFieldSpec(
                name=parts[1].strip().strip("`"),
                data_type=parts[2],
                nullable=parts[3].upper() == "Y",
                key=parts[4] or None,
                description=parts[5],
            )
        )
    return specs
