import asyncio
import json
import os
import pandas as pd
from sqlalchemy import select, delete
from app.core.database import init_db, AsyncSessionLocal
from app.core.config import settings
from app.models.events import RawTrip, SilverTrip, GoldHourlyDemand, PipelineRun, DataQualityLog
from app.services.etl_pipeline import ETLPipeline
from app.services.data_cleaner import DataCleaner
from app.ml.train import train_and_evaluate
from app.services.anomaly_detector import anomaly_detector

async def run_e2e_tests():
    print("=== 1. Database Init & Test Environment Reset ===")
    await init_db()
    # Reset tables for clean idempotent test run
    async with AsyncSessionLocal() as session:
        for model in [DataQualityLog, PipelineRun, GoldHourlyDemand, SilverTrip, RawTrip]:
            await session.execute(delete(model))
        await session.commit()

    print("=== 2. Batch Ingestion & Validation ===")
    sample_file = settings.DATA_DIR / "sample_trips.json"
    with open(sample_file, "r", encoding="utf-8") as f:
        trips = json.load(f)[:1200]

    ingest_res = await ETLPipeline.run_batch_ingestion(trips, source_name="e2e_test")
    print(f"Ingested: {ingest_res['ingested']}, Deduplicated: {ingest_res['deduplicated']}, Failed: {ingest_res['failed']}")
    assert ingest_res["ingested"] > 0, "Should ingest records"

    print("=== 3. Idempotent Deduplication ===")
    dedup_res = await ETLPipeline.run_batch_ingestion(trips[:200], source_name="e2e_test_dedup")
    print(f"Dedup check: {dedup_res['deduplicated']} duplicates properly filtered out.")
    assert dedup_res["deduplicated"] == 200, "All 200 replayed items should be deduplicated"

    print("=== 4. SQL Aggregations (Gold Table) ===")
    async with AsyncSessionLocal() as session:
        records = (await session.execute(select(GoldHourlyDemand).order_by(GoldHourlyDemand.time_bucket.asc()))).scalars().all()
        print(f"Created {len(records)} gold hourly buckets.")
        assert len(records) > 0, "Gold table must have records"

        df = pd.DataFrame([{
            "time_bucket": r.time_bucket,
            "location_id": r.location_id,
            "trip_count": r.trip_count,
            "avg_fare": r.avg_fare,
            "avg_distance": r.avg_distance,
            "total_revenue": r.total_revenue,
            "avg_duration_minutes": r.avg_duration_minutes
        } for r in records])

    print("=== 5. ML Demand Forecasting & Walk-Forward Validation ===")
    train_res = train_and_evaluate(df)
    for m in train_res["metrics"]:
        print(f"Model: {m['model_name']} -> MAE: {m['mae']}, RMSE: {m['rmse']}, R2: {m['r2_score']}")

    print("=== 6. Anomaly Detection ===")
    anom_results = anomaly_detector.fit_detect(df.to_dict(orient="records"))
    anomalies = [a for a in anom_results if a.get("is_anomaly")]
    print(f"Detected {len(anomalies)} demand anomalies across historical buckets.")

    print("\n>>> ALL FLOWSIGHT E2E PIPELINE TESTS PASSED SUCCESSFULLY! <<<")

if __name__ == "__main__":
    asyncio.run(run_e2e_tests())
