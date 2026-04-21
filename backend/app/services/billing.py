"""Billing — per-job cost from token counts + per-user aggregates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models_db import Job, User


def compute_cost(tokens_in: int, tokens_out: int) -> Decimal:
    """Return USD cost based on configured per-1K pricing. Precision kept to 6dp."""
    in_price = Decimal(str(settings.llm_input_price_per_1k))
    out_price = Decimal(str(settings.llm_output_price_per_1k))
    total = (Decimal(tokens_in) * in_price + Decimal(tokens_out) * out_price) / Decimal("1000")
    return total.quantize(Decimal("0.000001"))


async def create_job_record(
    session: AsyncSession,
    *,
    user_id: int,
    session_pk: int | None,
    job_id: str,
    model: str | None,
) -> Job:
    job = Job(
        user_id=user_id,
        session_id=session_pk,
        job_id=job_id,
        model=model,
        status="queued",
    )
    session.add(job)
    await session.flush()
    return job


async def finalize_job(
    session: AsyncSession,
    *,
    job_id: str,
    status: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    error: str | None = None,
) -> Job | None:
    result = await session.execute(select(Job).where(Job.job_id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        return None
    job.status = status
    job.tokens_in = tokens_in
    job.tokens_out = tokens_out
    job.cost_usd = compute_cost(tokens_in, tokens_out)
    job.completed_at = datetime.now(timezone.utc)
    job.error = error
    await session.flush()
    return job


@dataclass
class UserUsage:
    user_id: int
    job_count: int
    tokens_in: int
    tokens_out: int
    cost_usd: Decimal
    last_used: datetime | None


async def user_usage(session: AsyncSession, user_id: int) -> UserUsage:
    result = await session.execute(
        select(
            func.count(Job.id),
            func.coalesce(func.sum(Job.tokens_in), 0),
            func.coalesce(func.sum(Job.tokens_out), 0),
            func.coalesce(func.sum(Job.cost_usd), 0),
            func.max(Job.completed_at),
        ).where(Job.user_id == user_id)
    )
    row = result.one()
    return UserUsage(
        user_id=user_id,
        job_count=int(row[0] or 0),
        tokens_in=int(row[1] or 0),
        tokens_out=int(row[2] or 0),
        cost_usd=Decimal(row[3] or 0),
        last_used=row[4],
    )


async def all_usage(session: AsyncSession) -> dict[int, UserUsage]:
    result = await session.execute(
        select(
            Job.user_id,
            func.count(Job.id),
            func.coalesce(func.sum(Job.tokens_in), 0),
            func.coalesce(func.sum(Job.tokens_out), 0),
            func.coalesce(func.sum(Job.cost_usd), 0),
            func.max(Job.completed_at),
        ).group_by(Job.user_id)
    )
    out: dict[int, UserUsage] = {}
    for uid, cnt, tin, tout, cost, last in result.all():
        out[uid] = UserUsage(
            user_id=uid,
            job_count=int(cnt or 0),
            tokens_in=int(tin or 0),
            tokens_out=int(tout or 0),
            cost_usd=Decimal(cost or 0),
            last_used=last,
        )
    return out


async def recent_jobs_for_user(session: AsyncSession, user_id: int, limit: int = 50):
    result = await session.execute(
        select(Job).where(Job.user_id == user_id).order_by(Job.id.desc()).limit(limit)
    )
    return result.scalars().all()
