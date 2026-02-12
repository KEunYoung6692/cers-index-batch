"""
글로벌 기준 탄소배출 정보 조회 사이트 : 
"""

import argparse
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlsplit, urlunsplit

import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import ElementClickInterceptedException, TimeoutException
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE_ORIGIN = "https://nzdpu.com"
DEFAULT_DATA_EXPLORER_URL = f"{BASE_ORIGIN}/data-explorer"
SOURCE_NAME = Path(__file__).resolve().parent.name

TABLE_SELECTOR = 'table[aria-labelledby="Data Explorer Table"]'
TABLE_ROW_SELECTOR = f"{TABLE_SELECTOR} tbody tr"
COMPANY_LINK_SELECTOR = 'tbody tr td[data-attr-name="company_name"] a'
NEXT_PAGE_BUTTON_SELECTOR = 'button[aria-label="Next page"]'
NO_RESULTS_XPATH = "//*[contains(., '검색된 기록이 없습니다') or contains(., 'No records found')]"

NULL_TOKENS = {"—", "–", "-", ""}


def find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "README.md").exists() and (parent / "src").exists():
            return parent
    return Path.cwd()


def resolve_path(path: Path, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def split_url_params(url: str) -> tuple[str, dict[str, list[str]]]:
    sp = urlsplit(url)
    base = urlunsplit((sp.scheme, sp.netloc, sp.path, "", ""))
    params = parse_qs(sp.query, keep_blank_values=True)
    return base, params


def normalize_csv_value(value: str) -> str:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    return ",".join(parts)


def build_url(base: str, params: dict[str, list[str]]) -> str:
    # 이 사이트는 query encoding 시 공백을 "+"보다 "%20"로 보내는 편이 안정적이다.
    normalized = {k: list(v) for k, v in params.items()}
    for key in ("sics_sector", "reporting_year", "metric"):
        if key in normalized and normalized[key]:
            normalized[key][0] = normalize_csv_value(normalized[key][0])

    qs = urlencode(normalized, doseq=True, quote_via=quote)
    return base + (f"?{qs}" if qs else "")


def parse_query_params(raw_params: list[str]) -> dict[str, list[str]]:
    parsed: dict[str, list[str]] = {}
    for item in raw_params:
        if "=" not in item:
            raise ValueError(f"--query-param must be KEY=VALUE format: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(f"--query-param key is empty: {item}")
        parsed.setdefault(key, []).append(value)
    return parsed


def apply_filter_overrides(
    params: dict[str, list[str]],
    *,
    data_provider: str | None,
    sics_sector: str | None,
    jurisdiction: str | None,
    reporting_year: str | None,
    metric: list[str] | None,
    current_page: int,
    query_params: dict[str, list[str]],
) -> dict[str, list[str]]:
    merged = {k: list(v) for k, v in params.items()}

    if data_provider:
        merged["data_provider"] = [data_provider.strip()]
    if sics_sector:
        merged["sics_sector"] = [sics_sector.strip()]
    if jurisdiction:
        merged["jurisdiction"] = [jurisdiction.strip()]
    if reporting_year:
        merged["reporting_year"] = [reporting_year.strip()]
    if metric:
        metric_values: list[str] = []
        for item in metric:
            metric_values.extend([m.strip() for m in item.split(",") if m.strip()])
        if metric_values:
            merged["metric"] = [",".join(metric_values)]

    merged["currentPage"] = [str(current_page)]

    for key, values in query_params.items():
        merged[key] = values
    return merged


def build_target_url(args: argparse.Namespace) -> str:
    base, params = split_url_params(args.data_explorer_url)
    extra_query = parse_query_params(args.query_param)
    merged = apply_filter_overrides(
        params,
        data_provider=args.data_provider,
        sics_sector=args.sics_sector,
        jurisdiction=args.jurisdiction,
        reporting_year=args.reporting_year,
        metric=args.metric,
        current_page=args.current_page,
        query_params=extra_query,
    )
    return build_url(base, merged)


def norm_null(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return None if text in NULL_TOKENS else text


def build_driver(
    *,
    headless: bool,
    window_size: str,
    user_data_dir: Path | None,
    page_load_timeout: int,
) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument(f"--window-size={window_size}")

    if user_data_dir:
        user_data_dir.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={user_data_dir}")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(page_load_timeout)
    return driver


def wait_overlays_gone(driver, timeout=10) -> None:
    end = time.time() + timeout
    while time.time() < end:
        blockers = driver.find_elements(
            By.CSS_SELECTOR,
            ".MuiBackdrop-root, .MuiPopover-root, .MuiMenu-root, .MuiModal-root",
        )
        visible = [b for b in blockers if b.is_displayed()]
        if not visible:
            return
        time.sleep(0.1)


def safe_click(driver, element) -> None:
    try:
        element.click()
        return
    except ElementClickInterceptedException:
        pass

    try:
        ActionChains(driver).move_to_element(element).pause(0.05).click(element).perform()
        return
    except ElementClickInterceptedException:
        pass

    driver.execute_script("arguments[0].click();", element)


def dismiss_cookie(driver, timeout=5) -> None:
    candidates = [
        "//button[contains(., 'Accept')]",
        "//button[contains(., 'I agree')]",
        "//button[contains(., 'Allow')]",
        "//button[contains(., 'OK')]",
        "//button[contains(., '동의')]",
        "//button[contains(., '허용')]",
        "//button[contains(., '확인')]",
    ]
    end = time.time() + timeout
    while time.time() < end:
        for xpath in candidates:
            for element in driver.find_elements(By.XPATH, xpath):
                if element.is_displayed():
                    try:
                        safe_click(driver, element)
                        wait_overlays_gone(driver, 5)
                        return
                    except Exception:
                        pass
        time.sleep(0.2)


def get_data_table(driver):
    tables = driver.find_elements(By.CSS_SELECTOR, TABLE_SELECTOR)
    for table in tables:
        if (table.get_attribute("aria-hidden") or "").lower() == "true":
            continue
        if table.find_elements(By.CSS_SELECTOR, "tbody tr"):
            return table

    row = driver.find_element(By.CSS_SELECTOR, TABLE_ROW_SELECTOR)
    return row.find_element(By.XPATH, "ancestor::table[1]")


def wait_table_rows(driver, timeout=30) -> None:
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, TABLE_ROW_SELECTOR))
    )


def has_no_results_message(driver) -> bool:
    return len(driver.find_elements(By.XPATH, NO_RESULTS_XPATH)) > 0


def wait_page_data_ready(driver, timeout=30) -> None:
    wait_table_rows(driver, timeout=timeout)
    WebDriverWait(driver, timeout).until(
        lambda d: (
            len(get_data_table(d).find_elements(By.CSS_SELECTOR, COMPANY_LINK_SELECTOR)) >= 1
            or has_no_results_message(d)
        )
    )


def read_current_page_rows_dom(driver) -> list[dict[str, Any]]:
    wait_table_rows(driver)
    table = get_data_table(driver)
    rows = table.find_elements(By.CSS_SELECTOR, "tbody tr")

    out: list[dict[str, Any]] = []
    for row in rows:
        cells = row.find_elements(By.CSS_SELECTOR, "td[data-attr-name]")
        if not cells:
            continue

        obj: dict[str, Any] = {}
        for cell in cells:
            key = cell.get_attribute("data-attr-name")
            value_attr = (cell.get_attribute("data-attr-value") or "").strip()
            value_text = (cell.text or "").strip()
            value = value_attr if value_attr not in NULL_TOKENS else value_text
            obj[key] = norm_null(value)

        links = row.find_elements(By.CSS_SELECTOR, 'td[data-attr-name="company_name"] a')
        if not links:
            continue

        link = links[0]
        company_name = (link.text or "").strip()
        if company_name:
            obj["company_name"] = company_name

        href = (link.get_attribute("href") or "").strip()
        if href:
            obj["company_url"] = urljoin(driver.current_url, href)

        if not obj.get("company_name") and not obj.get("company_url"):
            continue

        out.append(obj)
    return out


def has_next_page(driver) -> bool:
    buttons = driver.find_elements(By.CSS_SELECTOR, NEXT_PAGE_BUTTON_SELECTOR)
    if not buttons:
        return False
    btn = buttons[0]
    cls = btn.get_attribute("class") or ""
    disabled_attr = btn.get_attribute("disabled")
    return (disabled_attr is None) and ("Mui-disabled" not in cls)


def get_current_page_number(driver) -> int:
    buttons = driver.find_elements(By.CSS_SELECTOR, 'button[aria-current="page"]')
    if not buttons:
        return -1
    text = (buttons[0].text or "").strip()
    return int(text) if text.isdigit() else -1


def first_company_href(driver) -> str | None:
    table = get_data_table(driver)
    links = table.find_elements(By.CSS_SELECTOR, COMPANY_LINK_SELECTOR)
    if not links:
        return None
    href = links[0].get_attribute("href")
    return href or None


def go_next_page(driver, timeout=30) -> None:
    before_page = get_current_page_number(driver)
    before_href = first_company_href(driver)

    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
    wait_overlays_gone(driver, 10)

    btn = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, NEXT_PAGE_BUTTON_SELECTOR))
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    driver.execute_script("window.scrollBy(0, -120);")
    time.sleep(0.1)
    safe_click(driver, btn)

    def _page_moved(d) -> bool:
        now_page = get_current_page_number(d)
        now_href = first_company_href(d)

        page_changed = before_page >= 0 and now_page >= 0 and now_page != before_page
        href_changed = before_href is not None and now_href is not None and now_href != before_href
        return page_changed or href_changed

    WebDriverWait(driver, timeout).until(_page_moved)
    wait_table_rows(driver, timeout=timeout)


def build_output_file(args: argparse.Namespace, repo_root: Path) -> Path:
    if args.output_file:
        output_file = args.output_file
    else:
        run_date = args.run_date or datetime.now().strftime("%Y-%m-%d")
        output_dir = args.output_dir or (repo_root / "storage" / "raw" / SOURCE_NAME / run_date)
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        output_file = output_dir / f"companies_{timestamp}.csv"

    output_file.parent.mkdir(parents=True, exist_ok=True)
    return output_file


def parse_args(repo_root: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="NZDPU data-explorer company list extractor.",
    )
    parser.add_argument(
        "--data-explorer-url",
        default=DEFAULT_DATA_EXPLORER_URL,
        help="Base/full data-explorer URL. Query가 포함되어도 됨.",
    )
    parser.add_argument("--data-provider", help="e.g. CDP")
    parser.add_argument("--sics-sector", help="e.g. Consumer Goods,Food & Beverage")
    parser.add_argument("--jurisdiction", default=None, help="e.g. Japan")
    parser.add_argument("--metric", action="append", help="metric list(csv). 반복 사용 가능.")
    parser.add_argument("--reporting-year", help="e.g. 2023 or 2022,2023")
    parser.add_argument("--current-page", type=int, default=1)
    parser.add_argument(
        "--query-param",
        action="append",
        default=[],
        help="Extra query param, format KEY=VALUE. 반복 사용 가능.",
    )

    parser.add_argument("--max-pages", type=int, default=200)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--sleep-sec", type=float, default=0.0)

    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--window-size", default="1400,900")
    parser.add_argument("--page-load-timeout", type=int, default=60)
    parser.add_argument(
        "--user-data-dir",
        type=Path,
        default=Path("storage") / "raw" / SOURCE_NAME / ".chrome-profile",
    )

    parser.add_argument("--run-date", help="Output partition date (YYYY-MM-DD).")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--output-file", type=Path)

    args = parser.parse_args()

    if args.current_page < 1:
        parser.error("--current-page must be >= 1")
    if args.max_pages < 1:
        parser.error("--max-pages must be >= 1")
    if args.timeout < 1:
        parser.error("--timeout must be >= 1")
    if args.page_load_timeout < 1:
        parser.error("--page-load-timeout must be >= 1")
    if args.sleep_sec < 0:
        parser.error("--sleep-sec must be >= 0")
    if args.run_date:
        try:
            datetime.strptime(args.run_date, "%Y-%m-%d")
        except ValueError as exc:
            parser.error(f"--run-date must be YYYY-MM-DD: {exc}")

    if args.user_data_dir:
        args.user_data_dir = resolve_path(args.user_data_dir, repo_root)
    if args.output_dir:
        args.output_dir = resolve_path(args.output_dir, repo_root)
    if args.output_file:
        args.output_file = resolve_path(args.output_file, repo_root)

    return args


def collect_rows(driver, target_url: str, *, max_pages: int, timeout: int, sleep_sec: float) -> list[dict[str, Any]]:
    driver.get(target_url)
    dismiss_cookie(driver)
    wait_overlays_gone(driver, 5)
    wait_table_rows(driver, timeout=max(timeout, 60))

    all_rows: list[dict[str, Any]] = []
    seen = set()

    for _ in range(max_pages):
        page_no = get_current_page_number(driver)
        wait_page_data_ready(driver, timeout=timeout)
        rows = read_current_page_rows_dom(driver)

        for row in rows:
            key = row.get("company_url") or (
                row.get("company_name"),
                row.get("reporting_year"),
                row.get("data_provider"),
            )
            if key in seen:
                continue
            seen.add(key)
            all_rows.append(row)

        print(f"page={page_no} rows(page)={len(rows)} rows(total)={len(all_rows)}")
        if not has_next_page(driver):
            break

        go_next_page(driver, timeout=timeout)
        if sleep_sec > 0:
            time.sleep(sleep_sec)

    return all_rows


def run(args: argparse.Namespace, output_file: Path) -> None:
    target_url = build_target_url(args)
    print("target_url:", target_url)

    driver = build_driver(
        headless=args.headless,
        window_size=args.window_size,
        user_data_dir=args.user_data_dir,
        page_load_timeout=args.page_load_timeout,
    )
    try:
        rows = collect_rows(
            driver,
            target_url,
            max_pages=args.max_pages,
            timeout=args.timeout,
            sleep_sec=args.sleep_sec,
        )
    finally:
        driver.quit()

    df = pd.DataFrame(rows)
    df.to_csv(output_file, index=False, encoding="utf-8-sig")
    print(f"Saved: {output_file} rows: {len(df)}")


def main() -> None:
    repo_root = find_repo_root()
    args = parse_args(repo_root)
    output_file = build_output_file(args, repo_root)
    run(args, output_file)


if __name__ == "__main__":
    main()
