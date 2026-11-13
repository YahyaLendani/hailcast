import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Set, Tuple
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.core.redis_client import redis_client
from app.models.events import RawTrip, SilverTrip, GoldHourlyDemand
from app.services.data_cleaner import DataCleaner
from app.services.broadcaster import broadcaster

logger = logging.getLogger(__name__)

class StreamingWorker:
    def __init__(self):
        self.is_running = False
        self._task = None
        self.processed_count = 0
        self.deduplicated_count = 0
        self.failed_count = 0
        self.last_eps = 0.0
        self._eps_timer = datetime.utcnow()
        self._eps_count = 0

    async def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Streaming worker started.")

    async def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Streaming worker stopped.")

    async def _run_loop(self):
        while self.is_running:
            try:
                events = await redis_client.read_events(count=25, block_ms=500)
                if events:
                    await self._process_batch(events)
                else:
                    await asyncio.sleep(0.1)

                # Calculate EPS every 3 seconds
                now = datetime.utcnow()
                elapsed = (now - self._eps_timer).total_seconds()
                if elapsed >= 3.0:
                    self.last_eps = round(self._eps_count / elapsed, 1)
                    self._eps_timer = now
                    self._eps_count = 0

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Streaming worker loop error: %s", e)
                await asyncio.sleep(0.5)

    async def _process_batch(self, events: List[Dict[str, Any]]):
        async with AsyncSessionLocal() as session:
            # AsyncSessionLocal uses autoflush=False, so track pending event_ids and
            # GoldHourlyDemand (time_bucket, location_id) rows within the current batch
            # to prevent intra-batch duplicate INSERT UNIQUE constraint violations.
            seen_event_ids: Set[str] = set()
            gold_cache: Dict[Tuple[datetime, int], GoldHourlyDemand] = {}
            batch_processed = 0
            batch_deduplicated = 0

            try:
                for entry in events:
                    payload = entry["payload"]
                    raw_data = payload.get("data", payload)
                    
                    p_time = datetime.fromisoformat(str(raw_data["pickup_datetime"]).replace("Z", ""))
                    d_time = datetime.fromisoformat(str(raw_data["dropoff_datetime"]).replace("Z", ""))
                    p_loc = int(raw_data["pickup_location_id"])
                    d_loc = int(raw_data["dropoff_location_id"])
                    fare = float(raw_data["fare_amount"])
                    
                    event_id = raw_data.get("event_id") or DataCleaner.generate_event_id(
                        p_time, d_time, p_loc, d_loc, fare
                    )

                    # 1. Idempotency Check: check in-batch cache first, then database
                    if event_id in seen_event_ids:
                        batch_deduplicated += 1
                        continue

                    existing = await session.execute(select(RawTrip.id).where(RawTrip.event_id == event_id))
                    if existing.scalar_one_or_none():
                        seen_event_ids.add(event_id)
                        batch_deduplicated += 1
                        continue

                    seen_event_ids.add(event_id)

                    raw_trip = RawTrip(
                        event_id=event_id,
                        pickup_datetime=p_time,
                        dropoff_datetime=d_time,
                        passenger_count=int(raw_data.get("passenger_count", 1)),
                        trip_distance=float(raw_data.get("trip_distance", 1.0)),
                        pickup_location_id=p_loc,
                        dropoff_location_id=d_loc,
                        fare_amount=fare,
                        tip_amount=float(raw_data.get("tip_amount", 0.0)),
                        total_amount=float(raw_data.get("total_amount", fare)),
                        payment_type=str(raw_data.get("payment_type", "Credit Card")),
                        is_replayed=bool(raw_data.get("is_replayed", True)),
                        source_file="realtime_stream",
                        ingested_at=datetime.utcnow()
                    )
                    session.add(raw_trip)

                    # 2. Validation & Silver transformation
                    is_valid, silver_trip, issues = DataCleaner.validate_and_clean_trip(raw_trip)
                    if is_valid and silver_trip:
                        session.add(silver_trip)

                        # 3. Gold aggregation (Hourly bucket) with in-batch cache
                        bucket = p_time.replace(minute=0, second=0, microsecond=0)
                        bucket_key = (bucket, p_loc)
                        gold_record = gold_cache.get(bucket_key)

                        if gold_record is None:
                            gold_res = await session.execute(
                                select(GoldHourlyDemand).where(
                                    GoldHourlyDemand.time_bucket == bucket,
                                    GoldHourlyDemand.location_id == p_loc
                                )
                            )
                            gold_record = gold_res.scalar_one_or_none()
                            if gold_record is not None:
                                gold_cache[bucket_key] = gold_record

                        if gold_record is not None:
                            new_count = gold_record.trip_count + 1
                            gold_record.trip_count = new_count
                            gold_record.total_passengers += silver_trip.passenger_count
                            gold_record.total_revenue = round(gold_record.total_revenue + silver_trip.total_amount, 2)
                            gold_record.avg_fare = round(
                                (gold_record.avg_fare * (new_count - 1) + silver_trip.fare_amount) / new_count, 2
                            )
                            gold_record.avg_distance = round(
                                (gold_record.avg_distance * (new_count - 1) + silver_trip.trip_distance) / new_count, 2
                            )
                            gold_record.avg_duration_minutes = round(
                                (gold_record.avg_duration_minutes * (new_count - 1) + silver_trip.trip_duration_minutes) / new_count, 2
                            )
                            gold_record.updated_at = datetime.utcnow()
                        else:
                            gold_record = GoldHourlyDemand(
                                time_bucket=bucket,
                                location_id=p_loc,
                                trip_count=1,
                                total_passengers=silver_trip.passenger_count,
                                avg_distance=silver_trip.trip_distance,
                                avg_fare=silver_trip.fare_amount,
                                total_revenue=silver_trip.total_amount,
                                avg_duration_minutes=silver_trip.trip_duration_minutes,
                                updated_at=datetime.utcnow()
                            )
                            session.add(gold_record)
                            gold_cache[bucket_key] = gold_record

                    batch_processed += 1

                await session.commit()
                self.processed_count += batch_processed
                self.deduplicated_count += batch_deduplicated
                self._eps_count += batch_processed

                # Broadcast live event to frontend subscribers
                if events:
                    latest = events[-1]["payload"]
                    await broadcaster.broadcast("new_trip_streamed", {
                        "batch_size": len(events),
                        "ingested_in_batch": batch_processed,
                        "deduplicated_in_batch": batch_deduplicated,
                        "total_processed": self.processed_count,
                        "eps": self.last_eps,
                        "sample": latest.get("data", latest)
                    })

            except Exception as e:
                await session.rollback()
                logger.error("Error committing streaming batch: %s", e)
                self.failed_count += len(events)

streaming_worker = StreamingWorker()
