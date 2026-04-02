"""Add starred to resume_artifacts.

Revision ID: 013
Revises: 012
Create Date: 2026-04-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("resume_artifacts", sa.Column("starred", sa.Boolean(), server_default="false"))


def downgrade() -> None:
    op.drop_column("resume_artifacts", "starred")
