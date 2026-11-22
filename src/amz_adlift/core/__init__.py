"""Core open-source econometric decomposition, 4-quadrant, iROAS, experiment, COSMO, and trust diagnostics."""

from amz_adlift.core.buybox_guard import (
    FulfillmentComparison,
    OperationalHealthReport,
    compare_fba_vs_fbm_economics,
    evaluate_buybox_and_promo_health,
)
from amz_adlift.core.cosmo_intent import (
    ListingAudit2026Result,
    audit_listing_2026,
    cluster_panel_by_cosmo_intent,
    infer_cosmo_intent_cluster,
)
from amz_adlift.core.decomposition import decompose_observation, decompose_panel
from amz_adlift.core.experiments import (
    CalibratedCausalPrior,
    MDEPowerResult,
    SyntheticControlResult,
    TrimmedMatchResult,
    calibrate_causal_prior,
    compute_experiment_mde,
    estimate_synthetic_control,
    estimate_trimmed_match,
)
from amz_adlift.core.iroas import (
    IROASEvaluation,
    compute_break_even_iroas,
    compute_effective_ltv_margin,
    compute_target_cpc_ceiling,
    evaluate_iroas_economics,
)
from amz_adlift.core.quadrants import (
    classify_keyword_series,
    classify_panel,
    compute_ols_slope,
    compute_pearson_corr,
)
from amz_adlift.core.trust_signals import (
    KeywordFunnelDiagnosis,
    diagnose_sqp_funnel_bottlenecks,
)

__all__ = [
    "CalibratedCausalPrior",
    "FulfillmentComparison",
    "IROASEvaluation",
    "KeywordFunnelDiagnosis",
    "ListingAudit2026Result",
    "MDEPowerResult",
    "OperationalHealthReport",
    "SyntheticControlResult",
    "TrimmedMatchResult",
    "audit_listing_2026",
    "calibrate_causal_prior",
    "classify_keyword_series",
    "classify_panel",
    "cluster_panel_by_cosmo_intent",
    "compare_fba_vs_fbm_economics",
    "compute_break_even_iroas",
    "compute_effective_ltv_margin",
    "compute_experiment_mde",
    "compute_ols_slope",
    "compute_pearson_corr",
    "compute_target_cpc_ceiling",
    "decompose_observation",
    "decompose_panel",
    "diagnose_sqp_funnel_bottlenecks",
    "estimate_synthetic_control",
    "estimate_trimmed_match",
    "evaluate_buybox_and_promo_health",
    "evaluate_iroas_economics",
    "infer_cosmo_intent_cluster",
]
