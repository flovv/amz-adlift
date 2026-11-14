"""Multi-Schema Parser & Weekly Panel Alignment Tests (tests/test_parsers.py)."""

from datetime import date
from pathlib import Path

import pytest

from amz_flywheel.contracts.exceptions import SchemaMismatchError
from amz_flywheel.io import (
    align_panels,
    ingest_and_align,
    parse_ads_csv,
    parse_rank_csv,
    parse_sqp_csv,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_sqp_asin_view_banner_and_normalization() -> None:
    """Ingests Seller Central SQP CSV with Row 1 ASIN=["..."] metadata banner."""
    sqp_rows = parse_sqp_csv(FIXTURES_DIR / "sqp_asin_view.csv")
    assert len(sqp_rows) == 4
    first = sqp_rows[0]
    assert first.asin == "B08XYZ123"
    assert first.week_start == date(2026, 10, 18)
    assert first.search_query == "magnesium glycinate 400mg"
    assert first.search_volume == 28500
    assert first.entity_impressions == 18400
    assert first.entity_clicks == 640
    assert first.entity_purchases == 125


def test_legacy_vs_2026_unified_and_german_ads_alignment() -> None:
    """
    Verifies that Legacy Sponsored Products, 2026 Unified Reporting, and German (DE)
    Ads Search Term CSVs parse and aggregate to identical weekly totals.
    """
    legacy_rows = parse_ads_csv(FIXTURES_DIR / "ads_legacy.csv", default_asin="B08XYZ123")
    unified_rows = parse_ads_csv(FIXTURES_DIR / "ads_unified_2026.csv", default_asin="B08XYZ123")
    de_rows = parse_ads_csv(FIXTURES_DIR / "ads_de.csv", default_asin="B08XYZ123")

    assert len(legacy_rows) == len(unified_rows) == 4
    for leg, uni in zip(legacy_rows, unified_rows):
        assert leg.asin == uni.asin == "B08XYZ123"
        assert leg.week_start == uni.week_start == date(2026, 10, 18)
        assert leg.search_query == uni.search_query
        assert leg.ad_impressions == uni.ad_impressions
        assert leg.ad_clicks == uni.ad_clicks
        assert leg.ad_spend == pytest.approx(uni.ad_spend)
        assert leg.ad_sales == pytest.approx(uni.ad_sales)
        assert leg.ad_orders == uni.ad_orders

    # Check German DE localized decimal/thousand parsing ("8.000", "390,75 €", "1.820,00 €")
    de_mg = next(r for r in de_rows if r.search_query == "magnesium glycinate 400mg")
    assert de_mg.week_start == date(2026, 10, 18)
    assert de_mg.ad_impressions == 8000
    assert de_mg.ad_clicks == 260
    assert de_mg.ad_spend == pytest.approx(390.75)
    assert de_mg.ad_sales == pytest.approx(1820.00)
    assert de_mg.ad_orders == 52


def test_rank_parser_weekly_median_and_unranked_cap() -> None:
    """Verifies weekly median organic_rank aggregation and >300 / unranked cap at 305.0."""
    rank_rows = parse_rank_csv(FIXTURES_DIR / "rank_helium10.csv", default_asin="B08XYZ123")
    by_kw = {r.search_query: r for r in rank_rows}

    assert by_kw["magnesium glycinate 400mg"].organic_rank == 1.0
    assert by_kw["magnesium glycinate 400mg"].sponsored_rank == 1.0
    assert by_kw["organic sleep aid capsules"].organic_rank == 7.0
    assert by_kw["organic sleep aid capsules"].sponsored_rank == 2.5
    assert by_kw["chelated magnesium powder"].organic_rank == 305.0
    assert by_kw["chelated magnesium powder"].sponsored_rank == 12.0


def test_panel_alignment_legacy_and_unified() -> None:
    """Joins SQP, Ads (Legacy & Unified), and Rank CSVs onto (asin, query, week_start)."""
    panel_legacy = ingest_and_align(
        sqp_csv_path=FIXTURES_DIR / "sqp_asin_view.csv",
        ads_csv_path=FIXTURES_DIR / "ads_legacy.csv",
        rank_csv_path=FIXTURES_DIR / "rank_helium10.csv",
    )
    panel_unified = ingest_and_align(
        sqp_csv_path=FIXTURES_DIR / "sqp_asin_view.csv",
        ads_csv_path=FIXTURES_DIR / "ads_unified_2026.csv",
        rank_csv_path=FIXTURES_DIR / "rank_helium10.csv",
    )

    assert len(panel_legacy) == len(panel_unified) == 4
    for r_leg, r_uni in zip(panel_legacy, panel_unified):
        assert r_leg.model_dump() == r_uni.model_dump()


def test_schema_mismatch_error_on_invalid_csv(tmp_path: Path) -> None:
    """Raises SchemaMismatchError when CSV headers do not match supported schemas."""
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("foo,bar,baz\n1,2,3\n", encoding="utf-8")
    with pytest.raises(SchemaMismatchError):
        parse_sqp_csv(bad_csv)
    with pytest.raises(SchemaMismatchError):
        parse_ads_csv(bad_csv)
    with pytest.raises(SchemaMismatchError):
        parse_rank_csv(bad_csv)


def test_multi_file_sqp_directory_ingestion(tmp_path: Path) -> None:
    """
    Verifies onboarding with a folder of separate weekly Seller Central SQP CSV exports
    (each with its own Row 1 Select Week banner).
    """
    sqp_dir = tmp_path / "sqp_weekly"
    sqp_dir.mkdir()
    weeks = [
        ("2026-09-27", "2026-10-03"),
        ("2026-10-04", "2026-10-10"),
        ("2026-10-11", "2026-10-17"),
        ("2026-10-18", "2026-10-24"),
    ]
    header = (
        '"Search Query","Search Query Score","Search Query Volume",'
        '"Impressions: Total Count","Impressions: ASIN Count",'
        '"Clicks: Total Count","Clicks: ASIN Count",'
        '"Cart Adds: Total Count","Cart Adds: ASIN Count",'
        '"Purchases: Total Count","Purchases: ASIN Count"\n'
    )
    row = '"magnesium glycinate 400mg","1","28,500","120,000","18,400","4,200","640","1,100","195","680","125"\n'

    for idx, (w_start, w_end) in enumerate(weeks, start=1):
        banner = f'"ASIN=[""B08XYZ123""]","Reporting Range=[""Weekly""]","Select Week=[""{w_start} - {w_end}""]"\n'
        (sqp_dir / f"sqp_week_{idx}.csv").write_text(banner + header + row, encoding="utf-8")

    records = parse_sqp_csv(sqp_dir)
    assert len(records) == 4
    assert [r.week_start for r in records] == [
        date(2026, 9, 27),
        date(2026, 10, 4),
        date(2026, 10, 11),
        date(2026, 10, 18),
    ]

