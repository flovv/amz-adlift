# AGENTS.md — Coding & Autonomous Agent Instructions for `amz-flywheel`

This file provides repository context, conventions, and verification commands for AI coding agents (Claude Code, Cursor, Codex, Windsurf, Antigravity) working on `amz-flywheel` and `amz-flywheel-pro-private`.

## Repository Map

- **Public Open-Core Repo (`/home/antigravity/amz-flywheel`)**:
  - `src/amz_flywheel/contracts/`: Pydantic v2 models (`schemas.py`) and custom exceptions (`exceptions.py`).
  - `src/amz_flywheel/io/`: Local CSV parsers (`sqp_parser.py`, `ads_parser.py`, `rank_parser.py`) and panel joiner (`aligner.py`).
  - `src/amz_flywheel/core/`: Funnel decomposition (`decomposition.py`) and deterministic 4-quadrant classifier (`quadrants.py`).
  - `src/amz_flywheel/pro/`: Runtime dynamic bridge (`bridge.py`) and Polar.sh wheel installer (`installer.py`).
  - `src/amz_flywheel/mcp_server.py`: FastMCP server (`amz-flywheel-mcp`) exposing tools, resources, and prompts.
  - `src/amz_flywheel/cli.py`: Typer CLI (`amz-flywheel audit`, `amz-flywheel mcp`, `amz-flywheel auth install-pro`).
- **Private Pro Cython Repo (`/home/antigravity/amz-flywheel-pro-private`)**:
  - `setup.py`: Uses `StripSourceBuildPy` to compile `.pyx` extensions into `.so`/`.pyd` binaries and strip all `.py`/`.pyx`/`.c` source files except `amz_flywheel_pro/__init__.py`.
  - `src/amz_flywheel_pro/_auth.pyx`: Polar.sh license validation + 24-hour HMAC-SHA256 cache (`~/.amz_flywheel/license.cache`).
  - `src/amz_flywheel_pro/category_priors.pyx`: C-level category priors and Empirical Bayes shrinkage (`shrink_elasticity`).
  - `src/amz_flywheel_pro/flywheel_model.pyx`: Asymmetric Velocity-to-Rank Elasticity solver (`fit_keyword_elasticity`).
  - `src/amz_flywheel_pro/bid_optimizer.pyx`: 21-day counterfactual bid-cut simulator (`simulate_bid_cut`), Halo ACoS (`compute_halo_acos`), and Bulk Sheet `.xlsx` exporter (`generate_ads_bulksheet`).

## Build & Verification Commands

Always use the virtualenv at `/home/antigravity/.venv`:

```bash
# 1. Run all unit & integration tests on the public repo
/home/antigravity/.venv/bin/pytest -v /home/antigravity/amz-flywheel/tests

# 2. Rebuild the Cython Pro binary wheel and run the Wheel Security Audit
/home/antigravity/.venv/bin/python -m pip wheel --no-build-isolation --no-deps \
  -w /home/antigravity/amz-flywheel-pro-private/dist \
  /home/antigravity/amz-flywheel-pro-private
/home/antigravity/.venv/bin/pytest -v /home/antigravity/amz-flywheel-pro-private/tests
```

## Critical Invariants Never to Break

1. **Zero OAuth / 100% Local**: Never add external cloud telemetry or mandatory network calls during CSV parsing, funnel decomposition, or elasticity modeling.
2. **Sunday–Saturday Weekly Alignment**: Amazon SQP weeks always start on Sunday (`align_to_sunday` in `sqp_parser.py`). All Ads and Rank timestamps must align to the Sunday of their respective week.
3. **Non-Negativity Invariant**: `organic_clicks >= 0` and `organic_orders >= 0` must hold for every `UnifiedKeywordWeek` observation (`attribution_window_gap = (ad_orders > sqp_purchases)`).
4. **Wheel Source Stripping**: Any wheel built from `amz-flywheel-pro-private` must contain **zero** `.py`, `.pyx`, `.pxd`, or `.c` files other than `amz_flywheel_pro/__init__.py`.
