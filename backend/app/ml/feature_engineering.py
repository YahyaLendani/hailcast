import numpy as np
import pandas as pd
from typing import Tuple, List

# Hours of history every row needs: the longest lag and rolling window.
HISTORY_HOURS = 24

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
        day_of_week = df["time_bucket"].dt.day_of_week
        
        df["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
        df["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
        df["dow_sin"] = np.sin(2 * np.pi * day_of_week / 7.0)
        df["dow_cos"] = np.cos(2 * np.pi * day_of_week / 7.0)

        # Binary calendar indicators
        df["is_weekend"] = day_of_week.isin([5, 6]).astype(int)
        df["is_rush_hour"] = hour.isin([7, 8, 9, 16, 17, 18, 19]).astype(int)
        df["is_night"] = hour.isin([0, 1, 2, 3, 4, 5]).astype(int)

        # 2. Causal Lag Features (past hours only)
        df["lag_1h"] = df[target_col].shift(1)
        df["lag_2h"] = df[target_col].shift(2)
        df["lag_3h"] = df[target_col].shift(3)
        df["lag_24h"] = df[target_col].shift(24)

        # 3. Rolling windows over the hours before this one (shifted by one hour, full windows only)
        past = df[target_col].shift(1)
        df["rolling_mean_3h"] = past.rolling(window=3).mean()
        df["rolling_mean_6h"] = past.rolling(window=6).mean()
        df["rolling_mean_24h"] = past.rolling(window=24).mean()
        df["rolling_std_6h"] = past.rolling(window=6).std()

        # 4. Contextual interaction features
        df["avg_fare_lag1"] = df["avg_fare"].shift(1) if "avg_fare" in df else 0.0
        df["avg_distance_lag1"] = df["avg_distance"].shift(1) if "avg_distance" in df else 0.0

        feature_cols = [
            "hour_sin", "hour_cos", "dow_sin", "dow_cos",
            "is_weekend", "is_rush_hour", "is_night",
            "lag_1h", "lag_2h", "lag_3h", "lag_24h",
            "rolling_mean_3h", "rolling_mean_6h", "rolling_mean_24h", "rolling_std_6h"
        ]

        # The first HISTORY_HOURS rows have no complete 24-hour history. They are dropped, never
        # back-filled: back-filling copies later values (including a row's own target) into them.
        df = df.dropna(subset=feature_cols).reset_index(drop=True)

        return df, feature_cols

