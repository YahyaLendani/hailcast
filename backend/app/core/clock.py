from datetime import datetime, timezone


def utc_now() -> datetime:
    """Current UTC time as a naive datetime, the form the database columns store.

    Replaces the deprecated datetime.utcnow() with the same result.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
