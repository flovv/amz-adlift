"""Tests for Phase 1-4 Scientific Modules: iROAS, Experiments, COSMO 2026, Buy Box & SQP Funnel."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from amz_adlift.contracts.schemas import UnifiedKeywordWeek
from amz_adlift.core.buybox_guard import (
    compare_fba_vs_fbm_economics,
    evaluate_buybox_and_promo_health,
)
from amz_adlift.core.cosmo_intent import (
    audit_listing_2026,
    cluster_panel_by_cosmo_intent,
)
from amz_adlift.core.experiments import (
    calibrate_causal_prior,
    compute_experiment_mde,
    estimate_synthetic_control,
    estimate_trimmed_match,
)
from amz_adlift.core.iroas import (
    compute_break_even_iroas,
    compute_target_cpc_ceiling,
    evaluate_iroas_economics,
)
from amz_adlift.core.trust_signals import diagnose_sqp_funnel_bottlenecks
from amz_adlift.io.amc_connector import (
    generate_amc_existing_customer_suppression_sql,
    generate_amc_ltv_cohort_sql,
    generate_amc_promo_isolation_sql,
)
from amz_adlift.io.business_report_parser import parse_business_report_csv


def test_phase1_iroas_ltv_and_amc_sql() -> None:
    assert compute_break_even_iroas(0.40) == pytest.approx(2.5)
    assert compute_target_cpc_ceiling(0.12, 0.25, 40.0) == pytest.approx(1.20)

    # Value-destructive on 1st order (iROAS 1.5 < 2.5 at 40% margin)
    bad = evaluate_iroas_economics(
        incremental_revenue=1500.0,
        incremental_spend=1000.0,
        product_margin=0.40,
        observed_revenue=6000.0,
        observed_spend=1000.0,
        ntb_share=0.45,
        ltv_repeat_multiplier=1.0,
    )
    assert bad.verdict == "VALUE_DESTRUCTIVE"
    assert bad.existing_customer_waste_flag is True
    assert bad.net_profit_per_ad_dollar == pytest.approx(-0.40)

    # LTV-only profitable for consumables (3.2x repeat multiplier)
    ltv_ok = evaluate_iroas_economics(
        incremental_revenue=1800.0,
        incremental_spend=1000.0,
        product_margin=0.35,
        ntb_share=0.75,
        ltv_repeat_multiplier=3.2,
        cvr=0.12,
        selling_price=35.0,
    )
    assert ltv_ok.verdict == "LTV_ONLY_PROFITABLE"
    assert ltv_ok.target_cpc_ceiling is not None and ltv_ok.target_cpc_ceiling > 0.0

    # Privacy-safe AMC SQL templates enforce HAVING COUNT(DISTINCT user_id) >= 100
    for sql in (
        generate_amc_promo_isolation_sql(28),
        generate_amc_ltv_cohort_sql(90),
        generate_amc_existing_customer_suppression_sql(60),
    ):
        assert "HAVING COUNT(DISTINCT user_id) >= 100" in sql


def test_phase2_mde_scm_trimmed_match_and_calibration() -> None:
    # Low-variance series is powered for 10% lift
    powered = compute_experiment_mde([1000, 1015, 990, 1005, 1010, 995], expected_lift_pct=0.10)
    assert powered.power_adequate is True

    # High-variance series is underpowered for 5% lift
    underpowered = compute_experiment_mde([700, 1300, 820, 1250, 760, 1180], expected_lift_pct=0.05)
    assert underpowered.power_adequate is False

    # Synthetic Control recovers exact 0.6/0.4 mix and excludes buffer zone donor
    d1_pre = [100.0, 110.0, 120.0, 130.0, 140.0, 150.0]
    d2_pre = [200.0, 190.0, 210.0, 200.0, 220.0, 210.0]
    treated_pre = [0.6 * a + 0.4 * b for a, b in zip(d1_pre, d2_pre)]
    d1_post = [160.0, 170.0]
    d2_post = [220.0, 230.0]
    # True lift = +$50/period (+$100 total on $40 spend -> iROAS = 2.5x)
    treated_post = [0.6 * a + 0.4 * b + 50.0 for a, b in zip(d1_post, d2_post)]

    scm = estimate_synthetic_control(
        treated_pre=treated_pre,
        treated_post=treated_post,
        donor_pre={"DMA_1": d1_pre, "DMA_2": d2_pre, "DMA_BORDER": [999.0] * 6},
        donor_post={"DMA_1": d1_post, "DMA_2": d2_post, "DMA_BORDER": [999.0] * 2},
        incremental_spend=40.0,
        buffer_excluded_donors=["DMA_BORDER"],
    )
    assert "DMA_BORDER" in scm.excluded_buffer_donors
    assert "DMA_BORDER" not in scm.donor_weights
    assert scm.pre_period_r2 > 0.98
    assert scm.iroas == pytest.approx(2.5, abs=0.15)

    # Trimmed Match resists a massive outlier pair
    tmd = estimate_trimmed_match(
        pair_revenue_deltas=[250.0, 240.0, 260.0, 255.0, 245.0, 2500.0, -900.0],
        pair_spend_deltas=[100.0] * 7,
        trim_fraction=0.15,
    )
    assert tmd.iroas == pytest.approx(2.5, abs=0.15)
    assert tmd.pairs_retained == 5

    # Meridian-style prior calibration inflates SD with age & scope mismatch
    cal = calibrate_causal_prior(2.5, 0.3, experiment_age_days=180, scope_mismatch_factor=1.5)
    assert cal.prior_sd > 0.3
    assert cal.variance_inflation_factor == pytest.approx(3.0, abs=0.05)


def test_phase3_cosmo_2026_listing_audit_and_clustering() -> None:
    res = audit_listing_2026(
        title="SleepWell Organic Magnesium Glycinate 400mg Capsules for Deep Restful Sleep Support 120 Count",
        item_highlights="Best #1 sleep capsules | Magnesium Glycinate | Sugar-free vegan formula for adults",
        legacy_backend_keywords="magnesium glycinate melatonin-free travel pack",
        sqp_queries=["magnesium for sleep", "non-slip yoga mat"],
    )
    assert res.title_compliant is False
    assert "TITLE_EXCEEDS_75_CHAR_AUTO_REWRITE_RISK" in res.flags
    assert "SUBJECTIVE_CLAIMS_IN_ITEM_HIGHLIGHTS" in res.flags
    assert "REDUNDANT_TITLE_KEYWORDS_IN_HIGHLIGHTS" in res.flags
    assert "ORPHANED_DEPRECATED_BACKEND_KEYWORDS" in res.flags
    assert "travel" in res.orphaned_backend_keywords
    assert "used_for_function" in res.detected_cosmo_relations
    assert "non-slip yoga mat" in res.missing_sqp_intent_terms

    # Cluster sparse weekly panel rows by COSMO intent
    base = date(2026, 9, 6)
    panel = [
        UnifiedKeywordWeek(
            asin="B08XYZ123",
            search_query="magnesium for sleep" if i % 2 == 0 else "herbal sleep aid",
            week_start=base + timedelta(days=7 * i),
            search_volume=5000,
            sqp_impressions=1000,
            sqp_clicks=80,
            sqp_cart_adds=25,
            sqp_purchases=14,
            total_market_clicks=400,
            total_market_purchases=50,
            ad_impressions=500,
            ad_clicks=20,
            ad_spend=60.0,
            ad_orders=4,
            ad_sales=140.0,
            organic_clicks=60,
            organic_orders=10,
            organic_rank=max(1.0, 6.0 - i),
        )
        for i in range(5)
    ]
    clusters = cluster_panel_by_cosmo_intent(panel, category="supplements")
    assert len(clusters) == 1
    assert clusters[0].search_query == "used_for_function:sleep"
    assert clusters[0].weeks_observed == 5


def test_phase4_buybox_fba_business_report_and_funnel_bottlenecks(tmp_path: Path) -> None:
    ops = evaluate_buybox_and_promo_health(
        buy_box_pct=88.5,
        promo_days_last_30=12,
        days_of_inventory_supply=18,
    )
    assert ops.allow_bid_increases is False
    assert "BUY_BOX_DEGRADED" in ops.flags
    assert "PROMO_DEPENDENCY_RISK" in ops.flags
    assert "INVENTORY_CURTAILMENT_RISK" in ops.flags

    comp = compare_fba_vs_fbm_economics(
        selling_price=40.0,
        cogs=10.0,
        fba_fulfillment_fee=6.5,
        fba_inbound_placement_fee=1.2,
        fba_storage_fee_per_unit=0.5,
        fbm_shipping_cost=9.0,
        fbm_pick_pack_cost=2.0,
        monthly_fbm_units=40,
    )
    assert comp.fba_monthly_profit > comp.fbm_monthly_profit
    assert comp.recommended_mode == "HYBRID_FBA_WITH_FBM_BACKUP"

    # Business Report CSV parsing
    biz_csv = tmp_path / "business_report.csv"
    biz_csv.write_text(
        "(Child) ASIN,Sessions - Total,Featured Offer (Buy Box) Percentage,Unit Session Percentage,Units Ordered,Ordered Product Sales\n"
        "B08XYZ123,\"1,240\",96.5%,14.2%,176,\"$6,160.00\"\n",
        encoding="utf-8",
    )
    recs = parse_business_report_csv(biz_csv)
    assert len(recs) == 1
    assert recs[0].asin == "B08XYZ123"
    assert recs[0].buy_box_pct == pytest.approx(96.5)
    assert recs[0].ordered_product_sales == pytest.approx(6160.0)

    # SQP 3-stage funnel bottleneck diagnosis
    low_ctr_row = UnifiedKeywordWeek(
        asin="B08XYZ123",
        search_query="weak main image kw",
        week_start=date(2026, 10, 4),
        search_volume=10000,
        sqp_impressions=5000,
        sqp_clicks=25,  # 0.5% CTR
        sqp_cart_adds=10,
        sqp_purchases=5,
        total_market_clicks=500,
        total_market_purchases=60,
        ad_impressions=1000,
        ad_clicks=10,
        ad_spend=20.0,
        ad_orders=2,
        ad_sales=70.0,
        organic_clicks=15,
        organic_orders=3,
    )
    diags = diagnose_sqp_funnel_bottlenecks([low_ctr_row], star_rating=4.1)
    assert len(diags) == 1
    assert diags[0].bottleneck == "CTR_MAIN_IMAGE_OR_PRICE"
    assert diags[0].trust_tier == "BELOW_4_3_VISIBILITY_PENALTY"
