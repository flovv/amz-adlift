"""
Featured Offer (Buy Box), >30% Promo-Dependency, <30-Day Stockout Guardrails,
and 2026 FBA vs. FBM Unit Economics Calculator (core/buybox_guard.py).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

BUY_BOX_MIN_HEALTHY_PCT: float = 95.0
PROMO_DEPENDENCY_MAX_SHARE: float = 0.30
INVENTORY_MIN_DAYS_SUPPLY: float = 30.0


class OperationalHealthReport(BaseModel):
    """Operational guardrails checked before scaling PPC bids or exporting bulksheets."""

    buy_box_pct: float
    promo_day_share: float
    days_of_inventory_supply: Optional[float] = None
    allow_bid_increases: bool
    flags: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class FulfillmentComparison(BaseModel):
    """2026 FBA vs. FBM unit and monthly profit comparison."""

    fba_unit_profit: float
    fbm_unit_profit: float
    fba_monthly_units: float
    fbm_monthly_units: float
    fba_monthly_profit: float
    fbm_monthly_profit: float
    recommended_mode: Literal["FBA", "FBM", "HYBRID_FBA_WITH_FBM_BACKUP"]
    summary: str


def evaluate_buybox_and_promo_health(
    *,
    buy_box_pct: float,
    promo_days_last_30: int = 0,
    days_of_inventory_supply: Optional[float] = None,
) -> OperationalHealthReport:
    """
    Evaluate Featured Offer stability, promo-dependency risk (>30% of days),
    and FBA regional inventory curtailment risk (<30 days of supply).
    """
    bb = float(buy_box_pct)
    if bb <= 1.0:
        bb *= 100.0
    promo_share = max(0.0, min(1.0, float(promo_days_last_30) / 30.0))

    flags: list[str] = []
    recs: list[str] = []
    allow_increases = True

    if bb < BUY_BOX_MIN_HEALTHY_PCT:
        flags.append("BUY_BOX_DEGRADED")
        allow_increases = False
        recs.append(
            f"Featured Offer share is {bb:.1f}% (<{BUY_BOX_MIN_HEALTHY_PCT:.0f}%). "
            "Cap or freeze PPC bid increases and check cross-channel price parity."
        )

    if promo_share > PROMO_DEPENDENCY_MAX_SHARE:
        flags.append("PROMO_DEPENDENCY_RISK")
        recs.append(
            f"Promotions active on {promo_share:.0%} of last 30 days (>30%). "
            "Excessive discounting degrades price-elasticity trust and risks a 20%-35% "
            "organic rank drop when returning to full price."
        )

    if days_of_inventory_supply is not None and days_of_inventory_supply < INVENTORY_MIN_DAYS_SUPPLY:
        flags.append("INVENTORY_CURTAILMENT_RISK")
        allow_increases = False
        recs.append(
            f"Only {days_of_inventory_supply:.0f} days of FBA supply (<30 days). "
            "Amazon may curtail regional distribution; pause bid expansion and keep an FBM backup offer active."
        )

    return OperationalHealthReport(
        buy_box_pct=round(bb, 2),
        promo_day_share=round(promo_share, 4),
        days_of_inventory_supply=days_of_inventory_supply,
        allow_bid_increases=allow_increases,
        flags=flags,
        recommendations=recs,
    )


def compare_fba_vs_fbm_economics(
    *,
    selling_price: float,
    cogs: float,
    fba_fulfillment_fee: float,
    fba_inbound_placement_fee: float = 0.0,
    fba_storage_fee_per_unit: float = 0.0,
    fbm_shipping_cost: float = 0.0,
    fbm_pick_pack_cost: float = 0.0,
    referral_fee_pct: float = 0.15,
    fba_cvr_lift_pct: float = 0.35,
    monthly_fbm_units: float = 30.0,
) -> FulfillmentComparison:
    """Compare net unit & monthly profit for FBA (with 2026 fees + Prime CVR lift) vs. FBM."""
    referral = selling_price * referral_fee_pct
    fba_unit = (
        selling_price
        - cogs
        - referral
        - fba_fulfillment_fee
        - fba_inbound_placement_fee
        - fba_storage_fee_per_unit
    )
    fbm_unit = selling_price - cogs - referral - fbm_shipping_cost - fbm_pick_pack_cost

    fbm_units = max(0.0, float(monthly_fbm_units))
    fba_units = fbm_units * (1.0 + max(0.0, float(fba_cvr_lift_pct)))
    fba_monthly = fba_unit * fba_units
    fbm_monthly = fbm_unit * fbm_units

    if fba_monthly > fbm_monthly * 1.10 and fba_unit > 0.0:
        mode: Literal["FBA", "FBM", "HYBRID_FBA_WITH_FBM_BACKUP"] = "HYBRID_FBA_WITH_FBM_BACKUP"
        summary = (
            f"FBA earns ${fba_monthly:.2f}/mo vs. FBM ${fbm_monthly:.2f}/mo "
            f"(+{fba_cvr_lift_pct:.0%} Prime CVR lift). Use FBA as primary with an FBM backup offer."
        )
    elif fbm_monthly >= fba_monthly:
        mode = "FBM"
        summary = (
            f"FBM earns ${fbm_monthly:.2f}/mo (${fbm_unit:.2f}/unit) vs. FBA "
            f"${fba_monthly:.2f}/mo (${fba_unit:.2f}/unit). Route heavy/slow-moving SKU via FBM."
        )
    else:
        mode = "FBA"
        summary = f"FBA edges out FBM (${fba_monthly:.2f}/mo vs. ${fbm_monthly:.2f}/mo)."

    return FulfillmentComparison(
        fba_unit_profit=round(fba_unit, 2),
        fbm_unit_profit=round(fbm_unit, 2),
        fba_monthly_units=round(fba_units, 1),
        fbm_monthly_units=round(fbm_units, 1),
        fba_monthly_profit=round(fba_monthly, 2),
        fbm_monthly_profit=round(fbm_monthly, 2),
        recommended_mode=mode,
        summary=summary,
    )
