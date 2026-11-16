import numpy as np
import pandas as pd
import logging
from typing import Dict, Any
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_error, root_mean_squared_error, r2_score
from app.core.config import settings
from app.ml.feature_engineering import FeatureEngineer, HISTORY_HOURS
from app.ml.models import (
    BaselinePersistenceModel,
    BaselineSeasonalNaiveModel,
    BaselineHourlyAverageModel,
    LightGBMDemandForecaster
)
from app.ml.tracking import experiment_tracker

logger = logging.getLogger(__name__)

def compute_mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = y_true > 0
    if not np.any(mask):
        return 0.0
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)

# Complete hours needed: HISTORY_HOURS are used up by the lag features, 12 remain to model.
MIN_TRAIN_HOURS = HISTORY_HOURS + 12


def to_citywide_hourly(df: pd.DataFrame, drop_incomplete: bool = True) -> pd.DataFrame:
    """Collapse per-zone hourly rows into one continuous city-wide hourly series.

    The gold table holds one row per (hour, zone). Lag and rolling features are only
    meaningful on a single evenly spaced series, so zones are summed per hour and
    missing hours are filled with zero demand. The newest bucket is dropped because
    it is usually still filling up during ingestion or replay.
    """
    if df.empty:
        return pd.DataFrame(columns=["time_bucket", "trip_count"])
    buckets = pd.to_datetime(df["time_bucket"])
    series = df["trip_count"].groupby(buckets).sum().sort_index()
    series = series.asfreq("h", fill_value=0)
    if drop_incomplete and len(series) > 1:
        series = series.iloc[:-1]
    out = series.rename("trip_count").astype(float).reset_index()
    out.columns = ["time_bucket", "trip_count"]
    return out


def forecast_citywide(df: pd.DataFrame, horizon_hours: int) -> Dict[str, Any]:
    """Recursive multi-step forecast from the saved LightGBM model.

    Each predicted hour is appended to the series, so the lag and rolling features
    of the following step are built from earlier predictions, never from future data.
    """
    series = to_citywide_hourly(df)
    if len(series) < MIN_TRAIN_HOURS:
        raise ValueError(
            f"At least {MIN_TRAIN_HOURS} complete hours of demand are required to forecast "
            f"(have {len(series)})."
        )
    model = LightGBMDemandForecaster()
    model.load(settings.MODEL_DIR / "lightgbm_demand_forecaster.joblib")

    profile = BaselineHourlyAverageModel()
    profile.fit(series, target_col="trip_count")

    work = series.copy()
    steps = []
    for _ in range(horizon_hours):
        next_time = work["time_bucket"].iloc[-1] + pd.Timedelta(hours=1)
        work = pd.concat(
            [work, pd.DataFrame({"time_bucket": [next_time], "trip_count": [0.0]})],
            ignore_index=True,
        )
        feats, _cols = FeatureEngineer.create_features(work, target_col="trip_count")
        pred = float(model.predict(feats.tail(1))[0])
        work.loc[work.index[-1], "trip_count"] = pred
        baseline = float(profile.predict(work.tail(1))[0])
        steps.append({"timestamp": next_time.to_pydatetime(), "predicted": pred, "baseline": baseline})

    history = [
        {"timestamp": row.time_bucket.to_pydatetime(), "actual": float(row.trip_count)}
        for row in series.tail(48).itertuples()
    ]
    return {"steps": steps, "history": history}


def train_and_evaluate(df_hourly: pd.DataFrame) -> Dict[str, Any]:
    """Train forecasting models using time-aware walk-forward validation (zero future leakage)."""
    df_hourly = to_citywide_hourly(df_hourly)
    if len(df_hourly) < MIN_TRAIN_HOURS:
        raise ValueError(
            f"At least {MIN_TRAIN_HOURS} complete hours of demand are required for training "
            f"(have {len(df_hourly)})."
        )

    # 1. Feature Engineering
    df_feat, feature_cols = FeatureEngineer.create_features(df_hourly, target_col="trip_count")
    
    # 2. Time-Aware Split (Walk-Forward Validation)
    # Using TimeSeriesSplit to strictly prevent future-data leakage
    tscv = TimeSeriesSplit(n_splits=3)
    
    models = {
        "Baseline_Persistence": BaselinePersistenceModel(),
        "Baseline_Seasonal_Naive": BaselineSeasonalNaiveModel(),
        "Baseline_Hourly_Avg": BaselineHourlyAverageModel(),
        "LightGBM_Forecaster": LightGBMDemandForecaster()
    }

    results = {name: {"mae": [], "rmse": [], "mape": [], "r2": []} for name in models}
    folds = []
    # Every test hour with each model's prediction, pooled over the folds for paired comparisons.
    test_predictions = {"time_bucket": [], "actual": [], **{name: [] for name in models}}

    for fold, (train_idx, test_idx) in enumerate(tscv.split(df_feat)):
        train_df = df_feat.iloc[train_idx]
        test_df = df_feat.iloc[test_idx]

        y_train = train_df["trip_count"].values
        y_test = test_df["trip_count"].values
        folds.append({
            "fold": fold + 1,
            "train_start": str(train_df["time_bucket"].min()), "train_end": str(train_df["time_bucket"].max()),
            "test_start": str(test_df["time_bucket"].min()), "test_end": str(test_df["time_bucket"].max()),
            "train_hours": len(train_df), "test_hours": len(test_df),
        })

        models["Baseline_Hourly_Avg"].fit(train_df, target_col="trip_count")
        models["LightGBM_Forecaster"].fit(train_df, y_train, feature_cols)

        test_predictions["time_bucket"] += [str(t) for t in test_df["time_bucket"]]
        test_predictions["actual"] += [float(v) for v in y_test]
        for name, model in models.items():
            pred = model.predict(test_df)
            test_predictions[name] += [float(v) for v in pred]
            results[name]["mae"].append(mean_absolute_error(y_test, pred))
            results[name]["rmse"].append(root_mean_squared_error(y_test, pred))
            results[name]["mape"].append(compute_mape(y_test, pred))
            results[name]["r2"].append(r2_score(y_test, pred))

    # Summary of metrics across folds
    metrics_summary = []
    for name, m in results.items():
        metrics_summary.append({
            "model_name": name,
            "mae": round(float(np.mean(m["mae"])), 2),
            "rmse": round(float(np.mean(m["rmse"])), 2),
            "mape": round(float(np.mean(m["mape"])), 2),
            "r2_score": round(float(np.mean(m["r2"])), 3),
            "validation_method": "TimeSeriesSplit (3-Fold Walk-Forward, No Leakage)",
            "train_samples": len(train_idx),
            "test_samples": len(test_idx)
        })

    # Train final production model on full dataset
    final_model = LightGBMDemandForecaster()
    final_model.fit(df_feat, df_feat["trip_count"].values, feature_cols)
    model_path = settings.MODEL_DIR / "lightgbm_demand_forecaster.joblib"
    final_model.save(model_path)

    feature_importances = final_model.get_feature_importances()

    # Log to experiment tracker
    lgb_metrics = next(m for m in metrics_summary if m["model_name"] == "LightGBM_Forecaster")
    best_model = min(metrics_summary, key=lambda m: m["mae"])["model_name"]
    experiment_tracker.log_experiment(
        model_name="LightGBM_Forecaster",
        params={
            "n_estimators": 150,
            "learning_rate": 0.05,
            "max_depth": 6,
            "features_count": len(feature_cols)
        },
        metrics=lgb_metrics,
        artifacts={"model_file": model_path.name},
        dataset_info={"total_records": len(df_feat), "start_date": str(df_feat["time_bucket"].min()), "end_date": str(df_feat["time_bucket"].max())},
        extra={"all_metrics": metrics_summary, "best_model": best_model}
    )

    for i, f in enumerate(folds):
        f["mae"] = {name: round(float(m["mae"][i]), 2) for name, m in results.items()}

    return {
        "metrics": metrics_summary,
        "best_model": best_model,
        "folds": folds,
        "hours_used": len(df_feat),
        "hours_dropped_for_history": len(df_hourly) - len(df_feat),
        "test_predictions": test_predictions,
        "feature_importances": feature_importances,
        "model_path": str(model_path)
    }

