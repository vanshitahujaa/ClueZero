"""Shared dependencies — Redis connection management."""

import redis as redis_lib

# Shared Redis connection, set during app lifespan
_redis_conn: redis_lib.Redis | None = None


def set_redis(conn: redis_lib.Redis) -> None:
    """Set the shared Redis connection (called at startup)."""
    global _redis_conn
    _redis_conn = conn


def get_redis() -> redis_lib.Redis:
    """Return the shared Redis connection."""
    assert _redis_conn is not None, "Redis not initialised — app not started?"
    return _redis_conn
