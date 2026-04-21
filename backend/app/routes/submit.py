"""POST /submit — accept a screenshot (token + session auth) and enqueue it."""

from __future__ import annotations

import uuid
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from rq import Queue
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.config import settings
from app.db import get_db
from app.deps import get_redis
from app.models import SubmitRequest, SubmitResponse, JobStatus
from app.models_db import User
from app.middleware.rate_limit import check_rate_limit
from app.services.image import optimize_image
from app.services.dedup import check_duplicate
from app.services import sessions as sess_svc
from app.services import billing as billing_svc
from app.queue.worker import process_screenshot

logger = logging.getLogger("cluezero.submit")
router = APIRouter()


@router.post("/submit", response_model=SubmitResponse)
async def submit_screenshot(
    req: SubmitRequest,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    x_session_id: Annotated[str | None, Header()] = None,
):
    if not x_session_id:
        raise HTTPException(status_code=400, detail="Missing X-Session-Id")

    s = await sess_svc.validate_live(db, user.id, x_session_id)
    if s is None:
        raise HTTPException(status_code=401, detail="session_revoked")

    r = get_redis()
    check_rate_limit(r, user.id)

    # Touch session liveness opportunistically.
    await sess_svc.touch(db, s)

    try:
        optimised_b64, image_hash = optimize_image(req.image)
    except Exception as exc:
        logger.warning("Image optimisation failed: %s", exc)
        raise HTTPException(status_code=400, detail=f"Invalid image data: {exc}")

    cached = check_duplicate(r, image_hash)
    if cached is not None:
        job_id = str(uuid.uuid4())
        r.setex(f"job:{job_id}:result", settings.job_result_ttl_seconds, cached)
        r.setex(f"job:{job_id}:status", settings.job_result_ttl_seconds, JobStatus.COMPLETED.value)
        # Record as a zero-cost dedup hit for visibility
        await billing_svc.create_job_record(
            db, user_id=user.id, session_pk=s.id, job_id=job_id, model=settings.llm_model
        )
        await billing_svc.finalize_job(db, job_id=job_id, status="completed")
        logger.info("Dedup hit → virtual job %s user=%s", job_id, user.id)
        return SubmitResponse(job_id=job_id, status=JobStatus.COMPLETED)

    job_id = str(uuid.uuid4())
    prompt = req.prompt or settings.default_prompt

    await billing_svc.create_job_record(
        db, user_id=user.id, session_pk=s.id, job_id=job_id, model=settings.llm_model
    )

    q = Queue(connection=r)
    q.enqueue(
        process_screenshot,
        args=(job_id, optimised_b64, prompt, image_hash, user.id),
        job_timeout=settings.job_ttl_seconds,
        result_ttl=0,
    )
    r.setex(f"job:{job_id}:status", settings.job_ttl_seconds, JobStatus.QUEUED.value)

    logger.info("Job %s queued user=%s", job_id, user.id)
    return SubmitResponse(job_id=job_id, status=JobStatus.QUEUED)
