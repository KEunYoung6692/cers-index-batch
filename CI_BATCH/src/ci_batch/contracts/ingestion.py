"""
Schema-aligned intermediate contracts for the ingestion domain.

These records intentionally keep stable runtime keys alongside database ids.
Database ids may not exist until the load phase, while runtime keys are needed
to connect parsed pages, evidence rows, vector chunks, and structured outputs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _serialize(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value


class IngestionStatus(str, Enum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    INDEXED = "indexed"
    STRUCTURED = "structured"
    FAILED = "failed"


class ExtractionStatus(str, Enum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class EvidenceBlockType(str, Enum):
    TEXT = "text"
    TABLE = "table"
    TOGGLE = "toggle"
    FORMULA = "formula"
    OTHER = "other"


@dataclass(frozen=True)
class DocumentRecord:
    document_key: str
    title: str
    company_name: str | None = None
    company_id: int | None = None
    source_id: int | None = None
    document_type: str = "sustainability_report"
    report_year: int | None = None
    published_at: date | None = None
    file_path: str | None = None
    file_hash: str | None = None
    language: str | None = None
    page_count: int | None = None
    ingestion_status: IngestionStatus = IngestionStatus.PENDING
    reg_date: datetime = field(default_factory=utc_now)
    registrar: str = "ci_batch"
    metadata: dict[str, Any] = field(default_factory=dict)
    document_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {key: _serialize(value) for key, value in asdict(self).items()}


@dataclass(frozen=True)
class DocumentPageRecord:
    page_key: str
    document_key: str
    page_no: int
    raw_text: str | None = None
    ocr_text: str | None = None
    reg_date: datetime = field(default_factory=utc_now)
    registrar: str = "ci_batch"
    metadata: dict[str, Any] = field(default_factory=dict)
    page_id: int | None = None
    document_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {key: _serialize(value) for key, value in asdict(self).items()}


@dataclass(frozen=True)
class ExtractionRunRecord:
    extraction_key: str
    document_key: str
    extractor_version: str
    extraction_mode: str | None = None
    status: ExtractionStatus = ExtractionStatus.STARTED
    run_started_at: datetime = field(default_factory=utc_now)
    run_finished_at: datetime | None = None
    error_message: str | None = None
    reg_date: datetime = field(default_factory=utc_now)
    registrar: str = "ci_batch"
    metadata: dict[str, Any] = field(default_factory=dict)
    extraction_run_id: int | None = None
    document_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {key: _serialize(value) for key, value in asdict(self).items()}


@dataclass(frozen=True)
class ExtractedEvidenceRecord:
    evidence_key: str
    extraction_key: str
    page_key: str
    block_type: EvidenceBlockType
    raw_snippet: str
    section_hint: str | None = None
    normalized_snippet: str | None = None
    confidence: float | None = None
    locator_json: dict[str, Any] | None = None
    is_methodology_content: bool | None = None
    reg_date: datetime = field(default_factory=utc_now)
    registrar: str = "ci_batch"
    metadata: dict[str, Any] = field(default_factory=dict)
    evidence_id: int | None = None
    extraction_run_id: int | None = None
    page_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {key: _serialize(value) for key, value in asdict(self).items()}

