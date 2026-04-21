"""GET /result/{job_id} — polling fallback, scoped to calling user."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.db import get_db
from app.deps import get_redis
from app.models import JobResult, JobStatus
from app.models_db import Job, User

logger = logging.getLogger("cluezero.result")
router = APIRouter()


@router.get("/result/{job_id}", response_model=JobResult)
async def get_result(
    job_id: str,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Ownership check — only the submitting user (or admin — admin uses a different route) sees results.
    result = await db.execute(select(Job).where(Job.job_id == job_id))
    record = result.scalar_one_or_none()
    if record is None or record.user_id != user.id:
        raise HTTPException(status_code=404, detail="Job not found or expired")

    r = get_redis()
    status_raw = r.get(f"job:{job_id}:status")
    if status_raw is None:
        # Redis expired; return the DB record's status if known.
        status = JobStatus(record.status) if record.status in JobStatus._value2member_map_ else JobStatus.FAILED
        return JobResult(job_id=job_id, status=status, response=None, error=record.error)

    status = JobStatus(status_raw)
    response_text = None
    error_text = None
    if status == JobStatus.COMPLETED:
        response_text = r.get(f"job:{job_id}:result")
    elif status == JobStatus.FAILED:
        error_text = r.get(f"job:{job_id}:error") or "Unknown error"

    return JobResult(job_id=job_id, status=status, response=response_text, error=error_text)
