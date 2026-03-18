# -*- coding: utf-8 -*-
"""
LLM API (OpenAI) 기반 탄소/ESG 정보 구조화 (DB화)

- 입력 : extract_report.py 출력 JSON
- 스키마 : schema/*.md  (추후 추가 예정 → 없으면 generic 모드로 동작)
- 출력 : DB 삽입 준비된 구조화 JSON

처리 흐름:
  1) 추출 JSON을 카테고리별로 읽음
  2) 카테고리 + 페이지 청크 단위로 LLM에 전송
  3) LLM이 스키마에 맞춰 레코드를 JSON으로 반환
  4) 청크 결과를 병합 → 최종 저장

스키마 MD 연동:
  - schema_path 에 있는 MD 파일을 읽어 시스템 프롬프트에 삽입
  - MD가 없으면 generic 프롬프트(탄소/ESG 주요 수치 추출)로 동작
  - MD 추가 후 재실행만으로 적용됨

사용법:
  python3 llm_structurer.py \
    --input  esg_carbon_extraction.json \
    --output esg_structured.json \
    [--schema  schema/schema.md] \
    [--model   gpt-4o-mini] \
    [--chunk-pages 8] \
    [--categories emissions carbon_targets]
"""

import os
import sys
import re
import json
import time
import argparse
import logging
from copy import deepcopy
from pathlib import Path
from datetime import datetime
from typing import Optional

from openai import OpenAI, RateLimitError, APIError


# -----------------------------------
# 기본 설정
# -----------------------------------
DEFAULT_MODEL        = "gpt-4o-mini"
DEFAULT_CHUNK_PAGES  = 8      # 한 번 API 호출 시 처리할 페이지 수
DEFAULT_SCHEMA_PATH  = os.path.join(os.path.dirname(__file__), "..", "schema", "schema.md")
MAX_RETRIES          = 4
RETRY_BASE_DELAY     = 2.0    # seconds (지수 백오프)

# 전체 카테고리 순서
ALL_CATEGORIES = [
    "emissions",
    "carbon_targets",
    "capital_flow",
    "board_governance",
    "internal_actions",
]

# 카테고리 한글명
CATEGORY_LABELS = {
    "board_governance": "이사회 / ESG 거버넌스",
    "carbon_targets":   "탄소중립 목표 / 감축 계획",
    "internal_actions": "내부 저감 활동 / 재생에너지",
    "capital_flow":     "환경 투자 / CapEx / 배출권 비용",
    "emissions":        "온실가스 배출량 (Scope 1·2·3)",
}


# -----------------------------------
# 로깅
# -----------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# -----------------------------------
# 1) 스키마 로딩
# -----------------------------------
def load_schema(schema_path: str) -> Optional[str]:
    """
    스키마 MD 파일을 읽어 반환.
    파일이 없으면 None 반환 → generic 모드로 동작.
    """
    path = Path(schema_path)
    if not path.exists():
        log.warning(f"스키마 파일 없음: {schema_path} → generic 모드로 실행")
        return None
    log.info(f"스키마 로드: {schema_path}")
    return path.read_text(encoding="utf-8")


# -----------------------------------
# 2) 시스템 프롬프트 구성
# -----------------------------------
GENERIC_SCHEMA_PROMPT = """
다음은 ESG / 탄소 관련 보고서에서 추출한 텍스트입니다.
각 카테고리의 내용을 읽고, 탄소 배출 DB화에 필요한 핵심 정보를 JSON 배열로 추출하세요.

[일반 추출 기준]
- 수치(배출량, 목표값, 투자금액 등)는 원문 그대로 포함
- 연도 정보가 있으면 반드시 포함
- 근거 페이지 번호(source_pages) 포함
- 불확실하거나 추론이 필요한 경우 해당 필드를 null 처리
- 중복 레코드 생성 금지 (같은 내용이 여러 페이지에 걸쳐 있을 경우 통합)
""".strip()


def build_system_prompt(schema_text: Optional[str]) -> str:
    base = (
        "당신은 ESG 보고서 데이터를 구조화된 JSON으로 변환하는 전문가입니다.\n"
        "주어진 텍스트에서 지시에 따라 정확히 JSON만 출력하세요. "
        "설명, 주석, 마크다운 코드블록 없이 순수 JSON 배열만 반환합니다.\n\n"
    )

    if schema_text:
        return base + "=== DB 스키마 ===\n" + schema_text
    else:
        return base + GENERIC_SCHEMA_PROMPT


# -----------------------------------
# 3) 사용자 프롬프트 구성
# -----------------------------------
def format_excerpts(excerpts: list) -> str:
    """page_excerpts 리스트를 LLM 입력용 텍스트로 직렬화."""
    parts = []
    for ex in excerpts:
        header = f"[페이지 {ex['page']}]"
        if ex.get("keywords"):
            header += f"  키워드: {', '.join(ex['keywords'][:5])}"
        if ex.get("values"):
            header += f"  수치: {', '.join(str(v) for v in ex['values'][:8])}"
        parts.append(header + "\n" + ex["text"])
    return "\n\n---\n\n".join(parts)


def format_tables(tables: list) -> str:
    """table_hits 리스트를 LLM 입력용 텍스트로 직렬화."""
    parts = []
    for tbl in tables:
        header = f"[표 | 페이지 {tbl['page']} / 표#{tbl['table_index']}]"
        if tbl.get("keywords"):
            header += f"  키워드: {', '.join(tbl['keywords'][:5])}"
        if tbl.get("values"):
            header += f"  수치: {', '.join(str(v) for v in tbl['values'][:8])}"
        rows_text = "\n".join(" | ".join(cell for cell in row) for row in tbl["rows"])
        parts.append(header + "\n" + rows_text)
    return "\n\n---\n\n".join(parts)


def build_user_prompt(
    category: str,
    excerpts: list,
    tables: list,
    source_pdf: str,
    schema_text: Optional[str],
    chunk_index: int,
    total_chunks: int,
) -> str:
    label = CATEGORY_LABELS.get(category, category)
    lines = [
        f"# 카테고리: {label}  ({category})",
        f"# 보고서: {os.path.basename(source_pdf)}",
        f"# 청크: {chunk_index + 1} / {total_chunks}",
        "",
    ]

    if excerpts:
        lines.append("## 본문 발췌")
        lines.append(format_excerpts(excerpts))

    if tables:
        lines.append("\n## 표 데이터")
        lines.append(format_tables(tables))

    # 스키마가 없을 때는 출력 형식 힌트 추가
    if not schema_text:
        lines.append(
            "\n## 출력 지침\n"
            "위 내용에서 DB 저장에 필요한 구조화된 레코드를 JSON 배열로 반환하세요.\n"
            "각 레코드에는 반드시 source_pages(관련 페이지 번호 배열) 필드를 포함하세요.\n"
            "빈 경우 [] 반환."
        )
    else:
        lines.append(
            "\n## 출력 지침\n"
            "스키마에 정의된 필드에 맞게 JSON 배열을 반환하세요.\n"
            "각 레코드에 source_pages(관련 페이지 번호 배열) 필드를 포함하세요.\n"
            "빈 경우 [] 반환."
        )

    return "\n".join(lines)


# -----------------------------------
# 4) OpenAI 호출 (재시도 포함)
# -----------------------------------
def call_llm(
    client: OpenAI,
    messages: list,
    model: str,
) -> tuple[str, dict]:
    """
    OpenAI Chat Completion 호출.
    반환: (content_str, usage_dict)
    """
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0,
            )
            content = resp.choices[0].message.content or "[]"
            usage = {
                "prompt_tokens":     resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
                "total_tokens":      resp.usage.total_tokens,
            }
            return content, usage

        except RateLimitError as e:
            wait = RETRY_BASE_DELAY * (2 ** attempt)
            log.warning(f"Rate limit – {wait:.0f}s 후 재시도 ({attempt+1}/{MAX_RETRIES}): {e}")
            time.sleep(wait)

        except APIError as e:
            wait = RETRY_BASE_DELAY * (2 ** attempt)
            log.warning(f"API 오류 – {wait:.0f}s 후 재시도 ({attempt+1}/{MAX_RETRIES}): {e}")
            time.sleep(wait)

    raise RuntimeError(f"OpenAI 호출 {MAX_RETRIES}회 실패")


def parse_llm_json(content: str) -> list:
    """
    LLM 응답 문자열에서 JSON 배열을 파싱.
    - {"records": [...]} 형태도 처리
    - 최상위가 배열이거나, 배열을 포함한 단일 키 dict 허용
    """
    try:
        obj = json.loads(content)
    except json.JSONDecodeError as e:
        log.error(f"JSON 파싱 실패: {e}\n응답 앞부분: {content[:300]}")
        return []

    if isinstance(obj, list):
        return obj

    if isinstance(obj, dict):
        # 배열 값을 가진 첫 번째 키 탐색
        for v in obj.values():
            if isinstance(v, list):
                return v
        # 단일 레코드 dict인 경우 리스트로 감쌈
        return [obj] if obj else []

    return []


# -----------------------------------
# 5) 청크 단위 처리
# -----------------------------------
def chunk_list(lst: list, size: int) -> list:
    return [lst[i: i + size] for i in range(0, len(lst), size)]


def get_tables_for_pages(tables: list, pages: set) -> list:
    """주어진 페이지 번호 집합에 속하는 표만 반환."""
    return [t for t in tables if t["page"] in pages]


def process_category(
    client: OpenAI,
    category: str,
    cat_data: dict,
    source_pdf: str,
    schema_text: Optional[str],
    model: str,
    chunk_pages: int,
) -> tuple[list, dict]:
    """
    카테고리 전체를 청크로 나눠 LLM 처리.
    반환: (records_list, usage_summary)
    """
    excerpts = cat_data.get("page_excerpts", [])
    tables   = cat_data.get("table_hits", [])

    if not excerpts and not tables:
        log.info(f"  [{category}] 데이터 없음 – 건너뜀")
        return [], {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # 표는 관련 excerpt 페이지에 맞춰 청크와 함께 처리
    # 표 전용(excerpt 미포함 페이지) 처리를 위해 excerpt가 없으면 더미 청크 사용
    if excerpts:
        excerpt_chunks = chunk_list(excerpts, chunk_pages)
    else:
        excerpt_chunks = [[]]   # 표만 있는 경우

    total_chunks = len(excerpt_chunks)
    system_prompt = build_system_prompt(schema_text)
    all_records   = []
    total_usage   = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    for idx, chunk_excerpts in enumerate(excerpt_chunks):
        # 이 청크에 해당하는 페이지 범위의 표 포함
        chunk_pages_set = {ex["page"] for ex in chunk_excerpts}

        # 마지막 청크에서 남은 표도 처리
        if idx == total_chunks - 1:
            covered_pages = {ex["page"] for chunks in excerpt_chunks[:idx+1] for ex in chunks}
            chunk_tables  = [t for t in tables if t["page"] not in (covered_pages - chunk_pages_set)]
        else:
            chunk_tables = get_tables_for_pages(tables, chunk_pages_set)

        user_prompt = build_user_prompt(
            category=category,
            excerpts=chunk_excerpts,
            tables=chunk_tables,
            source_pdf=source_pdf,
            schema_text=schema_text,
            chunk_index=idx,
            total_chunks=total_chunks,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ]

        log.info(
            f"  [{category}] 청크 {idx+1}/{total_chunks} "
            f"(페이지 {[e['page'] for e in chunk_excerpts]}, 표 {len(chunk_tables)}개)"
        )

        content, usage = call_llm(client, messages, model)
        records = parse_llm_json(content)
        all_records.extend(records)

        for k in total_usage:
            total_usage[k] += usage[k]

        log.info(
            f"    → {len(records)}개 레코드 | "
            f"토큰: {usage['prompt_tokens']}+{usage['completion_tokens']}={usage['total_tokens']}"
        )

    return all_records, total_usage


# -----------------------------------
# 6) 비용 추정 (gpt-4o-mini 기준 참고용)
# -----------------------------------
PRICE_PER_1K = {
    "gpt-4o":       {"input": 0.005,   "output": 0.015},
    "gpt-4o-mini":  {"input": 0.00015, "output": 0.0006},
    "gpt-4-turbo":  {"input": 0.01,    "output": 0.03},
}

def estimate_cost(model: str, total_usage: dict) -> str:
    price = PRICE_PER_1K.get(model)
    if not price:
        return "비용 정보 없음"
    cost = (total_usage["prompt_tokens"]     / 1000 * price["input"]
          + total_usage["completion_tokens"] / 1000 * price["output"])
    return f"${cost:.4f} (추정)"


# -----------------------------------
# 7) 실행 진입점
# -----------------------------------
def run(
    input_path: str,
    output_path: str,
    schema_path: str,
    model: str,
    chunk_pages: int,
    categories: Optional[list],
):
    # --- 입력 로드 ---
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"추출 JSON 없음: {input_path}")

    with open(input_path, encoding="utf-8-sig") as f:
        extracted = json.load(f)

    source_pdf = extracted.get("source_pdf", input_path)
    log.info(f"입력 파일: {input_path}")
    log.info(f"보고서  : {os.path.basename(source_pdf)}")

    # --- 스키마 로드 ---
    schema_text = load_schema(schema_path)

    # --- OpenAI 클라이언트 ---
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("환경변수 OPENAI_API_KEY 가 설정되지 않았습니다.")
    client = OpenAI(api_key=api_key)

    # --- 처리할 카테고리 결정 ---
    target_categories = categories if categories else ALL_CATEGORIES
    cat_data_map = extracted.get("categories", {})

    all_results = {}
    grand_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # --- 카테고리별 처리 ---
    for category in target_categories:
        if category not in cat_data_map:
            log.warning(f"[{category}] 추출 데이터 없음 – 건너뜀")
            continue

        log.info(f"▶ 카테고리 처리 시작: {category} ({CATEGORY_LABELS.get(category, '')})")
        records, usage = process_category(
            client=client,
            category=category,
            cat_data=cat_data_map[category],
            source_pdf=source_pdf,
            schema_text=schema_text,
            model=model,
            chunk_pages=chunk_pages,
        )
        all_results[category] = records

        for k in grand_usage:
            grand_usage[k] += usage[k]

        log.info(f"  완료: {len(records)}개 레코드")

    # --- 출력 저장 ---
    output = {
        "source_pdf":     source_pdf,
        "generated_at":   datetime.now().isoformat(),
        "model":          model,
        "schema_used":    schema_path if schema_text else None,
        "usage":          grand_usage,
        "estimated_cost": estimate_cost(model, grand_usage),
        "records":        all_results,
    }

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8-sig") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    log.info(f"[완료] 저장: {output_path}")
    log.info(
        f"총 토큰: {grand_usage['prompt_tokens']}+{grand_usage['completion_tokens']}"
        f"={grand_usage['total_tokens']}  |  비용 {estimate_cost(model, grand_usage)}"
    )

    # 레코드 수 요약
    print("\n=== 레코드 요약 ===")
    for cat, recs in all_results.items():
        print(f"  {cat:20s}: {len(recs):4d}개")


# -----------------------------------
# 8) CLI
# -----------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="LLM(OpenAI)으로 ESG 추출 JSON을 DB 레코드로 구조화"
    )
    parser.add_argument(
        "--input",
        required=True,
        help="extract_report.py 출력 JSON 경로",
    )
    parser.add_argument(
        "--output",
        default="esg_structured.json",
        help="출력 JSON 경로 (default: esg_structured.json)",
    )
    parser.add_argument(
        "--schema",
        default=DEFAULT_SCHEMA_PATH,
        help=f"스키마 MD 파일 경로 (default: {DEFAULT_SCHEMA_PATH})",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenAI 모델 (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--chunk-pages",
        type=int,
        default=DEFAULT_CHUNK_PAGES,
        help=f"한 번 API 호출 시 처리할 페이지 수 (default: {DEFAULT_CHUNK_PAGES})",
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        choices=ALL_CATEGORIES,
        default=None,
        help="처리할 카테고리 지정 (기본: 전체). 예: --categories emissions carbon_targets",
    )

    args = parser.parse_args()

    run(
        input_path=args.input,
        output_path=args.output,
        schema_path=args.schema,
        model=args.model,
        chunk_pages=args.chunk_pages,
        categories=args.categories,
    )

