import json
import asyncio
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from app.core.config import settings
from app.schemas.trip import ReplayControlRequest, ReplayStatusResponse
from app.services.replay_engine import replay_engine

router = APIRouter(prefix="/stream", tags=["Streaming & Replay"])

@router.post("/control", response_model=ReplayStatusResponse)
async def control_replay(req: ReplayControlRequest):
    """Control historical event replay simulator (start, pause, resume, stop)."""
    # Load dataset into replay buffer if empty
    if not replay_engine._dataset_buffer:
        sample_path = settings.DATA_DIR / "sample_trips.json"
        if sample_path.exists():
            with open(sample_path, "r", encoding="utf-8") as f:
                trips = json.load(f)
            replay_engine.load_dataset(trips)

    action = req.action.lower()
    if action == "start":
        await replay_engine.start(speed=req.speed_multiplier, batch_size=req.batch_size)
    elif action == "pause":
        replay_engine.pause()
    elif action == "resume":
        replay_engine.resume()
    elif action == "stop":
        replay_engine.stop()

    return replay_engine.get_status()

@router.get("/status", response_model=ReplayStatusResponse)
async def get_replay_status():
    """Get current status of historical event replay simulator."""
    return replay_engine.get_status()

@router.get("/sse")
async def event_stream(request: Request):
    """Server-Sent Events (SSE) stream for real-time live chart updates."""
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break

            status = replay_engine.get_status()
            payload = json.dumps({"type": "replay_tick", "data": status})
            yield f"data: {payload}\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

