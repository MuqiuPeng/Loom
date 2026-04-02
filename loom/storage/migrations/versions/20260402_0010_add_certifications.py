"""Add certifications JSONB column to profiles.

Revision ID: 010
Revises: 009
Create Date: 2026-04-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("certifications", JSONB, server_default="[]"))


def downgrade() -> None:
    op.drop_column("profiles", "certifications")
