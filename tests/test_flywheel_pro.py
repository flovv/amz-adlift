"""
Synthetic Flywheel Elasticity Recovery & Cython Wheel Security Audit Tests
(tests/test_flywheel_pro.py).
"""

import glob
import math
import random
import zipfile
from pathlib import Path

import pytest

amz_flywheel_pro = pytest.importorskip(
    "amz_flywheel_pro",
    reason="Optional private amz_flywheel_pro Cython extension not installed",
)
from amz_flywheel_pro import (
    allocate_portfolio_budget,
    compute_halo_acos,
    compute_marginal_response_curve,
    compute_velocity_state,
    fit_keyword_elasticity,
    predict_rank_trajectory,
    read_license_cache,
    shrink_elasticity,
    simulate_bid_cut,
    validate_license_key,
)


def test_synthetic_16_week_flywheel_elasticity_recovery() -> None:
    """
    Section 7 Acceptance Criterion:
    Generates a 16-week synthetic keyword panel with known true rank elasticity
    theta_true = 0.42 and carry-over lambda_true = 0.60; verifies the Cython
    solver recovers theta_hat / theta_eb within +/- 0.06 and accurately predicts
    rank decay under a simulated 50% spend cut.
    """
    theta_true = 0.42
    lambda_true = 0.60
    alpha_true = 3.20
    gamma_true = 0.12
    n_weeks = 16

    rng = random.Random(20261113)
    ad_orders: list[float] = []
    organic_orders: list[float] = []
    search_volumes: list[float] = []

    for t in range(n_weeks):
        # Ramp up PPC velocity over weeks 0..10, then hold steady
        paid_t = 6.0 + 2.8 * t + rng.uniform(-0.8, 0.8)
        org_t = 4.0 + 1.5 * t + rng.uniform(-0.5, 0.5)
        vol_t = 15000.0 + 200.0 * math.sin(t)
        ad_orders.append(round(paid_t, 2))
        organic_orders.append(round(org_t, 2))
        search_volumes.append(round(vol_t, 1))

    v_true = compute_velocity_state(ad_orders, organic_orders, lambda_true)
    organic_ranks: list[float] = []
    for t in range(n_weeks):
        m_t = math.log(1.0 + search_volumes[t])
        noise = rng.gauss(0.0, 0.012)
        log_r = alpha_true - theta_true * math.log(1.0 + v_true[t]) + gamma_true * m_t + noise
        organic_ranks.append(round(math.exp(log_r), 4))

    fit = fit_keyword_elasticity(
        ad_orders=ad_orders,
        organic_orders=organic_orders,
        organic_ranks=organic_ranks,
        search_volumes=search_volumes,
        category="pet_supplies",
    )

    assert abs(fit["theta_hat"] - theta_true) <= 0.06
    assert abs(fit["theta_eb"] - theta_true) <= 0.06
    assert abs(fit["lambda_decay"] - lambda_true) <= 0.10

    # Verify rank decay prediction under a simulated 50% PPC spend cut
    sim = simulate_bid_cut(
        theta_eb=fit["theta_eb"],
        lambda_decay=fit["lambda_decay"],
        current_rank=organic_ranks[-1],
        current_velocity=fit["terminal_velocity"],
        baseline_paid_orders=ad_orders[-1],
        baseline_organic_orders=organic_orders[-1],
        baseline_weekly_spend=180.0,
        avg_order_value=38.0,
        product_margin=0.38,
        spend_change_pct=-0.50,
        horizon_weeks=3,
    )

    projected = sim["projected_ranks"]
    assert len(projected) == 3
    # Under a 50% spend cut, rank number must decay (increase numerically away from #1)
    assert projected[0] > organic_ranks[-1]
    assert projected[1] > projected[0]
    assert projected[2] > projected[1]
    assert sim["organic_profit_loss_21d"] > 0.0


def test_empirical_bayes_short_history_shrinkage() -> None:
    """Verifies Empirical Bayes shrinkage pulls noisy short-history estimates toward mu_cat."""
    shrunk_short = shrink_elasticity(theta_hat=0.95, se2_hat=0.08, n_weeks=4, category="general")
    shrunk_long = shrink_elasticity(theta_hat=0.95, se2_hat=0.08, n_weeks=16, category="general")
    # Short history (4w) is pulled much closer to mu_cat (0.40) than 16w history
    assert abs(shrunk_short - 0.40) < abs(shrunk_long - 0.40)


def test_halo_acos_and_hmac_license_cache(tmp_path: Path) -> None:
    """Verifies Halo-Adjusted Break-Even ACoS and 24-hour HMAC-SHA256 license cache."""
    halo = compute_halo_acos(
        theta_eb=0.42,
        lambda_decay=0.60,
        product_margin=0.35,
        recent_ad_spend=120.0,
        recent_ad_sales=360.0,
        recent_ad_orders=10.0,
        recent_organic_orders=16.0,
        recent_organic_rank=5.0,
    )
    assert halo["halo_break_even_acos"] > halo["product_margin"]
    assert halo["organic_multiplier_21d"] > 0.0

    cache_file = tmp_path / "license.cache"
    res1 = validate_license_key(
        "AMZ_FW_PRO_AGENCY_998877",
        cache_path=str(cache_file),
    )
    assert res1["valid"] is True
    assert cache_file.exists()

    # Subsequent call hits sub-millisecond local HMAC cache
    res2 = read_license_cache(
        api_key="AMZ_FW_PRO_AGENCY_998877",
        cache_path=str(cache_file),
    )
    assert res2 is not None
    assert res2["source"] == "hmac_cache"


def test_marginal_response_curve_and_equimarginal_allocator() -> None:
    """
    Verifies Hill-saturated Marginal Response Curves (mROAS < Average ROAS due to
    diminishing returns) and Equimarginal Portfolio Budget Allocation shifting
    spend from saturated #1 rank terms to high-leverage rank #7 flywheel terms.
    """
    # Keyword A: Saturated #1 rank (Cannibalized Rent)
    curve_rent = compute_marginal_response_curve(
        theta_eb=0.10,
        lambda_decay=0.50,
        product_margin=0.38,
        current_weekly_spend=450.0,
        current_ad_sales=1100.0,
        current_ad_orders=30.0,
        current_organic_orders=45.0,
        current_organic_rank=1.0,
    )
    # Marginal paid ROAS must be strictly lower than Average paid ROAS under Hill saturation
    assert curve_rent["marginal_paid_roas"] < curve_rent["average_paid_roas"]
    # At rank #1.0, SERP ceiling is reached so marginal organic lift is zero
    assert curve_rent["marginal_organic_roas"] < 0.05
    assert curve_rent["marginal_net_profit_per_dollar"] < 0.0
    assert curve_rent["optimal_weekly_spend"] < 450.0

    # Keyword B: Underspent Rank #7 (Flywheel Leverage)
    curve_flywheel = compute_marginal_response_curve(
        theta_eb=0.48,
        lambda_decay=0.65,
        product_margin=0.38,
        current_weekly_spend=120.0,
        current_ad_sales=480.0,
        current_ad_orders=14.0,
        current_organic_orders=18.0,
        current_organic_rank=7.0,
    )
    assert curve_flywheel["marginal_organic_roas"] > 0.25
    assert curve_flywheel["marginal_total_roas"] > curve_flywheel["break_even_roas_target"]
    assert curve_flywheel["marginal_net_profit_per_dollar"] > 0.0

    # Portfolio Reallocation across both keywords
    portfolio = allocate_portfolio_budget(
        keyword_specs=[
            {
                "asin": "B08XYZ123",
                "search_query": "magnesium glycinate 400mg",
                "quadrant": "CANNIBALIZED_RENT",
                "current_weekly_spend": 450.0,
                "current_ad_sales": 1100.0,
                "current_ad_orders": 30.0,
                "current_organic_orders": 45.0,
                "current_organic_rank": 1.0,
                "theta_eb": 0.10,
                "lambda_decay": 0.50,
            },
            {
                "asin": "B08XYZ123",
                "search_query": "organic sleep aid capsules",
                "quadrant": "FLYWHEEL_LEVERAGE",
                "current_weekly_spend": 120.0,
                "current_ad_sales": 480.0,
                "current_ad_orders": 14.0,
                "current_organic_orders": 18.0,
                "current_organic_rank": 7.0,
                "theta_eb": 0.48,
                "lambda_decay": 0.65,
            },
        ],
        total_weekly_budget=570.0,
        product_margin=0.38,
    )
    allocs = {a["search_query"]: a for a in portfolio["allocations"]}
    # Budget must shift from Cannibalized Rent to Flywheel Leverage
    assert allocs["magnesium glycinate 400mg"]["spend_delta"] < 0.0
    assert allocs["organic sleep aid capsules"]["spend_delta"] > 0.0
    assert portfolio["projected_weekly_profit_lift"] > 0.0


def test_wheel_security_audit() -> None:
    """
    Section 7 Acceptance Criterion (Wheel Security Audit):
    Unzips every .whl built for amz_flywheel_pro and asserts zero .py or .pyx
    files exist except amz_flywheel_pro/__init__.py.
    """
    wheel_paths = glob.glob("/home/antigravity/amz-flywheel-pro-private/dist/*.whl")
    assert wheel_paths, "Expected at least one built wheel in amz-flywheel-pro-private/dist/"

    for whl in wheel_paths:
        with zipfile.ZipFile(whl, "r") as zf:
            names = zf.namelist()
            leaked_sources = [
                name
                for name in names
                if name.endswith((".py", ".pyx", ".pxd", ".c"))
                and name != "amz_flywheel_pro/__init__.py"
            ]
            assert not leaked_sources, f"Leaked source files in {whl}: {leaked_sources}"
            so_files = [name for name in names if name.endswith((".so", ".pyd"))]
            assert len(so_files) == 4, f"Expected 4 compiled Cython extensions, found: {so_files}"
