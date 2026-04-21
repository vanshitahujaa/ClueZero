"""Session lifecycle — open (LIFO) + ping heartbeat."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.db import get_db
from app.models_db import User
from app.services import sessions as sess_svc

logger = logging.getLogger("cluezero.session")
router = APIRouter(prefix="/session", tags=["session"])


class OpenRequest(BaseModel):
    platform: str | None = None
    machine_hint: str | None = None


class OpenResponse(BaseModel):
    session_id: str
    heartbeat_seconds: int


@router.post("/open", response_model=OpenResponse)
async def open_session(
    body: OpenRequest,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Open a new session; revoke all prior live sessions for this user."""
    s = await sess_svc.open_session(
        db, user.id, platform=body.platform, machine_hint=body.machine_hint
    )
    logger.info(
        "Session opened: user=%s session=%s platform=%s",
        user.id, s.session_id, body.platform,
    )
    from app.config import settings as cfg
    return OpenResponse(session_id=s.session_id, heartbeat_seconds=max(15, cfg.session_heartbeat_timeout // 3))


@router.post("/ping")
async def ping_session(
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    x_session_id: Annotated[str | None, Header()] = None,
):
    if not x_session_id:
        raise HTTPException(status_code=400, detail="Missing X-Session-Id")
    s = await sess_svc.validate_live(db, user.id, x_session_id)
    if s is None:
        raise HTTPException(status_code=401, detail="session_revoked")
    await sess_svc.touch(db, s)
    return {"status": "ok"}
