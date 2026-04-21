"""User service — CRUD + token generation."""

from __future__ import annotations

import secrets
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_db import User


def new_token() -> str:
    return "clz_" + secrets.token_hex(16)


async def create_user(session: AsyncSession, name: str) -> User:
    user = User(name=name.strip(), token=new_token(), active=True)
    session.add(user)
    await session.flush()
    return user


async def get_user_by_token(session: AsyncSession, token: str) -> User | None:
    result = await session.execute(select(User).where(User.token == token))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def list_users(session: AsyncSession) -> Sequence[User]:
    result = await session.execute(select(User).order_by(User.id.asc()))
    return result.scalars().all()


async def delete_user(session: AsyncSession, user_id: int) -> bool:
    user = await session.get(User, user_id)
    if user is None:
        return False
    await session.delete(user)
    return True


async def regenerate_token(session: AsyncSession, user_id: int) -> User | None:
    user = await session.get(User, user_id)
    if user is None:
        return None
    user.token = new_token()
    await session.flush()
    return user


async def set_active(session: AsyncSession, user_id: int, active: bool) -> User | None:
    user = await session.get(User, user_id)
    if user is None:
        return None
    user.active = active
    await session.flush()
    return user
