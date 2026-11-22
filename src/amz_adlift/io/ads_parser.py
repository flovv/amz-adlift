"""Amazon Ads Search Term CSV parser supporting Legacy, 2026 Unified Reporting, and DE schemas."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable, Optional, Union

from amz_adlift.contracts.exceptions import SchemaMismatchError
from amz_adlift.contracts.schemas import AdsRecord
from amz_adlift.io.sqp_parser import (
    normalize_query,
    parse_flexible_date,
    parse_localized_float,
    parse_localized_int,
)

_ADS_COLUMN_MAP: dict[str, tuple[str, ...]] = {
    "date_range": (
        "date range",
        "date",
        "start date",
        "startdatum",
        "datum",
        "week start",
        "week_start",
    ),
    "end_date": (
        "end date",
        "enddatum",
    ),
    "campaign_name": (
        "campaign name",
        "kampagnenname",
    ),
    "ad_group_name": (
        "ad group name",
        "anzeigengruppenname",
    ),
    "search_query": (
        "customer search term",
        "search term",
        "suchbegriff",
        "search query",
    ),
    "match_type": (
        "match type",
        "targeting match type",
        "übereinstimmungstyp",
    ),
    "ad_impressions": (
        "impressions",
        "impressionen",
    ),
    "ad_clicks": (
        "clicks",
        "klicks",
    ),
    "ad_spend": (
        "spend",
        "total cost",
        "ausgaben",
        "cost",
    ),
    "ad_sales": (
        "7 day total sales",
        "7 day total sales ",
        "sales",
        "7 tage, umsatz gesamt",
        "14 day total sales",
    ),
    "ad_orders": (
        "7 day total orders (#)",
        "purchases",
        "7 tage, aufträge gesamt (#)",
        "orders",
        "14 day total orders (#)",
    ),
    "asin": (
        "advertised asin",
        "asin",
        "purchased asin",
        "beworbene asin",
    ),
}


def _resolve_ads_headers(headers: Iterable[str]) -> dict[str, int]:
    """Map normalized Ads Search Term field names to column indices."""
    normalized_headers = [h.strip().strip("\ufeff").lower() for h in headers]
    mapping: dict[str, int] = {}
    for field_name, aliases in _ADS_COLUMN_MAP.items():
        for idx, header in enumerate(normalized_headers):
            if header in aliases:
                mapping[field_name] = idx
                break

    required = {
        "date_range",
        "search_query",
        "ad_impressions",
        "ad_clicks",
        "ad_spend",
        "ad_sales",
        "ad_orders",
    }
    missing = required - set(mapping.keys())
    if missing:
        raise SchemaMismatchError(
            f"Ads Search Term CSV is missing required columns: {sorted(missing)}. "
            f"Found headers: {list(headers)}"
        )
    return mapping


def parse_ads_csv(
    csv_path: Union[str, Path],
    default_asin: str = "UNKNOWN_ASIN",
) -> list[AdsRecord]:
    """
    Parse an Amazon Ads Search Term CSV (Legacy Sponsored Products, 2026 Unified Reporting,
    or German DE export) and aggregate rows into Sunday-Saturday weekly buckets grouped by
    `(asin, search_query, week_start)`.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Ads Search Term report file not found: {path}")

    if path.suffix.lower() in (".xlsx", ".xlsm"):
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            ws = wb.active
            rows = [
                ["" if cell is None else str(cell) for cell in r]
                for r in ws.iter_rows(values_only=True)
                if any(cell is not None and str(cell).strip() for cell in r)
            ]
        finally:
            wb.close()
    else:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            rows = [row for row in csv.reader(fh) if any(cell.strip() for cell in row)]

    if not rows:
        raise SchemaMismatchError(f"Ads Search Term report file is empty: {path}")

    col_idx = _resolve_ads_headers(rows[0])
    data_rows = rows[1:]

    # Aggregate by (asin, search_query, week_start)
    agg: dict[tuple[str, str, date], dict[str, Union[int, float, str]]] = defaultdict(
        lambda: {
            "campaign_name": "",
            "ad_group_name": "",
            "match_type": "",
            "ad_impressions": 0,
            "ad_clicks": 0,
            "ad_spend": 0.0,
            "ad_sales": 0.0,
            "ad_orders": 0,
        }
    )

    for row in data_rows:
        if len(row) <= col_idx["search_query"] or len(row) <= col_idx["date_range"]:
            continue

        query = normalize_query(row[col_idx["search_query"]])
        raw_date = row[col_idx["date_range"]].strip()
        if not query or not raw_date:
            continue

        week_start = parse_flexible_date(raw_date, align_week=True)

        row_asin = default_asin
        if "asin" in col_idx and col_idx["asin"] < len(row) and row[col_idx["asin"]].strip():
            row_asin = row[col_idx["asin"]].strip().upper()

        key = (row_asin, query, week_start)
        bucket = agg[key]

        def _get_str(field: str) -> str:
            idx = col_idx.get(field)
            if idx is None or idx >= len(row):
                return ""
            return row[idx].strip()

        def _get_int(field: str) -> int:
            idx = col_idx.get(field)
            if idx is None or idx >= len(row):
                return 0
            return max(0, parse_localized_int(row[idx]))

        def _get_float(field: str) -> float:
            idx = col_idx.get(field)
            if idx is None or idx >= len(row):
                return 0.0
            return max(0.0, parse_localized_float(row[idx]))

        if not bucket["campaign_name"]:
            bucket["campaign_name"] = _get_str("campaign_name")
        if not bucket["ad_group_name"]:
            bucket["ad_group_name"] = _get_str("ad_group_name")
        if not bucket["match_type"]:
            bucket["match_type"] = _get_str("match_type")

        bucket["ad_impressions"] = int(bucket["ad_impressions"]) + _get_int("ad_impressions")
        bucket["ad_clicks"] = int(bucket["ad_clicks"]) + _get_int("ad_clicks")
        bucket["ad_spend"] = round(float(bucket["ad_spend"]) + _get_float("ad_spend"), 4)
        bucket["ad_sales"] = round(float(bucket["ad_sales"]) + _get_float("ad_sales"), 4)
        bucket["ad_orders"] = int(bucket["ad_orders"]) + _get_int("ad_orders")

    records: list[AdsRecord] = []
    for (asin, query, week_start), metrics in sorted(
        agg.items(), key=lambda item: (item[0][0], item[0][1], item[0][2])
    ):
        records.append(
            AdsRecord(
                asin=asin,
                week_start=week_start,
                search_query=query,
                campaign_name=str(metrics["campaign_name"]),
                ad_group_name=str(metrics["ad_group_name"]),
                match_type=str(metrics["match_type"]),
                ad_impressions=int(metrics["ad_impressions"]),
                ad_clicks=int(metrics["ad_clicks"]),
                ad_spend=float(metrics["ad_spend"]),
                ad_sales=float(metrics["ad_sales"]),
                ad_orders=int(metrics["ad_orders"]),
            )
        )

    return records
