"""Make a demo shareable only when it is deliberately made shareable.

These pages carry a real business's name and photographs, so being reachable
by anyone with the URL is a decision per lead, not a side effect of building
one. Off by default; the public route 404s until it is turned on.

Revision ID: 023
Revises: 022
Create Date: 2026-08-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scout_leads",
        sa.Column(
            "demo_public", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    op.drop_column("scout_leads", "demo_public")
