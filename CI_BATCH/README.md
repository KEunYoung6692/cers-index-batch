# CI_BATCH 설계 문서

본 문서는 [schema.md](/home/on_dev/onjourney/cers-index-batch/CI_BATCH/docs/schema.md)와 함께 관리한다. 스키마 변경사항이나 확정사항이 생기면 이 문서의 구현 범위, 처리 순서, 산출물 계약도 같이 갱신한다.

## 1. 목적

`CI_BATCH`는 연 1회 수집된 기업 지속가능경영보고서 PDF를 입력으로 받아 다음 과정을 수행하는 배치 프로그램이다.

1. 보고서 PDF에서 텍스트를 추출한다.
2. 검색 가능한 단위로 청크를 생성한다.
3. OpenAI API를 사용해 임베딩을 생성한다.
4. 로컬 벡터DB에 저장한다.
5. RAG 기반으로 필요한 구조화 데이터를 추출한다.
6. 최종 업무 DB에 적재 가능한 형태로 정리한다.

현재 단계에서는 DB 스키마가 아직 확정되지 않았으므로, 본 문서는 스키마와 독립적인 공통 설계를 우선 정의한다.

## 2. 범위

### 포함

- 보고서가 저장된 로컬 경로를 입력으로 받는 배치 설계
- `langchain_community` 기반 PDF 텍스트 추출
- 텍스트 정제, 청킹, 임베딩, 벡터 인덱싱
- RAG 기반 구조화 추출 단계 설계
- 최종 DB 적재를 위한 중간 산출물 구조 정의
- 재실행, 부분 재처리, 장애 대응을 고려한 운영 설계

### 제외

- 보고서 다운로드 로직 구현
- 최종 DB 상세 스키마 구현
- 관리자 UI 또는 조회 API
- OCR 중심 고난도 문서 복원

## 3. 스키마 기준 1차 구현 범위

현재 `CI_BATCH`가 직접 책임지는 1차 구현 대상은 다음과 같다.

- Ingestion
  - `data_sources`
  - `documents`
  - `document_pages`
  - `extraction_runs`
  - `extracted_evidence`
- Fact
  - `company_emissions`
  - `company_scope3_categories`
  - `company_financial_metrics`
  - `climate_targets`
  - `climate_capex`
  - `board_climate_governance`
  - `executive_climate_kpi`
  - `assurance_records`
  - `company_cbam_exposure`
  - `company_internal_carbon_price`

초기 구현에서 후순위로 두는 영역은 다음과 같다.

- `companies`, `reporting_periods`, `units` 등 기준정보의 정교한 마스터 동기화
- Methodology 도메인 전체
- Benchmark 도메인 전체
- Scoring 도메인 전체
- `market_carbon_prices` 같은 외부 참조 적재

즉, `CI_BATCH`의 첫 책임은 "문서에서 근거를 추출하고, 스키마에 대응하는 원천값 레코드를 안정적으로 만드는 것"이다.

## 4. 전제 조건

- 보고서 다운로드는 외부 시스템에서 선행 수행한다.
- 배치는 "보고서 파일이 저장된 경로"를 입력받는다.
- `report_year`는 파일명보다 상위 폴더 경로의 연도 정보를 우선 사용한다.
- 파일명 연도 추론은 상위 폴더에 연도 정보가 없을 때만 fallback으로 사용한다.
- OpenAI API를 사용한다.
- `CI_BATCH/.env`가 있으면 해당 파일에서 OpenAI 관련 환경변수를 먼저 로드한다.
- 벡터DB는 로컬 환경에 구성한다.
- 샘플 보고서는 `docs/samples/reports`에 존재한다.
- 1차 버전은 PDF의 텍스트 추출이 가능한 문서를 우선 처리 대상으로 본다.

## 5. 핵심 설계 원칙

### 4.1 벡터DB와 최종 업무 DB는 분리한다

- 벡터DB는 검색과 근거 회수용 저장소다.
- 최종 업무 DB는 정규화된 구조화 레코드 저장소다.
- 벡터DB에 들어간다고 해서 DB 적재가 완료된 것은 아니다.

### 4.2 추출 단계와 구조화 단계는 분리한다

- PDF 추출 결과는 별도 산출물로 저장한다.
- 청크 생성과 임베딩도 별도 산출물로 저장한다.
- DB 스키마가 바뀌어도 `extract -> chunk -> embed`를 재사용할 수 있어야 한다.

### 4.3 재현성과 재실행 가능성을 보장한다

- 모든 실행은 `run_id`, `run_date`, 입력 파일 해시를 남긴다.
- 동일 파일은 중복 적재를 피하고, 필요 시 강제 재처리 옵션을 둔다.
- 파일 단위 실패 격리를 기본으로 한다.

### 4.4 근거 추적성을 보장한다

- 모든 구조화 레코드는 원문 출처를 가져야 한다.
- 최소한 `source_report_id`, `source_pages`, `source_chunk_ids`, `evidence_text`를 남긴다.

### 4.5 DB PK와 별도로 런타임 자연키를 둔다

- 스키마상의 `document_id`, `page_id`, `evidence_id`는 최종 DB 적재 시점에 확정될 수 있다.
- 배치 중간 단계에서는 `document_key`, `page_key`, `evidence_key`, `extraction_key` 같은 안정적인 자연키를 사용한다.
- 이를 통해 DB 적재 전에도 JSONL 산출물, 벡터 인덱스, RAG 결과를 서로 연결할 수 있어야 한다.

## 6. 권장 기술 선택

### 5.1 텍스트 추출

- `langchain_community.document_loaders`
- 1차 기본안: `PDFPlumberLoader`

선정 이유:

- 현재 저장소의 기존 실험 코드와 방향이 맞다.
- 페이지 단위 로딩이 가능하다.
- 표와 본문이 섞여 있는 지속가능경영보고서 처리에 비교적 유연하다.

### 5.2 임베딩/LLM

- 임베딩: OpenAI Embeddings API
- 구조화 추출: OpenAI Chat/Responses 계열 모델

### 5.3 로컬 벡터DB

- 기본 권장안: `Qdrant`

선정 이유:

- 로컬 영속 저장 구조가 명확하다.
- 검색 성능과 메타데이터 필터링이 안정적이다.
- 추후 서버형 전환이 상대적으로 쉽다.

## 7. 전체 처리 흐름

```text
입력 PDF 경로
  -> intake
  -> extract
  -> normalize
  -> chunk
  -> embed
  -> vectordb index
  -> rag retrieve
  -> llm structure
  -> validate
  -> load to DB
```

단계별 설명:

1. `intake`
   입력 PDF 목록 수집, 파일 메타데이터 생성, 실행 manifest 작성
2. `extract`
   PDF에서 페이지 단위 텍스트 추출
3. `normalize`
   노이즈 제거, 공통 메타 정리, 섹션/표 힌트 부여
4. `chunk`
   검색과 RAG에 적합한 청크 생성
5. `embed`
   OpenAI 임베딩 생성
6. `vectordb index`
   로컬 Qdrant에 청크와 메타데이터 적재
7. `rag retrieve`
   스키마별 질의에 필요한 근거 청크 검색
8. `llm structure`
   LLM이 스키마에 맞는 구조화 레코드 생성
9. `validate`
   필수 필드, 타입, 중복, 근거 누락 점검
10. `load to DB`
   staging 적재 후 최종 테이블 upsert

## 8. 배치 논리 구조

```text
CI_BATCH/
  README.md
  docs/
    schema.md
  src/ci_batch/
    contracts/
    jobs/
    intake/
    extract/
    normalize/
    chunk/
    embed/
    vectordb/
    rag/
    load/
    common/
  configs/
    pipeline.yaml
    prompts/
    schemas/
  storage/
    manifests/
    parsed/
    chunks/
    rag/
    load/
    qdrant/
    errors/
  tests/
```

## 9. 모듈 책임

### `jobs/`

- 배치 엔트리포인트
- 연간 전체 실행
- 특정 회사/연도만 재처리
- 특정 단계부터 재실행

예시:

- `run_full_batch.py`
- `reindex_reports.py`
- `rerun_rag.py`

### `intake/`

- 입력 경로 스캔
- PDF 파일 목록 수집
- 회사명, 보고연도 후보 추론
- 파일 해시 계산
- 보고서별 `report_id` 생성

### `extract/`

- LangChain 로더를 통한 PDF 로딩
- 페이지 단위 원문 추출
- 페이지 메타데이터 부여

### `normalize/`

- 헤더/푸터/페이지 번호성 노이즈 제거
- 공통 반복 문구 식별
- 표 유사 페이지, 목차 페이지, 검증의견서 페이지 태깅
- 회사명/연도/언어 보정

### `chunk/`

- 검색용 청크 생성
- 청크 안정 ID 생성
- 청크 메타데이터 구성

### `embed/`

- 배치 임베딩 호출
- 실패 재시도, rate limit 대응
- 토큰/비용/지연시간 기록

### `vectordb/`

- Qdrant collection 생성
- 업서트
- 메타데이터 필터 기반 검색
- 문서 단위 삭제/재색인

### `rag/`

- 스키마별 retrieval query 생성
- 관련 chunk 검색
- LLM 구조화 추출
- evidence 연결

### `load/`

- staging 적재
- schema validation
- dedupe
- 최종 upsert

현재 1차 구현 범위:

- structured fact draft를 테이블별 row payload로 materialize
- 스키마 기준 필수 컬럼 검증
- `ready`, `needs_resolution`, `invalid` 상태 분류
- 테이블별 적재 준비 JSONL 산출물 생성

### `common/`

- 설정 로딩
- 로깅
- run context
- manifest 작성
- 예외/재시도 유틸

### `contracts/`

- 스키마 대응 전 단계의 중간 데이터 계약
- DB PK 확정 전 자연키 정의
- JSONL 산출물 직렬화 규칙
- Ingestion/Fact record 초안 타입 정의

## 10. 입력/출력 계약

### 9.1 입력

- 배치 인자 예시
  - `--input-dir /path/to/reports`
  - `--run-date 2026-03-18`
  - `--company GS건설`
  - `--year 2025`
  - `--from-stage chunk`

### 10.2 보고서 식별자

권장 키:

- `report_id = {company_slug}_{report_year}_{file_hash_prefix}`
- `document_key`는 intake 시점에 고정한다.
- 이후 extract 단계에서 `report_year`가 본문 기준으로 보강되더라도 기존 `document_key`는 바꾸지 않는다.

보조 메타데이터:

- `company_name`
- `report_year`
- `source_path`
- `source_file_name`
- `file_hash`
- `file_size`
- `ingested_at`

중간 처리 자연키:

- `document_key`
- `page_key`
- `extraction_key`
- `evidence_key`

### 10.3 페이지 추출 산출물

저장 위치 예시:

- `storage/parsed/{run_date}/{report_id}/pages.jsonl`

레코드 예시:

```json
{
  "report_id": "gsenc_2025_ab12cd34",
  "company_name": "GS건설",
  "report_year": 2025,
  "page_number": 12,
  "text": "페이지 원문 텍스트",
  "raw_text": "정제 전 원문",
  "section_hint": "온실가스 배출량",
  "table_like": false,
  "toc_like": false
}
```

### 10.4 청크 산출물

저장 위치 예시:

- `storage/chunks/{run_date}/{report_id}/chunks.jsonl`

레코드 예시:

```json
{
  "chunk_id": "gsenc_2025_ab12cd34_p012_c003",
  "report_id": "gsenc_2025_ab12cd34",
  "company_name": "GS건설",
  "report_year": 2025,
  "page_start": 12,
  "page_end": 13,
  "chunk_type": "text",
  "section_hint": "온실가스 배출량",
  "table_like": false,
  "content": "검색 및 RAG에 사용할 청크 본문"
}
```

실제 1차 구현 파일:

- `storage/chunks/{run_date}/{document_key}/normalized_pages.jsonl`
- `storage/chunks/{run_date}/{document_key}/retrieval_chunks.jsonl`

### 10.5 구조화 산출물

저장 위치 예시:

- `storage/rag/{run_date}/{report_id}/{schema_name}.json`

레코드 예시:

```json
{
  "schema_name": "emissions",
  "report_id": "gsenc_2025_ab12cd34",
  "records": [
    {
      "source_pages": [12, 13],
      "source_chunk_ids": ["gsenc_2025_ab12cd34_p012_c003"],
      "evidence_text": "2024년 Scope 1 배출량은 ...",
      "confidence": 0.91
    }
  ]
}
```

### 10.6 적재 준비 산출물

저장 위치 예시:

- `storage/load/{run_date}/{table_name}/rows.jsonl`
- `storage/load/{run_date}/{table_name}/ready_rows.jsonl`
- `storage/load/{run_date}/{table_name}/needs_resolution_rows.jsonl`
- `storage/load/{run_date}/{table_name}/invalid_rows.jsonl`

레코드 예시:

```json
{
  "load_record_key": "e1_unknown_a5464d58_climate_targets_0002",
  "table_name": "climate_targets",
  "load_status": "needs_resolution",
  "row_payload": {
    "company_id": null,
    "period_id": null,
    "target_type": "mid",
    "target_year": 2030,
    "reduction_pct": 30,
    "data_status": "reported",
    "reg_date": "2026-03-18T09:20:00Z",
    "registrar": "ci_batch"
  },
  "missing_required_fields": ["company_id", "period_id"],
  "missing_business_fields": [],
  "missing_reference_fields": ["company_id", "period_id"]
}
```

## 11. 청킹 전략

### 목표

- 검색 정확도와 LLM 입력 효율을 동시에 만족해야 한다.
- 너무 작은 청크는 문맥이 깨지고, 너무 큰 청크는 검색 노이즈가 커진다.

### 권장 기준

- 기본 크기: 약 `800 ~ 1200 tokens`
- overlap: 약 `100 ~ 150 tokens`
- 페이지 경계는 존중하되, 의미상 연결된 문단은 일부 병합 허용

### 청크 유형

- `text`
- `table_like`
- `appendix`
- `assurance`
- `toc_like`

`toc_like`는 일반 검색 대상에서 제외하거나 낮은 우선순위를 준다.

## 12. RAG 설계 원칙

### 11.1 스키마 독립형 중간 계층을 둔다

최종 DB 스키마가 오기 전까지는 다음을 공통 인터페이스로 유지한다.

- `retrieval query`
- `source chunks`
- `structured draft`
- `validated records`

### 11.2 카테고리 단위 추출을 기본으로 한다

초기 카테고리 예시:

- 온실가스 배출량
- 감축 목표
- 내부 감축 활동
- 기후 관련 투자/비용
- 이사회/거버넌스

### 11.3 모든 결과는 근거와 함께 저장한다

필수 항목:

- `source_pages`
- `source_chunk_ids`
- `evidence_text`
- `confidence`

### 11.4 재구조화 가능해야 한다

- 청크와 벡터 인덱스를 재사용한다.
- 스키마 변경 시 `rag -> validate -> load`만 다시 실행 가능해야 한다.

## 13. 저장소 구조

```text
CI_BATCH/storage/
  manifests/
    run_*.json
  parsed/
    2026-03-18/
      gsenc_2025_ab12cd34/
        pages.jsonl
  chunks/
    2026-03-18/
      gsenc_2025_ab12cd34/
        chunks.jsonl
  rag/
    2026-03-18/
      gsenc_2025_ab12cd34/
        emissions.json
        targets.json
  qdrant/
    collections/
  errors/
    2026-03-18/
      gsenc_2025_ab12cd34.log
```

## 14. 실행 전략

### 13.1 기본 실행 단위

- 배치는 보고서 파일 단위로 처리한다.
- 한 보고서 실패가 전체 실행을 중단시키지 않도록 한다.

### 13.2 재실행 단위

- 전체 실행
- 회사 단위 재처리
- 보고서 단위 재처리
- 특정 단계부터 재실행

### 13.3 권장 실행 순서

1. `intake + extract`
2. `normalize + chunk`
3. `embed + vectordb`
4. `rag + validate`
5. `load`

## 15. 예외 처리 원칙

### 문서 단위 실패 격리

- 특정 PDF 실패 시 해당 파일만 `errors/`에 기록하고 다음 파일로 진행

### 재시도

- OpenAI 호출
- 로컬 벡터DB 일시 오류
- 파일 잠금/쓰기 실패

### 수동 확인 대상 분리

아래 경우는 별도 검토 큐로 보낸다.

- 추출 텍스트가 거의 없는 PDF
- 전 페이지가 이미지로만 구성된 PDF
- 회사명/보고연도 추론 실패
- 구조화 결과가 반복적으로 validation 실패하는 경우

## 16. 로깅 및 운영 지표

필수 로그:

- `run_id`
- `report_id`
- 단계명
- 시작/종료 시각
- 처리 시간
- 예외 메시지
- OpenAI 모델명
- 토큰 사용량
- 재시도 횟수

권장 운영 지표:

- 처리한 PDF 수
- 성공/실패 파일 수
- 파일별 페이지 수
- 추출 문자 수
- 생성 청크 수
- 임베딩 성공/실패 수
- RAG 추출 레코드 수
- validation 실패 수

## 17. 품질 관리 포인트

### 추출 품질

- 페이지별 문자 수 분포 확인
- 지나치게 짧은 페이지 비율 확인
- 반복 헤더/푸터 제거가 과도하지 않은지 확인

### 검색 품질

- 카테고리별 retrieval hit 점검
- 근거 chunk와 실제 정답 페이지 일치 여부 확인

### 구조화 품질

- 동일 값의 중복 레코드 생성 여부
- 연도, 단위, scope 파싱 누락 여부
- 근거 없는 추론성 필드 생성 여부

## 18. 추후 DB 스키마 수신 후 확정할 항목

스키마가 오면 아래를 바로 구체화한다.

1. staging 테이블 구조
2. final 테이블 구조
3. upsert key
4. dedupe 규칙
5. 카테고리별 prompt
6. 필드별 validation 규칙
7. 필수/선택 evidence 규칙

## 19. 1차 구현 우선순위

### Phase 1

- `data_sources`, `documents`, `document_pages`, `extraction_runs`, `extracted_evidence`에 맞는 ingestion 계층 구현
- 입력 스캔
- PDF 텍스트 추출
- 정제
- 청킹
- 임베딩
- 로컬 벡터DB 적재

현재 구현 완료 범위:

- 문서 스캔과 `documents` manifest 생성
- PDF 텍스트 추출과 `document_pages`, `extraction_runs`, `extracted_evidence` 산출물 생성
- 정규화 페이지와 retrieval chunk 생성
- OpenAI 임베딩 + 로컬 Qdrant 인덱싱 코드 뼈대

### Phase 2

- 카테고리별 retrieval
- LLM 구조화
- Fact 테이블 대응 원천값 생성
- validation
- staging 산출물 생성

현재 구현 완료 범위:

- 스키마 테이블별 extraction profile 정의
- schema.md에서 테이블 섹션과 대상 컬럼 자동 파싱
- keyword/vector retrieval 공통 진입점
- Fact draft JSONL 생성용 구조화 job
- Fact draft를 table-ready row payload로 materialize 하는 load job

### Phase 3

- 최종 DB 적재
- 재처리 CLI 고도화
- 운영 지표/모니터링 정비

## 20. 최종 요약

`CI_BATCH`의 핵심은 "PDF를 벡터DB에 넣는 것"이 아니라, 다음 두 계층을 명확히 분리하는 것이다.

- 검색 계층: 추출, 청크, 임베딩, 벡터 인덱스
- 구조화 계층: RAG 검색, LLM 추출, 검증, 최종 DB 적재

이 구조를 따르면 다음이 가능하다.

- 연 1회 대량 배치 처리
- 스키마 변경 후 재구조화
- 특정 보고서만 부분 재처리
- 근거 기반 데이터 적재
- 운영 로그와 재현성 확보

이 문서는 현재 시점의 기준 설계이며, DB 스키마가 전달되면 `rag`와 `load` 설계를 중심으로 2차 상세 설계를 확정한다.
