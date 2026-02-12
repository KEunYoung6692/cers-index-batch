"""
GIR-KOR carbon parser.

Raw CSV -> normalized carbon records.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import re

import pandas as pd

SOURCE_NAME = Path(__file__).resolve().parent.name
DEFAULT_INPUT_GLOB = "storage/raw/gir-kor/**/*.csv"

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

CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


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


def collect_input_files(args: argparse.Namespace, repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for raw in args.input_file:
        path = resolve_path(raw, repo_root)
        if path.exists() and path.is_file():
            files.append(path)

    if args.input_glob:
        files.extend(sorted(Path(repo_root).glob(args.input_glob)))

    # local examples fallback
    if not files:
        files.extend(sorted((Path(__file__).resolve().parent / "output-example").glob("*.csv")))

    seen: set[str] = set()
    deduped: list[Path] = []
    for path in files:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def make_record_base(*, file: Path, row_no: int, row: pd.Series) -> dict:
    year = to_int(row.get("year"))
    return {
        "source_name": SOURCE_NAME,
        "source_file": str(file),
        "source_row": row_no,
        "source_page": None,
        "company_name": row.get("corp_name"),
        "company_id": row.get("stock_code"),
        "company_url": None,
        "country": "KR",
        "jurisdiction": "Korea",
        "industry": row.get("industry"),
        "data_provider": "GIR-KOR",
        "report_year": year,
        "data_year": year,
        "target_year": None,
        "top_tab": None,
        "subtab": None,
        "row_type": "item",
        "raw_text": f"agency={row.get('agency')} verifier={row.get('verifier')} remark={row.get('remark')}",
    }


def parse_file(file: Path) -> list[dict]:
    df = pd.read_csv(file)
    records: list[dict] = []

    for idx, row in df.iterrows():
        row_no = idx + 2
        base = make_record_base(file=file, row_no=row_no, row=row)

        ghg = to_float(row.get("ghg_tco2eq"))
        if ghg is not None:
            records.append(
                {
                    **base,
                    "record_type": "emission",
                    "scope": "TOTAL",
                    "category": "facility",
                    "metric_name": "온실가스 배출량",
                    "metric_key": "ghg_tco2eq",
                    "value": ghg,
                    "unit": "tCO2e",
                    "raw_value": row.get("ghg_tco2eq"),
                    "confidence": "high" if base["data_year"] is not None else "medium",
                }
            )

        # energy is relevant context for emissions
        energy = to_float(row.get("energy_tj"))
        if energy is not None:
            records.append(
                {
                    **base,
                    "record_type": "emission",
                    "scope": None,
                    "category": "energy",
                    "metric_name": "에너지 사용량",
                    "metric_key": "energy_tj",
                    "value": energy,
                    "unit": "TJ",
                    "raw_value": row.get("energy_tj"),
                    "confidence": "medium",
                }
            )

    return records


def build_quality_flags(row: pd.Series) -> str:
    flags: list[str] = []
    if pd.isna(row.get("data_year")):
        flags.append("missing_data_year")
    if pd.isna(row.get("value")):
        flags.append("missing_value")
    if pd.isna(row.get("unit")):
        flags.append("missing_unit")
    if pd.isna(row.get("scope")):
        flags.append("missing_scope")
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
        subset=["source_file", "source_row", "metric_key", "value", "unit", "scope"],
        keep="first",
    )
    return df[OUTPUT_COLUMNS].reset_index(drop=True)


def parse_args(repo_root: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GIR-KOR carbon parser")
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
