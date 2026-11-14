import json
import logging
import asyncio
from typing import Optional, List, Dict, Any
from app.core.config import settings

logger = logging.getLogger(__name__)

class RedisStreamClient:
    def __init__(self):
        self.redis = None
        self.is_connected = False
        self.fallback_stream: asyncio.Queue = asyncio.Queue(maxsize=50000)
        self.fallback_storage: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()

    async def connect(self):
        try:
            import redis.asyncio as aioredis
            self.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            await self.redis.ping()
            self.is_connected = True
            logger.info("Connected to Redis Streams at %s", settings.REDIS_URL)
            
            # Setup consumer group if needed
            try:
                await self.redis.xgroup_create(
                    settings.REDIS_STREAM_KEY,
                    settings.REDIS_CONSUMER_GROUP,
                    id="0",
                    mkstream=True
                )
            except Exception:
                # Group might already exist
                pass
        except Exception as e:
            self.is_connected = False
            self.redis = None
            logger.warning(
                "Redis connection failed (%s). Using high-performance in-memory stream fallback.",
                str(e)
            )

    async def disconnect(self):
        if self.redis and self.is_connected:
            await self.redis.close()
            self.is_connected = False

    async def publish_event(self, event_data: Dict[str, Any]) -> str:
        """Publish event to Redis Stream or fallback in-memory stream."""
        payload = json.dumps(event_data, default=str)
        if self.is_connected and self.redis:
            try:
                msg_id = await self.redis.xadd(
                    settings.REDIS_STREAM_KEY,
                    {"data": payload}
                )
                return str(msg_id)
            except Exception as e:
                logger.error("Redis XADD error: %s, falling back to memory queue", e)
        
        # In-memory queue
        async with self._lock:
            msg_id = f"mem-{len(self.fallback_storage) + 1}-{asyncio.get_event_loop().time()}"
            item = {"id": msg_id, "data": payload}
            self.fallback_storage.append(item)
            if self.fallback_stream.full():
                try:
                    self.fallback_stream.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            await self.fallback_stream.put(item)
            return msg_id

    async def read_events(self, count: int = 50, block_ms: int = 1000) -> List[Dict[str, Any]]:
        """Read batch of events from stream."""
        if self.is_connected and self.redis:
            try:
                entries = await self.redis.xreadgroup(
                    groupname=settings.REDIS_CONSUMER_GROUP,
                    consumername="worker_1",
                    streams={settings.REDIS_STREAM_KEY: ">"},
                    count=count,
                    block=block_ms
                )
                results = []
                if entries:
                    for stream_name, messages in entries:
                        for msg_id, data in messages:
                            parsed = json.loads(data["data"])
                            results.append({"stream_id": msg_id, "payload": parsed})
                return results
            except Exception as e:
                logger.error("Redis XREADGROUP error: %s", e)

        # In-memory read
        results = []
        for _ in range(count):
            try:
                item = self.fallback_stream.get_nowait()
                parsed = json.loads(item["data"])
                results.append({"stream_id": item["id"], "payload": parsed})
                self.fallback_stream.task_done()
            except asyncio.QueueEmpty:
                break
        return results

    async def ack_events(self, events: List[Dict[str, Any]]) -> None:
        """Acknowledge events after they were stored or dead-lettered (not on read)."""
        if not (self.is_connected and self.redis):
            return
        ids = [e["stream_id"] for e in events if not str(e.get("stream_id", "")).startswith("mem-")]
        if not ids:
            return
        try:
            await self.redis.xack(settings.REDIS_STREAM_KEY, settings.REDIS_CONSUMER_GROUP, *ids)
        except Exception as e:
            logger.error("Redis XACK error: %s", e)

    async def get_stream_stats(self) -> Dict[str, Any]:
        """Return current stream length and status."""
        if self.is_connected and self.redis:
            try:
                length = await self.redis.xlen(settings.REDIS_STREAM_KEY)
                return {
                    "backend": "redis_streams",
                    "stream_key": settings.REDIS_STREAM_KEY,
                    "connected": True,
                    "stream_length": length
                }
            except Exception:
                pass
        return {
            "backend": "in_memory_stream",
            "stream_key": "in_memory_queue",
            "connected": False,
            "stream_length": len(self.fallback_storage),
            "pending_in_queue": self.fallback_stream.qsize()
        }

redis_client = RedisStreamClient()
