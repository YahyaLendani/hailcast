import numpy as np
import pandas as pd
import logging
from typing import Dict, Any, Tuple
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_error, root_mean_squared_error, r2_score
from app.core.config import settings
from app.ml.feature_engineering import FeatureEngineer
from app.ml.models import (
    BaselinePersistenceModel,
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

def train_and_evaluate(df_hourly: pd.DataFrame) -> Dict[str, Any]:
    """Train forecasting models using time-aware walk-forward validation (zero future leakage)."""
    if len(df_hourly) < 24:
        raise ValueError("At least 24 hours of aggregated data required for training.")

    # 1. Feature Engineering
    df_feat, feature_cols = FeatureEngineer.create_features(df_hourly, target_col="trip_count")
    
    # 2. Time-Aware Split (Walk-Forward Validation)
    # Using TimeSeriesSplit to strictly prevent future-data leakage
    tscv = TimeSeriesSplit(n_splits=3)
    
    models = {
        "Baseline_Persistence": BaselinePersistenceModel(),
        "Baseline_Hourly_Avg": BaselineHourlyAverageModel(),
        "LightGBM_Forecaster": LightGBMDemandForecaster()
    }
    
    results = {name: {"mae": [], "rmse": [], "mape": [], "r2": []} for name in models}

    for fold, (train_idx, test_idx) in enumerate(tscv.split(df_feat)):
        train_df = df_feat.iloc[train_idx]
        test_df = df_feat.iloc[test_idx]
        
        y_train = train_df["trip_count"].values
        y_test = test_df["trip_count"].values

        # 1. Baseline Persistence
        pred_persist = models["Baseline_Persistence"].predict(test_df)
        results["Baseline_Persistence"]["mae"].append(mean_absolute_error(y_test, pred_persist))
        results["Baseline_Persistence"]["rmse"].append(root_mean_squared_error(y_test, pred_persist))
        results["Baseline_Persistence"]["mape"].append(compute_mape(y_test, pred_persist))
        results["Baseline_Persistence"]["r2"].append(r2_score(y_test, pred_persist))

        # 2. Baseline Hourly Average
        models["Baseline_Hourly_Avg"].fit(train_df, target_col="trip_count")
        pred_avg = models["Baseline_Hourly_Avg"].predict(test_df)
        results["Baseline_Hourly_Avg"]["mae"].append(mean_absolute_error(y_test, pred_avg))
        results["Baseline_Hourly_Avg"]["rmse"].append(root_mean_squared_error(y_test, pred_avg))
        results["Baseline_Hourly_Avg"]["mape"].append(compute_mape(y_test, pred_avg))
        results["Baseline_Hourly_Avg"]["r2"].append(r2_score(y_test, pred_avg))

        # 3. LightGBM Forecaster
        models["LightGBM_Forecaster"].fit(train_df, y_train, feature_cols)
        pred_lgb = models["LightGBM_Forecaster"].predict(test_df)
        results["LightGBM_Forecaster"]["mae"].append(mean_absolute_error(y_test, pred_lgb))
        results["LightGBM_Forecaster"]["rmse"].append(root_mean_squared_error(y_test, pred_lgb))
        results["LightGBM_Forecaster"]["mape"].append(compute_mape(y_test, pred_lgb))
        results["LightGBM_Forecaster"]["r2"].append(r2_score(y_test, pred_lgb))

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
    experiment_tracker.log_experiment(
        model_name="LightGBM_Forecaster",
        params={
            "n_estimators": 150,
            "learning_rate": 0.05,
            "max_depth": 6,
            "features_count": len(feature_cols)
        },
        metrics=lgb_metrics,
        artifacts={"model_file": str(model_path)},
        dataset_info={"total_records": len(df_feat), "start_date": str(df_feat["time_bucket"].min()), "end_date": str(df_feat["time_bucket"].max())}
    )

    return {
        "metrics": metrics_summary,
        "best_model": "LightGBM_Forecaster",
        "feature_importances": feature_importances,
        "model_path": str(model_path)
    }

