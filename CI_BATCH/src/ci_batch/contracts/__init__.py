"""
Intermediate record contracts for schema-aligned batch processing.
"""

from .facts import StructuredFactRecord
from .ingestion import (
    DocumentRecord,
    DocumentPageRecord,
    EvidenceBlockType,
    ExtractedEvidenceRecord,
    ExtractionRunRecord,
    ExtractionStatus,
    IngestionStatus,
)
from .load import TableLoadRecord
from .retrieval import ChunkRecord

__all__ = [
    "ChunkRecord",
    "DocumentRecord",
    "DocumentPageRecord",
    "EvidenceBlockType",
    "ExtractedEvidenceRecord",
    "ExtractionRunRecord",
    "ExtractionStatus",
    "IngestionStatus",
    "StructuredFactRecord",
    "TableLoadRecord",
]
