import asyncio
import pandas as pd
from typing import List, Dict, Optional
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
from app.ml.models import LightGBMDemandForecaster
from app.ml.tracking import experiment_tracker
from app.services.anomaly_detector import anomaly_detector
from app.core.clock import utc_now

router = APIRouter(prefix="/ml", tags=["Machine Learning"])

async def train_and_score(db: AsyncSession) -> Dict:
    """Train and evaluate the forecaster on the Gold table, then score anomalies.

    Raises ValueError when there is too little data.
    """
    res = await db.execute(select(GoldHourlyDemand).order_by(GoldHourlyDemand.time_bucket.asc()))
    records = res.scalars().all()
    if not records:
        raise ValueError("No hourly demand data yet. Seed sample data or start the replay first.")

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
    # Training is CPU work; keep it off the event loop so the API stays responsive.
    train_summary = await asyncio.to_thread(train_and_evaluate, df)

    # 2. Run Anomaly Detection and update DB
    anom_results = await asyncio.to_thread(anomaly_detector.fit_detect, data)
    lookup = {(a["time_bucket"], a["location_id"]): a for a in anom_results}
    for rec in records:
        match = lookup.get((rec.time_bucket, rec.location_id))
        if match:
            rec.is_anomaly = match["is_anomaly"]
            rec.anomaly_score = match["anomaly_score"]
    await db.commit()
    return train_summary


@router.post("/train")
async def trigger_training(db: AsyncSession = Depends(get_db)):
    """Train gradient-boosting model and compare against baselines using time-aware validation."""
    try:
        train_summary = await train_and_score(db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
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
        generated_at=utc_now(),
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


@router.get("/zone-outlook")
async def get_zone_outlook(
    horizon_hours: int = Query(1, ge=1, le=12, description="Hours ahead to plan for"),
    db: AsyncSession = Depends(get_db)
):
    """Expected pickups per zone for the coming hours, for deciding where to send cabs.

    The city-wide LightGBM forecast for each coming hour is split across zones by
    each zone's historical share of trips at that hour of day.
    """
    from app.api.routes.analytics import ZONE_NAMES

    res = await db.execute(
        select(
            GoldHourlyDemand.time_bucket, GoldHourlyDemand.location_id,
            GoldHourlyDemand.trip_count, GoldHourlyDemand.total_revenue
        ).order_by(GoldHourlyDemand.time_bucket.asc())
    )
    df = pd.DataFrame([tuple(r) for r in res.all()], columns=["time_bucket", "location_id", "trip_count", "total_revenue"])
    if df.empty:
        raise HTTPException(status_code=400, detail="No demand data yet. Seed sample data or start the replay first.")
    df["time_bucket"] = pd.to_datetime(df["time_bucket"])

    model_file = settings.MODEL_DIR / "lightgbm_demand_forecaster.joblib"
    metrics, _best = _latest_metrics()
    try:
        if not metrics or not model_file.exists():
            train_and_evaluate(df[["time_bucket", "trip_count"]])
            metrics, _best = _latest_metrics()
        result = forecast_citywide(df[["time_bucket", "trip_count"]], horizon_hours)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    steps = result["steps"]
    lgb = next((m for m in metrics if m.model_name == "LightGBM_Forecaster"), metrics[0])
    last_hour = pd.Timestamp(steps[0]["timestamp"]) - pd.Timedelta(hours=1)

    # Only complete hours feed the shares, matching what the forecast was built on
    hist = df[df["time_bucket"] <= last_hour]
    hour_of_day = hist["time_bucket"].dt.hour
    zone_hour = hist.groupby([hour_of_day, "location_id"])["trip_count"].sum()
    hour_total = hist.groupby(hour_of_day)["trip_count"].sum()
    zone_total = hist.groupby("location_id")["trip_count"].sum()
    zone_revenue = hist.groupby("location_id")["total_revenue"].sum()
    all_trips = float(zone_total.sum()) or 1.0
    last_counts = hist[hist["time_bucket"] == last_hour].set_index("location_id")["trip_count"]

    zones = []
    for zone_id, trips in zone_total.items():
        expected = 0.0
        for step in steps:
            hour = step["timestamp"].hour
            total = float(hour_total.get(hour, 0.0))
            share = float(zone_hour.get((hour, zone_id), 0.0)) / total if total > 0 else float(trips) / all_trips
            expected += step["predicted"] * share
        per_trip = float(zone_revenue.get(zone_id, 0.0)) / float(trips) if trips else 0.0
        zones.append({
            "location_id": int(zone_id),
            "zone_name": ZONE_NAMES.get(int(zone_id), f"Zone {int(zone_id)}"),
            "expected_pickups": round(expected, 1),
            "last_hour_pickups": int(last_counts.get(zone_id, 0)),
            "avg_revenue_per_trip": round(per_trip, 2),
            "expected_revenue": round(expected * per_trip, 2),
        })
    zones.sort(key=lambda z: z["expected_pickups"], reverse=True)

    return {
        "horizon_hours": horizon_hours,
        "window_start": steps[0]["timestamp"].isoformat(),
        "window_end": (pd.Timestamp(steps[-1]["timestamp"]) + pd.Timedelta(hours=1)).isoformat(),
        "citywide_expected": round(sum(s["predicted"] for s in steps), 1),
        "typical_error_per_hour": lgb.mae,
        "history_hours": int(hist["time_bucket"].nunique()),
        "zones": zones,
    }
