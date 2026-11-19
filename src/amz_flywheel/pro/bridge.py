"""Runtime import check and dynamic dispatch bridge for amz_flywheel_pro."""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any, Optional

from amz_flywheel.contracts.exceptions import ProLicenseError


def get_pro_module() -> Optional[ModuleType]:
    """Attempt to import `amz_flywheel_pro` at runtime; return None if unavailable."""
    try:
        return importlib.import_module("amz_flywheel_pro")
    except ImportError:
        return None


def is_pro_available() -> bool:
    """Return True if the compiled `amz_flywheel_pro` extension is importable."""
    return get_pro_module() is not None


def require_pro() -> ModuleType:
    """
    Import and return `amz_flywheel_pro` after verifying an active license,
    or raise `ProLicenseError`.
    """
    mod = get_pro_module()
    if mod is None:
        raise ProLicenseError(
            "This feature requires `amz_flywheel_pro`. Activate a Polar.sh license key via "
            "`amz-flywheel auth install-pro --key <KEY>` or the `activate_amz_flywheel_pro` MCP tool."
        )
    if hasattr(mod, "assert_licensed"):
        try:
            mod.assert_licensed()
        except PermissionError as exc:
            raise ProLicenseError(str(exc)) from exc
    return mod


def enrich_with_pro_elasticity(
    panel_rows: list[Any],
    category: str = "general",
    product_margin: float = 0.35,
) -> dict[tuple[str, str], dict[str, Any]]:
    """
    If `amz_flywheel_pro` is installed and licensed, run:
      - Asymmetric Velocity-to-Rank Elasticity solver (with 90% CI & R^2)
      - Walk-Forward Out-of-Sample Backtest (MAE, MAPE, 90% PI coverage)
      - Halo-Adjusted Break-Even ACoS calculator
      - Empirical Hill-Saturated Marginal Response Curve solver
    Gracefully returns `{}` if Pro is absent or unlicensed so Open-Core audits never fail.
    """
    mod = get_pro_module()
    if mod is None:
        return {}

    if hasattr(mod, "assert_licensed"):
        try:
            mod.assert_licensed()
        except PermissionError:
            return {}

    from collections import defaultdict

    grouped: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for r in panel_rows:
        grouped[(r.asin, r.search_query)].append(r)

    results: dict[tuple[str, str], dict[str, Any]] = {}
    for key, rows in grouped.items():
        if len(rows) < 4:
            continue
        ordered = sorted(rows, key=lambda x: x.week_start)
        ad_orders = [float(x.ad_orders) for x in ordered]
        org_orders = [float(x.organic_orders) for x in ordered]
        ranks = [
            float(x.organic_rank if x.organic_rank is not None else 50.0)
            for x in ordered
        ]
        volumes = [float(x.search_volume) for x in ordered]
        spends = [float(x.ad_spend) for x in ordered]
        sales = [float(x.ad_sales) for x in ordered]

        recent_spend = sum(spends[-4:]) / 4.0
        recent_sales = sum(sales[-4:]) / 4.0
        recent_ad_orders = sum(ad_orders[-4:]) / 4.0
        recent_org_orders = sum(org_orders[-4:]) / 4.0
        recent_rank = ranks[-1]

        fit = mod.fit_keyword_elasticity(
            ad_orders=ad_orders,
            organic_orders=org_orders,
            organic_ranks=ranks,
            search_volumes=volumes,
            category=category,
        )
        halo = mod.compute_halo_acos(
            theta_eb=fit["theta_eb"],
            lambda_decay=fit["lambda_decay"],
            product_margin=product_margin,
            recent_ad_spend=recent_spend,
            recent_ad_sales=recent_sales,
            recent_ad_orders=recent_ad_orders,
            recent_organic_orders=recent_org_orders,
            recent_organic_rank=recent_rank,
        )

        backtest: dict[str, Any] = {}
        if hasattr(mod, "backtest_keyword_elasticity"):
            bt = mod.backtest_keyword_elasticity(
                ad_orders=ad_orders,
                organic_orders=org_orders,
                organic_ranks=ranks,
                search_volumes=volumes,
                holdout_weeks=2,
                category=category,
            )
            backtest = {
                "backtest_status": bt["status"],
                "backtest_rank_mae": bt["rank_mae"],
                "backtest_rank_mape": bt["rank_mape"],
                "backtest_within_90_ci_rate": bt["within_90_ci_rate"],
            }

        marginal: dict[str, Any] = {}
        if hasattr(mod, "compute_marginal_response_curve"):
            mc = mod.compute_marginal_response_curve(
                theta_eb=fit["theta_eb"],
                lambda_decay=fit["lambda_decay"],
                product_margin=product_margin,
                current_weekly_spend=recent_spend,
                current_ad_sales=recent_sales,
                current_ad_orders=recent_ad_orders,
                current_organic_orders=recent_org_orders,
                current_organic_rank=recent_rank,
                spend_series=spends,
                order_series=ad_orders,
            )
            marginal = {
                "average_paid_roas": mc["average_paid_roas"],
                "marginal_paid_roas": mc["marginal_paid_roas"],
                "marginal_organic_roas": mc["marginal_organic_roas"],
                "marginal_total_roas": mc["marginal_total_roas"],
                "marginal_net_profit_per_dollar": mc["marginal_net_profit_per_dollar"],
                "optimal_weekly_spend": mc["optimal_weekly_spend"],
                "recommended_spend_delta": mc["recommended_spend_delta"],
                "hill_fit_source": mc.get("hill_fit_source", "bayesian_prior"),
                "response_curve": mc.get("response_curve", []),
            }
        results[key] = {**fit, **halo, **backtest, **marginal}
    return results
