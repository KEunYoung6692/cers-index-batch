"""
PDF extraction stage for CI_BATCH.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import re
from typing import Any

try:
    from langchain_community.document_loaders import PDFPlumberLoader
except ImportError:
    from langchain.document_loaders import PDFPlumberLoader  # type: ignore[no-redef]

from ci_batch.contracts import (
    DocumentPageRecord,
    DocumentRecord,
    EvidenceBlockType,
    ExtractedEvidenceRecord,
    ExtractionRunRecord,
    ExtractionStatus,
    IngestionStatus,
)


METHODOLOGY_PATTERN = re.compile(
    r"\b(?:AHP|EWM|DQS|GV|methodology|formula|parameter|weight|score)\b|평가방법|가중치|산식|방법론",
    re.IGNORECASE,
)
TABLE_SIGNAL_PATTERN = re.compile(
    r"\bscope\s*[123]\b|tco2|tco2e|억원|백만원|조원|mwh|kwh|tj|capex|ebitda|revenue|%",
    re.IGNORECASE,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


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


def infer_report_year_from_pages(page_texts: list[str], probe_pages: int = 12) -> int | None:
    weighted: dict[int, int] = {}
    for page_index, text in enumerate(page_texts[:probe_pages], start=1):
        for match in re.finditer(r"(?<!\d)((?:19|20)\d{2})(?!\d)", text):
            year = int(match.group(1))
            if year < 1990 or year > 2100:
                continue

            score = 1
            if page_index <= 3:
                score += 2

            around = text[max(0, match.start() - 50): match.end() + 50]
            if re.search(r"report|보고서|지속가능|sustainability|esg", around, re.IGNORECASE):
                score += 3
            weighted[year] = weighted.get(year, 0) + score

    if not weighted:
        return None
    return max(weighted, key=lambda item: (weighted[item], item))


def guess_block_type(block_text: str) -> EvidenceBlockType:
    lines = [line.strip() for line in block_text.splitlines() if line.strip()]
    if not lines:
        return EvidenceBlockType.TEXT

    long_numeric_lines = 0
    for line in lines:
        if "|" in line:
            return EvidenceBlockType.TABLE
        number_tokens = len(re.findall(r"\d[\d,\.]*", line))
        if number_tokens >= 3 and TABLE_SIGNAL_PATTERN.search(line):
            long_numeric_lines += 1
    if long_numeric_lines >= 2:
        return EvidenceBlockType.TABLE
    return EvidenceBlockType.TEXT


def split_page_to_blocks(text: str, max_block_chars: int = 1600) -> list[str]:
    clean = clean_text(text)
    if not clean:
        return []

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", clean) if part.strip()]
    if not paragraphs:
        return [clean]

    blocks: list[str] = []
    current: list[str] = []
    current_len = 0

    for paragraph in paragraphs:
        next_len = current_len + len(paragraph) + (2 if current else 0)
        if current and next_len > max_block_chars:
            blocks.append("\n\n".join(current))
            current = [paragraph]
            current_len = len(paragraph)
        else:
            current.append(paragraph)
            current_len = next_len

    if current:
        blocks.append("\n\n".join(current))
    return blocks


def guess_section_hint(block_text: str) -> str | None:
    for line in block_text.splitlines():
        text = clean_text(line)
        if not text:
            continue
        if len(text) > 80:
            continue
        if len(re.findall(r"\d", text)) > max(2, len(text) // 3):
            continue
        return text
    return None


def is_methodology_content(text: str) -> bool:
    return bool(METHODOLOGY_PATTERN.search(text))


def build_page_key(document_key: str, page_no: int) -> str:
    return f"{document_key}_p{page_no:04d}"


def build_evidence_key(page_key: str, block_index: int) -> str:
    return f"{page_key}_b{block_index:03d}"


def build_extraction_key(document_key: str, run_id: str) -> str:
    return f"{document_key}_{run_id}"


def extract_document(
    document: DocumentRecord,
    *,
    run_id: str,
    extractor_version: str,
    registrar: str,
    extraction_mode: str = "text",
) -> tuple[DocumentRecord, ExtractionRunRecord, list[DocumentPageRecord], list[ExtractedEvidenceRecord]]:
    extraction_key = build_extraction_key(document.document_key, run_id)
    run_record = ExtractionRunRecord(
        extraction_key=extraction_key,
        document_key=document.document_key,
        extractor_version=extractor_version,
        extraction_mode=extraction_mode,
        status=ExtractionStatus.STARTED,
        registrar=registrar,
    )

    pdf_path = document.file_path
    if not pdf_path:
        failed_run = replace(
            run_record,
            status=ExtractionStatus.FAILED,
            run_finished_at=utc_now(),
            error_message="document.file_path is required for PDF extraction",
        )
        return document, failed_run, [], []

    try:
        loader = PDFPlumberLoader(pdf_path)
        loaded_pages = loader.load()
    except Exception as exc:
        failed_run = replace(
            run_record,
            status=ExtractionStatus.FAILED,
            run_finished_at=utc_now(),
            error_message=str(exc),
        )
        return document, failed_run, [], []

    page_records: list[DocumentPageRecord] = []
    evidence_records: list[ExtractedEvidenceRecord] = []
    page_texts: list[str] = []

    for page_index, loaded_page in enumerate(loaded_pages, start=1):
        raw_text = clean_text(loaded_page.page_content)
        page_key = build_page_key(document.document_key, page_index)
        page_record = DocumentPageRecord(
            page_key=page_key,
            document_key=document.document_key,
            page_no=page_index,
            raw_text=raw_text or None,
            ocr_text=None,
            registrar=registrar,
            metadata={
                "loader_metadata": dict(loaded_page.metadata or {}),
            },
        )
        page_records.append(page_record)
        page_texts.append(raw_text)

        blocks = split_page_to_blocks(raw_text)
        for block_index, block_text in enumerate(blocks, start=1):
            evidence_records.append(
                ExtractedEvidenceRecord(
                    evidence_key=build_evidence_key(page_key, block_index),
                    extraction_key=extraction_key,
                    page_key=page_key,
                    block_type=guess_block_type(block_text),
                    raw_snippet=block_text,
                    section_hint=guess_section_hint(block_text),
                    normalized_snippet=clean_text(block_text),
                    confidence=1.0 if block_text else None,
                    locator_json={
                        "page_no": page_index,
                        "block_index": block_index,
                    },
                    is_methodology_content=is_methodology_content(block_text),
                    registrar=registrar,
                )
            )

    inferred_year = document.report_year or infer_report_year_from_pages(page_texts)
    inferred_year_source = document.metadata.get("report_year_source", "unknown")
    if document.report_year is None and inferred_year is not None:
        inferred_year_source = "content"

    enriched_document = replace(
        document,
        report_year=inferred_year,
        page_count=len(page_records),
        ingestion_status=IngestionStatus.EXTRACTED,
        metadata={
            **document.metadata,
            "report_year_source": inferred_year_source,
            "page_count_extracted": len(page_records),
        },
    )
    finished_run = replace(
        run_record,
        status=ExtractionStatus.SUCCEEDED,
        run_finished_at=utc_now(),
        metadata={
            "page_count": len(page_records),
            "evidence_count": len(evidence_records),
        },
    )
    return enriched_document, finished_run, page_records, evidence_records
