# Source Field Inventory

This document tracks what each source parser can currently extract and how it maps to a common integration-ready shape.

## Canonical Columns (Draft)

- `source_name`
- `metadata_file`
- `document_path`
- `source_page`
- `source_row`
- `source_type`
- `company_name`
- `company_id`
- `company_url`
- `report_year`
- `record_type`
- `metric_name`
- `metric_key`
- `scope`
- `category`
- `data_year`
- `target_year`
- `baseline_year`
- `value`
- `unit`
- `reduction_pct`
- `evidence_text`

## Source Coverage Summary

| source | emission | target | scope | data_year | target_year | baseline_year | reduction_pct |
|---|---|---|---|---|---|---|---|
| `gir-kor` | yes | no | no | yes | no | no | no |
| `nzdpu-data-explorer` | yes | partial (metric-key based) | yes | yes | no | no | no |
| `nzdpu-company` | yes | yes | yes | yes | yes | no | no |
| `jpx-esgdata` | yes | yes | yes | yes | yes | no | yes |
| `krx-esg` | yes | yes | yes | yes | yes | yes | yes |

## Source Notes

### `gir-kor`
- Input is structured CSV.
- Main carbon metric: `ghg_tco2eq` (`metric_key`).
- Also includes `energy_tj` as activity context.
- No explicit scope or target fields.

### `nzdpu-data-explorer`
- Input is wide CSV and parser expands metrics into long rows.
- Scope and GHGP category are inferred from `metric_key`.
- Target-like rows may appear when metric keys contain target/reduction terms.

### `nzdpu-company`
- Input is company detail CSV with item/group row types.
- Supports emission and target rows through `record_type`.
- `target_year` is parsed from row context, `data_year` from source metadata strings.
- Good contextual fields: `top_tab`, `subtab`, `data_key`, `field_name`.

### `jpx-esgdata`
- Input is PDF with optional metadata CSV.
- Extracts both text and table evidence (`source_type`).
- Supports `reduction_pct`, `scope`, `data_year`, `target_year`.
- `source_file` is metadata CSV path when metadata is used.

### `krx-esg`
- Input is PDF with metadata fallback.
- Supports emission/target plus `baseline_year`.
- Includes page-level evidence text and source type (`text`, `table`, `text_window`).

## Code Reference

- Inventory and mapping code: `src/transforms/source_inventory.py`
- Main function for common projection: `to_common_schema(df, source_name)`

