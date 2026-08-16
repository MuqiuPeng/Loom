"""Add the outreach pipeline columns to scout_leads.

harvest → demo → draft → contacted. Each stage stores its output plus the
timestamp it ran, so the UI reads state off the row instead of a separate
status machine.

Revision ID: 018
Revises: 017
Create Date: 2026-08-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = [
    ("harvest", JSONB()),
    ("harvested_at", sa.DateTime()),
    ("demo_slug", sa.String(80)),
    ("demo_url", sa.Text()),
    ("demo_built_at", sa.DateTime()),
    ("draft_subject", sa.Text()),
    ("draft_body", sa.Text()),
    ("drafted_at", sa.DateTime()),
    ("contacted_at", sa.DateTime()),
]


def upgrade() -> None:
    for name, type_ in COLUMNS:
        op.add_column("scout_leads", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(COLUMNS):
        op.drop_column("scout_leads", name)
