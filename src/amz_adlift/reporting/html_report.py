"""
Interactive White-Label Executive HTML / Print-to-PDF Audit Report Generator
(reporting/html_report.py).

Produces a self-contained, zero-CDN HTML5 audit deck featuring:
  - White-label agency/client branding header
  - Executive KPI cards (Monthly Wasted Spend, Projected Profit Lift, Shadow Price, Backtest Accuracy)
  - Interactive 4-Quadrant SVG Scatter Plot (Organic Rank vs. Marginal Total ROAS)
  - Interactive Per-Keyword Marginal Response Curve Explorer (Avg ROAS vs. Marginal Paid & Organic Halo)
  - Full Equimarginal Reallocation Table with 90% CIs, Backtest MAPE & Adversarial Red-Team Warnings
"""

from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path
from typing import Any, Optional, Union


def generate_html_audit_report(
    audit_report: dict[str, Any],
    output_path: Union[str, Path],
    allocation_report: Optional[dict[str, Any]] = None,
    agency_name: str = "amz-adlift Econometrics",
    client_name: Optional[str] = None,
    logo_url: Optional[str] = None,
) -> dict[str, Any]:
    """
    Render a self-contained, print-to-PDF-ready interactive executive HTML audit deck
    from an `audit_amazon_flywheel` report and optional `optimize_budget_allocation` result.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    asin = str(audit_report.get("asin", "UNKNOWN_ASIN"))
    category = str(audit_report.get("category", "general"))
    margin = float(audit_report.get("product_margin", 0.35))
    pro_enabled = bool(audit_report.get("pro_enabled", False))
    keywords: list[dict[str, Any]] = list(audit_report.get("keywords", []))
    red_team_warnings: list[str] = list(audit_report.get("red_team_warnings", []))
    quad_counts: dict[str, int] = dict(audit_report.get("quadrant_counts", {}))
    operational_health: Optional[dict[str, Any]] = audit_report.get("operational_health")
    funnel_bottlenecks: list[dict[str, Any]] = list(audit_report.get("funnel_bottlenecks") or [])

    alloc_by_kw: dict[str, dict[str, Any]] = {}
    if allocation_report and allocation_report.get("allocations"):
        for item in allocation_report["allocations"]:
            alloc_by_kw[str(item.get("search_query", ""))] = item

    # Compute Executive KPIs
    weekly_wasted_spend = 0.0
    weekly_total_spend = 0.0
    backtest_mapes: list[float] = []

    enriched_rows: list[dict[str, Any]] = []
    for kw in keywords:
        q = str(kw.get("search_query", ""))
        quad = str(kw.get("quadrant", "INSUFFICIENT_DATA"))
        wk_spend = float(kw.get("weekly_ad_spend_avg", 0.0))
        weekly_total_spend += wk_spend
        if quad in ("CANNIBALIZED_RENT", "TREADMILL_DEAD_WEIGHT"):
            weekly_wasted_spend += wk_spend

        pm = kw.get("pro_metrics") or {}
        al = alloc_by_kw.get(q) or {}

        bt_mape = pm.get("backtest_rank_mape")
        if bt_mape is not None:
            backtest_mapes.append(float(bt_mape))

        enriched_rows.append(
            {
                "search_query": q,
                "asin": str(kw.get("asin", asin)),
                "quadrant": quad,
                "rank": kw.get("median_organic_rank_4w"),
                "weekly_spend": round(wk_spend, 2),
                "allocated_spend": al.get("allocated_weekly_spend", pm.get("optimal_weekly_spend")),
                "spend_delta": al.get("spend_delta", pm.get("recommended_spend_delta")),
                "avg_paid_roas": pm.get("average_paid_roas"),
                "marginal_paid_roas": pm.get("marginal_paid_roas"),
                "marginal_organic_roas": pm.get("marginal_organic_roas"),
                "marginal_total_roas": pm.get("marginal_total_roas"),
                "marginal_total_roas_allocated": al.get("marginal_total_roas_allocated"),
                "halo_break_even_acos": pm.get("halo_break_even_acos"),
                "theta_eb": pm.get("theta_eb"),
                "theta_ci_90": pm.get("theta_ci_90"),
                "r_squared": pm.get("r_squared"),
                "backtest_rank_mape": bt_mape,
                "hill_fit_source": pm.get("hill_fit_source", "bayesian_prior"),
                "response_curve": pm.get("response_curve", []),
                "red_team_flags": kw.get("red_team_flags", []),
                "summary": kw.get("diagnostic_summary", ""),
            }
        )

    monthly_wasted_spend = round(weekly_wasted_spend * 4.33, 2)
    weekly_profit_lift = (
        float(allocation_report.get("projected_weekly_profit_lift", 0.0))
        if allocation_report
        else 0.0
    )
    annual_profit_lift = round(weekly_profit_lift * 52.0, 2)
    shadow_price = (
        float(allocation_report.get("shadow_price_mroas", 0.0))
        if allocation_report
        else 0.0
    )
    break_even_roas = round(1.0 / max(0.05, margin), 2)
    avg_backtest_mape = (
        round((sum(backtest_mapes) / len(backtest_mapes)) * 100.0, 1)
        if backtest_mapes
        else None
    )

    display_client = client_name or f"ASIN {asin}"
    report_date = date.today().isoformat()
    safe_agency = html.escape(agency_name)
    safe_client = html.escape(display_client)
    logo_html = (
        f'<img src="{html.escape(logo_url)}" alt="{safe_agency}" class="brand-logo" />'
        if logo_url
        else f'<div class="brand-monogram">{html.escape(agency_name[:2].upper())}</div>'
    )

    payload_json = json.dumps(
        {
            "rows": enriched_rows,
            "margin": margin,
            "breakEvenRoas": break_even_roas,
            "shadowPrice": shadow_price,
        }
    ).replace("</", "<\\/")

    quad_badges_html = "".join(
        f'<span class="pill pill-{k.lower()}">{k.replace("_", " ")}: <strong>{quad_counts.get(k, 0)}</strong></span>'
        for k in (
            "CANNIBALIZED_RENT",
            "FLYWHEEL_LEVERAGE",
            "TREADMILL_DEAD_WEIGHT",
            "AT_RISK_DECAY",
        )
    )

    warnings_html = ""
    if red_team_warnings:
        items_li = "".join(f"<li>{html.escape(w)}</li>" for w in red_team_warnings)
        warnings_html = f"""
        <section class="card alert-card">
          <h2>Adversarial Red-Team Econometric Warnings ({len(red_team_warnings)})</h2>
          <ul>{items_li}</ul>
        </section>
        """

    ops_health_html = ""
    if operational_health:
        bb_pct = float(operational_health.get("buy_box_pct", 0.0))
        promo_share = float(operational_health.get("promo_day_share", 0.0)) * 100.0
        dos = operational_health.get("days_of_inventory_supply")
        dos_str = f"{float(dos):.0f} days" if dos is not None else "—"
        allow_inc = bool(operational_health.get("allow_bid_increases", True))
        bid_status = (
            '<span class="pos">ALLOWED</span>'
            if allow_inc
            else '<span class="neg">CAPPED / FROZEN</span>'
        )
        ops_flags = operational_health.get("flags") or []
        ops_recs = operational_health.get("recommendations") or []
        flags_line = (
            " &middot; ".join(html.escape(str(f)) for f in ops_flags)
            if ops_flags
            else "All operational guardrails healthy"
        )
        recs_li = "".join(f"<li>{html.escape(str(r))}</li>" for r in ops_recs)
        recs_block = f'<ul style="margin:8px 0 0;padding-left:18px;font-size:12.5px;">{recs_li}</ul>' if recs_li else ""
        ops_health_html = f"""
        <section class="card" id="operational-health-card">
          <h2>Operational Health &amp; Buy Box Guardrails</h2>
          <div style="display:flex;flex-wrap:wrap;gap:20px;font-size:13px;">
            <div><span class="muted">Featured Offer (Buy Box):</span> <strong>{bb_pct:.1f}%</strong></div>
            <div><span class="muted">Promo Days (30d):</span> <strong>{promo_share:.1f}%</strong></div>
            <div><span class="muted">FBA Days of Supply:</span> <strong>{dos_str}</strong></div>
            <div><span class="muted">Automated Bid Hikes:</span> {bid_status}</div>
            <div><span class="muted">Status:</span> <code>{flags_line}</code></div>
          </div>
          {recs_block}
        </section>
        """

    funnel_html = ""
    if funnel_bottlenecks:
        f_rows = []
        for fb in funnel_bottlenecks:
            f_rows.append(
                f"""
                <tr>
                  <td><strong>{html.escape(str(fb.get('search_query', '')))}</strong></td>
                  <td class="num">{float(fb.get('brand_ctr', 0.0)) * 100:.2f}%</td>
                  <td class="num">{float(fb.get('brand_atc_rate', 0.0)) * 100:.1f}%</td>
                  <td class="num">{float(fb.get('brand_checkout_rate', 0.0)) * 100:.1f}%</td>
                  <td class="num">{float(fb.get('cvr_index_vs_market', 1.0)):.2f}x</td>
                  <td><code>{html.escape(str(fb.get('bottleneck', 'HEALTHY')))}</code></td>
                  <td class="muted">{html.escape(str(fb.get('recommendation', '')))}</td>
                </tr>
                """
            )
        funnel_html = f"""
        <section class="card" id="sqp-funnel-card">
          <h2>SQP 3-Stage Funnel Bottlenecks</h2>
          <div style="overflow-x:auto;">
            <table>
              <thead>
                <tr>
                  <th>Search Query</th>
                  <th class="num">CTR</th>
                  <th class="num">ATC Rate</th>
                  <th class="num">Checkout</th>
                  <th class="num">CVR vs. Mkt</th>
                  <th>Bottleneck</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {''.join(f_rows)}
              </tbody>
            </table>
          </div>
        </section>
        """

    table_rows_html = []
    for r in enriched_rows:
        q_class = r["quadrant"].lower()
        rank_str = f"#{r['rank']:.1f}" if r["rank"] is not None else "—"
        alloc_str = (
            f"${r['allocated_spend']:,.2f}" if r["allocated_spend"] is not None else "—"
        )
        delta_val = r["spend_delta"]
        if delta_val is not None:
            delta_cls = "pos" if delta_val > 0 else ("neg" if delta_val < 0 else "")
            delta_str = f'<span class="{delta_cls}">{delta_val:+,.2f}</span>'
        else:
            delta_str = "—"

        avg_r = f"{r['avg_paid_roas']:.2f}x" if r["avg_paid_roas"] is not None else "—"
        m_tot = (
            f"{r['marginal_total_roas']:.2f}x"
            if r["marginal_total_roas"] is not None
            else "—"
        )
        m_org = (
            f"{r['marginal_organic_roas']:.2f}x"
            if r["marginal_organic_roas"] is not None
            else "—"
        )
        halo_acos = (
            f"{r['halo_break_even_acos'] * 100:.1f}%"
            if r["halo_break_even_acos"] is not None
            else "—"
        )
        if r["theta_eb"] is not None and r["theta_ci_90"]:
            ci = r["theta_ci_90"]
            theta_str = f"{r['theta_eb']:.2f} <span class='muted'>[{ci[0]:.2f}, {ci[1]:.2f}]</span>"
        elif r["theta_eb"] is not None:
            theta_str = f"{r['theta_eb']:.2f}"
        else:
            theta_str = "—"
        mape_str = (
            f"{r['backtest_rank_mape'] * 100:.1f}%"
            if r["backtest_rank_mape"] is not None
            else "—"
        )
        table_rows_html.append(
            f"""
            <tr>
              <td><strong>{html.escape(r['search_query'])}</strong></td>
              <td><span class="badge badge-{q_class}">{r['quadrant'].replace('_', ' ')}</span></td>
              <td class="num">{rank_str}</td>
              <td class="num">${r['weekly_spend']:,.2f}</td>
              <td class="num">{alloc_str}</td>
              <td class="num">{delta_str}</td>
              <td class="num">{avg_r}</td>
              <td class="num"><strong>{m_tot}</strong> <span class="muted">(halo {m_org})</span></td>
              <td class="num">{halo_acos}</td>
              <td class="num">{theta_str}</td>
              <td class="num">{mape_str}</td>
            </tr>
            """
        )

    backtest_kpi_val = f"{avg_backtest_mape:.1f}% MAPE" if avg_backtest_mape is not None else "N/A (<5w)"
    tier_badge = "PRO CYTHON ENGINE" if pro_enabled else "OPEN-CORE DIAGNOSTIC"

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Amazon Paid-to-Organic Flywheel Audit — {safe_client}</title>
  <style>
    :root {{
      --bg: #f8fafc;
      --surface: #ffffff;
      --ink: #0f172a;
      --muted: #64748b;
      --border: #e2e8f0;
      --accent: #2563eb;
      --rent: #dc2626;
      --flywheel: #16a34a;
      --treadmill: #d97706;
      --decay: #7c3aed;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, sans-serif;
      background: var(--bg);
      color: var(--ink);
      line-height: 1.5;
    }}
    .container {{
      max-width: 1220px;
      margin: 0 auto;
      padding: 32px 24px 64px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      padding-bottom: 20px;
      border-bottom: 2px solid var(--border);
      margin-bottom: 24px;
    }}
    .brand-block {{
      display: flex;
      align-items: center;
      gap: 14px;
    }}
    .brand-logo {{
      height: 44px;
      max-width: 160px;
      object-fit: contain;
    }}
    .brand-monogram {{
      width: 44px;
      height: 44px;
      border-radius: 10px;
      background: linear-gradient(135deg, #1d4ed8, #0f172a);
      color: #fff;
      font-weight: 800;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 16px;
      letter-spacing: 0.04em;
    }}
    h1 {{ margin: 0; font-size: 22px; letter-spacing: -0.02em; }}
    h2 {{ margin: 0 0 12px; font-size: 16px; letter-spacing: -0.01em; }}
    .subtitle {{ color: var(--muted); font-size: 13px; margin-top: 2px; }}
    .meta-right {{ text-align: right; font-size: 12px; color: var(--muted); }}
    .tier-tag {{
      display: inline-block;
      background: #eff6ff;
      color: #1d4ed8;
      border: 1px solid #bfdbfe;
      border-radius: 999px;
      padding: 2px 10px;
      font-size: 11px;
      font-weight: 700;
      margin-bottom: 4px;
    }}
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 16px;
      margin-bottom: 20px;
    }}
    .kpi {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 18px 20px;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }}
    .kpi-label {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--muted);
      font-weight: 700;
    }}
    .kpi-value {{
      font-size: 26px;
      font-weight: 800;
      margin-top: 6px;
      letter-spacing: -0.02em;
    }}
    .kpi-sub {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}
    .kpi-danger .kpi-value {{ color: var(--rent); }}
    .kpi-success .kpi-value {{ color: var(--flywheel); }}
    .pills {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; }}
    .pill {{
      font-size: 12px;
      padding: 5px 12px;
      border-radius: 999px;
      background: var(--surface);
      border: 1px solid var(--border);
    }}
    .charts-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
      margin-bottom: 20px;
    }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 20px;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }}
    .alert-card {{
      background: #fffbeb;
      border-color: #fde68a;
    }}
    .alert-card h2 {{ color: #92400e; }}
    .alert-card ul {{ margin: 0; padding-left: 18px; font-size: 13px; color: #78350f; }}
    .chart-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 10px;
    }}
    select {{
      padding: 6px 10px;
      border-radius: 8px;
      border: 1px solid var(--border);
      font-size: 13px;
      background: #fff;
      color: var(--ink);
    }}
    svg {{ width: 100%; height: 290px; display: block; }}
    .tooltip {{
      position: fixed;
      pointer-events: none;
      background: rgba(15, 23, 42, 0.94);
      color: #fff;
      padding: 8px 11px;
      border-radius: 8px;
      font-size: 12px;
      z-index: 999;
      display: none;
      max-width: 280px;
      box-shadow: 0 8px 20px rgba(0,0,0,0.2);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12.5px;
    }}
    th, td {{
      padding: 10px 8px;
      border-bottom: 1px solid var(--border);
      text-align: left;
    }}
    th {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--muted);
      background: #f8fafc;
    }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .muted {{ color: var(--muted); font-size: 11px; }}
    .pos {{ color: var(--flywheel); font-weight: 700; }}
    .neg {{ color: var(--rent); font-weight: 700; }}
    .badge {{
      display: inline-block;
      font-size: 10.5px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 6px;
      white-space: nowrap;
    }}
    .badge-cannibalized_rent {{ background: #fee2e2; color: #b91c1c; }}
    .badge-flywheel_leverage {{ background: #dcfce7; color: #15803d; }}
    .badge-treadmill_dead_weight {{ background: #fef3c7; color: #b45309; }}
    .badge-at_risk_decay {{ background: #ede9fe; color: #6d28d9; }}
    .badge-insufficient_data {{ background: #f1f5f9; color: #475569; }}
    footer {{
      text-align: center;
      font-size: 12px;
      color: var(--muted);
      margin-top: 28px;
    }}
    @media (max-width: 960px) {{
      .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
      .charts-grid {{ grid-template-columns: 1fr; }}
    }}
    @media print {{
      body {{ background: #fff; }}
      .container {{ padding: 0; max-width: 100%; }}
      .card, .kpi {{ box-shadow: none; break-inside: avoid; }}
      select {{ border: none; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand-block">
        {logo_html}
        <div>
          <h1>Paid-to-Organic Search Flywheel Audit</h1>
          <div class="subtitle">Prepared by <strong>{safe_agency}</strong> for <strong>{safe_client}</strong> &middot; ASIN <code>{html.escape(asin)}</code> &middot; Category: {html.escape(category)} &middot; Margin: {margin * 100:.1f}%</div>
        </div>
      </div>
      <div class="meta-right">
        <div class="tier-tag">{tier_badge}</div><br />
        Generated {report_date} &middot; 100% Local Zero-OAuth Audit
      </div>
    </header>

    <section class="kpi-grid">
      <div class="kpi kpi-danger">
        <div class="kpi-label">Monthly Wasted Spend</div>
        <div class="kpi-value">${monthly_wasted_spend:,.0f}/mo</div>
        <div class="kpi-sub">In Cannibalized Rent &amp; Dead Weight (${weekly_wasted_spend:,.0f}/wk)</div>
      </div>
      <div class="kpi kpi-success">
        <div class="kpi-label">Projected Annual Profit Lift</div>
        <div class="kpi-value">+${annual_profit_lift:,.0f}/yr</div>
        <div class="kpi-sub">+${weekly_profit_lift:,.2f}/wk via KKT Equimarginal Reallocation (0% extra spend)</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Portfolio Shadow Price (&mu;*)</div>
        <div class="kpi-value">{shadow_price:.2f}x mROAS</div>
        <div class="kpi-sub">Break-Even Target: {break_even_roas:.2f}x ({margin * 100:.0f}% margin)</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Walk-Forward Backtest Error</div>
        <div class="kpi-value">{backtest_kpi_val}</div>
        <div class="kpi-sub">Out-of-sample organic rank validation across {len(keywords)} keywords</div>
      </div>
    </section>

    <div class="pills">{quad_badges_html}</div>

    {warnings_html}

    {ops_health_html}

    {funnel_html}

    <section class="charts-grid">
      <div class="card">
        <div class="chart-header">
          <h2>4-Quadrant Flywheel Matrix (Organic Rank vs. Marginal Total ROAS)</h2>
        </div>
        <svg id="quadrant-chart" viewBox="0 0 540 290"></svg>
        <div class="muted">Bubble size = weekly ad spend. Dashed horizontal line = Break-Even ROAS ({break_even_roas:.2f}x). Hover points for details.</div>
      </div>

      <div class="card">
        <div class="chart-header">
          <h2>Marginal Response Curve Explorer</h2>
          <select id="curve-select"></select>
        </div>
        <svg id="curve-chart" viewBox="0 0 540 290"></svg>
        <div class="muted" id="curve-caption">Solid blue = Marginal Total ROAS (Paid + 21d Organic Halo). Dashed amber = Break-Even ROAS.</div>
      </div>
    </section>

    <section class="card">
      <h2>Keyword Econometrics &amp; KKT Equimarginal Budget Reallocation</h2>
      <div style="overflow-x: auto;">
        <table>
          <thead>
            <tr>
              <th>Search Query</th>
              <th>Quadrant</th>
              <th class="num">Org Rank</th>
              <th class="num">Curr / Wk</th>
              <th class="num">KKT Alloc</th>
              <th class="num">Delta</th>
              <th class="num">Avg ROAS</th>
              <th class="num">Marg Total ROAS</th>
              <th class="num">Halo ACoS*</th>
              <th class="num">&theta; EB [90% CI]</th>
              <th class="num">Backtest MAPE</th>
            </tr>
          </thead>
          <tbody>
            {''.join(table_rows_html)}
          </tbody>
        </table>
      </div>
    </section>

    <footer>
      Generated locally with <strong>amz-adlift</strong> &middot; Print this page (Ctrl/Cmd + P) to save as a client-ready PDF deck.
    </footer>
  </div>

  <div id="tooltip" class="tooltip"></div>

  <script>
    const DATA = {payload_json};
    const COLORS = {{
      CANNIBALIZED_RENT: "#dc2626",
      FLYWHEEL_LEVERAGE: "#16a34a",
      TREADMILL_DEAD_WEIGHT: "#d97706",
      AT_RISK_DECAY: "#7c3aed",
      INSUFFICIENT_DATA: "#64748b"
    }};
    const tip = document.getElementById("tooltip");

    function showTip(evt, htmlText) {{
      tip.innerHTML = htmlText;
      tip.style.display = "block";
      tip.style.left = (evt.clientX + 12) + "px";
      tip.style.top = (evt.clientY - 12) + "px";
    }}
    function hideTip() {{ tip.style.display = "none"; }}

    function svgEl(tag, attrs) {{
      const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
      for (const [k, v] of Object.entries(attrs || {{}})) el.setAttribute(k, v);
      return el;
    }}

    function renderQuadrantChart() {{
      const svg = document.getElementById("quadrant-chart");
      svg.innerHTML = "";
      const W = 540, H = 290, padL = 48, padR = 20, padT = 18, padB = 38;
      const plotW = W - padL - padR, plotH = H - padT - padB;
      const rows = DATA.rows.filter(r => r.rank !== null);
      const maxRank = Math.max(25, ...rows.map(r => Math.min(60, r.rank || 10)));
      const maxMroas = Math.max(DATA.breakEvenRoas * 1.35, 3.5, ...rows.map(r => r.marginal_total_roas || 0));
      const maxSpend = Math.max(50, ...rows.map(r => r.weekly_spend || 10));

      const xScale = r => padL + ((Math.min(60, r) - 1) / Math.max(1, maxRank - 1)) * plotW;
      const yScale = y => padT + plotH - (Math.min(maxMroas, Math.max(0, y)) / maxMroas) * plotH;

      // Grid & axes
      svg.appendChild(svgEl("line", {{ x1: padL, y1: padT + plotH, x2: W - padR, y2: padT + plotH, stroke: "#cbd5e1" }}));
      svg.appendChild(svgEl("line", {{ x1: padL, y1: padT, x2: padL, y2: padT + plotH, stroke: "#cbd5e1" }}));

      // Break-even horizontal dashed line
      const beY = yScale(DATA.breakEvenRoas);
      svg.appendChild(svgEl("line", {{
        x1: padL, y1: beY, x2: W - padR, y2: beY,
        stroke: "#d97706", "stroke-dasharray": "5,4", "stroke-width": "1.5"
      }}));
      const beTxt = svgEl("text", {{ x: W - padR - 4, y: beY - 5, "text-anchor": "end", fill: "#b45309", "font-size": "10" }});
      beTxt.textContent = "Break-Even " + DATA.breakEvenRoas.toFixed(2) + "x";
      svg.appendChild(beTxt);

      // Axis labels
      const xl = svgEl("text", {{ x: padL + plotW / 2, y: H - 8, "text-anchor": "middle", fill: "#64748b", "font-size": "11" }});
      xl.textContent = "Organic Rank (#1 Best \u2192 #60 Worst)";
      svg.appendChild(xl);

      const yl = svgEl("text", {{
        x: 14, y: padT + plotH / 2, "text-anchor": "middle", fill: "#64748b", "font-size": "11",
        transform: `rotate(-90 14 ${{padT + plotH / 2}})`
      }});
      yl.textContent = "Marginal Total ROAS";
      svg.appendChild(yl);

      rows.forEach(r => {{
        const cx = xScale(r.rank);
        const cy = yScale(r.marginal_total_roas || 0);
        const rad = 6 + Math.sqrt((r.weekly_spend || 10) / maxSpend) * 14;
        const c = svgEl("circle", {{
          cx, cy, r: rad,
          fill: COLORS[r.quadrant] || "#64748b",
          "fill-opacity": "0.78",
          stroke: "#ffffff",
          "stroke-width": "1.8",
          style: "cursor:pointer"
        }});
        c.addEventListener("mousemove", evt => {{
          showTip(evt,
            `<strong>${{r.search_query}}</strong><br/>` +
            `Quadrant: ${{r.quadrant}}<br/>` +
            `Organic Rank: #${{r.rank}}<br/>` +
            `Weekly Spend: $${{r.weekly_spend.toFixed(2)}}<br/>` +
            `Avg Paid ROAS: ${{r.avg_paid_roas ?? "—"}}x<br/>` +
            `Marginal Total ROAS: <strong>${{r.marginal_total_roas ?? "—"}}x</strong>`
          );
        }});
        c.addEventListener("mouseleave", hideTip);
        svg.appendChild(c);
      }});
    }}

    function renderCurve(row) {{
      const svg = document.getElementById("curve-chart");
      svg.innerHTML = "";
      const pts = (row && row.response_curve) || [];
      if (!pts.length) {{
        const t = svgEl("text", {{ x: 270, y: 145, "text-anchor": "middle", fill: "#64748b", "font-size": "13" }});
        t.textContent = "Activate amz_adlift_pro to plot Marginal Response Curves";
        svg.appendChild(t);
        return;
      }}
      const W = 540, H = 290, padL = 48, padR = 20, padT = 18, padB = 38;
      const plotW = W - padL - padR, plotH = H - padT - padB;
      const maxSpend = Math.max(...pts.map(p => p.weekly_spend), 10);
      const maxY = Math.max(DATA.breakEvenRoas * 1.3, ...pts.map(p => p.marginal_total_roas), 2.5);

      const xScale = s => padL + (s / maxSpend) * plotW;
      const yScale = y => padT + plotH - (Math.min(maxY, Math.max(0, y)) / maxY) * plotH;

      svg.appendChild(svgEl("line", {{ x1: padL, y1: padT + plotH, x2: W - padR, y2: padT + plotH, stroke: "#cbd5e1" }}));
      svg.appendChild(svgEl("line", {{ x1: padL, y1: padT, x2: padL, y2: padT + plotH, stroke: "#cbd5e1" }}));

      const beY = yScale(DATA.breakEvenRoas);
      svg.appendChild(svgEl("line", {{
        x1: padL, y1: beY, x2: W - padR, y2: beY,
        stroke: "#d97706", "stroke-dasharray": "5,4", "stroke-width": "1.5"
      }}));

      const totalPath = pts.map((p, i) => `${{i ? "L" : "M"}} ${{xScale(p.weekly_spend)}} ${{yScale(p.marginal_total_roas)}}`).join(" ");
      const paidPath = pts.map((p, i) => `${{i ? "L" : "M"}} ${{xScale(p.weekly_spend)}} ${{yScale(p.marginal_paid_roas)}}`).join(" ");
      svg.appendChild(svgEl("path", {{ d: paidPath, fill: "none", stroke: "#94a3b8", "stroke-width": "2", "stroke-dasharray": "3,3" }}));
      svg.appendChild(svgEl("path", {{ d: totalPath, fill: "none", stroke: "#2563eb", "stroke-width": "2.6" }}));

      pts.forEach(p => {{
        const dot = svgEl("circle", {{
          cx: xScale(p.weekly_spend), cy: yScale(p.marginal_total_roas), r: p.spend_multiplier === 1.0 ? 5.5 : 3.8,
          fill: p.spend_multiplier === 1.0 ? "#0f172a" : "#2563eb", stroke: "#fff", "stroke-width": "1.5", style: "cursor:pointer"
        }});
        dot.addEventListener("mousemove", evt => {{
          showTip(evt,
            `<strong>$${{p.weekly_spend.toFixed(2)}}/wk (${{Math.round(p.spend_multiplier*100)}}%)</strong><br/>` +
            `Marginal Total ROAS: <strong>${{p.marginal_total_roas}}x</strong><br/>` +
            `Marginal Paid: ${{p.marginal_paid_roas}}x &middot; Organic Halo: ${{p.marginal_organic_roas}}x<br/>` +
            `Projected Organic Rank: #${{p.expected_organic_rank}}`
          );
        }});
        dot.addEventListener("mouseleave", hideTip);
        svg.appendChild(dot);
      }});

      const xl = svgEl("text", {{ x: padL + plotW / 2, y: H - 8, "text-anchor": "middle", fill: "#64748b", "font-size": "11" }});
      xl.textContent = "Weekly PPC Spend ($)";
      svg.appendChild(xl);

      document.getElementById("curve-caption").textContent =
        `Hill fit: ${{row.hill_fit_source}} | Solid blue = Marginal Total ROAS (Paid + Organic Halo) | Dashed gray = Marginal Paid ROAS | Black dot = Current Spend ($${{row.weekly_spend.toFixed(2)}}).`;
    }}

    const sel = document.getElementById("curve-select");
    DATA.rows.forEach((r, idx) => {{
      const opt = document.createElement("option");
      opt.value = idx;
      opt.textContent = `${{r.search_query}} (${{r.quadrant.replace(/_/g, " ")}})`;
      sel.appendChild(opt);
    }});
    sel.addEventListener("change", () => renderCurve(DATA.rows[Number(sel.value)]));

    renderQuadrantChart();
    if (DATA.rows.length) renderCurve(DATA.rows[0]);
  </script>
</body>
</html>
"""

    out.write_text(html_doc, encoding="utf-8")
    return {
        "output_path": str(out.resolve()),
        "agency_name": agency_name,
        "client_name": display_client,
        "keywords_rendered": len(enriched_rows),
        "monthly_wasted_spend": monthly_wasted_spend,
        "projected_annual_profit_lift": annual_profit_lift,
        "average_backtest_mape_pct": avg_backtest_mape,
    }
