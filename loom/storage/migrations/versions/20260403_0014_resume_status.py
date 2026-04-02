"""Add status and generation_progress to resume_artifacts.

Revision ID: 014
Revises: 013
Create Date: 2026-04-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("resume_artifacts", sa.Column("status", sa.String(20), server_default="completed"))
    op.add_column("resume_artifacts", sa.Column("generation_progress", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("resume_artifacts", "generation_progress")
    op.drop_column("resume_artifacts", "status")
