"""Typer CLI for amz-adlift (`audit`, `report`, `bulksheet`, `allocate`, `mcp`, `auth`, `amc`)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from amz_adlift.core.buybox_guard import evaluate_buybox_and_promo_health
from amz_adlift.core.cosmo_intent import audit_listing_2026
from amz_adlift.core.experiments import compute_experiment_mde
from amz_adlift.core.iroas import evaluate_iroas_economics
from amz_adlift.io.amc_connector import (
    generate_amc_dsp_search_synergy_sql,
    generate_amc_existing_customer_suppression_sql,
    generate_amc_flywheel_sql,
    generate_amc_ltv_cohort_sql,
    generate_amc_promo_isolation_sql,
)
from amz_adlift.mcp_server import (
    analyze_amc_clean_room,
    audit_amazon_flywheel,
    export_ads_bulksheet,
    generate_audit_report,
    mcp as fastmcp_server,
    optimize_budget_allocation,
)
from amz_adlift.pro.installer import install_pro

app = typer.Typer(
    name="amz-adlift",
    help="Local-first Amazon Paid-to-Organic Search Flywheel & Rank Elasticity CLI.",
    no_args_is_help=True,
)
auth_app = typer.Typer(
    name="auth",
    help="Manage Polar.sh Pro licensing and compiled Cython wheel installation.",
    no_args_is_help=True,
)
amc_app = typer.Typer(
    name="amc",
    help="Amazon Marketing Cloud (AMC) privacy-safe SQL generator & Markov attribution tools.",
    no_args_is_help=True,
)
app.add_typer(auth_app, name="auth")
app.add_typer(amc_app, name="amc")


@app.command("audit")
def audit_command(
    sqp: Path = typer.Option(..., "--sqp", help="Path to Seller Central Brand Analytics SQP CSV or directory."),
    ads: Path = typer.Option(..., "--ads", help="Path to Amazon Ads Search Term Report CSV or XLSX."),
    rank: Optional[Path] = typer.Option(
        None, "--rank", help="Optional path to Organic Keyword Rank CSV (Helium 10 / DataDive)."
    ),
    amc: Optional[Path] = typer.Option(
        None, "--amc", help="Optional path to exported AMC Clean Room NTB/Halo CSV."
    ),
    biz_report: Optional[Path] = typer.Option(
        None, "--biz-report", help="Optional path to Seller Central Detail Page Sales & Traffic Business Report CSV."
    ),
    cluster_intent: bool = typer.Option(
        False, "--cluster-intent", help="Aggregate sparse keywords into COSMO intent clusters."
    ),
    promo_days: int = typer.Option(
        0, "--promo-days", help="Number of promotional days in the last 30 days (flags >30% dependency)."
    ),
    days_supply: Optional[float] = typer.Option(
        None, "--days-supply", help="Current FBA days of inventory supply (flags <30d curtailment risk)."
    ),
    star_rating: Optional[float] = typer.Option(
        None, "--star-rating", help="Optional listing star rating (evaluates 4.7+ vs <4.3 visibility tier)."
    ),
    category: str = typer.Option("general", "--category", help="Product category prior name."),
    margin: float = typer.Option(0.35, "--margin", help="Pre-ad unit gross margin (0.0 - 1.0)."),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Optional output path for JSON audit report."
    ),
) -> None:
    """Run local Paid-to-Organic flywheel audit from exported Seller Central, Ads, and AMC files."""
    report = audit_amazon_flywheel(
        sqp_csv_path=str(sqp),
        ads_csv_path=str(ads),
        rank_csv_path=str(rank) if rank is not None else None,
        amc_csv_path=str(amc) if amc is not None else None,
        category=category,
        product_margin=margin,
        biz_report_csv_path=str(biz_report) if biz_report is not None else None,
        cluster_intent=cluster_intent,
        promo_days_last_30=promo_days,
        days_of_inventory_supply=days_supply,
        star_rating=star_rating,
    )
    serialized = json.dumps(report, indent=2)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(serialized + "\n", encoding="utf-8")
        typer.echo(f"Audit report written to {out} ({report['total_keywords']} keywords).")
    else:
        typer.echo(serialized)


@app.command("report")
def report_command(
    out: Path = typer.Option(
        Path("./flywheel_audit_report.html"),
        "--out",
        help="Destination path for the interactive white-label HTML/PDF executive audit deck.",
    ),
    sqp: Optional[Path] = typer.Option(
        None, "--sqp", help="Optional SQP CSV/dir (if omitted, uses the most recent persisted audit)."
    ),
    ads: Optional[Path] = typer.Option(
        None, "--ads", help="Optional Ads Search Term CSV/XLSX (required if --sqp is provided)."
    ),
    rank: Optional[Path] = typer.Option(None, "--rank", help="Optional Organic Rank CSV."),
    amc: Optional[Path] = typer.Option(None, "--amc", help="Optional AMC Clean Room CSV."),
    category: str = typer.Option("general", "--category", help="Product category prior name."),
    margin: float = typer.Option(0.35, "--margin", help="Pre-ad unit gross margin (0.0 - 1.0)."),
    budget: Optional[float] = typer.Option(
        None, "--budget", help="Optional target weekly PPC budget for KKT Equimarginal charts."
    ),
    agency_name: str = typer.Option(
        "amz-adlift Econometrics", "--agency-name", help="White-label agency name for header."
    ),
    client_name: Optional[str] = typer.Option(
        None, "--client-name", help="White-label client brand name for header."
    ),
    logo_url: Optional[str] = typer.Option(
        None, "--logo-url", help="Optional HTTPS or data-URI agency logo image URL."
    ),
) -> None:
    """Generate an interactive white-label HTML/PDF Executive Flywheel Audit Report."""
    if sqp is not None and ads is not None:
        audit_amazon_flywheel(
            sqp_csv_path=str(sqp),
            ads_csv_path=str(ads),
            rank_csv_path=str(rank) if rank is not None else None,
            amc_csv_path=str(amc) if amc is not None else None,
            category=category,
            product_margin=margin,
        )
    res = generate_audit_report(
        output_path=str(out),
        total_weekly_budget=budget,
        agency_name=agency_name,
        client_name=client_name,
        logo_url=logo_url,
    )
    typer.echo(json.dumps(res, indent=2))


@app.command("bulksheet")
def bulksheet_command(
    out: Path = typer.Option(
        Path("./amazon_ads_bulk_update.xlsx"),
        "--out",
        help="Output path for upload-ready Amazon Ads Bulk Operations .xlsx file.",
    ),
    existing_bulk: Optional[Path] = typer.Option(
        None,
        "--existing-bulk",
        help="Exported Seller Central Bulk Operations .xlsx file to merge exact numeric Campaign/AdGroup/Keyword IDs.",
    ),
    max_change: float = typer.Option(
        0.25, "--max-change", help="Maximum single-step bid change fraction (default 0.25)."
    ),
    min_bid: float = typer.Option(0.15, "--min-bid", help="Safety floor for generated CPC bids."),
    max_bid: float = typer.Option(15.0, "--max-bid", help="Safety ceiling for generated CPC bids."),
) -> None:
    """[Pro] Export upload-ready Amazon Ads Bulk Operations .xlsx with safe bid guardrails."""
    res = export_ads_bulksheet(
        output_path=str(out),
        existing_bulksheet_path=str(existing_bulk) if existing_bulk is not None else None,
        max_bid_change_pct=max_change,
        min_bid=min_bid,
        max_bid=max_bid,
    )
    typer.echo(json.dumps(res, indent=2))


@app.command("mcp")
def mcp_command() -> None:
    """Start FastMCP stdio server for Claude Desktop / Cursor."""
    fastmcp_server.run()


@auth_app.command("install-pro")
def auth_install_pro_command(
    key: str = typer.Option(..., "--key", help="Polar.sh Pro license key (e.g. AMZ_AL_PRO_...)."),
    wheel_dir: Optional[Path] = typer.Option(
        None, "--wheel-dir", help="Optional local directory containing built amz_adlift_pro wheel."
    ),
    wheel_url: Optional[str] = typer.Option(
        None, "--wheel-url", help="Optional direct HTTPS URL for the platform .whl binary."
    ),
    manifest_url: Optional[str] = typer.Option(
        None, "--manifest-url", help="Optional JSON wheel manifest URL for automatic platform resolution."
    ),
) -> None:
    """Validate Polar.sh license key and install matching compiled Pro wheel."""
    result = install_pro(
        api_key=key,
        wheel_dir=wheel_dir,
        wheel_url=wheel_url,
        manifest_url=manifest_url,
    )
    typer.echo(json.dumps(result, indent=2))


@amc_app.command("sql")
def amc_sql_command(
    days: int = typer.Option(28, "--days", help="Lookback window in days."),
    synergy: bool = typer.Option(
        False, "--synergy", help="Print the DSP + Sponsored Products synergy overlap SQL query."
    ),
    template: str = typer.Option(
        "flywheel",
        "--template",
        help="SQL template: flywheel | synergy | promo | ltv | suppression.",
    ),
) -> None:
    """Print privacy-safe Amazon Marketing Cloud (AMC) SQL query with >=100 user cohort threshold."""
    tpl = "synergy" if synergy else template.strip().lower()
    if tpl == "synergy":
        typer.echo(generate_amc_dsp_search_synergy_sql(lookback_days=days))
    elif tpl == "promo":
        typer.echo(generate_amc_promo_isolation_sql(lookback_days=days))
    elif tpl == "ltv":
        typer.echo(generate_amc_ltv_cohort_sql(lookback_days=days))
    elif tpl == "suppression":
        typer.echo(generate_amc_existing_customer_suppression_sql(lookback_days=days))
    else:
        typer.echo(generate_amc_flywheel_sql(lookback_days=days))


@app.command("iroas")
def iroas_command(
    incremental_revenue: float = typer.Option(..., "--inc-rev", help="Incremental revenue from test/model."),
    incremental_spend: float = typer.Option(..., "--inc-spend", help="Incremental media spend."),
    margin: float = typer.Option(0.38, "--margin", help="Pre-ad gross margin (0.0 - 1.0)."),
    ntb_share: float = typer.Option(1.0, "--ntb-share", help="New-to-Brand order share (0.0 - 1.0)."),
    ltv_mult: float = typer.Option(1.0, "--ltv-mult", help="Repeat-buyer LTV multiplier (e.g. 3.0)."),
    cvr: Optional[float] = typer.Option(None, "--cvr", help="Optional conversion rate (0.0 - 1.0) for CPC ceiling."),
    price: Optional[float] = typer.Option(None, "--price", help="Optional selling price for CPC ceiling."),
) -> None:
    """Evaluate causal iROAS, LTV-adjusted break-even, and sustainable CPC ceiling."""
    res = evaluate_iroas_economics(
        incremental_revenue=incremental_revenue,
        incremental_spend=incremental_spend,
        product_margin=margin,
        ntb_share=ntb_share,
        ltv_repeat_multiplier=ltv_mult,
        cvr=cvr,
        selling_price=price,
    )
    typer.echo(res.model_dump_json(indent=2))


@app.command("listing-audit")
def listing_audit_command(
    title: str = typer.Option(..., "--title", help="Product title (2026 limit: <= 75 chars)."),
    highlights: str = typer.Option("", "--highlights", help="Item Highlights text (2026 limit: <= 125 chars)."),
    backend: str = typer.Option("", "--backend", help="Optional legacy backend keywords to check for orphaned terms."),
) -> None:
    """Audit an Amazon listing against July 2026 taxonomy rules and COSMO intent coverage."""
    res = audit_listing_2026(
        title=title,
        item_highlights=highlights,
        legacy_backend_keywords=backend,
    )
    typer.echo(res.model_dump_json(indent=2))


@app.command("experiment-power")
def experiment_power_command(
    baseline: str = typer.Option(
        ...,
        "--baseline",
        help="Comma-separated historical sales series (e.g. '1000,1040,980,1020,1010,995').",
    ),
    expected_lift: float = typer.Option(0.08, "--expected-lift", help="Expected relative lift (e.g. 0.08 for 8%)."),
    periods: int = typer.Option(4, "--periods", help="Planned test duration in periods."),
) -> None:
    """Pre-test Minimum Detectable Effect (MDE) and Signal-to-Noise power gate."""
    vals = [float(x.strip()) for x in baseline.split(",") if x.strip()]
    res = compute_experiment_mde(vals, expected_lift_pct=expected_lift, duration_periods=periods)
    typer.echo(res.model_dump_json(indent=2))


@app.command("ops-health")
def ops_health_command(
    buy_box_pct: float = typer.Option(..., "--buy-box", help="Featured Offer (Buy Box) percentage (0-100)."),
    promo_days: int = typer.Option(0, "--promo-days", help="Number of promotional days in last 30 days."),
    days_supply: Optional[float] = typer.Option(None, "--days-supply", help="Current FBA days of inventory supply."),
) -> None:
    """Check Buy Box, >30% promo-dependency, and <30-day stockout guardrails before scaling bids."""
    res = evaluate_buybox_and_promo_health(
        buy_box_pct=buy_box_pct,
        promo_days_last_30=promo_days,
        days_of_inventory_supply=days_supply,
    )
    typer.echo(res.model_dump_json(indent=2))


@amc_app.command("markov")
def amc_markov_command() -> None:
    """Run First-Order Markov Chain Removal Effect analysis across AMC touchpoint paths."""
    res = analyze_amc_clean_room()
    typer.echo(json.dumps(res["markov_attribution"], indent=2))


@app.command("allocate")
def allocate_command(
    budget: Optional[float] = typer.Option(
        None,
        "--budget",
        help="Optional target weekly PPC budget. If omitted, reallocates current weekly spend.",
    ),
) -> None:
    """[Pro] Reallocate weekly PPC budget across keywords using KKT Equimarginal Water-Filling."""
    res = optimize_budget_allocation(total_weekly_budget=budget)
    typer.echo(json.dumps(res, indent=2))


if __name__ == "__main__":
    app()
