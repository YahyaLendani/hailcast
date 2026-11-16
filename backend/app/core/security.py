"""Access control for the API. docs/security.md explains what is public and why.

Uploads (arbitrary data): when the API_KEY setting is empty (local development) the
endpoints are open. When it is set (the hosted demo) callers must send it in the
X-API-Key header.

Expensive actions (retraining, running a pipeline job): public, because the dashboard's
buttons call them, but rate-limited by a shared cooldown so a loop of requests cannot
keep the server busy. A valid X-API-Key skips the cooldown.

Replay controls stay public on purpose: they only re-stream the built-in sample.
"""
import math
import secrets
import time
from typing import Dict, Optional

from fastapi import Header, HTTPException

from app.core.config import settings


def has_valid_api_key(x_api_key: Optional[str]) -> bool:
    """True when a key is configured and `x_api_key` matches it (constant-time)."""
    expected = settings.API_KEY
    return bool(expected) and secrets.compare_digest((x_api_key or "").encode(), expected.encode())


async def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    if settings.API_KEY and not has_valid_api_key(x_api_key):
        raise HTTPException(
            status_code=401,
            detail="This endpoint needs a valid X-API-Key header on this server.",
        )


class Cooldown:
    """At most one run of each named action per window, shared by every caller.

    The window is global, not per client: the point is to cap the server's work, and
    client addresses behind Render's proxy are easy to vary. The check and the update
    run with no `await` between them, so concurrent requests cannot both pass.
    """

    def __init__(self) -> None:
        self._last_run: Dict[str, float] = {}

    def claim(self, action: str, seconds: float, now: Optional[float] = None) -> None:
        """Record a run of `action`, or raise 429 if the last one was too recent."""
        now = time.monotonic() if now is None else now
        last = self._last_run.get(action)
        if seconds > 0 and last is not None:
            wait = seconds - (now - last)
            if wait > 0:
                retry_after = math.ceil(wait)
                raise HTTPException(
                    status_code=429,
                    detail=f"This ran recently on the public demo. Try again in {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)},
                )
        self._last_run[action] = now

    def reset(self) -> None:
        self._last_run.clear()


cooldown = Cooldown()


def limit_expensive_action(action: str, x_api_key: Optional[str]) -> None:
    """Apply the shared cooldown to `action` unless the caller holds the API key.

    Callers must validate `action` first (for example, that a job name exists), so
    unknown names never become entries in the cooldown table.
    """
    if has_valid_api_key(x_api_key):
        return
    cooldown.claim(action, settings.EXPENSIVE_ACTION_COOLDOWN_SECONDS)
