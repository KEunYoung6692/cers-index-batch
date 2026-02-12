import argparse
import csv
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import pandas as pd

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, StaleElementReferenceException
from selenium.webdriver.chrome.options import Options

BASE_ORIGIN = "https://nzdpu.com"
DEFAULT_LIST_URL = f"{BASE_ORIGIN}/companies"
SOURCE_NAME = Path(__file__).resolve().parent.name
COMPANY_VIEW_LINK_SELECTOR = ".MuiDataGrid-row div[data-field='view'] a[href*='/companies/']"
NEXT_PAGE_BUTTON_SELECTOR = "button[aria-label='Next page']"
TABLE_ROW_SELECTOR = "table.MuiTable-root tbody tr"

# NZDPU null 표시: "—" 가 핵심 (스크린샷)
NULL_TOKENS = {"—", "–", "-", "--", ""}


def find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "README.md").exists() and (parent / "src").exists():
            return parent
    return Path.cwd()


def resolve_path(path: Path, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def set_query(url: str, **updates) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key, value in updates.items():
        if value is None:
            query.pop(key, None)
        else:
            query[key] = str(value)

    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        urlencode(query, doseq=True),
        parts.fragment,
    ))


def build_companies_list_url(base_url: str, jurisdiction: str | None) -> str:
    normalized = jurisdiction.strip() if jurisdiction else None
    if not normalized:
        normalized = None
    return set_query(base_url, jurisdiction=normalized)


def _load_values_from_file(path: Path, preferred_columns: tuple[str, ...]) -> list[str]:
    path = path.expanduser()
    if not path.exists():
        raise FileNotFoundError(f"input file not found: {path}")

    values: list[str] = []
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            sample = f.read(2048)
            f.seek(0)
            if sample.strip():
                try:
                    has_header = csv.Sniffer().has_header(sample)
                except csv.Error:
                    has_header = False
            else:
                has_header = False
            if has_header:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                selected_col = next((c for c in preferred_columns if c in fieldnames), None)
                if not selected_col and fieldnames:
                    selected_col = fieldnames[0]

                for row in reader:
                    raw = (row.get(selected_col, "") if selected_col else "").strip()
                    if raw:
                        values.append(raw)
            else:
                reader = csv.reader(f)
                for row in reader:
                    if row and row[0].strip():
                        values.append(row[0].strip())
    else:
        with path.open("r", encoding="utf-8-sig") as f:
            for line in f:
                raw = line.strip()
                if raw:
                    values.append(raw)

    # 순서 유지 중복 제거
    deduped: list[str] = []
    seen = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def load_company_urls(path: Path) -> list[str]:
    return _load_values_from_file(path, ("company_url", "url", "href"))


def load_company_names(path: Path) -> list[str]:
    return _load_values_from_file(path, ("company_name", "name", "company"))


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

def norm_null(s: str | None) -> str | None:
    if s is None:
        return None
    t = s.strip()
    return None if t in NULL_TOKENS else t

def safe_click(driver, el) -> None:
    try:
        el.click()
    except (ElementClickInterceptedException, Exception):
        driver.execute_script("arguments[0].click();", el)

def wait_overlays_gone(driver, timeout=10) -> None:
    end = time.time() + timeout
    while time.time() < end:
        backdrops = driver.find_elements(By.CSS_SELECTOR, ".MuiBackdrop-root, .MuiDialog-root, .MuiModal-root")
        visible = [b for b in backdrops if b.is_displayed()]
        if not visible:
            return
        time.sleep(0.15)

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
        for xp in candidates:
            for el in driver.find_elements(By.XPATH, xp):
                if el.is_displayed():
                    try:
                        safe_click(driver, el)
                        wait_overlays_gone(driver, 5)
                        return
                    except Exception:
                        pass
        time.sleep(0.2)

def dismiss_null_modal(driver, timeout=2) -> bool:
    """
    스크린샷의 'How Does NZDPU Represent Null / Missing Values?' 모달 포함
    - 우측 X 또는 하단 CLOSE 버튼 클릭
    - 새로고침 금지(시간만 버림)
    """
    end = time.time() + timeout
    while time.time() < end:
        # 모달이 떠있는지(제목 텍스트로) 감지
        headers = driver.find_elements(
            By.XPATH,
            "//*[contains(., 'Represent Null') or contains(., 'NULL VALUES') or contains(., 'Missing Values')]"
        )
        dialog = None
        for h in headers:
            try:
                # 근처에 dialog/root가 있을 확률이 높음
                dialog = h.find_element(By.XPATH, "ancestor::*[contains(@class,'MuiDialog-root') or contains(@class,'MuiModal-root')][1]")
                break
            except Exception:
                continue

        if dialog and dialog.is_displayed():
            # 1) CLOSE 버튼
            for xp in [
                ".//button[normalize-space()='CLOSE']",
                ".//button[contains(., 'CLOSE')]",
                ".//button[contains(., 'Close')]",
                ".//button[@aria-label='Close']",
                ".//*[name()='svg' and @data-testid='CloseIcon']/ancestor::button[1]",
            ]:
                try:
                    btns = dialog.find_elements(By.XPATH, xp)
                    for b in btns:
                        if b.is_displayed():
                            safe_click(driver, b)
                            wait_overlays_gone(driver, 5)
                            return True
                except Exception:
                    pass

        time.sleep(0.15)
    return False

def dismiss_all_popups(driver) -> None:
    dismiss_cookie(driver)
    dismiss_null_modal(driver)
    wait_overlays_gone(driver, 5)

# ---------------------------
# 리스트(Companies)에서 View URL 수집
# ---------------------------
def wait_companies_list_ready(driver, timeout=30) -> None:
    # 그리드 뜨기
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".MuiDataGrid-root"))
    )
    # ✅ View 링크가 최소 1개 뜰 때까지 (이게 핵심)
    WebDriverWait(driver, timeout).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, COMPANY_VIEW_LINK_SELECTOR)) > 0
    )

def get_view_links_on_current_page(driver) -> list[str]:
    links = driver.find_elements(
        By.CSS_SELECTOR,
        COMPANY_VIEW_LINK_SELECTOR,
    )

    urls, seen = [], set()
    for a in links:
        href = a.get_attribute("href") or ""
        if href.startswith("/"):
            href = urljoin(BASE_ORIGIN, href)

        # ✅ yama 같은 search_query 찌꺼기 제거
        href = set_query(href, search_query=None)

        if href and href not in seen:
            seen.add(href)
            urls.append(href)
    return urls

def norm_name(s: str | None) -> str:
    if not s:
        return ""
    # 공백/nbsp 정리 + 대문자화(영문만 영향)
    s = s.replace("\u00a0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s.upper()

def extract_name_and_view_urls_on_current_page(
    driver,
    target_norm_set: set[str] | None = None,
) -> list[tuple[str | None, str]]:
    """
    현재 페이지(.MuiDataGrid-row)에서 회사명 + view url을 뽑고,
    target_norm_set 이 주어지면 그 목록에 있는 회사만 반환
    """
    rows = driver.find_elements(By.CSS_SELECTOR, ".MuiDataGrid-row")
    results = []

    for row in rows:
        # 1) View URL
        try:
            view_a = row.find_element(By.CSS_SELECTOR, "div[data-field='view'] a[href*='/companies/']")
        except Exception:
            continue

        href = view_a.get_attribute("href") or ""
        if not href:
            continue
        if href.startswith("/"):
            href = urljoin(BASE_ORIGIN, href)

        # yama 같은 query 찌꺼기 제거
        href = set_query(href, search_query=None)

        # 2) 회사명 (row 안에서 View 말고 실제 회사명 텍스트 찾기)
        name = None

        # (가) row 안의 /companies/ 링크 중 "View" 아닌 텍스트 우선
        anchors = row.find_elements(By.CSS_SELECTOR, "a[href*='/companies/']")
        for a in anchors:
            txt = (a.text or "").strip()
            if txt and txt.lower() != "view":
                name = txt
                break

        # (나) 그래도 없으면, view/actions/id 제외한 첫 gridcell 텍스트
        if not name:
            cells = row.find_elements(By.CSS_SELECTOR, "div[role='gridcell']")
            for c in cells:
                field = (c.get_attribute("data-field") or "").lower()
                if field in ("view", "actions", "id"):
                    continue
                txt = (c.text or "").strip()
                if txt:
                    name = txt
                    break

        n = norm_name(name)

        if target_norm_set is None:
            results.append((name, href))
        else:
            if n and n in target_norm_set:
                results.append((name, href))

    return results

def click_next_page_if_possible(driver) -> bool:
    next_btns = driver.find_elements(By.CSS_SELECTOR, NEXT_PAGE_BUTTON_SELECTOR)
    if not next_btns:
        return False

    btn = next_btns[0]
    cls = btn.get_attribute("class") or ""
    if (not btn.is_enabled()) or ("Mui-disabled" in cls):
        return False

    # ✅ 페이지가 바뀌었는지 판정할 기준: 첫 View 링크 href
    old_links = driver.find_elements(
        By.CSS_SELECTOR,
        COMPANY_VIEW_LINK_SELECTOR,
    )
    old_first = (old_links[0].get_attribute("href") if old_links else None)

    safe_click(driver, btn)

    # ✅ 첫 링크 href가 바뀔 때까지 기다림 (row만 기다리면 또 0 뜸)
    WebDriverWait(driver, 30).until(
        lambda d: (
            len(d.find_elements(By.CSS_SELECTOR, COMPANY_VIEW_LINK_SELECTOR)) > 0
            and (old_first is None or d.find_elements(By.CSS_SELECTOR, COMPANY_VIEW_LINK_SELECTOR)[0].get_attribute("href") != old_first)
        )
    )
    return True


def collect_all_company_urls_from_list(
    driver,
    list_url: str,
    timeout=30,
    max_pages=200,
) -> list[str]:
    driver.get(list_url)
    dismiss_cookie(driver)
    wait_overlays_gone(driver, 5)
    wait_companies_list_ready(driver, timeout=timeout)

    all_urls: list[str] = []
    seen = set()

    for _ in range(max_pages):
        urls = get_view_links_on_current_page(driver)
        for url in urls:
            if url not in seen:
                seen.add(url)
                all_urls.append(url)

        if not click_next_page_if_possible(driver):
            break

    return all_urls


def collect_company_urls_from_list_filtered(
    driver,
    list_url: str,
    company_name_list: list[str],
    timeout=30,
    max_pages=200,
) -> tuple[list[str], list[str]]:
    driver.get(list_url)
    dismiss_cookie(driver)
    wait_overlays_gone(driver, 5)
    wait_companies_list_ready(driver, timeout=timeout)

    # 타겟 이름 세트
    target_norms = {norm_name(x) for x in company_name_list if str(x).strip()}
    found_map = {}  # norm_name -> (orig_name, url)

    for _ in range(max_pages):
        pairs = extract_name_and_view_urls_on_current_page(driver, target_norm_set=target_norms)

        for name, url in pairs:
            key = norm_name(name)
            if key and key not in found_map:
                found_map[key] = (name, url)

        # ✅ 다 찾았으면 페이지네이션 더 안 함 (속도 핵심)
        if len(found_map) >= len(target_norms):
            break

        if not click_next_page_if_possible(driver):
            break

    # company_name_list 순서대로 URL 정렬해서 반환 (못 찾은 건 None)
    ordered_urls = []
    missing = []
    for nm in company_name_list:
        k = norm_name(nm)
        if k in found_map:
            ordered_urls.append(found_map[k][1])
        else:
            missing.append(nm)

    return ordered_urls, missing



# ---------------------------
# 탭 클릭 유틸
# ---------------------------

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).upper()

def find_tablist_by_required_labels(driver, required_labels, timeout=15):
    req = [_norm(x) for x in required_labels]

    def _match(d):
        tablists = d.find_elements(By.CSS_SELECTOR, "[role='tablist']")
        for tl in tablists:
            try:
                if not tl.is_displayed():
                    continue
                tabs = tl.find_elements(By.CSS_SELECTOR, "[role='tab']")
                texts = [_norm(t.text) for t in tabs if t.is_displayed()]
                joined = " | ".join(texts)
                if all(r in joined for r in req):
                    return tl
            except StaleElementReferenceException:
                continue
        return False

    return WebDriverWait(driver, timeout).until(_match)

def click_tab_by_labels(driver, required_labels, tab_text, timeout=20):
    """
    required_labels로 tablist를 매번 다시 찾고, tab_text 탭을 클릭.
    StaleElementReferenceException 자동 재시도.
    """
    dismiss_all_popups(driver)
    target = _norm(tab_text)
    end = time.time() + timeout
    last_err = None

    while time.time() < end:
        try:
            tablist = find_tablist_by_required_labels(driver, required_labels, timeout=5)

            tabs = tablist.find_elements(By.CSS_SELECTOR, "[role='tab']")
            tab = None
            for t in tabs:
                if t.is_displayed() and target in _norm(t.text):
                    tab = t
                    break
            if tab is None:
                time.sleep(0.2)
                continue

            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tab)
            try:
                driver.switch_to.active_element.send_keys(Keys.ESCAPE)
            except Exception:
                pass

            safe_click(driver, tab)

            # aria-selected 확인도 "재탐색"으로 (stale 방지)
            def _selected(d):
                try:
                    tl2 = find_tablist_by_required_labels(d, required_labels, timeout=5)
                    tabs2 = tl2.find_elements(By.CSS_SELECTOR, "[role='tab']")
                    for t2 in tabs2:
                        if t2.is_displayed() and target in _norm(t2.text):
                            return (t2.get_attribute("aria-selected") or "").lower() == "true"
                    return False
                except Exception:
                    return False

            WebDriverWait(driver, 10).until(_selected)

            dismiss_all_popups(driver)
            wait_overlays_gone(driver, 5)
            return

        except StaleElementReferenceException as e:
            last_err = e
            time.sleep(0.2)
        except Exception as e:
            last_err = e
            time.sleep(0.2)

    if last_err is not None:
        raise last_err
    raise TimeoutException(f"failed to click tab '{tab_text}' within {timeout}s")



# ---------------------------
# 테이블 파싱(네 로직 유지 + 빈 테이블 처리)
# ---------------------------
def wait_any_table_or_empty(driver, timeout=30) -> None:
    # 테이블 row가 나오거나, "검색된 기록이 없습니다" 문구가 뜨거나 둘 중 하나
    WebDriverWait(driver, timeout).until(
        lambda d: (
            len(d.find_elements(By.CSS_SELECTOR, TABLE_ROW_SELECTOR)) > 0
            or len(d.find_elements(By.XPATH, "//*[contains(., '검색된 기록이 없습니다')]")) > 0
        )
    )

def pick_real_table(driver):
    tables = driver.find_elements(By.CSS_SELECTOR, "table.MuiTable-root")
    candidates = []
    for t in tables:
        try:
            tbody = t.find_element(By.CSS_SELECTOR, "tbody")
            trs = tbody.find_elements(By.CSS_SELECTOR, "tr")
            if not trs:
                continue

            joined = " ".join([tr.text for tr in trs]).strip()
            # '검색된 기록이 없습니다.' 테이블은 제외
            if "검색된 기록이 없습니다" in joined:
                continue

            score = 0
            if tbody.find_elements(By.CSS_SELECTOR, "tr[data-index]"):
                score += 2
            if tbody.find_elements(By.CSS_SELECTOR, "tr[id^='row-details-']"):
                score += 2
            if tbody.find_elements(By.CSS_SELECTOR, "[data-attr-name][data-attr-value]"):
                score += 1

            candidates.append((score, t))
        except Exception:
            continue

    if not candidates:
        # fallback: 첫 테이블(있으면)
        if tables:
            return tables[0]
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]

def parse_table(table) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    current_group = None

    trs = table.find_elements(By.CSS_SELECTOR, "tbody tr")
    for tr in trs:
        row_id = tr.get_attribute("id") or None
        tds = tr.find_elements(By.CSS_SELECTOR, "td")
        if not tds:
            continue

        field_name = norm_null(tds[0].text)

        # group row 판단
        is_group = False
        if row_id and row_id.endswith("_group"):
            is_group = True
        elif len(tds) >= 2:
            vtxt = norm_null(tds[1].text)
            stxt = norm_null(tds[2].text) if len(tds) > 2 else None
            utxt = norm_null(tds[3].text) if len(tds) > 3 else None
            if field_name and (vtxt is None and stxt is None and utxt is None):
                data_index = tr.get_attribute("data-index")
                if data_index is not None and data_index == "0" and row_id is None:
                    is_group = False
                else:
                    is_group = True

        if is_group:
            current_group = field_name
            out.append({
                "group": current_group,
                "field_name": field_name,
                "data_key": None,
                "value": None,
                "source": None,
                "last_updated": None,
                "restatement": None,
                "row_id": row_id,
                "row_type": "group"
            })
            continue

        data_key = None
        value = None
        if len(tds) >= 2:
            value_td = tds[1]
            candidates = value_td.find_elements(By.CSS_SELECTOR, "[data-attr-name]")
            for el in candidates:
                k = (el.get_attribute("data-attr-name") or "").strip()
                v = (el.get_attribute("data-attr-value") or "").strip()
                if not k:
                    continue
                if "unit" in k.lower() or k.lower().endswith("_units"):
                    continue
                if v:
                    data_key = k
                    value = v
                    break
            if value is None:
                value = norm_null(value_td.text)

        source = norm_null(tds[2].text) if len(tds) > 2 else None
        last_updated = norm_null(tds[3].text) if len(tds) > 3 else None
        restatement = norm_null(tds[4].text) if len(tds) > 4 else None

        out.append({
            "group": current_group,
            "field_name": field_name,
            "data_key": data_key,
            "value": norm_null(value),
            "source": source,
            "last_updated": last_updated,
            "restatement": restatement,
            "row_id": row_id,
            "row_type": "item"
        })

    return out

def scrape_current_view_tables(driver, timeout=30) -> list[dict[str, Any]]:
    dismiss_null_modal(driver, timeout=1.0)
    try:
        wait_any_table_or_empty(driver, timeout=timeout)
    except TimeoutException:
        return [{"row_type": "timeout", "field_name": None, "value": None}]

    table = pick_real_table(driver)
    if table is None:
        # 테이블이 진짜 없을 수도 있음
        return [{"row_type": "no_table", "field_name": None, "value": None}]

    rows = parse_table(table)
    if not rows:
        return [{"row_type": "empty", "field_name": None, "value": None}]
    return rows

# ---------------------------
# 회사 1곳 스크랩: EMISSIONS(4개) + TARGETS(3개)
# ---------------------------
EMISSIONS_SUBTABS = [
    "SCOPE 1 EMISSIONS",
    "SCOPE 2 EMISSIONS",
    "SCOPE 3 EMISSIONS",
    "ASSURANCE AND VERIFICATION",
]

TARGETS_SUBTABS = [
    "EMISSIONS REDUCTION TARGETS",
    "PROGRESS",
    "VALIDATION",
]

def company_id_from_url(url: str) -> str | None:
    m = re.search(r"/companies/(\d+)", url)
    return m.group(1) if m else None


def build_error_row(company_url: str, page_url: str, error: Exception) -> dict:
    return {
        "company_id": company_id_from_url(company_url),
        "company_url": company_url,
        "top_tab": "ERROR",
        "subtab": None,
        "page_url": page_url,
        "row_type": "error",
        "field_name": None,
        "data_key": None,
        "value": None,
        "source": None,
        "last_updated": None,
        "restatement": None,
        "error": repr(error),
    }


TOP_TABS_REQUIRED = ["EMISSIONS", "EMISSIONS REDUCTION TARGETS"]
EMISSIONS_TABS_REQUIRED = ["SCOPE 1", "SCOPE 2", "SCOPE 3", "ASSURANCE"]
TARGETS_TABS_REQUIRED = ["EMISSIONS REDUCTION TARGETS", "PROGRESS", "VALIDATION"]

def scrape_one_company(driver, company_url: str) -> list[dict[str, Any]]:
    cid = company_id_from_url(company_url)

    driver.get(company_url)
    dismiss_all_popups(driver)

    all_rows = []

    # 1) 상단: EMISSIONS
    click_tab_by_labels(driver, TOP_TABS_REQUIRED, "EMISSIONS", timeout=20)

    for sub in EMISSIONS_SUBTABS:
        click_tab_by_labels(driver, EMISSIONS_TABS_REQUIRED, sub, timeout=20)
        rows = scrape_current_view_tables(driver, timeout=35)
        cur_url = driver.current_url
        for r in rows:
            r.update({
                "company_id": cid,
                "company_url": company_url,
                "top_tab": "EMISSIONS",
                "subtab": sub,
                "page_url": cur_url,
            })
        all_rows.extend(rows)

    # 2) 상단: TARGETS
    click_tab_by_labels(driver, TOP_TABS_REQUIRED, "EMISSIONS REDUCTION TARGETS", timeout=20)

    for sub in TARGETS_SUBTABS:
        click_tab_by_labels(driver, TARGETS_TABS_REQUIRED, sub, timeout=20)
        rows = scrape_current_view_tables(driver, timeout=35)
        cur_url = driver.current_url
        for r in rows:
            r.update({
                "company_id": cid,
                "company_url": company_url,
                "top_tab": "EMISSIONS REDUCTION TARGETS",
                "subtab": sub,
                "page_url": cur_url,
            })
        all_rows.extend(rows)
    return all_rows


# ---------------------------
# 실행
# ---------------------------
def parse_args(repo_root: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="NZDPU extractor (company emissions/targets table scraper)."
    )
    parser.add_argument(
        "--list-url",
        default=DEFAULT_LIST_URL,
        help="Companies list URL used to resolve company pages.",
    )
    parser.add_argument(
        "--jurisdiction",
        default=None,
        help="List page jurisdiction filter (e.g. Japan). 기본값: 미지정(전체).",
    )
    parser.add_argument("--max-pages", type=int, default=200, help="Maximum pages to scan from list view.")
    parser.add_argument("--timeout", type=int, default=30, help="Selenium wait timeout (seconds).")
    parser.add_argument("--sleep-sec", type=float, default=0.2, help="Delay between company requests.")

    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument(
        "--collect-all",
        action="store_true",
        help="Collect all company URLs from the list page.",
    )
    input_group.add_argument(
        "--company-urls-file",
        type=Path,
        help="Text/CSV file with company URLs (relative path 기준: repo root).",
    )
    input_group.add_argument(
        "--company-names-file",
        type=Path,
        help="Text/CSV file with company names to match from the list page.",
    )
    parser.add_argument(
        "--print-missing",
        action="store_true",
        help="Print names that were not matched when --company-names-file is used.",
    )

    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode.")
    parser.add_argument("--window-size", default="1400,900")
    parser.add_argument("--page-load-timeout", type=int, default=60)
    parser.add_argument(
        "--user-data-dir",
        type=Path,
        default=Path("storage") / "raw" / SOURCE_NAME / ".chrome-profile",
        help="Chrome user data directory.",
    )

    parser.add_argument(
        "--run-date",
        help="Output partition date (YYYY-MM-DD). 기본값: today.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory. 기본값: storage/raw/<source>/<run_date>/",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        help="Final CSV file path. 지정 시 --output-dir 대신 사용.",
    )

    args = parser.parse_args()

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

    # 상대 경로는 repo root 기준으로 해석
    if args.company_urls_file:
        args.company_urls_file = resolve_path(args.company_urls_file, repo_root)
    if args.company_names_file:
        args.company_names_file = resolve_path(args.company_names_file, repo_root)
    if args.output_dir:
        args.output_dir = resolve_path(args.output_dir, repo_root)
    if args.output_file:
        args.output_file = resolve_path(args.output_file, repo_root)
    if args.user_data_dir:
        args.user_data_dir = resolve_path(args.user_data_dir, repo_root)

    return args


def resolve_output_file(args: argparse.Namespace, repo_root: Path) -> Path:
    if args.output_file:
        output_file = args.output_file
    else:
        run_date = args.run_date or datetime.now().strftime("%Y-%m-%d")
        output_dir = args.output_dir or (repo_root / "storage" / "raw" / SOURCE_NAME / run_date)
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        output_file = output_dir / f"company_emissions_targets_{timestamp}.csv"

    output_file.parent.mkdir(parents=True, exist_ok=True)
    return output_file


def resolve_company_urls(driver, args: argparse.Namespace) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    list_url = build_companies_list_url(args.list_url, args.jurisdiction)

    if args.company_urls_file:
        company_urls = load_company_urls(args.company_urls_file)
    elif args.company_names_file:
        company_names = load_company_names(args.company_names_file)
        if not company_names:
            raise ValueError(f"company names file is empty: {args.company_names_file}")
        company_urls, missing = collect_company_urls_from_list_filtered(
            driver,
            list_url=list_url,
            company_name_list=company_names,
            timeout=args.timeout,
            max_pages=args.max_pages,
        )
    else:
        # --collect-all 이거나 아무 인자를 주지 않은 경우 전체 수집
        company_urls = collect_all_company_urls_from_list(
            driver,
            list_url=list_url,
            timeout=args.timeout,
            max_pages=args.max_pages,
        )

    if not company_urls:
        raise RuntimeError("resolved company URL list is empty")
    return company_urls, missing


def run(args: argparse.Namespace, output_file: Path) -> None:
    driver = build_driver(
        headless=args.headless,
        window_size=args.window_size,
        user_data_dir=args.user_data_dir,
        page_load_timeout=args.page_load_timeout,
    )

    try:
        company_urls, missing = resolve_company_urls(driver, args)
        print("companies:", len(company_urls))

        if missing and args.print_missing:
            print(f"missing companies ({len(missing)}):")
            for m in missing:
                print(f"- {m}")

        all_rows = []
        for i, company_url in enumerate(company_urls, 1):
            print(f"[{i}/{len(company_urls)}] {company_url}")
            try:
                all_rows.extend(scrape_one_company(driver, company_url))
            except Exception as e:
                # 회사 하나가 터져도 전체 죽지 않게
                print("error:", e)
                all_rows.append(build_error_row(company_url, driver.current_url, e))
            time.sleep(args.sleep_sec)

        df = pd.DataFrame(all_rows)
        df.to_csv(output_file, index=False, encoding="utf-8-sig")
        print(f"done: {len(df)} rows -> {output_file}")
    finally:
        driver.quit()


def main() -> None:
    repo_root = find_repo_root()
    args = parse_args(repo_root)
    output_file = resolve_output_file(args, repo_root)
    run(args, output_file)


if __name__ == "__main__":
    main()
