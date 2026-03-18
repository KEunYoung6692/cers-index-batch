"""
Environment-backed settings for CI_BATCH.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from .env import load_env_file
from .storage import find_ci_batch_root, storage_root


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


@dataclass(frozen=True)
class BatchSettings:
    ci_batch_root: Path
    schema_doc_path: Path
    storage_dir: Path
    registrar: str
    extractor_version: str
    embedding_model: str
    embedding_dimensions: int | None
    structuring_model: str
    vector_db_backend: str
    vector_db_collection: str
    openai_api_key_env: str
    embedding_batch_size: int
    chunk_target_tokens: int
    chunk_overlap_tokens: int


def load_settings(start: Path | None = None) -> BatchSettings:
    ci_batch_root = find_ci_batch_root(start)
    load_env_file(ci_batch_root / ".env")
    return BatchSettings(
        ci_batch_root=ci_batch_root,
        schema_doc_path=ci_batch_root / "docs" / "schema.md",
        storage_dir=storage_root(ci_batch_root),
        registrar=_env("CI_BATCH_REGISTRAR", "ci_batch"),
        extractor_version=_env("CI_BATCH_EXTRACTOR_VERSION", "0.1.0"),
        embedding_model=_env("CI_BATCH_EMBEDDING_MODEL", "text-embedding-3-large"),
        embedding_dimensions=(_env_int("CI_BATCH_EMBEDDING_DIMENSIONS", 0) or None),
        structuring_model=_env("CI_BATCH_STRUCTURING_MODEL", "gpt-4o-mini"),
        vector_db_backend=_env("CI_BATCH_VECTOR_DB_BACKEND", "qdrant"),
        vector_db_collection=_env("CI_BATCH_VECTOR_DB_COLLECTION", "reports_chunks"),
        openai_api_key_env=_env("CI_BATCH_OPENAI_API_KEY_ENV", "OPENAI_API_KEY"),
        embedding_batch_size=_env_int("CI_BATCH_EMBEDDING_BATCH_SIZE", 32),
        chunk_target_tokens=_env_int("CI_BATCH_CHUNK_TARGET_TOKENS", 1000),
        chunk_overlap_tokens=_env_int("CI_BATCH_CHUNK_OVERLAP_TOKENS", 120),
    )
