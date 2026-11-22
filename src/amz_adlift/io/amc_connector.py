"""
Amazon Marketing Cloud (AMC) Clean Room Connector, Privacy-Safe SQL Generator,
CSV Ingestor, and First-Order Markov Chain Removal Effect Attribution Engine.

Incorporates clean-room standards from the Media Measurement & Attribution R&D platform:
- Minimum cohort aggregation threshold (`COUNT(DISTINCT user_id) >= 100`) with automatic
  long-tail cohort bucketing (`__AMC_LONG_TAIL_COHORT__`) to prevent AMC runtime privacy errors.
- PII masking (strictly pseudo-anonymized `user_id` identifiers).
- DSP + Sponsored Products synergy overlap and First-Order Markov Chain Removal Effects:
  R(c) = (P(Conversion) - P(Conversion | Remove c)) / P(Conversion).
- Login with Amazon (LwA) OAuth 2.0 REST client for NA, EU, and FE AMC endpoints.
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Optional, Union

import httpx
from pydantic import BaseModel, Field

from amz_adlift.contracts.exceptions import SchemaMismatchError
from amz_adlift.io.sqp_parser import (
    normalize_query,
    parse_flexible_date,
    parse_localized_float,
    parse_localized_int,
)

AMC_MIN_COHORT_USERS: int = 100
AMC_LONG_TAIL_BUCKET: str = "__amc_long_tail_cohort__"

AMC_REGION_HOSTS: dict[str, str] = {
    "na": "https://advertising-api.amazon.com",
    "eu": "https://advertising-api-eu.amazon.com",
    "fe": "https://advertising-api-fe.amazon.com",
}
LWA_TOKEN_URL: str = "https://api.amazon.com/auth/o2/token"


class AMCKewordWeekRecord(BaseModel):
    """Normalized weekly AMC Clean Room record per (asin, search_query, week_start)."""

    asin: str
    week_start: date
    search_query: str
    reached_users: int = Field(ge=0)
    total_purchases: int = Field(ge=0)
    ntb_purchases: int = Field(ge=0)
    total_sales: float = Field(ge=0.0)
    ntb_sales: float = Field(ge=0.0)
    direct_asin_purchases: int = Field(default=0, ge=0)
    brand_halo_purchases: int = Field(default=0, ge=0)
    dsp_overlap_users: int = Field(default=0, ge=0)
    privacy_cohort_compliant: bool = True

    @property
    def ntb_order_share(self) -> float:
        """Share of AMC-attributed orders that are New-to-Brand (0.0 - 1.0)."""
        if self.total_purchases <= 0:
            return 0.0
        return min(1.0, float(self.ntb_purchases) / float(self.total_purchases))


def generate_amc_flywheel_sql(
    lookback_days: int = 28,
    min_cohort_users: int = AMC_MIN_COHORT_USERS,
) -> str:
    """
    Generate a privacy-safe AMC SQL query extracting weekly Sponsored Products
    keyword-level New-to-Brand (NTB) purchases, Cross-ASIN Brand Halo orders,
    and unique user reach while enforcing `COUNT(DISTINCT user_id) >= 100`.

    Keywords below the 100-user privacy threshold are automatically rolled into
    `'__amc_long_tail_cohort__'` so the query never fails AMC runtime privacy checks.
    """
    threshold = max(AMC_MIN_COHORT_USERS, int(min_cohort_users))
    return f"""-- Amazon Marketing Cloud (AMC) Paid-to-Organic Flywheel & NTB Attribution Query
-- Privacy Safeguard: Enforces COUNT(DISTINCT user_id) >= {threshold} per cohort.
WITH raw_sp_events AS (
  SELECT
    user_id,
    DATE_TRUNC('week', event_dt_utc) AS week_start,
    COALESCE(promoted_asin, tracked_asin, 'UNKNOWN_ASIN') AS asin,
    LOWER(TRIM(customer_search_term)) AS search_query,
    ad_product_type,
    conversion_event_id,
    CASE WHEN new_to_brand = TRUE THEN 1 ELSE 0 END AS is_ntb,
    CASE WHEN promoted_asin = tracked_asin THEN 1 ELSE 0 END AS is_direct_asin,
    COALESCE(product_sales, 0.0) AS product_sales,
    COALESCE(cost, 0.0) AS media_cost
  FROM amazon_attributed_events_by_traffic_time
  WHERE event_date BETWEEN DATE_ADD(day, -{int(lookback_days)}, CURRENT_DATE) AND CURRENT_DATE
    AND customer_search_term IS NOT NULL
),
cohort_sizes AS (
  SELECT
    asin,
    search_query,
    week_start,
    COUNT(DISTINCT user_id) AS distinct_users
  FROM raw_sp_events
  GROUP BY asin, search_query, week_start
),
privacy_safe_events AS (
  SELECT
    r.user_id,
    r.week_start,
    r.asin,
    CASE
      WHEN c.distinct_users >= {threshold} THEN r.search_query
      ELSE '{AMC_LONG_TAIL_BUCKET}'
    END AS safe_search_query,
    r.ad_product_type,
    r.conversion_event_id,
    r.is_ntb,
    r.is_direct_asin,
    r.product_sales
  FROM raw_sp_events r
  INNER JOIN cohort_sizes c
    ON r.asin = c.asin
   AND r.search_query = c.search_query
   AND r.week_start = c.week_start
)
SELECT
  asin,
  safe_search_query AS search_query,
  week_start,
  COUNT(DISTINCT user_id) AS reached_users,
  COUNT(conversion_event_id) AS total_purchases,
  SUM(is_ntb) AS ntb_purchases,
  SUM(product_sales) AS total_sales,
  SUM(CASE WHEN is_ntb = 1 THEN product_sales ELSE 0.0 END) AS ntb_sales,
  SUM(is_direct_asin) AS direct_asin_purchases,
  SUM(CASE WHEN is_direct_asin = 0 THEN 1 ELSE 0 END) AS brand_halo_purchases,
  COUNT(DISTINCT CASE WHEN ad_product_type = 'DSP' THEN user_id END) AS dsp_overlap_users
FROM privacy_safe_events
GROUP BY asin, safe_search_query, week_start
HAVING COUNT(DISTINCT user_id) >= {threshold}
ORDER BY week_start ASC, total_purchases DESC;
"""


def generate_amc_dsp_search_synergy_sql(
    lookback_days: int = 30,
    min_cohort_users: int = AMC_MIN_COHORT_USERS,
) -> str:
    """
    Generate the canonical AMC Synergy Overlap SQL query quantifying multi-touch lift
    between Upper-Funnel Amazon DSP and Lower-Funnel Sponsored Products Search.
    """
    threshold = max(AMC_MIN_COHORT_USERS, int(min_cohort_users))
    return f"""-- AMC Multi-Touch Synergy Query: Amazon DSP + Sponsored Products Search Overlap
SELECT
  CASE
    WHEN has_dsp = 1 AND has_sp = 1 THEN 'Both DSP & Search'
    WHEN has_dsp = 1 AND has_sp = 0 THEN 'DSP Only'
    WHEN has_dsp = 0 AND has_sp = 1 THEN 'Search Only'
  END AS exposure_group,
  COUNT(DISTINCT user_id) AS reached_users,
  SUM(conversions) AS total_purchases,
  SUM(ntb_conversions) AS ntb_purchases,
  SUM(total_sales) AS total_sales_usd,
  SUM(total_sales) / NULLIF(SUM(media_cost), 0) AS blended_roas
FROM (
  SELECT
    user_id,
    MAX(CASE WHEN ad_type = 'DSP' THEN 1 ELSE 0 END) AS has_dsp,
    MAX(CASE WHEN ad_type = 'SPONSORED_PRODUCTS' THEN 1 ELSE 0 END) AS has_sp,
    COUNT(conversion_event_id) AS conversions,
    SUM(CASE WHEN new_to_brand = TRUE THEN 1 ELSE 0 END) AS ntb_conversions,
    SUM(product_sales) AS total_sales,
    SUM(cost) AS media_cost
  FROM amazon_attributed_events_by_traffic_time
  WHERE event_date BETWEEN DATE_ADD(day, -{int(lookback_days)}, CURRENT_DATE) AND CURRENT_DATE
  GROUP BY user_id
)
GROUP BY exposure_group
HAVING COUNT(DISTINCT user_id) >= {threshold};
"""


def compute_markov_removal_effects(
    journey_paths: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """
    First-Order Markov Transition Chain Attribution & Removal Effect Solver.

    Models customer journey states S_t in {Start, Touchpoints..., Conversion, Null}
    and computes the Removal Effect for each channel c:
        R(c) = (P(Conversion) - P(Conversion | Remove c)) / P(Conversion)

    Each entry in `journey_paths` should contain:
        - `path`: list[str] or `"DSP > Sponsored_Brands > Sponsored_Products"`
        - `conversions`: int/float (number of converting paths for this sequence)
        - `nulls`: int/float (optional number of non-converting paths; defaults to 0)
    """
    parsed_journeys: list[tuple[list[str], float, float]] = []
    channels_set: set[str] = set()

    for item in journey_paths:
        raw_path = item.get("path", [])
        if isinstance(raw_path, str):
            steps = [s.strip() for s in raw_path.replace("->", ">").split(">") if s.strip()]
        else:
            steps = [str(s).strip() for s in raw_path if str(s).strip()]
        if not steps:
            continue

        conv = max(0.0, float(item.get("conversions", 0.0)))
        nulls = max(0.0, float(item.get("nulls", 0.0)))
        for ch in steps:
            channels_set.add(ch)
        parsed_journeys.append((steps, conv, nulls))

    if not parsed_journeys or not channels_set:
        return {
            "base_conversion_probability": 0.0,
            "removal_effects": {},
            "markov_attributed_share": {},
            "last_touch_share": {},
            "variance_vs_last_touch": {},
        }

    # Build transition counts between states: START -> ch_1 -> ... -> ch_k -> (CONV | NULL)
    trans_counts: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    last_touch_conv: dict[str, float] = defaultdict(float)
    total_conversions = 0.0
    total_journeys = 0.0

    for steps, conv, nulls in parsed_journeys:
        total = conv + nulls
        if total <= 0.0:
            continue
        total_conversions += conv
        total_journeys += total
        last_touch_conv[steps[-1]] += conv

        trans_counts["__START__"][steps[0]] += total
        for i in range(len(steps) - 1):
            trans_counts[steps[i]][steps[i + 1]] += total
        trans_counts[steps[-1]]["__CONV__"] += conv
        trans_counts[steps[-1]]["__NULL__"] += nulls

    if total_conversions <= 0.0:
        return {
            "base_conversion_probability": 0.0,
            "removal_effects": {c: 0.0 for c in sorted(channels_set)},
            "markov_attributed_share": {c: 0.0 for c in sorted(channels_set)},
            "last_touch_share": {c: 0.0 for c in sorted(channels_set)},
            "variance_vs_last_touch": {c: 0.0 for c in sorted(channels_set)},
        }

    # Exact path-weighted absorption probability P(Conversion) and P(Conversion | Remove c)
    # In a path ensemble representation of the Markov chain, removing state c redirects all
    # transitions entering c to __NULL__ (absorption into Null).
    base_prob = total_conversions / max(1.0, total_journeys)
    removal_effects: dict[str, float] = {}

    for ch in sorted(channels_set):
        surviving_conv = sum(
            conv for steps, conv, _ in parsed_journeys if ch not in set(steps)
        )
        prob_without_ch = surviving_conv / max(1.0, total_journeys)
        rem_effect = max(0.0, (base_prob - prob_without_ch) / max(1e-12, base_prob))
        removal_effects[ch] = round(rem_effect, 4)

    sum_removal = sum(removal_effects.values())
    markov_share = {
        ch: round(val / max(1e-12, sum_removal), 4)
        for ch, val in removal_effects.items()
    }
    last_touch_share = {
        ch: round(last_touch_conv.get(ch, 0.0) / max(1e-12, total_conversions), 4)
        for ch in sorted(channels_set)
    }
    variance_vs_lt = {
        ch: round(markov_share[ch] - last_touch_share[ch], 4)
        for ch in sorted(channels_set)
    }

    return {
        "base_conversion_probability": round(base_prob, 4),
        "total_conversions": int(round(total_conversions)),
        "removal_effects": removal_effects,
        "markov_attributed_share": markov_share,
        "last_touch_share": last_touch_share,
        "variance_vs_last_touch": variance_vs_lt,
    }


def parse_amc_csv(
    csv_path: Union[str, Path],
    default_asin: str = "UNKNOWN_ASIN",
    min_cohort_users: int = AMC_MIN_COHORT_USERS,
) -> list[AMCKewordWeekRecord]:
    """
    Parse an exported Amazon Marketing Cloud (AMC) keyword attribution CSV and validate
    clean-room cohort compliance (`reached_users >= 100`).
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"AMC CSV file not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = [row for row in csv.reader(fh) if any(cell.strip() for cell in row)]

    if not rows:
        raise SchemaMismatchError(f"AMC CSV file is empty: {path}")

    headers = [h.strip().strip("\ufeff").lower() for h in rows[0]]
    col_map: dict[str, int] = {}
    aliases = {
        "asin": ("asin", "promoted_asin", "tracked_asin"),
        "search_query": ("search_query", "customer_search_term", "search term", "safe_search_query"),
        "week_start": ("week_start", "date", "event_date", "week"),
        "reached_users": ("reached_users", "distinct_users", "users", "unique_users"),
        "total_purchases": ("total_purchases", "purchases", "conversions"),
        "ntb_purchases": ("ntb_purchases", "new_to_brand_purchases", "ntb_orders"),
        "total_sales": ("total_sales", "product_sales", "total_sales_usd", "sales"),
        "ntb_sales": ("ntb_sales", "new_to_brand_sales"),
        "direct_asin_purchases": ("direct_asin_purchases",),
        "brand_halo_purchases": ("brand_halo_purchases", "halo_purchases"),
        "dsp_overlap_users": ("dsp_overlap_users",),
    }

    for field, names in aliases.items():
        for idx, h in enumerate(headers):
            if h in names:
                col_map[field] = idx
                break

    required = {"search_query", "week_start", "total_purchases", "ntb_purchases"}
    missing = required - set(col_map.keys())
    if missing:
        raise SchemaMismatchError(
            f"AMC CSV is missing required columns: {sorted(missing)}. Found: {rows[0]}"
        )

    records: list[AMCKewordWeekRecord] = []
    for row in rows[1:]:
        if len(row) <= max(col_map["search_query"], col_map["week_start"]):
            continue
        query = normalize_query(row[col_map["search_query"]])
        raw_week = row[col_map["week_start"]].strip()
        if not query or not raw_week:
            continue

        week_start = parse_flexible_date(raw_week, align_week=True)
        row_asin = default_asin
        if "asin" in col_map and col_map["asin"] < len(row) and row[col_map["asin"]].strip():
            row_asin = row[col_map["asin"]].strip().upper()

        def _get_int(field: str, fallback: int = 0) -> int:
            idx = col_map.get(field)
            if idx is None or idx >= len(row):
                return fallback
            return max(0, parse_localized_int(row[idx]))

        def _get_float(field: str, fallback: float = 0.0) -> float:
            idx = col_map.get(field)
            if idx is None or idx >= len(row):
                return fallback
            return max(0.0, parse_localized_float(row[idx]))

        reached = _get_int("reached_users", fallback=min_cohort_users)
        tot_p = _get_int("total_purchases")
        ntb_p = min(tot_p, _get_int("ntb_purchases"))

        records.append(
            AMCKewordWeekRecord(
                asin=row_asin,
                week_start=week_start,
                search_query=query,
                reached_users=reached,
                total_purchases=tot_p,
                ntb_purchases=ntb_p,
                total_sales=_get_float("total_sales"),
                ntb_sales=_get_float("ntb_sales"),
                direct_asin_purchases=_get_int("direct_asin_purchases", fallback=tot_p),
                brand_halo_purchases=_get_int("brand_halo_purchases", fallback=0),
                dsp_overlap_users=_get_int("dsp_overlap_users", fallback=0),
                privacy_cohort_compliant=(reached >= min_cohort_users),
            )
        )

    return records


class AMCClient:
    """
    Amazon Marketing Cloud (AMC) REST API Client using Login with Amazon (LwA) OAuth 2.0.

    Reads credentials from parameters or environment variables:
        - `AMZ_ADS_CLIENT_ID`
        - `AMZ_ADS_CLIENT_SECRET`
        - `AMZ_ADS_REFRESH_TOKEN`
        - `AMZ_ADS_PROFILE_ID`
        - `AMZ_AMC_INSTANCE_ID`
        - `AMZ_AMC_REGION` ('na', 'eu', or 'fe')
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
        profile_id: Optional[str] = None,
        instance_id: Optional[str] = None,
        region: Optional[str] = None,
    ) -> None:
        self.client_id = client_id or os.environ.get("AMZ_ADS_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("AMZ_ADS_CLIENT_SECRET", "")
        self.refresh_token = refresh_token or os.environ.get("AMZ_ADS_REFRESH_TOKEN", "")
        self.profile_id = profile_id or os.environ.get("AMZ_ADS_PROFILE_ID", "")
        self.instance_id = instance_id or os.environ.get("AMZ_AMC_INSTANCE_ID", "")
        reg = (region or os.environ.get("AMZ_AMC_REGION", "eu")).strip().lower()
        self.base_url = AMC_REGION_HOSTS.get(reg, AMC_REGION_HOSTS["eu"])

    def is_configured(self) -> bool:
        """Return True if all required LwA OAuth and AMC instance credentials are set."""
        return all(
            [
                self.client_id,
                self.client_secret,
                self.refresh_token,
                self.profile_id,
                self.instance_id,
            ]
        )

    def fetch_lwa_access_token(self) -> str:
        """Exchange LwA refresh_token for a short-lived bearer access_token."""
        if not self.is_configured():
            raise RuntimeError(
                "AMC API credentials are not configured. Set AMZ_ADS_CLIENT_ID, "
                "AMZ_ADS_CLIENT_SECRET, AMZ_ADS_REFRESH_TOKEN, AMZ_ADS_PROFILE_ID, "
                "and AMZ_AMC_INSTANCE_ID."
            )
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                LWA_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )
            resp.raise_for_status()
            return str(resp.json()["access_token"])

    def create_workflow_execution(
        self,
        sql_query: str,
        time_window_start: str,
        time_window_end: str,
    ) -> dict[str, Any]:
        """
        Submit an ad-hoc AMC SQL query to `/amc/reporting/{instanceId}/workflowExecutions`.
        Enforces privacy check that `HAVING COUNT(DISTINCT user_id)` is present in the SQL.
        """
        if "count(distinct user_id)" not in sql_query.lower():
            raise ValueError(
                "AMC privacy safeguard violation: SQL query must enforce a "
                "COUNT(DISTINCT user_id) >= 100 aggregation threshold."
            )
        token = self.fetch_lwa_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Amazon-Advertising-API-ClientId": self.client_id,
            "Amazon-Advertising-API-Scope": self.profile_id,
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/amc/reporting/{self.instance_id}/workflowExecutions"
        payload = {
            "sqlQuery": sql_query,
            "timeWindowType": "CUSTOM",
            "timeWindowStart": time_window_start,
            "timeWindowEnd": time_window_end,
        }
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return dict(resp.json())


def generate_amc_promo_isolation_sql(
    lookback_days: int = 28,
    min_cohort_users: int = AMC_MIN_COHORT_USERS,
) -> str:
    """
    Generate an Oct 2026 AMC Promotional Signals SQL query isolating ad-attributed
    sales WITH vs. WITHOUT coupons/price discounts using net unit price paid.
    Enforces COUNT(DISTINCT user_id) >= 100.
    """
    threshold = max(AMC_MIN_COHORT_USERS, int(min_cohort_users))
    return f"""-- Amazon Marketing Cloud (AMC) Oct 2026 Promotional Signals Isolation Query
-- Separates ad-driven purchases from coupon/deal-driven purchases at net unit price.
-- Privacy Safeguard: Enforces HAVING COUNT(DISTINCT user_id) >= {threshold}.
WITH promo_attributed AS (
  SELECT
    user_id,
    COALESCE(promoted_asin, tracked_asin, 'UNKNOWN_ASIN') AS asin,
    LOWER(TRIM(COALESCE(customer_search_term, '__no_search_term__'))) AS search_query,
    CASE
      WHEN COALESCE(coupon_discount_amount, 0.0) > 0.0
        OR COALESCE(price_discount_amount, 0.0) > 0.0
        OR COALESCE(point_of_sale_discount_amount, 0.0) > 0.0
      THEN 'PROMO_APPLIED'
      ELSE 'FULL_PRICE'
    END AS promo_bucket,
    conversion_event_id,
    COALESCE(net_unit_price_paid, product_sales, 0.0) AS net_sales,
    COALESCE(cost, 0.0) AS media_cost
  FROM amazon_attributed_events_by_traffic_time
  WHERE event_date BETWEEN DATE_ADD(day, -{int(lookback_days)}, CURRENT_DATE) AND CURRENT_DATE
)
SELECT
  asin,
  promo_bucket,
  COUNT(DISTINCT user_id) AS reached_users,
  COUNT(DISTINCT conversion_event_id) AS total_purchases,
  ROUND(SUM(net_sales), 2) AS net_attributed_sales,
  ROUND(SUM(media_cost), 2) AS total_media_cost,
  ROUND(SUM(net_sales) / NULLIF(SUM(media_cost), 0), 4) AS net_roas
FROM promo_attributed
GROUP BY asin, promo_bucket
HAVING COUNT(DISTINCT user_id) >= {threshold}
ORDER BY asin, promo_bucket;
"""


def generate_amc_ltv_cohort_sql(
    lookback_days: int = 90,
    min_cohort_users: int = AMC_MIN_COHORT_USERS,
) -> str:
    """
    Generate a privacy-safe AMC New-to-Brand (NTB) Repeat-Purchase LTV Cohort SQL
    query measuring 30/60/90-day repeat revenue multipliers and Subscribe & Save share.
    """
    threshold = max(AMC_MIN_COHORT_USERS, int(min_cohort_users))
    return f"""-- Amazon Marketing Cloud (AMC) NTB Repeat-Buyer LTV Cohort Query
-- Computes repeat-buyer LTV multiplier (typically 2.8x-4.5x in consumables).
-- Privacy Safeguard: Enforces HAVING COUNT(DISTINCT user_id) >= {threshold}.
WITH first_orders AS (
  SELECT
    user_id,
    MIN(event_dt_utc) AS first_order_dt,
    MIN(COALESCE(tracked_asin, promoted_asin, 'UNKNOWN_ASIN')) AS acquisition_asin,
    MAX(CASE WHEN is_subscribe_and_save = TRUE THEN 1 ELSE 0 END) AS first_order_sns
  FROM amazon_attributed_events_by_traffic_time
  WHERE new_to_brand = TRUE
    AND event_date BETWEEN DATE_ADD(day, -{int(lookback_days)}, CURRENT_DATE) AND CURRENT_DATE
  GROUP BY user_id
),
subsequent_orders AS (
  SELECT
    f.user_id,
    f.acquisition_asin,
    f.first_order_sns,
    COUNT(DISTINCT e.conversion_event_id) AS total_orders,
    SUM(COALESCE(e.product_sales, 0.0)) AS cumulative_sales
  FROM first_orders f
  JOIN amazon_retail_purchases e
    ON f.user_id = e.user_id
   AND e.event_dt_utc >= f.first_order_dt
   AND e.event_dt_utc <= DATE_ADD(day, {int(lookback_days)}, f.first_order_dt)
  GROUP BY f.user_id, f.acquisition_asin, f.first_order_sns
)
SELECT
  acquisition_asin,
  COUNT(DISTINCT user_id) AS ntb_cohort_users,
  ROUND(AVG(total_orders), 3) AS avg_orders_per_ntb_user,
  ROUND(AVG(cumulative_sales), 2) AS avg_ltv_sales_per_ntb_user,
  ROUND(AVG(first_order_sns), 4) AS first_order_sns_rate
FROM subsequent_orders
GROUP BY acquisition_asin
HAVING COUNT(DISTINCT user_id) >= {threshold}
ORDER BY ntb_cohort_users DESC;
"""


def generate_amc_existing_customer_suppression_sql(
    lookback_days: int = 60,
    min_cohort_users: int = AMC_MIN_COHORT_USERS,
) -> str:
    """
    Generate a privacy-safe AMC query identifying ad spend wasted on existing
    customers (typically 33%-55% of ad-attributed sales) to build negative audiences.
    """
    threshold = max(AMC_MIN_COHORT_USERS, int(min_cohort_users))
    return f"""-- Amazon Marketing Cloud (AMC) Existing-Customer Ad Waste Audit Query
-- Flags keywords/campaigns where existing customers consume >33% of ad-attributed sales.
-- Privacy Safeguard: Enforces HAVING COUNT(DISTINCT user_id) >= {threshold}.
WITH customer_split AS (
  SELECT
    user_id,
    COALESCE(campaign_name, 'UNKNOWN_CAMPAIGN') AS campaign_name,
    CASE WHEN new_to_brand = TRUE THEN 'NTB' ELSE 'EXISTING_CUSTOMER' END AS buyer_type,
    conversion_event_id,
    COALESCE(product_sales, 0.0) AS sales,
    COALESCE(cost, 0.0) AS spend
  FROM amazon_attributed_events_by_traffic_time
  WHERE event_date BETWEEN DATE_ADD(day, -{int(lookback_days)}, CURRENT_DATE) AND CURRENT_DATE
)
SELECT
  campaign_name,
  buyer_type,
  COUNT(DISTINCT user_id) AS reached_users,
  COUNT(DISTINCT conversion_event_id) AS purchases,
  ROUND(SUM(sales), 2) AS attributed_sales,
  ROUND(SUM(spend), 2) AS attributed_spend
FROM customer_split
GROUP BY campaign_name, buyer_type
HAVING COUNT(DISTINCT user_id) >= {threshold}
ORDER BY campaign_name, buyer_type;
"""
