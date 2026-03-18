"""
Build retrieval chunks from normalized extracted evidence.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ci_batch.contracts import ChunkRecord
from ci_batch.normalize.text import split_text_to_paragraphs


def build_chunk_id(document_key: str, index: int) -> str:
    return f"{document_key}_c{index:04d}"


def build_retrieval_chunks(
    *,
    document_key: str,
    company_name: str | None,
    report_year: int | None,
    normalized_pages: list[dict],
    evidence_rows: list[dict],
    target_chars: int,
    overlap_chars: int,
    registrar: str,
) -> list[ChunkRecord]:
    evidence_by_page: dict[int, list[dict]] = defaultdict(list)
    for evidence in evidence_rows:
        locator = evidence.get("locator_json") or {}
        page_no = locator.get("page_no")
        if page_no is None:
            continue
        evidence_by_page[int(page_no)].append(evidence)

    segments: list[dict[str, Any]] = []
    for page in normalized_pages:
        page_no = page["page_no"]
        if page.get("toc_like"):
            continue

        page_text = page.get("normalized_text") or ""
        if not page_text:
            continue

        page_evidence = evidence_by_page.get(page_no) or []
        for evidence in page_evidence:
            normalized_snippet = evidence.get("normalized_snippet") or ""
            raw_snippet = evidence.get("raw_snippet") or ""
            block_text = normalized_snippet or raw_snippet
            block_text = block_text.strip()
            if not block_text:
                continue

            for paragraph in split_text_to_paragraphs(block_text):
                segments.append(
                    {
                        "text": paragraph,
                        "page_no": page_no,
                        "page_key": evidence.get("page_key"),
                        "evidence_key": evidence.get("evidence_key"),
                        "block_type": evidence.get("block_type") or "text",
                        "section_hint": evidence.get("section_hint"),
                        "is_methodology_content": evidence.get("is_methodology_content"),
                    }
                )

    chunks: list[ChunkRecord] = []
    current_segments: list[dict[str, Any]] = []
    current_len = 0
    chunk_index = 1

    def flush() -> None:
        nonlocal current_segments, current_len, chunk_index
        if not current_segments:
            return

        content = "\n\n".join(segment["text"] for segment in current_segments).strip()
        page_nos = [segment["page_no"] for segment in current_segments]
        page_keys = list(dict.fromkeys(segment["page_key"] for segment in current_segments if segment["page_key"]))
        evidence_keys = list(
            dict.fromkeys(segment["evidence_key"] for segment in current_segments if segment["evidence_key"])
        )
        section_hint = next((segment["section_hint"] for segment in current_segments if segment["section_hint"]), None)
        block_types = {segment["block_type"] for segment in current_segments if segment["block_type"]}
        chunk_type = "table" if block_types == {"table"} else "text"
        methodology_flag = any(segment["is_methodology_content"] for segment in current_segments)
        chunks.append(
            ChunkRecord(
                chunk_id=build_chunk_id(document_key, chunk_index),
                document_key=document_key,
                content=content,
                company_name=company_name,
                report_year=report_year,
                page_start=min(page_nos),
                page_end=max(page_nos),
                page_keys=page_keys,
                evidence_keys=evidence_keys,
                chunk_type=chunk_type,
                section_hint=section_hint,
                registrar=registrar,
                metadata={
                    "segment_count": len(current_segments),
                    "char_count": len(content),
                    "contains_methodology_content": methodology_flag,
                },
            )
        )
        chunk_index += 1

        if overlap_chars > 0:
            overlap_segments: list[dict[str, Any]] = []
            overlap_len = 0
            for segment in reversed(current_segments):
                overlap_segments.insert(0, segment)
                overlap_len += len(segment["text"])
                if overlap_len >= overlap_chars:
                    break
            current_segments = overlap_segments
            current_len = overlap_len
        else:
            current_segments = []
            current_len = 0

    for segment in segments:
        segment_text = segment["text"].strip()
        if not segment_text:
            continue

        segment_len = len(segment_text)
        if current_segments and current_len + segment_len + 2 > target_chars:
            flush()
        current_segments.append(segment)
        current_len += segment_len + (2 if current_len else 0)

    flush()
    return chunks
