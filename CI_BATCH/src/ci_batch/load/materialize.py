"""
Materialize structured fact drafts into table-ready load rows.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ci_batch.contracts import TableLoadRecord
from ci_batch.rag.schema import TableFieldSpec


AUTO_MANAGED_FIELDS = {"reg_date", "registrar", "update_date", "updater"}
REFERENCE_FIELDS = {"company_id", "period_id", "source_document_id", "evidence_id", "unit_id"}


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_value(field_name: str, *, registrar: str) -> object | None:
    if field_name == "reg_date":
        return utc_iso_now()
    if field_name == "registrar":
        return registrar
    if field_name in {"update_date", "updater"}:
        return None
    return None


def build_row_payload(
    *,
    field_specs: list[TableFieldSpec],
    fact_payload: dict,
    registrar: str,
) -> dict:
    row_payload: dict = {}
    for spec in field_specs:
        if spec.key == "PK":
            continue
        if spec.name in fact_payload:
            row_payload[spec.name] = fact_payload.get(spec.name)
        else:
            row_payload[spec.name] = _default_value(spec.name, registrar=registrar)
    return row_payload


def classify_missing_fields(field_specs: list[TableFieldSpec], row_payload: dict) -> tuple[list[str], list[str], list[str]]:
    missing_required_fields: list[str] = []
    missing_business_fields: list[str] = []
    missing_reference_fields: list[str] = []

    for spec in field_specs:
        if spec.key == "PK" or spec.nullable:
            continue
        value = row_payload.get(spec.name)
        if value is not None:
            continue
        missing_required_fields.append(spec.name)
        if spec.name in REFERENCE_FIELDS or spec.name.endswith("_id"):
            missing_reference_fields.append(spec.name)
        else:
            missing_business_fields.append(spec.name)

    return missing_required_fields, missing_business_fields, missing_reference_fields


def determine_load_status(*, missing_required_fields: list[str], missing_business_fields: list[str]) -> str:
    if missing_business_fields:
        return "invalid"
    if missing_required_fields:
        return "needs_resolution"
    return "ready"


def materialize_structured_fact(
    *,
    structured_record: dict,
    field_specs: list[TableFieldSpec],
    registrar: str,
) -> TableLoadRecord:
    row_payload = build_row_payload(
        field_specs=field_specs,
        fact_payload=structured_record.get("fact_payload") or {},
        registrar=registrar,
    )
    missing_required_fields, missing_business_fields, missing_reference_fields = classify_missing_fields(
        field_specs,
        row_payload,
    )
    load_status = determine_load_status(
        missing_required_fields=missing_required_fields,
        missing_business_fields=missing_business_fields,
    )
    return TableLoadRecord(
        load_record_key=structured_record["structured_record_key"],
        table_name=structured_record["table_name"],
        load_status=load_status,
        row_payload=row_payload,
        document_key=structured_record["document_key"],
        company_name=structured_record.get("company_name"),
        report_year=structured_record.get("report_year"),
        missing_required_fields=missing_required_fields,
        missing_business_fields=missing_business_fields,
        missing_reference_fields=missing_reference_fields,
        source_chunk_ids=structured_record.get("source_chunk_ids") or [],
        source_page_numbers=structured_record.get("source_page_numbers") or [],
        source_evidence_keys=structured_record.get("source_evidence_keys") or [],
        source_evidence_excerpt=structured_record.get("source_evidence_excerpt"),
        registrar=registrar,
        metadata={
            **(structured_record.get("metadata") or {}),
            "materialized_at": utc_iso_now(),
        },
    )
