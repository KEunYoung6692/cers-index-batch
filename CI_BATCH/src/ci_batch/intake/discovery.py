"""
Document discovery for the CI_BATCH intake stage.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Iterable

from ci_batch.contracts import DocumentRecord


PDF_GLOB = "*.pdf"


def iter_pdf_files(input_dir: Path) -> Iterable[Path]:
    return sorted(path for path in input_dir.rglob(PDF_GLOB) if path.is_file())


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fp:
        while True:
            chunk = fp.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def normalize_company_name(stem: str) -> str:
    value = re.sub(
        r"[_\-\s]*(?:지속가능경영|지속가능|sustainability|esg|annual)?[_\-\s]*보고서.*$",
        "",
        stem,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"[_\-\s]+", " ", value).strip()
    return value or stem.strip()


def slugify_identifier(value: str) -> str:
    slug = value.strip().lower()
    slug = re.sub(r"[^0-9a-zA-Z가-힣]+", "_", slug)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "unknown"


def infer_report_year_from_name(stem: str) -> int | None:
    candidates = re.findall(r"(?:19|20)\d{2}", stem)
    if not candidates:
        return None
    return int(candidates[-1])


def infer_report_year_from_path(pdf_path: Path, input_dir: Path) -> int | None:
    input_dir = input_dir.resolve()
    for parent in [pdf_path.parent, *pdf_path.parent.parents]:
        if parent == input_dir.parent:
            break
        match = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", parent.name)
        if match:
            return int(match.group(1))
        if parent == input_dir:
            break
    return None


@dataclass(frozen=True)
class DiscoveryResult:
    document: DocumentRecord
    file_size_bytes: int


def build_document_record(
    pdf_path: Path,
    *,
    input_dir: Path,
    registrar: str,
    source_id: int | None = None,
) -> DiscoveryResult:
    company_name = normalize_company_name(pdf_path.stem)
    report_year = infer_report_year_from_path(pdf_path, input_dir) or infer_report_year_from_name(pdf_path.stem)
    file_hash = sha256_file(pdf_path)
    company_slug = slugify_identifier(company_name)
    year_token = str(report_year) if report_year is not None else "unknown"
    report_year_source = (
        "path"
        if infer_report_year_from_path(pdf_path, input_dir) is not None
        else ("file_name" if infer_report_year_from_name(pdf_path.stem) is not None else "unknown")
    )
    document_key = f"{company_slug}_{year_token}_{file_hash[:8]}"
    document = DocumentRecord(
        document_key=document_key,
        title=pdf_path.stem,
        company_name=company_name,
        source_id=source_id,
        report_year=report_year,
        file_path=str(pdf_path.resolve()),
        file_hash=file_hash,
        page_count=None,
        registrar=registrar,
        metadata={
            "source_file_name": pdf_path.name,
            "company_slug": company_slug,
            "file_size_bytes": pdf_path.stat().st_size,
            "relative_path": str(pdf_path.resolve().relative_to(input_dir.resolve())),
            "report_year_source": report_year_source,
        },
    )
    return DiscoveryResult(document=document, file_size_bytes=pdf_path.stat().st_size)


def discover_documents(
    input_dir: Path,
    *,
    registrar: str,
    source_id: int | None = None,
) -> list[DiscoveryResult]:
    input_dir = input_dir.resolve()
    return [
        build_document_record(pdf_path, input_dir=input_dir, registrar=registrar, source_id=source_id)
        for pdf_path in iter_pdf_files(input_dir)
    ]
