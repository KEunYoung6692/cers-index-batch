"""
Source field inventory and source-to-common projection utilities.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable

import pandas as pd


CANONICAL_COLUMNS = [
    "source_name",
    "metadata_file",
    "document_path",
    "source_page",
    "source_row",
    "source_type",
    "company_name",
    "company_id",
    "company_url",
    "report_year",
    "record_type",
    "metric_name",
    "metric_key",
    "scope",
    "category",
    "data_year",
    "target_year",
    "baseline_year",
    "value",
    "unit",
    "reduction_pct",
    "evidence_text",
]


def _series_const(df: pd.DataFrame, value) -> pd.Series:
    return pd.Series([value] * len(df), index=df.index, dtype="object")


def _series_col(df: pd.DataFrame, column: str) -> pd.Series:
    if column in df.columns:
        return df[column]
    return _series_const(df, None)


def _series_coalesce(df: pd.DataFrame, columns: list[str]) -> pd.Series:
    if not columns:
        return _series_const(df, None)
    out = _series_col(df, columns[0])
    for column in columns[1:]:
        out = out.combine_first(_series_col(df, column))
    return out


def _gir_record_type(df: pd.DataFrame) -> pd.Series:
    key = _series_col(df, "metric_key").astype("string").str.lower()
    out = _series_const(df, "unknown")
    out.loc[key == "ghg_tco2eq"] = "emission"
    out.loc[key == "energy_tj"] = "activity"
    return out


def _nzdpu_data_explorer_record_type(df: pd.DataFrame) -> pd.Series:
    key = _series_col(df, "metric_key").astype("string").str.lower()
    out = _series_const(df, "emission")
    target_mask = key.str.contains(r"target|reduction|net[_ ]?zero", regex=True, na=False)
    out.loc[target_mask] = "target"
    return out


def _nzdpu_company_report_year(df: pd.DataFrame) -> pd.Series:
    data_year = pd.to_numeric(_series_col(df, "data_year"), errors="coerce")
    target_year = pd.to_numeric(_series_col(df, "target_year"), errors="coerce")
    return data_year.combine_first(target_year)


def _metric_key_from_metric_name(df: pd.DataFrame) -> pd.Series:
    return _series_coalesce(df, ["metric_key", "metric_name"])


@dataclass(frozen=True)
class SourceInventory:
    source_name: str
    output_columns: list[str]
    supports: dict[str, bool]
    mapping: dict[str, object]
    notes: str


SOURCE_INVENTORY: dict[str, SourceInventory] = {
    "gir-kor": SourceInventory(
        source_name="gir-kor",
        output_columns=[
            "source_name",
            "source_file",
            "source_row",
            "company_name",
            "stock_code",
            "agency",
            "year",
            "designation_type",
            "industry",
            "verifier",
            "remark",
            "metric_key",
            "metric_name",
            "value",
            "unit",
        ],
        supports={
            "emission": True,
            "target": False,
            "scope": False,
            "data_year": True,
            "target_year": False,
            "baseline_year": False,
            "reduction_pct": False,
            "raw_evidence": True,
        },
        mapping={
            "source_name": "source_name",
            "metadata_file": "source_file",
            "document_path": "source_file",
            "source_page": ("const", None),
            "source_row": "source_row",
            "source_type": ("const", "table"),
            "company_name": "company_name",
            "company_id": "stock_code",
            "company_url": ("const", None),
            "report_year": "year",
            "record_type": _gir_record_type,
            "metric_name": "metric_name",
            "metric_key": "metric_key",
            "scope": ("const", None),
            "category": ("const", None),
            "data_year": "year",
            "target_year": ("const", None),
            "baseline_year": ("const", None),
            "value": "value",
            "unit": "unit",
            "reduction_pct": ("const", None),
            "evidence_text": ("coalesce", ["remark", "metric_name"]),
        },
        notes="Korean GIR table source with GHG and energy metrics.",
    ),
    "nzdpu-data-explorer": SourceInventory(
        source_name="nzdpu-data-explorer",
        output_columns=[
            "source_name",
            "source_file",
            "source_row",
            "company_name",
            "company_url",
            "reporting_year",
            "data_provider",
            "jurisdiction",
            "sics_sector",
            "metric_key",
            "scope",
            "category",
            "value",
            "unit",
            "raw_value",
        ],
        supports={
            "emission": True,
            "target": True,
            "scope": True,
            "data_year": True,
            "target_year": False,
            "baseline_year": False,
            "reduction_pct": False,
            "raw_evidence": True,
        },
        mapping={
            "source_name": "source_name",
            "metadata_file": "source_file",
            "document_path": "source_file",
            "source_page": ("const", None),
            "source_row": "source_row",
            "source_type": ("const", "table"),
            "company_name": "company_name",
            "company_id": ("const", None),
            "company_url": "company_url",
            "report_year": "reporting_year",
            "record_type": _nzdpu_data_explorer_record_type,
            "metric_name": "metric_key",
            "metric_key": "metric_key",
            "scope": "scope",
            "category": "category",
            "data_year": "reporting_year",
            "target_year": ("const", None),
            "baseline_year": ("const", None),
            "value": "value",
            "unit": "unit",
            "reduction_pct": ("const", None),
            "evidence_text": "raw_value",
        },
        notes="NZDPU data explorer wide metrics expanded into long rows.",
    ),
    "nzdpu-company": SourceInventory(
        source_name="nzdpu-company",
        output_columns=[
            "source_name",
            "source_file",
            "source_row",
            "company_id",
            "company_name",
            "company_url",
            "top_tab",
            "subtab",
            "page_url",
            "row_type",
            "group",
            "field_name",
            "data_key",
            "source",
            "last_updated",
            "restatement",
            "record_type",
            "scope",
            "category",
            "data_year",
            "target_year",
            "value",
            "unit",
            "raw_value",
        ],
        supports={
            "emission": True,
            "target": True,
            "scope": True,
            "data_year": True,
            "target_year": True,
            "baseline_year": False,
            "reduction_pct": False,
            "raw_evidence": True,
        },
        mapping={
            "source_name": "source_name",
            "metadata_file": "source_file",
            "document_path": ("coalesce", ["page_url", "source_file"]),
            "source_page": ("const", None),
            "source_row": "source_row",
            "source_type": "row_type",
            "company_name": "company_name",
            "company_id": "company_id",
            "company_url": "company_url",
            "report_year": _nzdpu_company_report_year,
            "record_type": "record_type",
            "metric_name": ("coalesce", ["field_name", "group", "data_key"]),
            "metric_key": ("coalesce", ["data_key", "field_name"]),
            "scope": "scope",
            "category": "category",
            "data_year": "data_year",
            "target_year": "target_year",
            "baseline_year": ("const", None),
            "value": "value",
            "unit": "unit",
            "reduction_pct": ("const", None),
            "evidence_text": ("coalesce", ["raw_value", "field_name", "group"]),
        },
        notes="NZDPU company detail tables with item/group rows and tabs.",
    ),
    "jpx-esgdata": SourceInventory(
        source_name="jpx-esgdata",
        output_columns=[
            "source_name",
            "source_file",
            "pdf_path",
            "source_page",
            "source_type",
            "company_name",
            "company_id",
            "company_url",
            "report_year",
            "record_type",
            "metric_name",
            "scope",
            "data_year",
            "target_year",
            "reduction_pct",
            "value",
            "unit",
            "raw_text",
        ],
        supports={
            "emission": True,
            "target": True,
            "scope": True,
            "data_year": True,
            "target_year": True,
            "baseline_year": False,
            "reduction_pct": True,
            "raw_evidence": True,
        },
        mapping={
            "source_name": "source_name",
            "metadata_file": "source_file",
            "document_path": "pdf_path",
            "source_page": "source_page",
            "source_row": ("const", None),
            "source_type": "source_type",
            "company_name": "company_name",
            "company_id": "company_id",
            "company_url": "company_url",
            "report_year": "report_year",
            "record_type": "record_type",
            "metric_name": "metric_name",
            "metric_key": _metric_key_from_metric_name,
            "scope": "scope",
            "category": ("const", None),
            "data_year": "data_year",
            "target_year": "target_year",
            "baseline_year": ("const", None),
            "value": "value",
            "unit": "unit",
            "reduction_pct": "reduction_pct",
            "evidence_text": "raw_text",
        },
        notes="JPX PDF parser from metadata + text/table extraction.",
    ),
    "krx-esg": SourceInventory(
        source_name="krx-esg",
        output_columns=[
            "source_name",
            "pdf_path",
            "file_name",
            "company_name",
            "report_year",
            "page_number",
            "record_type",
            "metric_name",
            "scope",
            "data_year",
            "target_year",
            "baseline_year",
            "value",
            "reduction_pct",
            "unit",
            "source_type",
            "raw_text",
        ],
        supports={
            "emission": True,
            "target": True,
            "scope": True,
            "data_year": True,
            "target_year": True,
            "baseline_year": True,
            "reduction_pct": True,
            "raw_evidence": True,
        },
        mapping={
            "source_name": "source_name",
            "metadata_file": ("const", None),
            "document_path": "pdf_path",
            "source_page": "page_number",
            "source_row": ("const", None),
            "source_type": "source_type",
            "company_name": "company_name",
            "company_id": ("const", None),
            "company_url": ("const", None),
            "report_year": "report_year",
            "record_type": "record_type",
            "metric_name": "metric_name",
            "metric_key": _metric_key_from_metric_name,
            "scope": "scope",
            "category": ("const", None),
            "data_year": "data_year",
            "target_year": "target_year",
            "baseline_year": "baseline_year",
            "value": "value",
            "unit": "unit",
            "reduction_pct": "reduction_pct",
            "evidence_text": "raw_text",
        },
        notes="KRX PDF parser with emission/target extraction including baseline years.",
    ),
}


def available_sources() -> list[str]:
    return sorted(SOURCE_INVENTORY)


def get_source_inventory(source_name: str) -> SourceInventory:
    if source_name not in SOURCE_INVENTORY:
        raise KeyError(f"Unknown source_name: {source_name}")
    return SOURCE_INVENTORY[source_name]


def _resolve_mapping(df: pd.DataFrame, spec) -> pd.Series:
    if callable(spec):
        out = spec(df)
        return out if isinstance(out, pd.Series) else _series_const(df, out)
    if isinstance(spec, str):
        return _series_col(df, spec)
    if isinstance(spec, tuple):
        mode, payload = spec
        if mode == "const":
            return _series_const(df, payload)
        if mode == "coalesce":
            return _series_coalesce(df, list(payload))
    raise ValueError(f"Unsupported mapping spec: {spec!r}")


def to_common_schema(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    inventory = get_source_inventory(source_name)
    out = pd.DataFrame(index=df.index)

    for canonical_column in CANONICAL_COLUMNS:
        spec = inventory.mapping.get(canonical_column, ("const", None))
        out[canonical_column] = _resolve_mapping(df, spec)

    numeric_columns = ["report_year", "data_year", "target_year", "baseline_year", "value", "reduction_pct"]
    for column in numeric_columns:
        out[column] = pd.to_numeric(out[column], errors="coerce")

    return out[CANONICAL_COLUMNS]


def inventory_as_dict() -> dict:
    rows = []
    for name in available_sources():
        item = SOURCE_INVENTORY[name]
        rows.append(
            {
                "source_name": item.source_name,
                "output_columns": item.output_columns,
                "supports": item.supports,
                "notes": item.notes,
            }
        )
    return {
        "canonical_columns": CANONICAL_COLUMNS,
        "sources": rows,
    }


def inventory_as_json() -> str:
    return json.dumps(inventory_as_dict(), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    print(inventory_as_json())

