"""
Tests for all 4 Commercial Upgrades (tests/test_commercial_upgrades.py):
  1. Interactive White-Label HTML/PDF Audit Report (`generate_audit_report`, `amz-adlift report`)
  2. Real Amazon Ads Bulk Operations `.xlsx` Parser & Safe Bid Updater + `.xlsx` Search Term parsing
  3. True KKT Water-Filling Equimarginal Solver, Empirical Hill Fitting & Walk-Forward Backtesting
  4. Production License Hardening (fail-closed without license, no prefix bypass, platform wheel tags)
"""

import json
import math
import random
from pathlib import Path

import openpyxl
import pytest
from typer.testing import CliRunner

try:
    import amz_adlift_pro
except ImportError:
    amz_adlift_pro = None  # type: ignore[assignment]

requires_pro = pytest.mark.skipif(
    amz_adlift_pro is None,
    reason="Optional private amz_adlift_pro Cython extension not installed",
)

from amz_adlift.cli import app
from amz_adlift.contracts.exceptions import ProLicenseError
from amz_adlift.io.ads_parser import parse_ads_csv
from amz_adlift.io.bulksheet_parser import merge_bulksheet_ids, parse_ads_bulksheet
from amz_adlift.mcp_server import (
    audit_amazon_flywheel,
    export_ads_bulksheet,
    generate_audit_report,
    optimize_budget_allocation,
)
from amz_adlift.pro.bridge import enrich_with_pro_elasticity, require_pro
from amz_adlift.pro.installer import detect_wheel_tags, validate_polar_key

FIXTURES_DIR = Path(__file__).parent / "fixtures"
runner = CliRunner()


def _create_mock_amazon_bulksheet(path: Path) -> Path:
    """Create a realistic Amazon Ads Sponsored Products Bulk Operations .xlsx file."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sponsored Products Campaigns"
    ws.append(
        [
            "Product",
            "Entity",
            "Operation",
            "Campaign ID",
            "Ad Group ID",
            "Keyword ID",
            "Campaign Name (Informational only)",
            "Ad Group Name (Informational only)",
            "Keyword Text",
            "Match Type",
            "State",
            "Bid",
        ]
    )
    # Non-keyword row (must be ignored by parser)
    ws.append(
        [
            "Sponsored Products",
            "Campaign",
            "",
            "99000111222",
            "",
            "",
            "SP_Sleep_Exact",
            "",
            "",
            "",
            "enabled",
            "",
        ]
    )
    # Real keyword rows matching multiweek fixtures
    rows = [
        ("99000111222", "88000111", "77000001", "SP_Sleep_Exact", "AG_Exact", "magnesium glycinate 400mg", "EXACT", "enabled", 2.40),
        ("99000111222", "88000111", "77000002", "SP_Sleep_Exact", "AG_Exact", "organic sleep aid capsules", "EXACT", "enabled", 1.85),
        ("99000111222", "88000111", "77000003", "SP_Sleep_Exact", "AG_Exact", "chelated magnesium powder", "EXACT", "enabled", 1.10),
        ("99000111222", "88000111", "77000004", "SP_Sleep_Exact", "AG_Exact", "magnesium supplement", "EXACT", "enabled", 1.60),
    ]
    for cid, agid, kwid, cname, agname, kw, mt, state, bid in rows:
        ws.append(
            [
                "Sponsored Products",
                "Keyword",
                "",
                cid,
                agid,
                kwid,
                cname,
                agname,
                kw,
                mt,
                state,
                bid,
            ]
        )
    wb.save(str(path))
    return path


@requires_pro
def test_real_amazon_bulksheet_merge_and_guardrails(tmp_path: Path) -> None:
    """Verifies real Amazon Ads Bulk .xlsx parsing, ID merge, min/max guardrails, and CLI export."""
    audit_amazon_flywheel(
        sqp_csv_path=str(FIXTURES_DIR / "sqp_multiweek.csv"),
        ads_csv_path=str(FIXTURES_DIR / "ads_multiweek.csv"),
        rank_csv_path=str(FIXTURES_DIR / "rank_multiweek.csv"),
        category="supplements",
        product_margin=0.38,
    )

    existing_bulk = _create_mock_amazon_bulksheet(tmp_path / "seller_central_bulk_export.xlsx")
    targets = parse_ads_bulksheet(existing_bulk)
    assert len(targets) == 4
    assert targets[0].keyword_id == "77000001"

    out_xlsx = tmp_path / "upload_ready_bulk.xlsx"
    res = export_ads_bulksheet(
        output_path=str(out_xlsx),
        existing_bulksheet_path=str(existing_bulk),
        max_bid_change_pct=0.20,
        min_bid=0.25,
        max_bid=5.00,
    )
    assert res["upload_ready"] is True
    assert res["verified_amazon_id_rows"] == 4
    assert len(res["bid_diffs"]) == 4

    diffs_by_kw = {d["search_query"]: d for d in res["bid_diffs"]}
    # CANNIBALIZED_RENT ("magnesium glycinate 400mg") started at real bid 2.40 -> cut 20% = 1.92
    assert diffs_by_kw["magnesium glycinate 400mg"]["keyword_id"] == "77000001"
    assert diffs_by_kw["magnesium glycinate 400mg"]["old_bid"] == pytest.approx(2.40)
    assert diffs_by_kw["magnesium glycinate 400mg"]["new_bid"] == pytest.approx(1.92)
    assert diffs_by_kw["magnesium glycinate 400mg"]["id_source"] == "amazon_bulksheet"

    # Also test Typer CLI `bulksheet` command
    cli_out = tmp_path / "cli_bulk.xlsx"
    cli_res = runner.invoke(
        app,
        [
            "bulksheet",
            "--out",
            str(cli_out),
            "--existing-bulk",
            str(existing_bulk),
            "--max-change",
            "0.25",
            "--min-bid",
            "0.30",
        ],
    )
    assert cli_res.exit_code == 0
    cli_json = json.loads(cli_res.stdout)
    assert cli_json["upload_ready"] is True
    assert cli_out.exists()


def test_native_xlsx_ads_search_term_parsing(tmp_path: Path) -> None:
    """Verifies parse_ads_csv transparently parses native Seller Central .xlsx Search Term exports."""
    xlsx_path = tmp_path / "ads_search_term_report.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(
        [
            "Start Date",
            "End Date",
            "Campaign Name",
            "Ad Group Name",
            "Customer Search Term",
            "Match Type",
            "Impressions",
            "Clicks",
            "Spend",
            "7 Day Total Sales",
            "7 Day Total Orders (#)",
        ]
    )
    ws.append(
        [
            "2026-10-19",
            "2026-10-24",
            "SP_Sleep_Exact",
            "AG_Exact",
            "organic sleep aid capsules",
            "EXACT",
            1200,
            64,
            "$88.50",
            "$350.00",
            10,
        ]
    )
    wb.save(str(xlsx_path))

    recs = parse_ads_csv(xlsx_path, default_asin="B08XYZ123")
    assert len(recs) == 1
    assert recs[0].search_query == "organic sleep aid capsules"
    assert recs[0].ad_spend == pytest.approx(88.50)
    assert recs[0].ad_orders == 10


@requires_pro
def test_kkt_water_filling_empirical_hill_and_walk_forward_backtest() -> None:
    """
    Verifies:
      - True KKT water-filling solver equalizes mROAS across interior keywords (spread < 0.05)
      - Empirical Hill parameter fitting activates when spend varies across >= 5 weeks
      - Walk-forward out-of-sample backtest achieves low rank MAPE and calibrated 90% CI
      - Rank #1.0 bid-cut simulation reflects SERP incrementality (positive net profit lift)
    """
    # 1. Empirical Hill fit with varying spend
    spends = [60.0, 95.0, 140.0, 190.0, 260.0, 320.0]
    orders = [5.0, 8.0, 11.0, 13.5, 16.0, 17.5]
    curve = amz_adlift_pro.compute_marginal_response_curve(
        theta_eb=0.45,
        lambda_decay=0.62,
        product_margin=0.40,
        current_weekly_spend=200.0,
        current_ad_sales=700.0,
        current_ad_orders=14.0,
        current_organic_orders=20.0,
        current_organic_rank=7.0,
        spend_series=spends,
        order_series=orders,
    )
    assert curve["hill_fit_source"] == "empirical_panel"

    # 2. KKT Water-Filling Equimarginal Optimality
    portfolio = amz_adlift_pro.allocate_portfolio_budget(
        keyword_specs=[
            {
                "asin": "B08XYZ123",
                "search_query": "kw_cannibalized",
                "quadrant": "CANNIBALIZED_RENT",
                "current_weekly_spend": 450.0,
                "current_ad_sales": 2000.0,
                "current_ad_orders": 55.0,
                "current_organic_orders": 90.0,
                "current_organic_rank": 1.0,
                "theta_eb": 0.08,
                "lambda_decay": 0.45,
            },
            {
                "asin": "B08XYZ123",
                "search_query": "kw_flywheel",
                "quadrant": "FLYWHEEL_LEVERAGE",
                "current_weekly_spend": 180.0,
                "current_ad_sales": 540.0,
                "current_ad_orders": 15.0,
                "current_organic_orders": 22.0,
                "current_organic_rank": 7.0,
                "theta_eb": 0.50,
                "lambda_decay": 0.65,
            },
            {
                "asin": "B08XYZ123",
                "search_query": "kw_decay",
                "quadrant": "AT_RISK_DECAY",
                "current_weekly_spend": 70.0,
                "current_ad_sales": 180.0,
                "current_ad_orders": 5.0,
                "current_organic_orders": 24.0,
                "current_organic_rank": 4.5,
                "theta_eb": 0.44,
                "lambda_decay": 0.68,
            },
        ],
        total_weekly_budget=700.0,
        product_margin=0.40,
    )
    assert portfolio["solver"] == "kkt_water_filling_equimarginal"
    assert portfolio["total_allocated_spend"] == pytest.approx(700.0, abs=0.5)
    assert portfolio["equimarginal_spread"] <= 0.05
    assert portfolio["projected_weekly_profit_lift"] > 0.0
    assert portfolio["projected_annual_profit_lift"] == pytest.approx(
        portfolio["projected_weekly_profit_lift"] * 52.0, abs=0.5
    )

    # 3. Walk-Forward Out-of-Sample Backtest on 16-week synthetic series
    rng = random.Random(42)
    ad_o, org_o, vols = [], [], []
    for t in range(16):
        ad_o.append(6.0 + 2.5 * t)
        org_o.append(4.0 + 1.4 * t)
        vols.append(12000.0 + 150.0 * math.sin(t))
    v = amz_adlift_pro.compute_velocity_state(ad_o, org_o, 0.60)
    ranks = [
        max(1.0, math.exp(3.2 - 0.42 * math.log(1.0 + v[t]) + 0.10 * math.log(1.0 + vols[t]) + rng.gauss(0.0, 0.015)))
        for t in range(16)
    ]
    bt = amz_adlift_pro.backtest_keyword_elasticity(
        ad_orders=ad_o,
        organic_orders=org_o,
        organic_ranks=ranks,
        search_volumes=vols,
        holdout_weeks=2,
        category="supplements",
    )
    assert bt["status"] == "ok"
    assert bt["holdout_weeks"] == 2
    assert bt["rank_mape"] < 0.15
    assert bt["within_90_ci_rate"] >= 0.50

    # 4. Rank #1.0 Cannibalized Rent bid cut yields positive 21d net profit impact
    sim_rent = amz_adlift_pro.simulate_bid_cut(
        theta_eb=0.08,
        lambda_decay=0.45,
        current_rank=1.0,
        current_velocity=150.0,
        baseline_paid_orders=50.0,
        baseline_organic_orders=90.0,
        baseline_weekly_spend=500.0,
        avg_order_value=35.0,
        product_margin=0.40,
        spend_change_pct=-0.50,
        horizon_weeks=3,
    )
    assert sim_rent["incrementality_factor"] == pytest.approx(0.28, abs=0.01)
    assert sim_rent["net_profit_impact_21d"] > 0.0


def test_white_label_html_audit_report_mcp_and_cli(tmp_path: Path) -> None:
    """Verifies interactive white-label HTML/PDF executive audit report via MCP and CLI."""
    audit_amazon_flywheel(
        sqp_csv_path=str(FIXTURES_DIR / "sqp_multiweek.csv"),
        ads_csv_path=str(FIXTURES_DIR / "ads_multiweek.csv"),
        rank_csv_path=str(FIXTURES_DIR / "rank_multiweek.csv"),
        category="supplements",
        product_margin=0.38,
    )

    html_out = tmp_path / "agency_client_audit.html"
    res = generate_audit_report(
        output_path=str(html_out),
        agency_name="Apex Marketplace Partners",
        client_name="SleepWell Naturals",
    )
    assert html_out.exists()
    assert res["agency_name"] == "Apex Marketplace Partners"
    assert res["client_name"] == "SleepWell Naturals"
    assert res["keywords_rendered"] == 4

    content = html_out.read_text(encoding="utf-8")
    assert "Apex Marketplace Partners" in content
    assert "SleepWell Naturals" in content
    assert 'id="quadrant-chart"' in content
    assert 'id="curve-chart"' in content
    assert "@media print" in content
    assert "Monthly Wasted Spend" in content

    # CLI `amz-adlift report`
    cli_html = tmp_path / "cli_report.html"
    cli_res = runner.invoke(
        app,
        [
            "report",
            "--out",
            str(cli_html),
            "--agency-name",
            "ScaleLabs",
            "--client-name",
            "VitaBrand",
        ],
    )
    assert cli_res.exit_code == 0
    assert cli_html.exists()
    assert "ScaleLabs" in cli_html.read_text(encoding="utf-8")


def test_production_license_gate_fail_closed_and_wheel_tags(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    Verifies production license hardening:
      - With AMZ_ADLIFT_DEV_TEST_MODE unset and no valid license cache,
        offline prefix bypass is REJECTED and Pro Cython calls fail closed.
      - Open-Core `enrich_with_pro_elasticity` degrades gracefully to `{}` instead of crashing.
      - `detect_wheel_tags()` returns valid PEP 425 Python & platform tags.
    """
    monkeypatch.delenv("AMZ_ADLIFT_DEV_TEST_MODE", raising=False)
    monkeypatch.delenv("AMZ_ADLIFT_LICENSE_KEY", raising=False)
    monkeypatch.setenv("AMZ_ADLIFT_LICENSE_CACHE", str(tmp_path / "nonexistent.cache"))

    # 1. Offline prefix bypass must fail closed in production
    with pytest.raises(ProLicenseError):
        validate_polar_key("AMZ_AL_PRO_FAKE_OFFLINE_KEY_9999")

    # 2. Pro Cython functions must enforce runtime license gate (when Pro binary is installed)
    if amz_adlift_pro is not None:
        with pytest.raises(PermissionError):
            amz_adlift_pro.fit_keyword_elasticity(
                [10, 12, 14, 16], [15, 16, 18, 20], [10.0, 8.0, 6.0, 5.0], [1000, 1000, 1000, 1000]
            )

    # 3. require_pro() must wrap PermissionError as ProLicenseError
    with pytest.raises(ProLicenseError):
        require_pro()

    # 4. enrich_with_pro_elasticity degrades gracefully when unlicensed
    assert enrich_with_pro_elasticity([], category="general", product_margin=0.35) == {}

    # 5. Platform wheel tag detector returns valid tags
    tags = detect_wheel_tags()
    assert tags["python_tag"].startswith("cp3")
    assert tags["platform_tag"] in (
        "manylinux_x86_64",
        "manylinux_aarch64",
        "macosx_arm64",
        "macosx_x86_64",
        "win_amd64",
    )
