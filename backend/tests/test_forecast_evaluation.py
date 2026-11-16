"""Baselines and the pre-registered comparison (docs/forecast_evaluation_preregistration.md)."""
import numpy as np
import pandas as pd
import pytest

from app.ml.compare import block_bootstrap_interval, compare_to_strongest_baseline
from app.ml.models import BaselineHourlyAverageModel, BaselineSeasonalNaiveModel


def test_hour_of_day_average_uses_the_hour_not_the_overall_mean():
    # Train on a Sunday, predict the Monday after: no (day of week, hour) pair is shared,
    # but every hour of the day is, so each prediction must be that hour's training mean.
    train = pd.DataFrame({"time_bucket": pd.date_range("2024-11-03", periods=24, freq="h"),
                          "trip_count": np.arange(24, dtype=float) * 10})
    test = pd.DataFrame({"time_bucket": pd.date_range("2024-11-04", periods=24, freq="h")})
    model = BaselineHourlyAverageModel()
    model.fit(train)
    np.testing.assert_array_equal(model.predict(test), train["trip_count"].values)


def test_same_hour_yesterday_predicts_lag_24h():
    df = pd.DataFrame({"lag_24h": [5.0, 7.0, 9.0]})
    np.testing.assert_array_equal(BaselineSeasonalNaiveModel().predict(df), [5.0, 7.0, 9.0])


def test_block_bootstrap_is_seeded_and_brackets_the_mean():
    d = np.random.default_rng(1).normal(2.0, 1.0, size=105)
    low, high = block_bootstrap_interval(d)
    assert (low, high) == block_bootstrap_interval(d)
    assert low < d.mean() < high
    assert block_bootstrap_interval(np.full(105, 3.0)) == pytest.approx((3.0, 3.0))


def _predictions(lgb_err, best_err, other_err=50.0, n=105):
    actual = np.full(n, 100.0)
    return {
        "actual": actual.tolist(),
        "LightGBM_Forecaster": (actual + lgb_err).tolist(),
        "Baseline_Seasonal_Naive": (actual + best_err).tolist(),
        "Baseline_Persistence": (actual + other_err).tolist(),
        "Baseline_Hourly_Avg": (actual - other_err).tolist(),
    }


def test_rule_picks_the_strongest_baseline_and_each_outcome():
    noise = np.random.default_rng(2).normal(0, 0.5, size=105)
    better = compare_to_strongest_baseline(_predictions(5.0 + noise, 10.0))
    assert better["comparator"] == "Baseline_Seasonal_Naive"
    assert better["outcome"] == "lightgbm_better"
    assert compare_to_strongest_baseline(_predictions(15.0 + noise, 10.0))["outcome"] == "baseline_better"
    centred = 4 * (noise - noise.mean())  # errors stay positive and average exactly 10
    tied = compare_to_strongest_baseline(_predictions(10.0 + centred, 10.0))
    assert tied["interval"][0] < 0 < tied["interval"][1]
    assert tied["outcome"] == "no_measurable_difference"
