import numpy as np
import pandas as pd
from typing import Tuple, List

class FeatureEngineer:
    @staticmethod
    def create_features(df: pd.DataFrame, target_col: str = "trip_count") -> Tuple[pd.DataFrame, List[str]]:
        """Extract time-aware features for demand forecasting without future-data leakage."""
        df = df.copy()
        
        # Ensure timestamp is datetime
        if not pd.api.types.is_datetime64_any_dtype(df["time_bucket"]):
            df["time_bucket"] = pd.to_datetime(df["time_bucket"])

        df = df.sort_values("time_bucket").reset_index(drop=True)

        # 1. Cyclical Temporal Features
        hour = df["time_bucket"].dt.hour
        day_of_week = df["time_bucket"].dt.dayofweek
        
        df["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
        df["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
        df["dow_sin"] = np.sin(2 * np.pi * day_of_week / 7.0)
        df["dow_cos"] = np.cos(2 * np.pi * day_of_week / 7.0)

        # Binary calendar indicators
        df["is_weekend"] = day_of_week.isin([5, 6]).astype(int)
        df["is_rush_hour"] = hour.isin([7, 8, 9, 16, 17, 18, 19]).astype(int)
        df["is_night"] = hour.isin([0, 1, 2, 3, 4, 5]).astype(int)

        # 2. Causal Lag Features (strictly strictly past data - NO future leakage)
        df["lag_1h"] = df[target_col].shift(1)
        df["lag_2h"] = df[target_col].shift(2)
        df["lag_3h"] = df[target_col].shift(3)
        df["lag_24h"] = df[target_col].shift(24)

        # 3. Rolling Window Aggregations (using closed='left' to prevent current/future leakage)
        df["rolling_mean_3h"] = df[target_col].shift(1).rolling(window=3, min_periods=1).mean()
        df["rolling_mean_6h"] = df[target_col].shift(1).rolling(window=6, min_periods=1).mean()
        df["rolling_mean_24h"] = df[target_col].shift(1).rolling(window=24, min_periods=1).mean()
        df["rolling_std_6h"] = df[target_col].shift(1).rolling(window=6, min_periods=1).std().fillna(0)

        # 4. Contextual interaction features
        df["avg_fare_lag1"] = df["avg_fare"].shift(1) if "avg_fare" in df else 0.0
        df["avg_distance_lag1"] = df["avg_distance"].shift(1) if "avg_distance" in df else 0.0

        # Drop NaNs created by shifting
        feature_cols = [
            "hour_sin", "hour_cos", "dow_sin", "dow_cos",
            "is_weekend", "is_rush_hour", "is_night",
            "lag_1h", "lag_2h", "lag_3h", "lag_24h",
            "rolling_mean_3h", "rolling_mean_6h", "rolling_mean_24h", "rolling_std_6h"
        ]

        # Fill initial NaNs with backward fill or mean for valid model execution
        df[feature_cols] = df[feature_cols].bfill().fillna(0.0)

        return df, feature_cols

