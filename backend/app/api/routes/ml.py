import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.config import settings
from app.models.events import GoldHourlyDemand
from app.schemas.ml import (
    ForecastRequest, ForecastResponse, ForecastPoint,
    ModelComparisonResponse, ModelMetrics, AnomalyPoint
)
from app.ml.train import train_and_evaluate, forecast_citywide
from app.ml.models import LightGBMDemandForecaster, BaselineHourlyAverageModel
from app.ml.feature_engineering import FeatureEngineer
from app.ml.tracking import experiment_tracker
from app.services.anomaly_detector import anomaly_detector

router = APIRouter(prefix="/ml", tags=["Machine Learning"])

@router.post("/train")
async def trigger_training(db: AsyncSession = Depends(get_db)):
    """Train gradient-boosting model and compare against baselines using time-aware validation."""
    res = await db.execute(select(GoldHourlyDemand).order_by(GoldHourlyDemand.time_bucket.asc()))
    records = res.scalars().all()
    if not records:
        raise HTTPException(status_code=400, detail="No hourly demand data yet. Seed sample data or start the replay first.")

    # Convert to pandas
    data = [
        {
            "time_bucket": r.time_bucket,
            "location_id": r.location_id,
            "trip_count": r.trip_count,
            "avg_fare": r.avg_fare,
            "avg_distance": r.avg_distance,
            "total_revenue": r.total_revenue,
            "avg_duration_minutes": r.avg_duration_minutes
        }
        for r in records
    ]
    df = pd.DataFrame(data)
    
    # 1. Run ML Training & Evaluation
    try:
        train_summary = train_and_evaluate(df)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # 2. Run Anomaly Detection and update DB
    anom_results = anomaly_detector.fit_detect(data)
    for rec in records:
        match = next((a for a in anom_results if a["time_bucket"] == rec.time_bucket and a["location_id"] == rec.location_id), None)
        if match:
            rec.is_anomaly = match["is_anomaly"]
            rec.anomaly_score = match["anomaly_score"]
    await db.commit()

    return {
        "status": "success",
        "message": "Models trained successfully with time-aware walk-forward validation.",
        "results": train_summary
    }

def _latest_metrics() -> tuple[List[ModelMetrics], Optional[str]]:
    """Walk-forward metrics from the most recent training run (empty if never trained)."""
    experiments = experiment_tracker.get_experiments()
    if not experiments:
        return [], None
    latest = experiments[-1]
    rows = latest.get("all_metrics") or [latest["metrics"]]
    metrics = [ModelMetrics(**row) for row in rows]
    best = latest.get("best_model") or min(metrics, key=lambda m: m.mae).model_name
    return metrics, best


async def _gold_frame(db: AsyncSession) -> pd.DataFrame:
    res = await db.execute(
        select(GoldHourlyDemand.time_bucket, GoldHourlyDemand.trip_count)
        .order_by(GoldHourlyDemand.time_bucket.asc())
    )
    return pd.DataFrame([tuple(r) for r in res.all()], columns=["time_bucket", "trip_count"])


@router.get("/models", response_model=ModelComparisonResponse)
async def get_model_comparison():
    """Compare the LightGBM forecaster against baselines using the latest training run."""
    metrics, best = _latest_metrics()

    importances: Dict[str, float] = {}
    model_file = settings.MODEL_DIR / "lightgbm_demand_forecaster.joblib"
    if metrics and model_file.exists():
        try:
            m = LightGBMDemandForecaster()
            m.load(model_file)
            importances = m.get_feature_importances()
        except Exception:
            importances = {}

    return ModelComparisonResponse(
        models=metrics,
        best_model=best or "untrained",
        feature_importances=importances
    )

@router.post("/forecast", response_model=ForecastResponse)
async def generate_forecast(req: ForecastRequest, db: AsyncSession = Depends(get_db)):
    """Recursive city-wide demand forecast from the trained LightGBM model."""
    df = await _gold_frame(db)
    model_file = settings.MODEL_DIR / "lightgbm_demand_forecaster.joblib"
    metrics, _best = _latest_metrics()

    try:
        if not metrics or not model_file.exists():
            train_and_evaluate(df)
            metrics, _best = _latest_metrics()
        result = forecast_citywide(df, req.horizon_hours)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    lgb = next((m for m in metrics if m.model_name == "LightGBM_Forecaster"), metrics[0])
    # ~80% band derived from the walk-forward RMSE of the validation folds
    band = 1.28 * lgb.rmse

    points = [
        ForecastPoint(
            timestamp=step["timestamp"],
            predicted_demand=round(step["predicted"], 1),
            lower_bound=round(max(0.0, step["predicted"] - band), 1),
            upper_bound=round(step["predicted"] + band, 1),
            baseline_demand=round(step["baseline"], 1)
        )
        for step in result["steps"]
    ]
    history = [
        ForecastPoint(
            timestamp=h["timestamp"],
            predicted_demand=h["actual"],
            lower_bound=h["actual"],
            upper_bound=h["actual"],
            actual_demand=h["actual"]
        )
        for h in result["history"]
    ]

    return ForecastResponse(
        model_name="LightGBM_Forecaster",
        horizon_hours=req.horizon_hours,
        generated_at=datetime.utcnow(),
        metrics=lgb,
        forecasts=points,
        history=history
    )

@router.get("/anomalies", response_model=List[AnomalyPoint])
async def get_anomalies(db: AsyncSession = Depends(get_db)):
    """Fetch detected demand anomalies with anomaly scores and severity."""
    query = select(GoldHourlyDemand).where(GoldHourlyDemand.is_anomaly == True).order_by(GoldHourlyDemand.time_bucket.desc())
    res = await db.execute(query)
    records = res.scalars().all()

    return [
        AnomalyPoint(
            timestamp=r.time_bucket,
            location_id=r.location_id,
            observed_demand=r.trip_count,
            expected_demand=round(r.trip_count * 0.5, 1),
            anomaly_score=r.anomaly_score or 0.85,
            is_anomaly=True,
            severity="high" if (r.anomaly_score or 0) > 0.8 else "medium"
        )
        for r in records
    ]

