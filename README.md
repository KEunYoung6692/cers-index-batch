# cers-index-batch
데이터 자동화 api


# directory
repo/
  README.md
  pyproject.toml
  .env.example
  .gitignore
  Makefile

  src/
    pipeline/                       # "프레임" (공통 런타임)
      cli.py                        # python -m pipeline ...
      settings.py                   # 환경변수/설정 로딩
      logging.py                    # 로깅 포맷, 파일/콘솔, trace_id
      run_context.py                # run_id, timestamps, manifest
      storage.py                    # 로컬/원격 스토리지 추상화
      http.py                       # retries, rate limit, user-agent, session
      db.py                         # connection pool, transaction helpers
      validators.py                 # pydantic, pandera 등 검증 유틸
      utils/

    sources/                        # 소스(사이트/API)별 "Extract + Parse"
      sbti/
        extractor.py                # 다운로드/수집
        parser.py                   # raw -> structured rows
        mapping.py                  # 회사명/식별자 매핑 규칙
        schemas.py                  # 이 소스에서 나오는 레코드 스키마
        tests/
      tpi/
        extractor.py
        parser.py
        mapping.py
        schemas.py
      ca100/
        extractor.py
        parser.py
        mapping.py
        schemas.py
      cdp/
        extractor.py
        parser.py
        mapping.py
        schemas.py

    transforms/                     # 소스 무관 "정제/표준화"
      normalize_company.py          # 회사명/식별자 표준화
      normalize_units.py            # 단위 통일 (tCO2e 등)
      normalize_scopes.py           # scope1/2/3 구조 통일
      dedupe.py                     # 중복 제거 전략
      quality_flags.py              # data_quality, confidence 등 부여

    models/                         # "표준 레코드 모델" (중간 표준)
      company.py
      emission.py
      target.py
      governance.py
      policy.py
      evidence.py

    loaders/                        # Load 계층 (DB 적재)
      staging.py                    # staging 테이블 적재
      upsert.py                     # 본 테이블 UPSERT/merge 로직
      migrations/                   # alembic 또는 SQL migration
      sql/                          # 핵심 쿼리(merge/stored procedure)

    jobs/                           # 파이프라인 단위 엔트리 (소스/배치)
      collect_sbti.py
      collect_tpi.py
      collect_ca100.py
      collect_cdp.py
      daily_refresh.py              # 조합 실행
      backfill.py                   # 기간 재처리

  configs/
    sources/                        # 소스별 설정(셀렉터/URL/레이트리밋/로그인)
      sbti.yaml
      tpi.yaml
      ca100.yaml
      cdp.yaml
    mapping/
      company_alias_rules.yaml      # 회사명 정규화 규칙
    db/
      tables.yaml                   # 테이블/컬럼 매핑(선택)

  storage/                          # Git에 보통 제외(.gitignore)
    raw/                            # 원천 그대로 (Bronze)
      sbti/2026-02-11/*.json
      tpi/2026-02-11/*.csv
    parsed/                         # 파싱 결과 (Silver)
      sbti/2026-02-11/*.parquet
    curated/                        # 표준화/정제 결과 (Gold)
      company/2026-02-11.parquet
      target/2026-02-11.parquet
    manifests/                      # run 메타데이터(재현성 핵심)
      run_2026-02-11T10-00-00Z.json

  scripts/
    dev_smoke_test.sh
    init_db.sh

  tests/
    test_transforms.py
    test_loaders.py

  notebooks/                        # 탐색/디버깅용 (프로덕션 로직 금지)
  docs/                             # 데이터 사전/소스별 주의사항/운영가이드

  docker/
    Dockerfile
    docker-compose.yml
