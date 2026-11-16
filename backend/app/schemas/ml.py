from datetime import datetime
from typing import List, Optional, Dict
from pydantic import BaseModel, Field

class ForecastPoint(BaseModel):
    timestamp: datetime
    predicted_demand: float
    lower_bound: float
    upper_bound: float
    baseline_demand: Optional[float] = None
    actual_demand: Optional[float] = None

class ForecastRequest(BaseModel):
    horizon_hours: int = Field(default=24, ge=1, le=168)
    location_id: Optional[int] = None
    model_name: str = "lightgbm"

class ModelMetrics(BaseModel):
    model_name: str
    mae: float
    rmse: float
    mape: float
    r2_score: float
    validation_method: str = "TimeSeriesSplit (Walk-Forward, No Future Leakage)"
    train_samples: int
    test_samples: int

class ForecastResponse(BaseModel):
    model_name: str
    horizon_hours: int
    generated_at: datetime
    metrics: ModelMetrics
    forecasts: List[ForecastPoint]
    history: List[ForecastPoint] = []

class ModelComparisonResponse(BaseModel):
    models: List[ModelMetrics]
    best_model: str
    feature_importances: Dict[str, float]

class AnomalyPoint(BaseModel):
    timestamp: datetime
    location_id: int
    observed_demand: int
    expected_demand: float
    anomaly_score: float
    is_anomaly: bool
    severity: str  # low, medium, high

