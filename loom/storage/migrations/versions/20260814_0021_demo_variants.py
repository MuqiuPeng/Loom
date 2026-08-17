"""Several demos per lead, one of them chosen.

Picking an art direction from the trade alone guesses at the owner's taste.
Generating a few and letting them be compared as thumbnails costs about a
dollar a lead and removes the guess.

demo_html stays, holding whatever the active variant is, so the public route
keeps working unchanged.

Revision ID: 021
Revises: 020
Create Date: 2026-08-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # {direction: {html, thumb(base64 jpeg), rounds, remaining, built_at}}
    op.add_column("scout_leads", sa.Column("demo_variants", JSONB(), nullable=True))
    op.add_column("scout_leads", sa.Column("demo_active", sa.String(40), nullable=True))


def downgrade() -> None:
    op.drop_column("scout_leads", "demo_active")
    op.drop_column("scout_leads", "demo_variants")
