---
name: amz-adlift
description: Audit Amazon PPC vs. organic search performance locally from Brand Analytics Search Query Performance (SQP), Amazon Ads Search Term (CSV/XLSX), and keyword rank exports. Use when analyzing Amazon ad cannibalization, TACoS, paid-to-organic rank lift, keyword bid cuts, weekly PPC budget reallocation, white-label client audit reports, or upload-ready Amazon Ads Bulk Operations spreadsheets.
---

# amz-adlift

Run local-first Amazon PPC vs. organic search audits without OAuth or cloud uploads. `amz-adlift` joins exported Brand Analytics Search Query Performance (SQP), Amazon Ads Search Term (CSV/XLSX), and optional keyword rank tracker CSVs to separate pure organic orders from paid orders, classify every keyword into four actionable quadrants, and generate reports or bid updates.

## Setup

Install the CLI / Python package:

```bash
pip install amz-adlift
```

Or run the local MCP server directly via `uvx`:

```bash
uvx --from amz-adlift amz-adlift-mcp
```

## Standard Audit Workflow

### 1. Gather Local Exports

Ask the user for the local paths to their exported files:
- **Required — SQP CSV (or directory of weekly CSVs):** Seller Central -> Brand Analytics -> Search Query Performance (ASIN View or Brand View).
- **Required — Amazon Ads Search Term Report (`.csv` or `.xlsx`):** Legacy Sponsored Products, 2026 Unified Reporting, or EU/DE localized exports.
- **Optional — Organic Rank CSV:** Helium 10 Keyword Tracker, DataDive, Perpetua, or generic `Keyword, Date, Organic Rank` CSV.
- **Optional — AMC Clean Room CSV:** New-to-Brand (NTB) cohort export for repeat-customer cannibalization checks.
- **Required context:** Pre-ad product gross margin (e.g. `0.38` for 38%) and product category (`general`, `supplements`, `electronics`, `home_kitchen`, `beauty`, `pet_supplies`, `apparel`).

All parsers automatically normalize US/UK (`1,234.56`, `$`, `£`) and EU/DE (`1.234,56`, `€`) formatting and align dates to Amazon SQP Sunday-Saturday weeks.

### 2. Run the Audit

**Via CLI:**
```bash
amz-adlift audit \
  --sqp ./exports/sqp.csv \
  --ads ./exports/ads_search_terms.csv \
  --rank ./exports/rank_tracker.csv \
  --category supplements \
  --margin 0.38 \
  --out ./reports/audit.json
```

**Via MCP:**
Call `audit_amazon_flywheel(sqp_csv_path=..., ads_csv_path=..., rank_csv_path=..., category=..., product_margin=0.38, include_raw_panel=False)`.
Use `include_raw_panel=False` when working in an LLM context window to keep the response compact; the full state is persisted locally to `~/.amz_adlift/last_audit_state.json`.

### 3. Interpret the Four Quadrants

Every `(asin, search_query)` with at least 4 aligned weeks is classified into one of four quadrants:

| Quadrant | Meaning | Recommended Action |
| :--- | :--- | :--- |
| `CANNIBALIZED_RENT` | Already ranking organically at #1-#2.5 with strong organic CVR (>=12%) while still spending heavily on Exact PPC. | Step down Exact CPC bids by 15%-25% to stop paying ad rent on organic clicks. |
| `FLYWHEEL_LEVERAGE` | Organic rank is climbing (`<= -0.5` pos/wk) and paid orders correlate with subsequent organic orders (`rho >= 0.35`). | Scale spend up to Halo-Adjusted Break-Even ACoS (factoring in the 21-day organic order lift). |
| `TREADMILL_DEAD_WEIGHT` | Significant 4-week spend (`>= $100`) with stagnant rank worse than #10 and SQP CVR below 50% of category median. | Cut bids by 25%-50% or negate until listing CVR/offer is fixed. |
| `AT_RISK_DECAY` | Organic rank is slipping (`>= +0.75` pos/wk) and SQP Brand Click Share is falling week-over-week. | Defend Top-5 rank with targeted Sponsored Products bids where organic halo is positive. |

Check `attribution_window_gap` flags (when 7-day post-click Ads orders exceed same-week SQP orders) and `red_team_warnings` (e.g. low AMC NTB share indicating repeat-customer cannibalization) before making final recommendations.

### 4. Generate Deliverables

- **White-label HTML/PDF executive report (Open Core + Pro):**
  ```bash
  amz-adlift report \
    --out ./reports/client_audit.html \
    --agency-name "Your Agency" \
    --client-name "Client Brand"
  ```
  Or call MCP tool `generate_audit_report`.

- **AMC privacy-safe SQL & Markov attribution (Open Core):**
  ```bash
  amz-adlift amc sql --days 28
  ```
  Or call MCP tool `analyze_amc_clean_room`.

- **Pro-only optimization & execution** (requires `amz_adlift_pro` activated via `amz-adlift auth install-pro --key "AMZ_AL_PRO_..."`):
  - **Equimarginal budget reallocation (KKT water-filling):** `amz-adlift allocate --budget 1100` or MCP tool `optimize_budget_allocation`.
  - **21-day bid-cut simulation:** MCP tool `simulate_keyword_bid_cut(search_query=..., asin=..., spend_change_pct=-0.50, horizon_weeks=3)`.
  - **Upload-ready Seller Central Bulksheet `.xlsx`:**
    ```bash
    amz-adlift bulksheet \
      --existing-bulk ./exports/Amazon_Ads_Bulk_Operations.xlsx \
      --out ./reports/upload_ready_bulk_update.xlsx \
      --max-change 0.25 --min-bid 0.20 --max-bid 8.00
    ```
    Always pass `--existing-bulk` so exact Amazon `Campaign ID`, `Ad Group ID`, and `Keyword ID` values are preserved, and enforce conservative `--max-change`, `--min-bid`, and `--max-bid` guardrails before uploading to Seller Central.

## Guardrails

- **Privacy:** Never upload raw Seller Central CSVs to external endpoints. All parsing and modeling run 100% locally.
- **Data sufficiency:** Quadrant classification requires >= 4 aligned weeks per `(asin, search_query)`. If fewer weeks are present, tell the user and request a wider export window.
- **Percentages:** Prefer decimal fractions (`0.38` for 38% margin, `-0.50` for a 50% bid cut); MCP tools auto-normalize whole percentages if passed.
- **No blind bid edits:** Always review `bid_diffs` and verify `upload_ready: true` before recommending a bulksheet upload.
