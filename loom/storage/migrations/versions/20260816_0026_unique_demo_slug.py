"""Make the public demo URL unique, because it is a URL.

`demo_slug` is derived from the business name and its Google place_id, both of
which are properties of the shop rather than of whoever scouted it. Two users
working the same suburb therefore computed the same slug, and the public route
reads `where demo_slug = $1 and demo_public = true limit 1` — so the link you
sent a customer could open the other person's page. Silently, and only
sometimes, which is the worst way for it to fail.

`slug_for()` now mixes in a fingerprint of the owner. This index is the half
that cannot be forgotten: if a collision is ever constructed some other way,
the write fails instead of the read going somewhere unexpected.

Partial, because most leads never get a demo and NULL is not a collision.

Revision ID: 026
Revises: 025
Create Date: 2026-08-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "026"
down_revision: Union[str, None] = "025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_scout_leads_demo_slug",
        "scout_leads",
        ["demo_slug"],
        unique=True,
        postgresql_where=sa.text("demo_slug IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_scout_leads_demo_slug", table_name="scout_leads")
