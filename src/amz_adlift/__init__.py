"""
amz-adlift: Zero-OAuth, local-first Python econometric package and FastMCP server
quantifying the causal Amazon Paid-to-Organic Search Flywheel.
"""

from amz_adlift.contracts import (
    AdsRecord,
    AmzAdliftError,
    AuditReport,
    InsufficientHistoryError,
    KeywordQuadrantDiagnostic,
    ProLicenseError,
    QuadrantLabel,
    RankRecord,
    SQPRecord,
    SchemaMismatchError,
    UnifiedKeywordWeek,
)
from amz_adlift.core import (
    classify_keyword_series,
    classify_panel,
    decompose_observation,
    decompose_panel,
)
from amz_adlift.io import (
    BulkKeywordTarget,
    align_panels,
    ingest_and_align,
    merge_bulksheet_ids,
    parse_ads_bulksheet,
    parse_ads_csv,
    parse_rank_csv,
    parse_sqp_csv,
)
from amz_adlift.pro import (
    detect_wheel_tags,
    enrich_with_pro_elasticity,
    get_pro_module,
    install_pro,
    is_pro_available,
    require_pro,
    resolve_and_download_wheel,
    validate_polar_key,
)
from amz_adlift.reporting import generate_html_audit_report

__version__ = "0.1.0"

__all__ = [
    "AdsRecord",
    "AmzAdliftError",
    "AuditReport",
    "BulkKeywordTarget",
    "InsufficientHistoryError",
    "KeywordQuadrantDiagnostic",
    "ProLicenseError",
    "QuadrantLabel",
    "RankRecord",
    "SQPRecord",
    "SchemaMismatchError",
    "UnifiedKeywordWeek",
    "__version__",
    "align_panels",
    "classify_keyword_series",
    "classify_panel",
    "decompose_observation",
    "decompose_panel",
    "detect_wheel_tags",
    "enrich_with_pro_elasticity",
    "generate_html_audit_report",
    "get_pro_module",
    "ingest_and_align",
    "install_pro",
    "is_pro_available",
    "merge_bulksheet_ids",
    "parse_ads_bulksheet",
    "parse_ads_csv",
    "parse_rank_csv",
    "parse_sqp_csv",
    "require_pro",
    "resolve_and_download_wheel",
    "validate_polar_key",
]
