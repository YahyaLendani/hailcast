from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.core.redis_client import redis_client
from app.models.events import RawTrip, SilverTrip, GoldHourlyDemand, PipelineRun, DataQualityLog
from app.services.streaming_worker import streaming_worker
from app.services.scheduler import scheduler
from app.core.clock import utc_now

router = APIRouter(prefix="/health", tags=["Health & Monitoring"])

@router.get("/")
async def get_pipeline_health(db: AsyncSession = Depends(get_db)):
    """Comprehensive pipeline health monitoring, queue depth, throughput, and data quality logs."""
    raw_cnt = (await db.execute(select(func.count(RawTrip.id)))).scalar_one() or 0
    silver_cnt = (await db.execute(select(func.count(SilverTrip.id)))).scalar_one() or 0
    gold_cnt = (await db.execute(select(func.count(GoldHourlyDemand.id)))).scalar_one() or 0

    dedup_rate = round(((raw_cnt - silver_cnt) / max(1, raw_cnt)) * 100, 1)

    # Stream statistics
    stream_stats = await redis_client.get_stream_stats()

    # Recent runs
    recent_runs_res = await db.execute(
        select(PipelineRun).order_by(PipelineRun.id.desc()).limit(5)
    )
    recent_runs = [
        {
            "id": r.id,
            "run_type": r.run_type,
            "status": r.status,
            "records_ingested": r.records_ingested,
            "records_deduplicated": r.records_deduplicated,
            "duration_seconds": r.duration_seconds,
            "started_at": r.started_at.isoformat() if r.started_at else None
        }
        for r in recent_runs_res.scalars().all()
    ]

    # Data quality logs
    dq_res = await db.execute(
        select(DataQualityLog).order_by(DataQualityLog.id.desc()).limit(10)
    )
    dq_tests = [
        {
            "id": q.id,
            "test_name": q.test_name,
            "category": q.category,
            "status": q.status,
            "tested_records": q.tested_records,
            "failed_records": q.failed_records,
            "details": q.details,
            "created_at": q.created_at.isoformat() if q.created_at else None
        }
        for q in dq_res.scalars().all()
    ]

    return {
        "status": "healthy",
        "timestamp": utc_now().isoformat(),
        "database": {
            "status": "connected",
            "raw_trips_bronze": raw_cnt,
            "silver_trips_cleaned": silver_cnt,
            "gold_hourly_analytics": gold_cnt,
            "deduplication_rate_percent": dedup_rate
        },
        "streaming": {
            "backend": stream_stats.get("backend"),
            "connected": stream_stats.get("connected"),
            "stream_length": stream_stats.get("stream_length", 0),
            "current_eps": streaming_worker.last_eps,
            "total_streamed_events": streaming_worker.processed_count,
            "deduplicated_in_stream": streaming_worker.deduplicated_count,
            "retried_batches": streaming_worker.retried_count,
            "failed_events": streaming_worker.failed_count,
            "dead_letters": list(streaming_worker.dead_letters)[-5:]
        },
        "scheduled_jobs": scheduler.status(),
        "recent_pipeline_runs": recent_runs,
        "data_quality_tests": dq_tests
    }


@router.post("/jobs/{name}/run")
async def run_scheduled_job(name: str):
    """Run one scheduled job immediately instead of waiting for its interval."""
    if name not in scheduler.jobs:
        raise HTTPException(status_code=404, detail=f"Unknown job: {name}")
    return await scheduler.run_job(name)

