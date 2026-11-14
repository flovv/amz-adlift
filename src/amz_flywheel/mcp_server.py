"""FastMCP Server exposing local Amazon Paid-to-Organic Search Flywheel tools, resources, and prompts."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Annotated, Any, Literal, Optional

from fastmcp import FastMCP
from pydantic import Field

from amz_flywheel.contracts.schemas import (
    AuditReport,
    KeywordQuadrantDiagnostic,
    UnifiedKeywordWeek,
)
from amz_flywheel.core.quadrants import classify_panel
from amz_flywheel.io.aligner import ingest_and_align
from amz_flywheel.io.amc_connector import (
    compute_markov_removal_effects,
    generate_amc_dsp_search_synergy_sql,
    generate_amc_flywheel_sql,
)
from amz_flywheel.io.sqp_parser import normalize_query
from amz_flywheel.pro.bridge import (
    enrich_with_pro_elasticity,
    is_pro_available,
    require_pro,
)
from amz_flywheel.pro.installer import install_pro

CategoryName = Literal[
    "general",
    "supplements",
    "electronics",
    "home_kitchen",
    "beauty",
    "pet_supplies",
    "apparel",
]

QUADRANT_ACTION_PLAYBOOK: dict[str, dict[str, Any]] = {
    "CANNIBALIZED_RENT": {
        "meaning": "Brand already holds #1-#2 organic rank with strong pure organic CVR (>=12%) while spending heavily on Sponsored Products.",
        "recommended_action": "Step down Exact-match CPC bids by 15%-25% (or test dayparting/top-of-search multiplier cuts) and monitor organic rank stability over 21 days.",
        "bid_direction": "DECREASE",
    },
    "FLYWHEEL_LEVERAGE": {
        "meaning": "Paid order velocity is actively accelerating organic rank toward #1 (slope <= -0.5 pos/wk) with positive lagged paid-to-organic order correlation (r >= 0.35).",
        "recommended_action": "Allow ACoS up to Halo-Adjusted Break-Even ACoS (ProductMargin * (1 + OrganicMultiplier_21d)) to sustain rank climb.",
        "bid_direction": "INCREASE_TO_HALO_ACOS",
    },
    "TREADMILL_DEAD_WEIGHT": {
        "meaning": "High cumulative ad spend (>= $100/4w) with stagnant organic rank worse than #10 and SQP conversion rate below 50% of category median.",
        "recommended_action": "Reduce bids by 25%-50% or negate search term; listing conversion rate or relevance must be fixed before PPC can lift rank.",
        "bid_direction": "DECREASE_OR_NEGATE",
    },
    "AT_RISK_DECAY": {
        "meaning": "Organic rank is slipping (>= +0.75 pos/wk numerically) alongside declining SQP Brand Click Share.",
        "recommended_action": "Run simulate_keyword_bid_cut and restore defensive Sponsored Products velocity if Halo Multiplier justifies the spend.",
        "bid_direction": "DEFEND_SELECTIVELY",
    },
    "INSUFFICIENT_DATA": {
        "meaning": "Fewer than 4 aligned weekly observations available for this (asin, search_query) pair.",
        "recommended_action": "Export at least 4 consecutive weekly Seller Central SQP and Ads Search Term reports before changing bids.",
        "bid_direction": "HOLD",
    },
}

mcp = FastMCP(
    name="amz-flywheel",
    instructions=(
        "Local Amazon Paid-to-Organic Search Flywheel & Rank Elasticity Auditor. "
        "Workflow: (1) Call `audit_amazon_flywheel` with local SQP, Ads, and optional Rank CSV paths "
        "to isolate pure organic clicks/orders and classify keywords into 4 flywheel quadrants. "
        "(2) Call `simulate_keyword_bid_cut` to project 21-day organic rank decay and net profit impact "
        "under -25%, -50%, or -100% PPC spend cuts. "
        "(3) Call `export_ads_bulksheet` to generate an Amazon Ads Sponsored Products Bulk Operations .xlsx file."
    ),
)

# Local process state + persistent disk state at ~/.amz_flywheel/last_audit_state.json
_LAST_AUDIT_STATE: dict[str, Any] = {
    "panel": [],
    "diagnostics": [],
    "pro_metrics": {},
    "category": "general",
    "product_margin": 0.35,
}


def _state_cache_file() -> Path:
    return Path.home() / ".amz_flywheel" / "last_audit_state.json"


def _normalize_fraction(value: float, default: float) -> float:
    """Normalize percentage values if an LLM passes e.g. 38 instead of 0.38 or -50 instead of -0.50."""
    if value == 0.0:
        return 0.0
    if abs(value) > 1.0:
        return value / 100.0
    return value if value is not None else default


def _persist_audit_state() -> None:
    """Persist the latest audit state to ~/.amz_flywheel/last_audit_state.json for cross-process resilience."""
    try:
        cache_file = _state_cache_file()
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        serializable = {
            "category": _LAST_AUDIT_STATE.get("category", "general"),
            "product_margin": _LAST_AUDIT_STATE.get("product_margin", 0.35),
            "panel": [
                r.model_dump(mode="json") for r in _LAST_AUDIT_STATE.get("panel", [])
            ],
            "diagnostics": [
                d.model_dump(mode="json")
                for d in _LAST_AUDIT_STATE.get("diagnostics", [])
            ],
            "pro_metrics": {
                f"{asin}|||{query}": val
                for (asin, query), val in _LAST_AUDIT_STATE.get("pro_metrics", {}).items()
            },
        }
        cache_file.write_text(json.dumps(serializable), encoding="utf-8")
    except Exception:
        pass


def _ensure_audit_state_loaded() -> bool:
    """Load persisted audit state from ~/.amz_flywheel/last_audit_state.json if in-memory state is empty."""
    if _LAST_AUDIT_STATE.get("panel"):
        return True
    cache_file = _state_cache_file()
    if not cache_file.exists():
        return False
    try:
        raw = json.loads(cache_file.read_text(encoding="utf-8"))
        _LAST_AUDIT_STATE["category"] = str(raw.get("category", "general"))
        _LAST_AUDIT_STATE["product_margin"] = float(raw.get("product_margin", 0.35))
        _LAST_AUDIT_STATE["panel"] = [
            UnifiedKeywordWeek.model_validate(item) for item in raw.get("panel", [])
        ]
        _LAST_AUDIT_STATE["diagnostics"] = [
            KeywordQuadrantDiagnostic.model_validate(item)
            for item in raw.get("diagnostics", [])
        ]
        pro_map: dict[tuple[str, str], dict[str, Any]] = {}
        for k, v in raw.get("pro_metrics", {}).items():
            if "|||" in k:
                asin_part, query_part = k.split("|||", 1)
                pro_map[(asin_part, query_part)] = v
        _LAST_AUDIT_STATE["pro_metrics"] = pro_map
        return bool(_LAST_AUDIT_STATE["panel"])
    except Exception:
        return False


@mcp.resource("flywheel://reference/quadrants")
def get_quadrant_definitions_resource() -> str:
    """Return machine-readable 4-Quadrant diagnostic rules, thresholds, and action playbooks."""
    return json.dumps(QUADRANT_ACTION_PLAYBOOK, indent=2)


@mcp.resource("flywheel://reference/category-priors")
def get_category_priors_resource() -> str:
    """Return available category elasticity priors for Empirical Bayes shrinkage."""
    categories = [
        "general",
        "supplements",
        "electronics",
        "home_kitchen",
        "beauty",
        "pet_supplies",
        "apparel",
    ]
    if is_pro_available():
        pro_mod = require_pro()
        priors = {c: pro_mod.get_category_prior(c) for c in categories}
    else:
        priors = {c: {"category": c} for c in categories}
    return json.dumps(priors, indent=2)


@mcp.resource("flywheel://amc/sql-recipes")
def get_amc_sql_recipes_resource() -> str:
    """Return privacy-safe Amazon Marketing Cloud (AMC) SQL queries with >=100 user cohort guards."""
    return json.dumps(
        {
            "keyword_ntb_and_halo_sql": generate_amc_flywheel_sql(lookback_days=28),
            "dsp_search_synergy_overlap_sql": generate_amc_dsp_search_synergy_sql(
                lookback_days=30
            ),
        },
        indent=2,
    )


@mcp.prompt("executive_flywheel_audit")
def executive_flywheel_audit_prompt(
    sqp_csv_path: str,
    ads_csv_path: str,
    rank_csv_path: str = "",
    product_margin: float = 0.35,
) -> str:
    """Prompt template guiding an AI agent through a complete Paid-to-Organic Flywheel audit."""
    rank_part = f", rank_csv_path='{rank_csv_path}'" if rank_csv_path else ""
    return (
        f"Run a complete Amazon Paid-to-Organic Flywheel Audit using local files:\n"
        f"1. Call `audit_amazon_flywheel(sqp_csv_path='{sqp_csv_path}', ads_csv_path='{ads_csv_path}'{rank_part}, product_margin={product_margin})`.\n"
        f"2. Group all keywords by their 4 quadrants (`CANNIBALIZED_RENT`, `FLYWHEEL_LEVERAGE`, `TREADMILL_DEAD_WEIGHT`, `AT_RISK_DECAY`).\n"
        f"3. For every `CANNIBALIZED_RENT` and `FLYWHEEL_LEVERAGE` keyword, call `simulate_keyword_bid_cut` with `spend_change_pct=-0.50` to quantify the 21-day organic rank trajectory and net profit impact.\n"
        f"4. Present an executive summary table showing wasted ad spend on cannibalized #1 keywords, undervalued flywheel keywords with Halo Break-Even ACoS > Product Margin, and offer to export the bulk sheet via `export_ads_bulksheet`."
    )


@mcp.tool()
def audit_amazon_flywheel(
    sqp_csv_path: Annotated[
        str,
        Field(
            description="Local path to Seller Central Brand Analytics Search Query Performance (SQP) CSV file, directory of weekly SQP CSVs, or glob pattern."
        ),
    ],
    ads_csv_path: Annotated[
        str,
        Field(
            description="Local path to Amazon Ads Sponsored Products Search Term Report CSV (Legacy, 2026 Unified, or DE)."
        ),
    ],
    rank_csv_path: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Optional local path to Organic Keyword Rank tracker CSV (Helium 10, DataDive, Perpetua). If omitted, organic rank is automatically inferred from SQP organic impression/click share.",
        ),
    ] = None,
    amc_csv_path: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Optional local path to Amazon Marketing Cloud (AMC) keyword export CSV containing New-to-Brand (NTB) orders and Cross-ASIN Halo counts.",
        ),
    ] = None,
    category: Annotated[
        str,
        Field(
            default="general",
            description="Category prior for Empirical Bayes shrinkage: 'general', 'supplements', 'electronics', 'home_kitchen', 'beauty', 'pet_supplies', or 'apparel'.",
        ),
    ] = "general",
    product_margin: Annotated[
        float,
        Field(
            default=0.35,
            description="Pre-ad unit gross profit margin as a decimal fraction (e.g. 0.35 for 35% margin). Values > 1 (e.g. 35) are automatically normalized to 0.35.",
        ),
    ] = 0.35,
    include_raw_panel: Annotated[
        bool,
        Field(
            default=True,
            description="Whether to include the full weekly `panel` array in the returned JSON. Set to False on large accounts (500+ keywords) to save LLM context tokens.",
        ),
    ] = True,
) -> dict[str, Any]:
    """
    Joins Brand Analytics SQP, Amazon Ads Search Term, Organic Rank, and optional AMC
    Clean Room CSVs locally. Isolates pure organic clicks/orders from paid search,
    classifies keywords into 4 flywheel quadrants, runs Adversarial Red-Team checks,
    and executes Pro rank-elasticity modeling if licensed.
    """
    norm_margin = _normalize_fraction(product_margin, 0.35)
    norm_category = category.strip().lower() or "general"

    panel: list[UnifiedKeywordWeek] = ingest_and_align(
        sqp_csv_path=sqp_csv_path,
        ads_csv_path=ads_csv_path,
        rank_csv_path=rank_csv_path,
        amc_csv_path=amc_csv_path,
    )
    diagnostics = classify_panel(panel, category=norm_category)
    pro_enabled = is_pro_available()
    pro_map = (
        enrich_with_pro_elasticity(
            panel, category=norm_category, product_margin=norm_margin
        )
        if pro_enabled
        else {}
    )

    enriched_diagnostics = []
    red_team_warnings: list[str] = []
    for diag in diagnostics:
        key = (diag.asin, diag.search_query)
        if key in pro_map:
            diag = diag.model_copy(update={"pro_metrics": pro_map[key]})
        enriched_diagnostics.append(diag)
        for flag in diag.red_team_flags:
            if flag != "SHORT_HISTORY_EMPIRICAL_BAYES_SHRINKAGE_ACTIVE":
                red_team_warnings.append(f"{diag.search_query}: {flag}")

    quad_counts = dict(Counter(d.quadrant for d in enriched_diagnostics))
    unique_weeks = len({r.week_start for r in panel})
    primary_asin = panel[0].asin if panel else "UNKNOWN_ASIN"

    report = AuditReport(
        asin=primary_asin,
        category=norm_category,
        product_margin=norm_margin,
        pro_enabled=pro_enabled,
        total_keywords=len(enriched_diagnostics),
        total_weeks=unique_weeks,
        quadrant_counts=quad_counts,
        red_team_warnings=red_team_warnings,
        keywords=enriched_diagnostics,
        panel=panel if include_raw_panel else [],
    )

    _LAST_AUDIT_STATE["panel"] = panel
    _LAST_AUDIT_STATE["diagnostics"] = enriched_diagnostics
    _LAST_AUDIT_STATE["pro_metrics"] = pro_map
    _LAST_AUDIT_STATE["category"] = norm_category
    _LAST_AUDIT_STATE["product_margin"] = norm_margin
    _persist_audit_state()

    output = report.model_dump(mode="json")
    output["quadrant_playbook"] = QUADRANT_ACTION_PLAYBOOK
    return output


@mcp.tool()
def simulate_keyword_bid_cut(
    search_query: Annotated[
        str,
        Field(description="Target search query / keyword to simulate (case-insensitive)."),
    ],
    asin: Annotated[
        str,
        Field(
            description="Target ASIN (e.g. 'B08XYZ123') or 'ANY' to match the primary audited ASIN."
        ),
    ],
    spend_change_pct: Annotated[
        float,
        Field(
            default=-0.50,
            description="Relative PPC spend change as a decimal fraction (e.g. -0.50 for a 50% spend cut, -1.0 for a full pause). Values like -50 are auto-normalized to -0.50.",
        ),
    ] = -0.50,
    horizon_weeks: Annotated[
        int,
        Field(
            default=3,
            ge=1,
            le=12,
            description="Simulation horizon in weeks (default 3 weeks = 21 days).",
        ),
    ] = 3,
) -> dict[str, Any]:
    """
    [Pro] Simulates 21-day organic rank trajectory and net organic profit impact
    if PPC spend on a specific keyword is reduced or paused.
    """
    pro_mod = require_pro()
    norm_q = normalize_query(search_query)
    norm_asin = asin.strip().upper()
    norm_spend_change = _normalize_fraction(spend_change_pct, -0.50)

    _ensure_audit_state_loaded()
    panel: list[UnifiedKeywordWeek] = _LAST_AUDIT_STATE.get("panel", [])
    matching = [
        r
        for r in panel
        if r.search_query == norm_q and (r.asin == norm_asin or norm_asin == "ANY")
    ]
    if not matching and panel:
        # Fallback to query-only match if ASIN string differed
        matching = [r for r in panel if r.search_query == norm_q]

    category = _LAST_AUDIT_STATE.get("category", "general")
    product_margin = float(_LAST_AUDIT_STATE.get("product_margin", 0.35))

    if len(matching) >= 4:
        ordered = sorted(matching, key=lambda x: x.week_start)
        ad_orders = [float(x.ad_orders) for x in ordered]
        org_orders = [float(x.organic_orders) for x in ordered]
        ranks = [
            float(x.organic_rank if x.organic_rank is not None else 25.0)
            for x in ordered
        ]
        volumes = [float(x.search_volume) for x in ordered]
        spends = [float(x.ad_spend) for x in ordered]
        sales = [float(x.ad_sales) for x in ordered]

        fit = pro_mod.fit_keyword_elasticity(
            ad_orders=ad_orders,
            organic_orders=org_orders,
            organic_ranks=ranks,
            search_volumes=volumes,
            category=category,
        )
        theta_eb = float(fit["theta_eb"])
        lambda_decay = float(fit["lambda_decay"])
        current_rank = ranks[-1]
        current_velocity = float(fit["terminal_velocity"])
        baseline_paid_orders = sum(ad_orders[-4:]) / 4.0
        baseline_org_orders = sum(org_orders[-4:]) / 4.0
        baseline_spend = sum(spends[-4:]) / 4.0
        total_orders_4w = sum(ad_orders[-4:])
        avg_order_value = (
            (sum(sales[-4:]) / total_orders_4w) if total_orders_4w > 0 else 35.0
        )
        data_source = "audited_panel"
    else:
        prior = pro_mod.get_category_prior(category)
        theta_eb = float(prior["mu_cat"])
        lambda_decay = float(prior["default_lambda"])
        current_rank = 6.0
        baseline_paid_orders = 12.0
        baseline_org_orders = 18.0
        current_velocity = baseline_paid_orders + baseline_org_orders
        baseline_spend = 120.0
        avg_order_value = 35.0
        data_source = "category_prior_fallback"

    sim = pro_mod.simulate_bid_cut(
        theta_eb=theta_eb,
        lambda_decay=lambda_decay,
        current_rank=current_rank,
        current_velocity=current_velocity,
        baseline_paid_orders=baseline_paid_orders,
        baseline_organic_orders=baseline_org_orders,
        baseline_weekly_spend=baseline_spend,
        avg_order_value=avg_order_value,
        product_margin=product_margin,
        spend_change_pct=norm_spend_change,
        horizon_weeks=horizon_weeks,
    )
    return {
        "asin": norm_asin,
        "search_query": norm_q,
        "data_source": data_source,
        **sim,
    }


@mcp.tool()
def export_ads_bulksheet(
    output_path: Annotated[
        str,
        Field(
            description="Destination path for the generated Amazon Ads Bulk Operations .xlsx file (e.g. './reports/amazon_ads_bulk_update.xlsx')."
        ),
    ],
    max_bid_change_pct: Annotated[
        float,
        Field(
            default=0.25,
            description="Maximum allowed single-step bid increase/decrease fraction (e.g. 0.25 caps bid changes at +/-25%). Values > 1 (e.g. 25) are auto-normalized to 0.25.",
        ),
    ] = 0.25,
) -> dict[str, Any]:
    """
    [Pro] Generates a ready-to-upload Amazon Ads Sponsored Products Bulk Operations
    spreadsheet with Halo-Adjusted Break-Even bids.
    """
    pro_mod = require_pro()
    norm_max_change = abs(_normalize_fraction(max_bid_change_pct, 0.25))

    _ensure_audit_state_loaded()
    panel: list[UnifiedKeywordWeek] = _LAST_AUDIT_STATE.get("panel", [])
    diagnostics = _LAST_AUDIT_STATE.get("diagnostics", [])
    pro_metrics = _LAST_AUDIT_STATE.get("pro_metrics", {})
    product_margin = float(_LAST_AUDIT_STATE.get("product_margin", 0.35))

    rows_payload: list[dict[str, Any]] = []
    for diag in diagnostics:
        key = (diag.asin, diag.search_query)
        kw_rows = [
            r for r in panel if r.asin == diag.asin and r.search_query == diag.search_query
        ]
        trailing = sorted(kw_rows, key=lambda x: x.week_start)[-4:] if kw_rows else []
        clicks = sum(r.ad_clicks for r in trailing)
        spend = sum(r.ad_spend for r in trailing)
        sales = sum(r.ad_sales for r in trailing)
        current_cpc = (spend / clicks) if clicks > 0 else 1.25
        current_acos = (spend / sales) if sales > 0 else product_margin

        pm = pro_metrics.get(key, {})
        halo_acos = float(pm.get("halo_break_even_acos", product_margin * 1.25))

        rows_payload.append(
            {
                "asin": diag.asin,
                "search_query": diag.search_query,
                "campaign_name": trailing[-1].campaign_name if trailing and trailing[-1].campaign_name else f"SP_{diag.asin}_Exact",
                "ad_group_name": trailing[-1].ad_group_name if trailing and trailing[-1].ad_group_name else "AG_Main",
                "match_type": trailing[-1].match_type if trailing and trailing[-1].match_type else "EXACT",
                "quadrant": diag.quadrant,
                "current_bid": round(current_cpc, 2),
                "current_acos": round(current_acos, 4),
                "halo_break_even_acos": round(halo_acos, 4),
            }
        )

    result = pro_mod.generate_ads_bulksheet(
        output_path=str(Path(output_path)),
        keyword_rows=rows_payload,
        max_bid_change_pct=norm_max_change,
    )
    return dict(result)


@mcp.tool()
def activate_amz_flywheel_pro(
    license_key: Annotated[
        str,
        Field(
            description="Polar.sh license key (e.g. 'AMZ_FW_PRO_...') to validate and cache for 24 hours at ~/.amz_flywheel/license.cache."
        ),
    ],
) -> dict[str, Any]:
    """
    Validates a Polar.sh license key and installs the compiled amz_flywheel_pro
    Cython binary into the active Python environment.
    """
    return install_pro(api_key=license_key)


@mcp.tool()
def analyze_amc_clean_room(
    journey_paths: Annotated[
        Optional[list[dict[str, Any]]],
        Field(
            default=None,
            description="Optional list of customer journey paths [{'path': 'DSP > Sponsored_Brands > Sponsored_Products', 'conversions': 180, 'nulls': 1200}] for First-Order Markov Removal Effect attribution.",
        ),
    ] = None,
    lookback_days: Annotated[
        int,
        Field(
            default=28,
            ge=7,
            le=365,
            description="Lookback window in days for the generated privacy-safe AMC SQL queries.",
        ),
    ] = 28,
) -> dict[str, Any]:
    """
    Generates privacy-safe Amazon Marketing Cloud (AMC) SQL queries (enforcing
    COUNT(DISTINCT user_id) >= 100 cohort thresholds) and computes First-Order Markov
    Chain Removal Effects vs. Last-Touch attribution variance across multi-touch journeys.
    """
    sample_paths = journey_paths or [
        {"path": "DSP > Sponsored_Brands > Sponsored_Products", "conversions": 420, "nulls": 2100},
        {"path": "DSP > Sponsored_Products", "conversions": 310, "nulls": 1800},
        {"path": "Sponsored_Brands > Sponsored_Products", "conversions": 260, "nulls": 1500},
        {"path": "Sponsored_Products", "conversions": 510, "nulls": 4200},
        {"path": "DSP", "conversions": 95, "nulls": 1900},
    ]
    markov = compute_markov_removal_effects(sample_paths)
    return {
        "privacy_cohort_threshold": 100,
        "markov_attribution": markov,
        "amc_flywheel_ntb_sql": generate_amc_flywheel_sql(lookback_days=lookback_days),
        "amc_dsp_search_synergy_sql": generate_amc_dsp_search_synergy_sql(
            lookback_days=lookback_days
        ),
    }


@mcp.tool()
def optimize_budget_allocation(
    total_weekly_budget: Annotated[
        Optional[float],
        Field(
            default=None,
            description="Optional target total weekly PPC budget across all audited keywords. If omitted, reallocates the existing weekly spend pool to maximize total net profit.",
        ),
    ] = None,
) -> dict[str, Any]:
    """
    [Pro] Uses Hill-Saturated Marginal Response Curves (mROAS = d(PaidSales + OrganicHaloSales)/dSpend)
    and the Equimarginal Principle to reallocate weekly PPC budget from saturated #1
    keywords (`CANNIBALIZED_RENT`) into high-marginal-return `FLYWHEEL_LEVERAGE` keywords.
    """
    pro_mod = require_pro()
    _ensure_audit_state_loaded()
    panel: list[UnifiedKeywordWeek] = _LAST_AUDIT_STATE.get("panel", [])
    diagnostics = _LAST_AUDIT_STATE.get("diagnostics", [])
    pro_metrics = _LAST_AUDIT_STATE.get("pro_metrics", {})
    product_margin = float(_LAST_AUDIT_STATE.get("product_margin", 0.35))

    keyword_specs: list[dict[str, Any]] = []
    for diag in diagnostics:
        key = (diag.asin, diag.search_query)
        kw_rows = [
            r for r in panel if r.asin == diag.asin and r.search_query == diag.search_query
        ]
        trailing = sorted(kw_rows, key=lambda x: x.week_start)[-4:] if kw_rows else []
        if not trailing:
            continue
        pm = pro_metrics.get(key) or (diag.pro_metrics or {})
        keyword_specs.append(
            {
                "asin": diag.asin,
                "search_query": diag.search_query,
                "quadrant": diag.quadrant,
                "theta_eb": float(pm.get("theta_eb", 0.40)),
                "lambda_decay": float(pm.get("lambda_decay", 0.58)),
                "current_weekly_spend": sum(r.ad_spend for r in trailing) / float(len(trailing)),
                "current_ad_sales": sum(r.ad_sales for r in trailing) / float(len(trailing)),
                "current_ad_orders": sum(r.ad_orders for r in trailing) / float(len(trailing)),
                "current_organic_orders": sum(r.organic_orders for r in trailing) / float(len(trailing)),
                "current_organic_rank": float(
                    trailing[-1].organic_rank if trailing[-1].organic_rank is not None else 10.0
                ),
            }
        )

    budget_arg = float(total_weekly_budget) if total_weekly_budget is not None else -1.0
    return dict(
        pro_mod.allocate_portfolio_budget(
            keyword_specs=keyword_specs,
            total_weekly_budget=budget_arg,
            product_margin=product_margin,
        )
    )


def main() -> None:
    """Entry point for `amz-flywheel-mcp` stdio server."""
    mcp.run()


if __name__ == "__main__":
    main()


