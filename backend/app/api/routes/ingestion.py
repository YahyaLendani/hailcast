import json
from fastapi import APIRouter, Depends, Query
from app.core.config import settings
from app.core.redis_client import redis_client
from app.core.security import require_api_key
from app.schemas.trip import TripCreate, BatchIngestRequest, BatchIngestResponse
from app.services.etl_pipeline import ETLPipeline

router = APIRouter(prefix="/ingest", tags=["Ingestion"], dependencies=[Depends(require_api_key)])

@router.post("/batch", response_model=BatchIngestResponse)
async def ingest_batch(request: BatchIngestRequest):
    """Batch data ingestion pipeline with validation, deduplication, and ELT transformations."""
    raw_dicts = [trip.model_dump(mode="json") for trip in request.trips]
    result = await ETLPipeline.run_batch_ingestion(raw_dicts, source_name=request.source_name)
    return result

@router.post("/event")
async def ingest_single_event(trip: TripCreate):
    """Publish a single trip event directly to Redis Stream / worker queue."""
    msg_id = await redis_client.publish_event(trip.model_dump(mode="json"))
    return {"status": "published", "stream_id": msg_id, "event": trip}

@router.post("/seed-sample")
async def seed_sample_data(sample_size: int = Query(default=2000, le=10000)):
    """Seed sample transportation records into database to immediately populate dashboard."""
    sample_path = settings.DATA_DIR / "sample_trips.json"
    if not sample_path.exists():
        from app.data.download_sample import generate_sample_dataset
        generate_sample_dataset(sample_path)

    with open(sample_path, "r", encoding="utf-8") as f:
        all_trips = json.load(f)

    subset = all_trips[:sample_size]
    res = await ETLPipeline.run_batch_ingestion(subset, source_name="seed_sample_generator")
    return {"message": f"Successfully seeded {res['ingested']} trips.", "details": res}
