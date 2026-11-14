"""Typer CLI for amz-flywheel (`audit`, `mcp`, `auth install-pro`, `amc sql`)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from amz_flywheel.io.amc_connector import (
    generate_amc_dsp_search_synergy_sql,
    generate_amc_flywheel_sql,
)
from amz_flywheel.mcp_server import (
    analyze_amc_clean_room,
    audit_amazon_flywheel,
    mcp as fastmcp_server,
    optimize_budget_allocation,
)
from amz_flywheel.pro.installer import install_pro

app = typer.Typer(
    name="amz-flywheel",
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
    ads: Path = typer.Option(..., "--ads", help="Path to Amazon Ads Search Term Report CSV."),
    rank: Optional[Path] = typer.Option(
        None, "--rank", help="Optional path to Organic Keyword Rank CSV (Helium 10 / DataDive)."
    ),
    amc: Optional[Path] = typer.Option(
        None, "--amc", help="Optional path to exported AMC Clean Room NTB/Halo CSV."
    ),
    category: str = typer.Option("general", "--category", help="Product category prior name."),
    margin: float = typer.Option(0.35, "--margin", help="Pre-ad unit gross margin (0.0 - 1.0)."),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Optional output path for JSON audit report."
    ),
) -> None:
    """Run local Paid-to-Organic flywheel audit from exported Seller Central, Ads, and AMC CSVs."""
    report = audit_amazon_flywheel(
        sqp_csv_path=str(sqp),
        ads_csv_path=str(ads),
        rank_csv_path=str(rank) if rank is not None else None,
        amc_csv_path=str(amc) if amc is not None else None,
        category=category,
        product_margin=margin,
    )
    serialized = json.dumps(report, indent=2)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(serialized + "\n", encoding="utf-8")
        typer.echo(f"Audit report written to {out} ({report['total_keywords']} keywords).")
    else:
        typer.echo(serialized)


@app.command("mcp")
def mcp_command() -> None:
    """Start FastMCP stdio server for Claude Desktop / Cursor."""
    fastmcp_server.run()


@auth_app.command("install-pro")
def auth_install_pro_command(
    key: str = typer.Option(..., "--key", help="Polar.sh Pro license key (e.g. AMZ_FW_PRO_...)."),
    wheel_dir: Optional[Path] = typer.Option(
        None, "--wheel-dir", help="Optional directory containing built amz_flywheel_pro wheel."
    ),
) -> None:
    """Validate Polar.sh license key and install compiled Pro wheel."""
    result = install_pro(api_key=key, wheel_dir=wheel_dir)
    typer.echo(json.dumps(result, indent=2))


@amc_app.command("sql")
def amc_sql_command(
    days: int = typer.Option(28, "--days", help="Lookback window in days."),
    synergy: bool = typer.Option(
        False, "--synergy", help="Print the DSP + Sponsored Products synergy overlap SQL query."
    ),
) -> None:
    """Print privacy-safe Amazon Marketing Cloud (AMC) SQL query with >=100 user cohort threshold."""
    if synergy:
        typer.echo(generate_amc_dsp_search_synergy_sql(lookback_days=days))
    else:
        typer.echo(generate_amc_flywheel_sql(lookback_days=days))


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
    """[Pro] Reallocate weekly PPC budget across keywords using Marginal Response Curves."""
    res = optimize_budget_allocation(total_weekly_budget=budget)
    typer.echo(json.dumps(res, indent=2))


if __name__ == "__main__":
    app()

