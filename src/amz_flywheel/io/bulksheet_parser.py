"""
Amazon Ads Sponsored Products Bulk Operations `.xlsx` Parser & ID Merger (io/bulksheet_parser.py).

Reads an exported Seller Central Bulk Operations `.xlsx` workbook to extract exact
numeric `Campaign ID`, `Ad Group ID`, `Keyword ID`, `State`, and current `Bid` values so
that generated bulk update files are 100% upload-ready for Amazon Ads Bulk Operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union

import openpyxl

from amz_flywheel.contracts.exceptions import SchemaMismatchError
from amz_flywheel.io.sqp_parser import normalize_query, parse_localized_float


@dataclass(frozen=True)
class BulkKeywordTarget:
    """Normalized Keyword row extracted from an Amazon Ads Bulk Operations `.xlsx` export."""

    campaign_id: str
    ad_group_id: str
    keyword_id: str
    campaign_name: str
    ad_group_name: str
    keyword_text: str
    match_type: str
    state: str
    bid: float


_BULK_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "product": ("product",),
    "entity": ("entity", "entität"),
    "campaign_id": ("campaign id", "kampagnen-id"),
    "ad_group_id": ("ad group id", "anzeigengruppen-id"),
    "keyword_id": ("keyword id", "keyword-id"),
    "campaign_name": (
        "campaign name",
        "campaign name (informational only)",
        "kampagnenname",
    ),
    "ad_group_name": (
        "ad group name",
        "ad group name (informational only)",
        "anzeigengruppenname",
    ),
    "keyword_text": ("keyword text", "keyword-text"),
    "match_type": ("match type", "übereinstimmungstyp"),
    "state": ("state", "status"),
    "bid": ("bid", "gebot"),
}


def _resolve_bulk_headers(headers: list[Any]) -> dict[str, int]:
    norm = [str(h or "").strip().strip("\ufeff").lower() for h in headers]
    mapping: dict[str, int] = {}
    for field_name, aliases in _BULK_COLUMN_ALIASES.items():
        for idx, h in enumerate(norm):
            if h in aliases:
                mapping[field_name] = idx
                break

    required = {"entity", "campaign_id", "ad_group_id", "keyword_id", "keyword_text", "bid"}
    missing = required - set(mapping.keys())
    if missing:
        raise SchemaMismatchError(
            f"Amazon Ads Bulk Operations .xlsx is missing required columns: {sorted(missing)}. "
            f"Found headers: {[str(h) for h in headers[:18]]}"
        )
    return mapping


def parse_ads_bulksheet(xlsx_path: Union[str, Path]) -> list[BulkKeywordTarget]:
    """
    Parse an exported Amazon Ads Sponsored Products Bulk Operations `.xlsx` file
    and return all Keyword target rows with real Amazon numeric IDs and live bids.
    """
    path = Path(xlsx_path)
    if not path.exists():
        raise FileNotFoundError(f"Bulk Operations file not found: {path}")

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet_name = (
            "Sponsored Products Campaigns"
            if "Sponsored Products Campaigns" in wb.sheetnames
            else wb.sheetnames[0]
        )
        ws = wb[sheet_name]
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header_row = list(next(rows_iter))
        except StopIteration as exc:
            raise SchemaMismatchError(f"Bulk Operations workbook {path} is empty.") from exc

        col_map = _resolve_bulk_headers(header_row)
        targets: list[BulkKeywordTarget] = []

        for row in rows_iter:
            if not row or all(cell is None for cell in row):
                continue
            entity = str(row[col_map["entity"]] or "").strip().lower()
            if entity != "keyword":
                continue

            kw_raw = str(row[col_map["keyword_text"]] or "").strip()
            if not kw_raw:
                continue

            kw_id = str(row[col_map["keyword_id"]] or "").strip()
            cmp_id = str(row[col_map["campaign_id"]] or "").strip()
            ag_id = str(row[col_map["ad_group_id"]] or "").strip()
            if not (kw_id and cmp_id and ag_id):
                continue

            cmp_name = (
                str(row[col_map["campaign_name"]] or "").strip()
                if "campaign_name" in col_map
                else ""
            )
            ag_name = (
                str(row[col_map["ad_group_name"]] or "").strip()
                if "ad_group_name" in col_map
                else ""
            )
            match_type = (
                str(row[col_map["match_type"]] or "EXACT").strip().upper()
                if "match_type" in col_map
                else "EXACT"
            )
            state = (
                str(row[col_map["state"]] or "enabled").strip().lower()
                if "state" in col_map
                else "enabled"
            )
            bid_raw = row[col_map["bid"]]
            bid_val = parse_localized_float(str(bid_raw)) if bid_raw is not None else 0.0
            if bid_val <= 0.0:
                continue

            targets.append(
                BulkKeywordTarget(
                    campaign_id=cmp_id,
                    ad_group_id=ag_id,
                    keyword_id=kw_id,
                    campaign_name=cmp_name,
                    ad_group_name=ag_name,
                    keyword_text=normalize_query(kw_raw),
                    match_type=match_type,
                    state=state,
                    bid=bid_val,
                )
            )
    finally:
        wb.close()

    return targets


def merge_bulksheet_ids(
    keyword_rows: list[dict[str, Any]],
    bulksheet_targets: list[BulkKeywordTarget],
) -> list[dict[str, Any]]:
    """
    Join audited keyword bid rows against real Amazon Ads Bulk Operations targets.

    Matching precedence:
      1. (keyword_text, match_type, campaign_name)
      2. (keyword_text, match_type)
      3. (keyword_text)

    Matched rows receive exact Amazon numeric `campaign_id`, `ad_group_id`,
    `keyword_id`, real live `current_bid`, and `id_source = "amazon_bulksheet"`.
    """
    by_full: dict[tuple[str, str, str], BulkKeywordTarget] = {}
    by_kw_match: dict[tuple[str, str], BulkKeywordTarget] = {}
    by_kw: dict[str, BulkKeywordTarget] = {}

    for t in bulksheet_targets:
        by_full[(t.keyword_text, t.match_type.upper(), t.campaign_name.lower())] = t
        by_kw_match.setdefault((t.keyword_text, t.match_type.upper()), t)
        by_kw.setdefault(t.keyword_text, t)

    enriched: list[dict[str, Any]] = []
    for row in keyword_rows:
        norm_kw = normalize_query(str(row.get("search_query", "")))
        mt = str(row.get("match_type", "EXACT")).strip().upper()
        cname = str(row.get("campaign_name", "")).strip().lower()

        matched: Optional[BulkKeywordTarget] = (
            by_full.get((norm_kw, mt, cname))
            or by_kw_match.get((norm_kw, mt))
            or by_kw.get(norm_kw)
        )

        merged = dict(row)
        if matched is not None:
            merged["campaign_id"] = matched.campaign_id
            merged["ad_group_id"] = matched.ad_group_id
            merged["keyword_id"] = matched.keyword_id
            merged["campaign_name"] = matched.campaign_name or merged.get("campaign_name", "")
            merged["ad_group_name"] = matched.ad_group_name or merged.get("ad_group_name", "")
            merged["match_type"] = matched.match_type
            merged["state"] = matched.state
            merged["current_bid"] = matched.bid
            merged["id_source"] = "amazon_bulksheet"
        else:
            merged.setdefault("id_source", "synthetic_placeholder")

        enriched.append(merged)

    return enriched
