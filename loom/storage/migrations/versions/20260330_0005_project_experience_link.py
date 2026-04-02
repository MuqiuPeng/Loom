"""Add experience_id FK to projects table.

Revision ID: 005
Revises: 004
Create Date: 2026-03-30

Links projects to experiences. NULL = personal/side project.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("experience_id", sa.Uuid(), sa.ForeignKey("experiences.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "experience_id")
