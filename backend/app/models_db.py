"""SQLAlchemy ORM models — users, sessions, jobs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sessions: Mapped[list["AgentSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    jobs: Mapped[list["Job"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class AgentSession(Base):
    """One live agent installation for a user. LIFO: opening a new session revokes older ones."""

    __tablename__ = "agent_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(32), nullable=True)
    machine_hint: Mapped[str | None] = mapped_column(String(128), nullable=True)

    user: Mapped["User"] = relationship(back_populates="sessions")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="SET NULL"), nullable=True
    )
    job_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, default=Decimal("0"), server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="jobs")
