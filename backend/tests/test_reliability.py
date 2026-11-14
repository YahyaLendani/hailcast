"""Streaming failure handling, scheduling, leakage and filter tests."""
import json

import numpy as np
import pandas as pd
from sqlalchemy import func, select

from conftest import run  # also isolates the database; must come before app imports
from app.core.config import settings
from app.core.database import AsyncSessionLocal, init_db
from app.ml.feature_engineering import FeatureEngineer
from app.models.events import RawTrip
from app.services import streaming_worker as worker_module
from app.services.etl_pipeline import ETLPipeline
from app.services.scheduler import Scheduler
from app.services.streaming_worker import StreamingWorker


def _event(i: int, **overrides):
    data = {
        "event_id": f"reliability-{i}",
        "pickup_datetime": f"2026-10-01T10:{i:02d}:00",
        "dropoff_datetime": f"2026-10-01T10:{i + 12:02d}:00",
        "passenger_count": 1,
        "trip_distance": 2.5,
        "pickup_location_id": 161,
        "dropoff_location_id": 237,
        "fare_amount": 14.0,
        "tip_amount": 2.0,
        "total_amount": 18.5,
        "payment_type": "Credit Card",
    }
    data.update(overrides)
    return {"stream_id": f"mem-{i}", "payload": {"data": data}}


async def _count(prefix: str) -> int:
    async with AsyncSessionLocal() as session:
        return (await session.execute(
            select(func.count(RawTrip.id)).where(RawTrip.event_id.like(f"{prefix}%"))
        )).scalar_one()


def test_bad_event_is_dead_lettered_and_good_events_survive():
    async def scenario():
        await init_db()
        worker = StreamingWorker()
        bad = _event(2)
        del bad["payload"]["data"]["pickup_datetime"]
        events = [_event(1), bad, _event(3)]

        await worker._process_with_retry(events)
        assert worker.failed_count == 1
        assert len(worker.dead_letters) == 1
        assert "KeyError" in worker.dead_letters[0]["error"]
        assert await _count("reliability-") == 2

        # Replaying the same events must not store them twice.
        await worker._process_with_retry([_event(1), _event(3)])
        assert worker.deduplicated_count == 2
        assert await _count("reliability-") == 2

    run(scenario())


def test_transient_failure_is_retried_with_backoff(monkeypatch):
    monkeypatch.setattr(worker_module, "BACKOFF_BASE_SECONDS", 0)
    worker = StreamingWorker()
    calls = []

    async def flaky(events):
        calls.append(len(events))
        if len(calls) < 3:
            raise ConnectionError("database is locked")

    monkeypatch.setattr(worker, "_process_batch", flaky)
    run(worker._process_with_retry([_event(10), _event(11)]))
    assert calls == [2, 2, 2]
    assert worker.retried_count == 2
    assert worker.failed_count == 0 and not worker.dead_letters


def test_scheduler_records_success_and_failure():
    async def scenario():
        scheduler = Scheduler()

        async def ok():
            return None

        async def boom():
            raise RuntimeError("no database")

        scheduler.add_job("ok", "works", 60, ok)
        scheduler.add_job("boom", "fails", 60, boom)
        good = await scheduler.run_job("ok")
        bad = await scheduler.run_job("boom")
        assert good["last_status"] == "success" and good["failures"] == 0
        assert bad["last_status"] == "failed" and bad["failures"] == 1
        assert "no database" in bad["last_error"]

    run(scenario())


def test_features_never_use_the_future():
    """Changing demand from hour t onward must not change any feature before hour t."""
    rng = np.random.default_rng(7)
    hours = pd.date_range("2026-10-01", periods=96, freq="h")
    base = pd.DataFrame({"time_bucket": hours, "trip_count": rng.integers(20, 200, size=96)})
    changed = base.copy()
    cut = 60
    changed.loc[cut:, "trip_count"] = changed.loc[cut:, "trip_count"] * 10 + 999

    feat_a, cols = FeatureEngineer.create_features(base)
    feat_b, _ = FeatureEngineer.create_features(changed)
    before_a = feat_a[feat_a["time_bucket"] <= hours[cut]].set_index("time_bucket")[cols]
    before_b = feat_b[feat_b["time_bucket"] <= hours[cut]].set_index("time_bucket")[cols]
    assert len(before_a) > 0
    pd.testing.assert_frame_equal(before_a, before_b)
    assert "trip_count" not in cols


def test_uploads_need_the_api_key_when_one_is_set(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    async def scenario():
        await init_db()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            seed = "/api/v1/ingest/seed-sample?sample_size=5"
            assert (await client.post(seed)).status_code == 200  # no key configured: open

            monkeypatch.setattr(settings, "API_KEY", "s3cret")
            assert (await client.post(seed)).status_code == 401
            assert (await client.post(seed, headers={"X-API-Key": "wrong"})).status_code == 401
            assert (await client.post(seed, headers={"X-API-Key": "s3cret"})).status_code == 200
            # Reading and the replay status stay public
            assert (await client.get("/api/v1/analytics/filters")).status_code == 200
            assert (await client.get("/api/v1/stream/status")).status_code == 200

    run(scenario())


def test_trip_and_demand_filters():
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    async def scenario():
        await init_db()
        with open(settings.DATA_DIR / "sample_trips.json", "r", encoding="utf-8") as f:
            await ETLPipeline.run_batch_ingestion(json.load(f)[:400], source_name="filter_test")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            options = (await client.get("/api/v1/analytics/filters")).json()
            assert options["zones"] and options["payment_types"] and options["first_pickup"]
            zone = options["zones"][0]["location_id"]
            pay = options["payment_types"][0]

            trips = (await client.get("/api/v1/analytics/trips",
                                      params={"location_id": zone, "payment_type": pay, "limit": 200})).json()
            assert all(t["pickup_location_id"] == zone and t["payment_type"] == pay for t in trips)

            day = options["first_pickup"][:10]
            series = (await client.get("/api/v1/analytics/demand-series",
                                       params={"start": f"{day}T00:00:00", "end": f"{day}T23:59:59"})).json()
            assert series and all(row["time_bucket"][:10] == day for row in series)
            total_all = sum(row["trip_count"] for row in series)
            one_zone = (await client.get("/api/v1/analytics/demand-series",
                                         params={"start": f"{day}T00:00:00", "end": f"{day}T23:59:59",
                                                 "location_id": zone})).json()
            assert sum(row["trip_count"] for row in one_zone) <= total_all

    run(scenario())
