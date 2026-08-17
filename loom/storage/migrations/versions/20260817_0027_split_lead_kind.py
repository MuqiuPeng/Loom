"""Separate job-hunt leads from freelance leads, in the data rather than the view.

The scout page has always had two lenses. `job` looks for companies with a
working site and a careers page; `freelance` looks for the opposite, a site
with something demonstrably wrong. But a lens is a filter over search results,
and once a lead was saved the distinction evaporated: one `scout_leads` table,
no column saying which lens put the row there.

That is not a tidiness problem. The two campaigns are legally different, as
company_scout.py's docstring has said all along — a message asking about
employment is not a commercial electronic message, while pitching freelance
work is, and needs consent, sender identification and a working opt-out. With
no discriminator, the outreach pipeline would happily take a company you
saved because you wanted to work there, build a mock site for it, and send its
owner a sales pitch signed with your business name.

So `kind` becomes a column, the outreach pipeline refuses anything that is not
"freelance", and the unique key gains it — the same business can legitimately
be both a place you would work and a site you would fix, and those are two
rows with separate status and history.

`provider` arrives at the same time, and joins the key for the same reason a
place_id needs one: the id is issued by a map service and means nothing
without it. Existing rows are Google's, because Google is all there has been.

Revision ID: 027
Revises: 026
Create Date: 2026-08-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Everything saved so far came from the freelance pipeline — it is the only
    # one that has ever had a pipeline — so that is what the existing rows are.
    op.add_column(
        "scout_leads",
        sa.Column("kind", sa.String(20), nullable=False, server_default="freelance"),
    )
    op.add_column(
        "scout_leads",
        sa.Column("provider", sa.String(20), nullable=False, server_default="google"),
    )
    op.create_index("ix_scout_leads_kind", "scout_leads", ["kind"])
    op.create_index("ix_scout_leads_provider", "scout_leads", ["provider"])

    op.drop_constraint("uq_scout_leads_user_place", "scout_leads", type_="unique")
    op.create_unique_constraint(
        "uq_scout_leads_user_kind_place",
        "scout_leads",
        ["user_id", "kind", "provider", "place_id"],
    )


def downgrade() -> None:
    # Collapsing the key can fail where it should: if a business was saved as
    # both a job lead and a freelance lead, there is no single row to keep, and
    # picking one is not a decision this migration can make.
    op.drop_constraint("uq_scout_leads_user_kind_place", "scout_leads", type_="unique")
    op.create_unique_constraint(
        "uq_scout_leads_user_place", "scout_leads", ["user_id", "place_id"]
    )
    op.drop_index("ix_scout_leads_provider", table_name="scout_leads")
    op.drop_index("ix_scout_leads_kind", table_name="scout_leads")
    op.drop_column("scout_leads", "provider")
    op.drop_column("scout_leads", "kind")
