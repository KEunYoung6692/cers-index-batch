"""
KRX ESG PDF parser for carbon-related records.

Extracts:
- emission rows (Scope 1/2/3, Scope 1+2, total, intensity, etc.)
- target rows (carbon neutrality, reduction targets, target year, baseline year, reduction %)
"""

from __future__ import annotations

import argparse
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

SOURCE_NAME = Path(__file__).resolve().parent.name

DEFAULT_METADATA_GLOB = "storage/raw/krx-esg/reports/*/metadata.csv"

CARBON_PAGE_KEYWORDS = (
    "온실가스",
    "탄소",
    "배출",
    "scope",
    "tco2",
    "co2e",
    "ghg",
    "net zero",
    "carbon negative",
    "탄소중립",
    "감축",
    "기후",
)

EMISSION_KEYWORDS = (
    "배출량",
    "직접배출",
    "간접배출",
    "총량",
    "scope",
    "집약도",
    "tco2",
    "co2e",
    "검증 범위",
)

TARGET_KEYWORDS = (
    "감축 목표",
    "배출량 목표",
    "배출목표",
    "목표량",
    "감축",
    "로드맵",
    "탄소중립",
    "net zero",
    "carbon negative",
)

YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
YEAR_KR_RE = re.compile(r"\b(?P<year>(19|20)\d{2})\s*년\b")
NUMBER_RE = re.compile(r"\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?")
PERCENT_RE = re.compile(r"(?P<pct>\d+(?:\.\d+)?)\s*%")
UNIT_RE = re.compile(
    r"(t\s*co[₂2]\s*(?:eq|e)?|tco2eq|tco2e|kgco2e|kgco2eq|gco2e|mwh|kwh|gwh|tj|ton|톤)",
    flags=re.IGNORECASE,
)
BASELINE_YEAR_RE = re.compile(r"기준연도(?:인)?\s*(?P<year>(19|20)\d{2})\s*년")
TARGET_YEAR_CONTEXT_RE = re.compile(
    r"(?P<year>(19|20)\d{2})\s*년(?=[^.\n]{0,24}(?:목표|달성|중립|감축|까지|scope|net\s*zero|carbon\s*negative))",
    flags=re.IGNORECASE,
)
DATE_TOKEN_RE = re.compile(r"\b\d{4}[./-]\d{1,2}[./-]\d{1,2}\b")
HYPHEN_CODE_RE = re.compile(r"\b[A-Za-z]?\d{1,4}-\d{1,3}\b")
SCENARIO_CODE_RE = re.compile(r"\b[A-Za-z]{2,}\d?-\d+(?:\.\d+)?\b")

NAVIGATION_MARKERS = (
    "목차화면으로 이동",
    "홈 화면으로 이동",
    "이전페이지",
    "다음페이지",
    "연관 링크 이동",
    "이전 상태로 이동",
)

SCOPE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"scope\s*1\s*[\+&,/]\s*2\s*[\+&,/]\s*3", re.IGNORECASE), "S1+2+3"),
    (re.compile(r"scope\s*1\s*[\+&,/]\s*2", re.IGNORECASE), "S1+2"),
    (re.compile(r"scope\s*1", re.IGNORECASE), "S1"),
    (re.compile(r"scope\s*2", re.IGNORECASE), "S2"),
    (re.compile(r"scope\s*3", re.IGNORECASE), "S3"),
    (re.compile(r"기타\s*간접\s*배출"), "S3"),
    (re.compile(r"직접\s*배출"), "S1"),
    (re.compile(r"간접\s*배출"), "S2"),
    (re.compile(r"총\s*온실가스\s*배출량|총량|합계|총배출량"), "TOTAL"),
]

UNIT_NORMALIZATION = {
    "tco2e": "tCO2e",
    "tco2eq": "tCO2e",
    "tco₂e": "tCO2e",
    "tco₂eq": "tCO2e",
    "kgco2e": "kgCO2e",
    "kgco2eq": "kgCO2e",
    "gco2e": "gCO2e",
    "mwh": "MWh",
    "kwh": "kWh",
    "gwh": "GWh",
    "tj": "TJ",
    "ton": "ton",
    "톤": "ton",
}

OUTPUT_COLUMNS = [
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
]


@dataclass
class PdfTask:
    pdf_path: Path
    company_name: str | None = None
    report_year: int | None = None


@dataclass
class CarbonRecord:
    source_name: str
    pdf_path: str
    file_name: str
    company_name: str | None
    report_year: int | None
    page_number: int
    record_type: str
    metric_name: str
    scope: str | None
    data_year: int | None
    target_year: int | None
    baseline_year: int | None
    value: float | None
    reduction_pct: float | None
    unit: str | None
    source_type: str
    confidence: str
    raw_text: str


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


def to_float(raw: str) -> float | None:
    text = (raw or "").strip().replace(",", "")
    if not text:
        return None
    if text in {"-", "—", "–", "N/A", "NA"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def infer_scope(text: str) -> str | None:
    lowered = text.lower()
    for pattern, scope in SCOPE_PATTERNS:
        if pattern.search(lowered):
            return scope
    return None


def extract_years(text: str) -> list[int]:
    years = [int(m.group()) for m in YEAR_RE.finditer(text)]
    return sorted({y for y in years if 1990 <= y <= 2100})


def extract_unit(text: str) -> str | None:
    match = UNIT_RE.search(text)
    if not match:
        return None
    token = match.group(1).lower().replace(" ", "")
    token = token.replace("co₂", "co2")
    return UNIT_NORMALIZATION.get(token, match.group(1))


def extract_numbers(
    text: str,
    *,
    drop_years: bool = True,
    drop_percent: bool = False,
    drop_scope_digits: bool = True,
) -> list[float]:
    scrubbed = text
    scrubbed = DATE_TOKEN_RE.sub(" ", scrubbed)
    scrubbed = HYPHEN_CODE_RE.sub(" ", scrubbed)
    scrubbed = SCENARIO_CODE_RE.sub(" ", scrubbed)
    if drop_scope_digits:
        scrubbed = re.sub(r"scope\s*\d(?:\s*[\+&,/]\s*\d+)*", " ", scrubbed, flags=re.IGNORECASE)
        scrubbed = re.sub(r"\b[CS]\s*\d+\b", " ", scrubbed, flags=re.IGNORECASE)
    numbers: list[float] = []
    for m in NUMBER_RE.finditer(scrubbed):
        token = m.group()
        if drop_percent:
            tail = scrubbed[m.end() : m.end() + 2]
            if "%" in tail:
                continue
        value = to_float(token)
        if value is None:
            continue
        if drop_years and value.is_integer() and 1990 <= int(value) <= 2100:
            continue
        numbers.append(value)
    return numbers


def contains_any(text: str, keywords: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def is_noise_line(text: str) -> bool:
    lowered = text.lower()
    if any(marker in lowered for marker in NAVIGATION_MARKERS):
        return True
    if "index" in lowered and len(extract_numbers(text, drop_years=False, drop_percent=False)) >= 2:
        return True
    if "gri" in lowered and HYPHEN_CODE_RE.search(text):
        return True
    return False


def has_target_intent(text: str) -> bool:
    lowered = text.lower()
    if ("탄소중립" in lowered or "carbon negative" in lowered or "net zero" in lowered) and contains_any(
        lowered, ("목표", "달성", "로드맵", "전략", "이행")
    ):
        return True
    if re.search(r"(온실가스|배출량|scope).{0,16}(목표|감축|달성)", lowered):
        return True
    if re.search(r"(목표|감축|달성).{0,16}(온실가스|배출량|scope)", lowered):
        return True
    return False


def find_nearby_year_header(lines: list[str], index: int) -> list[int]:
    for distance in range(0, 4):
        j = index - distance
        if j < 0:
            break
        years = extract_years(lines[j])
        if len(years) >= 2:
            return years
    return []


def infer_metric_name(text: str, record_type: str) -> str:
    lowered = text.lower()
    if "집약도" in lowered:
        return "온실가스 집약도"
    if "검증" in lowered and ("배출" in lowered or "scope" in lowered):
        return "검증 배출량"
    if record_type == "target":
        if "탄소중립" in lowered or "net zero" in lowered or "carbon negative" in lowered:
            return "탄소중립 목표"
        if "감축" in lowered:
            return "온실가스 감축 목표"
        return "온실가스 목표"
    return "온실가스 배출량"


def confidence_for_emission(*, data_year: int | None, scope: str | None, value: float | None) -> str:
    if data_year is not None and scope is not None and value is not None:
        return "high"
    if value is not None and (data_year is not None or scope is not None):
        return "medium"
    return "low"


def confidence_for_target(
    *,
    target_year: int | None,
    baseline_year: int | None,
    reduction_pct: float | None,
    value: float | None,
) -> str:
    if target_year is not None and (reduction_pct is not None or value is not None):
        return "high"
    if target_year is not None or baseline_year is not None or reduction_pct is not None:
        return "medium"
    return "low"


def parse_target_from_window(
    *,
    window_text: str,
    task: PdfTask,
    page_number: int,
    source_type: str,
) -> list[CarbonRecord]:
    if is_noise_line(window_text):
        return []
    if not contains_any(window_text, TARGET_KEYWORDS):
        return []
    if not contains_any(window_text, CARBON_PAGE_KEYWORDS):
        return []
    if not has_target_intent(window_text):
        return []

    target_years = [int(m.group("year")) for m in TARGET_YEAR_CONTEXT_RE.finditer(window_text)]
    target_years = sorted({y for y in target_years if 1990 <= y <= 2100})

    baseline_year = None
    baseline_match = BASELINE_YEAR_RE.search(window_text)
    if baseline_match:
        baseline_year = int(baseline_match.group("year"))

    percent_values = [to_float(m.group("pct")) for m in PERCENT_RE.finditer(window_text)]
    percent_values = [p for p in percent_values if p is not None and 0 <= p <= 100]
    if not contains_any(window_text.lower(), ("감축", "목표", "달성", "중립", "전환")):
        percent_values = []

    unit = extract_unit(window_text)
    value = None
    if contains_any(window_text, ("목표량", "배출목표", "감축량")) and unit is not None:
        value_candidates = extract_numbers(window_text, drop_years=True, drop_percent=True, drop_scope_digits=True)
        if len(value_candidates) == 1:
            value = value_candidates[0]

    scope = infer_scope(window_text)

    metric_name = infer_metric_name(window_text, "target")
    reduction_pct = max(percent_values) if percent_values else None

    if not target_years and baseline_year is None and reduction_pct is None and value is None:
        return []

    years = target_years or [None]
    records: list[CarbonRecord] = []
    for target_year in years:
        records.append(
            CarbonRecord(
                source_name=SOURCE_NAME,
                pdf_path=str(task.pdf_path),
                file_name=task.pdf_path.name,
                company_name=task.company_name,
                report_year=task.report_year,
                page_number=page_number,
                record_type="target",
                metric_name=metric_name,
                scope=scope,
                data_year=None,
                target_year=target_year,
                baseline_year=baseline_year,
                value=value,
                reduction_pct=reduction_pct,
                unit=unit,
                source_type=source_type,
                confidence=confidence_for_target(
                    target_year=target_year,
                    baseline_year=baseline_year,
                    reduction_pct=reduction_pct,
                    value=value,
                ),
                raw_text=window_text[:600],
            )
        )
    return records


def parse_special_verification_block(
    *,
    header_line: str,
    value_line: str,
    nearby_text: str,
    task: PdfTask,
    page_number: int,
    source_type: str,
) -> list[CarbonRecord]:
    header_has_scope_block = (
        ("직접배출" in header_line and "간접배출" in header_line)
        or ("scope 1" in header_line.lower() and "scope 2" in header_line.lower())
    )
    if not header_has_scope_block:
        return []

    values = extract_numbers(value_line, drop_years=False, drop_percent=True, drop_scope_digits=True)
    if len(values) < 3:
        return []

    year_candidates = extract_years(f"{nearby_text} {header_line} {value_line}")
    data_year = year_candidates[-1] if year_candidates else task.report_year
    unit = extract_unit(f"{header_line} {value_line}")
    scope_order = ["S1", "S2"]
    if "기타간접배출" in header_line or "scope 3" in header_line.lower():
        scope_order.append("S3")
    if "총량" in header_line or "total" in header_line.lower():
        scope_order.append("TOTAL")

    use_values = values[-len(scope_order) :]
    records: list[CarbonRecord] = []
    for scope, value in zip(scope_order, use_values):
        records.append(
            CarbonRecord(
                source_name=SOURCE_NAME,
                pdf_path=str(task.pdf_path),
                file_name=task.pdf_path.name,
                company_name=task.company_name,
                report_year=task.report_year,
                page_number=page_number,
                record_type="emission",
                metric_name="검증 배출량",
                scope=scope,
                data_year=data_year,
                target_year=None,
                baseline_year=None,
                value=value,
                reduction_pct=None,
                unit=unit,
                source_type=source_type,
                confidence=confidence_for_emission(data_year=data_year, scope=scope, value=value),
                raw_text=f"{header_line} {value_line}"[:600],
            )
        )
    return records


def parse_emission_from_line(
    *,
    line: str,
    all_lines: list[str],
    line_index: int,
    task: PdfTask,
    page_number: int,
    source_type: str,
) -> list[CarbonRecord]:
    if is_noise_line(line):
        return []
    if not contains_any(line, EMISSION_KEYWORDS):
        return []
    if contains_any(line, TARGET_KEYWORDS) and "배출량" not in line and "검증 범위" not in line and "집약도" not in line:
        return []
    context_lines = all_lines[max(0, line_index - 2) : min(len(all_lines), line_index + 3)]
    context = " ".join(context_lines)
    if not contains_any(context, CARBON_PAGE_KEYWORDS):
        return []
    if "탄소중립" in line and "배출량" not in line and "검증 범위" not in line:
        return []
    if "검증" in line and "검증 범위" not in line and "검증의견서" not in context:
        return []
    if "검증의견서" in line and "검증 범위" not in line:
        return []
    if not contains_any(
        line,
        ("온실가스", "scope", "co2", "탄소", "직접배출", "간접배출", "검증 범위", "집약도", "총 온실가스"),
    ):
        return []

    years = find_nearby_year_header(all_lines, line_index)
    if not years:
        inline_years = extract_years(line)
        if len(inline_years) >= 2:
            years = inline_years
    if len(years) > 5:
        years = years[-5:]

    values = extract_numbers(line, drop_years=True, drop_percent=True, drop_scope_digits=True)
    if not values:
        return []

    scope = infer_scope(line)
    unit = extract_unit(context)
    metric_name = infer_metric_name(line, "emission")
    if "단위" in line and "합계" not in line and line.count(",") == 0 and max(values) < 1000:
        return []
    if scope is None and unit is None and not years and len(values) == 1:
        return []

    records: list[CarbonRecord] = []
    if years and len(values) >= len(years):
        use_values = values[-len(years) :]
        for year, value in zip(years, use_values):
            records.append(
                CarbonRecord(
                    source_name=SOURCE_NAME,
                    pdf_path=str(task.pdf_path),
                    file_name=task.pdf_path.name,
                    company_name=task.company_name,
                    report_year=task.report_year,
                    page_number=page_number,
                    record_type="emission",
                    metric_name=metric_name,
                    scope=scope,
                    data_year=year,
                    target_year=None,
                    baseline_year=None,
                    value=value,
                    reduction_pct=None,
                    unit=unit,
                    source_type=source_type,
                    confidence=confidence_for_emission(data_year=year, scope=scope, value=value),
                    raw_text=line[:600],
                )
            )
        return records

    # Fallback for single-year single-value lines.
    data_year = None
    inline_years = extract_years(line)
    if inline_years:
        data_year = inline_years[-1]
    elif task.report_year is not None:
        data_year = task.report_year

    value = values[-1]
    records.append(
        CarbonRecord(
            source_name=SOURCE_NAME,
            pdf_path=str(task.pdf_path),
            file_name=task.pdf_path.name,
            company_name=task.company_name,
            report_year=task.report_year,
            page_number=page_number,
            record_type="emission",
            metric_name=metric_name,
            scope=scope,
            data_year=data_year,
            target_year=None,
            baseline_year=None,
            value=value,
            reduction_pct=None,
            unit=unit,
            source_type=source_type,
            confidence=confidence_for_emission(data_year=data_year, scope=scope, value=value),
            raw_text=line[:600],
        )
    )
    return records


def parse_text_block(
    *,
    page_text: str,
    task: PdfTask,
    page_number: int,
) -> list[CarbonRecord]:
    lines = [norm_ws(line) for line in (page_text or "").splitlines() if norm_ws(line)]
    if not lines:
        return []

    records: list[CarbonRecord] = []
    for i, line in enumerate(lines):
        if is_noise_line(line):
            continue
        nearby = lines[max(0, i - 2) : min(len(lines), i + 3)]

        # Target extraction
        if contains_any(line, TARGET_KEYWORDS) and contains_any(line, CARBON_PAGE_KEYWORDS):
            target_window = " ".join(lines[i : min(len(lines), i + 2)])
            records.extend(
                parse_target_from_window(
                    window_text=target_window,
                    task=task,
                    page_number=page_number,
                    source_type="text",
                )
            )

        # Verification pattern extraction (header line + next value line)
        if i > 0:
            records.extend(
                parse_special_verification_block(
                    header_line=lines[i - 1],
                    value_line=line,
                    nearby_text=" ".join(nearby),
                    task=task,
                    page_number=page_number,
                    source_type="text",
                )
            )

        # Emission extraction
        records.extend(
            parse_emission_from_line(
                line=line,
                all_lines=lines,
                line_index=i,
                task=task,
                page_number=page_number,
                source_type="text",
            )
        )

        # Fallback for broken line wraps in unfamiliar PDF layouts.
        if (
            i + 1 < len(lines)
            and contains_any(line, ("온실가스", "탄소", "배출", "scope", "co2"))
            and re.search(r"\d", lines[i + 1])
        ):
            line_pair = norm_ws(f"{line} {lines[i + 1]}")
            if line_pair != line:
                records.extend(
                    parse_emission_from_line(
                        line=line_pair,
                        all_lines=[line_pair],
                        line_index=0,
                        task=task,
                        page_number=page_number,
                        source_type="text_window",
                    )
                )
    return records


def detect_table_year_columns(table_rows: list[list[str]]) -> list[tuple[int, int]]:
    header_candidates = table_rows[: min(6, len(table_rows))]
    best: list[tuple[int, int]] = []
    for row in header_candidates:
        pairs: list[tuple[int, int]] = []
        for col_idx, cell in enumerate(row):
            years = extract_years(cell)
            if len(years) == 1:
                pairs.append((col_idx, years[0]))
        unique_years = sorted({year for _, year in pairs})
        if len(unique_years) >= 2 and len(pairs) > len(best):
            best = pairs
    return sorted(best, key=lambda x: x[0])


def parse_table_rows(
    *,
    table_rows: list[list[str]],
    task: PdfTask,
    page_number: int,
) -> list[CarbonRecord]:
    year_columns = detect_table_year_columns(table_rows)
    records: list[CarbonRecord] = []
    for row in table_rows:
        row_text = norm_ws(" ".join(cell for cell in row if cell))
        if not row_text:
            continue
        if is_noise_line(row_text):
            continue
        if not contains_any(row_text, CARBON_PAGE_KEYWORDS):
            continue

        # Table target rows
        if contains_any(row_text, TARGET_KEYWORDS):
            records.extend(
                parse_target_from_window(
                    window_text=row_text,
                    task=task,
                    page_number=page_number,
                    source_type="table",
                )
            )
            continue

        # Ambiguous merged rows can contain multiple scope labels; skip and rely on text parser.
        scope_hits = sum(1 for p, _ in SCOPE_PATTERNS if p.search(row_text))
        if scope_hits > 2:
            continue

        if not contains_any(row_text, EMISSION_KEYWORDS):
            continue

        scope = infer_scope(row_text)
        metric_name = infer_metric_name(row_text, "emission")
        unit = extract_unit(row_text)

        table_year_values: list[tuple[int, float]] = []
        for col_idx, year in year_columns:
            if col_idx >= len(row):
                continue
            cell_numbers = extract_numbers(row[col_idx], drop_years=True, drop_percent=True, drop_scope_digits=True)
            if not cell_numbers:
                continue
            table_year_values.append((year, cell_numbers[-1]))

        if table_year_values:
            for year, value in table_year_values:
                records.append(
                    CarbonRecord(
                        source_name=SOURCE_NAME,
                        pdf_path=str(task.pdf_path),
                        file_name=task.pdf_path.name,
                        company_name=task.company_name,
                        report_year=task.report_year,
                        page_number=page_number,
                        record_type="emission",
                        metric_name=metric_name,
                        scope=scope,
                        data_year=year,
                        target_year=None,
                        baseline_year=None,
                        value=value,
                        reduction_pct=None,
                        unit=unit,
                        source_type="table",
                        confidence=confidence_for_emission(data_year=year, scope=scope, value=value),
                        raw_text=row_text[:600],
                    )
                )
            continue

    return records


def extract_tables_from_page(page) -> list[list[list[str]]]:
    tables: list[list[list[str]]] = []
    tried: set[tuple[tuple[str, ...], ...]] = set()
    settings_candidates = [
        None,
        {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
        {"vertical_strategy": "text", "horizontal_strategy": "text"},
    ]
    for settings in settings_candidates:
        try:
            extracted = page.extract_tables() if settings is None else page.extract_tables(settings)
        except Exception:
            continue
        for table in extracted or []:
            normalized = [
                [norm_ws(str(cell)) if cell is not None else "" for cell in row]
                for row in (table or [])
            ]
            key = tuple(tuple(row) for row in normalized)
            if key in tried:
                continue
            tried.add(key)
            tables.append(normalized)
    return tables


def is_candidate_page(text: str) -> bool:
    return contains_any(text, CARBON_PAGE_KEYWORDS)


def extract_from_pdf(task: PdfTask, max_pages: int | None = None) -> list[CarbonRecord]:
    try:
        import pdfplumber
    except ModuleNotFoundError as exc:
        raise RuntimeError("pdfplumber is required. Install with: pip install pdfplumber") from exc

    records: list[CarbonRecord] = []
    with pdfplumber.open(task.pdf_path) as pdf:
        total_pages = len(pdf.pages)
        page_limit = min(total_pages, max_pages) if max_pages else total_pages
        for page_idx in range(page_limit):
            page = pdf.pages[page_idx]
            raw_text = page.extract_text() or ""
            if not is_candidate_page(raw_text):
                continue

            page_number = page_idx + 1
            records.extend(
                parse_text_block(
                    page_text=raw_text,
                    task=task,
                    page_number=page_number,
                )
            )

            tables = extract_tables_from_page(page)
            for table_rows in tables:
                records.extend(
                    parse_table_rows(
                        table_rows=table_rows,
                        task=task,
                        page_number=page_number,
                    )
                )
    return records


def parse_metadata_file(
    metadata_csv: Path,
    *,
    reports_root: Path | None,
    year_filter: set[int] | None,
) -> list[PdfTask]:
    if not metadata_csv.exists():
        return []
    try:
        df = pd.read_csv(metadata_csv)
    except Exception:
        return []

    tasks: list[PdfTask] = []
    for _, row in df.iterrows():
        status = str(row.get("download_status", "")).strip().lower()
        if status and status != "success":
            continue

        downloaded_file = row.get("downloaded_file")
        if not isinstance(downloaded_file, str) or not downloaded_file.strip():
            continue

        row_year = row.get("report_year", row.get("year"))
        report_year = int(row_year) if pd.notna(row_year) and str(row_year).isdigit() else None
        if year_filter and report_year is not None and report_year not in year_filter:
            continue

        rel_file = Path(downloaded_file)
        candidates = [metadata_csv.parent / rel_file]
        if reports_root and report_year is not None:
            candidates.append(reports_root / str(report_year) / rel_file)
        if reports_root:
            candidates.append(reports_root / rel_file)

        pdf_path = next((p for p in candidates if p.exists()), candidates[0])
        company_name = row.get("company_name")
        company = str(company_name).strip() if isinstance(company_name, str) and company_name.strip() else None

        tasks.append(
            PdfTask(
                pdf_path=pdf_path,
                company_name=company,
                report_year=report_year,
            )
        )
    return tasks


def collect_tasks(args: argparse.Namespace, repo_root: Path) -> list[PdfTask]:
    tasks_by_path: dict[str, PdfTask] = {}
    year_filter = set(args.years) if args.years else None
    reports_root = resolve_path(args.reports_root, repo_root) if args.reports_root else None

    metadata_files: list[Path] = []
    for p in args.metadata_csv:
        metadata_files.append(resolve_path(p, repo_root))
    if args.metadata_glob:
        metadata_files.extend(Path(repo_root).glob(args.metadata_glob))

    for metadata_csv in metadata_files:
        for task in parse_metadata_file(
            metadata_csv,
            reports_root=reports_root,
            year_filter=year_filter,
        ):
            key = str(task.pdf_path.resolve())
            if key not in tasks_by_path:
                tasks_by_path[key] = task

    for path_group in args.pdf_path:
        for raw in path_group:
            path = resolve_path(Path(raw), repo_root)
            key = str(path.resolve())
            if key not in tasks_by_path:
                tasks_by_path[key] = PdfTask(pdf_path=path)

    for raw_dir in args.pdf_dir:
        directory = resolve_path(raw_dir, repo_root)
        if not directory.exists():
            continue
        pattern = "**/*.pdf" if args.recursive else "*.pdf"
        for path in directory.glob(pattern):
            key = str(path.resolve())
            if key not in tasks_by_path:
                tasks_by_path[key] = PdfTask(pdf_path=path)

    tasks = [task for task in tasks_by_path.values() if task.pdf_path.exists()]
    if not tasks:
        sample_dirs = [
            Path(__file__).resolve().parent / "output_example",
            Path(__file__).resolve().parent / "output-example",
        ]
        for sample_dir in sample_dirs:
            if not sample_dir.exists():
                continue
            for path in sorted(sample_dir.glob("*.pdf")):
                key = str(path.resolve())
                if key not in tasks_by_path:
                    tasks_by_path[key] = PdfTask(pdf_path=path)
        tasks = [task for task in tasks_by_path.values() if task.pdf_path.exists()]

    tasks.sort(key=lambda t: str(t.pdf_path))
    return tasks


def parse_args(repo_root: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KRX ESG carbon parser.")
    parser.add_argument(
        "--metadata-csv",
        action="append",
        type=Path,
        default=[],
        help="metadata.csv path generated by extractor. Can be repeated.",
    )
    parser.add_argument(
        "--metadata-glob",
        default=DEFAULT_METADATA_GLOB,
        help=f"Glob from repo root for metadata files. Default: {DEFAULT_METADATA_GLOB}",
    )
    parser.add_argument(
        "--pdf-path",
        action="append",
        nargs="+",
        default=[],
        help="Direct PDF path(s). Can be repeated.",
    )
    parser.add_argument(
        "--pdf-dir",
        action="append",
        type=Path,
        default=[],
        help="Directory containing PDF files.",
    )
    parser.add_argument("--recursive", action="store_true", help="Use recursive search for --pdf-dir.")
    parser.add_argument(
        "--reports-root",
        type=Path,
        default=Path("storage") / "raw" / SOURCE_NAME / "reports",
        help="Root folder used by extractor output.",
    )
    parser.add_argument("--years", nargs="+", type=int, help="Filter report years when metadata is used.")
    parser.add_argument("--max-pages", type=int, help="Optional max page count per PDF for debugging.")
    parser.add_argument("--run-date", help="Output partition date (YYYY-MM-DD).")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--output-file", type=Path)
    parser.add_argument("--output-format", choices=["csv", "parquet"], default="csv")
    parser.add_argument(
        "--min-confidence",
        choices=["low", "medium", "high"],
        default="low",
        help=argparse.SUPPRESS,
    )
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
    args.reports_root = resolve_path(args.reports_root, repo_root) if args.reports_root else None
    return args


def resolve_output_file(args: argparse.Namespace, repo_root: Path) -> Path:
    if args.output_file:
        output_file = args.output_file
    else:
        run_date = args.run_date or datetime.now().strftime("%Y-%m-%d")
        output_dir = args.output_dir or (repo_root / "storage" / "parsed" / SOURCE_NAME / run_date)
        ext = "parquet" if args.output_format == "parquet" else "csv"
        output_file = output_dir / f"carbon_records.{ext}"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    return output_file


def records_to_frame(records: list[CarbonRecord]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    df = pd.DataFrame([asdict(record) for record in records])
    for col in OUTPUT_COLUMNS:
        if col not in df.columns:
            df[col] = None

    # emission records without numeric value are not useful
    df = df[~((df["record_type"] == "emission") & (df["value"].isna()))]
    # target records must carry at least one informative field
    target_empty = (
        (df["record_type"] == "target")
        & df["target_year"].isna()
        & df["baseline_year"].isna()
        & df["reduction_pct"].isna()
        & df["value"].isna()
    )
    df = df[~target_empty]

    df["unit"] = df["unit"].astype("string").str.strip().replace({"<NA>": None, "": None})
    df["scope"] = df["scope"].astype("string").str.strip().replace({"<NA>": None, "": None})

    df = df.sort_values(
        by=["pdf_path", "page_number", "record_type", "scope", "data_year", "target_year", "source_type"],
        kind="stable",
    )
    df = df.drop_duplicates(
        subset=[
            "pdf_path",
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
        ],
        keep="first",
    )
    df = df[OUTPUT_COLUMNS]
    return df.reset_index(drop=True)


def save_output(df: pd.DataFrame, output_file: Path, output_format: str) -> None:
    if output_format == "parquet" or output_file.suffix.lower() == ".parquet":
        df.to_parquet(output_file, index=False)
        return
    df.to_csv(output_file, index=False, encoding="utf-8-sig")


def run(args: argparse.Namespace, repo_root: Path) -> Path:
    output_file = resolve_output_file(args, repo_root)
    tasks = collect_tasks(args, repo_root)
    if not tasks:
        df = pd.DataFrame(columns=OUTPUT_COLUMNS)
        save_output(df, output_file, args.output_format)
        print(f"no input pdfs found; saved empty file: {output_file}")
        return output_file

    all_records: list[CarbonRecord] = []
    for i, task in enumerate(tasks, start=1):
        print(f"[{i}/{len(tasks)}] parsing: {task.pdf_path}")
        try:
            extracted = extract_from_pdf(task, max_pages=args.max_pages)
            all_records.extend(extracted)
            print(f"  extracted={len(extracted)}")
        except Exception as exc:
            print(f"  error: {exc!r}")

    df = records_to_frame(all_records)
    save_output(df, output_file, args.output_format)

    if not df.empty:
        summary = (
            df.groupby(["record_type", "file_name"], as_index=False)
            .size()
            .sort_values(by=["record_type", "size"], ascending=[True, False], kind="stable")
        )
        print(summary.to_string(index=False))
    print(f"saved: {output_file} rows={len(df)}")
    return output_file


def main() -> None:
    repo_root = find_repo_root()
    args = parse_args(repo_root)
    run(args, repo_root)


if __name__ == "__main__":
    main()
