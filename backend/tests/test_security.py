"""Cooldown on expensive public actions, and the CORS policy (see docs/security.md)."""
import pytest
from fastapi import HTTPException

from conftest import run  # also isolates the database; must come before app imports
from app.core.config import settings
from app.core.security import Cooldown, cooldown


def test_cooldown_blocks_a_repeat_inside_the_window_only():
    c = Cooldown()
    c.claim("train", 300, now=0.0)
    with pytest.raises(HTTPException) as blocked:
        c.claim("train", 300, now=10.0)
    assert blocked.value.status_code == 429
    assert blocked.value.headers["Retry-After"] == "290"
    c.claim("job:gold", 300, now=10.0)  # another action has its own window
    c.claim("train", 300, now=300.0)  # the window has passed
    for t in (301.0, 302.0):
        c.claim("other", 0, now=t)  # 0 turns the cooldown off


def _client():
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def test_job_endpoint_is_rate_limited_and_the_key_skips_the_wait(monkeypatch):
    from app.main import scheduler

    async def fake_run_job(name):
        return {"name": name, "last_status": "success"}

    monkeypatch.setattr(scheduler, "run_job", fake_run_job)
    monkeypatch.setattr(settings, "EXPENSIVE_ACTION_COOLDOWN_SECONDS", 300.0)
    cooldown.reset()
    job = next(iter(scheduler.jobs))

    async def scenario():
        async with _client() as client:
            url = f"/api/v1/health/jobs/{job}/run"
            assert (await client.post(url)).status_code == 200
            again = await client.post(url)
            assert again.status_code == 429
            assert int(again.headers["Retry-After"]) > 0
            assert "Try again" in again.json()["detail"]

            # Unknown names are rejected before the cooldown, so they never fill its table
            assert (await client.post("/api/v1/health/jobs/no-such-job/run")).status_code == 404
            assert "job:no-such-job" not in cooldown._last_run

            monkeypatch.setattr(settings, "API_KEY", "s3cret")
            assert (await client.post(url, headers={"X-API-Key": "wrong"})).status_code == 429
            assert (await client.post(url, headers={"X-API-Key": "s3cret"})).status_code == 200

    try:
        run(scenario())
    finally:
        cooldown.reset()


def test_train_endpoint_shares_the_cooldown(monkeypatch):
    from app.api.routes import ml

    async def fake_train(db):
        return {"best_model": "stub"}

    monkeypatch.setattr(ml, "train_and_score", fake_train)
    monkeypatch.setattr(settings, "EXPENSIVE_ACTION_COOLDOWN_SECONDS", 300.0)
    cooldown.reset()

    async def scenario():
        async with _client() as client:
            assert (await client.post("/api/v1/ml/train")).status_code == 200
            assert (await client.post("/api/v1/ml/train")).status_code == 429

    try:
        run(scenario())
    finally:
        cooldown.reset()


def test_cors_allows_only_configured_origins_and_no_credentials():
    async def scenario():
        async with _client() as client:
            preflight = {"Access-Control-Request-Method": "POST",
                         "Access-Control-Request-Headers": "X-API-Key"}
            ok = await client.options("/api/v1/ml/train",
                                      headers={"Origin": "http://localhost:3000", **preflight})
            assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
            assert "access-control-allow-credentials" not in ok.headers

            other = await client.options("/api/v1/ml/train",
                                         headers={"Origin": "https://attacker.example", **preflight})
            assert other.status_code == 400
            assert "access-control-allow-origin" not in other.headers

            read = await client.get("/api/info", headers={"Origin": "https://attacker.example"})
            assert "access-control-allow-origin" not in read.headers

    run(scenario())
