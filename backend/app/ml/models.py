import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from sklearn.metrics import mean_absolute_error, root_mean_squared_error, r2_score
from lightgbm import LGBMRegressor

class BaselinePersistenceModel:
    """Baseline Model 1: Naive Persistence (predicts demand = lag_1h)."""
    def __init__(self):
        self.name = "Baseline Persistence (Naive Lag-1)"

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return df["lag_1h"].values

class BaselineHourlyAverageModel:
    """Baseline Model 2: Historical Day-Hour Average Demand."""
    def __init__(self):
        self.name = "Baseline Hourly Average (Day/Hour Profile)"
        self.lookup_table: Dict[Tuple[int, int], float] = {}
        self.global_mean: float = 0.0

    def fit(self, df: pd.DataFrame, target_col: str = "trip_count"):
        self.global_mean = float(df[target_col].mean())
        df_copy = df.copy()
        df_copy["hour"] = df_copy["time_bucket"].dt.hour
        df_copy["dow"] = df_copy["time_bucket"].dt.dayofweek
        grouped = df_copy.groupby(["dow", "hour"])[target_col].mean()
        self.lookup_table = grouped.to_dict()

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        df_copy = df.copy()
        df_copy["hour"] = df_copy["time_bucket"].dt.hour
        df_copy["dow"] = df_copy["time_bucket"].dt.dayofweek
        preds = []
        for _, row in df_copy.iterrows():
            key = (int(row["dow"]), int(row["hour"]))
            preds.append(self.lookup_table.get(key, self.global_mean))
        return np.array(preds)

class LightGBMDemandForecaster:
    """Gradient-Boosted Decision Trees demand forecaster using LightGBM."""
    def __init__(self):
        self.name = "LightGBM Gradient Boosted Forecaster"
        self.model = LGBMRegressor(
            n_estimators=150,
            learning_rate=0.05,
            num_leaves=31,
            max_depth=6,
            min_child_samples=5,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbosity=-1
        )
        self.feature_cols: list[str] = []
        self.is_fitted: bool = False

    def fit(self, X: pd.DataFrame, y: np.ndarray, feature_cols: list[str]):
        self.feature_cols = feature_cols
        self.model.fit(X[feature_cols], y)
        self.is_fitted = True

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if not self.is_fitted:
            raise ValueError("Model is not fitted yet.")
        preds = self.model.predict(X[self.feature_cols])
        # Demand cannot be negative
        return np.clip(preds, a_min=0, a_max=None)

    def get_feature_importances(self) -> Dict[str, float]:
        if not self.is_fitted:
            return {}
        importances = self.model.feature_importances_
        total = np.sum(importances) or 1.0
        return {
            col: round(float(imp / total), 4)
            for col, imp in zip(self.feature_cols, importances)
        }

    def save(self, filepath: Path):
        joblib.dump({"model": self.model, "feature_cols": self.feature_cols}, filepath)

    def load(self, filepath: Path):
        data = joblib.load(filepath)
        self.model = data["model"]
        self.feature_cols = data["feature_cols"]
        self.is_fitted = True

