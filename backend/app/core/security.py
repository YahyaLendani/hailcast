"""Optional API-key protection for endpoints that write arbitrary data.

When the API_KEY setting is empty (local development) the endpoints are open.
When it is set (the hosted demo) callers must send it in the X-API-Key header.
Replay controls stay public on purpose: they only re-stream the built-in sample.
"""
import secrets
from typing import Optional

from fastapi import Header, HTTPException

from app.core.config import settings


async def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    expected = settings.API_KEY
    if not expected:
        return
    if not secrets.compare_digest((x_api_key or "").encode(), expected.encode()):
        raise HTTPException(
            status_code=401,
            detail="This endpoint needs a valid X-API-Key header on this server.",
        )
