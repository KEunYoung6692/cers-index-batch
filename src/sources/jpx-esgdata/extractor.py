"""
JPX ESG Data metadata collector and PDF downloader.
"""

import argparse
import csv
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

DEFAULT_URL = "https://jpx.esgdata.jp/app"
SOURCE_NAME = Path(__file__).resolve().parent.name
NEXT_PAGE_SELECTORS = [
    "button:has-text('Next')",
    "button:has-text('>')",
    "button:has-text('＞')",
    "button:has-text('次へ')",
    "a:has-text('Next')",
    "a:has-text('次へ')",
]

METADATA_FIELDS = [
    "date",
    "company",
    "code",
    "category",
    "title",
    "pdf_url",
    "tags",
    "page_idx",
    "download_status",
    "downloaded_file",
    "error",
]


def find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "README.md").exists() and (parent / "src").exists():
            return parent
    return Path.cwd()


def resolve_path(path: Path, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", (name or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:180] if len(cleaned) > 180 else cleaned


def guess_pdf_filename(pdf_url: str, code: str, date_str: str, title: str) -> str:
    path = urlparse(pdf_url).path
    base = Path(path).name
    if base.lower().endswith(".pdf") and len(base) > 5:
        return safe_filename(f"{date_str}_{code}_{base}")
    return safe_filename(f"{date_str}_{code}_{title}.pdf")


def polite_sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def extract_rows(page, base_url: str, page_idx: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    tr_locator = page.locator("table tbody tr")
    count = tr_locator.count()

    for i in range(count):
        tr = tr_locator.nth(i)
        tds = tr.locator("td")
        td_count = tds.count()
        if td_count < 5:
            continue

        date_str = (tds.nth(0).inner_text() or "").strip()
        company = (tds.nth(1).inner_text() or "").strip()
        code = (tds.nth(2).inner_text() or "").strip()
        category = (tds.nth(3).inner_text() or "").strip()

        link_locator = tds.nth(4).locator("a")
        if link_locator.count() == 0:
            continue

        title = (link_locator.first.inner_text() or "").strip()
        href = link_locator.first.get_attribute("href")
        if not href:
            continue
        pdf_url = urljoin(base_url, href)

        tags = ""
        if td_count >= 6:
            tags = (tds.nth(5).inner_text() or "").strip()

        if ".pdf" not in pdf_url.lower():
            continue

        rows.append(
            {
                "date": date_str,
                "company": company,
                "code": code,
                "category": category,
                "title": title,
                "pdf_url": pdf_url,
                "tags": tags,
                "page_idx": page_idx,
                "download_status": "pending",
                "downloaded_file": None,
                "error": None,
            }
        )
    return rows


def try_click_next(page, timeout_ms: int, page_delay_sec: float) -> bool:
    for selector in NEXT_PAGE_SELECTORS:
        loc = page.locator(selector)
        if loc.count() == 0:
            continue

        btn = loc.first
        disabled = btn.get_attribute("disabled")
        aria_disabled = (btn.get_attribute("aria-disabled") or "").lower()
        if disabled is not None or aria_disabled == "true":
            return False

        try:
            first_row = page.locator("table tbody tr").first
            btn.click()
            if first_row.count() > 0:
                try:
                    first_row.wait_for(state="detached", timeout=timeout_ms)
                except Exception:
                    pass
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
            polite_sleep(page_delay_sec)
            return True
        except Exception:
            return False
    return False


def collect_metadata(
    *,
    url: str,
    max_pages: int,
    timeout_ms: int,
    page_delay_sec: float,
    headless: bool,
) -> list[dict[str, Any]]:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError("playwright is required. Install with: pip install playwright") from exc

    all_rows: list[dict[str, Any]] = []
    seen = set()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        page.goto(url, wait_until="networkidle")
        page.wait_for_selector("table tbody tr", timeout=timeout_ms)
        polite_sleep(page_delay_sec)

        for page_idx in range(1, max_pages + 1):
            rows = extract_rows(page, base_url=url, page_idx=page_idx)
            new_count = 0
            for row in rows:
                key = (row["date"], row["code"], row["pdf_url"])
                if key in seen:
                    continue
                seen.add(key)
                all_rows.append(row)
                new_count += 1

            print(f"page={page_idx} collected={new_count} total={len(all_rows)}")

            if not try_click_next(page, timeout_ms=timeout_ms, page_delay_sec=page_delay_sec):
                break

        browser.close()

    return all_rows


def download_pdf(
    *,
    session: requests.Session,
    pdf_url: str,
    save_path: Path,
    referer: str,
    timeout_sec: int,
) -> bool:
    if save_path.exists() and save_path.stat().st_size > 0:
        return True

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": referer,
    }

    try:
        with session.get(pdf_url, headers=headers, stream=True, timeout=timeout_sec) as response:
            if response.status_code != 200:
                return False

            tmp_path = save_path.with_suffix(save_path.suffix + ".part")
            with tmp_path.open("wb") as file:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        file.write(chunk)
            tmp_path.replace(save_path)
        return True
    except Exception:
        return False


def download_pdfs(
    rows: list[dict[str, Any]],
    *,
    pdf_dir: Path,
    referer: str,
    delay_sec: float,
    timeout_sec: int,
) -> None:
    pdf_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    for idx, row in enumerate(rows, start=1):
        date_text = (row.get("date") or "").replace("/", "-")
        filename = guess_pdf_filename(
            pdf_url=row["pdf_url"],
            code=row.get("code") or "NA",
            date_str=date_text or "NA",
            title=row.get("title") or "untitled",
        )
        save_path = pdf_dir / filename

        ok = download_pdf(
            session=session,
            pdf_url=row["pdf_url"],
            save_path=save_path,
            referer=referer,
            timeout_sec=timeout_sec,
        )
        if ok:
            row["download_status"] = "success"
            row["downloaded_file"] = str(save_path.relative_to(pdf_dir.parent))
            row["error"] = None
        else:
            row["download_status"] = "failed"
            row["downloaded_file"] = None
            row["error"] = "download_failed"

        print(f"[{idx}/{len(rows)}] {row['download_status']} {save_path}")
        polite_sleep(delay_sec)


def save_metadata(rows: list[dict[str, Any]], metadata_path: Path) -> None:
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with metadata_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=METADATA_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def parse_args(repo_root: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JPX ESGData extractor.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--max-pages", type=int, default=50)
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--page-delay-sec", type=float, default=0.8)
    parser.add_argument("--download-delay-sec", type=float, default=0.5)
    parser.add_argument("--download-timeout-sec", type=int, default=60)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--skip-download", action="store_true")

    parser.add_argument("--run-date", help="Output partition date (YYYY-MM-DD).")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--metadata-file", type=Path)
    parser.add_argument("--pdf-dir", type=Path)
    args = parser.parse_args()

    if args.max_pages < 1:
        parser.error("--max-pages must be >= 1")
    if args.timeout_ms < 1000:
        parser.error("--timeout-ms must be >= 1000")
    if args.page_delay_sec < 0:
        parser.error("--page-delay-sec must be >= 0")
    if args.download_delay_sec < 0:
        parser.error("--download-delay-sec must be >= 0")
    if args.download_timeout_sec < 1:
        parser.error("--download-timeout-sec must be >= 1")
    if args.run_date:
        try:
            datetime.strptime(args.run_date, "%Y-%m-%d")
        except ValueError as exc:
            parser.error(f"--run-date must be YYYY-MM-DD: {exc}")

    if args.output_dir:
        args.output_dir = resolve_path(args.output_dir, repo_root)
    if args.metadata_file:
        args.metadata_file = resolve_path(args.metadata_file, repo_root)
    if args.pdf_dir:
        args.pdf_dir = resolve_path(args.pdf_dir, repo_root)
    return args


def resolve_output_paths(args: argparse.Namespace, repo_root: Path) -> tuple[Path, Path]:
    if args.output_dir:
        output_dir = args.output_dir
    else:
        run_date = args.run_date or datetime.now().strftime("%Y-%m-%d")
        output_dir = repo_root / "storage" / "raw" / SOURCE_NAME / run_date

    metadata_path = args.metadata_file or (output_dir / "metadata.csv")
    pdf_dir = args.pdf_dir or (output_dir / "pdfs")

    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    return metadata_path, pdf_dir


def run(args: argparse.Namespace, metadata_path: Path, pdf_dir: Path) -> None:
    rows = collect_metadata(
        url=args.url,
        max_pages=args.max_pages,
        timeout_ms=args.timeout_ms,
        page_delay_sec=args.page_delay_sec,
        headless=args.headless,
    )
    print(f"metadata collected: {len(rows)}")

    if not args.skip_download:
        download_pdfs(
            rows,
            pdf_dir=pdf_dir,
            referer=args.url,
            delay_sec=args.download_delay_sec,
            timeout_sec=args.download_timeout_sec,
        )
    else:
        for row in rows:
            row["download_status"] = "skipped"

    save_metadata(rows, metadata_path)
    print(f"metadata saved: {metadata_path}")


def main() -> None:
    repo_root = find_repo_root()
    args = parse_args(repo_root)
    metadata_path, pdf_dir = resolve_output_paths(args, repo_root)
    run(args, metadata_path, pdf_dir)


if __name__ == "__main__":
    main()
