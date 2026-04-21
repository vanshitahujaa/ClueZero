"""WebSocket /ws/{job_id} — real-time result delivery, token-gated."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from app.db import get_session_factory
from app.deps import get_redis
from app.models import JobStatus
from app.models_db import Job
from app.services.users import get_user_by_token

logger = logging.getLogger("cluezero.ws")
router = APIRouter()

POLL_INTERVAL = 1.0
MAX_WAIT = 180


def _extract_token(ws: WebSocket) -> str | None:
    auth = ws.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(None, 1)[1].strip()
    # Fallback to query param for clients that can't set WS headers easily.
    tok = ws.query_params.get("token")
    return tok


@router.websocket("/ws/{job_id}")
async def ws_result(websocket: WebSocket, job_id: str):
    token = _extract_token(websocket)
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="missing_token")
        return

    factory = get_session_factory()
    async with factory() as db:
        user = await get_user_by_token(db, token)
        if user is None or not user.active:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="invalid_token")
            return
        result = await db.execute(select(Job).where(Job.job_id == job_id))
        record = result.scalar_one_or_none()
        if record is None or record.user_id != user.id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="not_owner")
            return

    await websocket.accept()
    r = get_redis()

    try:
        elapsed = 0.0
        while elapsed < MAX_WAIT:
            status_raw = r.get(f"job:{job_id}:status")
            if status_raw is None:
                await websocket.send_json({"status": "error", "detail": "Job not found or expired"})
                break

            job_status = JobStatus(status_raw)
            if job_status == JobStatus.COMPLETED:
                result_text = r.get(f"job:{job_id}:result") or ""
                await websocket.send_json({"status": "completed", "response": result_text})
                break
            if job_status == JobStatus.FAILED:
                error_text = r.get(f"job:{job_id}:error") or "Unknown error"
                await websocket.send_json({"status": "failed", "error": error_text})
                break

            await websocket.send_json({"status": job_status.value})
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL

        if elapsed >= MAX_WAIT:
            await websocket.send_json({"status": "error", "detail": "Timed out waiting for result"})

    except WebSocketDisconnect:
        logger.info("Client disconnected from WS for job %s", job_id)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
