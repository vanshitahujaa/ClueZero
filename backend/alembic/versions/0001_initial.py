"""initial schema: users, agent_sessions, jobs

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("token", name="uq_users_token"),
    )
    op.create_index("ix_users_token", "users", ["token"])

    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("platform", sa.String(length=32), nullable=True),
        sa.Column("machine_hint", sa.String(length=128), nullable=True),
        sa.UniqueConstraint("session_id", name="uq_agent_sessions_session_id"),
    )
    op.create_index("ix_agent_sessions_user_id", "agent_sessions", ["user_id"])
    op.create_index("ix_agent_sessions_session_id", "agent_sessions", ["session_id"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("agent_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "cost_usd",
            sa.Numeric(10, 6),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.UniqueConstraint("job_id", name="uq_jobs_job_id"),
    )
    op.create_index("ix_jobs_user_id", "jobs", ["user_id"])
    op.create_index("ix_jobs_job_id", "jobs", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_jobs_job_id", table_name="jobs")
    op.drop_index("ix_jobs_user_id", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_agent_sessions_session_id", table_name="agent_sessions")
    op.drop_index("ix_agent_sessions_user_id", table_name="agent_sessions")
    op.drop_table("agent_sessions")
    op.drop_index("ix_users_token", table_name="users")
    op.drop_table("users")
