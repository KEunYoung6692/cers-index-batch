from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
import time
import requests
from bs4 import BeautifulSoup

import pandas as pd

import openpyxl
import os
import sys
import time
import json
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By


import re
import time
from selenium.webdriver.common.by import By

FRAME_KEYS = {"gri", "sasb", "tcfd", "un_sdgs"}

def download_report(driver, page_idx=1):
    """
    현재 목록 페이지에서 각 기업별 정보를 크롤링해서
    [{...}, {...}, ...] 형태로 반환합니다.
    """
    main_handle = driver.current_window_handle

    rows_data = []  # 이 페이지에서 수집할 결과들

    report_buttons = driver.find_elements(By.CSS_SELECTOR, 'a.icon_down.id_s2301.useK')
    total = len(report_buttons)
    print(f"[page {page_idx}] 총 보고서 버튼 개수: {total}")

    for idx in range(total):
        # 매 loop마다 다시 찾아서 stale 방지
        report_buttons = driver.find_elements(By.CSS_SELECTOR, 'a.icon_down.id_s2301.useK')
        if idx >= len(report_buttons):
            break

        btn = report_buttons[idx]

        # 이 버튼이 속한 tr 기준으로 리스트 정보 수집
        row_el = btn.find_element(By.XPATH, './ancestor::tr[1]')

        # 기본 row dict
        row_data = {
            "page_idx": page_idx,
            "row_idx": idx,
            "company_name": None,
            "industry": None,
            "frameworks": None,
            "list_assurance_org": None,   # 목록 테이블의 제3자 검증
            "report_name": None,          # 팝업 1. 보고서 명칭
            "detail_assurance_org": None, # 팝업 2. 검증기관(국문)
            "homepage": None,             # 팝업 4. 제출처 URL
            "submit_date": None,          # 팝업 6. 제출(확인)일자
        }

        # 회사명
        try:
            com_td = row_el.find_element(By.CSS_SELECTOR, 'td[name="com_abbrv"]')
            row_data["company_name"] = com_td.text.strip().split()[0]
        except Exception:
            pass

        # 업종
        try:
            upjong_td = row_el.find_element(By.CSS_SELECTOR, 'td[name="upjong"]')
            lines = [t.strip() for t in upjong_td.text.splitlines() if t.strip()]
            row_data["industry"] = lines[-1] if lines else None
        except Exception:
            pass

        # 목록 테이블의 제3자 검증기관
        try:
            remk_td = row_el.find_element(By.CSS_SELECTOR, 'td[name="remk"]')
            lines = [t.strip() for t in remk_td.text.splitlines() if t.strip()]
            row_data["list_assurance_org"] = lines[-1] if lines else None
        except Exception:
            pass

        # 작성기준 아이콘 (gri/sasb/tcfd/un_sdgs)
        try:
            bas_td = row_el.find_element(By.CSS_SELECTOR, 'td[name="bas_itm_cd_nm"]')
            spans_icon = bas_td.find_elements(By.CSS_SELECTOR, 'span.stan-icon')

            frameworks = set()
            for span in spans_icon:
                class_attr = span.get_attribute("class") or ""
                classes = class_attr.split()
                hit = FRAME_KEYS.intersection(classes)
                frameworks.update(hit)

            row_data["frameworks"] = ",".join(sorted(list(frameworks))) if frameworks else None
        except Exception:
            pass

        print(f"[page {page_idx} / row {idx}] list-info:",
              row_data["company_name"], row_data["industry"],
              row_data["list_assurance_org"], row_data["frameworks"])

        if not btn.is_displayed():
            rows_data.append(row_data)
            continue

        # 팝업 열기
        driver.switch_to.window(main_handle)
        btn.click()
        time.sleep(1.5)

        # 팝업 전환
        handles = driver.window_handles
        popup_handle = None
        for h in handles:
            if h != main_handle:
                popup_handle = h
                break

        if popup_handle is None:
            print(f"[page {page_idx} / row {idx}] 팝업 핸들을 찾지 못했습니다.")
            rows_data.append(row_data)
            continue

        driver.switch_to.window(popup_handle)

        try:
            # iframe 진입
            time.sleep(1.5)
            driver.switch_to.frame("docViewFrm")
            time.sleep(0.5)

            spans = driver.find_elements(By.CSS_SELECTOR, "span.xforms_input")
            print(f"[page {page_idx} / row {idx}] xforms_input 개수:", len(spans))

            def safe_get(i):
                return spans[i].text.strip() if len(spans) > i else None

            # 인덱스 구조: 0:보고서명, 1:검증기관(국문), 4:제출처, 6:제출일자
            row_data["report_name"] = safe_get(0)
            row_data["detail_assurance_org"] = safe_get(1)

            homepage_raw = safe_get(4)
            if homepage_raw:
                m = re.search(r"(https?://[^\s)]+)", homepage_raw)
                row_data["homepage"] = m.group(1) if m else homepage_raw

            row_data["submit_date"] = safe_get(6)

            print(
                f"    report_name={row_data['report_name']}, "
                f"detail_assurance_org={row_data['detail_assurance_org']}, "
                f"homepage={row_data['homepage']}, submit_date={row_data['submit_date']}"
            )

            # (원하면 여기서 바로 PDF까지 처리)

        except Exception as e:
            print(f"[page {page_idx} / row {idx}] 팝업 처리 중 오류:", e)

        finally:
            try:
                driver.switch_to.default_content()
            except:
                pass
            try:
                driver.close()
            except:
                pass
            driver.switch_to.window(main_handle)
            time.sleep(1)

        # 이 row에 대한 정보 수집 완료 → 리스트에 추가
        rows_data.append(row_data)

    return rows_data

def all_pages_download(year):
    url = 'https://esg.krx.co.kr/contents/02/02030000/ESG02030000.jsp'

    options = webdriver.ChromeOptions()
    options.add_argument(
        'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/58.0.3029.110 Safari/537.36'
    )

    options.add_experimental_option("prefs", prefs)
    options.add_argument("--lang=ko-KR")
    driver = webdriver.Chrome(options=options)

    driver.get(url)
    time.sleep(3)

    # 상세검색 버튼 클릭
    driver.find_element(By.CSS_SELECTOR, 'button.detail-search-button').click()
    time.sleep(1)

    # TCFD 체크 (3번째)
    driver.find_elements(By.CSS_SELECTOR, 'label.bas_itm_chk')[2].click()

    #년도 선택
    year = str(year)
    year_select = Select(driver.find_element(By.ID, 'sch_yyc4ca4238a0b923820dcc509a6f75849b'))
    year_select.select_by_value(year)   # "2025", "2024" 등
    time.sleep(0.2)
    
    # 검색 버튼 클릭 (id 값은 예제 그대로)
    driver.find_elements(By.ID, 'btnidc4ca4238a0b923820dcc509a6f75849b')[1].click()
    time.sleep(1)

    all_rows = []
    page_idx = 1

    while True:
        # 현재 페이지의 모든 기업 정보 수집
        page_rows = download_report(driver, page_idx=page_idx)
        all_rows.extend(page_rows)

        # 페이지네이션의 '다음' 버튼 상태 확인
        try:
            pagination = driver.find_element(By.CSS_SELECTOR, "div.pagination")
            next_li = pagination.find_element(By.CSS_SELECTOR, "li.next")
        except Exception:
            print("pagination 또는 next 버튼을 찾지 못했습니다. 종료합니다.")
            break

        classes = next_li.get_attribute("class") or ""
        if "disabled" in classes:
            print("마지막 페이지입니다. 종료합니다.")
            break

        # 다음 페이지로 이동
        next_a = next_li.find_element(By.TAG_NAME, "a")
        next_a.click()
        page_idx += 1
        time.sleep(3)  # 목록/버튼 갱신 대기

    driver.quit()

    # DataFrame으로 변환
    df = pd.DataFrame(all_rows)
    return df


if __name__ == "__main__":

    years = [2021, 2022, 2023, 2024, 2025]

    for year in years:

        print(f"Downloading companies for {year}...")
        df = all_pages_download(year)

        df['company_type'] = 'legal_entity'
        df['country'] = 'KR'
        df['report_year'] = str(year)


        df = df.rename(columns = {'submit_date': 'submission_date', 'frameworks': 'framework_code', 'list_assurance_org' : 'assurance_org', 'report_name': 'report_title'})
        df.to_csv(f'tables/{year}/df.csv', index=False)
        reports = df[['company_name', 'report_title', 'submission_date', 'report_year', 'assurance_org']]
        companies = df.drop(columns = ['page_idx', 'row_idx', 'detail_assurance_org', 'report_title', 'submission_date', 'report_year', 'assurance_org', 'framework_code'])
        frameworks = df[['company_name', 'report_title', 'framework_code']]

        out = (
            frameworks.assign(
                framework_code=frameworks["framework_code"]
                    .fillna("")                  # NaN 방지
                    .astype(str)
                    .str.split(",")              # 콤마 분리 (list)
            )
            .explode("framework_code", ignore_index=True)  # list -> row
        )

        # 공백/빈값 정리
        out["framework_code"] = out["framework_code"].astype(str).str.strip()
        frameworks = out[out["framework_code"].ne("")].reset_index(drop=True)


        companies.to_csv(f'tables/{year}/companies.csv', index=False)
        frameworks.to_csv(f'tables/{year}/frameworks.csv', index=False)
        reports.to_csv(f'tables/{year}/reports.csv', index=False)

        print(f"Downloaded companies for {year} successfully.")