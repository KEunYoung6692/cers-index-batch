"""
Filesystem helpers scoped to CI_BATCH.
"""

from __future__ import annotations

from pathlib import Path


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def find_ci_batch_root(start: Path | None = None) -> Path:
    here = (start or Path.cwd()).resolve()
    for parent in [here, *here.parents]:
        if parent.name == "CI_BATCH" and (parent / "docs" / "schema.md").exists():
            return parent
        candidate = parent / "CI_BATCH"
        if candidate.is_dir() and (candidate / "docs" / "schema.md").exists():
            return candidate.resolve()
    raise FileNotFoundError("Could not locate CI_BATCH root from current path")


def src_root(ci_batch_root: Path) -> Path:
    return ensure_dir(ci_batch_root / "src")


def docs_root(ci_batch_root: Path) -> Path:
    return ensure_dir(ci_batch_root / "docs")


def storage_root(ci_batch_root: Path) -> Path:
    return ensure_dir(ci_batch_root / "storage")


def manifests_dir(ci_batch_root: Path) -> Path:
    return ensure_dir(storage_root(ci_batch_root) / "manifests")


def parsed_dir(ci_batch_root: Path) -> Path:
    return ensure_dir(storage_root(ci_batch_root) / "parsed")


def chunks_dir(ci_batch_root: Path) -> Path:
    return ensure_dir(storage_root(ci_batch_root) / "chunks")


def rag_dir(ci_batch_root: Path) -> Path:
    return ensure_dir(storage_root(ci_batch_root) / "rag")


def load_dir(ci_batch_root: Path) -> Path:
    return ensure_dir(storage_root(ci_batch_root) / "load")


def qdrant_dir(ci_batch_root: Path) -> Path:
    return ensure_dir(storage_root(ci_batch_root) / "qdrant")


def errors_dir(ci_batch_root: Path) -> Path:
    return ensure_dir(storage_root(ci_batch_root) / "errors")


def run_partition_dir(base_dir: Path, run_date: str, report_key: str | None = None) -> Path:
    partition = ensure_dir(base_dir / run_date)
    if report_key is None:
        return partition
    return ensure_dir(partition / report_key)
