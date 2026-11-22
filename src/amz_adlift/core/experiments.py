"""
Geo-Incrementality Power Analysis (MDE / SNR), Counterfactual Estimators
(Synthetic Control & Trimmed Match), and Meridian-Style Bayesian Prior Calibration
(core/experiments.py).

Pure-Python implementations requiring zero external numerical dependencies.
"""

from __future__ import annotations

import math
import statistics
from typing import Optional, Sequence

from pydantic import BaseModel, Field


class MDEPowerResult(BaseModel):
    """Pre-test Minimum Detectable Effect (MDE) and Signal-to-Noise Ratio gate."""

    baseline_mean: float
    baseline_std: float
    baseline_cv: float
    mde_absolute: float
    mde_relative_pct: float
    expected_lift_pct: float
    signal_to_noise_ratio: float
    power_adequate: bool
    recommendation: str


class SyntheticControlResult(BaseModel):
    """Counterfactual Synthetic Control (SCM) geo/market lift estimate."""

    donor_weights: dict[str, float]
    excluded_buffer_donors: list[str]
    pre_period_rmse: float
    pre_period_r2: float
    in_time_placebo_bias_pct: Optional[float] = None
    treated_post_total: float
    counterfactual_post_total: float
    incremental_revenue: float
    incremental_spend: float
    iroas: float
    lift_pct: float


class TrimmedMatchResult(BaseModel):
    """Non-parametric Trimmed Match Design (TMD) iROAS estimator."""

    iroas: float
    iroas_se: float
    ci_90_low: float
    ci_90_high: float
    pairs_total: int
    pairs_retained: int
    trim_fraction: float


class CalibratedCausalPrior(BaseModel):
    """Meridian CalibrationBuilder-style variance-inflated Bayesian causal prior."""

    raw_iroas_mean: float
    raw_iroas_sd: float
    prior_mean: float
    prior_sd: float
    variance_inflation_factor: float
    recency_decay_factor: float
    effective_weight: float


def _norm_ppf(p: float) -> float:
    """Acklam's rational approximation for the standard normal inverse CDF."""
    if p <= 0.0 or p >= 1.0:
        raise ValueError("p must be strictly in (0, 1).")
    a = (
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    )
    b = (
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    )
    c = (
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    )
    d = (
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    )
    plow = 0.02425
    phigh = 1.0 - plow
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
            * q
            / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
        )
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
    )


def compute_experiment_mde(
    baseline_series: Sequence[float],
    expected_lift_pct: float,
    *,
    power: float = 0.80,
    alpha: float = 0.10,
    duration_periods: int = 4,
    variance_reduction_factor: float = 0.65,
) -> MDEPowerResult:
    """
    Pre-test power gate: computes Minimum Detectable Effect (MDE) and Signal-to-Noise
    Ratio (SNR) from historical sales volatility.

    variance_reduction_factor (default 0.65) reflects baseline residual variance
    reduction achieved by Synthetic Control / Trimmed Match vs. naive DiD (1.0).
    """
    vals = [float(x) for x in baseline_series]
    if len(vals) < 4:
        raise ValueError("baseline_series must contain at least 4 historical periods.")
    mean_v = statistics.fmean(vals)
    if mean_v <= 0.0:
        raise ValueError("baseline_series mean must be positive.")
    std_v = statistics.stdev(vals)
    cv = std_v / mean_v

    z_alpha = _norm_ppf(1.0 - alpha / 2.0)
    z_beta = _norm_ppf(power)
    eff_std = std_v * math.sqrt(max(0.05, min(1.0, variance_reduction_factor)))
    se_mean = eff_std * math.sqrt(2.0 / max(1, duration_periods))
    mde_abs = (z_alpha + z_beta) * se_mean
    mde_rel = mde_abs / mean_v
    snr = (expected_lift_pct * mean_v) / max(1e-9, se_mean)
    adequate = mde_rel <= expected_lift_pct

    if adequate:
        rec = (
            f"POWERED: MDE ({mde_rel:.1%}) <= expected lift ({expected_lift_pct:.1%}) "
            f"over {duration_periods} periods (SNR={snr:.2f}). Proceed with test."
        )
    else:
        rec = (
            f"UNDERPOWERED: MDE ({mde_rel:.1%}) > expected lift ({expected_lift_pct:.1%}). "
            "Extend test duration, increase treatment spend intensity, or apply SCM/TMD "
            "variance reduction before launching."
        )

    return MDEPowerResult(
        baseline_mean=round(mean_v, 2),
        baseline_std=round(std_v, 2),
        baseline_cv=round(cv, 4),
        mde_absolute=round(mde_abs, 2),
        mde_relative_pct=round(mde_rel, 4),
        expected_lift_pct=round(expected_lift_pct, 4),
        signal_to_noise_ratio=round(snr, 3),
        power_adequate=adequate,
        recommendation=rec,
    )


def _project_simplex(v: list[float]) -> list[float]:
    """Euclidean projection onto the probability simplex {w >= 0, sum(w) = 1}."""
    n = len(v)
    u = sorted(v, reverse=True)
    cssv = 0.0
    rho = -1
    for i, val in enumerate(u):
        cssv += val
        t = (cssv - 1.0) / (i + 1)
        if val - t > 0:
            rho = i
    theta = (sum(u[: rho + 1]) - 1.0) / (rho + 1)
    return [max(0.0, x - theta) for x in v]


def estimate_synthetic_control(
    treated_pre: Sequence[float],
    treated_post: Sequence[float],
    donor_pre: dict[str, Sequence[float]],
    donor_post: dict[str, Sequence[float]],
    incremental_spend: float,
    *,
    buffer_excluded_donors: Optional[Sequence[str]] = None,
    max_iter: int = 800,
) -> SyntheticControlResult:
    """
    Synthetic Control Method (SCM) with non-negative donor weights summing to 1.
    Supports SUTVA buffer-zone exclusion of adjacent/contaminated donor regions.
    """
    if incremental_spend <= 0.0:
        raise ValueError("incremental_spend must be positive.")
    excluded = set(buffer_excluded_donors or [])
    donor_names = [k for k in donor_pre if k not in excluded and k in donor_post]
    if not donor_names:
        raise ValueError("No eligible donor markets remain after buffer exclusion.")

    t_pre = [float(x) for x in treated_pre]
    t_post = [float(x) for x in treated_post]
    n_pre = len(t_pre)
    n_post = len(t_post)
    if n_pre < 3 or n_post < 1:
        raise ValueError("Need at least 3 pre-periods and 1 post-period.")

    d_pre = [[float(x) for x in donor_pre[k][:n_pre]] for k in donor_names]
    d_post = [[float(x) for x in donor_post[k][:n_post]] for k in donor_names]
    m = len(donor_names)

    # Normalize scale for stable projected gradient descent
    scale = max(1.0, max(abs(x) for x in t_pre))
    y = [x / scale for x in t_pre]
    X = [[val / scale for val in row] for row in d_pre]

    w = [1.0 / m] * m
    lr = 0.25
    for step in range(max_iter):
        # Residuals r_t = sum_j w_j X_{j,t} - y_t
        res = [sum(w[j] * X[j][t] for j in range(m)) - y[t] for t in range(n_pre)]
        grad = [
            (2.0 / n_pre) * sum(res[t] * X[j][t] for t in range(n_pre))
            for j in range(m)
        ]
        step_lr = lr / (1.0 + 0.002 * step)
        w = _project_simplex([w[j] - step_lr * grad[j] for j in range(m)])

    pred_pre = [sum(w[j] * d_pre[j][t] for j in range(m)) for t in range(n_pre)]
    pred_post = [sum(w[j] * d_post[j][t] for j in range(m)) for t in range(n_post)]

    sq_err = sum((t_pre[t] - pred_pre[t]) ** 2 for t in range(n_pre))
    rmse = math.sqrt(sq_err / n_pre)
    y_bar = statistics.fmean(t_pre)
    ss_tot = sum((x - y_bar) ** 2 for x in t_pre)
    r2 = 1.0 - (sq_err / ss_tot) if ss_tot > 1e-9 else 1.0

    # Simple in-time placebo bias on the last pre-period
    placebo_bias_pct: Optional[float] = None
    if t_pre[-1] > 0.0:
        placebo_bias_pct = round((t_pre[-1] - pred_pre[-1]) / t_pre[-1], 4)

    treated_total = sum(t_post)
    cf_total = sum(pred_post)
    inc_rev = treated_total - cf_total
    iroas = inc_rev / incremental_spend
    lift_pct = inc_rev / max(1e-9, cf_total)

    return SyntheticControlResult(
        donor_weights={donor_names[j]: round(w[j], 4) for j in range(m)},
        excluded_buffer_donors=sorted(excluded),
        pre_period_rmse=round(rmse, 3),
        pre_period_r2=round(r2, 4),
        in_time_placebo_bias_pct=placebo_bias_pct,
        treated_post_total=round(treated_total, 2),
        counterfactual_post_total=round(cf_total, 2),
        incremental_revenue=round(inc_rev, 2),
        incremental_spend=round(incremental_spend, 2),
        iroas=round(iroas, 4),
        lift_pct=round(lift_pct, 4),
    )


def estimate_trimmed_match(
    pair_revenue_deltas: Sequence[float],
    pair_spend_deltas: Sequence[float],
    *,
    trim_fraction: float = 0.15,
) -> TrimmedMatchResult:
    """
    Non-parametric Trimmed Match Design (TMD) estimator (Chen & Au):
    Finds iROAS theta where the symmetric trimmed mean of residuals (r_i - theta * s_i) = 0.
    """
    if len(pair_revenue_deltas) != len(pair_spend_deltas) or len(pair_revenue_deltas) < 4:
        raise ValueError("Need equal-length pair deltas with at least 4 matched pairs.")
    r = [float(x) for x in pair_revenue_deltas]
    s = [float(x) for x in pair_spend_deltas]
    n = len(r)
    k = int(math.floor(n * max(0.0, min(0.4, trim_fraction))))
    retained = n - 2 * k

    def _trimmed_mean(theta: float) -> float:
        res = sorted(r[i] - theta * s[i] for i in range(n))
        core = res[k : n - k] if k > 0 else res
        return statistics.fmean(core)

    # Bisection root-finding on monotonically decreasing trimmed mean (when s_i > 0)
    lo, hi = -20.0, 50.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if _trimmed_mean(mid) > 0.0:
            lo = mid
        else:
            hi = mid
    theta_hat = 0.5 * (lo + hi)

    # Winsorized / trimmed residual standard error for iROAS
    residuals = sorted(r[i] - theta_hat * s[i] for i in range(n))
    core_res = residuals[k : n - k] if k > 0 else residuals
    res_sd = statistics.stdev(core_res) if len(core_res) >= 2 else 0.0
    mean_s = max(1e-9, statistics.fmean(abs(x) for x in s))
    se_theta = res_sd / (mean_s * math.sqrt(max(1, retained)))
    z90 = 1.64485

    return TrimmedMatchResult(
        iroas=round(theta_hat, 4),
        iroas_se=round(se_theta, 4),
        ci_90_low=round(theta_hat - z90 * se_theta, 4),
        ci_90_high=round(theta_hat + z90 * se_theta, 4),
        pairs_total=n,
        pairs_retained=retained,
        trim_fraction=round(trim_fraction, 3),
    )


def calibrate_causal_prior(
    iroas_mean: float,
    iroas_sd: float,
    *,
    experiment_age_days: int = 0,
    scope_mismatch_factor: float = 1.0,
    half_life_days: float = 180.0,
) -> CalibratedCausalPrior:
    """
    Meridian CalibrationBuilder-style prior adjustment: inflates experimental
    prior variance as the experiment ages or differs in spend scale from
    ongoing national/portfolio spend.
    """
    if iroas_sd <= 0.0:
        raise ValueError("iroas_sd must be positive.")
    age = max(0, int(experiment_age_days))
    scope = max(1.0, float(scope_mismatch_factor))
    decay = 0.5 ** (age / max(1.0, float(half_life_days)))
    vif = scope / max(0.10, decay)
    inflated_sd = iroas_sd * math.sqrt(vif)
    eff_weight = 1.0 / (1.0 + inflated_sd * inflated_sd)

    return CalibratedCausalPrior(
        raw_iroas_mean=round(iroas_mean, 4),
        raw_iroas_sd=round(iroas_sd, 4),
        prior_mean=round(iroas_mean, 4),
        prior_sd=round(inflated_sd, 4),
        variance_inflation_factor=round(vif, 4),
        recency_decay_factor=round(decay, 4),
        effective_weight=round(eff_weight, 4),
    )
