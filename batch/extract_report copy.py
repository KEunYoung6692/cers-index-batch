# -*- coding: utf-8 -*-
"""
ESG / 탄소 관련 PDF 원문 추출기  (v2 - 경량화 + 완전 추출)

- 목표: LLM API 입력 토큰 최소화 + 정보 누락 없는 완전 추출
- 입력: 텍스트 기반 PDF
- 출력: JSON (페이지×카테고리 단위 통합)

추출 방식:
  1) 텍스트 블록(PyMuPDF) + 인접 블록 컨텍스트 확장
     - line_window 방식 완전 대체: 블록 단위로 인접 컨텍스트 포함
  2) 표(pdfplumber)
  3) 페이지×카테고리 단위로 통합하여 중복 제거

카테고리:
  1) board_governance : 이사회 / ESG위원회 / 기후 거버넌스
  2) carbon_targets   : 탄소중립 / Net Zero / RE100 / 감축 목표
  3) internal_actions : 재생에너지 / 효율화 / 폐기물 / 자원순환 / 저감활동
  4) capital_flow     : 친환경 투자 / 환경 관련 투자 / CapEx / 배출권 비용
  5) emissions        : 온실가스 배출량 / Scope 1,2,3 / 검증의견서
"""

import os
import re
import json
import argparse
from datetime import datetime

import fitz  # PyMuPDF
import pdfplumber


# -----------------------------------
# 1) 카테고리별 핵심 패턴
# -----------------------------------
CATEGORY_PATTERNS = {
    "board_governance": [
        r"이사회",
        r"지속가능경영위원회",
        r"ESG위원회",
        r"사외이사",
        r"이사회 보고",
        r"기후변화 관련 이사회",
        r"환경 관련 이사회",
        r"리스크관리위원회",
    ],
    "carbon_targets": [
        r"탄소중립",
        r"탄소 중립",
        r"Net Zero",
        r"net zero",
        r"RE100",
        r"감축 목표",
        r"온실가스 목표",
        r"배출 감축 목표",
        r"탄소중립 로드맵",
        r"탄소 중립 로드맵",
        r"로드맵",
        r"배출량 Zero",
        r"2050",
        r"2045",
        r"2040",
        r"2035",
        r"2030",
    ],
    "internal_actions": [
        r"재생에너지",
        r"태양광",
        r"PPA",
        r"자가발전",
        r"자체발전",
        r"에너지 효율화",
        r"에너지 절감",
        r"에너지 관리",
        r"폐기물",
        r"자원순환",
        r"녹색구매",
        r"환경교육",
        r"탄소배출 저감",
        r"온실가스 감축 활동",
        r"회수보일러",
        r"SAF",
        r"LCA",
        r"친환경 설비",
        r"전력 사용 절감",
    ],
    "capital_flow": [
        r"환경 관련 투자",
        r"친환경 투자",
        r"기후변화 대응 투자",
        r"탄소중립 투자",
        r"환경투자",
        r"설비 투자",
        r"설비투자",
        r"자본적 지출",
        r"자본지출",
        r"CapEx",
        r"CAPEX",
        r"투자 현황",
        r"투자 금액",
        r"집행 실적",
        r"에너지 절감 비용",
        r"배출권 구매 비용",
        r"배출권 비용",
        r"환경 비용",
    ],
    "emissions": [
        r"온실가스 배출량",
        r"온실가스 배출",
        r"온실가스 인벤토리",
        r"인벤토리",
        r"배출 집약도",
        r"직접 배출",
        r"간접 배출",
        r"Scope\s*1",
        r"Scope\s*2",
        r"Scope\s*3",
        r"tCO2eq",
        r"tCO2-eq",
        r"tCO2e",
        r"tCO₂eq",
        r"tCO₂e",
        r"천tCO2eq",
        r"온실가스 검증",
        r"검증 의견서",
        r"검증의견서",
        r"검증 성명서",
    ],
}


# -----------------------------------
# 2) 문맥 필터
#    - 오탐이 많은 카테고리에만 강하게 적용
# -----------------------------------
CONTEXT_PATTERNS = {
    "board_governance": [
        r"기후",
        r"탄소",
        r"ESG",
        r"환경",
        r"리스크",
        r"온실가스",
        r"지속가능",
        r"감독",
    ],
    "capital_flow": [
        r"기후",
        r"탄소",
        r"온실가스",
        r"환경",
        r"재생에너지",
        r"배출권",
        r"에너지",
        r"감축",
        r"저감",
    ],
}


# -----------------------------------
# 3) 섹션 힌트
#    - 섹션 제목/목차 문구를 우선 인식
# -----------------------------------
SECTION_HINTS = {
    "board_governance": [
        r"ESG 거버넌스",
        r"지배구조",
        r"이사회 구성 및 운영",
        r"이사회 운영",
        r"지속가능경영위원회",
        r"ESG위원회",
        r"환경경영 거버넌스",
        r"기후변화 관련 거버넌스",
    ],
    "carbon_targets": [
        r"기후변화 대응",
        r"탄소중립",
        r"탄소 중립",
        r"탄소중립 로드맵",
        r"탄소 중립 로드맵",
        r"Net Zero",
        r"RE100",
        r"기후 목표",
        r"온실가스 감축 목표",
    ],
    "internal_actions": [
        r"환경경영",
        r"기후변화 대응",
        r"에너지 관리",
        r"재생에너지",
        r"폐기물 관리",
        r"자원순환",
        r"환경 성과",
        r"친환경 활동",
    ],
    "capital_flow": [
        r"환경 관련 투자",
        r"친환경 투자",
        r"기후변화 대응 투자",
        r"탄소중립 투자",
        r"환경 비용",
        r"환경 투자",
    ],
    "emissions": [
        r"온실가스 배출량",
        r"온실가스 인벤토리",
        r"온실가스 검증",
        r"검증 의견서",
        r"검증 성명서",
        r"배출량 데이터",
    ],
}


# -----------------------------------
# 4) 숫자 / 단위 패턴
#    - 정규화는 하지 않고 원문 mention만 수집
# -----------------------------------
VALUE_PATTERNS = [
    r"\b(?:19|20)\d{2}\b",
    r"\d[\d,\.]*\s*(?:tCO2e|tCO2eq|tCO2-eq|tCO₂e|tCO₂eq|kgCO2e|kgCO2eq|천tCO2eq)",
    r"\d[\d,\.]*\s*(?:TJ|GJ|MW|MWh|kWh|%)",
    r"\d[\d,\.]*\s*(?:억\s*원|조\s*원|백만\s*원|백만원|천원|원)",
    r"\bScope\s*[123]\b",
    r"\bRE100\b",
    r"\bPPA\b",
]


# -----------------------------------
# 인접 블록 컨텍스트 확장 설정
#   - 매칭 블록 위아래 최대 N개 인접 블록 포함
#   - 수직 간격이 CONTEXT_GAP_PX 이내인 경우에만 확장
# -----------------------------------
CONTEXT_NEIGHBOR_COUNT = 1   # 위아래 각 최대 몇 블록
CONTEXT_GAP_PX = 80          # 블록 간 최대 수직 간격(px)


# -----------------------------------
# 5) 유틸
# -----------------------------------
def clean_text(text: str) -> str:
    if text is None:
        return ""
    text = str(text)
    text = text.replace("\xa0", " ")
    text = text.replace("\u200b", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def unique_preserve_order(seq):
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def find_matched_keywords(text: str, patterns):
    matched = []
    for p in patterns:
        if re.search(p, text, flags=re.IGNORECASE):
            matched.append(p)
    return matched


def find_section_hints(text: str, patterns):
    matched = []
    for p in patterns:
        if re.search(p, text, flags=re.IGNORECASE):
            matched.append(p)
    return matched


def find_value_mentions(text: str):
    vals = []
    for p in VALUE_PATTERNS:
        vals.extend(re.findall(p, text, flags=re.IGNORECASE))
    return unique_preserve_order(vals)


def matched_with_context(text: str, main_patterns, context_patterns=None):
    main = [p for p in main_patterns if re.search(p, text, flags=re.IGNORECASE)]
    if not main:
        return []

    if context_patterns:
        has_context = any(re.search(p, text, flags=re.IGNORECASE) for p in context_patterns)
        if not has_context:
            return []

    return main


def match_category_text(category: str, text: str):
    """
    카테고리별 최종 매칭 함수
    1) 섹션 힌트 우선 수집
    2) 필요 카테고리는 문맥 필터 적용
    3) 연도 단독 오탐 방지
    """
    main_patterns = CATEGORY_PATTERNS[category]
    context_patterns = CONTEXT_PATTERNS.get(category)
    section_patterns = SECTION_HINTS.get(category, [])

    section_hits = find_section_hints(text, section_patterns)

    if context_patterns:
        main_hits = matched_with_context(text, main_patterns, context_patterns)
    else:
        main_hits = find_matched_keywords(text, main_patterns)

    # carbon_targets: 2030/2040/2045/2050 숫자만 단독으로 잡히는 오탐 방지
    if category == "carbon_targets" and main_hits:
        only_year_tokens = {r"2050", r"2045", r"2040", r"2035", r"2030"}
        if all(x in only_year_tokens for x in main_hits):
            if not re.search(r"탄소|온실가스|기후|RE100|Net Zero|net zero|감축|로드맵", text, flags=re.IGNORECASE):
                main_hits = []

    # capital_flow: 투자 문구가 있어도 환경/탄소 맥락 없으면 제외
    if category == "capital_flow" and main_hits:
        if not re.search(r"기후|탄소|온실가스|환경|재생에너지|배출권|에너지|감축|저감", text, flags=re.IGNORECASE):
            main_hits = []

    return unique_preserve_order(section_hits + main_hits)


# -----------------------------------
# 6) 텍스트 블록 추출 (PyMuPDF)
# -----------------------------------
def extract_text_blocks(pdf_path: str):
    doc = fitz.open(pdf_path)
    pages = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_num = page_idx + 1

        blocks = []
        raw_blocks = page.get_text("blocks")

        for b in raw_blocks:
            if len(b) < 5:
                continue

            x0, y0, x1, y1, text = b[:5]
            text = clean_text(text)
            if not text:
                continue

            blocks.append({
                "bbox": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
                "text": text
            })

        pages.append({
            "page": page_num,
            "blocks": blocks
        })

    doc.close()
    return pages


# -----------------------------------
# 7) 표 추출 (pdfplumber)
# -----------------------------------
def extract_tables(pdf_path: str):
    all_tables = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages, start=1):
            try:
                tables = page.extract_tables()
            except Exception:
                tables = []

            for t_idx, table in enumerate(tables, start=1):
                if not table:
                    continue

                cleaned_rows = []
                for row in table:
                    row = row or []
                    cleaned_row = [clean_text(cell) if cell is not None else "" for cell in row]
                    if any(cell for cell in cleaned_row):
                        cleaned_rows.append(cleaned_row)

                if not cleaned_rows:
                    continue

                # 매칭 검사용 텍스트 (내부용, 출력에는 미포함)
                table_text = "\n".join(" | ".join(row) for row in cleaned_rows)

                all_tables.append({
                    "page": page_idx,
                    "table_index": t_idx,
                    "rows": cleaned_rows,
                    "_table_text": table_text   # 내부 매칭용 (출력 시 제외)
                })

    return all_tables


# -----------------------------------
# 8) 인접 블록 컨텍스트 확장
#    - line_window 방식 대체
#    - 매칭 블록 ±N개 인접 블록을 수직 간격 기준으로 포함
# -----------------------------------
def expand_with_neighbors(sorted_blocks, matched_indices):
    """
    매칭된 블록 인덱스를 기준으로, 수직으로 인접한 블록을 확장하여
    포함할 블록 인덱스 집합을 반환한다.

    - CONTEXT_NEIGHBOR_COUNT: 위아래 최대 N개
    - CONTEXT_GAP_PX: 블록 간 수직 간격 임계값(px)
    """
    n = len(sorted_blocks)
    included = set(matched_indices)

    for i in matched_indices:
        # 위쪽 (역방향)
        neighbor_count = 0
        j = i - 1
        while j >= 0 and neighbor_count < CONTEXT_NEIGHBOR_COUNT:
            # 현재 블록의 y0와 j번 블록의 y1 사이 간격 확인
            gap = sorted_blocks[i]["bbox"][1] - sorted_blocks[j]["bbox"][3]
            if gap <= CONTEXT_GAP_PX:
                included.add(j)
                neighbor_count += 1
                j -= 1
            else:
                break

        # 아래쪽 (순방향)
        neighbor_count = 0
        j = i + 1
        while j < n and neighbor_count < CONTEXT_NEIGHBOR_COUNT:
            gap = sorted_blocks[j]["bbox"][1] - sorted_blocks[i]["bbox"][3]
            if gap <= CONTEXT_GAP_PX:
                included.add(j)
                neighbor_count += 1
                j += 1
            else:
                break

    return included


# -----------------------------------
# 9) 페이지×카테고리 단위 통합 추출
# -----------------------------------
def consolidate_page_for_category(blocks, category):
    """
    한 페이지의 블록들을 카테고리 기준으로 분석하여,
    매칭 블록 + 인접 컨텍스트를 통합한 단일 excerpt를 반환한다.

    반환값: dict or None
      {
        "keywords": [...],
        "values":   [...],
        "text":     "..."
      }
    """
    if not blocks:
        return None

    # y0 기준으로 정렬 (읽기 순서)
    sorted_blocks = sorted(blocks, key=lambda b: b["bbox"][1])
    n = len(sorted_blocks)

    # 매칭 블록 탐색
    matched_indices = set()
    all_keywords = []

    for i, blk in enumerate(sorted_blocks):
        kw = match_category_text(category, blk["text"])
        if kw:
            matched_indices.add(i)
            all_keywords.extend(kw)

    if not matched_indices:
        return None

    # 인접 블록 컨텍스트 확장
    included_indices = expand_with_neighbors(sorted_blocks, matched_indices)

    # 포함 블록 텍스트 통합 (위치 순)
    included_blocks = [sorted_blocks[i] for i in sorted(included_indices)]
    merged_text = "\n".join(blk["text"] for blk in included_blocks)
    merged_text = clean_text(merged_text)

    # 통합 텍스트로 키워드/값 재집계
    all_keywords = unique_preserve_order(all_keywords)
    value_mentions = find_value_mentions(merged_text)

    return {
        "keywords": all_keywords,
        "values": value_mentions,
        "text": merged_text,
    }


# -----------------------------------
# 10) 카테고리 분류 (경량화 버전)
# -----------------------------------
def classify_hits(text_pages, tables):
    results = {
        cat: {"page_excerpts": [], "table_hits": []}
        for cat in CATEGORY_PATTERNS
    }

    # 텍스트 블록 - 페이지×카테고리 단위 통합
    for page in text_pages:
        page_num = page["page"]
        blocks = page["blocks"]

        for category in CATEGORY_PATTERNS:
            excerpt = consolidate_page_for_category(blocks, category)
            if excerpt:
                results[category]["page_excerpts"].append({
                    "page": page_num,
                    "keywords": excerpt["keywords"],
                    "values": excerpt["values"],
                    "text": excerpt["text"],
                })

    # 표 - 카테고리 매칭
    for tbl in tables:
        table_text = tbl["_table_text"]
        for category in CATEGORY_PATTERNS:
            matched = match_category_text(category, table_text)
            if matched:
                results[category]["table_hits"].append({
                    "page": tbl["page"],
                    "table_index": tbl["table_index"],
                    "keywords": matched,
                    "values": find_value_mentions(table_text),
                    "rows": tbl["rows"],
                })

    # 정렬 (페이지 순)
    for category in results:
        results[category]["page_excerpts"].sort(key=lambda x: x["page"])
        results[category]["table_hits"].sort(key=lambda x: x["page"])

    return results


# -----------------------------------
# 11) 요약 메타
# -----------------------------------
def build_summary(results):
    summary = {}

    for category, payload in results.items():
        pages = set()
        for x in payload["page_excerpts"]:
            pages.add(x["page"])
        for x in payload["table_hits"]:
            pages.add(x["page"])

        summary[category] = {
            "page_count": len(pages),
            "pages": sorted(list(pages)),
            "excerpt_count": len(payload["page_excerpts"]),
            "table_count": len(payload["table_hits"]),
        }

    return summary


# -----------------------------------
# 12) 실행
# -----------------------------------
def run(pdf_path: str, output_path: str):
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")

    text_pages = extract_text_blocks(pdf_path)
    tables = extract_tables(pdf_path)
    results = classify_hits(text_pages, tables)
    summary = build_summary(results)

    output = {
        "source_pdf": os.path.abspath(pdf_path),
        "generated_at": datetime.now().isoformat(),
        "page_count": len(text_pages),
        "summary": summary,
        "categories": results,
    }

    with open(output_path, "w", encoding="utf-8-sig") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[완료] 저장: {output_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="탄소/ESG 관련 PDF 원문 추출기")
    parser.add_argument("--pdf_path", help="입력 PDF 경로")
    parser.add_argument(
        "--output",
        default="esg_carbon_extraction.json",
        help="출력 JSON 경로 (default: esg_carbon_extraction.json)",
    )
    args = parser.parse_args()

    run(args.pdf_path, args.output)
