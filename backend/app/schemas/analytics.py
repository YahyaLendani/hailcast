from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

class HourlyDemandPoint(BaseModel):
    time_bucket: datetime
    location_id: int
    trip_count: int
    total_revenue: float
    avg_fare: float
    avg_distance: float
    anomaly_score: float
    is_anomaly: bool

    class Config:
        from_attributes = True

class AnalyticsOverview(BaseModel):
    total_trips: int
    total_revenue: float
    avg_fare: float
    avg_trip_distance: float
    avg_duration_minutes: float
    total_anomalies: int
    active_pickup_zones: int
    data_freshness_seconds: float

class ZoneDemand(BaseModel):
    location_id: int
    zone_name: str
    trip_count: int
    total_revenue: float
    avg_fare: float

class PipelineHealthMetrics(BaseModel):
    raw_trips_count: int
    silver_trips_count: int
    gold_records_count: int
    deduplication_rate_percent: float
    ingestion_rate_eps: float  # events per second
    stream_backend: str
    stream_length: int
    pending_queue_size: int
    recent_runs: List[Dict[str, Any]]
    data_quality_tests: List[Dict[str, Any]]

