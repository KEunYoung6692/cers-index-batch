# -*- coding: utf-8 -*-
"""
ESG / 탄소 관련 PDF 추출기 (LangChain + 경량화 버전)

목표:
1) PDF 추출 라이브러리를 LangChain 로더로 통일
2) LLM 입력 토큰 절감을 위해 탄소/ESG 핵심 정보만 보존

출력 스키마:
- categories -> {records, facts}
- records: 핵심 snippet + 값/신호
- facts: 카테고리 전체 집계(연도/scope/검증/목표 관련)
"""

import argparse
import json
import os
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

try:
    from langchain_community.document_loaders import PDFPlumberLoader
except ImportError:
    try:
        # 구버전 호환
        from langchain.document_loaders import PDFPlumberLoader
    except ImportError as exc:
        raise RuntimeError(
            "LangChain PDF 로더가 필요합니다. "
            "예: pip install langchain langchain-community pdfplumber"
        ) from exc


# -----------------------------------
# 1) 카테고리별 핵심 패턴
# -----------------------------------
CATEGORY_PATTERNS: Dict[str, List[str]] = {
    "board_governance": [
        r"이사회",
        r"이사회\s*산하",
        r"이사회\s*보고",
        r"이사회\s*승인",
        r"이사회\s*감독",
        r"ESG위원회",
        r"지속가능경영위원회",
        r"기후변화위원회",
        r"기후\s*위원회",
        r"환경\s*위원회",
        r"리스크관리위원회",
        r"리스크\s*관리",
        r"기후\s*리스크",
        r"전사\s*리스크",
        r"TCFD",
        r"거버넌스",
        r"climate governance",
        r"board oversight",
        r"board of directors",
        r"management role",
        r"경영진\s*역할",
        r"최고경영진",
        r"대표이사",
        r"CSO",
        r"책임\s*조직",
        r"전담\s*조직",
        r"의사결정",
        r"KPI",
        r"성과평가",
        r"보상\s*연계",
        r"환경 관련 이사회",
        r"기후변화 관련 이사회",
        r"사외이사",
    ],
    "carbon_targets": [
        r"탄소중립",
        r"탄소 중립",
        r"탄소중립\s*달성",
        r"탄소중립\s*비전",
        r"Net Zero",
        r"net zero",
        r"net-zero",
        r"RE100",
        r"SBTi",
        r"Science Based Targets",
        r"NDC",
        r"국가온실가스감축목표",
        r"절대배출",
        r"배출집약도\s*목표",
        r"집약도\s*목표",
        r"감축률",
        r"감축\s*경로",
        r"감축\s*시나리오",
        r"감축 목표",
        r"온실가스 목표",
        r"배출 감축 목표",
        r"탄소중립 로드맵",
        r"탄소 중립 로드맵",
        r"로드맵",
        r"이행계획",
        r"전환계획",
        r"transition plan",
        r"목표치",
        r"목표값",
        r"목표연도",
        r"기준연도",
        r"base year",
        r"baseline year",
        r"중간목표",
        r"중간\s*목표",
        r"interim target",
        r"milestone",
        r"목표 범위",
        r"목표범위",
        r"적용 범위",
        r"조직 경계",
        r"운영 경계",
        r"value chain",
        r"upstream",
        r"downstream",
        r"1\.5",
        r"단기",
        r"중기",
        r"장기",
        r"short[\s-]*term",
        r"mid[\s-]*term",
        r"long[\s-]*term",
        r"Scope\s*[123]",
        r"Scope\s*1,?\s*2,?\s*3",
        r"2050",
        r"2045",
        r"2040",
        r"2035",
        r"2030",
        r"2028",
        r"2027",
        r"2026",
        r"2025",
    ],
    "internal_actions": [
        r"감축 활동",
        r"감축 이행",
        r"배출 저감",
        r"탄소 저감",
        r"재생에너지",
        r"재생전력",
        r"재생에너지 전환",
        r"신재생에너지",
        r"태양광",
        r"풍력",
        r"PPA",
        r"REC",
        r"녹색프리미엄",
        r"자가발전",
        r"자체발전",
        r"연료 전환",
        r"전기화",
        r"공정 개선",
        r"설비 개선",
        r"저탄소 연료",
        r"LNG\s*전환",
        r"수소",
        r"그린수소",
        r"CCUS",
        r"탄소 포집",
        r"메탄",
        r"누출 저감",
        r"에너지 효율화",
        r"에너지 절감",
        r"에너지 관리",
        r"열회수",
        r"효율 개선",
        r"고효율 설비",
        r"전력 최적화",
        r"전동화",
        r"전기차 전환",
        r"친환경 물류",
        r"폐기물",
        r"자원순환",
        r"폐기물 감량",
        r"순환경제",
        r"녹색구매",
        r"환경교육",
        r"임직원 교육",
        r"탄소배출 저감",
        r"온실가스 감축 활동",
        r"친환경 설비",
        r"전력 사용 절감",
        r"LCA",
        r"에코디자인",
        r"공급망 감축",
        r"Scope\s*3\s*감축",
    ],
    "capital_flow": [
        r"환경 관련 투자",
        r"친환경 투자",
        r"기후변화 대응 투자",
        r"탄소중립 투자",
        r"탈탄소 투자",
        r"기후 투자",
        r"녹색 투자",
        r"녹색채권",
        r"Sustainability bond",
        r"환경투자",
        r"설비 투자",
        r"전환 투자",
        r"자본적 지출",
        r"자본지출",
        r"CapEx",
        r"CAPEX",
        r"OPEX",
        r"운영비",
        r"투자 계획",
        r"투자 집행",
        r"탄소가격",
        r"내부탄소가격",
        r"배출권 구매",
        r"배출권 비용",
        r"탄소세",
        r"기후비용",
        r"환경 비용",
        r"투자 현황",
        r"투자 금액",
        r"투자액",
        r"투입 금액",
        r"원 단위",
        r"억원",
        r"백만원",
    ],
    "emissions": [
        r"온실가스 배출량",
        r"온실가스 배출",
        r"온실가스 인벤토리",
        r"배출량 산정",
        r"배출량 집계",
        r"배출 원단위",
        r"배출 집약도",
        r"직접 배출",
        r"간접 배출",
        r"Scope\s*1",
        r"Scope\s*2",
        r"Scope\s*3",
        r"카테고리\s*[1-9]|Category\s*[1-9]",
        r"총배출량",
        r"총 배출량",
        r"기준배출량",
        r"배출계수",
        r"산정 방법",
        r"산정기준",
        r"GHG Protocol",
        r"ISO\s*14064",
        r"ISAE\s*3000",
        r"tCO2eq",
        r"tCO2-eq",
        r"tCO2e",
        r"tCO₂eq",
        r"tCO₂e",
        r"ktCO2e",
        r"MtCO2e",
        r"온실가스 검증",
        r"검증 의견서",
        r"검증의견서",
        r"검증 성명서",
        r"제3자 검증",
        r"외부 검증",
        r"보증 보고서",
        r"Assurance Report",
        r"limited assurance",
        r"reasonable assurance",
        r"검증 기관",
        r"검증 범위",
        r"검증 기준",
        r"현장\s*확인",
        r"현장 검증",
        r"현장 실사",
        r"현장 방문",
    ],
}


# -----------------------------------
# 2) 문맥 필터
# -----------------------------------
CONTEXT_PATTERNS: Dict[str, List[str]] = {
    "board_governance": [
        r"기후",
        r"탄소",
        r"ESG",
        r"환경",
        r"온실가스",
        r"지속가능",
        r"감독",
        r"risk",
        r"리스크",
        r"배출",
    ],
    "internal_actions": [
        r"기후",
        r"탄소",
        r"온실가스",
        r"배출",
        r"에너지",
        r"재생에너지",
        r"저감",
        r"감축",
        r"net zero",
        r"탄소중립",
        r"RE100",
        r"Scope",
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
        r"net zero",
        r"탄소중립",
    ],
}


# -----------------------------------
# 3) 섹션 힌트
# -----------------------------------
SECTION_HINTS: Dict[str, List[str]] = {
    "board_governance": [
        r"ESG 거버넌스",
        r"지배구조",
        r"이사회 구성 및 운영",
        r"이사회 운영",
        r"지속가능경영위원회",
        r"ESG위원회",
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
# 4) 값/단위 패턴
# -----------------------------------
VALUE_PATTERNS: List[str] = [
    r"\b(?:19|20)\d{2}\b",
    r"\d[\d,\.]*\s*(?:tCO2e|tCO2eq|tCO2-eq|tCO₂e|tCO₂eq|kgCO2e|kgCO2eq|천tCO2eq)",
    r"\d[\d,\.]*\s*(?:TJ|GJ|MW|MWh|kWh|%)",
    r"\d[\d,\.]*\s*(?:억\s*원|조\s*원|백만\s*원|백만원|천원|원)",
    r"\bScope\s*[123]\b",
    r"\bRE100\b",
    r"\bPPA\b",
]

SCOPE_PATTERN = r"\bScope\s*[1-3]\b"
HORIZON_PATTERN = r"단기|중기|장기|short[\s-]*term|mid[\s-]*term|long[\s-]*term"
ASSURANCE_PATTERN = r"제3자\s*검증|외부\s*검증|검증\s*의견서|보증\s*보고서|limited assurance|reasonable assurance"
SITE_VERIFICATION_PATTERN = r"현장\s*(?:검증|실사|방문)|site\s*visit"
TARGET_RANGE_PATTERN = r"목표\s*범위|목표범위|적용\s*범위|대상\s*범위|조직\s*경계|운영\s*경계|scope\s*범위"
TARGET_TYPE_PATTERN = r"Net Zero|net zero|탄소중립|탄소 중립|RE100|SBTi"

DETAIL_PATTERNS: Dict[str, str] = {
    "board_governance": r"위원회|의사결정|보고|감독|책임|리스크|전담",
    "carbon_targets": r"목표|감축|기준연도|목표연도|중간목표|단기|중기|장기|범위|scope|로드맵|전환계획|target|baseline",
    "internal_actions": r"감축 활동|이행|에너지|절감|효율|재생에너지|폐기물|자원순환|연료전환|설비|CCUS|메탄|scope 3",
    "capital_flow": r"투자|CapEx|CAPEX|OPEX|비용|집행|지출|배출권|탄소가격|탄소세|녹색채권|금액",
    "emissions": r"배출량|인벤토리|검증|보증|의견서|현장|실사|scope|산정|배출계수|GHG|ISO|ISAE|assurance",
}

NAVIGATION_PATTERN = r"목차|contents|index|table of contents|gri standards.*index"
CARBON_CONTEXT_PATTERN = r"기후|탄소|온실가스|배출|저감|감축|에너지|재생에너지|net zero|탄소중립|scope|ghg"
STRONG_PATTERNS: Dict[str, str] = {
    "board_governance": r"ESG위원회|지속가능경영위원회|기후변화위원회|board oversight|climate governance|TCFD",
    "carbon_targets": r"Net Zero|RE100|SBTi|탄소중립|감축 목표|목표연도|기준연도|Scope\s*[123]",
    "internal_actions": r"재생에너지|PPA|REC|에너지 효율화|연료 전환|CCUS|탄소 포집|배출 저감",
    "capital_flow": r"CapEx|탄소중립 투자|배출권 비용|녹색채권|내부탄소가격",
    "emissions": r"온실가스 배출량|Scope\s*[123]|tCO2|검증 의견서|제3자 검증|Assurance",
}


# -----------------------------------
# 5) 경량화 설정
# -----------------------------------
CONTEXT_LINE_WINDOW = 1
EXPANDED_LINE_WINDOW = 2
MAX_LINES_PER_EXCERPT = 10
MAX_SNIPPETS_PER_EXCERPT = 5
MAX_SNIPPET_CHARS = 260
COMMON_NOISE_PAGE_RATIO = 0.45
COMMON_NOISE_MAX_CHARS = 48


# -----------------------------------
# 6) 유틸
# -----------------------------------
def clean_text(text: str) -> str:
    if text is None:
        return ""
    out = str(text)
    out = out.replace("\xa0", " ")
    out = out.replace("\u200b", " ")
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def clean_line(line: str) -> str:
    line = clean_text(line)
    line = re.sub(r"\s*\|\s*", " | ", line)
    return line.strip()


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def unique_preserve_order(items: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for item in items:
        if not item:
            continue
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def find_matched_keywords(text: str, patterns: Sequence[str]) -> List[str]:
    hits: List[str] = []
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            hits.append(clean_text(m.group(0)))
    return unique_preserve_order(hits)


def find_value_mentions(text: str) -> List[str]:
    values: List[str] = []
    for pattern in VALUE_PATTERNS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            token = clean_text(match.group(0))
            if re.search(r"scope", token, flags=re.IGNORECASE):
                token = normalize_scope(token)
            values.append(token)
    return unique_preserve_order(values)


def has_value(text: str) -> bool:
    for pattern in VALUE_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    return False


def is_detail_line(category: str, text: str) -> bool:
    detail_pattern = DETAIL_PATTERNS.get(category)
    if not detail_pattern:
        return False
    return bool(re.search(detail_pattern, text, flags=re.IGNORECASE))


def is_weak_line(text: str) -> bool:
    if not text:
        return True
    if re.fullmatch(r"\d{1,2}", text):
        return True
    if re.fullmatch(r"[-_/|.·• ]+", text):
        return True
    return False


def is_navigation_line(text: str) -> bool:
    if re.search(NAVIGATION_PATTERN, text, flags=re.IGNORECASE):
        return True
    # 목차 라인은 보통 짧은 숫자 토큰(페이지 번호)이 다수 등장
    if re.search(r"contents|index|목차", text, flags=re.IGNORECASE):
        if len(re.findall(r"\b\d{1,3}\b", text)) >= 2:
            return True
    # 예: "주제명 014 ... 037 ... 112" 형태의 TOC 라인 제거
    if len(re.findall(r"\b\d{3}\b", text)) >= 3:
        if not re.search(r"tCO2|Scope|MWh|kWh|억\s*원|조\s*원|%", text, flags=re.IGNORECASE):
            return True
    # 예: "제3자 검증의견서 113" 같은 목차 엔트리 제거
    if len(text) <= 40 and re.search(r"\s\d{2,3}$", text):
        if not has_value(text):
            return True
    return False


def normalize_horizon(token: str) -> str:
    low = token.lower()
    if "short" in low:
        return "short_term"
    if "mid" in low:
        return "mid_term"
    if "long" in low:
        return "long_term"
    if token == "단기":
        return "short_term"
    if token == "중기":
        return "mid_term"
    if token == "장기":
        return "long_term"
    return token


def normalize_scope(scope_token: str) -> str:
    token = re.sub(r"\s+", " ", scope_token.strip())
    m = re.search(r"([1-3])", token)
    if m:
        return f"Scope {m.group(1)}"
    token = token.lower().replace("scope", "Scope")
    return token


def extract_labeled_years(text: str, label_pattern: str) -> List[int]:
    years: List[int] = []
    pattern = rf"(?:{label_pattern})[\s:：\-]*((?:19|20)\d{{2}})"
    for m in re.finditer(pattern, text, flags=re.IGNORECASE):
        years.append(int(m.group(1)))
    return sorted(set(years))


def match_category_text(category: str, text: str) -> List[str]:
    main_hits = find_matched_keywords(text, CATEGORY_PATTERNS[category])
    section_hits = find_matched_keywords(text, SECTION_HINTS.get(category, []))
    strong_pattern = STRONG_PATTERNS.get(category, "")
    has_strong = bool(strong_pattern and re.search(strong_pattern, text, flags=re.IGNORECASE))
    has_carbon_context = bool(re.search(CARBON_CONTEXT_PATTERN, text, flags=re.IGNORECASE))

    # 오탐 방지용 문맥 필터
    context_patterns = CONTEXT_PATTERNS.get(category)
    if context_patterns and main_hits:
        has_context = any(re.search(p, text, flags=re.IGNORECASE) for p in context_patterns)
        if not has_context and not has_strong and not has_carbon_context:
            main_hits = []

    # 탄소 목표: "연도만 있는 줄" 오탐 제거
    if category == "carbon_targets" and main_hits:
        year_only = set(main_hits).issubset({"2030", "2035", "2040", "2045", "2050"})
        if year_only and not re.search(
            r"탄소|온실가스|기후|RE100|Net Zero|net zero|감축|로드맵|목표|scope",
            text,
            flags=re.IGNORECASE,
            ):
                main_hits = []

    # 이사회/투자/활동 카테고리는 탄소 문맥이 전혀 없으면 제외
    if category in {"board_governance", "internal_actions", "capital_flow"} and main_hits:
        if not has_carbon_context and not has_strong:
            main_hits = []

    # 배출 카테고리는 단위값이나 scope가 있으면 살리고, 아니면 배출/검증 문맥 필요
    if category == "emissions" and main_hits:
        if not has_value(text):
            if not re.search(r"배출|인벤토리|scope|검증|보증|의견서|ghg", text, flags=re.IGNORECASE):
                main_hits = []

    # 누락 방지용 fallback 룰
    if category == "carbon_targets" and not main_hits:
        if has_value(text) and re.search(r"목표|감축|저감|탄소중립|net zero|RE100|SBTi", text, flags=re.IGNORECASE):
            main_hits = ["target_inferred"]

    if category == "emissions" and not main_hits:
        if has_value(text) and re.search(r"배출|scope|인벤토리|검증|보증|tco2|ghg", text, flags=re.IGNORECASE):
            main_hits = ["emission_inferred"]

    return unique_preserve_order(section_hits + main_hits)


def contains_protected_keyword(text: str) -> bool:
    if has_value(text):
        return True
    for category in CATEGORY_PATTERNS:
        if match_category_text(category, text):
            return True
    return False


def detect_common_noise_lines(pages: List[Dict[str, Any]]) -> Set[str]:
    if not pages:
        return set()

    freq: Dict[str, int] = {}
    for page in pages:
        for line in set(page["lines"]):
            if len(line) > COMMON_NOISE_MAX_CHARS:
                continue
            freq[line] = freq.get(line, 0) + 1

    threshold = max(6, int(len(pages) * COMMON_NOISE_PAGE_RATIO))
    noise: Set[str] = set()
    for line, count in freq.items():
        if count < threshold:
            continue
        if contains_protected_keyword(line):
            continue
        noise.add(line)
    return noise


def extract_pages_with_langchain(pdf_path: str) -> List[Dict[str, Any]]:
    loader = PDFPlumberLoader(pdf_path)
    docs = loader.load()

    pages: List[Dict[str, Any]] = []
    for idx, doc in enumerate(docs):
        metadata = doc.metadata or {}
        raw_page = metadata.get("page", idx)
        try:
            page_num = int(raw_page) + 1  # loader는 0-based 페이지 번호를 주는 경우가 많음
        except (TypeError, ValueError):
            page_num = idx + 1

        page_text = clean_text(doc.page_content)
        lines = [clean_line(x) for x in page_text.splitlines()]
        lines = [x for x in lines if not is_weak_line(x) and not is_navigation_line(x)]

        pages.append({
            "page": page_num,
            "text": page_text,
            "lines": lines,
        })

    common_noise = detect_common_noise_lines(pages)
    if common_noise:
        for page in pages:
            page["lines"] = [line for line in page["lines"] if line not in common_noise]

    pages.sort(key=lambda x: x["page"])
    return pages


def score_line(category: str, line: str, keyword_hits: Sequence[str]) -> int:
    score = 0
    if keyword_hits:
        score += 5
    if has_value(line):
        score += 3
    if is_detail_line(category, line):
        score += 2
    if len(line) > 220:
        score -= 1
    return score


def build_snippets(lines: Sequence[str], selected_indices: Sequence[int]) -> List[str]:
    if not selected_indices:
        return []

    sorted_idx = sorted(set(selected_indices))
    groups: List[List[int]] = []
    cur: List[int] = []

    for idx in sorted_idx:
        if not cur:
            cur = [idx]
            continue
        if idx - cur[-1] <= 1:
            cur.append(idx)
        else:
            groups.append(cur)
            cur = [idx]

    if cur:
        groups.append(cur)

    snippets: List[str] = []
    for group in groups:
        merged = " ".join(lines[i] for i in group)
        merged = truncate_text(clean_text(merged), MAX_SNIPPET_CHARS)
        if merged:
            snippets.append(merged)
        if len(snippets) >= MAX_SNIPPETS_PER_EXCERPT:
            break

    return unique_preserve_order(snippets)


def extract_signals(category: str, text: str) -> Dict[str, Any]:
    signals: Dict[str, Any] = {}

    years = sorted({int(x) for x in re.findall(r"\b(?:19|20)\d{2}\b", text)})
    if years:
        signals["years"] = years

    scopes = unique_preserve_order(
        normalize_scope(m.group(0))
        for m in re.finditer(SCOPE_PATTERN, text, flags=re.IGNORECASE)
    )
    if scopes:
        signals["scopes"] = scopes

    if category == "carbon_targets":
        baseline_years = extract_labeled_years(text, r"기준연도|base year|baseline year")
        if baseline_years:
            signals["baseline_years"] = baseline_years

        target_years = extract_labeled_years(text, r"목표연도|target year|달성연도|목표 시점|달성 시점")
        if target_years:
            signals["target_years"] = target_years

        horizons = unique_preserve_order(
            normalize_horizon(m.group(0))
            for m in re.finditer(HORIZON_PATTERN, text, flags=re.IGNORECASE)
        )
        if horizons:
            signals["time_horizons"] = horizons

        target_types = unique_preserve_order(
            m.group(0) for m in re.finditer(TARGET_TYPE_PATTERN, text, flags=re.IGNORECASE)
        )
        if target_types:
            signals["target_types"] = target_types

        target_ranges = unique_preserve_order(
            m.group(0) for m in re.finditer(TARGET_RANGE_PATTERN, text, flags=re.IGNORECASE)
        )
        if target_ranges:
            signals["target_ranges"] = target_ranges

        reduction_rates = unique_preserve_order(re.findall(r"\d[\d,\.]*\s*%", text))
        if reduction_rates:
            signals["reduction_rates"] = reduction_rates

    if category == "emissions":
        inventory_years = extract_labeled_years(text, r"산정연도|보고연도|배출연도|inventory year|reporting year")
        if inventory_years:
            signals["inventory_years"] = inventory_years

        assurance_mentions = unique_preserve_order(
            m.group(0) for m in re.finditer(ASSURANCE_PATTERN, text, flags=re.IGNORECASE)
        )
        if assurance_mentions:
            signals["assurance_mentions"] = assurance_mentions

        if re.search(SITE_VERIFICATION_PATTERN, text, flags=re.IGNORECASE):
            signals["site_verification"] = "mentioned"
        elif re.search(r"검증|보증|의견서", text, flags=re.IGNORECASE):
            signals["site_verification"] = "verification_mentioned"

    return signals


def merge_signals(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, val in extra.items():
        if val is None:
            continue
        if key not in merged:
            merged[key] = val
            continue

        old = merged[key]
        if isinstance(old, list) and isinstance(val, list):
            merged[key] = unique_preserve_order([*old, *val])
            continue
        if isinstance(old, list):
            merged[key] = unique_preserve_order([*old, val])
            continue
        if isinstance(val, list):
            merged[key] = unique_preserve_order([old, *val])
            continue

        if key == "site_verification":
            # 우선순위: mentioned > verification_mentioned
            priority = {"mentioned": 2, "verification_mentioned": 1}
            if priority.get(str(val), 0) > priority.get(str(old), 0):
                merged[key] = val
            continue

        if old != val:
            merged[key] = unique_preserve_order([str(old), str(val)])
    return merged


def merge_values(base_values: Sequence[str], extra_values: Sequence[str]) -> List[str]:
    return unique_preserve_order([*base_values, *extra_values])


def compact_category_records(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    dedup: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    for rec in records:
        text = clean_text(rec.get("text", ""))
        if not text:
            continue
        values = rec.get("values", [])
        signals = rec.get("signals", {})
        if text not in dedup:
            dedup[text] = {
                "text": text,
                "values": unique_preserve_order(values),
                "signals": dict(signals),
            }
            order.append(text)
        else:
            existing = dedup[text]
            existing["values"] = merge_values(existing.get("values", []), values)
            existing["signals"] = merge_signals(existing.get("signals", {}), signals)

    return [dedup[text] for text in order]


def build_category_facts(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    facts: Dict[str, Any] = {}
    years: List[int] = []
    scopes: List[str] = []
    horizons: List[str] = []
    target_types: List[str] = []
    target_ranges: List[str] = []
    reduction_rates: List[str] = []
    baseline_years: List[int] = []
    target_years: List[int] = []
    inventory_years: List[int] = []
    assurance_mentions: List[str] = []
    value_mentions: List[str] = []
    site_status = ""

    for rec in records:
        value_mentions = merge_values(value_mentions, rec.get("values", []))
        signals = rec.get("signals", {}) or {}
        years.extend(signals.get("years", []))
        scopes = merge_values(scopes, signals.get("scopes", []))
        horizons = merge_values(horizons, signals.get("time_horizons", []))
        target_types = merge_values(target_types, signals.get("target_types", []))
        target_ranges = merge_values(target_ranges, signals.get("target_ranges", []))
        reduction_rates = merge_values(reduction_rates, signals.get("reduction_rates", []))
        baseline_years.extend(signals.get("baseline_years", []))
        target_years.extend(signals.get("target_years", []))
        inventory_years.extend(signals.get("inventory_years", []))
        assurance_mentions = merge_values(assurance_mentions, signals.get("assurance_mentions", []))

        current_site = signals.get("site_verification")
        if current_site == "mentioned":
            site_status = "mentioned"
        elif current_site == "verification_mentioned" and site_status != "mentioned":
            site_status = "verification_mentioned"

    if years:
        facts["years"] = sorted(set(int(y) for y in years))
    if scopes:
        facts["scopes"] = scopes
    if baseline_years:
        facts["baseline_years"] = sorted(set(int(y) for y in baseline_years))
    if target_years:
        facts["target_years"] = sorted(set(int(y) for y in target_years))
    if inventory_years:
        facts["inventory_years"] = sorted(set(int(y) for y in inventory_years))
    if horizons:
        facts["time_horizons"] = horizons
    if target_types:
        facts["target_types"] = target_types
    if target_ranges:
        facts["target_ranges"] = target_ranges
    if reduction_rates:
        facts["reduction_rates"] = reduction_rates
    if assurance_mentions:
        facts["assurance_mentions"] = assurance_mentions
    if site_status:
        facts["site_verification"] = site_status
    if value_mentions:
        facts["value_mentions"] = value_mentions

    facts["record_count"] = len(records)
    return facts


def consolidate_page_for_category(lines: Sequence[str], category: str) -> Optional[Dict[str, Any]]:
    if not lines:
        return None

    matched_indices: Set[int] = set()

    for i, line in enumerate(lines):
        hits = match_category_text(category, line)
        if hits:
            matched_indices.add(i)

    if not matched_indices:
        return None

    # 1차: 매칭 라인 주변 최소 문맥
    candidate_indices: Set[int] = set()
    n = len(lines)
    for idx in matched_indices:
        start = max(0, idx - CONTEXT_LINE_WINDOW)
        end = min(n, idx + CONTEXT_LINE_WINDOW + 1)
        candidate_indices.update(range(start, end))

    # 2차: 숫자/목표 세부 정보를 놓치지 않도록 확장
    for idx in matched_indices:
        start = max(0, idx - EXPANDED_LINE_WINDOW)
        end = min(n, idx + EXPANDED_LINE_WINDOW + 1)
        for j in range(start, end):
            line = lines[j]
            if has_value(line) or is_detail_line(category, line):
                candidate_indices.add(j)

    scored: List[Dict[str, Any]] = []
    for idx in sorted(candidate_indices):
        line = lines[idx]
        keyword_hits = match_category_text(category, line)
        if not keyword_hits and not has_value(line) and not is_detail_line(category, line):
            continue
        scored.append({
            "idx": idx,
            "score": score_line(category, line, keyword_hits),
        })

    selected_indices: List[int] = []

    # 매칭 라인을 우선 유지
    for idx in sorted(matched_indices):
        if idx not in selected_indices:
            selected_indices.append(idx)
        if len(selected_indices) >= MAX_LINES_PER_EXCERPT:
            break

    # 점수 기반으로 남은 슬롯 채우기
    if len(selected_indices) < MAX_LINES_PER_EXCERPT:
        for item in sorted(scored, key=lambda x: (-x["score"], x["idx"])):
            idx = item["idx"]
            if idx in selected_indices:
                continue
            selected_indices.append(idx)
            if len(selected_indices) >= MAX_LINES_PER_EXCERPT:
                break

    snippets = build_snippets(lines, selected_indices)
    if not snippets:
        return None

    compact_text = "\n".join(snippets)
    compact_text = clean_text(compact_text)

    # 저신호 excerpt 제거 (목차/색인/약한 힌트 문장)
    if is_navigation_line(compact_text):
        return None

    if category == "carbon_targets":
        has_target_signal = bool(
            re.search(
                r"탄소|온실가스|Net Zero|net zero|RE100|목표|감축|scope|기준연도|목표연도|로드맵",
                compact_text,
                flags=re.IGNORECASE,
            )
        )
        if not has_target_signal:
            return None

    if category == "emissions":
        has_emission_signal = bool(
            re.search(
                r"배출|인벤토리|scope|검증|보증|의견서|tCO2",
                compact_text,
                flags=re.IGNORECASE,
            )
        )
        if not has_emission_signal:
            return None

    return {
        "values": find_value_mentions(compact_text),
        "signals": extract_signals(category, compact_text),
        "text": compact_text,
    }


def classify_hits(pages: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    results: Dict[str, Any] = {
        cat: {"records": [], "facts": {}}
        for cat in CATEGORY_PATTERNS
    }

    for page in pages:
        lines = page["lines"]
        for category in CATEGORY_PATTERNS:
            excerpt = consolidate_page_for_category(lines, category)
            if excerpt:
                results[category]["records"].append({
                    "values": excerpt["values"],
                    "signals": excerpt["signals"],
                    "text": excerpt["text"],
                })

    for category in results:
        compact_records = compact_category_records(results[category]["records"])
        results[category]["records"] = compact_records
        results[category]["facts"] = build_category_facts(compact_records)

    return results


def build_summary(results: Dict[str, Any]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    for category, payload in results.items():
        summary[category] = {
            "record_count": len(payload["records"]),
        }
    return summary


def run(pdf_path: str, output_path: str):
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")

    pages = extract_pages_with_langchain(pdf_path)
    results = classify_hits(pages)
    summary = build_summary(results)

    output = {
        "source_pdf": os.path.abspath(pdf_path),
        "generated_at": datetime.now().isoformat(),
        "summary": summary,
        "categories": results,
    }

    with open(output_path, "w", encoding="utf-8-sig") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[완료] 저장: {output_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="탄소/ESG 관련 PDF 원문 추출기 (LangChain)")
    parser.add_argument("--pdf_path", required=True, help="입력 PDF 경로")
    parser.add_argument(
        "--output",
        default="esg_carbon_extraction.json",
        help="출력 JSON 경로 (default: esg_carbon_extraction.json)",
    )
    args = parser.parse_args()
    run(args.pdf_path, args.output)
