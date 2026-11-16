"""Live NYC buses: SIRI parsing, trip stitching and the /live-bus-trips endpoints."""
from datetime import datetime, timedelta, timezone

from conftest import run  # also isolates the database; must come before app imports
from app.collector import mta
from app.collector.stitcher import Stitcher

T0 = datetime(2026, 11, 16, 15, 0, 0, tzinfo=timezone.utc)  # 10:00 in New York


def activity(vehicle, trip, at, lat, lon, status=None, line="B63"):
    """One VehicleActivity in the shape of MTA SIRI VehicleMonitoring v2 JSON."""
    journey = {
        "LineRef": f"MTA NYCT_{line}",
        "PublishedLineName": [line],
        "DestinationName": ["BAY RIDGE"],
        "FramedVehicleJourneyRef": {"DataFrameRef": "2026-11-16", "DatedVehicleJourneyRef": f"MTA NYCT_{trip}"},
        "VehicleLocation": {"Longitude": lon, "Latitude": lat},
        "VehicleRef": f"MTA NYCT_{vehicle}",
    }
    if status:
        journey["ProgressStatus"] = [status]
    return {"RecordedAtTime": at.isoformat().replace("+00:00", "Z"), "MonitoredVehicleJourney": journey}


def payload(*activities):
    return {"Siri": {"ServiceDelivery": {"VehicleMonitoringDelivery": [{"VehicleActivity": list(activities)}]}}}


def drive(stitcher, polls, step=30):
    """Bus 7582 waits on layover, then runs trip A north at 24 km/h with one GPS glitch;
    bus 1111 makes a trip too short to keep."""
    finished = []
    for k in range(polls):
        at = T0 + timedelta(seconds=step * k)
        acts = []
        if k < 3:
            acts.append(activity("7582", "A", at, 40.6400, -74.0300, status="layover"))
        else:
            lat = 40.6400 + 0.0018 * (k - 3)  # 200 m per 30 s = 24 km/h
            if k == 10:
                lat += 0.05  # a 5 km jump in 30 s: a glitch
            acts.append(activity("7582", "A", at, lat, -74.0300))
        if k < 4:
            acts.append(activity("1111", "B", at, 40.7, -73.9 + 0.001 * k, line="M15"))
        finished += stitcher.feed(mta.parse(payload(*acts)), at)
    return finished


def test_parse_reads_siri_and_skips_layovers():
    at = T0
    fixes = mta.parse(payload(activity("7582", "A", at, 40.64, -74.03),
                              activity("9", "C", at, 40.6, -74.0, status="layover"),
                              {"RecordedAtTime": at.isoformat(), "MonitoredVehicleJourney": {}}))
    assert len(fixes) == 1
    f = fixes[0]
    assert (f.vehicle, f.trip_ref, f.route, f.destination) == ("7582", "A", "B63", "BAY RIDGE")
    assert f.at == at and f.lat == 40.64
    assert mta.parse({}) == []


def test_stitcher_closes_trips_and_drops_glitches():
    s = Stitcher()
    finished = drive(s, 40)
    assert finished == []  # still running; bus 1111 is idle but not yet for five minutes
    later = T0 + timedelta(seconds=30 * 39)
    # Bus 7582 starts its next trip: trip A closes at once.
    finished = s.feed(mta.parse(payload(activity("7582", "Z", later + timedelta(seconds=30), 40.7, -74.03))), later)
    assert len(finished) == 1  # bus 1111 closed too (idle), but 4 fixes is too short to keep
    trip = finished[0]
    assert trip["route"] == "B63" and trip["vehicle"] == "7582"
    assert trip["gps_fixes"] == 36  # 37 running fixes minus the glitch
    assert trip["start"] == datetime(2026, 11, 16, 10, 1, 30)  # New York time of the first running fix
    assert trip["duration_s"] == 36 * 30
    assert 22 < trip["avg_kmh"] < 26 and trip["max_kmh"] < 50
    assert trip["stopped_s"] == 0
    assert trip["points"][0][2] == 0 and trip["points"][-1][2] == trip["duration_s"]
    assert len(trip["points"]) < trip["gps_fixes"]  # steady motion simplifies away
    assert len(trip["speeds"]) == trip["gps_fixes"] - 1
    assert trip["id"].startswith("7582-202611161001-")


def test_idle_trip_closes_after_five_minutes():
    s = Stitcher()
    drive(s, 40)
    assert s.feed([], T0 + timedelta(seconds=30 * 39 + 299)) == []
    assert len(s.feed([], T0 + timedelta(seconds=30 * 39 + 301))) == 1


def test_live_bus_endpoints():
    from httpx import ASGITransport, AsyncClient
    from app.collector.run import store
    from app.core.database import init_db
    from app.main import app

    s = Stitcher()
    drive(s, 40)
    trip = s.feed([], T0 + timedelta(hours=1))[0]
    slow = {**trip, "id": "slow", "route": "M15", "avg_kmh": 5.0,
            "end_utc": trip["end_utc"] - timedelta(minutes=1)}

    async def scenario():
        await init_db()
        await store([trip, slow])
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            listing = (await client.get("/api/v1/analytics/live-bus-trips")).json()
            assert listing["source"]["name"] == "MTA Bus Time"
            assert [t["id"] for t in listing["trips"]] == [trip["id"], "slow"]  # newest first
            assert "points" not in listing["trips"][0]
            only = (await client.get("/api/v1/analytics/live-bus-trips", params={"route": "m15"})).json()
            assert [t["id"] for t in only["trips"]] == ["slow"]

            d = (await client.get(f"/api/v1/analytics/live-bus-trips/{trip['id']}")).json()
            assert d["points"] == trip["points"] and d["start"] == "2026-11-16T10:01:30"
            c = d["compare"]
            assert c["sample_trips"] == 2 and c["slower_than_percent"] == 50.0
            assert c["route_trips"] == 1 and c["route_slower_than_percent"] == 0.0
            assert (await client.get("/api/v1/analytics/live-bus-trips/nope")).status_code == 404

    run(scenario())
