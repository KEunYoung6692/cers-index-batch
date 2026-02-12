"""
GIR-KOR (온실가스종합정보센터) 테이블 수집기.
"""

import argparse
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import pandas as pd
from bs4 import BeautifulSoup

DEFAULT_URL = "https://www.gir.go.kr/home/index.do?menuId=37"
SOURCE_NAME = Path(__file__).resolve().parent.name

COLUMNS = [
    "no",
    "agency",
    "corp_name",
    "year",
    "designation_type",
    "industry",
    "ghg_tco2eq",
    "energy_tj",
    "verifier",
    "remark",
]

DNS_ERROR_MARKERS = [
    "DNS address could not be found",
    "This site can’t be reached",
    "ERR_NAME_NOT_RESOLVED",
]

# lazy-loaded selenium symbols
webdriver = None
Options = None
By = None
EC = None
Select = None
WebDriverWait = None
TimeoutException = Exception
WebDriverException = Exception


def ensure_selenium() -> None:
    global webdriver, Options, By, EC, Select, WebDriverWait, TimeoutException, WebDriverException
    if webdriver is not None:
        return

    try:
        from selenium import webdriver as _webdriver
        from selenium.common.exceptions import TimeoutException as _TimeoutException
        from selenium.common.exceptions import WebDriverException as _WebDriverException
        from selenium.webdriver.chrome.options import Options as _Options
        from selenium.webdriver.common.by import By as _By
        from selenium.webdriver.support import expected_conditions as _EC
        from selenium.webdriver.support.ui import Select as _Select
        from selenium.webdriver.support.ui import WebDriverWait as _WebDriverWait
    except ModuleNotFoundError as exc:
        raise RuntimeError("selenium is required. Install with: pip install selenium") from exc

    webdriver = _webdriver
    Options = _Options
    By = _By
    EC = _EC
    Select = _Select
    WebDriverWait = _WebDriverWait
    TimeoutException = _TimeoutException
    WebDriverException = _WebDriverException


def find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "README.md").exists() and (parent / "src").exists():
            return parent
    return Path.cwd()


def resolve_path(path: Path, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def to_int(value: str) -> int | None:
    text = (value or "").replace(",", "").strip()
    return int(text) if text.isdigit() else None


def page_has_dns_error(driver) -> bool:
    try:
        title = driver.title or ""
        html = driver.page_source or ""
        blob = f"{title}\n{html}"
        return any(marker in blob for marker in DNS_ERROR_MARKERS)
    except Exception:
        return False


def safe_get(
    driver,
    wait,
    url: str,
    *,
    retries: int = 5,
    base_sleep: float = 1.0,
    load_timeout: int = 30,
) -> None:
    last_error: Exception | None = None
    for i in range(retries):
        try:
            driver.set_page_load_timeout(load_timeout)
            driver.get(url)

            if page_has_dns_error(driver):
                raise WebDriverException("DNS/NAME_NOT_RESOLVED page detected")

            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody")))
            return
        except (TimeoutException, WebDriverException) as exc:
            last_error = exc
            time.sleep(base_sleep * (2**i))
    raise RuntimeError(f"safe_get failed after {retries} retries: {last_error}")


def parse_table(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if not table:
        return []

    tbody = table.find("tbody")
    if not tbody:
        return []

    rows: list[dict[str, Any]] = []
    for tr in tbody.find_all("tr"):
        tds = [td.get_text(strip=True).replace("\xa0", " ") for td in tr.find_all("td")]
        if len(tds) < 10:
            continue

        rows.append(
            {
                "no": to_int(tds[0]),
                "agency": tds[1],
                "corp_name": tds[2].strip(),
                "year": to_int(tds[3]),
                "designation_type": tds[4],
                "industry": tds[5],
                "ghg_tco2eq": to_int(tds[6]),
                "energy_tj": to_int(tds[7]),
                "verifier": tds[8],
                "remark": tds[9],
            }
        )
    return rows


def get_last_offset(driver) -> int | None:
    try:
        last_link = driver.find_element(By.CSS_SELECTOR, "div.pagination a.last")
        href = last_link.get_attribute("href")
        if not href:
            return None
        qs = parse_qs(urlparse(href).query)
        if "pagerOffset" not in qs:
            return None
        return int(qs["pagerOffset"][0])
    except Exception:
        return None


def build_url_with_params(start_url: str, params: dict[str, str]) -> str:
    parsed = urlparse(start_url)
    qs = parse_qs(parsed.query)
    for key, value in params.items():
        qs[key] = [str(value)]
    new_query = urlencode(qs, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def wait_table_loaded(wait: WebDriverWait, *, require_row: bool = False) -> None:
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody")))
    if require_row:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr")))


def select_year(
    driver,
    wait,
    target_year: int,
    *,
    retries: int,
    retry_base_sleep: float,
    load_timeout: int,
) -> None:
    old_first_row = ""
    try:
        old_first_row = driver.find_element(By.CSS_SELECTOR, "table tbody tr").text.strip()
    except Exception:
        pass

    year_select = Select(wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "select#year"))))
    available_values = {opt.get_attribute("value") for opt in year_select.options}
    if str(target_year) not in available_values:
        raise ValueError(f"year not available in select#year: {target_year}")
    year_select.select_by_value(str(target_year))

    forced_url = build_url_with_params(
        driver.current_url,
        {"condition.year": str(target_year), "pagerOffset": "0"},
    )
    safe_get(
        driver,
        wait,
        forced_url,
        retries=retries,
        base_sleep=retry_base_sleep,
        load_timeout=load_timeout,
    )
    wait_table_loaded(wait, require_row=False)

    try:
        wait.until(lambda d: d.find_element(By.CSS_SELECTOR, "table tbody tr").text.strip() != old_first_row)
    except Exception:
        pass


def build_driver(*, headless: bool, window_size: str, page_load_timeout: int):
    ensure_selenium()
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument(f"--window-size={window_size}")

    # 네트워크 관련 불필요 기능 완화
    options.add_argument("--disable-features=NetworkService")
    options.add_argument("--dns-prefetch-disable")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-default-apps")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-sync")
    options.add_argument("--metrics-recording-only")
    options.add_argument("--no-first-run")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(page_load_timeout)
    return driver


def scrape_with_selenium(
    *,
    start_url: str,
    target_year: int | None,
    sleep_sec: float,
    timeout: int,
    retries: int,
    retry_base_sleep: float,
    page_load_timeout: int,
    page_step: int,
    max_pages: int,
    headless: bool,
    window_size: str,
) -> pd.DataFrame:
    ensure_selenium()
    driver = build_driver(headless=headless, window_size=window_size, page_load_timeout=page_load_timeout)
    wait = WebDriverWait(driver, timeout)
    all_rows: list[dict[str, Any]] = []

    try:
        safe_get(
            driver,
            wait,
            start_url,
            retries=retries,
            base_sleep=retry_base_sleep,
            load_timeout=page_load_timeout,
        )
        wait_table_loaded(wait, require_row=False)

        if target_year is not None:
            select_year(
                driver,
                wait,
                target_year,
                retries=retries,
                retry_base_sleep=retry_base_sleep,
                load_timeout=page_load_timeout,
            )

        first_rows = parse_table(driver.page_source)
        all_rows.extend(first_rows)
        print(f"page=1 rows={len(first_rows)} total={len(all_rows)}")

        last_offset = get_last_offset(driver)
        if last_offset is None:
            # 페이지 끝을 모르면 max_pages까지만 탐색
            last_offset = page_step * max_pages

        base_url = driver.current_url
        pages_scraped = 1
        for offset in range(page_step, last_offset + page_step, page_step):
            if pages_scraped >= max_pages:
                break

            page_url = build_url_with_params(base_url, {"pagerOffset": str(offset)})
            safe_get(
                driver,
                wait,
                page_url,
                retries=retries,
                base_sleep=retry_base_sleep,
                load_timeout=page_load_timeout,
            )
            wait_table_loaded(wait, require_row=False)

            rows = parse_table(driver.page_source)
            if not rows:
                break

            all_rows.extend(rows)
            pages_scraped += 1
            print(f"page={pages_scraped} rows={len(rows)} total={len(all_rows)}")
            time.sleep(sleep_sec)
    finally:
        driver.quit()

    df = pd.DataFrame(all_rows, columns=COLUMNS).drop_duplicates()
    return df


def parse_args(repo_root: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GIR-KOR emissions table extractor.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--year", type=int, help="Target year filter (optional).")
    parser.add_argument("--max-pages", type=int, default=200)
    parser.add_argument("--page-step", type=int, default=10)
    parser.add_argument("--sleep-sec", type=float, default=0.2)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--retry-base-sleep", type=float, default=1.0)
    parser.add_argument("--page-load-timeout", type=int, default=30)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--window-size", default="1920,1080")

    parser.add_argument("--run-date", help="Output partition date (YYYY-MM-DD).")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--output-file", type=Path)
    args = parser.parse_args()

    if args.max_pages < 1:
        parser.error("--max-pages must be >= 1")
    if args.page_step < 1:
        parser.error("--page-step must be >= 1")
    if args.sleep_sec < 0:
        parser.error("--sleep-sec must be >= 0")
    if args.timeout < 1:
        parser.error("--timeout must be >= 1")
    if args.retries < 1:
        parser.error("--retries must be >= 1")
    if args.retry_base_sleep < 0:
        parser.error("--retry-base-sleep must be >= 0")
    if args.page_load_timeout < 1:
        parser.error("--page-load-timeout must be >= 1")
    if args.run_date:
        try:
            datetime.strptime(args.run_date, "%Y-%m-%d")
        except ValueError as exc:
            parser.error(f"--run-date must be YYYY-MM-DD: {exc}")

    if args.output_dir:
        args.output_dir = resolve_path(args.output_dir, repo_root)
    if args.output_file:
        args.output_file = resolve_path(args.output_file, repo_root)
    return args


def resolve_output_file(args: argparse.Namespace, repo_root: Path) -> Path:
    if args.output_file:
        output_file = args.output_file
    else:
        run_date = args.run_date or datetime.now().strftime("%Y-%m-%d")
        output_dir = args.output_dir or (repo_root / "storage" / "raw" / SOURCE_NAME / run_date)
        suffix = f"_{args.year}" if args.year else ""
        output_file = output_dir / f"emissions{suffix}.csv"

    output_file.parent.mkdir(parents=True, exist_ok=True)
    return output_file


def run(args: argparse.Namespace, output_file: Path) -> None:
    df = scrape_with_selenium(
        start_url=args.url,
        target_year=args.year,
        sleep_sec=args.sleep_sec,
        timeout=args.timeout,
        retries=args.retries,
        retry_base_sleep=args.retry_base_sleep,
        page_load_timeout=args.page_load_timeout,
        page_step=args.page_step,
        max_pages=args.max_pages,
        headless=args.headless,
        window_size=args.window_size,
    )
    df.to_csv(output_file, index=False, encoding="utf-8-sig")
    print(f"saved: {output_file} rows={len(df)}")


def main() -> None:
    repo_root = find_repo_root()
    args = parse_args(repo_root)
    output_file = resolve_output_file(args, repo_root)
    run(args, output_file)


if __name__ == "__main__":
    main()
