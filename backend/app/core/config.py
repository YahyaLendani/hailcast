import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


def utc_now() -> datetime:
    """Return naive UTC datetime compatible with SQLite and PostgreSQL DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


BASE_DIR_PATH = Path(__file__).resolve().parent.parent.parent
DEFAULT_SQLITE_PATH = (BASE_DIR_PATH / "flowsight.db").as_posix()


class Settings(BaseSettings):
    PROJECT_NAME: str = "Hailcast"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = (
        "Real-Time Transportation Analytics, Historical Event Replay, "
        "Medallion ETL, and Walk-Forward ML Demand Forecasting Platform"
    )
    API_V1_STR: str = "/api/v1"

    # Base directories
    BASE_DIR: Path = BASE_DIR_PATH
    DATA_DIR: Path = BASE_DIR_PATH / "app" / "data"
    MODEL_DIR: Path = BASE_DIR_PATH / "app" / "ml" / "saved_models"

    # Database configuration (Dual mode: PostgreSQL with fallback to SQLite for zero-config run)
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DEFAULT_SQLITE_PATH}")
    SYNC_DATABASE_URL: str = os.getenv("SYNC_DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH}")

    # Redis configuration (with automatic high-throughput in-memory stream fallback)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_STREAM_KEY: str = "flowsight:trip_events"
    REDIS_CONSUMER_GROUP: str = "flowsight_workers"

    # Event Replay & Bootstrap settings
    REPLAY_SPEED_MULTIPLIER: float = 10.0
    BATCH_SIZE: int = 1000
    AUTO_SEED_ON_STARTUP: bool = True
    INITIAL_SEED_SIZE: int = 5000

    # When set, upload endpoints require this value in the X-API-Key header
    API_KEY: str = ""

    # Seconds between public calls that retrain the model or run a pipeline job,
    # shared by all callers. A valid X-API-Key skips the wait; 0 turns it off.
    EXPENSIVE_ACTION_COOLDOWN_SECONDS: float = 300.0

    # Live NYC bus collector (python -m app.collector.run). Without MTA_API_KEY it does not start.
    MTA_API_KEY: str = ""
    BUS_POLL_SECONDS: float = 30.0  # the MTA asks for no more than one request per 30 seconds
    BUS_RETENTION_HOURS: float = 24.0

    # Browser origins allowed to call the API from another site. The served dashboard
    # is same-origin and needs none; this default lets the local Next.js prototype
    # in frontend/ reach a local backend.
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="allow",
        case_sensitive=False,
    )


settings = Settings()
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.MODEL_DIR.mkdir(parents=True, exist_ok=True)
