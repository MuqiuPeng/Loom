"""Make profile name and location bilingual (en/zh).

Revision ID: 003
Revises: 002
Create Date: 2026-03-30

Renames name -> name_en, location -> location_en, and adds _zh counterparts.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename name -> name_en, add name_zh
    op.alter_column("profiles", "name", new_column_name="name_en")
    op.add_column("profiles", sa.Column("name_zh", sa.String(255), nullable=True))

    # Rename location -> location_en, add location_zh
    op.alter_column("profiles", "location", new_column_name="location_en")
    op.add_column("profiles", sa.Column("location_zh", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("profiles", "location_zh")
    op.alter_column("profiles", "location_en", new_column_name="location")

    op.drop_column("profiles", "name_zh")
    op.alter_column("profiles", "name_en", new_column_name="name")
