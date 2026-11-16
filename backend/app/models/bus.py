from sqlalchemy import Column, DateTime, Float, Index, Integer, JSON, String

from app.core.clock import utc_now
from app.core.database import Base


class BusTrip(Base):
    """A finished NYC bus trip stitched from MTA Bus Time positions by app.collector."""
    __tablename__ = "bus_trips"

    id = Column(String(160), primary_key=True)  # vehicle + MTA trip id + service date
    route = Column(String(32), nullable=False, index=True)
    destination = Column(String(160), default="")
    vehicle = Column(String(32), nullable=False)
    start = Column(DateTime, nullable=False)  # New York local time
    end_utc = Column(DateTime, nullable=False, index=True)
    duration_s = Column(Integer, nullable=False)
    distance_km = Column(Float, nullable=False)
    avg_kmh = Column(Float, nullable=False)
    max_kmh = Column(Float, nullable=False)
    stopped_s = Column(Integer, nullable=False)
    gps_fixes = Column(Integer, nullable=False)
    points = Column(JSON, nullable=False)  # [[lat, lon, seconds], ...]
    speeds = Column(JSON, nullable=False)  # [[seconds, km/h], ...] one per pair of fixes
    stored_at = Column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (Index("idx_bus_route_end", "route", "end_utc"),)
