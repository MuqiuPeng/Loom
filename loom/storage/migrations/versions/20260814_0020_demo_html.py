"""Store the demo page itself on the lead.

The generated HTML was living on the API box's filesystem, which made the
demo a second source of truth that had to be kept in step with the row. It is
one self-contained document a few kilobytes long — the row is where it
belongs, and serving it becomes a SELECT instead of a deploy.

Revision ID: 020
Revises: 019
Create Date: 2026-08-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scout_leads", sa.Column("demo_html", sa.Text(), nullable=True))
    # Serving is a lookup by slug from an unauthenticated route.
    op.create_index("ix_scout_leads_demo_slug", "scout_leads", ["demo_slug"])


def downgrade() -> None:
    op.drop_index("ix_scout_leads_demo_slug")
    op.drop_column("scout_leads", "demo_html")
