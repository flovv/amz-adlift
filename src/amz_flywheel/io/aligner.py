"""Panel aligner joining SQP, Ads, Rank, and optional AMC Clean Room records on (asin, search_query, week_start)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable, Optional, Union

from amz_flywheel.contracts.schemas import (
    AdsRecord,
    RankRecord,
    SQPRecord,
    UnifiedKeywordWeek,
)
from amz_flywheel.core.decomposition import decompose_observation
from amz_flywheel.io.ads_parser import parse_ads_csv
from amz_flywheel.io.amc_connector import (
    AMC_LONG_TAIL_BUCKET,
    AMCKewordWeekRecord,
    parse_amc_csv,
)
from amz_flywheel.io.rank_parser import parse_rank_csv
from amz_flywheel.io.sqp_parser import parse_sqp_csv


def estimate_sqp_organic_rank(
    sqp: SQPRecord,
    ad_impressions: int,
    organic_clicks: int,
) -> float:
    """
    Estimate an implied organic SERP rank position (1.0 .. 305.0) from Brand Analytics
    SQP pure organic click share and pure organic impression share when no external
    rank tracker CSV (e.g. Helium 10 / DataDive) is provided.
    """
    org_impressions = max(0, int(sqp.entity_impressions) - int(ad_impressions))
    imp_share = float(org_impressions) / float(max(1, sqp.total_impressions))
    clk_share = float(organic_clicks) / float(max(1, sqp.total_clicks))
    vis_share = 0.65 * clk_share + 0.35 * imp_share

    if vis_share <= 0.0005:
        return 305.0

    implied = (0.11 / vis_share) ** 1.45
    return round(min(305.0, max(1.0, implied)), 2)


def align_panels(
    sqp_records: Iterable[SQPRecord],
    ads_records: Iterable[AdsRecord],
    rank_records: Optional[Iterable[RankRecord]] = None,
    amc_records: Optional[Iterable[AMCKewordWeekRecord]] = None,
    infer_rank_from_sqp: bool = True,
) -> list[UnifiedKeywordWeek]:
    """
    Join SQP, Ads, optional Rank, and optional AMC Clean Room records on
    `(asin, search_query, week_start)` and isolate pure organic funnel metrics.
    """
    sqp_list = list(sqp_records)
    ads_list = list(ads_records)
    rank_list = list(rank_records) if rank_records is not None else []
    amc_list = list(amc_records) if amc_records is not None else []

    primary_asin = (
        sqp_list[0].asin
        if sqp_list
        else (ads_list[0].asin if ads_list else "UNKNOWN_ASIN")
    )

    ads_by_key: dict[tuple[str, str, date], AdsRecord] = {}
    ads_by_query_week: dict[tuple[str, date], AdsRecord] = {}
    for ad in ads_list:
        resolved_asin = primary_asin if ad.asin == "UNKNOWN_ASIN" else ad.asin
        ads_by_key[(resolved_asin, ad.search_query, ad.week_start)] = ad
        ads_by_query_week[(ad.search_query, ad.week_start)] = ad

    rank_by_key: dict[tuple[str, str, date], RankRecord] = {}
    rank_by_query_week: dict[tuple[str, date], RankRecord] = {}
    for rk in rank_list:
        resolved_asin = primary_asin if rk.asin == "UNKNOWN_ASIN" else rk.asin
        rank_by_key[(resolved_asin, rk.search_query, rk.week_start)] = rk
        rank_by_query_week[(rk.search_query, rk.week_start)] = rk

    amc_by_key: dict[tuple[str, str, date], AMCKewordWeekRecord] = {}
    amc_by_query_week: dict[tuple[str, date], AMCKewordWeekRecord] = {}
    for amc in amc_list:
        resolved_asin = primary_asin if amc.asin == "UNKNOWN_ASIN" else amc.asin
        amc_by_key[(resolved_asin, amc.search_query, amc.week_start)] = amc
        amc_by_query_week[(amc.search_query, amc.week_start)] = amc

    panel: list[UnifiedKeywordWeek] = []
    for sqp in sorted(sqp_list, key=lambda r: (r.asin, r.search_query, r.week_start)):
        key = (sqp.asin, sqp.search_query, sqp.week_start)
        ad = ads_by_key.get(key) or ads_by_query_week.get((sqp.search_query, sqp.week_start))
        rk = rank_by_key.get(key) or rank_by_query_week.get((sqp.search_query, sqp.week_start))
        amc = (
            amc_by_key.get(key)
            or amc_by_query_week.get((sqp.search_query, sqp.week_start))
            or amc_by_query_week.get((AMC_LONG_TAIL_BUCKET, sqp.week_start))
        )

        ad_impressions = ad.ad_impressions if ad else 0
        ad_clicks = ad.ad_clicks if ad else 0
        ad_spend = ad.ad_spend if ad else 0.0
        ad_orders = ad.ad_orders if ad else 0
        ad_sales = ad.ad_sales if ad else 0.0

        org_clicks, org_orders, gap, _ = decompose_observation(
            sqp_clicks=sqp.entity_clicks,
            sqp_purchases=sqp.entity_purchases,
            ad_clicks=ad_clicks,
            ad_orders=ad_orders,
        )

        if rk is not None:
            resolved_org_rank: Optional[float] = rk.organic_rank
            resolved_spon_rank: Optional[float] = rk.sponsored_rank
            is_proxy = False
        elif infer_rank_from_sqp:
            resolved_org_rank = estimate_sqp_organic_rank(
                sqp=sqp,
                ad_impressions=ad_impressions,
                organic_clicks=org_clicks,
            )
            resolved_spon_rank = None
            is_proxy = True
        else:
            resolved_org_rank = None
            resolved_spon_rank = None
            is_proxy = False

        panel.append(
            UnifiedKeywordWeek(
                asin=sqp.asin,
                search_query=sqp.search_query,
                week_start=sqp.week_start,
                search_volume=sqp.search_volume,
                sqp_impressions=sqp.entity_impressions,
                sqp_clicks=sqp.entity_clicks,
                sqp_cart_adds=sqp.entity_cart_adds,
                sqp_purchases=sqp.entity_purchases,
                total_market_clicks=sqp.total_clicks,
                total_market_purchases=sqp.total_purchases,
                ad_impressions=ad_impressions,
                ad_clicks=ad_clicks,
                ad_spend=ad_spend,
                ad_orders=ad_orders,
                ad_sales=ad_sales,
                organic_clicks=org_clicks,
                organic_orders=org_orders,
                attribution_window_gap=gap,
                organic_rank=resolved_org_rank,
                sponsored_rank=resolved_spon_rank,
                rank_is_sqp_proxy=is_proxy,
                amc_ntb_orders=amc.ntb_purchases if amc else None,
                amc_ntb_share=round(amc.ntb_order_share, 4) if amc else None,
                amc_brand_halo_orders=amc.brand_halo_purchases if amc else None,
                amc_reached_users=amc.reached_users if amc else None,
                campaign_name=ad.campaign_name if ad else "",
                ad_group_name=ad.ad_group_name if ad else "",
                match_type=ad.match_type if ad else "",
            )
        )

    return panel


def ingest_and_align(
    sqp_csv_path: Union[str, Path, Iterable[Union[str, Path]]],
    ads_csv_path: Union[str, Path],
    rank_csv_path: Optional[Union[str, Path]] = None,
    amc_csv_path: Optional[Union[str, Path]] = None,
    default_asin: Optional[str] = None,
    infer_rank_from_sqp: bool = True,
) -> list[UnifiedKeywordWeek]:
    """
    Parse SQP (single CSV, directory of weekly CSVs, or glob pattern), Ads, optional
    Rank, and optional AMC Clean Room CSVs from disk and return the aligned weekly panel.
    """
    sqp_records = parse_sqp_csv(sqp_csv_path, default_asin=default_asin)
    inferred_asin = (
        sqp_records[0].asin if sqp_records else (default_asin or "UNKNOWN_ASIN")
    )
    ads_records = parse_ads_csv(ads_csv_path, default_asin=inferred_asin)
    rank_records = (
        parse_rank_csv(rank_csv_path, default_asin=inferred_asin)
        if rank_csv_path is not None
        else None
    )
    amc_records = (
        parse_amc_csv(amc_csv_path, default_asin=inferred_asin)
        if amc_csv_path is not None
        else None
    )
    return align_panels(
        sqp_records,
        ads_records,
        rank_records,
        amc_records=amc_records,
        infer_rank_from_sqp=infer_rank_from_sqp,
    )
