"""Organic & Sponsored Keyword Rank CSV parser (Helium 10, DataDive, Perpetua, generic)."""

from __future__ import annotations

import csv
import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable, Optional, Union

from amz_flywheel.contracts.exceptions import SchemaMismatchError
from amz_flywheel.contracts.schemas import RankRecord
from amz_flywheel.io.sqp_parser import (
    normalize_query,
    parse_flexible_date,
    parse_localized_float,
)

UNRANKED_CAP: float = 305.0
MAX_RANK_THRESHOLD: float = 300.0

_RANK_COLUMN_MAP: dict[str, tuple[str, ...]] = {
    "search_query": (
        "keyword",
        "search term",
        "search query",
        "phrase",
        "suchbegriff",
    ),
    "date": (
        "date",
        "timestamp",
        "tracked date",
        "week start",
        "week_start",
        "datum",
    ),
    "organic_rank": (
        "organic rank",
        "organic_rank",
        "organic position",
        "rank",
        "organischer rang",
    ),
    "sponsored_rank": (
        "sponsored rank",
        "sponsored_rank",
        "sponsored position",
        "paid rank",
        "gesponserter rang",
    ),
    "asin": (
        "asin",
        "tracked asin",
        "product asin",
    ),
}


def _parse_organic_rank_value(raw: Optional[str]) -> float:
    """Parse raw organic rank cell; unranked or >300 is capped at 305.0."""
    if raw is None:
        return UNRANKED_CAP
    cleaned = raw.strip().lower()
    if (
        not cleaned
        or cleaned in {"-", "—", "n/a", "na", "unranked", "none", "null", "0"}
        or cleaned.startswith(">")
    ):
        return UNRANKED_CAP
    try:
        val = parse_localized_float(cleaned)
    except ValueError:
        return UNRANKED_CAP
    if val <= 0.0 or val > MAX_RANK_THRESHOLD:
        return UNRANKED_CAP
    return max(1.0, float(val))


def _parse_sponsored_rank_value(raw: Optional[str]) -> Optional[float]:
    """Parse raw sponsored rank cell; returns None if unranked/empty."""
    if raw is None:
        return None
    cleaned = raw.strip().lower()
    if (
        not cleaned
        or cleaned in {"-", "—", "n/a", "na", "unranked", "none", "null", "0"}
        or cleaned.startswith(">")
    ):
        return None
    try:
        val = parse_localized_float(cleaned)
    except ValueError:
        return None
    if val <= 0.0:
        return None
    return min(UNRANKED_CAP, max(1.0, float(val)))


def _resolve_rank_headers(headers: Iterable[str]) -> dict[str, int]:
    """Map normalized Rank CSV field names to column indices."""
    normalized_headers = [h.strip().strip("\ufeff").lower() for h in headers]
    mapping: dict[str, int] = {}
    for field_name, aliases in _RANK_COLUMN_MAP.items():
        for idx, header in enumerate(normalized_headers):
            if header in aliases:
                mapping[field_name] = idx
                break

    required = {"search_query", "date", "organic_rank"}
    missing = required - set(mapping.keys())
    if missing:
        raise SchemaMismatchError(
            f"Rank CSV is missing required columns: {sorted(missing)}. "
            f"Found headers: {list(headers)}"
        )
    return mapping


def parse_rank_csv(
    csv_path: Union[str, Path],
    default_asin: str = "UNKNOWN_ASIN",
) -> list[RankRecord]:
    """
    Parse a Helium 10, DataDive, Perpetua, or generic rank tracker CSV and aggregate
    observations into weekly median `organic_rank` (capped at 305.0) and `sponsored_rank`.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Rank CSV file not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = [row for row in csv.reader(fh) if any(cell.strip() for cell in row)]

    if not rows:
        raise SchemaMismatchError(f"Rank CSV file is empty: {path}")

    col_idx = _resolve_rank_headers(rows[0])
    data_rows = rows[1:]

    org_buckets: dict[tuple[str, str, date], list[float]] = defaultdict(list)
    spon_buckets: dict[tuple[str, str, date], list[float]] = defaultdict(list)

    for row in data_rows:
        if len(row) <= col_idx["search_query"] or len(row) <= col_idx["date"]:
            continue
        query = normalize_query(row[col_idx["search_query"]])
        raw_date = row[col_idx["date"]].strip()
        if not query or not raw_date:
            continue

        week_start = parse_flexible_date(raw_date, align_week=True)
        row_asin = default_asin
        if "asin" in col_idx and col_idx["asin"] < len(row) and row[col_idx["asin"]].strip():
            row_asin = row[col_idx["asin"]].strip().upper()

        key = (row_asin, query, week_start)
        raw_org = (
            row[col_idx["organic_rank"]]
            if col_idx["organic_rank"] < len(row)
            else None
        )
        org_buckets[key].append(_parse_organic_rank_value(raw_org))

        if "sponsored_rank" in col_idx and col_idx["sponsored_rank"] < len(row):
            spon_val = _parse_sponsored_rank_value(row[col_idx["sponsored_rank"]])
            if spon_val is not None:
                spon_buckets[key].append(spon_val)

    records: list[RankRecord] = []
    for (asin, query, week_start), org_vals in sorted(
        org_buckets.items(), key=lambda item: (item[0][0], item[0][1], item[0][2])
    ):
        median_org = float(statistics.median(org_vals))
        spon_vals = spon_buckets.get((asin, query, week_start), [])
        median_spon = float(statistics.median(spon_vals)) if spon_vals else None
        records.append(
            RankRecord(
                asin=asin,
                week_start=week_start,
                search_query=query,
                organic_rank=round(median_org, 2),
                sponsored_rank=round(median_spon, 2) if median_spon is not None else None,
            )
        )

    return records
