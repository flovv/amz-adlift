"""
Seller Central Business Report (Detail Page Sales and Traffic) CSV Parser
(io/business_report_parser.py).

Extracts Featured Offer (Buy Box) %, Sessions, Unit Session % (CVR), Units Ordered,
and Ordered Product Sales per ASIN (handling US/UK and EU/DE number formats).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Union

from pydantic import BaseModel, Field

from amz_adlift.contracts.exceptions import SchemaMismatchError
from amz_adlift.io.sqp_parser import parse_localized_float, parse_localized_int


class BusinessReportRecord(BaseModel):
    """Normalized Seller Central Detail Page Sales & Traffic record per ASIN."""

    asin: str
    sessions: int = Field(ge=0)
    buy_box_pct: float = Field(ge=0.0, le=100.0)
    unit_session_pct: float = Field(ge=0.0, le=100.0)
    units_ordered: int = Field(ge=0)
    ordered_product_sales: float = Field(ge=0.0)


def _find_col(headers: list[str], candidates: tuple[str, ...]) -> int:
    lower = [h.strip().lower() for h in headers]
    for cand in candidates:
        for idx, h in enumerate(lower):
            if cand == h or cand in h:
                return idx
    return -1


def parse_business_report_csv(path: Union[str, Path]) -> list[BusinessReportRecord]:
    """Parse a Seller Central Detail Page Sales and Traffic Business Report CSV."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Business Report CSV not found: {file_path}")

    with file_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        headers = next(reader, None)
        if not headers:
            raise SchemaMismatchError(f"Business Report CSV is empty: {file_path}")

        asin_idx = _find_col(headers, ("(child) asin", "child asin", "asin"))
        bb_idx = _find_col(
            headers,
            (
                "featured offer (buy box) percentage",
                "buy box percentage",
                "featured offer percentage",
                "einkaufswagenfeld",
            ),
        )
        sess_idx = _find_col(headers, ("sessions - total", "sessions", "sitzungen"))
        cvr_idx = _find_col(
            headers,
            ("unit session percentage", "einheiten-sitzungsprozentsatz", "cvr"),
        )
        units_idx = _find_col(headers, ("units ordered", "bestellte einheiten"))
        sales_idx = _find_col(
            headers, ("ordered product sales", "umsatz durch bestellte produkte")
        )

        if asin_idx < 0 or bb_idx < 0:
            raise SchemaMismatchError(
                f"Business Report CSV missing ASIN or Featured Offer (Buy Box) % column: {headers}"
            )

        records: list[BusinessReportRecord] = []
        for row in reader:
            if not row or len(row) <= max(asin_idx, bb_idx):
                continue
            asin = row[asin_idx].strip()
            if not asin:
                continue
            bb = parse_localized_float(row[bb_idx].replace("%", ""))
            sess = parse_localized_int(row[sess_idx]) if sess_idx >= 0 and sess_idx < len(row) else 0
            cvr = (
                parse_localized_float(row[cvr_idx].replace("%", ""))
                if cvr_idx >= 0 and cvr_idx < len(row)
                else 0.0
            )
            units = (
                parse_localized_int(row[units_idx])
                if units_idx >= 0 and units_idx < len(row)
                else 0
            )
            sales = (
                parse_localized_float(row[sales_idx])
                if sales_idx >= 0 and sales_idx < len(row)
                else 0.0
            )
            records.append(
                BusinessReportRecord(
                    asin=asin,
                    sessions=max(0, sess),
                    buy_box_pct=max(0.0, min(100.0, bb)),
                    unit_session_pct=max(0.0, min(100.0, cvr)),
                    units_ordered=max(0, units),
                    ordered_product_sales=max(0.0, sales),
                )
            )
        return records
