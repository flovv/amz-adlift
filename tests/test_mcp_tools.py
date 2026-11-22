"""FastMCP Server Tools, Resources, Prompts & Typer CLI Tests (tests/test_mcp_tools.py)."""

import importlib.util
import json
from pathlib import Path

import openpyxl
import pytest
from typer.testing import CliRunner

HAS_PRO = importlib.util.find_spec("amz_adlift_pro") is not None
requires_pro = pytest.mark.skipif(
    not HAS_PRO,
    reason="Optional private amz_adlift_pro Cython extension not installed",
)

from amz_adlift.cli import app
from amz_adlift.mcp_server import (
    _LAST_AUDIT_STATE,
    activate_amz_adlift_pro,
    audit_amazon_flywheel,
    executive_flywheel_audit_prompt,
    export_ads_bulksheet,
    get_category_priors_resource,
    get_quadrant_definitions_resource,
    simulate_keyword_bid_cut,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
runner = CliRunner()


def test_mcp_audit_simulate_and_bulksheet_tools(tmp_path: Path) -> None:
    """Tests FastMCP tools end-to-end on local multi-week fixtures."""
    report = audit_amazon_flywheel(
        sqp_csv_path=str(FIXTURES_DIR / "sqp_multiweek.csv"),
        ads_csv_path=str(FIXTURES_DIR / "ads_multiweek.csv"),
        rank_csv_path=str(FIXTURES_DIR / "rank_multiweek.csv"),
        category="supplements",
        product_margin=0.38,
    )

    assert report["asin"] == "B08XYZ123"
    assert report["total_keywords"] == 4
    assert report["total_weeks"] == 6
    assert report["quadrant_counts"]["CANNIBALIZED_RENT"] == 1
    assert report["quadrant_counts"]["FLYWHEEL_LEVERAGE"] == 1
    assert report["quadrant_counts"]["TREADMILL_DEAD_WEIGHT"] == 1
    assert report["quadrant_counts"]["AT_RISK_DECAY"] == 1
    assert "quadrant_playbook" in report

    if HAS_PRO:
        # Pro simulation tool
        sim = simulate_keyword_bid_cut(
            search_query="organic sleep aid capsules",
            asin="B08XYZ123",
            spend_change_pct=-0.50,
            horizon_weeks=3,
        )
        assert sim["asin"] == "B08XYZ123"
        assert sim["search_query"] == "organic sleep aid capsules"
        assert sim["data_source"] == "audited_panel"
        assert len(sim["projected_ranks"]) == 3
        assert "-25%" in sim["scenarios"]
        assert "-50%" in sim["scenarios"]
        assert "-100%" in sim["scenarios"]

        # Pro Amazon Ads Bulk Operations spreadsheet export
        bulk_xlsx = tmp_path / "bulk_ops.xlsx"
        bulk_res = export_ads_bulksheet(
            output_path=str(bulk_xlsx),
            max_bid_change_pct=0.25,
        )
        assert bulk_res["rows_written"] == 4
        assert bulk_res["operation"] == "Update"
        assert bulk_xlsx.exists()

        wb = openpyxl.load_workbook(bulk_xlsx)
        ws = wb["Sponsored Products Campaigns"]
        rows = list(ws.iter_rows(values_only=True))
        assert len(rows) == 5  # 1 header + 4 keyword rows
        assert rows[0][2] == "Operation"
        for data_row in rows[1:]:
            assert data_row[2] == "Update"
            assert float(data_row[11]) > 0.0


def test_agent_resilience_normalization_and_state_persistence() -> None:
    """
    Verifies agent-readiness features:
    - Auto-normalization when LLM passes whole percentages (38 -> 0.38, -50 -> -0.50)
    - Context-saving mode (`include_raw_panel=False`)
    - Disk state persistence across process restarts (`~/.amz_adlift/last_audit_state.json`)
    - MCP resources and prompt generation
    """
    report = audit_amazon_flywheel(
        sqp_csv_path=str(FIXTURES_DIR / "sqp_multiweek.csv"),
        ads_csv_path=str(FIXTURES_DIR / "ads_multiweek.csv"),
        rank_csv_path=str(FIXTURES_DIR / "rank_multiweek.csv"),
        category="supplements",
        product_margin=38.0,  # Whole percentage passed by LLM
        include_raw_panel=False,
    )
    assert report["product_margin"] == pytest.approx(0.38)
    assert report["panel"] == []

    # Simulate process restart by clearing in-memory state
    _LAST_AUDIT_STATE["panel"] = []
    _LAST_AUDIT_STATE["diagnostics"] = []

    # Tool automatically reloads persisted state from ~/.amz_adlift/last_audit_state.json
    # and normalizes spend_change_pct=-50.0 -> -0.50
    if HAS_PRO:
        sim = simulate_keyword_bid_cut(
            search_query="organic sleep aid capsules",
            asin="ANY",
            spend_change_pct=-50.0,
            horizon_weeks=3,
        )
        assert sim["data_source"] == "audited_panel"
        assert sim["spend_change_pct"] == pytest.approx(-0.50)

    # Verify MCP resources and prompt
    quads_json = json.loads(get_quadrant_definitions_resource())
    assert "CANNIBALIZED_RENT" in quads_json
    priors_json = json.loads(get_category_priors_resource())
    assert "supplements" in priors_json
    prompt_text = executive_flywheel_audit_prompt(
        sqp_csv_path="sqp.csv", ads_csv_path="ads.csv", product_margin=0.38
    )
    assert "audit_amazon_flywheel" in prompt_text


def test_mcp_activate_pro_and_cli_commands(tmp_path: Path) -> None:
    """Tests activate_amz_adlift_pro and Typer CLI audit + auth install-pro commands."""
    auth_res = activate_amz_adlift_pro("AMZ_AL_PRO_TEST_KEY_2026")
    assert auth_res["status"] == "activated"
    assert auth_res["license"]["valid"] is True

    out_json = tmp_path / "audit_report.json"
    res = runner.invoke(
        app,
        [
            "audit",
            "--sqp",
            str(FIXTURES_DIR / "sqp_multiweek.csv"),
            "--ads",
            str(FIXTURES_DIR / "ads_multiweek.csv"),
            "--rank",
            str(FIXTURES_DIR / "rank_multiweek.csv"),
            "--margin",
            "0.38",
            "--out",
            str(out_json),
        ],
    )
    assert res.exit_code == 0
    assert out_json.exists()
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["total_keywords"] == 4


def test_amc_clean_room_markov_and_red_team_flags(tmp_path: Path) -> None:
    """
    Tests AMC privacy-safe SQL generation (HAVING COUNT(DISTINCT user_id) >= 100),
    First-Order Markov Chain Removal Effects vs. Last-Touch variance, and AMC NTB
    CSV ingestion with Adversarial Red-Team flags.
    """
    from amz_adlift.mcp_server import analyze_amc_clean_room

    amc_res = analyze_amc_clean_room(lookback_days=28)
    assert amc_res["privacy_cohort_threshold"] == 100
    assert "HAVING COUNT(DISTINCT user_id) >= 100" in amc_res["amc_flywheel_ntb_sql"]
    assert "__amc_long_tail_cohort__" in amc_res["amc_flywheel_ntb_sql"]

    markov = amc_res["markov_attribution"]
    # Upper-funnel DSP has higher Markov share than Last-Touch share
    assert markov["markov_attributed_share"]["DSP"] > markov["last_touch_share"]["DSP"]
    assert markov["variance_vs_last_touch"]["DSP"] > 0.0

    # Create a mock AMC CSV export where "magnesium glycinate 400mg" has only 10% NTB orders
    amc_csv = tmp_path / "amc_export.csv"
    amc_csv.write_text(
        "asin,search_query,week_start,reached_users,total_purchases,ntb_purchases,total_sales,ntb_sales\n"
        "B08XYZ123,magnesium glycinate 400mg,2026-10-04,450,50,5,1750.0,175.0\n"
        "B08XYZ123,magnesium glycinate 400mg,2026-10-11,480,50,5,1750.0,175.0\n"
        "B08XYZ123,magnesium glycinate 400mg,2026-10-18,510,50,5,1750.0,175.0\n"
        "B08XYZ123,organic sleep aid capsules,2026-10-18,220,18,14,630.0,490.0\n",
        encoding="utf-8",
    )

    report = audit_amazon_flywheel(
        sqp_csv_path=str(FIXTURES_DIR / "sqp_multiweek.csv"),
        ads_csv_path=str(FIXTURES_DIR / "ads_multiweek.csv"),
        rank_csv_path=str(FIXTURES_DIR / "rank_multiweek.csv"),
        amc_csv_path=str(amc_csv),
        category="supplements",
        product_margin=0.38,
    )
    by_kw = {k["search_query"]: k for k in report["keywords"]}
    mg_diag = by_kw["magnesium glycinate 400mg"]
    assert mg_diag["amc_ntb_share_4w"] == pytest.approx(0.10)
    assert "LOW_AMC_NTB_REPEAT_CUSTOMER_CANNIBALIZATION" in mg_diag["red_team_flags"]
    assert any(
        "LOW_AMC_NTB_REPEAT_CUSTOMER_CANNIBALIZATION" in w
        for w in report["red_team_warnings"]
    )


@requires_pro
def test_optimize_budget_allocation_mcp_and_cli() -> None:
    """
    Tests the `optimize_budget_allocation` MCP tool and `amz-adlift allocate` CLI command,
    verifying that keywords receive marginal response curves and equimarginal budget shifts.
    """
    from amz_adlift.mcp_server import optimize_budget_allocation

    report = audit_amazon_flywheel(
        sqp_csv_path=str(FIXTURES_DIR / "sqp_multiweek.csv"),
        ads_csv_path=str(FIXTURES_DIR / "ads_multiweek.csv"),
        rank_csv_path=str(FIXTURES_DIR / "rank_multiweek.csv"),
        category="supplements",
        product_margin=0.38,
    )
    by_kw = {k["search_query"]: k for k in report["keywords"]}
    # Verify marginal response fields are populated on keyword pro_metrics
    assert by_kw["magnesium glycinate 400mg"]["pro_metrics"]["marginal_paid_roas"] is not None
    assert by_kw["organic sleep aid capsules"]["pro_metrics"]["marginal_organic_roas"] is not None
    assert (
        by_kw["organic sleep aid capsules"]["pro_metrics"]["marginal_total_roas"]
        > by_kw["magnesium glycinate 400mg"]["pro_metrics"]["marginal_total_roas"]
    )

    alloc_res = optimize_budget_allocation()
    assert alloc_res["projected_weekly_profit_lift"] >= 0.0
    alloc_by_kw = {a["search_query"]: a for a in alloc_res["allocations"]}
    assert alloc_by_kw["magnesium glycinate 400mg"]["spend_delta"] < 0.0
    assert alloc_by_kw["organic sleep aid capsules"]["spend_delta"] > 0.0

    cli_res = runner.invoke(app, ["allocate", "--budget", "600"])
    assert cli_res.exit_code == 0
    cli_json = json.loads(cli_res.stdout)
    assert cli_json["total_allocated_spend"] == pytest.approx(600.0, abs=1.0)


