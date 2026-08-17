"""Add service column to log_entries.

Revision ID: 016
Revises: 015
Create Date: 2026-04-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("log_entries", sa.Column("service", sa.String(50), server_default="resume_tailor"))
    op.create_index("ix_log_entries_service", "log_entries", ["service"])


def downgrade() -> None:
    op.drop_index("ix_log_entries_service")
    op.drop_column("log_entries", "service")
