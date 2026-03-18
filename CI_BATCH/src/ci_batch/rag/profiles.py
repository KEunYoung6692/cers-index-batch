"""
Extraction profiles for fact tables.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FactExtractionProfile:
    table_name: str
    description: str
    query_text: str
    keywords: tuple[str, ...]
    max_chunks: int = 8


FACT_PROFILES = [
    FactExtractionProfile(
        table_name="company_emissions",
        description="온실가스 배출량과 Scope별 수치를 추출한다.",
        query_text="Find explicit greenhouse gas emissions disclosures for scope 1, scope 2, and scope 3, including units, basis, and verification status.",
        keywords=("온실가스", "배출량", "scope", "tco2", "검증", "배출"),
    ),
    FactExtractionProfile(
        table_name="company_scope3_categories",
        description="Scope 3 카테고리별 배출량과 데이터 품질 정보를 추출한다.",
        query_text="Find explicit Scope 3 category disclosures, category values, primary data ratios, estimation details, and data quality framework references.",
        keywords=("scope 3", "category", "카테고리", "공급망", "pcaf", "dqs", "primary data"),
    ),
    FactExtractionProfile(
        table_name="company_financial_metrics",
        description="매출, EBITDA, 총 CapEx 등 재무 지표를 추출한다.",
        query_text="Find explicit company financial metrics such as revenue, EBITDA, and total capex with units or currency.",
        keywords=("매출", "revenue", "ebitda", "capex", "자본지출", "별도", "연결"),
    ),
    FactExtractionProfile(
        table_name="climate_targets",
        description="단기/중기/장기/넷제로 목표와 기준연도, 목표연도, 감축률을 추출한다.",
        query_text="Find explicit climate target disclosures including base year, target year, target scope, reduction percentage, SBTi status, and offset usage.",
        keywords=("탄소중립", "net zero", "목표", "기준연도", "target", "sbti", "re100", "감축"),
    ),
    FactExtractionProfile(
        table_name="climate_capex",
        description="녹색/전환 CapEx와 taxonomy 정렬 정보를 추출한다.",
        query_text="Find explicit green or transition capex disclosures, ratios, taxonomy alignment, and total capex values.",
        keywords=("green capex", "capex", "taxonomy", "녹색", "전환", "자본지출", "투자"),
    ),
    FactExtractionProfile(
        table_name="board_climate_governance",
        description="이사회 기후 감독과 위원회 정보를 추출한다.",
        query_text="Find explicit board-level climate governance disclosures including board oversight, committees, approvals, review frequency, and director climate expertise.",
        keywords=("이사회", "위원회", "esg위원회", "거버넌스", "감독", "board", "climate committee"),
    ),
    FactExtractionProfile(
        table_name="executive_climate_kpi",
        description="경영진 보상과 기후 KPI 연계 정보를 추출한다.",
        query_text="Find explicit executive compensation links to climate or ESG KPIs, including STI, LTI, and quantitative linkage.",
        keywords=("보상", "kpi", "성과급", "sti", "lti", "연계", "executive"),
    ),
    FactExtractionProfile(
        table_name="assurance_records",
        description="제3자 검증 및 보증 기록을 추출한다.",
        query_text="Find explicit assurance or verification disclosures including scope, level, verifier, site visit, and statement type.",
        keywords=("검증", "보증", "assurance", "제3자", "의견서", "검증기관", "limited assurance"),
    ),
    FactExtractionProfile(
        table_name="company_cbam_exposure",
        description="CBAM 관련 노출 수치와 수출량, 내재배출량 정보를 추출한다.",
        query_text="Find explicit CBAM-related export disclosures including product names, export quantity, embedded emissions, destination regions, and carbon price paid.",
        keywords=("cbam", "eu", "수출", "내재배출", "embedded emission", "톤"),
    ),
    FactExtractionProfile(
        table_name="company_internal_carbon_price",
        description="내부 탄소가격(ICP)과 적용 범위를 추출한다.",
        query_text="Find explicit internal carbon price disclosures including price value, basis, and whether it is used for capex or procurement decisions.",
        keywords=("내부탄소가격", "carbon price", "shadow price", "icp", "procurement", "capex"),
    ),
]


FACT_PROFILE_BY_TABLE = {profile.table_name: profile for profile in FACT_PROFILES}
