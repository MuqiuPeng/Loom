"""Add github and linkedin to profiles.

Revision ID: 015
Revises: 014
Create Date: 2026-04-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("github", sa.String(255), nullable=True))
    op.add_column("profiles", sa.Column("linkedin", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("profiles", "linkedin")
    op.drop_column("profiles", "github")
