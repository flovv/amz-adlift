# Case Study: Typical Amazon PPC Optimization vs. `amz-adlift` Econometric Reallocation

This case study uses synthetic keyword panel data modeled from real-world Seller Central Brand Analytics Search Query Performance (SQP), Amazon Sponsored Products, and organic rank tracking metrics. It compares standard rule-based / agency optimization against the recommendations produced by `amz-adlift` and `amz_adlift_pro`.

---

## 1. Scenario Economics & Baseline Setup

* **ASIN**: `B08XYZ123` (Premium Herbal Sleep Gummies)
* **Unit Economics**:
  * Average Order Value (AOV): **$35.00**
  * Pre-Ad Gross Unit Margin: **40.0%**
  * Target / Break-Even ACoS: **40.0%** (Equivalent to Target ROAS: **2.50x**)
* **Current PPC Budget**: **$1,100.00 / week** across 4 representative keywords covering the four diagnostic quadrants.

---

## 2. Head-to-Head Comparison: Typical PPC Rule vs. `amz-adlift`

| Search Query | Weekly Spend | Organic Rank | Paid ROAS (ACoS) | **Typical PPC Tool / Agency Action** | **`amz-adlift` Quadrant & Marginal Metrics** | **`amz-adlift` Reallocation Recommendation** |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`brand name sleep gummies`** | $500.00 | **#1.0** | **5.0x** (20.0%) | **Increase Bids (+20%)**<br>• *"20% ACoS is well below target 40%. Star performer; bid up to capture more volume!"* | **`CANNIBALIZED_RENT`**<br>• SERP Ceiling reached ($R=1.0$)<br>• Incremental Click Share: ~28%<br>• Marginal Paid ROAS: **0.35x**<br>• Marginal Organic Halo: **0.00x**<br>• Marginal Total ROAS: **0.35x**<br>• Marginal Net Profit: **-$0.86 / $** | **Cut Weekly Spend to $286.46 (-42.7%)**<br>• 21-day rank simulation confirms rank stays at `[1.0, 1.0, 1.0]` with **zero organic loss**.<br>• Unlocks **+$154.55 / week** in pure profit by ending non-incremental cannibalization. |
| **`organic sleep gummies for adults`** | $250.00 | **#7.0** | **2.2x** (45.5%) | **Cut Bids (-15%)**<br>• *"ACoS 45.5% exceeds 40% margin target. Unprofitable keyword; bid down to hit target ACoS."* | **`FLYWHEEL_LEVERAGE`**<br>• Rank Elasticity $\hat{\theta}^{\text{EB}} = 0.52$, $\lambda = 0.68$<br>• Marginal Paid ROAS: **1.30x**<br>• Marginal Organic Halo ROAS: **1.14x**<br>• Marginal Total ROAS: **2.44x**<br>• Halo Break-Even ACoS: **55.2%** | **Scale Weekly Spend to $572.92 (+129.2%)**<br>• Velocity pushes organic rank from #7 $\to$ #3, generating downstream organic sales that dwarf the ad spend.<br>• Cutting bids here would cause organic rank collapse. |
| **`melatonin free sleep supplement`** | $300.00 | **#48.0** | **1.4x** (71.4%) | **Hold / Slow Bid Down**<br>• *"Keep spending for brand awareness and to establish organic rank."* | **`TREADMILL_DEAD_WEIGHT`**<br>• Rank Elasticity $\hat{\theta}^{\text{EB}} = 0.05$ (near zero)<br>• Listing CVR $<50\%$ of category benchmark<br>• Marginal Total ROAS: **0.68x**<br>• Marginal Net Profit: **-$0.73 / $** | **Slash Weekly Spend to $68.75 (-77.1%)**<br>• Stops incinerating capital where listing conversion defects prevent rank transmission.<br>• Frees **$231.25 / week** for high-velocity keywords. |
| **`tart cherry sleep aid`** | $50.00 | **#4.5** | **2.1x** (47.6%) | **Deprioritize / Low Bid**<br>• *"Low volume, ACoS 47.6% is above target."* | **`AT_RISK_DECAY`**<br>• Rank Elasticity $\hat{\theta}^{\text{EB}} = 0.44$, $\lambda = 0.72$<br>• Organic rank slipping (#2.0 $\to$ #4.5)<br>• Marginal Organic Halo ROAS: **2.26x**<br>• Marginal Total ROAS: **3.42x**<br>• Marginal Net Profit: **+$0.37 / $** | **Increase Weekly Spend to $171.88 (+243.8%)**<br>• Restores organic top-3 placement.<br>• Every additional dollar yields **$1.37 in gross margin**. |

---

## 3. Mathematical Foundations: Why Rule-Based Systems Fail

### 3.1. The Average ROAS vs. Marginal ROAS Fallacy

Traditional bid optimizers operate on **Average ROAS**:
$$\text{Average ROAS} = \frac{\text{Ad Sales}}{\text{Ad Spend}}$$

Because paid advertising exhibits **diminishing returns** (governed by Hill saturation), the return on the *next dollar spent* ($\text{mROAS}$) is strictly lower than the average return of all previous dollars:
$$\text{mROAS}_{\text{paid}}(S) = \frac{\partial \text{AdSales}(S)}{\partial S} < \text{Average ROAS}(S)$$

On `brand name sleep gummies`:
* Average ROAS looks stellar at **5.0x** (20% ACoS).
* Marginal ROAS on the 500th dollar is only **0.35x**. At a 40% margin, that dollar generates only $0.14 of margin—a net loss of $0.86 per dollar spent!

### 3.2. SERP Rank #1 Ceiling & Cannibalization Discounting

At organic slot #1.0, an Amazon listing has reached the SERP ceiling:
$$R_s = \min\left(305, \max\left(1.0, R_0 \cdot \left(\frac{1 + V_0}{1 + V_s}\right)^{\hat{\theta}^{\text{EB}}}\right)\right)$$
* For $R_0 = 1.0$, $R_s$ cannot improve. Therefore, **Marginal Organic Halo ROAS is identically 0.00x**.
* Furthermore, Brand Analytics SQP reveals that ~72% of consumers searching the brand term will click the organic listing if the ad is not present. Only 28% of paid clicks are incremental.

### 3.3. Halo-Adjusted Break-Even ACoS

On mid-pack keywords like `organic sleep gummies for adults` (Organic Rank #7), PPC velocity transmits into organic rank improvement. Over a 21-day Adstock horizon ($\lambda = 0.68$), downstream organic sales add **1.14x in organic revenue per ad dollar**:
$$\text{ACoS}^*_{\text{halo}} = \text{ProductMargin} \times \left(1 + \text{OrganicMultiplier}_{21\text{d}}\right) = 40.0\% \times (1 + 0.38) = 55.2\%$$
A 45.5% observed ACoS is therefore highly profitable when accounting for organic halo.

---

## 4. Portfolio Optimization Results

Running `allocate_portfolio_budget` with a fixed **$1,100.00 / week** budget reallocates dollars according to the Equimarginal Principle ($\text{ProductMargin} \times \text{mROAS}_{\text{total}} = 1.0$):

```text
================================================================================
TOTAL WEEKLY BUDGET:      $1,100.00  ──►  $1,100.01  (0.0% spend increase)
NET WEEKLY PROFIT LIFT:   Baseline   ──►  +$145.18 / week
ANNUALIZED PROFIT LIFT:   Baseline   ──►  +$7,549.36 / year (single ASIN)
================================================================================
```

### Capital Flow Breakdown:
1. **Capital Reclaimed from Negative Marginal Terms**:
   * `brand name sleep gummies`: -$213.54 / week
   * `melatonin free sleep supplement`: -$231.25 / week
   * **Total Reclaimed**: **$444.79 / week**
2. **Capital Reinvested into High Flywheel Leverage**:
   * `organic sleep gummies for adults`: +$322.92 / week
   * `tart cherry sleep aid`: +$121.88 / week
   * **Total Reinvested**: **$444.80 / week**

---

## 5. How to Replicate This Analysis

### Using the FastMCP Server (Claude Desktop / Cursor)
```json
// 1. Audit panel and fit Cython econometric models
audit_amazon_flywheel(
  sqp_csv_path="./exports/Search_Query_Performance.csv",
  ads_csv_path="./exports/Sponsored_Products_Search_Terms.csv",
  rank_csv_path="./exports/Organic_Rank_Tracker.csv",
  category="supplements",
  product_margin=0.40
)

// 2. Compute equimarginal portfolio allocation
optimize_budget_allocation(total_weekly_budget=1100.0)

// 3. Export upload-ready Amazon Ads Bulk Sheet
export_ads_bulksheet(output_path="./reports/bulk_update.xlsx")
```

### Using the Typer CLI
```bash
# Reallocate weekly budget across keywords
amz-adlift allocate --budget 1100
```
