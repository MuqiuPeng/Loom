"""Give the existing data a real owner, and make ownership the unit of uniqueness.

Every table has carried a `user_id` since the beginning, but nothing ever set
it: the column defaulted to "local" and the API took it as a query parameter
that no caller passed. One account's worth of data under a placeholder name
was harmless while there was one account. It stops being harmless the moment a
second address can sign in, because "local" is what both of them resolve to.

Two changes, and they have to happen together:

  * Re-stamp every row from "local" to the owner's address, so the data has an
    owner that a session can actually match. LOOM_OWNER_EMAIL overrides the
    default for anyone running this against a different install.

  * `scout_leads.place_id` was globally unique — one row per business, which
    was the right rule when the business could only belong to one person.
    Under per-user scoping it means the second user to scout a suburb silently
    inherits the first user's outreach history, or collides with it. The
    unique key becomes (user_id, place_id).

`workflow_definitions` is deliberately left alone: those rows are seeded
configuration rather than anyone's data, and `get_workflow_definitions()`
never filters by user.

Revision ID: 025
Revises: 024
Create Date: 2026-08-16
"""
import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OWNER = os.environ.get("LOOM_OWNER_EMAIL", "guanshunpeng@gmail.com")
PLACEHOLDER = "local"

# Every table whose rows belong to a person.
TABLES = (
    "profiles",
    "skills",
    "experiences",
    "education",
    "bullets",
    "projects",
    "jd_records",
    "resume_artifacts",
    "tasks",
    "workflow_runs",
    "step_runs",
    "token_usages",
    "scout_leads",
    "log_entries",
)


def upgrade() -> None:
    conn = op.get_bind()
    for table in TABLES:
        conn.execute(
            sa.text(
                f"UPDATE {table} SET user_id = :owner WHERE user_id = :placeholder"
            ),
            {"owner": OWNER, "placeholder": PLACEHOLDER},
        )

    op.drop_constraint("uq_scout_leads_place_id", "scout_leads", type_="unique")
    op.create_unique_constraint(
        "uq_scout_leads_user_place", "scout_leads", ["user_id", "place_id"]
    )


def downgrade() -> None:
    # Reversing the unique key can fail where it should: if two users have both
    # scouted the same business, there is no single row to keep, and dropping
    # one of them is a decision this migration has no business making.
    op.drop_constraint("uq_scout_leads_user_place", "scout_leads", type_="unique")
    op.create_unique_constraint("uq_scout_leads_place_id", "scout_leads", ["place_id"])

    conn = op.get_bind()
    for table in TABLES:
        conn.execute(
            sa.text(
                f"UPDATE {table} SET user_id = :placeholder WHERE user_id = :owner"
            ),
            {"owner": OWNER, "placeholder": PLACEHOLDER},
        )
