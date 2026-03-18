# CERs Index DB Schema
> 기준 문서: `CERs_DB_Schema_Dictionary_v2_reviewed.xlsx` 기반 재정리 + 후속 합의사항 반영
## 반영된 후속 합의사항
- `companies.status` 추가: 허용값은 `active`, `inactive`, `split`, `merged`
- `company_status_history` 신규 추가
- 모든 `created_at/create_at` 컬럼은 `reg_date`, `registrar`로 변경
- `created_at/create_at`와 `updated_at/update_at`가 함께 있던 테이블은 `reg_date`, `registrar`, `update_date`, `updater`로 변경
- 본 문서는 프로젝트 참조용 Markdown 스키마 문서입니다.
## 공통 메타데이터 컬럼 표준
| 컬럼명 | 타입 | Nullable | 설명 |
|---|---|---|---|
| reg_date | TIMESTAMP | N | 레코드 최초 등록 일시 |
| registrar | VARCHAR(100) | N | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |
| update_date | TIMESTAMP | Y | 레코드 최종 수정 일시 |
| updater | VARCHAR(100) | Y | 레코드를 마지막으로 수정한 주체(사용자, 시스템, 배치명 등) |
## 테이블 목록
| Domain | Table | Purpose | Row Grain |
|---|---|---|---|
| Master | `companies` | 기업 기본 식별 및 분류 정보를 저장합니다. | 기업 1개당 1행 |
| Master | `company_status_history` | 회사의 현재 상태 외 상세 상태 변경 이력과 연관 회사 정보를 저장합니다. | 회사 상태 이력 1건당 1행 |
| Master | `sectors` | 상위 섹터 분류 마스터입니다. | 섹터 1개당 1행 |
| Master | `industries` | 세부 산업 분류 마스터입니다. | 산업 1개당 1행 |
| Master | `units` | 측정 단위 마스터입니다. | 단위 1개당 1행 |
| Master | `reporting_periods` | 기업별 보고 기간을 관리합니다. | 기업-회계연도 1개당 1행 |
| Ingestion | `data_sources` | 원천 수집 채널 또는 제공기관을 관리합니다. | 원천 소스 1개당 1행 |
| Ingestion | `documents` | 수집된 보고서/PDF 파일 메타데이터를 저장합니다. | 문서 1개당 1행 |
| Ingestion | `document_pages` | 문서 페이지 단위의 텍스트를 저장합니다. | 문서 페이지 1개당 1행 |
| Ingestion | `extraction_runs` | 문서 추출 배치 실행 이력을 저장합니다. | 문서-추출실행 1개당 1행 |
| Ingestion | `extracted_evidence` | PDF에서 추출한 근거 블록을 저장합니다. 토글/수식 블록 구분용 필드를 포함합니다. | 추출 블록 1개당 1행 |
| Methodology | `methodology_versions` | 평가 방법론 버전을 관리합니다. | 방법론 버전 1개당 1행 |
| Methodology | `score_categories` | 평가 대분류(Cat1~Cat4)를 관리합니다. | 카테고리 1개당 1행 |
| Methodology | `score_variables` | 방법론 버전별 변수 사전을 관리합니다. | 방법론 버전-변수 1개당 1행 |
| Methodology | `methodology_parameters` | 수식 상수·가중치·임계치를 버전별로 관리합니다. | 방법론 파라미터 1개당 1행 |
| Methodology | `methodology_toggles` | 문서 내 토글형 설명 블록(AHP/EWM, DQS, GV 등)을 메타데이터로 관리합니다. | 토글 정의 1개당 1행 |
| Methodology | `regulatory_parameters` | 연도별 CBAM factor 등 제도 파라미터를 관리합니다. | 제도 파라미터 1개당 1행 |
| Fact | `company_emissions` | 기업별 온실가스 원천 배출량을 저장합니다. | 기업-기간-배출범위 1개당 1행 |
| Fact | `company_scope3_categories` | 기업별 Scope 3 카테고리 및 데이터 품질 입력값을 저장합니다. | 기업-기간-카테고리 1개당 1행 |
| Fact | `company_financial_metrics` | 기업별 재무 지표 원천값을 저장합니다. | 기업-기간-지표 1개당 1행 |
| Fact | `climate_targets` | 기업별 단·중·장기 및 넷제로 목표 입력값을 저장합니다. | 기업-기간-목표 1개당 1행 |
| Fact | `climate_capex` | 기업별 녹색/전환 CapEx 입력값을 저장합니다. | 기업-기간 1개당 1행 |
| Fact | `board_climate_governance` | 이사회 차원의 기후 감독 및 위원회 정보를 저장합니다. | 기업-기간 1개당 1행 |
| Fact | `executive_climate_kpi` | 경영진 보상과 기후 KPI 연계 정보를 저장합니다. | 기업-기간 1개당 1행 |
| Fact | `assurance_records` | 배출량/공시 데이터에 대한 제3자 검증 및 보증 정보를 저장합니다. | 기업-기간-보증범위 1개당 1행 |
| Fact | `company_cbam_exposure` | CBAM 대상 수출량 및 내재배출량 입력값을 저장합니다. | 기업-기간-품목 1개당 1행 |
| Fact | `market_carbon_prices` | 시장 탄소가격 시계열을 저장합니다. | 시장-일자 1개당 1행 |
| Fact | `company_internal_carbon_price` | 기업의 내부 탄소가격(ICP) 실효성 입력값을 저장합니다. | 기업-기간 1개당 1행 |
| Benchmark | `industry_pathways` | 산업별 감축 경로(LARR/SDA)를 관리합니다. | 산업-버전-구간 1개당 1행 |
| Benchmark | `industry_intensity_benchmarks` | 산업별 탄소집약도 비교 분포를 저장합니다. | 산업-기간-지표 1개당 1행 |
| Benchmark | `industry_material_scope3_categories` | 산업별 중대 Scope 3 카테고리를 관리합니다. | 산업-카테고리 1개당 1행 |
| Benchmark | `industry_green_capex_targets` | 산업별 목표 녹색 CapEx 비율을 관리합니다. | 산업-기간 1개당 1행 |
| Scoring | `scoring_runs` | 기업별 스코어링 실행 이력을 저장합니다. | 기업-기간-실행 1개당 1행 |
| Scoring | `variable_input_snapshots` | 각 변수 계산 시 사용한 입력 스냅샷을 저장합니다. | 스코어링-변수 1개당 1행 |
| Scoring | `variable_scores` | 변수별 계산 결과와 가중치를 저장합니다. | 스코어링-변수 1개당 1행 |
| Scoring | `category_scores` | 카테고리별 점수와 가중 반영값을 저장합니다. | 스코어링-카테고리 1개당 1행 |
| Scoring | `risk_adjustments` | CEF, GV 등 외생 리스크 조정값을 저장합니다. | 스코어링-조정항 1개당 1행 |
| Scoring | `final_scores` | 기초점수, 조정항, 최종점수를 저장합니다. | 스코어링 실행 1개당 1행 |

## Master

### `companies`
- 목적: 기업 기본 식별 및 분류 정보를 저장합니다.
- 행 단위: 기업 1개당 1행
- 배치 단계: 기준정보

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `company_id` | BIGINT | N | PK | 기업 식별자 |
| `company_name_kr` | VARCHAR(200) | N |  | 기업 한글명 |
| `company_name_en` | VARCHAR(200) | Y |  | 기업 영문명 |
| `stock_code` | VARCHAR(50) | Y |  | 종목코드 또는 티커 |
| `country_code` | CHAR(2) | Y |  | 국가 코드(ISO 3166-1 alpha-2 권장) |
| `market_type` | VARCHAR(50) | Y |  | 상장시장 또는 구분(KOSPI, KOSDAQ 등) |
| `sector_id` | BIGINT | Y | FK | 상위 섹터 참조 |
| `industry_id` | BIGINT | Y | FK | 세부 산업 참조 |
| `fiscal_year_end` | VARCHAR(5) | Y |  | 결산월일(MM-DD) |
| `status` | VARCHAR(20) | N |  | 회사 현재 상태. 허용값: active, inactive, split, merged |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |
| `update_date` | TIMESTAMP | Y |  | 레코드 최종 수정 일시 |
| `updater` | VARCHAR(100) | Y |  | 레코드를 마지막으로 수정한 주체(사용자, 시스템, 배치명 등) |

### `company_status_history`
- 목적: 회사의 현재 상태 외 상세 상태 변경 이력과 연관 회사 정보를 저장합니다.
- 행 단위: 회사 상태 이력 1건당 1행
- 배치 단계: 기준정보

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `company_status_history_id` | BIGINT | N | PK | 회사 상태 이력 레코드의 고유 식별자 |
| `company_id` | BIGINT | N | FK | 상태 이력이 속한 회사 식별자. companies.company_id 참조 |
| `status` | VARCHAR(20) | N |  | 해당 이력 시점의 회사 상태. 허용값: active, inactive, split, merged |
| `event_type` | VARCHAR(100) | Y |  | 상태 변경의 상세 사건 유형(예: spin_off, absorbed, merged_into_parent, business_shutdown) |
| `effective_from` | DATE | N |  | 해당 상태의 효력 시작일 |
| `effective_to` | DATE | Y |  | 해당 상태의 효력 종료일. 현재도 유효하면 NULL |
| `related_company_id` | BIGINT | Y | FK | 합병·분할 등으로 직접 연관된 상대 회사 식별자. companies.company_id 참조 |
| `reason` | TEXT | Y |  | 상태 변경 사유 설명 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |
| `note` | TEXT | Y |  | 추가 메모 또는 보충 설명 |

### `sectors`
- 목적: 상위 섹터 분류 마스터입니다.
- 행 단위: 섹터 1개당 1행
- 배치 단계: 기준정보

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `sector_id` | BIGINT | N | PK | 상위 섹터 식별자 |
| `sector_code` | VARCHAR(50) | Y |  | 섹터 코드 |
| `sector_name` | VARCHAR(200) | N |  | 섹터명 |
| `source_standard` | VARCHAR(100) | Y |  | 분류 체계명(GICS 등) |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |
| `update_date` | TIMESTAMP | Y |  | 레코드 최종 수정 일시 |
| `updater` | VARCHAR(100) | Y |  | 레코드를 마지막으로 수정한 주체(사용자, 시스템, 배치명 등) |

### `industries`
- 목적: 세부 산업 분류 마스터입니다.
- 행 단위: 산업 1개당 1행
- 배치 단계: 기준정보

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `industry_id` | BIGINT | N | PK | 세부 산업 식별자 |
| `sector_id` | BIGINT | N | FK | 상위 섹터 참조 |
| `industry_code` | VARCHAR(50) | Y |  | 산업 코드 |
| `industry_name` | VARCHAR(200) | N |  | 산업명 |
| `source_standard` | VARCHAR(100) | Y |  | 분류 체계명(GICS 등) |
| `level_no` | SMALLINT | Y |  | 분류 단계 레벨 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |
| `update_date` | TIMESTAMP | Y |  | 레코드 최종 수정 일시 |
| `updater` | VARCHAR(100) | Y |  | 레코드를 마지막으로 수정한 주체(사용자, 시스템, 배치명 등) |

### `units`
- 목적: 측정 단위 마스터입니다.
- 행 단위: 단위 1개당 1행
- 배치 단계: 기준정보

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `unit_id` | BIGINT | N | PK | 단위 식별자 |
| `unit_code` | VARCHAR(50) | N |  | 단위 코드(tCO2e, KRW, %, ton 등) |
| `unit_name` | VARCHAR(100) | N |  | 단위명 |
| `unit_category` | VARCHAR(50) | Y |  | 단위 분류(질량, 통화, 비율 등) |
| `conversion_basis` | VARCHAR(200) | Y |  | 환산 기준 또는 메모 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

### `reporting_periods`
- 목적: 기업별 보고 기간을 관리합니다.
- 행 단위: 기업-회계연도 1개당 1행
- 배치 단계: 기준정보

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `period_id` | BIGINT | N | PK | 보고기간 식별자 |
| `company_id` | BIGINT | N | FK | 기업 참조 |
| `fiscal_year` | INTEGER | N |  | 회계연도 |
| `start_date` | DATE | Y |  | 보고기간 시작일 |
| `end_date` | DATE | Y |  | 보고기간 종료일 |
| `label` | VARCHAR(100) | Y |  | 표시용 라벨(예: FY2025) |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |
| `update_date` | TIMESTAMP | Y |  | 레코드 최종 수정 일시 |
| `updater` | VARCHAR(100) | Y |  | 레코드를 마지막으로 수정한 주체(사용자, 시스템, 배치명 등) |

## Ingestion

### `data_sources`
- 목적: 원천 수집 채널 또는 제공기관을 관리합니다.
- 행 단위: 원천 소스 1개당 1행
- 배치 단계: 수집/추출

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `source_id` | BIGINT | N | PK | 원천 소스 식별자 |
| `source_type` | VARCHAR(50) | N |  | 원천 유형(pdf, api, web, manual 등) |
| `source_name` | VARCHAR(200) | N |  | 원천 소스명 |
| `provider_name` | VARCHAR(200) | Y |  | 제공기관명 |
| `source_url` | TEXT | Y |  | 원천 URL 또는 참조 경로 |
| `license_note` | TEXT | Y |  | 이용 조건 또는 라이선스 메모 |
| `refresh_frequency` | VARCHAR(50) | Y |  | 갱신 주기 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

### `documents`
- 목적: 수집된 보고서/PDF 파일 메타데이터를 저장합니다.
- 행 단위: 문서 1개당 1행
- 배치 단계: 수집/추출

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `document_id` | BIGINT | N | PK | 문서 식별자 |
| `company_id` | BIGINT | Y | FK | 기업 참조 |
| `source_id` | BIGINT | N | FK | 원천 소스 참조 |
| `document_type` | VARCHAR(100) | N |  | 문서 유형(sustainability_report 등) |
| `title` | VARCHAR(500) | N |  | 문서 제목 |
| `report_year` | INTEGER | Y |  | 보고 연도 |
| `published_at` | DATE | Y |  | 공시/발행일 |
| `file_path` | TEXT | Y |  | 저장 경로 또는 파일 위치 |
| `file_hash` | VARCHAR(128) | Y |  | 파일 해시값 |
| `language` | VARCHAR(20) | Y |  | 문서 언어 |
| `page_count` | INTEGER | Y |  | 문서 페이지 수 |
| `ingestion_status` | VARCHAR(30) | Y |  | 수집 상태 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

### `document_pages`
- 목적: 문서 페이지 단위의 텍스트를 저장합니다.
- 행 단위: 문서 페이지 1개당 1행
- 배치 단계: 수집/추출

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `page_id` | BIGINT | N | PK | 페이지 식별자 |
| `document_id` | BIGINT | N | FK | 문서 참조 |
| `page_no` | INTEGER | N |  | 문서 내 페이지 번호 |
| `raw_text` | TEXT | Y |  | 페이지 원문 텍스트 |
| `ocr_text` | TEXT | Y |  | OCR 보조 텍스트 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

### `extraction_runs`
- 목적: 문서 추출 배치 실행 이력을 저장합니다.
- 행 단위: 문서-추출실행 1개당 1행
- 배치 단계: 수집/추출

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `extraction_run_id` | BIGINT | N | PK | 추출 실행 식별자 |
| `document_id` | BIGINT | N | FK | 문서 참조 |
| `extractor_version` | VARCHAR(100) | N |  | 추출기 버전 |
| `extraction_mode` | VARCHAR(50) | Y |  | 추출 모드(text/table/hybrid 등) |
| `run_started_at` | TIMESTAMP | N |  | 실행 시작 시각 |
| `run_finished_at` | TIMESTAMP | Y |  | 실행 종료 시각 |
| `status` | VARCHAR(30) | N |  | 실행 상태 |
| `error_message` | TEXT | Y |  | 실패 시 오류 메시지 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

### `extracted_evidence`
- 목적: PDF에서 추출한 근거 블록을 저장합니다. 토글/수식 블록 구분용 필드를 포함합니다.
- 행 단위: 추출 블록 1개당 1행
- 배치 단계: 수집/추출

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `evidence_id` | BIGINT | N | PK | 근거 블록 식별자 |
| `extraction_run_id` | BIGINT | N | FK | 추출 실행 참조 |
| `page_id` | BIGINT | N | FK | 페이지 참조 |
| `block_type` | VARCHAR(50) | N |  | 블록 유형(text, table, toggle, formula 등) |
| `section_hint` | VARCHAR(200) | Y |  | 문서 섹션 힌트 |
| `raw_snippet` | TEXT | N |  | 추출 원문 |
| `normalized_snippet` | TEXT | Y |  | 정규화/요약 텍스트 |
| `confidence` | NUMERIC(5,4) | Y |  | 추출 신뢰도 |
| `locator_json` | JSONB | Y |  | 좌표/셀/표 위치 정보 |
| `is_methodology_content` | BOOLEAN | Y |  | 회사 fact가 아닌 방법론/토글 블록 여부 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

## Methodology

### `methodology_versions`
- 목적: 평가 방법론 버전을 관리합니다.
- 행 단위: 방법론 버전 1개당 1행
- 배치 단계: 정규화/스코어링

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `methodology_version_id` | BIGINT | N | PK | 방법론 버전 식별자 |
| `version_name` | VARCHAR(50) | N |  | 버전명(v0.1 등) |
| `source_document_name` | VARCHAR(300) | Y |  | 기준 문서명 |
| `source_document_version` | VARCHAR(100) | Y |  | 기준 문서 버전/개정판 |
| `effective_from` | DATE | N |  | 적용 시작일 |
| `effective_to` | DATE | Y |  | 적용 종료일 |
| `is_active` | BOOLEAN | N |  | 현재 활성 버전 여부 |
| `change_summary` | TEXT | Y |  | 버전 변경 요약 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

### `score_categories`
- 목적: 평가 대분류(Cat1~Cat4)를 관리합니다.
- 행 단위: 카테고리 1개당 1행
- 배치 단계: 정규화/스코어링

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `category_id` | BIGINT | N | PK | 카테고리 식별자 |
| `methodology_version_id` | BIGINT | N | FK | 방법론 버전 참조 |
| `category_code` | VARCHAR(20) | N |  | 카테고리 코드(CAT1 등) |
| `category_name` | VARCHAR(200) | N |  | 카테고리명 |
| `prior_weight` | NUMERIC(8,6) | N |  | 상위 계층 사전 가중치 |
| `display_order` | SMALLINT | N |  | 표시 순서 |
| `description` | TEXT | Y |  | 카테고리 설명 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |
| `update_date` | TIMESTAMP | Y |  | 레코드 최종 수정 일시 |
| `updater` | VARCHAR(100) | Y |  | 레코드를 마지막으로 수정한 주체(사용자, 시스템, 배치명 등) |

### `score_variables`
- 목적: 방법론 버전별 변수 사전을 관리합니다.
- 행 단위: 방법론 버전-변수 1개당 1행
- 배치 단계: 정규화/스코어링

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `variable_id` | BIGINT | N | PK | 변수 식별자 |
| `methodology_version_id` | BIGINT | N | FK | 방법론 버전 참조 |
| `stable_code` | VARCHAR(100) | N |  | 안정 식별 코드(버전 간 유지) |
| `display_code` | VARCHAR(30) | Y |  | 표시용 변수 번호(V1 등) |
| `alt_display_codes` | VARCHAR(100) | Y |  | 문서 내 충돌/대체 표기 보관 |
| `source_section` | VARCHAR(100) | Y |  | 정의 출처 섹션(본문 3.3.1, 수집경로표 등) |
| `category_id` | BIGINT | N | FK | 카테고리 참조 |
| `display_name` | VARCHAR(300) | N |  | 표시용 변수명 |
| `formula_type` | VARCHAR(100) | Y |  | 산식 유형(linear, minmax, penalty 등) |
| `requires_industry_benchmark` | BOOLEAN | N |  | 산업 벤치마크 필요 여부 |
| `requires_manual_review` | BOOLEAN | N |  | 수기 검토 필요 여부 |
| `is_scored` | BOOLEAN | N |  | 해당 버전 총점에 반영되는 변수 여부 |
| `is_experimental` | BOOLEAN | N |  | 실험/후보 변수 여부 |
| `activation_rule` | TEXT | Y |  | 포함/제외 조건 또는 활성화 규칙 |
| `status` | VARCHAR(30) | N |  | 상태(active, draft, deprecated 등) |
| `remarks` | TEXT | Y |  | 비고 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

### `methodology_parameters`
- 목적: 수식 상수·가중치·임계치를 버전별로 관리합니다.
- 행 단위: 방법론 파라미터 1개당 1행
- 배치 단계: 정규화/스코어링

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `parameter_id` | BIGINT | N | PK | 파라미터 식별자 |
| `methodology_version_id` | BIGINT | N | FK | 방법론 버전 참조 |
| `parameter_key` | VARCHAR(100) | N |  | 파라미터 키(tau, lambda, alpha 등) |
| `parameter_value` | NUMERIC(20,8) | Y |  | 파라미터 값 |
| `parameter_data_type` | VARCHAR(30) | N |  | 값 타입(numeric, text, json 등) |
| `unit_code` | VARCHAR(50) | Y |  | 단위 코드 |
| `applies_to_category_id` | BIGINT | Y | FK | 특정 카테고리 전용일 경우 참조 |
| `applies_to_variable_id` | BIGINT | Y | FK | 특정 변수 전용일 경우 참조 |
| `applies_to_industry_id` | BIGINT | Y | FK | 특정 산업 전용일 경우 참조 |
| `effective_from` | DATE | Y |  | 적용 시작일 |
| `description` | TEXT | Y |  | 파라미터 설명 |

### `methodology_toggles`
- 목적: 문서 내 토글형 설명 블록(AHP/EWM, DQS, GV 등)을 메타데이터로 관리합니다.
- 행 단위: 토글 정의 1개당 1행
- 배치 단계: 정규화/스코어링

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `toggle_id` | BIGINT | N | PK | 토글 식별자 |
| `methodology_version_id` | BIGINT | N | FK | 방법론 버전 참조 |
| `toggle_code` | VARCHAR(100) | N |  | 토글 코드(AHP_EWM_NOTE 등) |
| `title` | VARCHAR(300) | N |  | 토글 제목 |
| `description` | TEXT | Y |  | 설명 본문 |
| `affects_scoring_flag` | BOOLEAN | N |  | 점수 계산 규칙에 영향을 주는지 여부 |
| `affects_extraction_flag` | BOOLEAN | N |  | 추출 로직에 영향을 주는지 여부 |
| `storage_rule` | TEXT | Y |  | 회사 fact로 저장하지 않고 메타로 분리하는 규칙 설명 |
| `source_section` | VARCHAR(100) | Y |  | 문서 출처 섹션 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

### `regulatory_parameters`
- 목적: 연도별 CBAM factor 등 제도 파라미터를 관리합니다.
- 행 단위: 제도 파라미터 1개당 1행
- 배치 단계: 정규화/스코어링

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `regulatory_parameter_id` | BIGINT | N | PK | 제도 파라미터 식별자 |
| `regime_code` | VARCHAR(50) | N |  | 제도 코드(CBAM, K_ETS 등) |
| `parameter_key` | VARCHAR(100) | N |  | 파라미터 키(CBAM_FACTOR 등) |
| `parameter_year` | INTEGER | Y |  | 연도 기준 파라미터일 경우 해당 연도 |
| `effective_from` | DATE | Y |  | 적용 시작일 |
| `effective_to` | DATE | Y |  | 적용 종료일 |
| `parameter_value` | NUMERIC(20,8) | N |  | 파라미터 값 |
| `unit_code` | VARCHAR(50) | Y |  | 단위 코드 |
| `source_name` | VARCHAR(200) | Y |  | 출처명 |
| `description` | TEXT | Y |  | 파라미터 설명 |

## Fact

### `company_emissions`
- 목적: 기업별 온실가스 원천 배출량을 저장합니다.
- 행 단위: 기업-기간-배출범위 1개당 1행
- 배치 단계: 원천값 적재

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `emission_id` | BIGINT | N | PK | 배출량 식별자 |
| `company_id` | BIGINT | N | FK | 기업 참조 |
| `period_id` | BIGINT | N | FK | 보고기간 참조 |
| `scope_code` | VARCHAR(30) | N |  | 배출 범위(scope1, scope2_lb, scope2_mb, scope3_total 등) |
| `value` | NUMERIC(24,6) | Y |  | 배출량 값 |
| `unit_id` | BIGINT | N | FK | 단위 참조 |
| `basis_code` | VARCHAR(50) | Y |  | 산정 기준(location-based 등) |
| `is_verified` | BOOLEAN | Y |  | 검증 여부 |
| `assurance_level` | VARCHAR(30) | Y |  | 보증 수준 |
| `source_document_id` | BIGINT | Y | FK | 근거 문서 참조 |
| `evidence_id` | BIGINT | Y | FK | 근거 블록 참조 |
| `data_status` | VARCHAR(30) | N |  | reported, estimated, missing 등 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |
| `update_date` | TIMESTAMP | Y |  | 레코드 최종 수정 일시 |
| `updater` | VARCHAR(100) | Y |  | 레코드를 마지막으로 수정한 주체(사용자, 시스템, 배치명 등) |

### `company_scope3_categories`
- 목적: 기업별 Scope 3 카테고리 및 데이터 품질 입력값을 저장합니다.
- 행 단위: 기업-기간-카테고리 1개당 1행
- 배치 단계: 원천값 적재

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `s3_id` | BIGINT | N | PK | Scope 3 카테고리 식별자 |
| `company_id` | BIGINT | N | FK | 기업 참조 |
| `period_id` | BIGINT | N | FK | 보고기간 참조 |
| `category_code` | VARCHAR(20) | N |  | Scope 3 카테고리 코드 |
| `category_name` | VARCHAR(200) | Y |  | 카테고리명 |
| `emission_value` | NUMERIC(24,6) | Y |  | 카테고리 배출량 |
| `unit_id` | BIGINT | Y | FK | 단위 참조 |
| `material_category_flag` | BOOLEAN | Y |  | 산업상 중대성 카테고리 여부 |
| `materiality_weight` | NUMERIC(10,6) | Y |  | 전체 Scope 3 대비 가중치 비중 |
| `disclosed_flag` | BOOLEAN | Y |  | 해당 카테고리 공시 여부 |
| `data_source_type` | VARCHAR(50) | Y |  | 데이터 출처 유형(primary, revenue-based 등) |
| `primary_data_ratio` | NUMERIC(8,5) | Y |  | 카테고리 내 1차 데이터 사용 비율 |
| `supplier_primary_data_ratio` | NUMERIC(8,5) | Y |  | 협력사 실측/1차 데이터 비율 |
| `estimation_method_detail` | TEXT | Y |  | 추정 방식 상세 설명 |
| `dqs_score` | NUMERIC(4,2) | Y |  | PCAF 등가 데이터 품질 점수 |
| `pcaf_or_equivalent_method` | VARCHAR(100) | Y |  | 적용한 품질 평가 프레임워크 |
| `source_document_id` | BIGINT | Y | FK | 근거 문서 참조 |
| `evidence_id` | BIGINT | Y | FK | 근거 블록 참조 |
| `data_status` | VARCHAR(30) | N |  | reported, estimated, missing 등 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

### `company_financial_metrics`
- 목적: 기업별 재무 지표 원천값을 저장합니다.
- 행 단위: 기업-기간-지표 1개당 1행
- 배치 단계: 원천값 적재

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `finance_id` | BIGINT | N | PK | 재무지표 식별자 |
| `company_id` | BIGINT | N | FK | 기업 참조 |
| `period_id` | BIGINT | N | FK | 보고기간 참조 |
| `metric_code` | VARCHAR(50) | N |  | 지표 코드(revenue, EBITDA, capex_total 등) |
| `value` | NUMERIC(24,6) | Y |  | 지표 값 |
| `unit_id` | BIGINT | Y | FK | 단위 참조 |
| `currency_code` | CHAR(3) | Y |  | 통화 코드 |
| `consolidation_basis` | VARCHAR(50) | Y |  | 연결/별도 기준 |
| `source_document_id` | BIGINT | Y | FK | 근거 문서 참조 |
| `evidence_id` | BIGINT | Y | FK | 근거 블록 참조 |
| `data_status` | VARCHAR(30) | N |  | reported, estimated, missing 등 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |
| `update_date` | TIMESTAMP | Y |  | 레코드 최종 수정 일시 |
| `updater` | VARCHAR(100) | Y |  | 레코드를 마지막으로 수정한 주체(사용자, 시스템, 배치명 등) |

### `climate_targets`
- 목적: 기업별 단·중·장기 및 넷제로 목표 입력값을 저장합니다.
- 행 단위: 기업-기간-목표 1개당 1행
- 배치 단계: 원천값 적재

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `target_id` | BIGINT | N | PK | 목표 식별자 |
| `company_id` | BIGINT | N | FK | 기업 참조 |
| `period_id` | BIGINT | N | FK | 보고기간 참조 |
| `target_type` | VARCHAR(50) | N |  | 목표 유형(short, mid, long, netzero 등) |
| `target_period_bucket` | VARCHAR(30) | Y |  | 평가 구간(short/mid/long/netzero) |
| `base_year` | INTEGER | Y |  | 기준연도 |
| `target_year` | INTEGER | Y |  | 목표연도 |
| `target_scope` | VARCHAR(100) | Y |  | 목표 적용 범위(scope1_2, scope1_2_3 등) |
| `baseline_emission_value` | NUMERIC(24,6) | Y |  | 기준연도 배출량 |
| `target_emission_value` | NUMERIC(24,6) | Y |  | 목표 배출량 |
| `reduction_pct` | NUMERIC(8,5) | Y |  | 감축 목표 비율 |
| `scope3_coverage_pct` | NUMERIC(8,5) | Y |  | 목표에 포함된 Scope 3 범위 비율 |
| `sbti_status` | VARCHAR(100) | Y |  | SBTi 승인/커밋 상태 |
| `sbti_temperature_label` | VARCHAR(50) | Y |  | 1.5C 등 온도 라벨 |
| `uses_offsets_flag` | BOOLEAN | Y |  | 배출권 상쇄 사용 여부 |
| `offset_limit_pct` | NUMERIC(8,5) | Y |  | 허용/계획된 상쇄 비율 |
| `offset_disclosure_level` | VARCHAR(50) | Y |  | 상쇄 공시 수준 |
| `target_boundary_desc` | TEXT | Y |  | 목표 경계/포함범위 설명 |
| `actual_emission_scope_basis` | VARCHAR(100) | Y |  | 실적치와 비교할 배출 범위 기준 |
| `source_document_id` | BIGINT | Y | FK | 근거 문서 참조 |
| `evidence_id` | BIGINT | Y | FK | 근거 블록 참조 |
| `data_status` | VARCHAR(30) | N |  | reported, estimated, missing 등 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

### `climate_capex`
- 목적: 기업별 녹색/전환 CapEx 입력값을 저장합니다.
- 행 단위: 기업-기간 1개당 1행
- 배치 단계: 원천값 적재

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `capex_id` | BIGINT | N | PK | CapEx 식별자 |
| `company_id` | BIGINT | N | FK | 기업 참조 |
| `period_id` | BIGINT | N | FK | 보고기간 참조 |
| `total_capex_value` | NUMERIC(24,6) | Y |  | 총 자본지출 |
| `green_capex_value` | NUMERIC(24,6) | Y |  | 녹색 자본지출 |
| `transition_capex_value` | NUMERIC(24,6) | Y |  | 전환 목적 자본지출 |
| `green_capex_ratio` | NUMERIC(8,5) | Y |  | 총 CapEx 대비 녹색 CapEx 비율 |
| `taxonomy_alignment_ratio` | NUMERIC(8,5) | Y |  | taxonomy 정렬 비율 |
| `target_green_capex_ratio` | NUMERIC(8,5) | Y |  | 비교 기준 목표 비율 |
| `taxonomy_standard` | VARCHAR(100) | Y |  | 적용 taxonomy 기준 |
| `taxonomy_jurisdiction` | VARCHAR(50) | Y |  | taxonomy 관할권 |
| `green_capex_definition_note` | TEXT | Y |  | 녹색/전환 CapEx 정의 메모 |
| `source_document_id` | BIGINT | Y | FK | 근거 문서 참조 |
| `evidence_id` | BIGINT | Y | FK | 근거 블록 참조 |
| `data_status` | VARCHAR(30) | N |  | reported, estimated, missing 등 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

### `board_climate_governance`
- 목적: 이사회 차원의 기후 감독 및 위원회 정보를 저장합니다.
- 행 단위: 기업-기간 1개당 1행
- 배치 단계: 원천값 적재

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `board_climate_governance_id` | BIGINT | N | PK | 이사회 기후 거버넌스 식별자 |
| `company_id` | BIGINT | N | FK | 기업 참조 |
| `period_id` | BIGINT | N | FK | 보고기간 참조 |
| `board_oversight_flag` | BOOLEAN | Y |  | 이사회 기후감독 명시 여부 |
| `climate_committee_flag` | BOOLEAN | Y |  | 기후/ESG 전담 위원회 존재 여부 |
| `committee_name` | VARCHAR(200) | Y |  | 위원회명 |
| `board_approval_flag` | BOOLEAN | Y |  | 전환계획/기후목표 이사회 승인 여부 |
| `board_review_frequency` | SMALLINT | Y |  | 연간 검토 횟수 |
| `director_climate_training_flag` | BOOLEAN | Y |  | 이사회 대상 기후교육 시행 여부 |
| `climate_expertise_flag` | BOOLEAN | Y |  | 기후 전문성 보유 이사 존재 여부 |
| `governance_disclosure_level` | VARCHAR(50) | Y |  | 거버넌스 공시 수준 |
| `source_document_id` | BIGINT | Y | FK | 근거 문서 참조 |
| `evidence_id` | BIGINT | Y | FK | 근거 블록 참조 |
| `data_status` | VARCHAR(30) | N |  | reported, estimated, missing 등 |
| `notes` | TEXT | Y |  | 추가 메모 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

### `executive_climate_kpi`
- 목적: 경영진 보상과 기후 KPI 연계 정보를 저장합니다.
- 행 단위: 기업-기간 1개당 1행
- 배치 단계: 원천값 적재

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `kpi_id` | BIGINT | N | PK | 경영진 KPI 식별자 |
| `company_id` | BIGINT | N | FK | 기업 참조 |
| `period_id` | BIGINT | N | FK | 보고기간 참조 |
| `climate_linked_comp_ratio` | NUMERIC(8,5) | Y |  | 전체 보상 중 기후 연계 비율 |
| `short_term_ratio` | NUMERIC(8,5) | Y |  | 단기 성과급 중 기후 연계 비율 |
| `long_term_ratio` | NUMERIC(8,5) | Y |  | 장기 인센티브 중 기후 연계 비율 |
| `has_quantitative_link` | BOOLEAN | Y |  | 정량 지표 연계 여부 |
| `lti_link_flag` | BOOLEAN | Y |  | LTI 연계 여부 |
| `sti_link_flag` | BOOLEAN | Y |  | STI 연계 여부 |
| `source_document_id` | BIGINT | Y | FK | 근거 문서 참조 |
| `evidence_id` | BIGINT | Y | FK | 근거 블록 참조 |
| `data_status` | VARCHAR(30) | N |  | reported, estimated, missing 등 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

### `assurance_records`
- 목적: 배출량/공시 데이터에 대한 제3자 검증 및 보증 정보를 저장합니다.
- 행 단위: 기업-기간-보증범위 1개당 1행
- 배치 단계: 원천값 적재

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `assurance_id` | BIGINT | N | PK | 보증 기록 식별자 |
| `company_id` | BIGINT | N | FK | 기업 참조 |
| `period_id` | BIGINT | N | FK | 보고기간 참조 |
| `assurance_scope` | VARCHAR(200) | Y |  | 보증 대상 범위 설명 |
| `assurance_scope_code` | VARCHAR(100) | Y |  | 정규화한 보증 범위 코드 |
| `assurance_level` | VARCHAR(30) | Y |  | 보증 수준(reasonable, limited 등) |
| `assurance_statement_type` | VARCHAR(100) | Y |  | 성명서 유형/형식 |
| `verifier_name` | VARCHAR(200) | Y |  | 검증기관명 |
| `site_visit_flag` | BOOLEAN | Y |  | 현장 검증 수행 여부 |
| `gov_db_match_flag` | BOOLEAN | Y |  | 정부 DB와의 일치 여부 |
| `gov_db_match_source` | VARCHAR(200) | Y |  | 대조한 정부 DB 출처 |
| `emission_match_ratio` | NUMERIC(8,5) | Y |  | 공시치와 정부 DB 일치 비율 |
| `institution_trust_score` | NUMERIC(8,5) | Y |  | 기관 신뢰도 점수 |
| `source_document_id` | BIGINT | Y | FK | 근거 문서 참조 |
| `evidence_id` | BIGINT | Y | FK | 근거 블록 참조 |
| `data_status` | VARCHAR(30) | N |  | reported, estimated, missing 등 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

### `company_cbam_exposure`
- 목적: CBAM 대상 수출량 및 내재배출량 입력값을 저장합니다.
- 행 단위: 기업-기간-품목 1개당 1행
- 배치 단계: 원천값 적재

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `cbam_id` | BIGINT | N | PK | CBAM 노출 식별자 |
| `company_id` | BIGINT | N | FK | 기업 참조 |
| `period_id` | BIGINT | N | FK | 보고기간 참조 |
| `product_code` | VARCHAR(50) | N |  | 대상 품목 코드 |
| `product_name` | VARCHAR(200) | Y |  | 대상 품목명 |
| `export_qty_ton` | NUMERIC(24,6) | Y |  | EU 수출량(톤) |
| `embedded_emission_tco2e_per_ton` | NUMERIC(24,6) | Y |  | 1톤당 내재배출량 |
| `destination_region` | VARCHAR(50) | Y |  | 수출 대상 지역(EU 등) |
| `paid_domestic_carbon_price_eur_per_ton` | NUMERIC(24,6) | Y |  | 국내 기지불 실효 탄소가격 |
| `source_document_id` | BIGINT | Y | FK | 근거 문서 참조 |
| `evidence_id` | BIGINT | Y | FK | 근거 블록 참조 |
| `data_status` | VARCHAR(30) | N |  | reported, estimated, missing 등 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

### `market_carbon_prices`
- 목적: 시장 탄소가격 시계열을 저장합니다.
- 행 단위: 시장-일자 1개당 1행
- 배치 단계: 외부참조 적재

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `market_price_id` | BIGINT | N | PK | 시장가격 식별자 |
| `market_code` | VARCHAR(50) | N |  | 시장 코드(EU_ETS, K_ETS 등) |
| `price_date` | DATE | N |  | 가격 기준일 |
| `price_value` | NUMERIC(24,6) | N |  | 가격 값 |
| `currency_code` | CHAR(3) | Y |  | 통화 코드 |
| `unit_code` | VARCHAR(50) | Y |  | 단위 코드(€/tCO2e 등) |
| `source_name` | VARCHAR(200) | Y |  | 가격 출처명 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

### `company_internal_carbon_price`
- 목적: 기업의 내부 탄소가격(ICP) 실효성 입력값을 저장합니다.
- 행 단위: 기업-기간 1개당 1행
- 배치 단계: 원천값 적재

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `icp_id` | BIGINT | N | PK | ICP 식별자 |
| `company_id` | BIGINT | N | FK | 기업 참조 |
| `period_id` | BIGINT | N | FK | 보고기간 참조 |
| `shadow_price_value` | NUMERIC(24,6) | Y |  | 내부 탄소가격 값 |
| `currency_code` | CHAR(3) | Y |  | 통화 코드 |
| `unit_code` | VARCHAR(50) | Y |  | 단위 코드 |
| `price_basis` | VARCHAR(100) | Y |  | 가격 산정 기준(투자, 리스크, 규제 대비 등) |
| `covers_capex_decisions_flag` | BOOLEAN | Y |  | CapEx 의사결정 반영 여부 |
| `covers_procurement_flag` | BOOLEAN | Y |  | 조달/공급망 의사결정 반영 여부 |
| `reference_market_price_flag` | BOOLEAN | Y |  | 시장가격 연동 여부 |
| `source_document_id` | BIGINT | Y | FK | 근거 문서 참조 |
| `evidence_id` | BIGINT | Y | FK | 근거 블록 참조 |
| `data_status` | VARCHAR(30) | N |  | reported, estimated, missing 등 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

## Benchmark

### `industry_pathways`
- 목적: 산업별 감축 경로(LARR/SDA)를 관리합니다.
- 행 단위: 산업-버전-구간 1개당 1행
- 배치 단계: 벤치마크 적재

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `pathway_id` | BIGINT | N | PK | 산업 경로 식별자 |
| `industry_id` | BIGINT | N | FK | 산업 참조 |
| `methodology_version_id` | BIGINT | N | FK | 방법론 버전 참조 |
| `pathway_type` | VARCHAR(30) | N |  | 경로 유형(LARR, SDA 등) |
| `period_bucket` | VARCHAR(30) | Y |  | 구간(short, mid, long) |
| `base_year` | INTEGER | Y |  | 기준연도 |
| `target_year` | INTEGER | Y |  | 목표연도 |
| `annual_reduction_rate` | NUMERIC(8,5) | Y |  | 연간 감축률 |
| `source_name` | VARCHAR(200) | Y |  | 출처명 |
| `description` | TEXT | Y |  | 경로 설명 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

### `industry_intensity_benchmarks`
- 목적: 산업별 탄소집약도 비교 분포를 저장합니다.
- 행 단위: 산업-기간-지표 1개당 1행
- 배치 단계: 벤치마크 적재

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `benchmark_id` | BIGINT | N | PK | 집약도 벤치마크 식별자 |
| `industry_id` | BIGINT | N | FK | 산업 참조 |
| `period_id` | BIGINT | N | FK | 보고기간 참조 |
| `metric_code` | VARCHAR(50) | N |  | 집약도 지표 코드 |
| `p10_value` | NUMERIC(24,6) | Y |  | 하위 백분위 기준값 |
| `p90_value` | NUMERIC(24,6) | Y |  | 상위 백분위 기준값 |
| `avg_value` | NUMERIC(24,6) | Y |  | 평균값 |
| `median_value` | NUMERIC(24,6) | Y |  | 중앙값 |
| `method` | VARCHAR(100) | Y |  | 정규화 방법(minmax, zscore 등) |
| `source_name` | VARCHAR(200) | Y |  | 출처명 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

### `industry_material_scope3_categories`
- 목적: 산업별 중대 Scope 3 카테고리를 관리합니다.
- 행 단위: 산업-카테고리 1개당 1행
- 배치 단계: 벤치마크 적재

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `materiality_id` | BIGINT | N | PK | 중대성 매핑 식별자 |
| `industry_id` | BIGINT | N | FK | 산업 참조 |
| `category_code` | VARCHAR(20) | N |  | Scope 3 카테고리 코드 |
| `category_name` | VARCHAR(200) | Y |  | 카테고리명 |
| `weight` | NUMERIC(10,6) | Y |  | 카테고리 가중치 |
| `rank_order` | SMALLINT | Y |  | 중요도 순위 |
| `source_framework` | VARCHAR(100) | Y |  | 출처 프레임워크(GHG Protocol 등) |
| `source_name` | VARCHAR(200) | Y |  | 출처명 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

### `industry_green_capex_targets`
- 목적: 산업별 목표 녹색 CapEx 비율을 관리합니다.
- 행 단위: 산업-기간 1개당 1행
- 배치 단계: 벤치마크 적재

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `target_id` | BIGINT | N | PK | 산업 CapEx 목표 식별자 |
| `industry_id` | BIGINT | N | FK | 산업 참조 |
| `period_id` | BIGINT | N | FK | 보고기간 참조 |
| `target_ratio` | NUMERIC(8,5) | Y |  | 산업 목표 비율 |
| `taxonomy_standard` | VARCHAR(100) | Y |  | 적용 taxonomy 기준 |
| `source_name` | VARCHAR(200) | Y |  | 출처명 |
| `description` | TEXT | Y |  | 산정 설명 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

## Scoring

### `scoring_runs`
- 목적: 기업별 스코어링 실행 이력을 저장합니다.
- 행 단위: 기업-기간-실행 1개당 1행
- 배치 단계: 스코어링

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `scoring_run_id` | BIGINT | N | PK | 스코어링 실행 식별자 |
| `company_id` | BIGINT | N | FK | 기업 참조 |
| `period_id` | BIGINT | N | FK | 보고기간 참조 |
| `methodology_version_id` | BIGINT | N | FK | 방법론 버전 참조 |
| `run_type` | VARCHAR(30) | N |  | 실행 유형(batch, recalc, backfill 등) |
| `run_started_at` | TIMESTAMP | N |  | 실행 시작 시각 |
| `run_finished_at` | TIMESTAMP | Y |  | 실행 종료 시각 |
| `status` | VARCHAR(30) | N |  | 실행 상태 |
| `triggered_by` | VARCHAR(100) | Y |  | 실행 주체 또는 트리거 |
| `notes` | TEXT | Y |  | 추가 메모 |

### `variable_input_snapshots`
- 목적: 각 변수 계산 시 사용한 입력 스냅샷을 저장합니다.
- 행 단위: 스코어링-변수 1개당 1행
- 배치 단계: 스코어링

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `snapshot_id` | BIGINT | N | PK | 입력 스냅샷 식별자 |
| `scoring_run_id` | BIGINT | N | FK | 스코어링 실행 참조 |
| `variable_id` | BIGINT | N | FK | 변수 참조 |
| `input_json` | JSONB | N |  | 계산에 사용한 입력값 |
| `missing_flags_json` | JSONB | Y |  | 누락/대체 처리 플래그 |
| `evidence_refs_json` | JSONB | Y |  | 사용 근거 참조 목록 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

### `variable_scores`
- 목적: 변수별 계산 결과와 가중치를 저장합니다.
- 행 단위: 스코어링-변수 1개당 1행
- 배치 단계: 스코어링

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `variable_score_id` | BIGINT | N | PK | 변수 점수 식별자 |
| `scoring_run_id` | BIGINT | N | FK | 스코어링 실행 참조 |
| `variable_id` | BIGINT | N | FK | 변수 참조 |
| `raw_value_json` | JSONB | Y |  | 원시 또는 중간 계산값 |
| `normalized_value` | NUMERIC(12,8) | Y |  | 정규화 값 |
| `score_value` | NUMERIC(12,8) | Y |  | 최종 변수 점수 |
| `weight_global` | NUMERIC(12,8) | Y |  | 전사 최종 가중치 |
| `weight_local_ahp` | NUMERIC(12,8) | Y |  | AHP 국소 가중치 |
| `weight_local_ewm` | NUMERIC(12,8) | Y |  | EWM 국소 가중치 |
| `weight_local_final` | NUMERIC(12,8) | Y |  | 결합된 국소 가중치 |
| `calc_trace_json` | JSONB | Y |  | 계산 추적 정보 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

### `category_scores`
- 목적: 카테고리별 점수와 가중 반영값을 저장합니다.
- 행 단위: 스코어링-카테고리 1개당 1행
- 배치 단계: 스코어링

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `category_score_id` | BIGINT | N | PK | 카테고리 점수 식별자 |
| `scoring_run_id` | BIGINT | N | FK | 스코어링 실행 참조 |
| `category_id` | BIGINT | N | FK | 카테고리 참조 |
| `category_score` | NUMERIC(12,8) | Y |  | 카테고리 원점수 |
| `weighted_score` | NUMERIC(12,8) | Y |  | 가중 반영 점수 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

### `risk_adjustments`
- 목적: CEF, GV 등 외생 리스크 조정값을 저장합니다.
- 행 단위: 스코어링-조정항 1개당 1행
- 배치 단계: 스코어링

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `adjustment_id` | BIGINT | N | PK | 조정항 식별자 |
| `scoring_run_id` | BIGINT | N | FK | 스코어링 실행 참조 |
| `adjustment_type` | VARCHAR(30) | N |  | 조정 유형(CEF, GV 등) |
| `input_json` | JSONB | Y |  | 조정식 입력값 |
| `adjustment_factor` | NUMERIC(12,8) | Y |  | 최종 적용 계수 |
| `calc_trace_json` | JSONB | Y |  | 조정 계산 추적 |
| `notes` | TEXT | Y |  | 예: GV는 greenwashing penalty 의미 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

### `final_scores`
- 목적: 기초점수, 조정항, 최종점수를 저장합니다.
- 행 단위: 스코어링 실행 1개당 1행
- 배치 단계: 스코어링

| 컬럼명 | 타입 | Nullable | Key | 설명 |
|---|---|---|---|---|
| `final_score_id` | BIGINT | N | PK | 최종 점수 식별자 |
| `scoring_run_id` | BIGINT | N | FK | 스코어링 실행 참조 |
| `sbase` | NUMERIC(12,8) | Y |  | 기초 점수(Sbase) |
| `cef` | NUMERIC(12,8) | Y |  | CBAM 노출 조정 계수(CEF) |
| `gv` | NUMERIC(12,8) | Y |  | 그린워싱 분산 패널티(GV) |
| `final_score` | NUMERIC(12,8) | Y |  | 최종 CERs Index 점수 |
| `score_grade` | VARCHAR(20) | Y |  | 등급 또는 밴드 |
| `interpretation_note` | TEXT | Y |  | 점수 해석 메모 |
| `reg_date` | TIMESTAMP | N |  | 레코드 최초 등록 일시 |
| `registrar` | VARCHAR(100) | N |  | 레코드를 최초 등록한 주체(사용자, 시스템, 배치명 등) |

## 변수 매핑 요약
| Stable Code | Canonical Display Code | Alt Display Codes | Candidate Display Name | Primary Fact Tables | Status | Comment |
|---|---|---|---|---|---|---|
| `ABS_REDUCTION` | `V1` |  | 절대 감축률 | company_emissions | Scored | 본문과 수집경로 표가 비교적 일치 |
| `INTENSITY_EFF` | `V2` |  | 탄소 집약도 효율성 | company_emissions, company_financial_metrics, industry_intensity_benchmarks | Scored | 산업 벤치마크 필요 |
| `SCOPE3_TRANSPARENCY` | `V3` |  | Scope 3 가치사슬 데이터 투명성 | company_scope3_categories, industry_material_scope3_categories | Scored | material category + primary data ratio + DQS 반영 |
| `TARGET_GAP_SHORT` | `V4` | V5 (수집경로표는 단·중기 통합) | 단기 목표 비대칭 잔차 | climate_targets, industry_pathways | Scored | 본문 3.3.1 기준 세분화 |
| `TARGET_GAP_MID` | `V5` | V5 (수집경로표는 단·중기 통합) | 중기 목표 비대칭 잔차 | climate_targets, industry_pathways | Scored | 본문 3.3.1 기준 세분화 |
| `TARGET_GAP_LONG` | `V6` |  | 장기 목표 비대칭 잔차 | climate_targets, industry_pathways | Scored | 본문 3.3.1 기준 세분화 |
| `NETZERO_AMBITION` | `V7` | V4 (수집경로표) | 과학기반 넷제로 타당성/야심 | climate_targets | Scored | SBTi, Scope 3 포함률, offset 제한 반영 |
| `GREEN_CAPEX` | `V8` | V6 (본문 Cat3 서술) | 자본 지출의 기후 정렬도 | climate_capex, industry_green_capex_targets | Scored | taxonomy 정렬 정보 필요 |
| `EXEC_KPI_LINK` | `V9` | V7 (본문 Cat3 서술) | 경영진 보상 연계율 | executive_climate_kpi | Scored | LTI/STI와 정량 KPI 연계 수준 |
| `ASSURANCE_LEVEL` | `V10` | V8 (수집경로표) | 제3자 검증 및 보증 수준 | assurance_records | Scored | 교집합/현장검증/기관신뢰도 상세화 |
| `ICP_EFFECTIVENESS` | `V9 (수집경로표)` |  | 내부 탄소가격제 실효성 | company_internal_carbon_price | Scored candidate | 공식 후보 변수이나 본문 산식 확정 전 |
| `BOARD_GOVERNANCE_SUPPORT` | `` |  | 이사회 기후 거버넌스 지원 입력 | board_climate_governance | Supporting | 독립 점수변수라기보다 Cat3/추후 확장 지원 fact |
| `CARBON_EXPOSURE_FACTOR` | `CEF` |  | CBAM 노출 리스크 | company_cbam_exposure, market_carbon_prices, company_financial_metrics, regulatory_parameters | Adjustment | 최종 점수 조정항 |
| `GREENWASHING_PENALTY` | `GV` |  | 그린워싱 분산 패널티 | category_scores | Adjustment | AP-RP divergence penalty |
