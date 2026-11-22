"""Core open-source econometric decomposition and 4-quadrant diagnostics."""

from amz_adlift.core.decomposition import decompose_observation, decompose_panel
from amz_adlift.core.quadrants import (
    classify_keyword_series,
    classify_panel,
    compute_ols_slope,
    compute_pearson_corr,
)

__all__ = [
    "classify_keyword_series",
    "classify_panel",
    "compute_ols_slope",
    "compute_pearson_corr",
    "decompose_observation",
    "decompose_panel",
]
