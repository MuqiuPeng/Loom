"""Add scout_leads — saved outreach leads from Company Scout.

Google-derived columns (name/address/phone) are paired with google_expires_at
so they can be blanked on schedule; the self-sourced columns have no expiry.
See loom/storage/models.py:ScoutLeadModel.

Revision ID: 017
Revises: 016
Create Date: 2026-08-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scout_leads",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.String(100), nullable=False, server_default="local"),
        sa.Column("place_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="new"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("site_url", sa.Text(), nullable=True),
        sa.Column("site_title", sa.Text(), nullable=True),
        sa.Column("careers_url", sa.Text(), nullable=True),
        sa.Column("emails", JSONB(), nullable=True),
        sa.Column("audit", JSONB(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("google_name", sa.Text(), nullable=True),
        sa.Column("google_address", sa.Text(), nullable=True),
        sa.Column("google_phone", sa.String(50), nullable=True),
        sa.Column("google_expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("checked_at", sa.DateTime(), nullable=True),
    )
    op.create_unique_constraint("uq_scout_leads_place_id", "scout_leads", ["place_id"])
    op.create_index("ix_scout_leads_user_id", "scout_leads", ["user_id"])
    op.create_index("ix_scout_leads_status", "scout_leads", ["status"])
    op.create_index("ix_scout_leads_score", "scout_leads", ["score"])


def downgrade() -> None:
    op.drop_index("ix_scout_leads_score")
    op.drop_index("ix_scout_leads_status")
    op.drop_index("ix_scout_leads_user_id")
    op.drop_constraint("uq_scout_leads_place_id", "scout_leads")
    op.drop_table("scout_leads")
