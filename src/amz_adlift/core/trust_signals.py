"""
SQP 3-Stage Funnel Bottleneck & Algorithmic Trust Diagnostics (core/trust_signals.py).

Decomposes each keyword's SQP funnel into:
  1. CTR (Impression -> Click) vs. market
  2. ATC Rate (Click -> Cart Add) vs. market
  3. Checkout Completion (Cart Add -> Purchase) vs. market
and pairs it with review rating tier thresholds (4.7+ high visibility vs. <4.3 risk).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Literal, Optional

from pydantic import BaseModel

from amz_adlift.contracts.schemas import UnifiedKeywordWeek

BottleneckStage = Literal[
    "CTR_MAIN_IMAGE_OR_PRICE",
    "ATC_LISTING_OR_TRUST",
    "CHECKOUT_BUYBOX_OR_SHIPPING",
    "HEALTHY",
]


class KeywordFunnelDiagnosis(BaseModel):
    """3-stage SQP funnel diagnostic for a single (asin, search_query)."""

    asin: str
    search_query: str
    brand_ctr: float
    brand_atc_rate: float
    brand_checkout_rate: float
    market_purchase_per_click: float
    brand_purchase_per_click: float
    cvr_index_vs_market: float
    bottleneck: BottleneckStage
    trust_tier: Optional[str] = None
    recommendation: str


def diagnose_sqp_funnel_bottlenecks(
    panel: Iterable[UnifiedKeywordWeek],
    *,
    star_rating: Optional[float] = None,
) -> list[KeywordFunnelDiagnosis]:
    """Pinpoint the exact SQP conversion bottleneck for each (asin, search_query)."""
    by_kw: dict[tuple[str, str], list[UnifiedKeywordWeek]] = defaultdict(list)
    for row in panel:
        by_kw[(row.asin, row.search_query)].append(row)

    trust_tier: Optional[str] = None
    if star_rating is not None:
        if star_rating >= 4.7:
            trust_tier = "HIGH_VISIBILITY_4_7_PLUS"
        elif star_rating < 4.3:
            trust_tier = "BELOW_4_3_VISIBILITY_PENALTY"
        else:
            trust_tier = "STANDARD_4_3_TO_4_69"

    results: list[KeywordFunnelDiagnosis] = []
    for (asin, kw), rows in sorted(by_kw.items()):
        imp = sum(r.sqp_impressions for r in rows)
        clk = sum(r.sqp_clicks for r in rows)
        atc = sum(r.sqp_cart_adds for r in rows)
        pur = sum(r.sqp_purchases for r in rows)
        mkt_clk = sum(r.total_market_clicks for r in rows)
        mkt_pur = sum(r.total_market_purchases for r in rows)

        ctr = clk / max(1, imp)
        atc_rate = atc / max(1, clk)
        chk_rate = pur / max(1, atc) if atc > 0 else (pur / max(1, clk))
        brand_cvr = pur / max(1, clk)
        mkt_cvr = (mkt_pur / max(1, mkt_clk)) if mkt_clk > 0 else brand_cvr
        cvr_idx = brand_cvr / max(1e-6, mkt_cvr) if mkt_cvr > 0 else 1.0

        if ctr < 0.015:
            bottleneck: BottleneckStage = "CTR_MAIN_IMAGE_OR_PRICE"
            rec = (
                "Low SERP CTR (<1.5%). Test main image, 75-char title clarity, "
                "or headline price via Manage Your Experiments (MYE)."
            )
        elif atc_rate < 0.15:
            bottleneck = "ATC_LISTING_OR_TRUST"
            rec = (
                "Weak Click-to-Cart rate (<15%). Upgrade Item Highlights, above-the-fold "
                "imagery, A+ Content, or address review objections."
            )
        elif chk_rate < 0.35 or cvr_idx < 0.70:
            bottleneck = "CHECKOUT_BUYBOX_OR_SHIPPING"
            rec = (
                "High cart abandonment or sub-market CVR. Check Buy Box share, "
                "Prime delivery speed (30d FBA stock), and checkout price parity."
            )
        else:
            bottleneck = "HEALTHY"
            rec = "Funnel stages healthy relative to market."

        results.append(
            KeywordFunnelDiagnosis(
                asin=asin,
                search_query=kw,
                brand_ctr=round(ctr, 4),
                brand_atc_rate=round(atc_rate, 4),
                brand_checkout_rate=round(chk_rate, 4),
                market_purchase_per_click=round(mkt_cvr, 4),
                brand_purchase_per_click=round(brand_cvr, 4),
                cvr_index_vs_market=round(cvr_idx, 3),
                bottleneck=bottleneck,
                trust_tier=trust_tier,
                recommendation=rec,
            )
        )
    return results
