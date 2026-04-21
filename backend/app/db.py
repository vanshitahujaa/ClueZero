"""Async SQLAlchemy engine + session factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


def _normalize_async_url(url: str) -> str:
    """Neon gives postgres:// or postgresql://; SQLAlchemy async needs postgresql+asyncpg://."""
    if not url:
        return url
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    # asyncpg doesn't understand ?sslmode=require / ?channel_binding=require; Neon requires SSL by default.
    if "?" in url:
        base, query = url.split("?", 1)
        kept = [
            p for p in query.split("&")
            if not p.startswith("sslmode=") and not p.startswith("channel_binding=")
        ]
        url = base + ("?" + "&".join(kept) if kept else "")
    return url


_engine: AsyncEngine | None = None
_SessionFactory: async_sessionmaker[AsyncSession] | None = None


def init_engine() -> AsyncEngine:
    global _engine, _SessionFactory
    if _engine is not None:
        return _engine
    url = _normalize_async_url(settings.database_url)
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    _engine = create_async_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        # Neon requires TLS but doesn't need strict cert verification at the
        # driver level (Let's Encrypt chain). "require" = TLS without verify.
        connect_args={"ssl": "require"},
    )
    _SessionFactory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _SessionFactory is None:
        init_engine()
    assert _SessionFactory is not None
    return _SessionFactory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — yields a session, commits on success, rolls back on error."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    global _engine, _SessionFactory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _SessionFactory = None
