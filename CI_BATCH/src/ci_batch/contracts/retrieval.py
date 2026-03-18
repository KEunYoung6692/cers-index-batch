"""
Intermediate contracts for retrieval and chunking artifacts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {key: _serialize(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value


@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    document_key: str
    content: str
    company_name: str | None = None
    report_year: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    page_keys: list[str] = field(default_factory=list)
    evidence_keys: list[str] = field(default_factory=list)
    chunk_type: str = "text"
    section_hint: str | None = None
    reg_date: datetime = field(default_factory=utc_now)
    registrar: str = "ci_batch"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {key: _serialize(value) for key, value in asdict(self).items()}
