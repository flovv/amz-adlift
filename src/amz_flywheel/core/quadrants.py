"""Deterministic 4-Quadrant Diagnostic Classifier (core/quadrants.py)."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Iterable, Optional

from amz_flywheel.contracts.exceptions import InsufficientHistoryError
from amz_flywheel.contracts.schemas import (
    KeywordQuadrantDiagnostic,
    QuadrantLabel,
    UnifiedKeywordWeek,
)

DEFAULT_CATEGORY_MEDIAN_CVR: dict[str, float] = {
    "general": 0.10,
    "supplements": 0.14,
    "electronics": 0.08,
    "home_kitchen": 0.11,
    "beauty": 0.13,
    "pet_supplies": 0.13,
}


def compute_ols_slope(values: list[float]) -> float:
    """Compute Ordinary Least Squares slope dY/dt for equally spaced weekly observations."""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / float(n)
    num = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    if den <= 1e-12:
        return 0.0
    return num / den


def compute_pearson_corr(x: list[float], y: list[float]) -> float:
    """Compute Pearson correlation coefficient between two series of equal length."""
    n = min(len(x), len(y))
    if n < 2:
        return 0.0
    x_s = x[:n]
    y_s = y[:n]
    x_mean = sum(x_s) / float(n)
    y_mean = sum(y_s) / float(n)
    cov = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x_s, y_s))
    var_x = sum((xi - x_mean) ** 2 for xi in x_s)
    var_y = sum((yi - y_mean) ** 2 for yi in y_s)
    denom = math.sqrt(var_x * var_y)
    if denom <= 1e-12:
        # If paid orders were sustained at a positive constant level while organic orders grew,
        # treat correlation with time/growth as positive flywheel momentum
        if sum(x_s) > 0 and compute_ols_slope(y_s) > 0:
            return 0.50
        return 0.0
    return max(-1.0, min(1.0, cov / denom))


def _brand_click_share(row: UnifiedKeywordWeek) -> float:
    """Compute SQP Brand/ASIN click share for a weekly observation."""
    denom = row.total_market_clicks if row.total_market_clicks > 0 else max(1, row.search_volume)
    return float(row.sqp_clicks) / float(denom)


def classify_keyword_series(
    history: list[UnifiedKeywordWeek],
    account_spend_p75: float = 50.0,
    category_median_cvr: float = 0.10,
    strict: bool = False,
) -> KeywordQuadrantDiagnostic:
    """
    Classify a single `(asin, search_query)` time series into one of the 4 Flywheel quadrants.

    Requires at least 4 weeks of aligned history. If `strict=True`, raises
    `InsufficientHistoryError` when fewer than 4 weeks are present.
    """
    if not history:
        raise InsufficientHistoryError("Cannot classify an empty keyword history.")

    ordered = sorted(history, key=lambda r: r.week_start)
    asin = ordered[0].asin
    query = ordered[0].search_query
    n_weeks = len(ordered)

    if n_weeks < 4:
        if strict:
            raise InsufficientHistoryError(
                f"Keyword {query!r} ({asin}) has only {n_weeks} weeks of history; "
                "at least 4 aligned weeks are required."
            )
        return KeywordQuadrantDiagnostic(
            asin=asin,
            search_query=query,
            weeks_observed=n_weeks,
            quadrant="INSUFFICIENT_DATA",
            diagnostic_summary=f"Insufficient history ({n_weeks}/4 weeks minimum).",
        )

    trailing_4w = ordered[-4:]
    trailing_8w = ordered[-8:]

    ranks_4w = [r.organic_rank for r in trailing_4w if r.organic_rank is not None]
    ranks_8w = [r.organic_rank for r in trailing_8w if r.organic_rank is not None]

    median_rank_4w = float(statistics.median(ranks_4w)) if ranks_4w else None
    slope_8w = compute_ols_slope([float(x) for x in ranks_8w]) if len(ranks_8w) >= 2 else None
    slope_4w = compute_ols_slope([float(x) for x in ranks_4w]) if len(ranks_4w) >= 2 else None
    rank_slope = slope_8w if slope_8w is not None else slope_4w

    org_clicks_4w = sum(r.organic_clicks for r in trailing_4w)
    org_orders_4w = sum(r.organic_orders for r in trailing_4w)
    organic_cvr_4w = float(org_orders_4w) / float(max(1, org_clicks_4w))

    sqp_clicks_4w = sum(r.sqp_clicks for r in trailing_4w)
    sqp_purchases_4w = sum(r.sqp_purchases for r in trailing_4w)
    sqp_cvr_4w = float(sqp_purchases_4w) / float(max(1, sqp_clicks_4w))

    cum_spend_4w = sum(r.ad_spend for r in trailing_4w)
    weekly_spend_avg = cum_spend_4w / 4.0

    # Lagged paid orders O^{ads}_{t-1} vs subsequent organic orders O^{org}_{t}
    lagged_paid = [float(r.ad_orders) for r in trailing_8w[:-1]]
    subseq_org = [float(r.organic_orders) for r in trailing_8w[1:]]
    lag_corr = compute_pearson_corr(lagged_paid, subseq_org)

    # Brand click share trend over trailing 4 weeks
    click_shares_4w = [_brand_click_share(r) for r in trailing_4w]
    click_share_slope = compute_ols_slope(click_shares_4w)
    click_share_declining = (
        click_share_slope < 0.0 or click_shares_4w[-1] < click_shares_4w[0]
    )

    total_ad_orders_4w = sum(r.ad_orders for r in trailing_4w)
    true_paid_share = float(total_ad_orders_4w) / float(
        max(1, total_ad_orders_4w + org_orders_4w)
    )

    high_spend_flag = weekly_spend_avg >= 50.0 or (
        account_spend_p75 > 0.0 and weekly_spend_avg >= account_spend_p75
    )

    quadrant: QuadrantLabel = "INSUFFICIENT_DATA"
    summary = ""

    # 1. CANNIBALIZED_RENT
    if (
        median_rank_4w is not None
        and median_rank_4w <= 2.5
        and organic_cvr_4w >= 0.12
        and high_spend_flag
    ):
        quadrant = "CANNIBALIZED_RENT"
        summary = (
            "Brand is paying CPC rent on clicks it already owns organically at the top of SERP "
            f"(median rank #{median_rank_4w:.1f}, pure organic CVR {organic_cvr_4w:.1%})."
        )
    # 2. FLYWHEEL_LEVERAGE
    elif (
        rank_slope is not None
        and rank_slope <= -0.5
        and lag_corr >= 0.35
    ):
        quadrant = "FLYWHEEL_LEVERAGE"
        summary = (
            f"Paid velocity is actively accelerating organic rank ({rank_slope:+.2f} pos/wk) "
            f"with lagged paid-to-organic order correlation r={lag_corr:.2f}."
        )
    # 3. TREADMILL_DEAD_WEIGHT
    elif (
        cum_spend_4w >= 100.0
        and (rank_slope is None or rank_slope > -0.2)
        and (median_rank_4w is None or median_rank_4w > 10.0)
        and sqp_cvr_4w < 0.50 * category_median_cvr
    ):
        quadrant = "TREADMILL_DEAD_WEIGHT"
        summary = (
            f"Non-converting spend sink (${cum_spend_4w:.2f} 4w spend, rank #{(median_rank_4w or 305.0):.1f}, "
            f"SQP CVR {sqp_cvr_4w:.1%} below 50% of category median)."
        )
    # 4. AT_RISK_DECAY
    elif (
        slope_4w is not None
        and slope_4w >= 0.75
        and click_share_declining
    ):
        quadrant = "AT_RISK_DECAY"
        summary = (
            f"Losing organic ground: rank slipping {slope_4w:+.2f} pos/wk with declining "
            "SQP brand click share."
        )
    else:
        # Secondary best-fit diagnostic assignment when 4+ weeks exist
        if median_rank_4w is not None and median_rank_4w <= 2.5 and weekly_spend_avg > 0:
            quadrant = "CANNIBALIZED_RENT"
            summary = "Top-of-SERP organic position with overlapping paid spend."
        elif rank_slope is not None and rank_slope < -0.2:
            quadrant = "FLYWHEEL_LEVERAGE"
            summary = "Positive organic rank trajectory supported by paid velocity."
        elif slope_4w is not None and slope_4w > 0.25:
            quadrant = "AT_RISK_DECAY"
            summary = "Slipping organic rank position over trailing 4 weeks."
        else:
            quadrant = "TREADMILL_DEAD_WEIGHT"
            summary = "Stagnant organic rank trajectory relative to ad spend."

    amc_shares = [r.amc_ntb_share for r in trailing_4w if r.amc_ntb_share is not None]
    amc_ntb_share_4w = (
        round(sum(amc_shares) / float(len(amc_shares)), 4) if amc_shares else None
    )

    # Adversarial Red-Team / Econometric Sanity Flags
    red_team_flags: list[str] = []
    if (
        median_rank_4w is not None
        and median_rank_4w <= 3.0
        and true_paid_share > 0.80
    ):
        red_team_flags.append(
            "OVER_ATTRIBUTION_GT_80PCT_ON_TOP_ORGANIC_RANK"
        )
    gap_weeks = sum(1 for r in trailing_4w if r.attribution_window_gap)
    if gap_weeks >= 2:
        red_team_flags.append(
            "ATTRIBUTION_WINDOW_HALO_DISTORTION"
        )
    if (
        amc_ntb_share_4w is not None
        and amc_ntb_share_4w < 0.20
        and weekly_spend_avg >= 50.0
    ):
        red_team_flags.append(
            "LOW_AMC_NTB_REPEAT_CUSTOMER_CANNIBALIZATION"
        )
    if n_weeks < 8:
        red_team_flags.append(
            "SHORT_HISTORY_EMPIRICAL_BAYES_SHRINKAGE_ACTIVE"
        )

    return KeywordQuadrantDiagnostic(
        asin=asin,
        search_query=query,
        weeks_observed=n_weeks,
        quadrant=quadrant,
        median_organic_rank_4w=round(median_rank_4w, 2) if median_rank_4w is not None else None,
        organic_cvr_4w=round(organic_cvr_4w, 4),
        sqp_cvr_4w=round(sqp_cvr_4w, 4),
        weekly_ad_spend_avg=round(weekly_spend_avg, 2),
        cumulative_ad_spend_4w=round(cum_spend_4w, 2),
        rank_velocity_slope=round(rank_slope, 4) if rank_slope is not None else None,
        lagged_paid_to_organic_corr=round(lag_corr, 4),
        brand_click_share_slope=round(click_share_slope, 5),
        true_paid_order_share=round(true_paid_share, 4),
        amc_ntb_share_4w=amc_ntb_share_4w,
        red_team_flags=red_team_flags,
        diagnostic_summary=summary,
    )


def classify_panel(
    panel: Iterable[UnifiedKeywordWeek],
    category: str = "general",
    strict: bool = False,
) -> list[KeywordQuadrantDiagnostic]:
    """
    Group a `UnifiedKeywordWeek` panel by `(asin, search_query)` and run the
    deterministic 4-quadrant diagnostic classifier across all keywords.
    """
    grouped: dict[tuple[str, str], list[UnifiedKeywordWeek]] = defaultdict(list)
    for row in panel:
        grouped[(row.asin, row.search_query)].append(row)

    if not grouped:
        return []

    # Compute account-level 75th percentile weekly spend and empirical median SQP CVR
    weekly_spends: list[float] = []
    keyword_cvrs: list[float] = []
    for rows in grouped.values():
        trailing = sorted(rows, key=lambda r: r.week_start)[-4:]
        weekly_spends.append(sum(r.ad_spend for r in trailing) / float(len(trailing)))
        clicks = sum(r.sqp_clicks for r in trailing)
        purchases = sum(r.sqp_purchases for r in trailing)
        if clicks > 0 and purchases > 0:
            keyword_cvrs.append(float(purchases) / float(clicks))

    sorted_spends = sorted(weekly_spends)
    p75_idx = int(0.75 * (len(sorted_spends) - 1))
    account_spend_p75 = max(50.0, sorted_spends[p75_idx]) if sorted_spends else 50.0

    cat_cvr = DEFAULT_CATEGORY_MEDIAN_CVR.get(category.lower(), 0.10)
    if len(keyword_cvrs) >= 3:
        cat_cvr = max(cat_cvr, float(statistics.median(keyword_cvrs)))

    diagnostics: list[KeywordQuadrantDiagnostic] = []
    for key in sorted(grouped.keys()):
        diagnostics.append(
            classify_keyword_series(
                grouped[key],
                account_spend_p75=account_spend_p75,
                category_median_cvr=cat_cvr,
                strict=strict,
            )
        )
    return diagnostics
