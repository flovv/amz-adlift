"""Funnel Decomposition Invariant & 4-Quadrant Diagnostic Tests (tests/test_decomposition.py)."""

from datetime import date
from pathlib import Path

import pytest

from amz_adlift.contracts.exceptions import InsufficientHistoryError
from amz_adlift.core import (
    classify_keyword_series,
    classify_panel,
    decompose_observation,
    decompose_panel,
)
from amz_adlift.io import ingest_and_align

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_funnel_decomposition_invariants() -> None:
    """
    Verifies organic_clicks >= 0 and organic_orders >= 0 across all rows, and
    confirms attribution_window_gap == True triggers whenever ad_orders > sqp_purchases.
    """
    panel = ingest_and_align(
        sqp_csv_path=FIXTURES_DIR / "sqp_asin_view.csv",
        ads_csv_path=FIXTURES_DIR / "ads_unified_2026.csv",
        rank_csv_path=FIXTURES_DIR / "rank_helium10.csv",
    )
    decomposed = decompose_panel(panel)

    for row in decomposed:
        assert row.organic_clicks >= 0
        assert row.organic_orders >= 0
        assert row.attribution_window_gap is (row.ad_orders > row.sqp_purchases)
        assert 0.0 <= row.true_paid_share_of_orders <= 1.0

    # Specifically check "chelated magnesium powder": sqp_purchases=2, ad_orders=6
    powder = next(r for r in decomposed if r.search_query == "chelated magnesium powder")
    assert powder.sqp_purchases == 2
    assert powder.ad_orders == 6
    assert powder.organic_orders == 0
    assert powder.attribution_window_gap is True

    # Check "magnesium glycinate 400mg": sqp_clicks=640, ad_clicks=260 -> organic_clicks=380
    mg = next(r for r in decomposed if r.search_query == "magnesium glycinate 400mg")
    assert mg.organic_clicks == 380
    assert mg.organic_orders == 125 - 52
    assert mg.attribution_window_gap is False


def test_decompose_observation_edge_cases() -> None:
    """Tests direct decompose_observation boundary behavior when ad metrics exceed SQP."""
    org_c, org_o, gap, share = decompose_observation(
        sqp_clicks=40, sqp_purchases=5, ad_clicks=75, ad_orders=12
    )
    assert org_c == 0
    assert org_o == 0
    assert gap is True
    assert share == 1.0


def test_four_quadrant_classifier_on_multiweek_panel() -> None:
    """Verifies deterministic 4-quadrant classification across all 4 flywheel archetypes."""
    panel = ingest_and_align(
        sqp_csv_path=FIXTURES_DIR / "sqp_multiweek.csv",
        ads_csv_path=FIXTURES_DIR / "ads_multiweek.csv",
        rank_csv_path=FIXTURES_DIR / "rank_multiweek.csv",
    )
    diagnostics = classify_panel(panel, category="supplements", strict=True)
    by_kw = {d.search_query: d for d in diagnostics}

    assert by_kw["magnesium glycinate 400mg"].quadrant == "CANNIBALIZED_RENT"
    assert by_kw["organic sleep aid capsules"].quadrant == "FLYWHEEL_LEVERAGE"
    assert by_kw["chelated magnesium powder"].quadrant == "TREADMILL_DEAD_WEIGHT"
    assert by_kw["magnesium supplement"].quadrant == "AT_RISK_DECAY"


def test_insufficient_history_handling() -> None:
    """Verifies InsufficientHistoryError when strict=True and INSUFFICIENT_DATA when strict=False."""
    single_week_panel = ingest_and_align(
        sqp_csv_path=FIXTURES_DIR / "sqp_asin_view.csv",
        ads_csv_path=FIXTURES_DIR / "ads_unified_2026.csv",
        rank_csv_path=FIXTURES_DIR / "rank_helium10.csv",
    )
    kw_rows = [
        r for r in single_week_panel if r.search_query == "magnesium glycinate 400mg"
    ]
    with pytest.raises(InsufficientHistoryError):
        classify_keyword_series(kw_rows, strict=True)

    diag = classify_keyword_series(kw_rows, strict=False)
    assert diag.quadrant == "INSUFFICIENT_DATA"


def test_zero_rank_tracker_sqp_proxy_onboarding() -> None:
    """
    Verifies that when rank_csv_path=None (no Helium 10 / DataDive export),
    aligner automatically estimates organic_rank from SQP pure organic click/impression
    share (`rank_is_sqp_proxy=True`) and recovers all 4 flywheel quadrants.
    """
    panel = ingest_and_align(
        sqp_csv_path=FIXTURES_DIR / "sqp_multiweek.csv",
        ads_csv_path=FIXTURES_DIR / "ads_multiweek.csv",
        rank_csv_path=None,
    )
    assert all(r.rank_is_sqp_proxy is True for r in panel)
    assert all(r.organic_rank is not None and r.organic_rank >= 1.0 for r in panel)

    diagnostics = classify_panel(panel, category="supplements", strict=True)
    by_kw = {d.search_query: d for d in diagnostics}

    assert by_kw["magnesium glycinate 400mg"].quadrant == "CANNIBALIZED_RENT"
    assert by_kw["organic sleep aid capsules"].quadrant == "FLYWHEEL_LEVERAGE"
    assert by_kw["chelated magnesium powder"].quadrant == "TREADMILL_DEAD_WEIGHT"
    assert by_kw["magnesium supplement"].quadrant == "AT_RISK_DECAY"

