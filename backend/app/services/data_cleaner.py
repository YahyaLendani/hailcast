import hashlib
from datetime import datetime
from typing import Tuple, Dict, Any, List, Optional
from app.models.events import RawTrip, SilverTrip, DataQualityLog

class DataCleaner:
    @staticmethod
    def generate_event_id(pickup_time: datetime, dropoff_time: datetime, p_loc: int, d_loc: int, fare: float) -> str:
        """Deterministic SHA256 event ID for idempotent event processing & deduplication."""
        raw_key = f"{pickup_time.isoformat()}_{dropoff_time.isoformat()}_{p_loc}_{d_loc}_{round(fare, 2)}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def validate_and_clean_trip(trip: RawTrip) -> Tuple[bool, Optional[SilverTrip], List[Dict[str, Any]]]:
        """Validate trip against data engineering quality standards and create Silver record."""
        quality_issues = []

        # 1. Temporal validity
        if trip.dropoff_datetime <= trip.pickup_datetime:
            quality_issues.append({"test": "temporal_sequence", "reason": "dropoff_datetime <= pickup_datetime"})

        duration_minutes = (trip.dropoff_datetime - trip.pickup_datetime).total_seconds() / 60.0
        if duration_minutes < 1.0 or duration_minutes > 240.0:
            quality_issues.append({"test": "duration_range", "reason": f"Duration {duration_minutes:.1f}m outside 1-240m range"})

        # 2. Distance checks
        if trip.trip_distance <= 0.0 or trip.trip_distance > 150.0:
            quality_issues.append({"test": "distance_range", "reason": f"Distance {trip.trip_distance} outside (0, 150] miles"})

        # 3. Fare checks
        if trip.fare_amount < 2.50 or trip.fare_amount > 600.0:
            quality_issues.append({"test": "fare_range", "reason": f"Fare ${trip.fare_amount} outside [2.50, 600.00]"})

        # 4. Speed reasonableness
        speed_mph = (trip.trip_distance / (duration_minutes / 60.0)) if duration_minutes > 0 else 0.0
        if speed_mph > 85.0:
            quality_issues.append({"test": "speed_limit", "reason": f"Calculated speed {speed_mph:.1f} mph exceeds 85 mph threshold"})

        # 5. Passenger range
        if trip.passenger_count < 1 or trip.passenger_count > 9:
            quality_issues.append({"test": "passenger_count", "reason": f"Passenger count {trip.passenger_count} outside 1-9"})

        # If critical validation fails, reject from Silver
        if quality_issues:
            return False, None, quality_issues

        silver = SilverTrip(
            event_id=trip.event_id,
            pickup_datetime=trip.pickup_datetime,
            dropoff_datetime=trip.dropoff_datetime,
            trip_duration_minutes=round(duration_minutes, 2),
            passenger_count=trip.passenger_count,
            trip_distance=round(trip.trip_distance, 2),
            pickup_location_id=trip.pickup_location_id,
            dropoff_location_id=trip.dropoff_location_id,
            fare_amount=round(trip.fare_amount, 2),
            tip_amount=round(trip.tip_amount, 2),
            total_amount=round(trip.total_amount, 2),
            speed_mph=round(speed_mph, 1),
            payment_type=trip.payment_type,
            is_replayed=trip.is_replayed,
            processed_at=datetime.utcnow()
        )
        return True, silver, quality_issues
