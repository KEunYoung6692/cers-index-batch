"""
Storage path helpers.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


VALID_LAYERS = {"raw", "parsed", "curated"}


def find_repo_root(start: Path | None = None) -> Path:
    here = (start or Path.cwd()).resolve()
    for parent in [here, *here.parents]:
        if (parent / "README.md").exists() and (parent / "src").exists():
            return parent
    return here


def validate_run_date(run_date: str) -> str:
    datetime.strptime(run_date, "%Y-%m-%d")
    return run_date


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def storage_root(repo_root: Path) -> Path:
    return ensure_dir(repo_root / "storage")


def layer_dir(repo_root: Path, layer: str) -> Path:
    if layer not in VALID_LAYERS and layer != "manifests":
        raise ValueError(f"Unsupported storage layer: {layer}")
    return ensure_dir(storage_root(repo_root) / layer)


def source_partition_dir(repo_root: Path, layer: str, source_name: str, run_date: str) -> Path:
    if layer not in VALID_LAYERS:
        raise ValueError(f"source partitions are only valid for {sorted(VALID_LAYERS)}")
    validate_run_date(run_date)
    return ensure_dir(layer_dir(repo_root, layer) / source_name / run_date)


def output_file_path(
    repo_root: Path,
    *,
    layer: str,
    source_name: str,
    run_date: str,
    filename: str,
) -> Path:
    return source_partition_dir(repo_root, layer, source_name, run_date) / filename


def manifest_file_path(repo_root: Path, run_id: str) -> Path:
    return layer_dir(repo_root, "manifests") / f"{run_id}.json"

