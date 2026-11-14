"""Test isolation.

Points the app at a throwaway SQLite database and model directory *before* any
`app` module is imported, so the tests never touch the development database or
the experiment registry.
"""
import asyncio
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="hailcast-test-"))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["SYNC_DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["MODEL_DIR"] = str(_TMP / "models")


def run(coro):
    """Run a coroutine on a fresh event loop and release the engine's connections after it."""
    from app.core.database import engine

    async def _main():
        try:
            return await coro
        finally:
            await engine.dispose()

    return asyncio.run(_main())
