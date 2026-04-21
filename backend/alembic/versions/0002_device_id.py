"""add device_id to agent_sessions for session-resume binding

Revision ID: 0002_device_id
Revises: 0001_initial
Create Date: 2026-04-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_device_id"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_sessions",
        sa.Column("device_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_agent_sessions_user_device",
        "agent_sessions",
        ["user_id", "device_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_sessions_user_device", table_name="agent_sessions")
    op.drop_column("agent_sessions", "device_id")
