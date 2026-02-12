"""
NZDPU company parser.

Company-level table rows -> normalized carbon records.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import re

import pandas as pd

SOURCE_NAME = Path(__file__).resolve().parent.name
DEFAULT_INPUT_GLOB = "storage/raw/nzdpu-company/**/*.csv"

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

CARBON_HINTS = (
    "emission",
    "ghg",
    "scope",
    "co2",
    "carbon",
    "target",
    "reduction",
    "verification",
    "assurance",
    "온실",
    "배출",
    "탄소",
)

SCOPE_PATTERNS = [
    (re.compile(r"scope\s*1\s*[+&/,]\s*2\s*[+&/,]\s*3", re.I), "S1+2+3"),
    (re.compile(r"scope\s*1\s*[+&/,]\s*2", re.I), "S1+2"),
    (re.compile(r"scope\s*1", re.I), "S1"),
    (re.compile(r"scope\s*2", re.I), "S2"),
    (re.compile(r"scope\s*3", re.I), "S3"),
    (re.compile(r"direct\s*emissions|직접\s*배출", re.I), "S1"),
    (re.compile(r"indirect\s*emissions|간접\s*배출", re.I), "S2"),
    (re.compile(r"total\s*emissions|총\s*배출량|합계", re.I), "TOTAL"),
]

CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
VALUE_RE = re.compile(r"\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?")
UNIT_RE = re.compile(r"(t\s*co[₂2]\s*(?:eq|e)?|tco2eq|tco2e|kgco2e|gco2e|mwh|kwh|gwh|tj|%)", re.I)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
CAT_RE = re.compile(r"_ghgp_c(\d+)_", re.I)


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


def parse_value_unit(raw) -> tuple[float | None, str | None]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None, None
    text = str(raw).strip()
    if not text or text in {"-", "--", "—", "–", "nan"}:
        return None, None

    numbers = [to_float(m.group()) for m in VALUE_RE.finditer(text)]
    numbers = [n for n in numbers if n is not None]

    unit_match = UNIT_RE.search(text)
    unit = unit_match.group(1) if unit_match else None
    if unit:
        unit = unit.replace(" ", "").replace("co₂", "co2")
        unit = unit.replace("tco2eq", "tCO2e").replace("tco2e", "tCO2e")

    value = numbers[0] if numbers else None
    return value, unit


def infer_scope(text: str) -> str | None:
    for pattern, scope in SCOPE_PATTERNS:
        if pattern.search(text):
            return scope
    return None


def extract_year(text: str | None) -> int | None:
    if not text:
        return None
    years = [int(m.group()) for m in YEAR_RE.finditer(text)]
    years = [y for y in years if 1990 <= y <= 2100]
    return years[-1] if years else None


def extract_target_year(text: str | None, base_year: int | None) -> int | None:
    if not text:
        return None
    years = [int(m.group()) for m in YEAR_RE.finditer(text)]
    years = [y for y in years if 1990 <= y <= 2100]
    if not years:
        return None
    if base_year is None:
        return max(years)
    candidates = [y for y in years if y >= base_year]
    if candidates:
        return max(candidates)
    return max(years)


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


def row_is_carbon_related(row: pd.Series) -> bool:
    text = " ".join(
        str(row.get(k) or "")
        for k in ["group", "field_name", "data_key", "top_tab", "subtab", "value"]
    ).lower()
    return any(hint in text for hint in CARBON_HINTS)


def infer_record_type(row: pd.Series, context: str) -> str:
    top_tab = str(row.get("top_tab") or "").upper()
    subtab = str(row.get("subtab") or "").upper()
    if "TARGET" in top_tab or "TARGET" in subtab:
        return "target"
    if "PROGRESS" in subtab or "VALIDATION" in subtab:
        return "target"
    if "target" in context.lower() or "reduction" in context.lower():
        return "target"
    return "emission"


def infer_category(data_key: str | None) -> str | None:
    if not data_key:
        return None
    text = str(data_key)
    if text in {"", "nan", "None"}:
        return None
    match = CAT_RE.search(text)
    if match:
        return f"GHGP_C{match.group(1)}"
    return None


def parse_file(file: Path) -> list[dict]:
    df = pd.read_csv(file)
    records: list[dict] = []

    for idx, row in df.iterrows():
        row_no = idx + 2
        if str(row.get("row_type") or "").lower() not in {"item", "group"}:
            continue
        if not row_is_carbon_related(row):
            continue

        context = " ".join(
            str(row.get(k) or "")
            for k in ["group", "field_name", "data_key", "top_tab", "subtab", "value"]
        )
        record_type = infer_record_type(row, context)

        data_year = (
            extract_year(str(row.get("source") or ""))
            or extract_year(str(row.get("last_updated") or ""))
            or extract_year(str(row.get("page_url") or ""))
        )
        report_year = data_year
        target_year = extract_target_year(context, report_year) if record_type == "target" else None

        value, unit = parse_value_unit(row.get("value"))
        scope = infer_scope(context)
        category = infer_category(row.get("data_key"))

        confidence = "high"
        if value is None and record_type == "emission":
            confidence = "low"
        elif value is None and record_type == "target" and target_year is None:
            confidence = "low"
        elif (record_type == "emission" and (data_year is None or scope is None)) or (
            record_type == "target" and target_year is None
        ):
            confidence = "medium"

        records.append(
            {
                "source_name": SOURCE_NAME,
                "source_file": str(file),
                "source_row": row_no,
                "source_page": None,
                "company_name": row.get("company_name"),
                "company_id": row.get("company_id"),
                "company_url": row.get("company_url"),
                "country": "Unknown",
                "jurisdiction": None,
                "industry": None,
                "data_provider": None,
                "report_year": report_year,
                "data_year": data_year if record_type == "emission" else None,
                "target_year": target_year,
                "record_type": record_type,
                "scope": scope,
                "category": category,
                "metric_name": row.get("field_name") or row.get("group") or row.get("data_key"),
                "metric_key": row.get("data_key") or row.get("field_name"),
                "value": value,
                "unit": unit,
                "raw_value": row.get("value"),
                "top_tab": row.get("top_tab"),
                "subtab": row.get("subtab"),
                "row_type": row.get("row_type"),
                "confidence": confidence,
                "raw_text": context[:800],
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

    # keep target rows even without numeric value if they have target_year
    df = df[~((df["record_type"] == "emission") & (df["value"].isna()))]

    df["confidence_score"] = df["confidence"].map(CONFIDENCE_RANK).fillna(0).astype(int)
    df["quality_flags"] = df.apply(build_quality_flags, axis=1)
    df["needs_review"] = df["quality_flags"].ne("")
    df = df[df["confidence_score"] >= CONFIDENCE_RANK[min_confidence]]

    df = df.sort_values(["source_file", "source_row", "metric_key"], kind="stable")
    df = df.drop_duplicates(
        subset=["company_id", "top_tab", "subtab", "metric_key", "data_year", "target_year", "value", "unit"],
        keep="first",
    )
    return df[OUTPUT_COLUMNS].reset_index(drop=True)


def parse_args(repo_root: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NZDPU company carbon parser")
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
