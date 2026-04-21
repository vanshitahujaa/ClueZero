"""RQ worker task — processes a screenshot through the LLM pipeline.

Runs in a sync process (RQ workers), so uses a sync SQLAlchemy engine
to write billing info. We don't keep a long-lived engine — each job
opens a fresh connection, which is fine at ClueZero's volume.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

import redis as redis_lib
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session

from app.config import settings
from app.models import JobStatus
from app.models_db import Job
from app.services.llm import get_provider
from app.services.dedup import store_dedup

logger = logging.getLogger("cluezero.worker")


def _sync_db_url() -> str:
    """Neon-friendly sync URL for the worker's one-shot updates."""
    url = settings.database_url
    if not url:
        raise RuntimeError("DATABASE_URL not set for worker")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql+asyncpg://"):
        url = "postgresql+psycopg://" + url[len("postgresql+asyncpg://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _compute_cost(tokens_in: int, tokens_out: int) -> Decimal:
    in_p = Decimal(str(settings.llm_input_price_per_1k))
    out_p = Decimal(str(settings.llm_output_price_per_1k))
    total = (Decimal(tokens_in) * in_p + Decimal(tokens_out) * out_p) / Decimal("1000")
    return total.quantize(Decimal("0.000001"))


def _finalize_job_row(job_id: str, status: str, tokens_in: int, tokens_out: int, error: str | None) -> None:
    """Update the Job row with terminal status + billing info. Uses its own sync connection."""
    try:
        engine = create_engine(_sync_db_url(), pool_pre_ping=True)
        with Session(engine) as s:
            s.execute(
                update(Job)
                .where(Job.job_id == job_id)
                .values(
                    status=status,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=_compute_cost(tokens_in, tokens_out),
                    completed_at=datetime.now(timezone.utc),
                    error=error,
                )
            )
            s.commit()
        engine.dispose()
    except Exception as exc:
        logger.exception("Failed to finalize job row %s: %s", job_id, exc)


def process_screenshot(
    job_id: str,
    image_b64: str,
    prompt: str,
    image_hash: str,
    user_id: int,
) -> None:
    r = redis_lib.Redis.from_url(settings.redis_url, decode_responses=True)

    try:
        r.setex(f"job:{job_id}:status", settings.job_ttl_seconds, JobStatus.PROCESSING.value)
        logger.info("Processing job %s user=%s", job_id, user_id)

        provider = get_provider()
        result = provider.analyze_image(image_b64, prompt)

        r.setex(f"job:{job_id}:result", settings.job_result_ttl_seconds, result.text)
        r.setex(f"job:{job_id}:status", settings.job_result_ttl_seconds, JobStatus.COMPLETED.value)
        store_dedup(r, image_hash, result.text)

        _finalize_job_row(
            job_id=job_id,
            status="completed",
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            error=None,
        )
        logger.info(
            "Job %s completed (%d chars, tin=%d tout=%d)",
            job_id, len(result.text), result.tokens_in, result.tokens_out,
        )

    except Exception as exc:
        logger.exception("Job %s failed: %s", job_id, exc)
        r.setex(f"job:{job_id}:error", settings.job_result_ttl_seconds, str(exc))
        r.setex(f"job:{job_id}:status", settings.job_result_ttl_seconds, JobStatus.FAILED.value)
        _finalize_job_row(job_id=job_id, status="failed", tokens_in=0, tokens_out=0, error=str(exc))
        raise
    finally:
        r.close()
