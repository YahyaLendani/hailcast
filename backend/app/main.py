import asyncio
import json
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy import select, func
from app.core.config import settings
from app.core.database import init_db, AsyncSessionLocal
from app.core.redis_client import redis_client
from app.models.events import RawTrip
from app.services.broadcaster import broadcaster
from app.services.streaming_worker import streaming_worker
from app.services.replay_engine import replay_engine
from app.services.etl_pipeline import ETLPipeline
from app.services.scheduler import scheduler
from app.api.routes import ingestion, streaming, analytics, ml, health
from app.ml.tracking import experiment_tracker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("hailcast")

GOLD_REBUILD_INTERVAL_SECONDS = 300


async def rebuild_gold_from_silver():
    """Scheduled job: recompute the Gold hourly table from Silver.

    The stream updates Gold incrementally; this periodic full recompute corrects
    any drift (for example after a dead-lettered or partially applied batch).
    """
    async with streaming_worker.write_lock:
        await ETLPipeline.run_gold_transformations()


scheduler.add_job(
    "gold_rebuild",
    "Recompute Gold hourly demand from Silver",
    GOLD_REBUILD_INTERVAL_SECONDS,
    rebuild_gold_from_silver,
)

async def bootstrap():
    """First-run preparation: seed an empty database, start the replay where the
    stored data ends, and train once so Forecast and Anomalies are never empty."""
    try:
        async with AsyncSessionLocal() as session:
            count = (await session.execute(select(func.count(RawTrip.id)))).scalar_one() or 0
        seeded = False
        if count == 0 and settings.AUTO_SEED_ON_STARTUP:
            ordered = replay_engine._dataset_buffer[:settings.INITIAL_SEED_SIZE]
            logger.info("Empty database detected. Seeding %d trips...", len(ordered))
            for start in range(0, len(ordered), 1000):
                await ETLPipeline.run_batch_ingestion(ordered[start:start + 1000], source_name="initial_seed")
            seeded = True
            logger.info("Initial seed complete.")

        async with AsyncSessionLocal() as session:
            latest = (await session.execute(select(func.max(RawTrip.pickup_datetime)))).scalar_one()
        replay_engine.resume_after(latest)

        if seeded or not experiment_tracker.get_experiments():
            async with AsyncSessionLocal() as session:
                result = await ml.train_and_score(session)
            logger.info("Startup training complete. Best model: %s", result.get("best_model"))
    except asyncio.CancelledError:
        raise
    except ValueError as exc:
        logger.warning("Startup training skipped: %s", exc)
    except Exception:
        logger.exception("Startup preparation failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Hailcast...")
    await init_db()
    await redis_client.connect()
    await streaming_worker.start()

    # Preload sample dataset into replay engine buffer
    sample_path = settings.DATA_DIR / "sample_trips.json"
    if not sample_path.exists():
        from app.data.download_sample import generate_sample_dataset
        generate_sample_dataset(sample_path)

    if sample_path.exists():
        with open(sample_path, "r", encoding="utf-8") as f:
            trips = json.load(f)
        replay_engine.load_dataset(trips)

    # Seed, position the replay and train in the background so the server
    # answers straight away (this matters on slow free hosting).
    bootstrap_task = asyncio.create_task(bootstrap())
    scheduler.start()

    yield

    bootstrap_task.cancel()

    # Shutdown
    logger.info("Shutting down Hailcast...")
    await scheduler.stop()
    replay_engine.stop()
    await streaming_worker.stop()
    await redis_client.disconnect()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Hailcast: NYC taxi demand, streamed through a Medallion pipeline and forecast",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,  # the API uses no cookies
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)

# API Routers
app.include_router(ingestion.router, prefix=settings.API_V1_STR)
app.include_router(streaming.router, prefix=settings.API_V1_STR)
app.include_router(analytics.router, prefix=settings.API_V1_STR)
app.include_router(ml.router, prefix=settings.API_V1_STR)
app.include_router(health.router, prefix=settings.API_V1_STR)

@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    """Real-time streaming WebSocket endpoint for live chart events and anomaly alerts."""
    await broadcaster.connect(websocket)
    try:
        while True:
            # Keepalive receiver
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        broadcaster.disconnect(websocket)
    except Exception:
        broadcaster.disconnect(websocket)

@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard():
    static_file = Path(__file__).parent / "static" / "index.html"
    if static_file.exists():
        return FileResponse(static_file)
    return HTMLResponse("<h1>Hailcast is online</h1><p>Visit <a href='/docs'>/docs</a> for API</p>")

@app.get("/api/info")
async def api_info():
    return {
        "platform": "Hailcast",
        "description": "Real-Time Data Engineering & Predictive Analytics Platform",
        "status": "online",
        "docs_url": "/docs",
        "health_check": f"{settings.API_V1_STR}/health"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
