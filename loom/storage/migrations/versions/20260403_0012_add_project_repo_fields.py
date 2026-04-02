"""Add local_repo_path, last_analyzed_at, auto_update to projects.

Revision ID: 012
Revises: 011
Create Date: 2026-04-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("local_repo_path", sa.String(500), nullable=True))
    op.add_column("projects", sa.Column("last_analyzed_at", sa.DateTime(), nullable=True))
    op.add_column("projects", sa.Column("auto_update", sa.Boolean(), server_default="false"))


def downgrade() -> None:
    op.drop_column("projects", "auto_update")
    op.drop_column("projects", "last_analyzed_at")
    op.drop_column("projects", "local_repo_path")
