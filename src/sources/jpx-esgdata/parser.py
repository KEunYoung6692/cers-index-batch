"""
JPX ESGData parser.

Metadata/PDF inputs -> normalized carbon records.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re

import pandas as pd

SOURCE_NAME = Path(__file__).resolve().parent.name
DEFAULT_METADATA_GLOB = "storage/raw/jpx-esgdata/*/metadata.csv"

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

CARBON_PAGE_KEYWORDS = (
    "温室効果ガス",
    "排出",
    "排出量",
    "co2",
    "co₂",
    "ghg",
    "scope",
    "スコープ",
    "脱炭素",
    "カーボン",
    "ネットゼロ",
    "削減",
    "目標",
    "carbon",
    "net zero",
)

EMISSION_KEYWORDS = (
    "温室効果ガス",
    "排出量",
    "ghg",
    "emission",
    "scope",
    "スコープ",
    "co2",
    "co₂",
    "総排出",
    "合計",
)

TARGET_KEYWORDS = (
    "目標",
    "削減",
    "ロードマップ",
    "ネットゼロ",
    "カーボンニュートラル",
    "net zero",
    "carbon neutral",
)

SCOPE_PATTERNS = [
    (re.compile(r"(scope|スコープ)\s*1\s*[+&/,]\s*2\s*[+&/,]\s*3", re.I), "S1+2+3"),
    (re.compile(r"(scope|スコープ)\s*1\s*[+&/,]\s*2", re.I), "S1+2"),
    (re.compile(r"(scope|スコープ)\s*1", re.I), "S1"),
    (re.compile(r"(scope|スコープ)\s*2", re.I), "S2"),
    (re.compile(r"(scope|スコープ)\s*3", re.I), "S3"),
    (re.compile(r"直接\s*排出", re.I), "S1"),
    (re.compile(r"間接\s*排出", re.I), "S2"),
    (re.compile(r"その他\s*間接\s*排出|サプライチェーン", re.I), "S3"),
    (re.compile(r"総排出|合計|total", re.I), "TOTAL"),
]

CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
YEAR_JP_RE = re.compile(r"(?P<year>(19|20)\d{2})\s*年")
NUMBER_RE = re.compile(r"\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?")
PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
UNIT_RE = re.compile(r"(t\s*-?\s*co[₂2]\s*(?:eq|e)?|tco2eq|tco2e|kgco2e|gco2e|千t\s*-?\s*co2e?|万t\s*-?\s*co2e?)", re.I)


@dataclass
class PdfTask:
    pdf_path: Path
    company_name: str | None
    company_id: str | None
    company_url: str | None
    report_year: int | None
    source_file: str | None = None


def find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "README.md").exists() and (parent / "src").exists():
            return parent
    return Path.cwd()


def resolve_path(path: Path, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def to_float(text) -> float | None:
    if text is None:
        return None
    s = str(text).strip().replace(",", "")
    if s in {"", "-", "--", "—", "–", "nan", "None"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(k.lower() in lowered for k in keywords)


def infer_scope(text: str) -> str | None:
    for pattern, scope in SCOPE_PATTERNS:
        if pattern.search(text):
            return scope
    return None


def extract_years(text: str) -> list[int]:
    years = [int(m.group()) for m in YEAR_RE.finditer(text)]
    years.extend(int(m.group("year")) for m in YEAR_JP_RE.finditer(text))
    return sorted({y for y in years if 1990 <= y <= 2100})


def extract_unit(text: str) -> str | None:
    m = UNIT_RE.search(text)
    if not m:
        return None
    u = m.group(1).replace(" ", "")
    u = u.replace("co₂", "co2")
    u = u.replace("tco2eq", "tCO2e").replace("tco2e", "tCO2e")
    return u


def extract_numbers(text: str, *, drop_years: bool = True, drop_percent: bool = False) -> list[float]:
    values: list[float] = []
    for m in NUMBER_RE.finditer(text):
        end = m.end()
        if drop_percent and "%" in text[end : end + 2]:
            continue
        v = to_float(m.group())
        if v is None:
            continue
        if drop_years and v.is_integer() and 1990 <= int(v) <= 2100:
            continue
        values.append(v)
    return values


def confidence_for_emission(data_year: int | None, scope: str | None, value: float | None, unit: str | None) -> str:
    if value is not None and data_year is not None and scope is not None and unit is not None:
        return "high"
    if value is not None and (data_year is not None or scope is not None):
        return "medium"
    return "low"


def confidence_for_target(target_year: int | None, pct: float | None, value: float | None) -> str:
    if target_year is not None and (pct is not None or value is not None):
        return "high"
    if target_year is not None or pct is not None or value is not None:
        return "medium"
    return "low"


def parse_emission_line(*, line: str, context: str, task: PdfTask, page_num: int, source_type: str) -> list[dict]:
    if not contains_any(line, EMISSION_KEYWORDS):
        return []
    if not contains_any(context, CARBON_PAGE_KEYWORDS):
        return []

    scope = infer_scope(line)
    unit = extract_unit(context)
    years = extract_years(context)
    values = extract_numbers(line, drop_years=True, drop_percent=True)
    if not values:
        return []

    metric_name = "온실가스 배출량"
    if "検証" in line or "verification" in line.lower():
        metric_name = "검증 배출량"
    elif "intensity" in line.lower() or "原単位" in line:
        metric_name = "온실가스 집약도"

    records: list[dict] = []
    if years and len(values) >= len(years):
        use_values = values[-len(years) :]
        for year, value in zip(years, use_values):
            records.append(
                {
                    "source_name": SOURCE_NAME,
                    "source_file": task.source_file or str(task.pdf_path),
                    "source_row": None,
                    "source_page": page_num,
                    "company_name": task.company_name,
                    "company_id": task.company_id,
                    "company_url": task.company_url,
                    "country": "JP",
                    "jurisdiction": "Japan",
                    "industry": None,
                    "data_provider": "JPX ESGData",
                    "report_year": task.report_year,
                    "data_year": year,
                    "target_year": None,
                    "record_type": "emission",
                    "scope": scope,
                    "category": None,
                    "metric_name": metric_name,
                    "metric_key": metric_name,
                    "value": value,
                    "unit": unit,
                    "raw_value": line,
                    "top_tab": None,
                    "subtab": None,
                    "row_type": source_type,
                    "confidence": confidence_for_emission(year, scope, value, unit),
                    "raw_text": line[:800],
                }
            )
        return records

    data_year = task.report_year
    line_years = extract_years(line)
    if line_years:
        data_year = line_years[-1]

    value = values[-1]
    records.append(
        {
            "source_name": SOURCE_NAME,
            "source_file": task.source_file or str(task.pdf_path),
            "source_row": None,
            "source_page": page_num,
            "company_name": task.company_name,
            "company_id": task.company_id,
            "company_url": task.company_url,
            "country": "JP",
            "jurisdiction": "Japan",
            "industry": None,
            "data_provider": "JPX ESGData",
            "report_year": task.report_year,
            "data_year": data_year,
            "target_year": None,
            "record_type": "emission",
            "scope": scope,
            "category": None,
            "metric_name": metric_name,
            "metric_key": metric_name,
            "value": value,
            "unit": unit,
            "raw_value": line,
            "top_tab": None,
            "subtab": None,
            "row_type": source_type,
            "confidence": confidence_for_emission(data_year, scope, value, unit),
            "raw_text": line[:800],
        }
    )
    return records


def parse_target_text(*, text: str, task: PdfTask, page_num: int, source_type: str) -> list[dict]:
    if not contains_any(text, TARGET_KEYWORDS):
        return []
    if not contains_any(text, CARBON_PAGE_KEYWORDS):
        return []

    years = extract_years(text)
    target_years = sorted({y for y in years if y >= 1990})

    pct_values = [to_float(m.group(1)) for m in PCT_RE.finditer(text)]
    pct_values = [p for p in pct_values if p is not None and 0 <= p <= 100]
    reduction_pct = max(pct_values) if pct_values else None

    unit = extract_unit(text)
    value = None
    if unit and contains_any(text, ("target", "目標", "削減")):
        nums = extract_numbers(text, drop_years=True, drop_percent=True)
        if nums:
            value = nums[0]

    if not target_years and reduction_pct is None and value is None:
        return []

    scope = infer_scope(text)
    out: list[dict] = []
    years_for_emit = target_years or [None]
    for target_year in years_for_emit:
        out.append(
            {
                "source_name": SOURCE_NAME,
                "source_file": task.source_file or str(task.pdf_path),
                "source_row": None,
                "source_page": page_num,
                "company_name": task.company_name,
                "company_id": task.company_id,
                "company_url": task.company_url,
                "country": "JP",
                "jurisdiction": "Japan",
                "industry": None,
                "data_provider": "JPX ESGData",
                "report_year": task.report_year,
                "data_year": None,
                "target_year": target_year,
                "record_type": "target",
                "scope": scope,
                "category": None,
                "metric_name": "온실가스 감축 목표",
                "metric_key": "target",
                "value": value,
                "unit": unit,
                "raw_value": text,
                "top_tab": None,
                "subtab": None,
                "row_type": source_type,
                "confidence": confidence_for_target(target_year, reduction_pct, value),
                "raw_text": text[:800],
            }
        )
        out[-1]["category"] = f"reduction_pct={reduction_pct}" if reduction_pct is not None else None
    return out


def extract_tables_from_page(page) -> list[list[list[str]]]:
    tables: list[list[list[str]]] = []
    settings_candidates = [
        None,
        {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
        {"vertical_strategy": "text", "horizontal_strategy": "text"},
    ]
    seen: set[tuple[tuple[str, ...], ...]] = set()
    for settings in settings_candidates:
        try:
            extracted = page.extract_tables() if settings is None else page.extract_tables(settings)
        except Exception:
            continue
        for table in extracted or []:
            normalized = [[norm_ws(str(cell)) if cell is not None else "" for cell in row] for row in (table or [])]
            key = tuple(tuple(r) for r in normalized)
            if key in seen:
                continue
            seen.add(key)
            tables.append(normalized)
    return tables


def parse_pdf(task: PdfTask, max_pages: int | None) -> list[dict]:
    try:
        import pdfplumber
    except ModuleNotFoundError as exc:
        raise RuntimeError("pdfplumber is required. Install with: pip install pdfplumber") from exc

    records: list[dict] = []
    with pdfplumber.open(task.pdf_path) as pdf:
        limit = min(len(pdf.pages), max_pages) if max_pages else len(pdf.pages)
        for page_idx in range(limit):
            page = pdf.pages[page_idx]
            page_num = page_idx + 1
            text = page.extract_text() or ""
            if not contains_any(text, CARBON_PAGE_KEYWORDS):
                continue

            lines = [norm_ws(line) for line in text.splitlines() if norm_ws(line)]
            for i, line in enumerate(lines):
                ctx = " ".join(lines[max(0, i - 2) : min(len(lines), i + 3)])
                records.extend(parse_emission_line(line=line, context=ctx, task=task, page_num=page_num, source_type="text"))

                target_window = " ".join(lines[i : min(len(lines), i + 2)])
                records.extend(parse_target_text(text=target_window, task=task, page_num=page_num, source_type="text"))

            tables = extract_tables_from_page(page)
            for table in tables:
                for row in table:
                    row_text = norm_ws(" ".join(c for c in row if c))
                    if not row_text:
                        continue
                    records.extend(
                        parse_emission_line(
                            line=row_text,
                            context=row_text,
                            task=task,
                            page_num=page_num,
                            source_type="table",
                        )
                    )
                    records.extend(parse_target_text(text=row_text, task=task, page_num=page_num, source_type="table"))

    return records


def parse_metadata_file(metadata_file: Path) -> list[PdfTask]:
    tasks: list[PdfTask] = []
    if not metadata_file.exists():
        return tasks

    df = pd.read_csv(metadata_file)
    for _, row in df.iterrows():
        status = str(row.get("download_status") or "").lower().strip()
        if status and status != "success":
            continue

        downloaded_file = row.get("downloaded_file")
        if not isinstance(downloaded_file, str) or not downloaded_file.strip():
            continue

        rel = Path(downloaded_file)
        candidates = [
            metadata_file.parent / rel,
            metadata_file.parent / "pdfs" / rel.name,
        ]
        pdf_path = next((p for p in candidates if p.exists()), None)
        if pdf_path is None:
            continue

        date_text = str(row.get("date") or "")
        report_year = None
        years = extract_years(date_text)
        if years:
            report_year = years[0]

        tasks.append(
            PdfTask(
                pdf_path=pdf_path,
                company_name=row.get("company"),
                company_id=str(row.get("code")) if pd.notna(row.get("code")) else None,
                company_url=row.get("pdf_url"),
                report_year=report_year,
                source_file=str(metadata_file),
            )
        )

    return tasks


def collect_tasks(args: argparse.Namespace, repo_root: Path) -> list[PdfTask]:
    tasks: list[PdfTask] = []

    metadata_files: list[Path] = [resolve_path(p, repo_root) for p in args.metadata_csv]
    if args.metadata_glob:
        metadata_files.extend(sorted(Path(repo_root).glob(args.metadata_glob)))

    for metadata in metadata_files:
        try:
            tasks.extend(parse_metadata_file(metadata))
        except Exception as exc:
            print(f"metadata parse error: {metadata} -> {exc!r}")

    for group in args.pdf_path:
        for raw in group:
            pdf = resolve_path(Path(raw), repo_root)
            if pdf.exists() and pdf.is_file():
                tasks.append(PdfTask(pdf_path=pdf, company_name=None, company_id=None, company_url=None, report_year=None))

    for raw_dir in args.pdf_dir:
        d = resolve_path(raw_dir, repo_root)
        if not d.exists():
            continue
        pattern = "**/*.pdf" if args.recursive else "*.pdf"
        for pdf in d.glob(pattern):
            tasks.append(PdfTask(pdf_path=pdf, company_name=None, company_id=None, company_url=None, report_year=None))

    if not tasks:
        sample_dir = Path(__file__).resolve().parent / "output_example"
        if sample_dir.exists():
            for pdf in sorted(sample_dir.glob("*.pdf")):
                tasks.append(PdfTask(pdf_path=pdf, company_name=None, company_id=None, company_url=None, report_year=None))

    seen: set[str] = set()
    deduped: list[PdfTask] = []
    for task in tasks:
        key = str(task.pdf_path.resolve())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(task)
    return deduped


def build_quality_flags(row: pd.Series) -> str:
    flags: list[str] = []
    if row.get("record_type") == "emission":
        if pd.isna(row.get("data_year")):
            flags.append("missing_data_year")
        if pd.isna(row.get("scope")):
            flags.append("missing_scope")
        if pd.isna(row.get("unit")):
            flags.append("missing_unit")
    else:
        if pd.isna(row.get("target_year")):
            flags.append("missing_target_year")
        if pd.isna(row.get("value")) and (not isinstance(row.get("category"), str) or "reduction_pct=" not in str(row.get("category"))):
            flags.append("missing_target_value")
    return ";".join(flags)


def records_to_frame(records: list[dict], min_confidence: str) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    df = pd.DataFrame(records)
    for col in OUTPUT_COLUMNS:
        if col not in df.columns:
            df[col] = None

    df = df[~((df["record_type"] == "emission") & (df["value"].isna()))]

    df["confidence_score"] = df["confidence"].map(CONFIDENCE_RANK).fillna(0).astype(int)
    df["quality_flags"] = df.apply(build_quality_flags, axis=1)
    df["needs_review"] = df["quality_flags"].ne("")
    df = df[df["confidence_score"] >= CONFIDENCE_RANK[min_confidence]]

    # Split reduction pct in category into separate numeric where possible
    pct = df["category"].astype("string").str.extract(r"reduction_pct=(\d+(?:\.\d+)?)", expand=False)
    pct = pd.to_numeric(pct, errors="coerce")
    df.loc[(df["record_type"] == "target") & df["value"].isna() & pct.notna(), "value"] = pct
    df.loc[(df["record_type"] == "target") & df["metric_name"].eq("온실가스 감축 목표") & df["unit"].isna() & pct.notna(), "unit"] = "%"

    df = df.sort_values(["source_file", "source_page", "record_type", "scope", "data_year", "target_year"], kind="stable")
    df = df.drop_duplicates(
        subset=["source_file", "source_page", "record_type", "scope", "metric_name", "data_year", "target_year", "value", "unit"],
        keep="first",
    )
    return df[OUTPUT_COLUMNS].reset_index(drop=True)


def parse_args(repo_root: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JPX ESGData carbon parser")
    parser.add_argument("--metadata-csv", action="append", type=Path, default=[])
    parser.add_argument("--metadata-glob", default=DEFAULT_METADATA_GLOB)
    parser.add_argument("--pdf-path", action="append", nargs="+", default=[])
    parser.add_argument("--pdf-dir", action="append", type=Path, default=[])
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--min-confidence", choices=["low", "medium", "high"], default="low")

    parser.add_argument("--run-date", help="Output partition date (YYYY-MM-DD)")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--output-file", type=Path)
    parser.add_argument("--output-format", choices=["csv", "parquet"], default="csv")
    args = parser.parse_args()

    if args.max_pages is not None and args.max_pages < 1:
        parser.error("--max-pages must be >= 1")
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
    tasks = collect_tasks(args, repo_root)
    records: list[dict] = []

    for i, task in enumerate(tasks, start=1):
        print(f"[{i}/{len(tasks)}] parse: {task.pdf_path}")
        try:
            records.extend(parse_pdf(task, max_pages=args.max_pages))
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
