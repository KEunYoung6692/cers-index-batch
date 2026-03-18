"""
Run context utilities for CI_BATCH.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

from .storage import manifests_dir


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class RunContext:
    batch_name: str
    run_id: str
    run_date: str
    started_at: str
    ci_batch_root: Path

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["ci_batch_root"] = str(self.ci_batch_root)
        return payload

    def default_manifest_path(self) -> Path:
        return manifests_dir(self.ci_batch_root) / f"{self.run_id}.json"


def make_run_context(
    *,
    batch_name: str,
    ci_batch_root: Path,
    run_date: str | None = None,
    now: datetime | None = None,
) -> RunContext:
    current = now or utc_now()
    resolved_run_date = run_date or current.strftime("%Y-%m-%d")
    timestamp = current.strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:8]
    run_id = f"run_{batch_name}_{timestamp}_{suffix}"
    return RunContext(
        batch_name=batch_name,
        run_id=run_id,
        run_date=resolved_run_date,
        started_at=utc_iso(current),
        ci_batch_root=ci_batch_root.resolve(),
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
    temp_path = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(manifest_path)
    return manifest_path

