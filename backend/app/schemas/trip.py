from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

class TripBase(BaseModel):
    pickup_datetime: datetime
    dropoff_datetime: datetime
    passenger_count: int = Field(default=1, ge=1, le=10)
    trip_distance: float = Field(ge=0.0)
    pickup_location_id: int = Field(ge=1, le=300)
    dropoff_location_id: int = Field(ge=1, le=300)
    fare_amount: float = Field(ge=0.0)
    tip_amount: float = Field(default=0.0, ge=0.0)
    total_amount: float = Field(ge=0.0)
    payment_type: str = "Credit Card"

class TripCreate(TripBase):
    event_id: Optional[str] = None
    is_replayed: bool = True  # Explicitly labeled as simulated real-time replayed event

class TripResponse(TripBase):
    id: int
    event_id: str
    trip_duration_minutes: Optional[float] = None
    speed_mph: Optional[float] = None
    is_replayed: bool
    ingested_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class BatchIngestRequest(BaseModel):
    trips: List[TripCreate]
    source_name: str = "batch_upload"

class BatchIngestResponse(BaseModel):
    run_id: int
    status: str
    total_received: int
    ingested: int
    deduplicated: int
    failed: int
    duration_seconds: float

class ReplayControlRequest(BaseModel):
    action: str = Field(..., description="'start', 'pause', 'resume', or 'stop'")
    speed_multiplier: float = Field(default=10.0, ge=1.0, le=100.0)
    batch_size: int = Field(default=10, ge=1, le=500)

class ReplayStatusResponse(BaseModel):
    is_active: bool
    is_paused: bool
    speed_multiplier: float
    events_replayed: int
    current_simulated_time: Optional[str] = None
    queue_depth: int
    total_buffered: int = 0

