"""Add google_extra to scout_leads.

Rating, price level, opening hours, map link and type list — all Enterprise
tier fields that ride along free with the website lookup we already pay for.
One JSONB column rather than five typed ones because it is cached Places
Content: it lives and dies with google_expires_at, so it is never queried on
and never worth a schema commitment.

Revision ID: 019
Revises: 018
Create Date: 2026-08-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scout_leads", sa.Column("google_extra", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("scout_leads", "google_extra")
