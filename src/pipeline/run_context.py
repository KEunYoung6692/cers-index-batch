"""
Run context utilities for batch jobs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid


DEFAULT_MANIFEST_DIR = Path("storage") / "manifests"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class RunContext:
    source_name: str
    run_id: str
    run_date: str
    started_at: str
    repo_root: Path

    def to_dict(self) -> dict:
        data = asdict(self)
        data["repo_root"] = str(self.repo_root)
        return data

    def default_manifest_path(self, manifest_dir: Path | None = None) -> Path:
        target_dir = self.repo_root / (manifest_dir or DEFAULT_MANIFEST_DIR)
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / f"{self.run_id}.json"


def make_run_context(
    *,
    source_name: str,
    repo_root: Path,
    run_date: str | None = None,
    now: datetime | None = None,
) -> RunContext:
    current = now or utc_now()
    resolved_run_date = run_date or current.strftime("%Y-%m-%d")
    timestamp = current.strftime("%Y%m%dT%H%M%SZ")
    rand = uuid.uuid4().hex[:8]
    run_id = f"run_{source_name}_{timestamp}_{rand}"
    return RunContext(
        source_name=source_name,
        run_id=run_id,
        run_date=resolved_run_date,
        started_at=to_utc_iso(current),
        repo_root=repo_root.resolve(),
    )


def write_manifest(
    context: RunContext,
    *,
    extra: dict | None = None,
    output_path: Path | None = None,
) -> Path:
    payload = context.to_dict()
    if extra:
        payload["extra"] = extra

    manifest_path = output_path or context.default_manifest_path()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(manifest_path)
    return manifest_path

