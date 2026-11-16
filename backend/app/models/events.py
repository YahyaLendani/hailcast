from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean, Text, Index
)
from app.core.database import Base
from app.core.clock import utc_now

class RawTrip(Base):
    """Bronze Tier: Raw immutable trip events as ingested from batches or streams."""
    __tablename__ = "raw_trips"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(64), unique=True, index=True, nullable=False)
    pickup_datetime = Column(DateTime, nullable=False, index=True)
    dropoff_datetime = Column(DateTime, nullable=False)
    passenger_count = Column(Integer, default=1)
    trip_distance = Column(Float, nullable=False)
    pickup_location_id = Column(Integer, nullable=False, index=True)
    dropoff_location_id = Column(Integer, nullable=False)
    fare_amount = Column(Float, nullable=False)
    tip_amount = Column(Float, default=0.0)
    total_amount = Column(Float, nullable=False)
    payment_type = Column(String(32), default="Credit Card")
    is_replayed = Column(Boolean, default=True, nullable=False)  # Clearly labels simulated real-time events
    source_file = Column(String(128), default="nyc_yellow_taxi")
    ingested_at = Column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        Index("idx_raw_pickup_time_loc", "pickup_datetime", "pickup_location_id"),
    )

class SilverTrip(Base):
    """Silver Tier: Cleaned, deduplicated, enriched trip records."""
    __tablename__ = "silver_trips"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(64), unique=True, index=True, nullable=False)
    pickup_datetime = Column(DateTime, nullable=False, index=True)
    dropoff_datetime = Column(DateTime, nullable=False)
    trip_duration_minutes = Column(Float, nullable=False)
    passenger_count = Column(Integer, default=1)
    trip_distance = Column(Float, nullable=False)
    pickup_location_id = Column(Integer, nullable=False, index=True)
    dropoff_location_id = Column(Integer, nullable=False)
    fare_amount = Column(Float, nullable=False)
    tip_amount = Column(Float, default=0.0)
    total_amount = Column(Float, nullable=False)
    speed_mph = Column(Float, default=0.0)
    payment_type = Column(String(32), default="Credit Card")
    is_replayed = Column(Boolean, default=True, nullable=False)
    processed_at = Column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        Index("idx_silver_pickup_time_loc", "pickup_datetime", "pickup_location_id"),
    )

class GoldHourlyDemand(Base):
    """Gold Tier: Pre-aggregated hourly analytics & feature-ready demand data."""
    __tablename__ = "gold_hourly_demand"

    id = Column(Integer, primary_key=True, autoincrement=True)
    time_bucket = Column(DateTime, nullable=False, index=True)
    location_id = Column(Integer, nullable=False, index=True)
    trip_count = Column(Integer, nullable=False, default=0)
    total_passengers = Column(Integer, nullable=False, default=0)
    avg_distance = Column(Float, nullable=False, default=0.0)
    avg_fare = Column(Float, nullable=False, default=0.0)
    total_revenue = Column(Float, nullable=False, default=0.0)
    avg_duration_minutes = Column(Float, nullable=False, default=0.0)
    anomaly_score = Column(Float, default=0.0)
    is_anomaly = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        Index("idx_gold_bucket_loc", "time_bucket", "location_id", unique=True),
    )

class PipelineRun(Base):
    """Pipeline orchestration & health tracking."""
    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_type = Column(String(32), nullable=False)  # batch, stream_replay, ml_training
    status = Column(String(32), nullable=False)    # running, completed, failed
    records_ingested = Column(Integer, default=0)
    records_deduplicated = Column(Integer, default=0)
    records_failed = Column(Integer, default=0)
    duration_seconds = Column(Float, default=0.0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, default=utc_now, nullable=False)
    completed_at = Column(DateTime, nullable=True)

class DataQualityLog(Base):
    """Data quality tests & validation statistics."""
    __tablename__ = "data_quality_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pipeline_run_id = Column(Integer, nullable=True)
    test_name = Column(String(64), nullable=False)
    category = Column(String(32), default="schema")
    status = Column(String(16), nullable=False)  # passed, warning, failed
    tested_records = Column(Integer, default=0)
    failed_records = Column(Integer, default=0)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

