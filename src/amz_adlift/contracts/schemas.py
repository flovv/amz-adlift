"""Pydantic v2 input/output data models for amz-adlift."""

from datetime import date
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

QuadrantLabel = Literal[
    "CANNIBALIZED_RENT",
    "FLYWHEEL_LEVERAGE",
    "TREADMILL_DEAD_WEIGHT",
    "AT_RISK_DECAY",
    "INSUFFICIENT_DATA",
]


class SQPRecord(BaseModel):
    """Normalized Brand Analytics Search Query Performance row."""

    asin: str
    week_start: date
    search_query: str
    sqp_score: int = Field(default=0, ge=0)
    search_volume: int = Field(ge=0)
    total_impressions: int = Field(ge=0)
    entity_impressions: int = Field(ge=0)
    total_clicks: int = Field(ge=0)
    entity_clicks: int = Field(ge=0)
    total_cart_adds: int = Field(ge=0)
    entity_cart_adds: int = Field(ge=0)
    total_purchases: int = Field(ge=0)
    entity_purchases: int = Field(ge=0)


class AdsRecord(BaseModel):
    """Normalized Amazon Ads Search Term weekly aggregated row."""

    asin: str
    week_start: date
    search_query: str
    campaign_name: str = ""
    ad_group_name: str = ""
    match_type: str = ""
    ad_impressions: int = Field(ge=0)
    ad_clicks: int = Field(ge=0)
    ad_spend: float = Field(ge=0.0)
    ad_sales: float = Field(ge=0.0)
    ad_orders: int = Field(ge=0)


class RankRecord(BaseModel):
    """Normalized weekly median Organic & Sponsored Keyword Rank row."""

    asin: str
    week_start: date
    search_query: str
    organic_rank: float = Field(ge=1.0, le=305.0)
    sponsored_rank: Optional[float] = Field(default=None, ge=1.0)


class UnifiedKeywordWeek(BaseModel):
    """Aligned weekly observation joining SQP, Ads, and Organic Rank metrics."""

    asin: str
    search_query: str
    week_start: date
    search_volume: int = Field(ge=0)
    # SQP Combined Totals (Organic + Sponsored Products on SERP)
    sqp_impressions: int = Field(ge=0)
    sqp_clicks: int = Field(ge=0)
    sqp_cart_adds: int = Field(ge=0)
    sqp_purchases: int = Field(ge=0)
    # Market-level SQP clicks/purchases for brand share computation
    total_market_clicks: int = Field(default=0, ge=0)
    total_market_purchases: int = Field(default=0, ge=0)
    # Paid Search Term Metrics
    ad_impressions: int = Field(ge=0)
    ad_clicks: int = Field(ge=0)
    ad_spend: float = Field(ge=0.0)
    ad_orders: int = Field(ge=0)
    ad_sales: float = Field(ge=0.0)
    # Isolated Pure Organic Metrics (Computed)
    organic_clicks: int = Field(ge=0)
    organic_orders: int = Field(ge=0)
    attribution_window_gap: bool = False
    # SERP Rank Position
    organic_rank: Optional[float] = Field(default=None, ge=1.0)
    sponsored_rank: Optional[float] = Field(default=None, ge=1.0)
    rank_is_sqp_proxy: bool = False
    # Optional AMC Clean Room Metrics (New-to-Brand & Cross-ASIN Halo)
    amc_ntb_orders: Optional[int] = Field(default=None, ge=0)
    amc_ntb_share: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    amc_brand_halo_orders: Optional[int] = Field(default=None, ge=0)
    amc_reached_users: Optional[int] = Field(default=None, ge=0)
    # Optional campaign context for bulk operations export
    campaign_name: str = ""
    ad_group_name: str = ""
    match_type: str = ""

    @property
    def true_paid_share_of_orders(self) -> float:
        """True paid share of total brand orders on this keyword-week."""
        denom = max(1, self.ad_orders + self.organic_orders)
        return min(1.0, float(self.ad_orders) / float(denom))


class KeywordQuadrantDiagnostic(BaseModel):
    """4-Quadrant diagnostic classification and supporting econometric metrics for a keyword."""

    asin: str
    search_query: str
    weeks_observed: int
    quadrant: QuadrantLabel
    median_organic_rank_4w: Optional[float] = None
    organic_cvr_4w: float = 0.0
    sqp_cvr_4w: float = 0.0
    weekly_ad_spend_avg: float = 0.0
    cumulative_ad_spend_4w: float = 0.0
    rank_velocity_slope: Optional[float] = None
    lagged_paid_to_organic_corr: Optional[float] = None
    brand_click_share_slope: float = 0.0
    true_paid_order_share: float = 0.0
    amc_ntb_share_4w: Optional[float] = None
    red_team_flags: list[str] = Field(default_factory=list)
    diagnostic_summary: str = ""
    pro_metrics: Optional[dict[str, Any]] = None


class AuditReport(BaseModel):
    """Complete output of a local Amazon Paid-to-Organic Flywheel audit."""

    asin: str
    category: str
    product_margin: float
    pro_enabled: bool
    total_keywords: int
    total_weeks: int
    quadrant_counts: dict[str, int]
    red_team_warnings: list[str] = Field(default_factory=list)
    keywords: list[KeywordQuadrantDiagnostic]
    panel: list[UnifiedKeywordWeek]
