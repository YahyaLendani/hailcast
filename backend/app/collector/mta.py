"""Read bus positions from the MTA Bus Time SIRI VehicleMonitoring feed (JSON).

Docs: https://bustime.mta.info/wiki/Developers/SIRIVehicleMonitoring. The MTA asks clients to poll
no more than once every 30 seconds. The API key is read from the environment, never from git.
"""
from datetime import datetime

from app.collector.stitcher import Fix

FEED_URL = "https://bustime.mta.info/api/siri/vehicle-monitoring.json"


def _text(value):
    """SIRI fields are sometimes a string and sometimes a one-item list of strings."""
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "")


def _short(ref):
    """'MTA NYCT_B63' -> 'B63'; agency prefixes add nothing on the map."""
    ref = _text(ref)
    return ref.split("_", 1)[1] if "_" in ref else ref


def parse(payload: dict):
    """All usable fixes in one feed response. Buses on layover or still finishing a previous trip are
    left out, so a trip covers only the time the bus was running it."""
    fixes = []
    deliveries = payload.get("Siri", {}).get("ServiceDelivery", {}).get("VehicleMonitoringDelivery", [])
    for delivery in deliveries:
        for activity in delivery.get("VehicleActivity", []):
            journey = activity.get("MonitoredVehicleJourney") or {}
            status = _text(journey.get("ProgressStatus"))
            if "layover" in status or "prevTrip" in status:
                continue
            loc = journey.get("VehicleLocation") or {}
            frame = journey.get("FramedVehicleJourneyRef") or {}
            vehicle, trip_ref = _short(journey.get("VehicleRef")), _short(frame.get("DatedVehicleJourneyRef"))
            recorded = activity.get("RecordedAtTime")
            if not (vehicle and trip_ref and recorded and "Latitude" in loc and "Longitude" in loc):
                continue
            try:
                at = datetime.fromisoformat(recorded.replace("Z", "+00:00"))
            except ValueError:
                continue
            if at.tzinfo is None:
                continue
            fixes.append(Fix(
                vehicle=vehicle,
                trip_ref=trip_ref,
                route=_text(journey.get("PublishedLineName")) or _short(journey.get("LineRef")),
                destination=_text(journey.get("DestinationName")),
                at=at,
                lat=float(loc["Latitude"]),
                lon=float(loc["Longitude"]),
            ))
    return fixes


async def fetch(client, api_key: str) -> dict:
    resp = await client.get(FEED_URL, params={"key": api_key, "version": "2"}, timeout=60)
    resp.raise_for_status()
    return resp.json()
