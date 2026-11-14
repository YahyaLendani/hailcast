"""Small in-process job scheduler.

Runs recurring maintenance jobs on a fixed interval inside the API process and
keeps the outcome of each run so the health endpoint and the dashboard can show it.
"""
import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.core.config import utc_now

logger = logging.getLogger(__name__)


@dataclass
class ScheduledJob:
    name: str
    description: str
    interval_seconds: float
    func: Callable[[], Awaitable[Any]]
    runs: int = 0
    failures: int = 0
    last_status: str = "never run"
    last_error: Optional[str] = None
    last_run_at: Optional[str] = None
    last_duration_seconds: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "interval_seconds": self.interval_seconds,
            "runs": self.runs,
            "failures": self.failures,
            "last_status": self.last_status,
            "last_error": self.last_error,
            "last_run_at": self.last_run_at,
            "last_duration_seconds": self.last_duration_seconds,
        }


class Scheduler:
    def __init__(self) -> None:
        self.jobs: Dict[str, ScheduledJob] = {}
        self._tasks: List[asyncio.Task] = []

    def add_job(self, name: str, description: str, interval_seconds: float,
                func: Callable[[], Awaitable[Any]]) -> None:
        self.jobs[name] = ScheduledJob(name, description, interval_seconds, func)

    async def run_job(self, name: str) -> Dict[str, Any]:
        """Run one job now. A failure is recorded and logged, never raised."""
        job = self.jobs[name]
        started = time.perf_counter()
        job.last_run_at = utc_now().isoformat()
        try:
            await job.func()
            job.last_status = "success"
            job.last_error = None
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # a failing job must not stop the schedule
            job.failures += 1
            job.last_status = "failed"
            job.last_error = f"{type(exc).__name__}: {exc}"
            logger.exception("Scheduled job %s failed", name)
        job.runs += 1
        job.last_duration_seconds = round(time.perf_counter() - started, 3)
        return job.as_dict()

    async def _loop(self, job: ScheduledJob) -> None:
        while True:
            await asyncio.sleep(job.interval_seconds)
            await self.run_job(job.name)

    def start(self) -> None:
        if self._tasks:
            return
        self._tasks = [asyncio.create_task(self._loop(job)) for job in self.jobs.values()]
        logger.info("Scheduler started with %d job(s).", len(self._tasks))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    def status(self) -> List[Dict[str, Any]]:
        return [job.as_dict() for job in self.jobs.values()]


scheduler = Scheduler()
