"""Collector process: python -m app.collector.run

Polls the MTA feed every BUS_POLL_SECONDS, stitches positions into trips and stores each finished
trip. Trips still running when the process stops are lost; the next ones are collected as normal.
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import delete

from app.collector import mta
from app.collector.stitcher import Stitcher
from app.core.config import settings
from app.core.database import AsyncSessionLocal, init_db
from app.models.bus import BusTrip

logger = logging.getLogger("bus_collector")


def redact(text: str) -> str:
    """Hide the API key in a message, raw or URL-encoded, wherever it appears as key=..."""
    text = re.sub(r"(key=)[^&\s'\"]+", r"\1***", text)
    return text.replace(settings.MTA_API_KEY, "***") if settings.MTA_API_KEY else text


async def store(trips):
    if not trips:
        return
    async with AsyncSessionLocal() as session:
        for trip in trips:
            await session.merge(BusTrip(**trip))
        await session.commit()


async def prune():
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=settings.BUS_RETENTION_HOURS)
    async with AsyncSessionLocal() as session:
        result = await session.execute(delete(BusTrip).where(BusTrip.end_utc < cutoff))
        await session.commit()
    if result.rowcount:
        logger.info("pruned %d trips older than %s h", result.rowcount, settings.BUS_RETENTION_HOURS)


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # httpx logs every request URL at INFO, and the MTA key is a query parameter.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    if not settings.MTA_API_KEY:
        raise SystemExit("MTA_API_KEY is not set; the bus collector has nothing to poll.")
    await init_db()
    stitcher = Stitcher()
    polls = 0
    async with httpx.AsyncClient(headers={"User-Agent": "hailcast-bus-collector"}) as client:
        while True:
            started = asyncio.get_running_loop().time()
            try:
                fixes = mta.parse(await mta.fetch(client, settings.MTA_API_KEY))
                finished = stitcher.feed(fixes, datetime.now(timezone.utc))
                await store(finished)
                logger.info("%d fixes, %d trips open, %d stored", len(fixes), len(stitcher.open), len(finished))
                polls += 1
                if polls % 120 == 1:  # about once an hour
                    await prune()
            except Exception as exc:  # network trouble or a bad response: try again next poll
                # httpx puts the request URL, key included, in its messages; keep the key out of logs.
                logger.warning("poll failed: %s", redact(str(exc)))
            elapsed = asyncio.get_running_loop().time() - started
            await asyncio.sleep(max(1.0, settings.BUS_POLL_SECONDS - elapsed))


if __name__ == "__main__":
    asyncio.run(main())
