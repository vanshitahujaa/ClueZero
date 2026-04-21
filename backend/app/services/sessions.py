"""Session / LIFO service — one live agent per user token."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models_db import AgentSession


def new_session_id() -> str:
    return secrets.token_hex(16)


async def open_session(
    session: AsyncSession,
    user_id: int,
    platform: str | None = None,
    machine_hint: str | None = None,
    device_id: str | None = None,
) -> AgentSession:
    """
    Open or resume a session.

    If `device_id` is provided and a live session for (user_id, device_id)
    already exists, return it unchanged (resume — no heartbeat gap, same
    session_id, does not revoke itself). Otherwise revoke all prior live
    sessions for this user (LIFO) and create a new one.
    """
    now = datetime.now(timezone.utc)

    if device_id:
        existing_q = await session.execute(
            select(AgentSession).where(
                AgentSession.user_id == user_id,
                AgentSession.device_id == device_id,
                AgentSession.revoked_at.is_(None),
            )
        )
        existing = existing_q.scalar_one_or_none()
        if existing is not None:
            existing.last_seen = now
            await session.flush()
            return existing

    # Revoke all live sessions for this user (LIFO across devices).
    await session.execute(
        update(AgentSession)
        .where(AgentSession.user_id == user_id, AgentSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )

    s = AgentSession(
        user_id=user_id,
        session_id=new_session_id(),
        started_at=now,
        last_seen=now,
        platform=platform,
        machine_hint=machine_hint,
        device_id=device_id,
    )
    session.add(s)
    await session.flush()
    return s


async def get_session(session: AsyncSession, session_id: str) -> AgentSession | None:
    result = await session.execute(
        select(AgentSession).where(AgentSession.session_id == session_id)
    )
    return result.scalar_one_or_none()


async def validate_live(
    session: AsyncSession, user_id: int, session_id: str
) -> AgentSession | None:
    """
    Return the session if it is alive (belongs to the user, not revoked,
    and seen within the heartbeat window). Returns None otherwise.
    """
    s = await get_session(session, session_id)
    if s is None or s.user_id != user_id:
        return None
    if s.revoked_at is not None:
        return None
    return s


async def touch(session: AsyncSession, s: AgentSession) -> None:
    s.last_seen = datetime.now(timezone.utc)
    await session.flush()


async def revoke(session: AsyncSession, s: AgentSession) -> None:
    if s.revoked_at is None:
        s.revoked_at = datetime.now(timezone.utc)
        await session.flush()


async def sweep_stale(session: AsyncSession) -> int:
    """
    Mark as revoked any sessions whose last_seen is older than the heartbeat timeout.
    Returns the number of sessions revoked.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.session_heartbeat_timeout)
    result = await session.execute(
        update(AgentSession)
        .where(AgentSession.revoked_at.is_(None), AgentSession.last_seen < cutoff)
        .values(revoked_at=datetime.now(timezone.utc))
        .returning(AgentSession.id)
    )
    return len(result.all())
