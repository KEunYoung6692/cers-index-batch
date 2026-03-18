"""
Text normalization helpers for extracted report pages.
"""

from __future__ import annotations

from collections import Counter
import re
from typing import Iterable, Sequence


PAGINATION_PATTERNS = [
    re.compile(r"^\d{1,4}$"),
    re.compile(r"^\d{1,4}\s*/\s*\d{1,4}$"),
    re.compile(r"^p(?:age)?\.?\s*\d{1,4}(?:\s*of\s*\d{1,4})?$", re.IGNORECASE),
]

PROTECTED_SIGNAL_PATTERN = re.compile(
    r"탄소|온실가스|scope|배출|감축|net zero|탄소중립|re100|tco2|kpi|목표|투자|위원회|지배구조|%|억원|조원|mwh|kwh|capex|ebitda|revenue",
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


def clean_text(text: str | None) -> str:
    if text is None:
        return ""
    value = str(text)
    value = value.replace("\xa0", " ")
    value = value.replace("\u200b", " ")
    value = value.replace("\ufeff", " ")
    value = value.replace("\x07", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def normalize_noise_key(line: str) -> str:
    key = line.lower().strip()
    key = re.sub(r"\d{1,4}", "<n>", key)
    key = re.sub(r"\s+", " ", key)
    return key


def is_pagination_line(line: str) -> bool:
    return any(pattern.match(line) for pattern in PAGINATION_PATTERNS)


def has_protected_signal(line: str) -> bool:
    return bool(PROTECTED_SIGNAL_PATTERN.search(line))


def is_navigation_line(line: str) -> bool:
    text = line.strip()
    if any(pattern.match(text) for pattern in NAVIGATION_LINE_PATTERNS):
        return True
    if len(text) <= 100 and re.match(r"^[A-Za-z가-힣0-9()·/&\-\s]+\s\d{3}$", text):
        return True
    return False


def is_toc_like_text(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        return False

    has_hint = bool(TOC_HINT_PATTERN.search(text))
    page_token_lines = sum(1 for line in lines if re.search(r"\b\d{3}\b", line))
    short_lines = sum(1 for line in lines if len(line) <= 65)
    if has_hint and page_token_lines >= 3 and short_lines >= max(2, len(lines) // 2):
        return True
    return False


def detect_common_noise_keys(
    pages: Sequence[Sequence[str]],
    *,
    ratio: float = 0.35,
    min_pages: int = 3,
    max_line_chars: int = 90,
) -> set[str]:
    if not pages:
        return set()

    freq: Counter[str] = Counter()
    for lines in pages:
        seen: set[str] = set()
        for line in lines:
            if not line or len(line) > max_line_chars or is_pagination_line(line):
                continue
            key = normalize_noise_key(line)
            if key:
                seen.add(key)
        for key in seen:
            freq[key] += 1

    threshold = max(min_pages, int(len(pages) * ratio))
    return {
        key
        for key, count in freq.items()
        if count >= threshold and not has_protected_signal(key)
    }


def normalize_page_texts(page_texts: Sequence[str]) -> list[dict]:
    page_lines = [[line.strip() for line in clean_text(text).splitlines() if line.strip()] for text in page_texts]
    common_noise_keys = detect_common_noise_keys(page_lines)
    results: list[dict] = []

    for page_no, lines in enumerate(page_lines, start=1):
        dropped = 0
        kept_lines: list[str] = []
        for line in lines:
            if is_pagination_line(line):
                dropped += 1
                continue
            if is_navigation_line(line):
                dropped += 1
                continue
            key = normalize_noise_key(line)
            if key in common_noise_keys and not has_protected_signal(line):
                dropped += 1
                continue
            kept_lines.append(line)

        normalized_text = clean_text("\n".join(kept_lines))
        toc_like = is_toc_like_text(normalized_text)
        results.append(
            {
                "page_no": page_no,
                "normalized_text": normalized_text,
                "dropped_line_count": dropped,
                "toc_like": toc_like,
                "line_count": len(lines),
            }
        )
    return results


def split_text_to_paragraphs(text: str) -> list[str]:
    normalized = clean_text(text)
    if not normalized:
        return []
    parts = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    if parts:
        return parts
    return [normalized]
