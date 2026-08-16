"""Record where each address was published, not just what it is.

Under the Spam Act a commercial message needs consent, and for a published
business address that consent is inferred rather than given — but only if
several conditions held at the moment of publication: the address was
conspicuously published, it would be reasonable to assume the publication was
agreed to, and no statement refusing unsolicited commercial mail accompanied
it. Section 16(5) puts the evidential burden on the sender.

An address stored as a bare string cannot answer any of that. "Where did you
get this, and what did the page say?" is the question the whole model turns
on, and until now the answer lived nowhere.

So: {address: {url, how, at, refuses_unsolicited}}, captured at the moment of
harvest. It is not proof on its own, but it is the difference between a
record and a shrug.

Revision ID: 024
Revises: 023
Create Date: 2026-08-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scout_leads",
        sa.Column("email_sources", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scout_leads", "email_sources")
