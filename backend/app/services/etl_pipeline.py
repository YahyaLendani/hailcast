import time
import logging
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy import select, func, text
from app.core.database import AsyncSessionLocal
from app.models.events import RawTrip, SilverTrip, GoldHourlyDemand, PipelineRun, DataQualityLog
from app.services.data_cleaner import DataCleaner

logger = logging.getLogger(__name__)

class ETLPipeline:
    @staticmethod
    async def run_batch_ingestion(trips_data: List[Dict[str, Any]], source_name: str = "batch_file") -> Dict[str, Any]:
        """Full ETL Pipeline: Ingestion (Bronze) -> Validation & Cleaning (Silver) -> SQL Aggregations (Gold)."""
        start_time = time.time()
        ingested = 0
        deduplicated = 0
        failed = 0
        quality_failures = 0

        async with AsyncSessionLocal() as session:
            # 1. Create PipelineRun tracking record
            pipeline_run = PipelineRun(
                run_type="batch_etl",
                status="running",
                started_at=datetime.utcnow()
            )
            session.add(pipeline_run)
            await session.flush()

            silver_candidates = []

            for item in trips_data:
                try:
                    p_time = datetime.fromisoformat(str(item["pickup_datetime"]).replace("Z", ""))
                    d_time = datetime.fromisoformat(str(item["dropoff_datetime"]).replace("Z", ""))
                    p_loc = int(item["pickup_location_id"])
                    d_loc = int(item["dropoff_location_id"])
                    fare = float(item["fare_amount"])

                    event_id = item.get("event_id") or DataCleaner.generate_event_id(
                        p_time, d_time, p_loc, d_loc, fare
                    )

                    # Deduplication check
                    exists = await session.execute(select(RawTrip.id).where(RawTrip.event_id == event_id))
                    if exists.scalar_one_or_none():
                        deduplicated += 1
                        continue

                    raw = RawTrip(
                        event_id=event_id,
                        pickup_datetime=p_time,
                        dropoff_datetime=d_time,
                        passenger_count=int(item.get("passenger_count", 1)),
                        trip_distance=float(item.get("trip_distance", 1.0)),
                        pickup_location_id=p_loc,
                        dropoff_location_id=d_loc,
                        fare_amount=fare,
                        tip_amount=float(item.get("tip_amount", 0.0)),
                        total_amount=float(item.get("total_amount", fare)),
                        payment_type=str(item.get("payment_type", "Credit Card")),
                        is_replayed=bool(item.get("is_replayed", True)),
                        source_file=source_name,
                        ingested_at=datetime.utcnow()
                    )
                    session.add(raw)
                    ingested += 1

                    # Quality check & Silver conversion
                    valid, silver, issues = DataCleaner.validate_and_clean_trip(raw)
                    if valid and silver:
                        session.add(silver)
                        silver_candidates.append(silver)
                    else:
                        quality_failures += 1
                        if issues:
                            log_entry = DataQualityLog(
                                pipeline_run_id=pipeline_run.id,
                                test_name=issues[0]["test"],
                                category="data_cleaning",
                                status="rejected",
                                tested_records=1,
                                failed_records=1,
                                details=issues[0]["reason"],
                                created_at=datetime.utcnow()
                            )
                            session.add(log_entry)

                except Exception as e:
                    failed += 1
                    logger.warning("Error processing row in ETL: %s", e)

            await session.commit()

            # 2. Run Gold SQL Aggregations
            await ETLPipeline.run_gold_transformations()

            # 3. Finalize PipelineRun metrics
            duration = round(time.time() - start_time, 2)
            pipeline_run.status = "completed"
            pipeline_run.records_ingested = ingested
            pipeline_run.records_deduplicated = deduplicated
            pipeline_run.records_failed = failed + quality_failures
            pipeline_run.duration_seconds = duration
            pipeline_run.completed_at = datetime.utcnow()

            # Record overall data quality test pass log
            q_log = DataQualityLog(
                pipeline_run_id=pipeline_run.id,
                test_name="batch_ingestion_validation",
                category="pipeline_health",
                status="passed" if quality_failures == 0 else "warning",
                tested_records=ingested,
                failed_records=quality_failures,
                details=f"Ingested {ingested} raw, created {len(silver_candidates)} silver records, {deduplicated} duplicates filtered.",
                created_at=datetime.utcnow()
            )
            session.add(q_log)
            await session.commit()

            return {
                "run_id": pipeline_run.id,
                "status": "completed",
                "total_received": len(trips_data),
                "ingested": ingested,
                "deduplicated": deduplicated,
                "failed": failed + quality_failures,
                "duration_seconds": duration
            }

    @staticmethod
    async def run_gold_transformations():
        """SQL Transformations: Aggregate Silver trips into Gold hourly analytical tables."""
        async with AsyncSessionLocal() as session:
            # Query silver aggregated by hour and pickup location
            query = select(
                func.strftime('%Y-%m-%d %H:00:00', SilverTrip.pickup_datetime).label("time_bucket"),
                SilverTrip.pickup_location_id.label("location_id"),
                func.count(SilverTrip.id).label("trip_count"),
                func.sum(SilverTrip.passenger_count).label("total_passengers"),
                func.avg(SilverTrip.trip_distance).label("avg_distance"),
                func.avg(SilverTrip.fare_amount).label("avg_fare"),
                func.sum(SilverTrip.total_amount).label("total_revenue"),
                func.avg(SilverTrip.trip_duration_minutes).label("avg_duration")
            ).group_by("time_bucket", SilverTrip.pickup_location_id)

            res = await session.execute(query)
            rows = res.fetchall()

            for r in rows:
                bucket_dt = datetime.fromisoformat(r.time_bucket)
                loc_id = int(r.location_id)

                existing = await session.execute(
                    select(GoldHourlyDemand).where(
                        GoldHourlyDemand.time_bucket == bucket_dt,
                        GoldHourlyDemand.location_id == loc_id
                    )
                )
                gold_rec = existing.scalar_one_or_none()

                if gold_rec:
                    gold_rec.trip_count = int(r.trip_count)
                    gold_rec.total_passengers = int(r.total_passengers or 0)
                    gold_rec.avg_distance = round(float(r.avg_distance or 0.0), 2)
                    gold_rec.avg_fare = round(float(r.avg_fare or 0.0), 2)
                    gold_rec.total_revenue = round(float(r.total_revenue or 0.0), 2)
                    gold_rec.avg_duration_minutes = round(float(r.avg_duration or 0.0), 2)
                    gold_rec.updated_at = datetime.utcnow()
                else:
                    new_gold = GoldHourlyDemand(
                        time_bucket=bucket_dt,
                        location_id=loc_id,
                        trip_count=int(r.trip_count),
                        total_passengers=int(r.total_passengers or 0),
                        avg_distance=round(float(r.avg_distance or 0.0), 2),
                        avg_fare=round(float(r.avg_fare or 0.0), 2),
                        total_revenue=round(float(r.total_revenue or 0.0), 2),
                        avg_duration_minutes=round(float(r.avg_duration or 0.0), 2),
                        updated_at=datetime.utcnow()
                    )
                    session.add(new_gold)

            await session.commit()
            logger.info("Gold transformations completed. Upserted %d hourly buckets.", len(rows))

