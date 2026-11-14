"""
amz-flywheel: Zero-OAuth, local-first Python econometric package and FastMCP server
quantifying the causal Amazon Paid-to-Organic Search Flywheel.
"""

from amz_flywheel.contracts import (
    AdsRecord,
    AmzFlywheelError,
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
from amz_flywheel.core import (
    classify_keyword_series,
    classify_panel,
    decompose_observation,
    decompose_panel,
)
from amz_flywheel.io import (
    align_panels,
    ingest_and_align,
    parse_ads_csv,
    parse_rank_csv,
    parse_sqp_csv,
)
from amz_flywheel.pro import (
    enrich_with_pro_elasticity,
    get_pro_module,
    install_pro,
    is_pro_available,
    require_pro,
    validate_polar_key,
)

__version__ = "0.1.0"

__all__ = [
    "AdsRecord",
    "AmzFlywheelError",
    "AuditReport",
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
    "enrich_with_pro_elasticity",
    "get_pro_module",
    "ingest_and_align",
    "install_pro",
    "is_pro_available",
    "parse_ads_csv",
    "parse_rank_csv",
    "parse_sqp_csv",
    "require_pro",
    "validate_polar_key",
]
