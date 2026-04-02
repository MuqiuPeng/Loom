"""Add log_entries table.

Revision ID: 008
Revises: 007
Create Date: 2026-04-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "log_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.String(100), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=True, index=True),
        sa.Column("step_name", sa.String(100), nullable=True),
        sa.Column("data", JSONB, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("traceback", sa.Text(), nullable=True),
    )
    op.create_index("ix_log_entries_created_at", "log_entries", ["created_at"])
    op.create_index("ix_log_entries_category_level", "log_entries", ["category", "level"])


def downgrade() -> None:
    op.drop_index("ix_log_entries_category_level")
    op.drop_index("ix_log_entries_created_at")
    op.drop_table("log_entries")
