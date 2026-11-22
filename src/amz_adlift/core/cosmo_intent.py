"""
2026 Amazon Listing Taxonomy Linter & COSMO Semantic Intent Cluster Auditor
(core/cosmo_intent.py).

Enforces post-July 2026 listing rules:
  - Title strictly <= 75 characters (flags AI auto-rewrite risk)
  - Item Highlights <= 125 characters, factual attributes only (no subjective fluff
    or redundant title keyword duplication)
  - Backend keywords deprecated -> flags orphaned backend-only terms
  - COSMO intent relation coverage (`used_for_audience`, `used_for_function`,
    `used_for_event`, `capable_of`) cross-referenced against SQP demand.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable, Optional, Sequence

from pydantic import BaseModel, Field

from amz_adlift.contracts.schemas import KeywordQuadrantDiagnostic, UnifiedKeywordWeek
from amz_adlift.core.quadrants import classify_panel

TITLE_MAX_CHARS_2026: int = 75
ITEM_HIGHLIGHTS_MAX_CHARS_2026: int = 125

SUBJECTIVE_BANNED_PHRASES: tuple[str, ...] = (
    "best",
    "#1",
    "number one",
    "top rated",
    "top-rated",
    "guaranteed",
    "cheapest",
    "amazing",
    "perfect",
    "miracle",
    "ultimate",
)

COSMO_RELATION_CUES: dict[str, tuple[str, ...]] = {
    "used_for_audience": (
        "for women",
        "for men",
        "for kids",
        "for adults",
        "for seniors",
        "for dogs",
        "for cats",
        "pregnant",
        "athletes",
        "beginners",
        "students",
        "runners",
    ),
    "used_for_function": (
        "sleep",
        "relief",
        "support",
        "recovery",
        "hydration",
        "storage",
        "cleaning",
        "charging",
        "protection",
        "insulation",
        "waterproof",
        "non-slip",
        "slip-resistant",
    ),
    "used_for_event": (
        "travel",
        "camping",
        "gift",
        "wedding",
        "gym",
        "workout",
        "office",
        "flight",
        "hiking",
        "christmas",
        "holiday",
    ),
    "capable_of": (
        "fast",
        "wireless",
        "rechargeable",
        "washable",
        "foldable",
        "sugar-free",
        "sugar free",
        "melatonin-free",
        "melatonin free",
        "organic",
        "vegan",
        "gluten-free",
    ),
}

_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "your", "our", "are", "into",
}


class ListingAudit2026Result(BaseModel):
    """Structured compliance & COSMO semantic gap report for an Amazon listing."""

    title_length: int
    title_compliant: bool
    item_highlights_length: int
    item_highlights_compliant: bool
    subjective_claims_found: list[str] = Field(default_factory=list)
    redundant_highlight_tokens: list[str] = Field(default_factory=list)
    orphaned_backend_keywords: list[str] = Field(default_factory=list)
    detected_cosmo_relations: dict[str, list[str]] = Field(default_factory=dict)
    missing_sqp_intent_terms: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


def _tokenize(text: str) -> set[str]:
    return {
        tok
        for tok in re.findall(r"[a-z0-9]+", text.lower())
        if len(tok) >= 3 and tok not in _STOPWORDS
    }


def audit_listing_2026(
    *,
    title: str,
    item_highlights: str = "",
    bullets: Optional[Sequence[str]] = None,
    a_plus_text: str = "",
    legacy_backend_keywords: str = "",
    sqp_queries: Optional[Sequence[str]] = None,
) -> ListingAudit2026Result:
    """Audit listing copy against July 2026 Amazon taxonomy rules and COSMO intent."""
    flags: list[str] = []
    recs: list[str] = []

    t_len = len(title.strip())
    h_len = len(item_highlights.strip())
    t_ok = t_len <= TITLE_MAX_CHARS_2026
    h_ok = h_len <= ITEM_HIGHLIGHTS_MAX_CHARS_2026

    if not t_ok:
        flags.append("TITLE_EXCEEDS_75_CHAR_AUTO_REWRITE_RISK")
        recs.append(
            f"Trim title from {t_len} to <= {TITLE_MAX_CHARS_2026} chars (Brand + Core Entity + "
            "Primary Variation) to prevent Amazon AI auto-rewrite."
        )
    if not h_ok:
        flags.append("ITEM_HIGHLIGHTS_EXCEEDS_125_CHAR")
        recs.append(
            f"Trim Item Highlights from {h_len} to <= {ITEM_HIGHLIGHTS_MAX_CHARS_2026} chars."
        )
    if h_len == 0:
        flags.append("ITEM_HIGHLIGHTS_MISSING")
        recs.append(
            "Populate the 125-char Item Highlights field with factual attributes "
            "(materials, compatibility, use-case) to feed COSMO."
        )

    highlights_lower = item_highlights.lower()
    subjective = [p for p in SUBJECTIVE_BANNED_PHRASES if p in highlights_lower]
    if subjective:
        flags.append("SUBJECTIVE_CLAIMS_IN_ITEM_HIGHLIGHTS")
        recs.append(
            f"Remove subjective phrases ({', '.join(subjective)}) from Item Highlights; "
            "use objective attributes only."
        )

    title_tokens = _tokenize(title)
    highlight_tokens = _tokenize(item_highlights)
    redundant = sorted(title_tokens & highlight_tokens)
    if redundant:
        flags.append("REDUNDANT_TITLE_KEYWORDS_IN_HIGHLIGHTS")
        recs.append(
            f"Remove duplicated title terms ({', '.join(redundant[:6])}) from Item Highlights "
            "to maximize semantic density."
        )

    visible_corpus = " ".join(
        [title, item_highlights, " ".join(bullets or []), a_plus_text]
    ).lower()
    visible_tokens = _tokenize(visible_corpus)

    orphaned: list[str] = []
    if legacy_backend_keywords.strip():
        backend_tokens = _tokenize(legacy_backend_keywords)
        orphaned = sorted(backend_tokens - visible_tokens)
        if orphaned:
            flags.append("ORPHANED_DEPRECATED_BACKEND_KEYWORDS")
            recs.append(
                f"Backend search terms are deprecated; migrate high-value terms "
                f"({', '.join(orphaned[:8])}) into Item Highlights or indexed A+ Content."
            )

    detected_relations: dict[str, list[str]] = {}
    for rel, cues in COSMO_RELATION_CUES.items():
        hits = [cue for cue in cues if cue in visible_corpus]
        if hits:
            detected_relations[rel] = hits

    missing_sqp: list[str] = []
    if sqp_queries:
        for q in sqp_queries:
            q_tokens = _tokenize(q)
            if q_tokens and not (q_tokens & visible_tokens):
                missing_sqp.append(q)
        if missing_sqp:
            flags.append("SQP_COSMO_INTENT_GAP")
            recs.append(
                f"SQP queries with zero visible attribute coverage ({', '.join(missing_sqp[:5])}); "
                "add their underlying function/audience attributes to Item Highlights or A+ text."
            )

    return ListingAudit2026Result(
        title_length=t_len,
        title_compliant=t_ok,
        item_highlights_length=h_len,
        item_highlights_compliant=h_ok,
        subjective_claims_found=subjective,
        redundant_highlight_tokens=redundant,
        orphaned_backend_keywords=orphaned,
        detected_cosmo_relations=detected_relations,
        missing_sqp_intent_terms=missing_sqp,
        flags=flags,
        recommendations=recs,
    )


def infer_cosmo_intent_cluster(search_query: str) -> str:
    """Assign a search query to a coarse COSMO intent relation bucket."""
    q = search_query.lower()
    for rel, cues in COSMO_RELATION_CUES.items():
        for cue in cues:
            if cue in q:
                return f"{rel}:{cue.replace(' ', '_')}"
    return "core_entity:general"


def cluster_panel_by_cosmo_intent(
    panel: Iterable[UnifiedKeywordWeek],
    *,
    category: str = "general",
    custom_clusters: Optional[dict[str, str]] = None,
) -> list[KeywordQuadrantDiagnostic]:
    """
    Aggregate sparse keyword-week observations into COSMO intent clusters and
    classify each cluster using the 4-quadrant diagnostic engine.
    """
    grouped: dict[tuple[str, str, str], list[UnifiedKeywordWeek]] = defaultdict(list)
    custom = {k.lower(): v for k, v in (custom_clusters or {}).items()}

    for row in panel:
        cluster = custom.get(row.search_query.lower()) or infer_cosmo_intent_cluster(
            row.search_query
        )
        grouped[(row.asin, cluster, row.week_start.isoformat())].append(row)

    cluster_series: dict[tuple[str, str], list[UnifiedKeywordWeek]] = defaultdict(list)
    for (asin, cluster, _week_iso), rows in grouped.items():
        ranks = [r.organic_rank for r in rows if r.organic_rank is not None]
        agg = UnifiedKeywordWeek(
            asin=asin,
            search_query=cluster,
            week_start=rows[0].week_start,
            search_volume=sum(r.search_volume for r in rows),
            sqp_impressions=sum(r.sqp_impressions for r in rows),
            sqp_clicks=sum(r.sqp_clicks for r in rows),
            sqp_cart_adds=sum(r.sqp_cart_adds for r in rows),
            sqp_purchases=sum(r.sqp_purchases for r in rows),
            total_market_clicks=sum(r.total_market_clicks for r in rows),
            total_market_purchases=sum(r.total_market_purchases for r in rows),
            ad_impressions=sum(r.ad_impressions for r in rows),
            ad_clicks=sum(r.ad_clicks for r in rows),
            ad_spend=round(sum(r.ad_spend for r in rows), 2),
            ad_orders=sum(r.ad_orders for r in rows),
            ad_sales=round(sum(r.ad_sales for r in rows), 2),
            organic_clicks=sum(r.organic_clicks for r in rows),
            organic_orders=sum(r.organic_orders for r in rows),
            organic_rank=min(ranks) if ranks else None,
        )
        cluster_series[(asin, cluster)].append(agg)

    aggregated_rows: list[UnifiedKeywordWeek] = []
    for (_asin, _cluster), series in sorted(cluster_series.items()):
        aggregated_rows.extend(series)
    return classify_panel(aggregated_rows, category=category, strict=False)
