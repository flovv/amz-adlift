"""Organic vs. Paid Funnel Isolation (core/decomposition.py)."""

from __future__ import annotations

from typing import Iterable

from amz_adlift.contracts.schemas import UnifiedKeywordWeek


def decompose_observation(
    sqp_clicks: int,
    sqp_purchases: int,
    ad_clicks: int,
    ad_orders: int,
) -> tuple[int, int, bool, float]:
    """
    Isolate pure organic clicks, pure organic orders, attribution window mismatch flag,
    and true paid share of brand orders for a single (asin, search_query, week_start) row.

    Formulas:
        - organic_clicks = max(0, sqp_clicks - ad_clicks)
        - organic_orders = max(0, sqp_purchases - ad_orders)
        - attribution_window_gap = (ad_orders > sqp_purchases)
        - paid_share = ad_orders / max(1, ad_orders + organic_orders)
    """
    organic_clicks = max(0, int(sqp_clicks) - int(ad_clicks))
    organic_orders = max(0, int(sqp_purchases) - int(ad_orders))
    attribution_window_gap = bool(int(ad_orders) > int(sqp_purchases))
    total_brand_orders = max(1, int(ad_orders) + organic_orders)
    paid_share = min(1.0, float(ad_orders) / float(total_brand_orders))
    return organic_clicks, organic_orders, attribution_window_gap, paid_share


def decompose_panel(panel: Iterable[UnifiedKeywordWeek]) -> list[UnifiedKeywordWeek]:
    """
    Recompute and enforce funnel decomposition invariants across a sequence of
    UnifiedKeywordWeek observations.
    """
    updated: list[UnifiedKeywordWeek] = []
    for row in panel:
        org_clicks, org_orders, gap, _ = decompose_observation(
            sqp_clicks=row.sqp_clicks,
            sqp_purchases=row.sqp_purchases,
            ad_clicks=row.ad_clicks,
            ad_orders=row.ad_orders,
        )
        updated.append(
            row.model_copy(
                update={
                    "organic_clicks": org_clicks,
                    "organic_orders": org_orders,
                    "attribution_window_gap": gap,
                }
            )
        )
    return updated
