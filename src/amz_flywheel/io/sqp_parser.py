"""Brand Analytics Search Query Performance (SQP) CSV parser (ASIN & Brand View)."""

from __future__ import annotations

import csv
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional, Union

from amz_flywheel.contracts.exceptions import SchemaMismatchError
from amz_flywheel.contracts.schemas import SQPRecord

_CURRENCY_RE = re.compile(r"[€$£¥%\s\u00a0]")
_INT_THOUSANDS_RE = re.compile(r"^-?\d{1,3}([.,]\d{3})+$")
_ASIN_BANNER_RE = re.compile(r'ASIN\s*=\s*\[\s*"?([A-Z0-9_-]{5,20})"?\s*\]', re.IGNORECASE)
_BRAND_BANNER_RE = re.compile(r'Brand\s*=\s*\[\s*"?([^"\]]+)"?\s*\]', re.IGNORECASE)
_WEEK_BANNER_RE = re.compile(
    r'Select\s+Week\s*=\s*\[\s*"?([^"\]]+)"?\s*\]', re.IGNORECASE
)
_MONTH_BANNER_RE = re.compile(
    r'Select\s+Month\s*=\s*\[\s*"?([^"\]]+)"?\s*\]', re.IGNORECASE
)
_ISO_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_ISO_MONTH_RE = re.compile(r"(\d{4}-\d{2})")


def normalize_query(query: str) -> str:
    """Lowercase, strip, and normalize internal whitespace of a search query."""
    return " ".join(query.strip().lower().split())


def align_to_sunday(dt: date) -> date:
    """Align any date to the Sunday start of its Amazon SQP week (Sunday-Saturday)."""
    days_since_sunday = (dt.weekday() + 1) % 7
    return dt - timedelta(days=days_since_sunday)


def parse_flexible_date(raw: str, align_week: bool = True) -> date:
    """Parse ISO, US, EU/DE, or date-range strings into a Python date."""
    cleaned = raw.strip().strip('"').strip("'")
    if not cleaned:
        raise ValueError("Empty date string")

    iso_match = _ISO_DATE_RE.search(cleaned)
    if iso_match:
        parsed = date.fromisoformat(iso_match.group(1))
        return align_to_sunday(parsed) if align_week else parsed

    # Handle range separators like "10/18/2026 - 10/24/2026" or "18.10.2026 - 24.10.2026"
    first_part = re.split(r"\s*(?:-\s+|\bis\b|\bto\b|–|—)\s*", cleaned)[0].strip()

    for fmt in (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d.%m.%Y",
        "%Y/%m/%d",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d/%m/%Y",
    ):
        try:
            parsed = datetime.strptime(first_part, fmt).date()
            return align_to_sunday(parsed) if align_week else parsed
        except ValueError:
            continue

    month_match = _ISO_MONTH_RE.search(cleaned)
    if month_match:
        parsed = date.fromisoformat(f"{month_match.group(1)}-01")
        return align_to_sunday(parsed) if align_week else parsed

    raise ValueError(f"Unrecognized date format: {raw!r}")


def parse_localized_float(value: Union[str, int, float, None]) -> float:
    """Parse localized US/UK (1,234.56) or EU/DE (1.234,56) numeric strings."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = _CURRENCY_RE.sub("", str(value).strip())
    if not cleaned or cleaned.lower() in {"-", "—", "n/a", "na", "null", "none"}:
        return 0.0

    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            # EU/DE format: 1.234,56
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            # US/UK format: 1,234.56
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # Check if comma is decimal separator (e.g. 12,34 or 0,5) vs thousands (1,234)
        parts = cleaned.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    return float(cleaned)


def parse_localized_int(value: Union[str, int, float, None]) -> int:
    """Parse localized integer counts (handling thousand separators in US and DE)."""
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    cleaned = _CURRENCY_RE.sub("", str(value).strip())
    if not cleaned or cleaned.lower() in {"-", "—", "n/a", "na", "null", "none"}:
        return 0
    if _INT_THOUSANDS_RE.match(cleaned):
        return int(cleaned.replace(",", "").replace(".", ""))
    return int(round(parse_localized_float(cleaned)))


_SQP_COLUMN_MAP: dict[str, tuple[str, ...]] = {
    "search_query": ("search query", "suchanfrage", "search term"),
    "sqp_score": ("search query score", "suchanfrage-score", "query score"),
    "search_volume": ("search query volume", "suchanfragevolumen", "search volume"),
    "total_impressions": (
        "impressions: total count",
        "impressionen: gesamtanzahl",
        "total impressions",
    ),
    "entity_impressions": (
        "impressions: asin count",
        "impressions: brand count",
        "impressionen: asin-anzahl",
        "impressionen: markenanzahl",
        "asin impressions",
        "brand impressions",
    ),
    "total_clicks": (
        "clicks: total count",
        "klicks: gesamtanzahl",
        "total clicks",
    ),
    "entity_clicks": (
        "clicks: asin count",
        "clicks: brand count",
        "klicks: asin-anzahl",
        "klicks: markenanzahl",
        "asin clicks",
        "brand clicks",
    ),
    "total_cart_adds": (
        "cart adds: total count",
        "einkaufswagen-hinzufügungen: gesamtanzahl",
        "total cart adds",
    ),
    "entity_cart_adds": (
        "cart adds: asin count",
        "cart adds: brand count",
        "einkaufswagen-hinzufügungen: asin-anzahl",
        "einkaufswagen-hinzufügungen: markenanzahl",
        "asin cart adds",
        "brand cart adds",
    ),
    "total_purchases": (
        "purchases: total count",
        "käufe: gesamtanzahl",
        "total purchases",
    ),
    "entity_purchases": (
        "purchases: asin count",
        "purchases: brand count",
        "käufe: asin-anzahl",
        "käufe: markenanzahl",
        "asin purchases",
        "brand purchases",
    ),
}


def _extract_banner_metadata(row_cells: list[str]) -> tuple[Optional[str], Optional[date]]:
    """Extract ASIN/Brand and Select Week/Month from Row 1 metadata banner."""
    joined = ",".join(row_cells)
    asin_val: Optional[str] = None
    week_val: Optional[date] = None

    asin_match = _ASIN_BANNER_RE.search(joined)
    if asin_match:
        asin_val = asin_match.group(1).upper()
    else:
        brand_match = _BRAND_BANNER_RE.search(joined)
        if brand_match:
            asin_val = f"BRAND:{brand_match.group(1).strip()}"

    week_match = _WEEK_BANNER_RE.search(joined)
    if week_match:
        raw_week = week_match.group(1)
        # If Select Week start is explicitly given (e.g. 2026-10-18 - 2026-10-24),
        # keep the exact start date if it is already ISO, or align to Sunday
        iso_match = _ISO_DATE_RE.search(raw_week)
        if iso_match:
            week_val = align_to_sunday(date.fromisoformat(iso_match.group(1)))
        else:
            week_val = parse_flexible_date(raw_week, align_week=True)
    else:
        month_match = _MONTH_BANNER_RE.search(joined)
        if month_match:
            week_val = parse_flexible_date(month_match.group(1), align_week=True)

    return asin_val, week_val


def _resolve_header_indices(headers: Iterable[str]) -> dict[str, int]:
    """Map normalized SQP field names to column indices."""
    normalized_headers = [h.strip().strip("\ufeff").lower() for h in headers]
    mapping: dict[str, int] = {}
    for field_name, aliases in _SQP_COLUMN_MAP.items():
        for idx, header in enumerate(normalized_headers):
            if header in aliases:
                mapping[field_name] = idx
                break

    # Optional inline columns for multi-week / multi-ASIN exports
    for idx, header in enumerate(normalized_headers):
        if header in ("asin", "child asin", "advertised asin"):
            mapping["asin"] = idx
        elif header in ("reporting date", "week start", "week_start", "select week", "date"):
            mapping["week_start"] = idx

    required = {
        "search_query",
        "search_volume",
        "total_impressions",
        "entity_impressions",
        "total_clicks",
        "entity_clicks",
        "total_cart_adds",
        "entity_cart_adds",
        "total_purchases",
        "entity_purchases",
    }
    missing = required - set(mapping.keys())
    if missing:
        raise SchemaMismatchError(
            f"SQP CSV is missing required columns: {sorted(missing)}. "
            f"Found headers: {list(headers)}"
        )
    return mapping


def resolve_csv_paths(
    path_spec: Union[str, Path, Iterable[Union[str, Path]]],
) -> list[Path]:
    """
    Resolve a single CSV file path, a directory containing CSV files, a glob pattern,
    comma-separated paths, or an iterable of paths into a sorted list of existing Paths.
    """
    if isinstance(path_spec, (list, tuple, set)):
        resolved: list[Path] = []
        for item in path_spec:
            resolved.extend(resolve_csv_paths(item))
        return resolved

    raw_str = str(path_spec).strip()
    if "," in raw_str and not Path(raw_str).exists():
        parts = [p.strip() for p in raw_str.split(",") if p.strip()]
        resolved = []
        for part in parts:
            resolved.extend(resolve_csv_paths(part))
        return resolved

    candidate = Path(raw_str)
    if candidate.is_dir():
        csv_files = sorted(candidate.glob("*.csv"))
        if not csv_files:
            raise FileNotFoundError(f"No .csv files found in directory: {candidate}")
        return csv_files

    if any(ch in raw_str for ch in ("*", "?", "[")) and not candidate.exists():
        import glob as _glob

        matches = sorted(Path(p) for p in _glob.glob(raw_str) if Path(p).is_file())
        if not matches:
            raise FileNotFoundError(f"No CSV files matched glob pattern: {raw_str!r}")
        return matches

    if not candidate.exists():
        raise FileNotFoundError(f"CSV file not found: {candidate}")
    return [candidate]


def _parse_single_sqp_csv(
    path: Path,
    default_asin: Optional[str] = None,
    default_week_start: Optional[date] = None,
) -> list[SQPRecord]:
    """Parse a single Seller Central Brand Analytics SQP CSV file."""
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = [row for row in csv.reader(fh) if any(cell.strip() for cell in row)]

    if not rows:
        raise SchemaMismatchError(f"SQP CSV file is empty: {path}")

    banner_asin, banner_week = _extract_banner_metadata(rows[0])
    if banner_asin is not None or banner_week is not None or any("=" in c for c in rows[0]):
        if len(rows) < 2:
            raise SchemaMismatchError(
                f"SQP CSV contains Row 1 metadata banner but no Row 2 header: {path}"
            )
        header_row = rows[1]
        data_rows = rows[2:]
    else:
        header_row = rows[0]
        data_rows = rows[1:]

    col_idx = _resolve_header_indices(header_row)
    resolved_asin = banner_asin or default_asin or "UNKNOWN_ASIN"
    resolved_week = banner_week or default_week_start

    records: list[SQPRecord] = []
    for row in data_rows:
        if len(row) <= col_idx["search_query"]:
            continue
        raw_query = row[col_idx["search_query"]]
        query = normalize_query(raw_query)
        if not query:
            continue

        row_asin = resolved_asin
        if "asin" in col_idx and col_idx["asin"] < len(row) and row[col_idx["asin"]].strip():
            row_asin = row[col_idx["asin"]].strip().upper()

        row_week = resolved_week
        if (
            "week_start" in col_idx
            and col_idx["week_start"] < len(row)
            and row[col_idx["week_start"]].strip()
        ):
            row_week = parse_flexible_date(row[col_idx["week_start"]], align_week=True)

        if row_week is None:
            raise SchemaMismatchError(
                "Could not determine SQP week_start from Row 1 metadata banner, "
                "inline week column, or default_week_start parameter."
            )

        def _get_int(field: str) -> int:
            idx = col_idx.get(field)
            if idx is None or idx >= len(row):
                return 0
            return max(0, parse_localized_int(row[idx]))

        records.append(
            SQPRecord(
                asin=row_asin,
                week_start=row_week,
                search_query=query,
                sqp_score=_get_int("sqp_score"),
                search_volume=_get_int("search_volume"),
                total_impressions=_get_int("total_impressions"),
                entity_impressions=_get_int("entity_impressions"),
                total_clicks=_get_int("total_clicks"),
                entity_clicks=_get_int("entity_clicks"),
                total_cart_adds=_get_int("total_cart_adds"),
                entity_cart_adds=_get_int("entity_cart_adds"),
                total_purchases=_get_int("total_purchases"),
                entity_purchases=_get_int("entity_purchases"),
            )
        )

    return records


def parse_sqp_csv(
    csv_path: Union[str, Path, Iterable[Union[str, Path]]],
    default_asin: Optional[str] = None,
    default_week_start: Optional[date] = None,
) -> list[SQPRecord]:
    """
    Parse one or more Amazon Seller Central Brand Analytics Search Query Performance CSVs.

    Accepts a single CSV path, a directory of weekly SQP exports (each with its own Row 1
    `Select Week=["..."]` metadata banner), a glob pattern (`./exports/sqp_*.csv`), or
    comma-separated paths, and deduplicates by `(asin, search_query, week_start)`.
    """
    paths = resolve_csv_paths(csv_path)
    if len(paths) == 1:
        return _parse_single_sqp_csv(
            paths[0], default_asin=default_asin, default_week_start=default_week_start
        )

    by_key: dict[tuple[str, str, date], SQPRecord] = {}
    for p in paths:
        for rec in _parse_single_sqp_csv(
            p, default_asin=default_asin, default_week_start=default_week_start
        ):
            by_key[(rec.asin, rec.search_query, rec.week_start)] = rec

    return sorted(
        by_key.values(),
        key=lambda r: (r.asin, r.week_start, r.sqp_score, r.search_query),
    )

