"""Paired comparison of LightGBM against the strongest baseline, as pre-registered.

See docs/forecast_evaluation_preregistration.md. The rule is fixed there; this module
only computes it.
"""
from typing import Any, Dict

import numpy as np

BASELINES = ("Baseline_Persistence", "Baseline_Seasonal_Naive", "Baseline_Hourly_Avg")
CANDIDATE = "LightGBM_Forecaster"
BLOCK_HOURS = 24
RESAMPLES = 2000
SEED = 0


def block_bootstrap_interval(d: np.ndarray, block: int = BLOCK_HOURS, resamples: int = RESAMPLES,
                             seed: int = SEED, level: float = 0.95) -> tuple[float, float]:
    """Percentile interval for the mean of `d` from a moving block bootstrap.

    Each resample joins randomly chosen runs of `block` consecutive values until it is as long
    as `d`, so the correlation between neighbouring hours is kept inside each block.
    """
    d = np.asarray(d, dtype=float)
    n = len(d)
    if n == 0:
        raise ValueError("No values to resample.")
    block = min(block, n)
    starts_per_sample = -(-n // block)  # ceil(n / block)
    rng = np.random.default_rng(seed)
    means = np.empty(resamples)
    offsets = np.arange(block)
    for i in range(resamples):
        starts = rng.integers(0, n - block + 1, size=starts_per_sample)
        idx = (starts[:, None] + offsets).ravel()[:n]
        means[i] = d[idx].mean()
    tail = (1 - level) / 2 * 100
    low, high = np.percentile(means, [tail, 100 - tail])
    return float(low), float(high)


def compare_to_strongest_baseline(test_predictions: Dict[str, list]) -> Dict[str, Any]:
    """Apply the pre-registered decision rule to the pooled test hours."""
    actual = np.asarray(test_predictions["actual"], dtype=float)
    abs_err = {name: np.abs(np.asarray(test_predictions[name], dtype=float) - actual)
               for name in (*BASELINES, CANDIDATE)}
    pooled_mae = {name: float(err.mean()) for name, err in abs_err.items()}
    comparator = min(BASELINES, key=lambda name: pooled_mae[name])
    d = abs_err[CANDIDATE] - abs_err[comparator]
    low, high = block_bootstrap_interval(d)
    if high < 0:
        outcome = "lightgbm_better"
    elif low > 0:
        outcome = "baseline_better"
    else:
        outcome = "no_measurable_difference"
    return {
        "test_hours": int(len(actual)),
        "pooled_mae": pooled_mae,
        "comparator": comparator,
        "mean_difference": float(d.mean()),
        "interval": (low, high),
        "outcome": outcome,
    }
