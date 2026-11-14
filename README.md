# amz-flywheel

**Zero-OAuth, local-first Python econometric package & Model Context Protocol (MCP) server quantifying the causal Amazon Paid-to-Organic Search Flywheel.**

`amz-flywheel` isolates pure organic search conversions from combined Amazon Brand Analytics Search Query Performance (SQP) reports, classifies every `(asin, search_query)` panel into four deterministic diagnostic quadrants, and—when paired with the compiled Cython Pro engine (`amz_flywheel_pro`)—estimates asymmetric velocity-to-rank elasticities ($\theta^{\text{EB}}_k, \lambda_k$), simulates 21-day counterfactual bid cuts, and exports ready-to-upload Amazon Ads Bulk Operations `.xlsx` spreadsheets.

---

## Architecture & Open-Core Topology

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ REPO 1: PUBLIC (`amz-flywheel`)                                            │
│ • Pure readable Python (>=3.10) (`pip install amz-flywheel`)               │
│ • Multi-format local CSV ingestor (Brand Analytics SQP + Ads + Rank logs)  │
│ • Organic vs. Paid funnel isolation & 4-Quadrant diagnostic classifier     │
│ • FastMCP server (`amz-flywheel-mcp`) with Tools, Resources & Prompts      │
│ • Pro binary bridge & Polar.sh wheel installer (`install_pro(api_key)`)    │
└─────────────────────────────────────┬──────────────────────────────────────┘
                                      │ Dynamic Runtime Bridge
                                      ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ REPO 2: PRIVATE (`amz-flywheel-pro-private` -> `amz_flywheel_pro`)         │
│ • Compiled Cython C-extensions (`.so` / `.pyd`) with stripped source       │
│ • Asymmetric Adstock-to-Rank elasticity & 21-day bid-cut simulator         │
│ • Embedded C-level category elasticity priors (`category_priors.pyx`)      │
│ • Halo-Adjusted Break-Even ACoS & Amazon Ads Bulk Sheet generator          │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Quickstart

### 1. Installation

```bash
pip install amz-flywheel
```

### 2. CLI Usage (`amz-flywheel`)

```bash
# 1. Run a local Paid-to-Organic Flywheel audit from exported CSVs
amz-flywheel audit \
  --sqp ./exports/US_Search_Query_Performance_ASIN.csv \
  --ads ./exports/Sponsored_Products_Search_Term_Report.csv \
  --rank ./exports/Helium10_Keyword_Tracker.csv \
  --category supplements \
  --margin 0.38 \
  --out ./reports/flywheel_audit.json

# 2. Validate Polar.sh license key and activate Pro Cython wheel
amz-flywheel auth install-pro --key "AMZ_FW_PRO_..."

# 3. Reallocate portfolio budget using Hill-Saturated Marginal Response Curves
amz-flywheel allocate --budget 1100

# 4. Generate privacy-safe Amazon Marketing Cloud (AMC) SQL queries
amz-flywheel amc sql --days 28

# 5. Start the FastMCP stdio server for Claude Desktop / Cursor
amz-flywheel mcp
```

---

## Agentic Setup: Claude Desktop & Cursor (FastMCP)

`amz-flywheel-mcp` runs 100% locally over `stdio`. Proprietary Seller Central Brand Analytics and Sponsored Products CSVs never leave the analyst's machine.

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "amz-flywheel": {
      "command": "uvx",
      "args": ["--from", "amz-flywheel", "amz-flywheel-mcp"]
    }
  }
}
```

### Cursor (`.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "amz-flywheel": {
      "command": "amz-flywheel-mcp",
      "args": []
    }
  }
}
```

### Exposed MCP Capabilities

| Type | Name / URI | Tier | Description |
| :--- | :--- | :--- | :--- |
| **Tool** | `audit_amazon_flywheel` | Open Core + Pro | Joins local SQP, Ads, and Rank CSVs; isolates pure organic clicks/orders; classifies 4 quadrants; attaches Pro elasticity & Halo ACoS if licensed. |
| **Tool** | `optimize_budget_allocation` | Pro | Uses Hill-Saturated Marginal Response Curves (`mROAS`) and the Equimarginal Principle to reallocate weekly PPC budget from saturated #1 rank terms into high-leverage flywheel terms. |
| **Tool** | `simulate_keyword_bid_cut` | Pro | Simulates 21-day organic rank trajectory ($\hat{R}_{t+1\dots t+3}$) and net organic profit impact under `-25%`, `-50%`, and `-100%` PPC spend cuts. |
| **Tool** | `export_ads_bulksheet` | Pro | Generates an Amazon Ads Sponsored Products Bulk Operations `.xlsx` file (`Operation = Update`) with Halo-Adjusted Break-Even bids. |
| **Tool** | `analyze_amc_clean_room` | Open Core | Generates privacy-safe AMC SQL queries (`COUNT(DISTINCT user_id) >= 100`) and computes First-Order Markov Chain Removal Effects vs. Last-Touch variance. |
| **Tool** | `activate_amz_flywheel_pro` | Pro | Validates a Polar.sh key and writes a 24-hour HMAC-SHA256 signed token to `~/.amz_flywheel/license.cache`. |
| **Resource** | `flywheel://reference/quadrants` | Open Core | Machine-readable JSON of the 4 diagnostic quadrants, exact mathematical thresholds, and bid action playbooks. |
| **Resource** | `flywheel://reference/category-priors` | Open Core + Pro | Available category elasticity priors (`general`, `supplements`, `electronics`, `home_kitchen`, `beauty`, `pet_supplies`, `apparel`). |
| **Prompt** | `executive_flywheel_audit` | Open Core + Pro | Structured multi-step prompt guiding an LLM agent through a CFO/CMO Paid-to-Organic audit. |

---

## Python SDK Usage

```python
from amz_flywheel import ingest_and_align, classify_panel, enrich_with_pro_elasticity

# 1. Ingest and align multi-format Seller Central SQP, Ads, and Rank CSVs
panel = ingest_and_align(
    sqp_csv_path="tests/fixtures/sqp_multiweek.csv",
    ads_csv_path="tests/fixtures/ads_multiweek.csv",
    rank_csv_path="tests/fixtures/rank_multiweek.csv",
)

# 2. Run deterministic 4-quadrant diagnostic classification
diagnostics = classify_panel(panel, category="supplements", strict=True)
for diag in diagnostics:
    print(f"{diag.search_query:30s} -> {diag.quadrant:22s} | {diag.diagnostic_summary}")

# 3. Optional Pro elasticity & Halo Break-Even ACoS enrichment
pro_metrics = enrich_with_pro_elasticity(panel, category="supplements", product_margin=0.38)
```

---

## Supported Multi-Format CSV Schemas (Zero OAuth)

All parsers automatically normalize US/UK (`1,234.56`, `$`, `£`) and EU/DE (`1.234,56`, `€`) number formats and align dates to Amazon SQP weekly Sunday–Saturday buckets.

### 1. Brand Analytics Search Query Performance (`io/sqp_parser.py`)
Supports Row 1 metadata banners (`ASIN=["B08XYZ123"],Reporting Range=["Weekly"],Select Week=["2026-10-18 - 2026-10-24"]`) followed by Row 2 headers in both **ASIN View** (`Impressions: ASIN Count`, `Clicks: ASIN Count`, `Purchases: ASIN Count`) and **Brand View** (`Impressions: Brand Count`, `Clicks: Brand Count`, `Purchases: Brand Count`).

### 2. Amazon Ads Search Term Reports (`io/ads_parser.py`)

| Normalized Field | Legacy Sponsored Products Header | 2026 Unified Reporting Header | German (DE) Header |
| :--- | :--- | :--- | :--- |
| `date_range` | `Start Date` + `End Date` | `Date range` or `Date` | `Startdatum` + `Enddatum` |
| `campaign_name` | `Campaign Name` | `Campaign name` | `Kampagnenname` |
| `ad_group_name` | `Ad Group Name` | `Ad group name` | `Anzeigengruppenname` |
| `search_query` | `Customer Search Term` | `Search term` | `Suchbegriff` |
| `match_type` | `Match Type` | `Targeting match type` | `Übereinstimmungstyp` |
| `ad_impressions` | `Impressions` | `Impressions` | `Impressionen` |
| `ad_clicks` | `Clicks` | `Clicks` | `Klicks` |
| `ad_spend` | `Spend` | `Total cost` | `Ausgaben` |
| `ad_sales` | `7 Day Total Sales` | `Sales` | `7 Tage, Umsatz gesamt` |
| `ad_orders` | `7 Day Total Orders (#)` | `Purchases` | `7 Tage, Aufträge gesamt (#)` |

### 3. Organic Keyword Rank Tracker (`io/rank_parser.py`)
Accepts Helium 10 Keyword Tracker, DataDive, Perpetua, or generic CSV exports containing `Keyword` / `Search Term`, `Date` / `Timestamp`, `Organic Rank` (aggregated to weekly median; `>300` or `unranked` capped at `305.0`), and optional `Sponsored Rank`.

---

## Econometric Methodology & 4-Quadrant Definitions

### Funnel Isolation (`core/decomposition.py`)
Amazon SQP reports combine organic and Sponsored Products SERP interactions within a calendar week, whereas Ads reports use a 7-day post-click attribution window:
- **Pure Organic Clicks**: $C^{\text{org}}_{k,t} = \max\left(0, C^{\text{SQP}}_{k,t} - C^{\text{ads}}_{k,t}\right)$
- **Pure Organic Orders**: $O^{\text{org}}_{k,t} = \max\left(0, O^{\text{SQP}}_{k,t} - O^{\text{ads}}_{k,t}\right)$
- **Attribution Window Gap Flag**: `attribution_window_gap = True` whenever $O^{\text{ads}}_{k,t} > O^{\text{SQP}}_{k,t}$.
- **True Paid Share of Brand Orders**: $\text{PaidShare}_{k,t} = \frac{O^{\text{ads}}_{k,t}}{\max\left(1, O^{\text{ads}}_{k,t} + O^{\text{org}}_{k,t}\right)}$

### 4-Quadrant Diagnostic Classifier (`core/quadrants.py`)
Requires $\ge 4$ aligned weeks per `(asin, search_query)`:

| Quadrant | Classification Criteria | Recommended Bid Action |
| :--- | :--- | :--- |
| **`CANNIBALIZED_RENT`** | Trailing 4w median `organic_rank <= 2.5` **AND** pure organic CVR $\ge 12\%$ **AND** weekly `ad_spend >= $50` (or top 25% of account). | Step down Exact CPC bids by 15%–25%; brand is paying rent on clicks it already owns organically at #1–#2. |
| **`FLYWHEEL_LEVERAGE`** | Trailing 4–8w OLS rank velocity slope $\frac{\Delta R_k}{\Delta t} \le -0.5$ pos/wk (climbing toward #1) **AND** lagged paid-to-organic order correlation $\rho \ge 0.35$. | Bid up to **Halo-Adjusted Break-Even ACoS**: $\text{ACoS}^*_{\text{halo}} = \text{Margin} \times (1 + \text{OrganicMultiplier}_{k,21\text{d}})$. |
| **`TREADMILL_DEAD_WEIGHT`** | Cumulative 4w `ad_spend >= $100` **AND** rank slope $> -0.2$ (stagnant worse than #10) **AND** SQP CVR $< 50\%$ of category median. | Cut bids by 25%–50% or negate; listing conversion rate must be improved before PPC can lift organic rank. |
| **`AT_RISK_DECAY`** | Trailing 4w rank velocity slope $\ge +0.75$ pos/wk (slipping down SERP) **AND** SQP Brand Click Share declining week-over-week. | Run `simulate_keyword_bid_cut` and deploy defensive Sponsored Products bids where Halo Multiplier is positive. |

---

## Case Study: Typical PPC Tool vs. `amz-flywheel` Optimization

> *Detailed econometric walkthrough, mathematical derivations, and reproduction scripts are documented in [docs/case_study_optimization.md](docs/case_study_optimization.md).*

### Scenario: Herbal Sleep Supplement (`ASIN: B08XYZ123`, 40% Margin, $1,100/wk Budget)

| Search Query | Organic Rank | Paid ROAS (ACoS) | **Typical Tool / Agency Action** | **`amz-flywheel` Econometric Diagnosis** | **`amz-flywheel` Recommendation** |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`brand name sleep gummies`** | **#1.0** | **5.0x** (20%) | **Raise Bids (+20%)**<br>*(Star performer; low ACoS)* | **`CANNIBALIZED_RENT`**<br>SERP ceiling reached; marginal total ROAS = **0.35x** (-$0.86 net profit per dollar). | **Cut Spend: $500 $\to$ $286 (-43%)**<br>Saves $213/wk with **zero rank loss** (`[1.0, 1.0, 1.0]`). |
| **`organic sleep gummies for adults`** | **#7.0** | **2.2x** (45.5%) | **Cut Bids (-15%)**<br>*(ACoS 45.5% > 40% target)* | **`FLYWHEEL_LEVERAGE`**<br>High rank elasticity ($\theta = 0.52$); 21d organic halo adds **1.14x**; marginal total ROAS = **2.44x**. | **Scale Spend: $250 $\to$ $573 (+129%)**<br>Drives rank from #7 $\to$ #3, unlocking organic order halo. |
| **`melatonin free sleep supplement`** | **#48.0** | **1.4x** (71.4%) | **Hold / Slow Bid Down**<br>*(Keep spending for "rank")* | **`TREADMILL_DEAD_WEIGHT`**<br>Zero rank elasticity ($\theta = 0.05$); CVR defect; marginal total ROAS = **0.68x**. | **Slash Spend: $300 $\to$ $69 (-77%)**<br>Stops capital waste on un-rankable term. |
| **`tart cherry sleep aid`** | **#4.5** | **2.1x** (47.6%) | **Under-bid / Deprioritize**<br>*(Low volume, marginal ACoS)* | **`AT_RISK_DECAY`**<br>Rank slipping; marginal total ROAS = **3.42x** (+$0.37 net profit per dollar). | **Scale Spend: $50 $\to$ $172 (+244%)**<br>Defends Top-5 organic rank. |

### The Portfolio Bottom Line (Equimarginal Reallocation)

```text
Total Weekly Spend:      $1,100.00  ──►  $1,100.01  (0.0% spend increase)
Net Weekly Profit Lift:  Baseline   ──►  +$145.18 / week
Annualized Profit Lift:  Baseline   ──►  +$7,549.36 / year (single ASIN)
```

**Why It Works**: Traditional tools operate on **Average ROAS** and cannot distinguish incremental paid orders from cannibalized organic clicks at Rank #1. `amz-flywheel` computes **Marginal Total ROAS** across both paid and organic funnels, shifting budget out of saturated negative-marginal terms into positive-marginal flywheel drivers without increasing total spend by a single dollar.

