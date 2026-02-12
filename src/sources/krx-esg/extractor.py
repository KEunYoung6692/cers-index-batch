"""
KRX ESG 포털 보고서(PDF) 다운로드 스크립트.
"""

import argparse
import re
import time
from pathlib import Path
from typing import Any

import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import ElementClickInterceptedException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

KRX_ESG_URL = "https://esg.krx.co.kr/contents/02/02030000/ESG02030000.jsp"
SOURCE_NAME = Path(__file__).resolve().parent.name

DETAIL_SEARCH_BUTTON_SELECTOR = "button.detail-search-button"
TCFD_LABEL_SELECTOR = "label.bas_itm_chk"
YEAR_SELECT_ID = "sch_yyc4ca4238a0b923820dcc509a6f75849b"
SEARCH_BUTTON_ID = "btnidc4ca4238a0b923820dcc509a6f75849b"
REPORT_BUTTON_SELECTOR = "a.icon_down.id_s2301.useK"
INDUSTRY_CELL_SELECTOR = 'td[name="upjong"]'
PAGINATION_SELECTOR = "div.pagination"
NEXT_PAGE_ITEM_SELECTOR = "li.next"

ATTACHED_DOC_SELECT_ID = "attachedDoc"
DOC_FRAME_ID = "docViewFrm"
PDF_LINK_SELECTOR = 'a[href$=".pdf"], a[href*=".pdf"]'
NO_RESULTS_XPATH = (
    "//*[contains(., '조회된 데이터가 없습니다') or "
    "contains(., '검색 결과가 없습니다') or "
    "contains(., '데이터가 없습니다')]"
)
FRAME_KEYS = {"gri", "sasb", "tcfd", "un_sdgs"}

METADATA_COLUMNS = [
    "year",
    "report_year",
    "company_type",
    "country",
    "page_idx",
    "row_idx",
    "company_name",
    "industry",
    "frameworks",
    "list_assurance_org",
    "report_name",
    "detail_assurance_org",
    "homepage",
    "submit_date",
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


def sanitize_path_segment(name: str) -> str:
    text = (name or "").strip()
    if not text:
        return "etc"
    invalid = '<>:"/\\|?*'
    for ch in invalid:
        text = text.replace(ch, "_")
    return text[:100] or "etc"


def safe_click(driver, element) -> None:
    try:
        element.click()
    except ElementClickInterceptedException:
        driver.execute_script("arguments[0].click();", element)


def has_no_results(driver) -> bool:
    return len(driver.find_elements(By.XPATH, NO_RESULTS_XPATH)) > 0


def wait_report_buttons_or_no_results(driver, timeout: int) -> None:
    WebDriverWait(driver, timeout).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, REPORT_BUTTON_SELECTOR)) > 0 or has_no_results(d)
    )


def select_tcfd_filter(driver, timeout: int) -> None:
    labels = WebDriverWait(driver, timeout).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, TCFD_LABEL_SELECTOR))
    )

    target = None
    for label in labels:
        if "TCFD" in (label.text or "").upper():
            target = label
            break
    if target is None and len(labels) > 2:
        target = labels[2]
    if target is None:
        raise RuntimeError("TCFD filter label not found.")

    safe_click(driver, target)


def apply_filters(driver, year: int, timeout: int) -> None:
    detail_button = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, DETAIL_SEARCH_BUTTON_SELECTOR))
    )
    safe_click(driver, detail_button)

    select_tcfd_filter(driver, timeout=timeout)

    year_select = Select(driver.find_element(By.ID, YEAR_SELECT_ID))
    year_select.select_by_value(str(year))

    search_buttons = driver.find_elements(By.ID, SEARCH_BUTTON_ID)
    if not search_buttons:
        raise RuntimeError("Search button not found.")

    search_button = next((btn for btn in search_buttons if btn.is_displayed()), search_buttons[-1])
    safe_click(driver, search_button)

    wait_report_buttons_or_no_results(driver, timeout=timeout)


def extract_frameworks_from_row(row) -> str | None:
    try:
        framework_td = row.find_element(By.CSS_SELECTOR, 'td[name="bas_itm_cd_nm"]')
        spans = framework_td.find_elements(By.CSS_SELECTOR, "span.stan-icon")
        frameworks = set()
        for span in spans:
            class_attr = span.get_attribute("class") or ""
            classes = set(class_attr.split())
            frameworks.update(FRAME_KEYS.intersection(classes))
        return ",".join(sorted(frameworks)) if frameworks else None
    except Exception:
        return None


def extract_list_metadata_from_button(button, *, year: int, page_idx: int, row_idx: int) -> dict[str, Any]:
    try:
        row = button.find_element(By.XPATH, "./ancestor::tr[1]")
    except Exception:
        return {
            "year": year,
            "report_year": str(year),
            "company_type": "legal_entity",
            "country": "KR",
            "page_idx": page_idx,
            "row_idx": row_idx,
            "company_name": None,
            "industry": None,
            "frameworks": None,
            "list_assurance_org": None,
            "report_name": None,
            "detail_assurance_org": None,
            "homepage": None,
            "submit_date": None,
            "download_status": "error",
            "downloaded_file": None,
            "error": "failed to resolve table row from button",
        }
    company_name = None
    industry = None
    list_assurance_org = None

    try:
        company_td = row.find_element(By.CSS_SELECTOR, 'td[name="com_abbrv"]')
        lines = [line.strip() for line in company_td.text.splitlines() if line.strip()]
        company_name = lines[0] if lines else None
    except Exception:
        pass

    try:
        industry_td = row.find_element(By.CSS_SELECTOR, INDUSTRY_CELL_SELECTOR)
        industry_lines = [line.strip() for line in industry_td.text.splitlines() if line.strip()]
        industry = industry_lines[-1] if industry_lines else None
    except Exception:
        pass

    try:
        assurance_td = row.find_element(By.CSS_SELECTOR, 'td[name="remk"]')
        assurance_lines = [line.strip() for line in assurance_td.text.splitlines() if line.strip()]
        list_assurance_org = assurance_lines[-1] if assurance_lines else None
    except Exception:
        pass

    return {
        "year": year,
        "report_year": str(year),
        "company_type": "legal_entity",
        "country": "KR",
        "page_idx": page_idx,
        "row_idx": row_idx,
        "company_name": company_name,
        "industry": industry,
        "frameworks": extract_frameworks_from_row(row),
        "list_assurance_org": list_assurance_org,
        "report_name": None,
        "detail_assurance_org": None,
        "homepage": None,
        "submit_date": None,
        "download_status": "pending",
        "downloaded_file": None,
        "error": None,
    }


def select_preferred_pdf_link(links):
    keywords = ("국문", "한글", "kor")
    for link in links:
        text = (link.text or "").lower()
        if any(keyword in text for keyword in keywords):
            return link
    return links[0] if links else None


def extract_popup_metadata_from_doc_frame(driver) -> dict[str, Any]:
    spans = driver.find_elements(By.CSS_SELECTOR, "span.xforms_input")

    def safe_get(index: int) -> str | None:
        if len(spans) <= index:
            return None
        value = (spans[index].text or "").strip()
        return value or None

    homepage_raw = safe_get(4)
    homepage = None
    if homepage_raw:
        match = re.search(r"(https?://[^\s)]+)", homepage_raw)
        homepage = match.group(1) if match else homepage_raw

    return {
        "report_name": safe_get(0),
        "detail_assurance_org": safe_get(1),
        "homepage": homepage,
        "submit_date": safe_get(6),
    }


def wait_download_complete(download_dir: Path, before_files: set[str], timeout: int) -> Path:
    end = time.time() + timeout
    while time.time() < end:
        current_paths = [p for p in download_dir.iterdir() if p.is_file()]
        current_files = {p.name for p in current_paths}
        new_files = current_files - before_files
        completed_new_paths = [p for p in current_paths if p.name in new_files and not p.name.endswith(".crdownload")]
        has_partial = any(name.endswith(".crdownload") for name in current_files)
        if completed_new_paths and not has_partial:
            completed_new_paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return completed_new_paths[0]
        time.sleep(0.3)
    raise TimeoutException(f"download did not finish within {timeout}s: {download_dir}")


def handle_report_popup_and_download(
    driver,
    *,
    main_handle: str,
    download_dir: Path,
    timeout: int,
    download_wait_timeout: int,
) -> tuple[dict[str, Any], Path]:
    WebDriverWait(driver, timeout).until(lambda d: len(d.window_handles) > 1)

    popup_handle = next((h for h in driver.window_handles if h != main_handle), None)
    if popup_handle is None:
        raise RuntimeError("Popup window not found.")

    driver.switch_to.window(popup_handle)
    popup_metadata: dict[str, Any] = {
        "report_name": None,
        "detail_assurance_org": None,
        "homepage": None,
        "submit_date": None,
    }
    try:
        select_el = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.ID, ATTACHED_DOC_SELECT_ID))
        )
        select = Select(select_el)
        if len(select.options) > 1:
            select.select_by_index(1)

        WebDriverWait(driver, timeout).until(
            EC.frame_to_be_available_and_switch_to_it((By.ID, DOC_FRAME_ID))
        )
        popup_metadata = extract_popup_metadata_from_doc_frame(driver)

        pdf_links = WebDriverWait(driver, timeout).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, PDF_LINK_SELECTOR))
        )
        selected_link = select_preferred_pdf_link(pdf_links)
        if selected_link is None:
            raise RuntimeError("PDF link not found.")

        before_files = {p.name for p in download_dir.iterdir() if p.is_file()}
        driver.execute_cdp_cmd(
            "Page.setDownloadBehavior",
            {"behavior": "allow", "downloadPath": str(download_dir)},
        )
        safe_click(driver, selected_link)
        downloaded_path = wait_download_complete(download_dir, before_files, timeout=download_wait_timeout)
        return popup_metadata, downloaded_path
    finally:
        try:
            driver.switch_to.default_content()
        except Exception:
            pass
        driver.close()
        driver.switch_to.window(main_handle)


def download_reports_on_current_page(
    driver,
    *,
    year: int,
    page_idx: int,
    year_download_dir: Path,
    timeout: int,
    download_wait_timeout: int,
) -> tuple[int, list[dict[str, Any]]]:
    main_handle = driver.current_window_handle
    report_buttons = driver.find_elements(By.CSS_SELECTOR, REPORT_BUTTON_SELECTOR)
    total = len(report_buttons)
    success_count = 0
    metadata_rows: list[dict[str, Any]] = []

    for idx in range(total):
        report_buttons = driver.find_elements(By.CSS_SELECTOR, REPORT_BUTTON_SELECTOR)
        if idx >= len(report_buttons):
            break

        button = report_buttons[idx]
        if not button.is_displayed():
            continue

        row_metadata = extract_list_metadata_from_button(
            button,
            year=year,
            page_idx=page_idx,
            row_idx=idx,
        )

        industry_display = row_metadata.get("industry") or "etc"
        industry_dir = year_download_dir / sanitize_path_segment(industry_display)
        industry_dir.mkdir(parents=True, exist_ok=True)

        try:
            driver.switch_to.window(main_handle)
            safe_click(driver, button)
            popup_metadata, downloaded_path = handle_report_popup_and_download(
                driver,
                main_handle=main_handle,
                download_dir=industry_dir,
                timeout=timeout,
                download_wait_timeout=download_wait_timeout,
            )
            row_metadata.update(popup_metadata)
            row_metadata["download_status"] = "success"
            row_metadata["downloaded_file"] = str(downloaded_path.relative_to(year_download_dir))
            success_count += 1
            print(f"[{industry_display}] download success ({idx + 1}/{total})")
        except TimeoutException as exc:
            row_metadata["download_status"] = "timeout"
            row_metadata["error"] = repr(exc)
            print(f"[{industry_display}] timeout ({idx + 1}/{total}): {exc}")
        except Exception as exc:
            row_metadata["download_status"] = "error"
            row_metadata["error"] = repr(exc)
            print(f"[{industry_display}] error ({idx + 1}/{total}): {exc}")
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                driver.switch_to.window(main_handle)
            except Exception:
                pass
        finally:
            metadata_rows.append(row_metadata)

    return success_count, metadata_rows


def go_next_page_if_possible(driver, timeout: int) -> bool:
    try:
        pagination = driver.find_element(By.CSS_SELECTOR, PAGINATION_SELECTOR)
        next_li = pagination.find_element(By.CSS_SELECTOR, NEXT_PAGE_ITEM_SELECTOR)
    except Exception:
        return False

    classes = next_li.get_attribute("class") or ""
    if "disabled" in classes:
        return False

    current_first = None
    buttons = driver.find_elements(By.CSS_SELECTOR, REPORT_BUTTON_SELECTOR)
    if buttons:
        current_first = buttons[0]

    next_anchor = next_li.find_element(By.TAG_NAME, "a")
    safe_click(driver, next_anchor)

    if current_first is not None:
        try:
            WebDriverWait(driver, timeout).until(EC.staleness_of(current_first))
        except TimeoutException:
            pass

    wait_report_buttons_or_no_results(driver, timeout=timeout)
    return True


def build_driver(*, default_download_dir: Path, headless: bool, page_load_timeout: int) -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36"
    )
    if headless:
        options.add_argument("--headless=new")

    prefs = {
        "download.default_directory": str(default_download_dir),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True,
    }
    options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(page_load_timeout)
    return driver


def parse_args(repo_root: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KRX ESG report downloader.")
    parser.add_argument("--years", nargs="+", type=int, required=True, help="Download target years. e.g. 2023 2024 2025")
    parser.add_argument("--url", default=KRX_ESG_URL)
    parser.add_argument("--download-root", type=Path, default=Path("storage") / "raw" / SOURCE_NAME / "reports")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--download-wait-timeout", type=int, default=30)
    parser.add_argument("--page-load-timeout", type=int, default=60)
    parser.add_argument("--sleep-sec", type=float, default=0.3, help="Sleep between pages.")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    if args.timeout < 1:
        parser.error("--timeout must be >= 1")
    if args.download_wait_timeout < 1:
        parser.error("--download-wait-timeout must be >= 1")
    if args.page_load_timeout < 1:
        parser.error("--page-load-timeout must be >= 1")
    if args.sleep_sec < 0:
        parser.error("--sleep-sec must be >= 0")

    args.download_root = resolve_path(args.download_root, repo_root)
    return args


def save_metadata_csv(metadata_rows: list[dict[str, Any]], metadata_path: Path) -> None:
    if metadata_rows:
        df = pd.DataFrame(metadata_rows)
    else:
        df = pd.DataFrame(columns=METADATA_COLUMNS)

    for column in METADATA_COLUMNS:
        if column not in df.columns:
            df[column] = None
    df = df[METADATA_COLUMNS]
    df.to_csv(metadata_path, index=False, encoding="utf-8-sig")


def download_all_pages_for_year(
    year: int,
    *,
    url: str,
    year_download_dir: Path,
    timeout: int,
    download_wait_timeout: int,
    page_load_timeout: int,
    sleep_sec: float,
    headless: bool,
) -> None:
    year_download_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = year_download_dir / "metadata.csv"

    driver = build_driver(
        default_download_dir=year_download_dir,
        headless=headless,
        page_load_timeout=page_load_timeout,
    )
    try:
        driver.get(url)
        apply_filters(driver, year=year, timeout=timeout)

        page_num = 1
        total_downloaded = 0
        all_metadata_rows: list[dict[str, Any]] = []
        while True:
            downloaded, page_metadata = download_reports_on_current_page(
                driver,
                year=year,
                page_idx=page_num,
                year_download_dir=year_download_dir,
                timeout=timeout,
                download_wait_timeout=download_wait_timeout,
            )
            all_metadata_rows.extend(page_metadata)
            total_downloaded += downloaded
            print(f"[year={year}] page={page_num} downloaded={downloaded} total={total_downloaded}")

            moved = go_next_page_if_possible(driver, timeout=timeout)
            if not moved:
                break
            page_num += 1
            if sleep_sec > 0:
                time.sleep(sleep_sec)
        save_metadata_csv(all_metadata_rows, metadata_path)
        print(f"[year={year}] metadata saved: {metadata_path} rows={len(all_metadata_rows)}")
    finally:
        driver.quit()


def run(args: argparse.Namespace) -> None:
    years = sorted(set(args.years))
    print(f"years={years}")
    print(f"download_root={args.download_root}")

    for year in years:
        print(f"\n{'=' * 50}")
        print(f"{year}년도 보고서 다운로드 시작")
        print(f"{'=' * 50}")
        year_dir = args.download_root / str(year)
        download_all_pages_for_year(
            year,
            url=args.url,
            year_download_dir=year_dir,
            timeout=args.timeout,
            download_wait_timeout=args.download_wait_timeout,
            page_load_timeout=args.page_load_timeout,
            sleep_sec=args.sleep_sec,
            headless=args.headless,
        )
        print(f"{year}년도 보고서 다운로드 완료")


def main() -> None:
    repo_root = find_repo_root()
    args = parse_args(repo_root)
    run(args)


if __name__ == "__main__":
    main()
