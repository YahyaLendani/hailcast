"""Trip detail for the map view: zone points, route, derived figures and comparisons."""
import json

from conftest import run  # also isolates the database; must come before app imports
from app.core.config import settings
from app.core.database import init_db
from app.core.zones import ZONES
from app.services.etl_pipeline import ETLPipeline


def test_trip_detail_has_route_and_comparisons():
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    async def scenario():
        await init_db()
        with open(settings.DATA_DIR / "sample_trips.json", "r", encoding="utf-8") as f:
            await ETLPipeline.run_batch_ingestion(json.load(f)[:300], source_name="map_test")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            trips = (await client.get("/api/v1/analytics/trips", params={"limit": 200})).json()
            cross = next(t for t in trips if t["pickup_location_id"] != t["dropoff_location_id"])

            detail = (await client.get(f"/api/v1/analytics/trips/{cross['id']}")).json()
            assert detail["trip"]["id"] == cross["id"]
            assert detail["pickup"]["lat"] == ZONES[cross["pickup_location_id"]][1]
            assert not detail["same_zone"]
            points = detail["route"]["points"]
            assert len(points) >= 2 and detail["route"]["road_miles"] > 0
            # The route starts and ends near the two zone centres (within about 1 km).
            assert abs(points[0][0] - detail["pickup"]["lat"]) < 0.01
            assert abs(points[-1][0] - detail["dropoff"]["lat"]) < 0.01
            assert "not the exact path" in detail["route_note"]

            compare = detail["compare"]
            assert compare["all_trips"] >= 300 and compare["same_route_trips"] >= 1
            assert 0 <= compare["slower_than_percent"] <= 100
            assert detail["derived"]["fare_per_mile"] > 0

            assert (await client.get("/api/v1/analytics/trips/99999999")).status_code == 404

    run(scenario())


def test_every_zone_pair_has_a_route():
    routes = json.loads((settings.DATA_DIR / "zone_routes.json").read_text(encoding="utf-8"))
    for a in ZONES:
        for b in ZONES:
            if a != b:
                assert len(routes[f"{a}-{b}"]["points"]) >= 2, f"{a}-{b}"
