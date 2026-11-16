import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from app.core.redis_client import redis_client
from app.services.broadcaster import broadcaster
from app.core.clock import utc_now

logger = logging.getLogger(__name__)

class ReplayEngine:
    def __init__(self):
        self.is_active = False
        self.is_paused = False
        self.speed_multiplier = 10.0
        self.batch_size = 20
        self.events_replayed = 0
        self.current_simulated_time: Optional[datetime] = None
        self._task: Optional[asyncio.Task] = None
        self._dataset_buffer: List[Dict[str, Any]] = []
        self.start_index = 0

    def resume_after(self, latest_pickup: Optional[datetime]):
        """Start the replay at the first buffered trip newer than what is already stored.

        Without this the replay would begin with trips the database already holds, and a
        visitor would watch only duplicates being skipped. Wraps to the start when
        everything has been loaded.
        """
        index = 0
        if latest_pickup is not None:
            for index, trip in enumerate(self._dataset_buffer):
                if datetime.fromisoformat(str(trip["pickup_datetime"]).replace("Z", "")) > latest_pickup:
                    break
            else:
                index = 0
        self.start_index = index
        if not self.is_active:
            self.events_replayed = index
            self.current_simulated_time = latest_pickup if index else None

    def load_dataset(self, trips: List[Dict[str, Any]]):
        """Buffer historical trips sorted by pickup_datetime."""
        self._dataset_buffer = sorted(
            trips,
            key=lambda x: datetime.fromisoformat(str(x["pickup_datetime"]).replace("Z", ""))
        )
        logger.info("Loaded %d events into Replay buffer.", len(self._dataset_buffer))

    async def start(self, speed: float = 10.0, batch_size: int = 20):
        if self.is_active:
            self.speed_multiplier = speed
            self.batch_size = batch_size
            self.is_paused = False
            return

        self.is_active = True
        self.is_paused = False
        self.speed_multiplier = speed
        self.batch_size = batch_size
        self._task = asyncio.create_task(self._replay_loop())
        logger.info("Replay engine started with speed %.1fx", self.speed_multiplier)

    def pause(self):
        self.is_paused = True
        logger.info("Replay engine paused.")

    def resume(self):
        self.is_paused = False
        logger.info("Replay engine resumed.")

    def stop(self):
        self.is_active = False
        self.is_paused = False
        if self._task:
            self._task.cancel()
        logger.info("Replay engine stopped.")

    async def _replay_loop(self):
        if not self._dataset_buffer:
            logger.warning("No dataset buffered for replay. Replay loop exiting.")
            self.is_active = False
            return

        total = len(self._dataset_buffer)
        idx = self.start_index if self.start_index < total else 0
        self.events_replayed = idx

        while self.is_active:
            if self.is_paused:
                await asyncio.sleep(0.5)
                continue

            if idx >= total:
                # Every buffered trip has been replayed: stop instead of looping, so the
                # stream never silently turns into duplicates. The next start begins again
                # from the first trip (and shows deduplication at work).
                self.is_active = False
                self.start_index = 0
                await broadcaster.broadcast("replay_status", {**self.get_status(), "finished": True})
                logger.info("Replay finished: all %d buffered trips were replayed.", total)
                break

            batch = self._dataset_buffer[idx : idx + self.batch_size]
            idx += len(batch)

            for event in batch:
                event_copy = dict(event)
                # CRITICAL REQUIREMENT: Clearly label simulated real-time events as replayed historical data
                event_copy["is_replayed"] = True
                event_copy["replayed_at"] = utc_now().isoformat()
                
                self.current_simulated_time = datetime.fromisoformat(
                    str(event_copy["pickup_datetime"]).replace("Z", "")
                )
                
                await redis_client.publish_event(event_copy)
                self.events_replayed += 1

            # Broadcast status update
            await broadcaster.broadcast("replay_status", {
                "is_active": self.is_active,
                "is_paused": self.is_paused,
                "speed_multiplier": self.speed_multiplier,
                "events_replayed": self.events_replayed,
                "current_simulated_time": self.current_simulated_time.isoformat() if self.current_simulated_time else None,
                "total_buffered": total
            })

            # Interval scaled by speed_multiplier
            delay = max(0.05, 1.0 / self.speed_multiplier)
            await asyncio.sleep(delay)

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_active": self.is_active,
            "is_paused": self.is_paused,
            "speed_multiplier": self.speed_multiplier,
            "events_replayed": self.events_replayed,
            "current_simulated_time": self.current_simulated_time.isoformat() if self.current_simulated_time else None,
            "queue_depth": len(self._dataset_buffer),
            "total_buffered": len(self._dataset_buffer)
        }

replay_engine = ReplayEngine()

