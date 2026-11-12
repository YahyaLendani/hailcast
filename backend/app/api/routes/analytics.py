from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from app.core.database import get_db
from app.models.events import RawTrip, SilverTrip, GoldHourlyDemand
from app.schemas.analytics import AnalyticsOverview, HourlyDemandPoint, ZoneDemand
from app.schemas.trip import TripResponse

router = APIRouter(prefix="/analytics", tags=["Analytics"])

ZONE_NAMES = {
    161: "Midtown Center",
    236: "Upper East Side North",
    237: "Upper East Side South",
    186: "Penn Station / Madison Sq West",
    142: "Lincoln Square East",
    230: "Times Square / Theatre District",
    138: "LaGuardia Airport",
    132: "JFK Airport",
    79:  "East Village",
    148: "Lower East Side",
    234: "Flatiron",
    107: "Gramercy"
}

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
    db: AsyncSession = Depends(get_db)
):
    """Explore cleaned historical trip records."""
    query = select(SilverTrip).order_by(SilverTrip.pickup_datetime.desc()).offset(offset).limit(limit)
    res = await db.execute(query)
    return res.scalars().all()

