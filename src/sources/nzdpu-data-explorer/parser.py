"""
NZDPU data explorer parser.

Wide metric CSV -> long-form carbon records.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import re

import pandas as pd

SOURCE_NAME = Path(__file__).resolve().parent.name
DEFAULT_INPUT_GLOB = "storage/raw/nzdpu-data-explorer/**/*.csv"

OUTPUT_COLUMNS = [
    "source_name",
    "source_file",
    "source_row",
    "source_page",
    "company_name",
    "company_id",
    "company_url",
    "country",
    "jurisdiction",
    "industry",
    "data_provider",
    "report_year",
    "data_year",
    "target_year",
    "record_type",
    "scope",
    "category",
    "metric_name",
    "metric_key",
    "value",
    "unit",
    "raw_value",
    "top_tab",
    "subtab",
    "row_type",
    "confidence",
    "confidence_score",
    "needs_review",
    "quality_flags",
    "raw_text",
]

META_COLUMNS = {
    "company_name",
    "reporting_year",
    "data_provider",
    "jurisdiction",
    "sics_sector",
    "company_url",
}

CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
VALUE_RE = re.compile(r"\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?")
UNIT_RE = re.compile(r"(t\s*co[₂2]\s*(?:eq|e)?|tco2eq|tco2e|kgco2e|gco2e)", re.IGNORECASE)
COMPANY_ID_RE = re.compile(r"/companies/(\d+)")
CATEGORY_RE = re.compile(r"_ghgp_c(\d+)_")


def find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "README.md").exists() and (parent / "src").exists():
            return parent
    return Path.cwd()


def resolve_path(path: Path, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def to_float(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "--", "—", "–", "nan", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_int(value) -> int | None:
    number = to_float(value)
    if number is None:
        return None
    if number.is_integer():
        return int(number)
    return None


def parse_value_unit(raw) -> tuple[float | None, str | None]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None, None
    text = str(raw).strip()
    if not text or text in {"-", "--", "—", "–"}:
        return None, None

    unit_match = UNIT_RE.search(text)
    unit = unit_match.group(1) if unit_match else None
    if unit:
        unit = unit.replace(" ", "").replace("co₂", "co2")
        unit = unit.replace("tco2eq", "tCO2e").replace("tco2e", "tCO2e")

    numbers = [to_float(m.group()) for m in VALUE_RE.finditer(text)]
    numbers = [n for n in numbers if n is not None]
    if not numbers:
        return None, unit
    return numbers[0], unit


def collect_input_files(args: argparse.Namespace, repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for raw in args.input_file:
        path = resolve_path(raw, repo_root)
        if path.exists() and path.is_file():
            files.append(path)

    if args.input_glob:
        files.extend(sorted(Path(repo_root).glob(args.input_glob)))

    if not files:
        files.extend(sorted((Path(__file__).resolve().parent / "output_example").glob("*.csv")))

    seen: set[str] = set()
    deduped: list[Path] = []
    for path in files:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def infer_scope(metric_key: str) -> str | None:
    key = metric_key.lower()
    if "s1" in key and "s2" in key and "s3" in key:
        return "S1+2+3"
    if "s1" in key and "s2" in key:
        return "S1+2"
    if "s1" in key:
        return "S1"
    if "s2" in key:
        return "S2"
    if "s3" in key:
        return "S3"
    return None


def infer_category(metric_key: str) -> str | None:
    match = CATEGORY_RE.search(metric_key.lower())
    if match:
        return f"GHGP_C{match.group(1)}"
    return None


def infer_record_type(metric_key: str) -> str:
    key = metric_key.lower()
    if "target" in key or "reduction" in key:
        return "target"
    return "emission"


def infer_metric_name(metric_key: str) -> str:
    text = metric_key.replace("_", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def extract_company_id(company_url: str | None) -> str | None:
    if not company_url:
        return None
    match = COMPANY_ID_RE.search(company_url)
    return match.group(1) if match else None


def parse_file(file: Path) -> list[dict]:
    df = pd.read_csv(file)
    records: list[dict] = []

    metric_cols = [c for c in df.columns if c not in META_COLUMNS]

    for idx, row in df.iterrows():
        row_no = idx + 2
        company_url = row.get("company_url")
        report_year = to_int(row.get("reporting_year"))

        base = {
            "source_name": SOURCE_NAME,
            "source_file": str(file),
            "source_row": row_no,
            "source_page": None,
            "company_name": row.get("company_name"),
            "company_id": extract_company_id(company_url),
            "company_url": company_url,
            "country": row.get("jurisdiction"),
            "jurisdiction": row.get("jurisdiction"),
            "industry": row.get("sics_sector"),
            "data_provider": row.get("data_provider"),
            "report_year": report_year,
            "data_year": report_year,
            "target_year": None,
            "top_tab": None,
            "subtab": None,
            "row_type": "item",
        }

        for metric_key in metric_cols:
            raw = row.get(metric_key)
            if raw is None or (isinstance(raw, float) and pd.isna(raw)):
                continue
            raw_text = str(raw).strip()
            if raw_text in {"", "-", "--", "—", "–", "nan"}:
                continue

            value, unit = parse_value_unit(raw)
            record_type = infer_record_type(metric_key)
            scope = infer_scope(metric_key)
            category = infer_category(metric_key)
            target_year = report_year if record_type == "target" else None

            confidence = "high"
            if value is None:
                confidence = "low"
            elif scope is None or unit is None:
                confidence = "medium"

            records.append(
                {
                    **base,
                    "record_type": record_type,
                    "scope": scope,
                    "category": category,
                    "metric_name": infer_metric_name(metric_key),
                    "metric_key": metric_key,
                    "value": value,
                    "unit": unit,
                    "raw_value": raw,
                    "target_year": target_year,
                    "confidence": confidence,
                    "raw_text": f"metric={metric_key} raw={raw_text}",
                }
            )

    return records


def build_quality_flags(row: pd.Series) -> str:
    flags: list[str] = []
    if row.get("record_type") == "emission":
        if pd.isna(row.get("data_year")):
            flags.append("missing_data_year")
        if pd.isna(row.get("scope")):
            flags.append("missing_scope")
        if pd.isna(row.get("value")):
            flags.append("missing_value")
        if pd.isna(row.get("unit")):
            flags.append("missing_unit")
    else:
        if pd.isna(row.get("target_year")):
            flags.append("missing_target_year")
        if pd.isna(row.get("value")):
            flags.append("missing_target_value")
    return ";".join(flags)


def records_to_frame(records: list[dict], min_confidence: str) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    df = pd.DataFrame(records)
    for col in OUTPUT_COLUMNS:
        if col not in df.columns:
            df[col] = None

    df["confidence_score"] = df["confidence"].map(CONFIDENCE_RANK).fillna(0).astype(int)
    df["quality_flags"] = df.apply(build_quality_flags, axis=1)
    df["needs_review"] = df["quality_flags"].ne("")
    df = df[df["confidence_score"] >= CONFIDENCE_RANK[min_confidence]]

    df = df.sort_values(["source_file", "source_row", "metric_key"], kind="stable")
    df = df.drop_duplicates(
        subset=["company_id", "report_year", "metric_key", "value", "unit"],
        keep="first",
    )
    return df[OUTPUT_COLUMNS].reset_index(drop=True)


def parse_args(repo_root: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NZDPU data explorer carbon parser")
    parser.add_argument("--input-file", action="append", type=Path, default=[])
    parser.add_argument("--input-glob", default=DEFAULT_INPUT_GLOB)
    parser.add_argument("--min-confidence", choices=["low", "medium", "high"], default="low")

    parser.add_argument("--run-date", help="Output partition date (YYYY-MM-DD)")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--output-file", type=Path)
    parser.add_argument("--output-format", choices=["csv", "parquet"], default="csv")
    args = parser.parse_args()

    if args.run_date:
        try:
            datetime.strptime(args.run_date, "%Y-%m-%d")
        except ValueError as exc:
            parser.error(f"--run-date must be YYYY-MM-DD: {exc}")

    if args.output_dir:
        args.output_dir = resolve_path(args.output_dir, repo_root)
    if args.output_file:
        args.output_file = resolve_path(args.output_file, repo_root)
    return args


def resolve_output_file(args: argparse.Namespace, repo_root: Path) -> Path:
    if args.output_file:
        output = args.output_file
    else:
        run_date = args.run_date or datetime.now().strftime("%Y-%m-%d")
        out_dir = args.output_dir or (repo_root / "storage" / "parsed" / SOURCE_NAME / run_date)
        ext = "parquet" if args.output_format == "parquet" else "csv"
        output = out_dir / f"carbon_records.{ext}"
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def save_output(df: pd.DataFrame, output_file: Path, output_format: str) -> None:
    if output_format == "parquet" or output_file.suffix.lower() == ".parquet":
        df.to_parquet(output_file, index=False)
    else:
        df.to_csv(output_file, index=False, encoding="utf-8-sig")


def run(args: argparse.Namespace, repo_root: Path) -> Path:
    files = collect_input_files(args, repo_root)
    records: list[dict] = []

    for i, file in enumerate(files, start=1):
        print(f"[{i}/{len(files)}] parse: {file}")
        try:
            records.extend(parse_file(file))
        except Exception as exc:
            print(f"  error: {exc!r}")

    df = records_to_frame(records, min_confidence=args.min_confidence)
    output = resolve_output_file(args, repo_root)
    save_output(df, output, args.output_format)
    print(f"saved: {output} rows={len(df)}")
    return output


def main() -> None:
    repo_root = find_repo_root()
    args = parse_args(repo_root)
    run(args, repo_root)


if __name__ == "__main__":
    main()
