"""Per-user sliding-window rate limiter keyed on user.id."""

import logging

import redis as redis_lib
from fastapi import HTTPException

from app.config import settings

logger = logging.getLogger("cluezero.ratelimit")


def check_rate_limit(r: redis_lib.Redis, user_id: int) -> None:
    """
    Enforce a minimum interval between requests for a given user.

    Raises HTTP 429 if the same user submits within the configured window.
    """
    key = f"ratelimit:{user_id}"
    window = settings.rate_limit_seconds

    if r.exists(key):
        ttl = r.ttl(key)
        logger.warning("Rate limit hit for user_id=%s (retry in %ds)", user_id, ttl)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limited. Please wait {ttl} seconds before next request.",
        )

    r.setex(key, window, "1")
