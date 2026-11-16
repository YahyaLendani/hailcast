import json
from datetime import datetime
from functools import lru_cache
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import case, desc, func, select
from app.core.config import settings
from app.core.database import get_db
from app.core.zones import ZONES, ZONE_NAMES
from app.models.events import SilverTrip, GoldHourlyDemand
from app.schemas.analytics import AnalyticsOverview, HourlyDemandPoint, ZoneDemand
from app.schemas.trip import TripResponse

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/overview", response_model=AnalyticsOverview)
async def get_overview(db: AsyncSession = Depends(get_db)):
    """Summary KPI metrics for the analytics dashboard."""
    total_trips = (await db.execute(select(func.count(SilverTrip.id)))).scalar_one() or 0
    total_rev = (await db.execute(select(func.sum(SilverTrip.total_amount)))).scalar_one() or 0.0
    avg_fare = (await db.execute(select(func.avg(SilverTrip.fare_amount)))).scalar_one() or 0.0
    avg_dist = (await db.execute(select(func.avg(SilverTrip.trip_distance)))).scalar_one() or 0.0
    avg_dur = (await db.execute(select(func.avg(SilverTrip.trip_duration_minutes)))).scalar_one() or 0.0
    anomalies = (await db.execute(select(func.count(GoldHourlyDemand.id)).where(GoldHourlyDemand.is_anomaly == True))).scalar_one() or 0
    active_zones = (await db.execute(select(func.count(func.distinct(SilverTrip.pickup_location_id))))).scalar_one() or 0

    return AnalyticsOverview(
        total_trips=total_trips,
        total_revenue=round(float(total_rev), 2),
        avg_fare=round(float(avg_fare), 2),
        avg_trip_distance=round(float(avg_dist), 2),
        avg_duration_minutes=round(float(avg_dur), 1),
        total_anomalies=anomalies,
        active_pickup_zones=active_zones,
        data_freshness_seconds=1.2
    )

@router.get("/hourly-demand", response_model=List[HourlyDemandPoint])
async def get_hourly_demand(
    location_id: Optional[int] = Query(None, description="Optional pickup zone filter"),
    limit: int = Query(168, le=500),
    db: AsyncSession = Depends(get_db)
):
    """Hourly aggregated demand time-series for charts and anomaly display."""
    query = select(GoldHourlyDemand)
    if location_id:
        query = query.where(GoldHourlyDemand.location_id == location_id)
    query = query.order_by(GoldHourlyDemand.time_bucket.asc()).limit(limit)

    res = await db.execute(query)
    records = res.scalars().all()
    return records

@router.get("/zones", response_model=List[ZoneDemand])
async def get_top_zones(limit: int = Query(10, le=50), db: AsyncSession = Depends(get_db)):
    """Top pickup zones by demand and total revenue."""
    query = select(
        SilverTrip.pickup_location_id.label("location_id"),
        func.count(SilverTrip.id).label("trip_count"),
        func.sum(SilverTrip.total_amount).label("total_revenue"),
        func.avg(SilverTrip.fare_amount).label("avg_fare")
    ).group_by(SilverTrip.pickup_location_id).order_by(desc("trip_count")).limit(limit)

    res = await db.execute(query)
    rows = res.fetchall()
    
    return [
        ZoneDemand(
            location_id=r.location_id,
            zone_name=ZONE_NAMES.get(r.location_id, f"Zone {r.location_id}"),
            trip_count=r.trip_count,
            total_revenue=round(float(r.total_revenue or 0.0), 2),
            avg_fare=round(float(r.avg_fare or 0.0), 2)
        )
        for r in rows
    ]

@router.get("/trips", response_model=List[TripResponse])
async def get_trips(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    location_id: Optional[int] = Query(None, description="Pickup zone filter"),
    payment_type: Optional[str] = Query(None, description="Payment type filter"),
    start: Optional[datetime] = Query(None, description="Earliest pickup time (inclusive)"),
    end: Optional[datetime] = Query(None, description="Latest pickup time (inclusive)"),
    db: AsyncSession = Depends(get_db)
):
    """Explore cleaned historical trip records, newest first."""
    query = select(SilverTrip)
    if location_id is not None:
        query = query.where(SilverTrip.pickup_location_id == location_id)
    if payment_type:
        query = query.where(SilverTrip.payment_type == payment_type)
    if start is not None:
        query = query.where(SilverTrip.pickup_datetime >= start)
    if end is not None:
        query = query.where(SilverTrip.pickup_datetime <= end)
    query = query.order_by(SilverTrip.pickup_datetime.desc()).offset(offset).limit(limit)
    res = await db.execute(query)
    return res.scalars().all()


@lru_cache(maxsize=1)
def _zone_routes() -> dict:
    """Road routes between zone centres, precomputed by backend/scripts/build_zone_routes.py."""
    path = settings.DATA_DIR / "zone_routes.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _zone_point(location_id: int) -> dict:
    name, lat, lon = ZONES.get(location_id, (f"Zone {location_id}", None, None))
    return {"location_id": location_id, "zone_name": name, "lat": lat, "lon": lon}


@router.get("/trips/{trip_id}")
async def get_trip_detail(trip_id: int, db: AsyncSession = Depends(get_db)):
    """One cleaned trip placed on the map, with derived figures and how it compares to others.

    The records hold pickup and drop-off zones, not GPS points, so the route is the likely road
    route between the two zone centres (OpenStreetMap data via OSRM), not the path the cab drove.
    """
    trip = await db.get(SilverTrip, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")

    same_zone = trip.pickup_location_id == trip.dropoff_location_id
    route = None if same_zone else _zone_routes().get(f"{trip.pickup_location_id}-{trip.dropoff_location_id}")

    speed = trip.speed_mph or 0.0
    total, slower, city_speed, city_fare_mile = (await db.execute(select(
        func.count(SilverTrip.id),
        func.sum(case((SilverTrip.speed_mph < speed, 1), else_=0)),
        func.avg(SilverTrip.speed_mph),
        func.avg(SilverTrip.fare_amount / func.nullif(SilverTrip.trip_distance, 0)),
    ))).one()
    pair_count, pair_fare, pair_minutes, pair_speed = (await db.execute(select(
        func.count(SilverTrip.id),
        func.avg(SilverTrip.total_amount),
        func.avg(SilverTrip.trip_duration_minutes),
        func.avg(SilverTrip.speed_mph),
    ).where(
        SilverTrip.pickup_location_id == trip.pickup_location_id,
        SilverTrip.dropoff_location_id == trip.dropoff_location_id,
    ))).one()

    distance = trip.trip_distance or 0.0
    minutes = trip.trip_duration_minutes or 0.0
    return {
        "trip": TripResponse.model_validate(trip).model_dump(mode="json"),
        "pickup": _zone_point(trip.pickup_location_id),
        "dropoff": _zone_point(trip.dropoff_location_id),
        "same_zone": same_zone,
        "route": route,
        "route_note": (
            "Pickup and drop-off are in the same zone, so there is no route between zones to draw."
            if same_zone else
            "The record has zones, not GPS points. The line is the likely road route between the two "
            "zone centres, not the exact path the cab drove."
        ),
        "derived": {
            "fare_per_mile": round(trip.fare_amount / distance, 2) if distance else None,
            "fare_per_minute": round(trip.fare_amount / minutes, 2) if minutes else None,
            "tip_percent": round(100 * (trip.tip_amount or 0) / trip.fare_amount, 1) if trip.fare_amount else None,
        },
        "compare": {
            "all_trips": total,
            "slower_than_percent": round(100 * (slower or 0) / total, 1) if total else None,
            "city_avg_speed_mph": round(city_speed, 1) if city_speed is not None else None,
            "city_avg_fare_per_mile": round(city_fare_mile, 2) if city_fare_mile is not None else None,
            "same_route_trips": pair_count,
            "same_route_avg_total": round(pair_fare, 2) if pair_fare is not None else None,
            "same_route_avg_minutes": round(pair_minutes, 1) if pair_minutes is not None else None,
            "same_route_avg_speed_mph": round(pair_speed, 1) if pair_speed is not None else None,
        },
    }


@lru_cache(maxsize=1)
def _gps_sample() -> dict:
    """Real Porto taxi trips with GPS, built by backend/scripts/build_porto_sample.py."""
    path = settings.DATA_DIR / "porto_trips.json"
    if not path.exists():
        return {"source": None, "trips": []}
    return json.loads(path.read_text(encoding="utf-8"))


_GPS_SUMMARY_FIELDS = ("id", "start", "call_type", "snapped_to_roads", "duration_s", "distance_km",
                       "avg_kmh", "max_kmh", "stopped_s", "gps_fixes")


@router.get("/gps-trips")
async def list_gps_trips():
    """Real taxi trips from Porto with a GPS fix every 15 seconds (CC BY 4.0 sample)."""
    sample = _gps_sample()
    return {
        "source": sample["source"],
        "trips": [{k: t[k] for k in _GPS_SUMMARY_FIELDS} for t in sample["trips"]],
    }


@router.get("/gps-trips/{trip_id}")
async def get_gps_trip(trip_id: str):
    """One real trip: its road-snapped path with a time for every point, speed per 15 seconds,
    and how it compares with the rest of the sample."""
    trips = _gps_sample()["trips"]
    trip = next((t for t in trips if t["id"] == trip_id), None)
    if trip is None:
        raise HTTPException(status_code=404, detail="GPS trip not found")
    speeds = [t["avg_kmh"] for t in trips]
    return {
        **trip,
        "compare": {
            "sample_trips": len(trips),
            "slower_than_percent": round(100 * sum(s < trip["avg_kmh"] for s in speeds) / len(speeds), 1),
            "sample_avg_kmh": round(sum(speeds) / len(speeds), 1),
            "sample_avg_minutes": round(sum(t["duration_s"] for t in trips) / len(trips) / 60, 1),
            "sample_avg_km": round(sum(t["distance_km"] for t in trips) / len(trips), 2),
        },
    }


@router.get("/filters")
async def get_filter_options(db: AsyncSession = Depends(get_db)):
    """Values the dashboard can filter by: pickup zones, payment types and the date span."""
    zone_ids = (await db.execute(select(SilverTrip.pickup_location_id).distinct())).scalars().all()
    payments = (await db.execute(select(SilverTrip.payment_type).distinct())).scalars().all()
    first, last = (await db.execute(
        select(func.min(SilverTrip.pickup_datetime), func.max(SilverTrip.pickup_datetime))
    )).one()
    zones = sorted(
        ({"location_id": z, "zone_name": ZONE_NAMES.get(z, f"Zone {z}")} for z in zone_ids if z is not None),
        key=lambda z: z["zone_name"],
    )
    return {
        "zones": zones,
        "payment_types": sorted(p for p in payments if p),
        "first_pickup": first.isoformat() if first else None,
        "last_pickup": last.isoformat() if last else None,
    }


@router.get("/demand-series")
async def get_demand_series(
    hours: int = Query(72, ge=1, le=336, description="Most recent hours to return when no dates are given"),
    location_id: Optional[int] = Query(None, description="Pickup zone filter"),
    start: Optional[datetime] = Query(None, description="Earliest hour (inclusive)"),
    end: Optional[datetime] = Query(None, description="Latest hour (inclusive)"),
    db: AsyncSession = Depends(get_db)
):
    """Hourly demand, oldest first: all zones summed, or one zone when location_id is given."""
    query = select(
        GoldHourlyDemand.time_bucket,
        func.sum(GoldHourlyDemand.trip_count),
        func.sum(GoldHourlyDemand.total_revenue),
        func.sum(func.coalesce(GoldHourlyDemand.is_anomaly, False)),
    )
    if location_id is not None:
        query = query.where(GoldHourlyDemand.location_id == location_id)
    if start is not None:
        query = query.where(GoldHourlyDemand.time_bucket >= start)
    if end is not None:
        query = query.where(GoldHourlyDemand.time_bucket <= end)
    limit = 336 if (start is not None or end is not None) else hours
    query = query.group_by(GoldHourlyDemand.time_bucket).order_by(GoldHourlyDemand.time_bucket.desc()).limit(limit)
    rows = (await db.execute(query)).all()
    return [
        {
            "time_bucket": bucket.isoformat(),
            "trip_count": int(trips or 0),
            "total_revenue": round(float(revenue or 0.0), 2),
            "anomalous_zones": int(anomalies or 0),
        }
        for bucket, trips, revenue, anomalies in reversed(rows)
    ]
