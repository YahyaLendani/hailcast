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
from app.api.routes import ingestion, streaming, analytics, ml, health

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("FlowSight")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting FlowSight platform...")
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

        # Auto-seed initial batch into DB if database is empty
        async with AsyncSessionLocal() as session:
            count = (await session.execute(select(func.count(RawTrip.id)))).scalar_one() or 0
            if count == 0:
                logger.info("Empty database detected. Seeding initial 1,500 trips...")
                await ETLPipeline.run_batch_ingestion(trips[:1500], source_name="initial_seed")
                logger.info("Initial seed complete.")

    yield

    # Shutdown
    logger.info("Shutting down FlowSight platform...")
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
