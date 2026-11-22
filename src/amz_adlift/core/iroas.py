"""
Causal iROAS, LTV-Adjusted Break-Even Economics & Target CPC Ceiling Calculator
(core/iroas.py).

Grounds Amazon PPC capital allocation in incremental economics rather than
platform-reported observational ROAS:
  - Break-even iROAS = 1 / gross_margin
  - Effective LTV Margin = margin * (1 + ntb_share * (ltv_repeat_multiplier - 1))
  - Target CPC Ceiling = cvr * target_acos * selling_price
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

VerdictLabel = Literal[
    "PROFITABLE_INCREMENTAL",
    "LTV_ONLY_PROFITABLE",
    "VALUE_DESTRUCTIVE",
]


class IROASEvaluation(BaseModel):
    """Causal iROAS and LTV-adjusted unit economics readout."""

    product_margin: float = Field(gt=0.0, le=1.0)
    observed_roas: float = Field(ge=0.0)
    causal_iroas: float = Field(ge=0.0)
    break_even_iroas: float = Field(gt=0.0)
    effective_ltv_margin: float = Field(gt=0.0)
    ltv_break_even_iroas: float = Field(gt=0.0)
    net_profit_per_ad_dollar: float
    ltv_net_profit_per_ad_dollar: float
    existing_customer_share: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    existing_customer_waste_flag: bool = False
    target_cpc_ceiling: Optional[float] = Field(default=None, ge=0.0)
    verdict: VerdictLabel
    summary: str


def compute_break_even_iroas(product_margin: float) -> float:
    """Break-even iROAS is strictly the reciprocal of pre-ad gross margin."""
    if product_margin <= 0.0 or product_margin > 1.0:
        raise ValueError("product_margin must be in (0.0, 1.0].")
    return 1.0 / product_margin


def compute_effective_ltv_margin(
    product_margin: float,
    ntb_share: float = 1.0,
    ltv_repeat_multiplier: float = 1.0,
) -> float:
    """
    Effective contribution margin per first-order revenue dollar when New-to-Brand
    buyers generate repeat purchases (typically 2.8x-4.5x in consumables).
    """
    if product_margin <= 0.0 or product_margin > 1.0:
        raise ValueError("product_margin must be in (0.0, 1.0].")
    clamped_ntb = max(0.0, min(1.0, float(ntb_share)))
    clamped_mult = max(1.0, float(ltv_repeat_multiplier))
    return product_margin * (1.0 + clamped_ntb * (clamped_mult - 1.0))


def compute_target_cpc_ceiling(
    cvr: float,
    target_acos: float,
    selling_price: float,
) -> float:
    """Exact maximum sustainable CPC: Target CPC = CVR * Target ACoS * Selling Price."""
    if cvr < 0.0 or target_acos < 0.0 or selling_price < 0.0:
        raise ValueError("cvr, target_acos, and selling_price must be non-negative.")
    return round(float(cvr) * float(target_acos) * float(selling_price), 4)


def evaluate_iroas_economics(
    *,
    incremental_revenue: float,
    incremental_spend: float,
    product_margin: float,
    observed_revenue: Optional[float] = None,
    observed_spend: Optional[float] = None,
    ntb_share: float = 1.0,
    ltv_repeat_multiplier: float = 1.0,
    cvr: Optional[float] = None,
    selling_price: Optional[float] = None,
) -> IROASEvaluation:
    """
    Evaluate whether a campaign or keyword creates net enterprise profit on
    both first-order iROAS and LTV-adjusted iROAS bases.
    """
    if incremental_spend <= 0.0:
        raise ValueError("incremental_spend must be positive.")

    causal_iroas = max(0.0, float(incremental_revenue) / float(incremental_spend))
    if observed_revenue is not None and observed_spend and observed_spend > 0.0:
        observed_roas = max(0.0, float(observed_revenue) / float(observed_spend))
    else:
        observed_roas = causal_iroas

    be_iroas = compute_break_even_iroas(product_margin)
    eff_ltv_margin = compute_effective_ltv_margin(
        product_margin, ntb_share=ntb_share, ltv_repeat_multiplier=ltv_repeat_multiplier
    )
    ltv_be_iroas = 1.0 / eff_ltv_margin

    net_profit_per_dollar = causal_iroas * product_margin - 1.0
    ltv_net_profit_per_dollar = causal_iroas * eff_ltv_margin - 1.0

    existing_share = round(1.0 - max(0.0, min(1.0, float(ntb_share))), 4)
    waste_flag = existing_share >= 0.33

    cpc_ceiling: Optional[float] = None
    if cvr is not None and selling_price is not None:
        cpc_ceiling = compute_target_cpc_ceiling(cvr, eff_ltv_margin, selling_price)

    if causal_iroas >= be_iroas:
        verdict: VerdictLabel = "PROFITABLE_INCREMENTAL"
        summary = (
            f"Causal iROAS {causal_iroas:.2f}x exceeds first-order break-even "
            f"{be_iroas:.2f}x (+${net_profit_per_dollar:.2f} net profit per ad dollar)."
        )
    elif causal_iroas >= ltv_be_iroas:
        verdict = "LTV_ONLY_PROFITABLE"
        summary = (
            f"First-order iROAS {causal_iroas:.2f}x is below {be_iroas:.2f}x break-even, "
            f"but LTV-adjusted break-even ({ltv_be_iroas:.2f}x at {ltv_repeat_multiplier:.1f}x repeat) "
            f"is profitable (+${ltv_net_profit_per_dollar:.2f}/$)."
        )
    else:
        verdict = "VALUE_DESTRUCTIVE"
        summary = (
            f"Causal iROAS {causal_iroas:.2f}x destroys capital even after LTV adjustment "
            f"(needs >= {ltv_be_iroas:.2f}x; observed ROAS {observed_roas:.2f}x overstates lift)."
        )

    return IROASEvaluation(
        product_margin=round(product_margin, 4),
        observed_roas=round(observed_roas, 4),
        causal_iroas=round(causal_iroas, 4),
        break_even_iroas=round(be_iroas, 4),
        effective_ltv_margin=round(eff_ltv_margin, 4),
        ltv_break_even_iroas=round(ltv_be_iroas, 4),
        net_profit_per_ad_dollar=round(net_profit_per_dollar, 4),
        ltv_net_profit_per_ad_dollar=round(ltv_net_profit_per_dollar, 4),
        existing_customer_share=existing_share,
        existing_customer_waste_flag=waste_flag,
        target_cpc_ceiling=cpc_ceiling,
        verdict=verdict,
        summary=summary,
    )
