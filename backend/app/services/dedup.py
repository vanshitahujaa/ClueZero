"""Request deduplication — cache results by image hash."""

import logging
from typing import Optional

import redis as redis_lib

from app.config import settings

logger = logging.getLogger("cluezero.dedup")

DEDUP_TTL = 300  # 5 minutes default


def check_duplicate(r: redis_lib.Redis, image_hash: str) -> Optional[str]:
    """
    Check if an identical image was recently processed.

    Returns:
        The cached LLM response if a duplicate is found, else None.
    """
    key = f"dedup:{image_hash}"
    cached = r.get(key)
    if cached:
        logger.info("Dedup cache hit: hash=%s", image_hash[:12])
    return cached


def store_dedup(r: redis_lib.Redis, image_hash: str, result: str) -> None:
    """Store a result in the dedup cache with TTL."""
    key = f"dedup:{image_hash}"
    r.setex(key, DEDUP_TTL, result)
    logger.debug("Dedup cached: hash=%s ttl=%ds", image_hash[:12], DEDUP_TTL)
