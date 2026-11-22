# amz-adlift

Local-first Python package, CLI, and MCP server that separates **true incremental Amazon PPC lift** from **organic cannibalization** using your exported Seller Central reports.

## What You Get

- **Stop paying ad rent on #1 organic keywords** — Isolates pure organic clicks and orders from combined Search Query Performance (SQP) data so you immediately see where Exact PPC is just cannibalizing clicks you already own.
- **Find keywords where PPC actually drives organic rank** — Classifies every `(asin, search_query)` pair into four clear buckets (`CANNIBALIZED_RENT`, `FLYWHEEL_LEVERAGE`, `TREADMILL_DEAD_WEIGHT`, `AT_RISK_DECAY`) instead of judging keywords on misleading Average ACoS alone.
- **Zero OAuth, 100% local privacy** — Drop in exported CSV/XLSX files from Seller Central, Amazon Ads, and your rank tracker. Your account data never leaves your machine and no SP-API / Ads API credentials are required.
- **Works with messy real-world Seller Central exports** — Auto-detects ASIN View and Brand View SQP banners, Legacy Sponsored Products reports, 2026 Unified Reporting, native `.xlsx` Search Term exports, and US/UK (`$`, `£`) or EU/DE (`€`, comma decimals) number formats.
- **Client-ready executive reports in one command** — Generates self-contained, print-to-PDF white-label HTML audit decks with interactive 4-quadrant charts for agencies and brand operators.
- **Built for AI agents out of the box** — Ships with a local FastMCP `stdio` server for Claude Desktop and Cursor, plus an installable [`skills.sh`](https://skills.sh) agent skill.
- **Optional Pro econometrics & bulk execution** — Pair with `amz_adlift_pro` to estimate keyword rank elasticities, simulate 21-day bid cuts, reallocate weekly PPC budgets via a KKT equimarginal solver, and export upload-ready Amazon Ads Bulk Operations `.xlsx` files with exact Amazon IDs and bid guardrails.

---

## Install

```bash
pip install amz-adlift
```

### Install as an Agent Skill (`skills.sh`)

```bash
npx skills add flovv/amz-adlift
```

Skill definition: [skills/amz-adlift/SKILL.md](skills/amz-adlift/SKILL.md)

---

## Quickstart (CLI)

```bash
# 1. Run a local Paid vs. Organic audit from exported CSV/XLSX files
amz-adlift audit \
  --sqp ./exports/US_Search_Query_Performance_ASIN.csv \
  --ads ./exports/Sponsored_Products_Search_Term_Report.csv \
  --rank ./exports/Helium10_Keyword_Tracker.csv \
  --category supplements \
  --margin 0.38 \
  --out ./reports/adlift_audit.json

# 2. Generate a white-label HTML/PDF executive audit report
amz-adlift report \
  --out ./reports/client_adlift_audit.html \
  --agency-name "Your Agency Name" \
  --client-name "Client Brand"

# 3. Generate privacy-safe Amazon Marketing Cloud (AMC) SQL queries
amz-adlift amc sql --days 28

# 4. Start the local FastMCP stdio server (Claude Desktop / Cursor)
amz-adlift mcp
```

### Pro Engine Commands (Optional)

```bash
# Activate a Polar.sh Pro license and install the matching platform wheel
amz-adlift auth install-pro --key "AMZ_AL_PRO_..."

# Reallocate weekly portfolio budget via KKT water-filling solver
amz-adlift allocate --budget 1100

# Export an upload-ready Amazon Ads Bulk Operations .xlsx with ID merge & guardrails
amz-adlift bulksheet \
  --existing-bulk ./exports/Amazon_Ads_Bulk_Operations.xlsx \
  --out ./reports/upload_ready_bulk_update.xlsx \
  --max-change 0.25 --min-bid 0.20 --max-bid 8.00
```

---

## MCP Setup (Claude Desktop & Cursor)

`amz-adlift-mcp` runs locally over `stdio`. Exported Seller Central files stay on your machine.

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "amz-adlift": {
      "command": "uvx",
      "args": ["--from", "amz-adlift", "amz-adlift-mcp"]
    }
  }
}
```

### Cursor (`.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "amz-adlift": {
      "command": "amz-adlift-mcp",
      "args": []
    }
  }
}
```

### Available MCP Tools, Resources & Prompts

| Type | Name / URI | Tier | Description |
| :--- | :--- | :--- | :--- |
| **Tool** | `audit_amazon_flywheel` | Open Core + Pro | Joins local SQP, Ads (CSV/XLSX), and Rank CSVs; isolates pure organic clicks/orders; classifies 4 quadrants; attaches Pro elasticity (`90% CI`, `R²`), Walk-Forward Backtest MAPE & Halo ACoS when licensed. |
| **Tool** | `generate_audit_report` | Open Core + Pro | Renders a self-contained, print-to-PDF white-label HTML audit deck with 4-quadrant scatter plot, marginal response curves, and reallocation table. |
| **Tool** | `analyze_amc_clean_room` | Open Core | Generates privacy-safe AMC SQL (`HAVING COUNT(DISTINCT user_id) >= 100`) and computes First-Order Markov Chain Removal Effects vs. Last-Touch variance. |
| **Tool** | `optimize_budget_allocation` | Pro | Fits Hill-saturated marginal response curves and runs a KKT water-filling solver to equalize marginal total ROAS across keywords. |
| **Tool** | `simulate_keyword_bid_cut` | Pro | Projects 21-day organic rank trajectory and SERP-incrementality-adjusted net profit impact under `-25%`, `-50%`, and `-100%` spend cuts. |
| **Tool** | `export_ads_bulksheet` | Pro | Merges exact `Campaign ID`, `Ad Group ID`, `Keyword ID`, and live bids from Seller Central Bulk `.xlsx` exports and writes an upload-ready `Operation = Update` sheet with bid guardrails. |
| **Tool** | `activate_amz_adlift_pro` | Pro | Validates a Polar.sh key (fail-closed in production), downloads the matching platform `.whl` with SHA-256 verification, and caches the license locally for 24h. |
| **Resource** | `flywheel://reference/quadrants` | Open Core | Machine-readable JSON of the 4 quadrants, thresholds, and bid playbooks. |
| **Resource** | `flywheel://reference/category-priors` | Open Core + Pro | Category elasticity priors (`general`, `supplements`, `electronics`, `home_kitchen`, `beauty`, `pet_supplies`, `apparel`). |
| **Prompt** | `executive_flywheel_audit` | Open Core + Pro | Structured multi-step prompt for running a paid-vs-organic audit with an LLM. |

---

## Python SDK

```python
from amz_adlift import ingest_and_align, classify_panel, enrich_with_pro_elasticity

# 1. Ingest and align Seller Central SQP, Ads, and Rank CSVs
panel = ingest_and_align(
    sqp_csv_path="tests/fixtures/sqp_multiweek.csv",
    ads_csv_path="tests/fixtures/ads_multiweek.csv",
    rank_csv_path="tests/fixtures/rank_multiweek.csv",
)

# 2. Classify keywords into the 4 diagnostic quadrants
diagnostics = classify_panel(panel, category="supplements", strict=True)
for diag in diagnostics:
    print(f"{diag.search_query:30s} -> {diag.quadrant:22s} | {diag.diagnostic_summary}")

# 3. Optional Pro elasticity & Halo Break-Even ACoS enrichment
pro_metrics = enrich_with_pro_elasticity(panel, category="supplements", product_margin=0.38)
```

---

## Supported Export Formats

All parsers normalize US/UK (`1,234.56`, `$`, `£`) and EU/DE (`1.234,56`, `€`) numbers and align dates to Amazon SQP weekly Sunday–Saturday buckets.

- **Brand Analytics SQP (`io/sqp_parser.py`)** — Handles Row 1 metadata banners (`ASIN=[...], Reporting Range=["Weekly"], Select Week=[...]`) and Row 2 headers for both **ASIN View** and **Brand View**.
- **Amazon Ads Search Term Reports (`io/ads_parser.py`)** — Supports `.csv` and `.xlsx` across Legacy Sponsored Products (`Customer Search Term`, `Spend`, `7 Day Total Sales`), 2026 Unified Reporting (`Search term`, `Total cost`, `Sales`, `Purchases`), and German/EU exports (`Suchbegriff`, `Ausgaben`, `7 Tage, Umsatz gesamt`).
- **Organic Keyword Rank Trackers (`io/rank_parser.py`)** — Accepts Helium 10 Keyword Tracker, DataDive, Perpetua, or generic CSVs (`Keyword`, `Date`, `Organic Rank`; `>300` / `unranked` capped at `305.0`).

---

## How the Math Works

### Pure Organic Funnel Isolation (`core/decomposition.py`)

Amazon SQP combines organic and Sponsored Products interactions in the same calendar week, while Ads reports use a 7-day post-click window:

- **Pure Organic Clicks:** $C^{\text{org}}_{k,t} = \max\left(0, C^{\text{SQP}}_{k,t} - C^{\text{ads}}_{k,t}\right)$
- **Pure Organic Orders:** $O^{\text{org}}_{k,t} = \max\left(0, O^{\text{SQP}}_{k,t} - O^{\text{ads}}_{k,t}\right)$
- **Attribution Window Gap Flag:** `attribution_window_gap = True` whenever $O^{\text{ads}}_{k,t} > O^{\text{SQP}}_{k,t}$.
- **True Paid Share of Brand Orders:** $\text{PaidShare}_{k,t} = \frac{O^{\text{ads}}_{k,t}}{\max\left(1, O^{\text{ads}}_{k,t} + O^{\text{org}}_{k,t}\right)}$

### 4-Quadrant Diagnostic Classifier (`core/quadrants.py`)

Requires $\ge 4$ aligned weeks per `(asin, search_query)`:

| Quadrant | Criteria | Recommended Bid Action |
| :--- | :--- | :--- |
| **`CANNIBALIZED_RENT`** | Trailing 4w median `organic_rank <= 2.5` **AND** pure organic CVR $\ge 12\%$ **AND** weekly `ad_spend >= $50` (or top 25% of account). | Cut Exact CPC bids by 15%–25%; you are paying ad rent on clicks you already capture organically. |
| **`FLYWHEEL_LEVERAGE`** | Trailing 4–8w OLS rank slope $\frac{\Delta R_k}{\Delta t} \le -0.5$ pos/wk (climbing toward #1) **AND** lagged paid-to-organic correlation $\rho \ge 0.35$. | Bid up to **Halo-Adjusted Break-Even ACoS**: $\text{ACoS}^*_{\text{halo}} = \text{Margin} \times (1 + \text{OrganicMultiplier}_{k,21\text{d}})$. |
| **`TREADMILL_DEAD_WEIGHT`** | Cumulative 4w `ad_spend >= $100` **AND** rank slope $> -0.2$ (stagnant worse than #10) **AND** SQP CVR $< 50\%$ of category median. | Cut bids by 25%–50% or negate; fix listing conversion rate before spending for rank. |
| **`AT_RISK_DECAY`** | Trailing 4w rank slope $\ge +0.75$ pos/wk (slipping) **AND** SQP Brand Click Share declining week-over-week. | Simulate bid cuts and deploy defensive Sponsored Products bids where organic halo is positive. |

---

## Example: Average-ACoS Rules vs. `amz-adlift`

> Full walkthrough and reproduction steps in [docs/case_study_optimization.md](docs/case_study_optimization.md).

**Scenario:** Herbal Sleep Supplement (`ASIN: B08XYZ123`, 40% margin, $1,100/wk budget)

| Search Query | Organic Rank | Paid ROAS (ACoS) | Typical PPC Rule | `amz-adlift` Diagnosis | `amz-adlift` Action |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`brand name sleep gummies`** | **#1.0** | **5.0x** (20%) | Raise bids (+20%) | `CANNIBALIZED_RENT` (mTotal ROAS **0.35x**) | Cut spend $500 -> $286 (**-43%**) with zero rank loss |
| **`organic sleep gummies for adults`** | **#7.0** | **2.2x** (45.5%) | Cut bids (-15%) | `FLYWHEEL_LEVERAGE` (mTotal ROAS **2.44x**) | Scale spend $250 -> $573 (**+129%**), pushing rank #7 -> #3 |
| **`melatonin free sleep supplement`** | **#48.0** | **1.4x** (71.4%) | Hold for "rank" | `TREADMILL_DEAD_WEIGHT` (mTotal ROAS **0.68x**) | Slash spend $300 -> $69 (**-77%**) |
| **`tart cherry sleep aid`** | **#4.5** | **2.1x** (47.6%) | Deprioritize | `AT_RISK_DECAY` (mTotal ROAS **3.42x**) | Scale spend $50 -> $172 (**+244%**) to defend Top-5 rank |

**Result on the same $1,100/wk budget:** **+$145.18/week** (**+$7,549.36/year** on a single ASIN) with **$0 extra ad spend**.

---

## Open Core & Pro Extension

- **`amz-adlift` (this repo, MIT):** Pure Python (`>=3.10`) multi-format parsers, funnel isolation, 4-quadrant classifier, white-label HTML/PDF reports, AMC SQL/Markov attribution, CLI, and FastMCP server.
- **`amz_adlift_pro` (optional licensed extension):** Compiled Cython engine for asymmetric velocity-to-rank elasticity, 21-day bid-cut simulation, KKT equimarginal budget allocation, and Seller Central bulk `.xlsx` bid updates.
