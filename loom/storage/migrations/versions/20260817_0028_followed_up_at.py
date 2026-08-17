"""Record that the one follow-up has gone.

The follow-up template is labelled "once, then stop" and its body says so to
the recipient: "just say so and I won't write again". Keeping the promise needs
somewhere to write down that it has already been used, and contacted_at cannot
carry it — that timestamp is what the schedule counts from, so overwriting it
would make the follow-up eligible again three days later, forever.

A timestamp rather than a counter or a boolean, for the same reason every other
stage here has one: knowing a thing happened is rarely as useful as knowing
when, and "sent Tuesday" is what someone reads when they want to know why a
lead has gone quiet.

Revision ID: 028
Revises: 027
Create Date: 2026-08-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "028"
down_revision: Union[str, None] = "027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scout_leads",
        sa.Column("followed_up_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scout_leads", "followed_up_at")
