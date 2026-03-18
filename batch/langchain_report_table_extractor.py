# -*- coding: utf-8 -*-
"""
LangChain(community) 기반 PDF 보고서 추출기.

목표:
1) `samples/reports` 같은 폴더의 PDF를 일괄 로딩
2) 페이지 번호/문자 수 같은 메타는 제외하고 LLM 입력용 row 테이블 생성
3) 원문은 최대한 그대로 유지하고, 반복 헤더/푸터/페이지번호성 노이즈만 제거
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

try:
    from langchain_community.document_loaders import PDFPlumberLoader
except ImportError:
    try:
        # 구버전 호환
        from langchain.document_loaders import PDFPlumberLoader
    except ImportError as exc:
        raise RuntimeError(
            "LangChain PDF 로더가 필요합니다. "
            "예: pip install langchain langchain-community pdfplumber"
        ) from exc


PAGINATION_PATTERNS = [
    re.compile(r"^\d{1,4}$"),
    re.compile(r"^\d{1,4}\s*/\s*\d{1,4}$"),
    re.compile(r"^p(?:age)?\.?\s*\d{1,4}(?:\s*of\s*\d{1,4})?$", re.IGNORECASE),
]

PROTECTED_SIGNAL_PATTERN = re.compile(
    r"탄소|온실가스|scope|배출|감축|net zero|re100|tco2|kpi|목표|투자|위원회|지배구조|%|억원|조원",
    re.IGNORECASE,
)

NAVIGATION_LINE_PATTERNS = [
    re.compile(
        r"^(introduction|esg management|esg report|appendix)(?:\s+\w+){0,10}\s+\d{3}$",
        re.IGNORECASE,
    ),
    re.compile(r"^(목차|contents|table of contents)$", re.IGNORECASE),
]

TOC_HINT_PATTERN = re.compile(
    r"about this report|contents|table of contents|gri standards|tcfd index|sasb index|appendix|목차",
    re.IGNORECASE,
)


def clean_text(text: str) -> str:
    if text is None:
        return ""
    value = str(text)
    value = value.replace("\xa0", " ")
    value = value.replace("\u200b", " ")
    value = value.replace("\ufeff", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def clean_line(line: str) -> str:
    value = clean_text(line)
    return value.strip()


def normalize_noise_key(line: str) -> str:
    key = line.lower().strip()
    key = re.sub(r"\d{1,4}", "<n>", key)
    key = re.sub(r"\s+", " ", key)
    return key


def is_pagination_line(line: str) -> bool:
    return any(pat.match(line) for pat in PAGINATION_PATTERNS)


def is_navigation_line(line: str) -> bool:
    text = line.strip()
    if any(pat.match(text) for pat in NAVIGATION_LINE_PATTERNS):
        return True
    if len(text) <= 100 and re.match(r"^[A-Za-z가-힣0-9()·/&\-\s]+\s\d{3}$", text):
        return True
    return False


def has_protected_signal(line: str) -> bool:
    return bool(PROTECTED_SIGNAL_PATTERN.search(line))


def detect_common_noise_keys(
    pages: Sequence[Sequence[str]],
    *,
    ratio: float = 0.35,
    min_pages: int = 3,
    max_line_chars: int = 90,
) -> Set[str]:
    if not pages:
        return set()

    freq: Counter[str] = Counter()
    for page_lines in pages:
        seen_keys = set()
        for line in page_lines:
            if not line:
                continue
            if len(line) > max_line_chars:
                continue
            if is_pagination_line(line):
                continue
            key = normalize_noise_key(line)
            if not key:
                continue
            seen_keys.add(key)
        for key in seen_keys:
            freq[key] += 1

    threshold = max(min_pages, int(len(pages) * ratio))
    noise_keys = set()
    for key, count in freq.items():
        if count < threshold:
            continue
        if has_protected_signal(key):
            continue
        noise_keys.add(key)
    return noise_keys


def should_drop_line(line: str, common_noise_keys: Set[str]) -> bool:
    if not line:
        return True
    if is_pagination_line(line):
        return True
    if is_navigation_line(line):
        return True
    key = normalize_noise_key(line)
    if key in common_noise_keys and not has_protected_signal(line):
        return True
    return False


def should_keep_chunk(chunk: str, min_informative_chars: int = 60) -> bool:
    if not chunk:
        return False
    if is_toc_like_chunk(chunk):
        return False
    if len(chunk) >= min_informative_chars:
        return True
    if has_protected_signal(chunk):
        return True
    return False


def is_toc_like_chunk(chunk: str) -> bool:
    lines = [line.strip() for line in chunk.splitlines() if line.strip()]
    if len(lines) < 3:
        return False

    has_hint = bool(TOC_HINT_PATTERN.search(chunk))
    page_token_lines = sum(1 for line in lines if re.search(r"\b\d{3}\b", line))
    short_lines = sum(1 for line in lines if len(line) <= 65)

    if has_hint and page_token_lines >= 3 and short_lines >= max(2, len(lines) // 2):
        return True
    return False


def infer_company_name(pdf_path: Path) -> str:
    stem = pdf_path.stem
    stem = re.sub(
        r"[_\-\s]*(?:지속가능경영|지속가능|sustainability|esg|annual)?[_\-\s]*보고서.*$",
        "",
        stem,
        flags=re.IGNORECASE,
    )
    stem = stem.strip("_- ")
    return stem or pdf_path.stem


def infer_report_year(pages: Sequence[Sequence[str]], probe_pages: int = 12) -> Optional[int]:
    weighted: Counter[int] = Counter()

    for page_idx, lines in enumerate(pages[:probe_pages], start=1):
        text = " ".join(lines)
        for match in re.finditer(r"\b(19|20)\d{2}\b", text):
            year = int(match.group(0))
            if year < 1990 or year > 2100:
                continue

            score = 1
            if page_idx <= 3:
                score += 2

            around = text[max(0, match.start() - 40): match.end() + 40]
            if re.search(r"report|보고서|지속가능|sustainability|esg", around, re.IGNORECASE):
                score += 3
            weighted[year] += score

    if not weighted:
        return None

    return max(weighted, key=lambda y: (weighted[y], y))


def split_lines_to_chunks(
    lines: Sequence[str],
    *,
    max_chunk_chars: int = 1600,
    min_chunk_chars: int = 120,
) -> List[str]:
    if not lines:
        return []

    chunks: List[str] = []
    buf: List[str] = []
    cur_len = 0

    for line in lines:
        if not line:
            continue

        next_len = cur_len + len(line) + (1 if buf else 0)
        if buf and next_len > max_chunk_chars:
            chunk = clean_text("\n".join(buf))
            if chunk:
                chunks.append(chunk)
            buf = [line]
            cur_len = len(line)
        else:
            buf.append(line)
            cur_len = next_len

    if buf:
        chunk = clean_text("\n".join(buf))
        if chunk:
            chunks.append(chunk)

    if not chunks:
        return []

    merged: List[str] = []
    for chunk in chunks:
        if merged and len(chunk) < min_chunk_chars:
            merged[-1] = clean_text(merged[-1] + "\n" + chunk)
        else:
            merged.append(chunk)
    return merged


def is_table_like(text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return False

    pipe_rows = sum(1 for line in lines if "|" in line)
    tab_rows = sum(1 for line in lines if "\t" in line)
    multi_num_rows = sum(1 for line in lines if len(re.findall(r"\d[\d,\.]*", line)) >= 3)
    column_gap_rows = sum(1 for line in lines if re.search(r"\S+\s{2,}\S+", line))
    year_header_rows = sum(
        1 for line in lines if re.search(r"(?:19|20)\d{2}.*(?:19|20)\d{2}", line)
    )

    if pipe_rows >= 1 or tab_rows >= 1:
        return True
    if year_header_rows >= 1 and multi_num_rows >= 2:
        return True
    if multi_num_rows >= 2 and column_gap_rows >= 1:
        return True
    return False


def _load_pages_with_langchain(pdf_path: str) -> List[List[str]]:
    docs = PDFPlumberLoader(pdf_path).load()
    pages: List[List[str]] = []

    for doc in docs:
        page_text = clean_text(doc.page_content or "")
        lines = [clean_line(raw) for raw in page_text.splitlines()]
        lines = [line for line in lines if line]
        pages.append(lines)

    return pages


def extract_report_rows_with_langchain(
    pdf_path: str,
    *,
    max_chunk_chars: int = 1600,
    min_chunk_chars: int = 120,
) -> List[Dict[str, Any]]:
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")

    pages = _load_pages_with_langchain(str(path))
    common_noise_keys = detect_common_noise_keys(pages)

    company = infer_company_name(path)
    report_year = infer_report_year(pages)

    rows: List[Dict[str, Any]] = []
    seen_content_keys = set()
    sequence = 1

    for page_lines in pages:
        filtered = [line for line in page_lines if not should_drop_line(line, common_noise_keys)]
        if not filtered:
            continue

        for chunk in split_lines_to_chunks(
            filtered,
            max_chunk_chars=max_chunk_chars,
            min_chunk_chars=min_chunk_chars,
        ):
            if not should_keep_chunk(chunk):
                continue

            content_key = re.sub(r"\s+", " ", chunk).strip().lower()
            if not content_key or content_key in seen_content_keys:
                continue
            seen_content_keys.add(content_key)

            rows.append(
                {
                    "company": company,
                    "report_year": report_year,
                    "source_file": path.name,
                    "record_type": "table_like" if is_table_like(chunk) else "text",
                    "content": chunk,
                    "sequence": sequence,
                }
            )
            sequence += 1

    return rows


def extract_reports_directory_to_rows(
    report_dir: str,
    *,
    glob_pattern: str = "*.pdf",
    max_chunk_chars: int = 1600,
    min_chunk_chars: int = 120,
) -> List[Dict[str, Any]]:
    root = Path(report_dir)
    if not root.exists():
        raise FileNotFoundError(f"입력 폴더를 찾을 수 없습니다: {report_dir}")

    rows: List[Dict[str, Any]] = []
    pdf_paths = sorted(root.glob(glob_pattern))

    for pdf_path in pdf_paths:
        rows.extend(
            extract_report_rows_with_langchain(
                str(pdf_path),
                max_chunk_chars=max_chunk_chars,
                min_chunk_chars=min_chunk_chars,
            )
        )

    return rows


def save_rows(rows: Sequence[Dict[str, Any]], output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()

    if suffix == ".json":
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    if suffix == ".jsonl":
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return

    if suffix == ".csv":
        fieldnames = ["company", "report_year", "source_file", "record_type", "content", "sequence"]
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k) for k in fieldnames})
        return

    raise ValueError("output 확장자는 .json / .jsonl / .csv 중 하나여야 합니다.")


def build_summary(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    by_file: Counter[str] = Counter(row.get("source_file", "") for row in rows)
    by_type: Counter[str] = Counter(row.get("record_type", "") for row in rows)

    return {
        "row_count": len(rows),
        "files": dict(sorted(by_file.items(), key=lambda x: x[0])),
        "record_types": dict(sorted(by_type.items(), key=lambda x: x[0])),
    }


def run(
    input_dir: Optional[str],
    output_path: str,
    *,
    input_file: Optional[str] = None,
    glob_pattern: str = "*.pdf",
    max_chunk_chars: int = 1600,
    min_chunk_chars: int = 120,
) -> None:
    if input_file:
        rows = extract_report_rows_with_langchain(
            input_file,
            max_chunk_chars=max_chunk_chars,
            min_chunk_chars=min_chunk_chars,
        )
    else:
        if not input_dir:
            raise ValueError("input_file 또는 input_dir 중 하나는 지정해야 합니다.")
        rows = extract_reports_directory_to_rows(
            input_dir,
            glob_pattern=glob_pattern,
            max_chunk_chars=max_chunk_chars,
            min_chunk_chars=min_chunk_chars,
        )

    save_rows(rows, output_path)
    print(f"[완료] 저장: {output_path}")
    print(json.dumps(build_summary(rows), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="LangChain(community) 기반 PDF 보고서 -> LLM 입력용 row 테이블 추출기"
    )

    parser.add_argument(
        "--input_file",
        default=None,
        help="입력 PDF 파일 경로 (단일 파일 처리)",
    )
    parser.add_argument(
        "--input_dir",
        default="samples/reports",
        help="입력 PDF 폴더 (default: samples/reports, input_file 미지정 시 사용)",
    )
    parser.add_argument(
        "--glob",
        default="*.pdf",
        help="입력 파일 glob 패턴 (default: *.pdf)",
    )
    parser.add_argument(
        "--output",
        default="sample_reports_rows.jsonl",
        help="출력 파일 (.json/.jsonl/.csv)",
    )
    parser.add_argument(
        "--max_chunk_chars",
        type=int,
        default=1600,
        help="chunk 최대 문자 수 (default: 1600)",
    )
    parser.add_argument(
        "--min_chunk_chars",
        type=int,
        default=120,
        help="작은 chunk 병합 기준 문자 수 (default: 120)",
    )

    args = parser.parse_args()
    run(
        input_dir=args.input_dir,
        output_path=args.output,
        input_file=args.input_file,
        glob_pattern=args.glob,
        max_chunk_chars=args.max_chunk_chars,
        min_chunk_chars=args.min_chunk_chars,
    )
