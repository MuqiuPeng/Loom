"""Store the design proposal that precedes generation.

Building every direction and choosing afterwards pays for the ones that were
never plausible. The plan is one cheap call whose output is reviewed and
adjusted before anything expensive runs.

Revision ID: 022
Revises: 021
Create Date: 2026-08-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scout_leads", sa.Column("demo_plan", JSONB(), nullable=True))
    op.add_column("scout_leads", sa.Column("planned_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("scout_leads", "planned_at")
    op.drop_column("scout_leads", "demo_plan")
