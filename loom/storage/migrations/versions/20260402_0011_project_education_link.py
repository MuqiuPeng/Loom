"""Add education_id to projects table.

Revision ID: 011
Revises: 010
Create Date: 2026-04-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("education_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_projects_education_id", "projects", "education",
        ["education_id"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_projects_education_id", "projects", type_="foreignkey")
    op.drop_column("projects", "education_id")
