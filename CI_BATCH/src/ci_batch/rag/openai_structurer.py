"""
OpenAI-backed fact structuring for retrieved chunks.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from openai import APIError, OpenAI, RateLimitError

from ci_batch.rag.profiles import FactExtractionProfile


MAX_RETRIES = 4
RETRY_BASE_DELAY = 2.0


SYSTEM_PROMPT = """당신은 지속가능경영보고서에서 DB 적재용 원천 fact를 추출하는 전문가다.
오직 제공된 문서 근거에 기반해 JSON만 출력한다.
추론해서 값을 만들지 않는다.
명시되지 않은 값은 null로 둔다.
동일 사실은 중복 레코드로 반복하지 않는다.
출력 형식은 반드시 {"records": [...]} 이다.
각 record는 다음 키를 가진다:
- fact_payload: 대상 테이블 컬럼만 포함하는 객체
- source_chunk_ids: 근거 chunk id 배열
- source_page_numbers: 근거 페이지 번호 배열
- source_evidence_keys: 근거 evidence key 배열
- source_evidence_excerpt: 핵심 근거 원문 일부
"""


class OpenAIFactStructurer:
    def __init__(self, *, api_key_env: str, model: str) -> None:
        api_key = os.getenv(api_key_env)
        if not api_key:
            raise RuntimeError(f"Environment variable {api_key_env} is required for OpenAI structuring")
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def structure(
        self,
        *,
        profile: FactExtractionProfile,
        schema_section: str,
        target_fields: list[str],
        company_name: str | None,
        report_year: int | None,
        document_key: str,
        retrieved_chunks: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, int]]:
        user_prompt = self._build_user_prompt(
            profile=profile,
            schema_section=schema_section,
            target_fields=target_fields,
            company_name=company_name,
            report_year=report_year,
            document_key=document_key,
            retrieved_chunks=retrieved_chunks,
        )

        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0,
                )
                content = response.choices[0].message.content or '{"records":[]}'
                return (
                    json.loads(content),
                    {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens,
                    },
                )
            except RateLimitError as exc:
                last_error = exc
                time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
            except APIError as exc:
                last_error = exc
                time.sleep(RETRY_BASE_DELAY * (2 ** attempt))

        detail = f": {last_error}" if last_error is not None else ""
        raise RuntimeError(f"OpenAI structuring failed after {MAX_RETRIES} attempts{detail}")

    def _build_user_prompt(
        self,
        *,
        profile: FactExtractionProfile,
        schema_section: str,
        target_fields: list[str],
        company_name: str | None,
        report_year: int | None,
        document_key: str,
        retrieved_chunks: list[dict[str, Any]],
    ) -> str:
        lines = [
            f"# target_table: {profile.table_name}",
            f"# company_name: {company_name or ''}",
            f"# report_year: {report_year or ''}",
            f"# document_key: {document_key}",
            "",
            "## 대상 테이블 스키마",
            schema_section,
            "",
            "## 출력 대상 컬럼",
            json.dumps(target_fields, ensure_ascii=False),
            "",
            "## 추출 규칙",
            f"- 목적: {profile.description}",
            "- fact_payload에는 대상 컬럼만 포함한다.",
            "- company_id, period_id, source_document_id, evidence_id, reg_date, registrar, update_date, updater는 출력하지 않는다.",
            "- data_status는 명시 공시값이면 reported, 추정/가정/대용치면 estimated, 근거가 부족하면 missing으로 둔다.",
            "- 동일 사실의 중복 레코드는 금지한다.",
            "- source_chunk_ids, source_page_numbers, source_evidence_keys는 반드시 근거에 맞게 채운다.",
            "",
            "## 후보 chunk",
        ]

        for index, chunk in enumerate(retrieved_chunks, start=1):
            lines.extend(
                [
                    f"[chunk {index}]",
                    f"chunk_id: {chunk.get('chunk_id')}",
                    f"page_range: {chunk.get('page_start')} - {chunk.get('page_end')}",
                    f"page_keys: {json.dumps(chunk.get('page_keys') or [], ensure_ascii=False)}",
                    f"evidence_keys: {json.dumps(chunk.get('evidence_keys') or [], ensure_ascii=False)}",
                    f"section_hint: {chunk.get('section_hint') or ''}",
                    chunk.get("content") or "",
                    "",
                ]
            )

        if not retrieved_chunks:
            lines.append("관련 chunk가 없습니다. 반드시 {\"records\": []} 를 반환하세요.")

        return "\n".join(lines)
