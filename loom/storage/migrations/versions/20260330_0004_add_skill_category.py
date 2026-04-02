"""Add category column to skills table.

Revision ID: 004
Revises: 003
Create Date: 2026-03-30

Categorizes skills by usage scenario (Backend, Frontend, AI/ML, etc.)
rather than by the project where the skill was learned.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("skills", sa.Column("category", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("skills", "category")
