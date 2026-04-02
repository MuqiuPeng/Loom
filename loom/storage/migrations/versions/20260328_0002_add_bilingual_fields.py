"""Add bilingual fields to profile, experience, education, bullet, project tables.

Revision ID: 002
Revises: 001
Create Date: 2026-03-28

All new columns are nullable. Proper-noun _zh columns (company_zh, institution_zh)
are populated from their _en counterparts via server_default or post-migration UPDATE.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── profiles ──────────────────────────────────────────────
    # Rename summary -> summary_en, then add summary_zh
    op.alter_column("profiles", "summary", new_column_name="summary_en")
    op.add_column("profiles", sa.Column("summary_zh", sa.Text(), nullable=True))

    # ── skills ────────────────────────────────────────────────
    # Rename context -> context_en, then add context_zh
    op.alter_column("skills", "context", new_column_name="context_en")
    op.add_column("skills", sa.Column("context_zh", sa.Text(), nullable=True))

    # ── experiences ───────────────────────────────────────────
    # Rename company -> company_en, title -> title_en, location -> location_en
    op.alter_column("experiences", "company", new_column_name="company_en")
    op.alter_column("experiences", "title", new_column_name="title_en")
    op.alter_column("experiences", "location", new_column_name="location_en")

    # Add _zh counterparts
    op.add_column("experiences", sa.Column("company_zh", sa.String(255), nullable=True))
    op.add_column("experiences", sa.Column("title_zh", sa.String(255), nullable=True))
    op.add_column("experiences", sa.Column("location_zh", sa.String(255), nullable=True))

    # Default company_zh to company_en for existing rows
    op.execute("UPDATE experiences SET company_zh = company_en WHERE company_zh IS NULL")

    # ── education ─────────────────────────────────────────────
    # Rename institution -> institution_en, degree -> degree_en, field -> field_en
    op.alter_column("education", "institution", new_column_name="institution_en")
    op.alter_column("education", "degree", new_column_name="degree_en")
    op.alter_column("education", "field", new_column_name="field_en")

    # Add _zh counterparts
    op.add_column("education", sa.Column("institution_zh", sa.String(255), nullable=True))
    op.add_column("education", sa.Column("degree_zh", sa.String(100), nullable=True))
    op.add_column("education", sa.Column("field_zh", sa.String(255), nullable=True))

    # Default institution_zh to institution_en for existing rows
    op.execute("UPDATE education SET institution_zh = institution_en WHERE institution_zh IS NULL")

    # ── bullets ───────────────────────────────────────────────
    op.add_column("bullets", sa.Column("content_en", sa.Text(), nullable=True))
    op.add_column("bullets", sa.Column("content_zh", sa.Text(), nullable=True))

    # ── projects ──────────────────────────────────────────────
    # Rename name -> name_en, description -> description_en, role -> role_en
    op.alter_column("projects", "name", new_column_name="name_en")
    op.alter_column("projects", "description", new_column_name="description_en")
    op.alter_column("projects", "role", new_column_name="role_en")

    # Add _zh counterparts
    op.add_column("projects", sa.Column("name_zh", sa.String(255), nullable=True))
    op.add_column("projects", sa.Column("description_zh", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("role_zh", sa.String(255), nullable=True))


def downgrade() -> None:
    # ── projects ──────────────────────────────────────────────
    op.drop_column("projects", "role_zh")
    op.drop_column("projects", "description_zh")
    op.drop_column("projects", "name_zh")
    op.alter_column("projects", "role_en", new_column_name="role")
    op.alter_column("projects", "description_en", new_column_name="description")
    op.alter_column("projects", "name_en", new_column_name="name")

    # ── bullets ───────────────────────────────────────────────
    op.drop_column("bullets", "content_zh")
    op.drop_column("bullets", "content_en")

    # ── education ─────────────────────────────────────────────
    op.drop_column("education", "field_zh")
    op.drop_column("education", "degree_zh")
    op.drop_column("education", "institution_zh")
    op.alter_column("education", "field_en", new_column_name="field")
    op.alter_column("education", "degree_en", new_column_name="degree")
    op.alter_column("education", "institution_en", new_column_name="institution")

    # ── experiences ───────────────────────────────────────────
    op.drop_column("experiences", "location_zh")
    op.drop_column("experiences", "title_zh")
    op.drop_column("experiences", "company_zh")
    op.alter_column("experiences", "location_en", new_column_name="location")
    op.alter_column("experiences", "title_en", new_column_name="title")
    op.alter_column("experiences", "company_en", new_column_name="company")

    # ── skills ────────────────────────────────────────────────
    op.drop_column("skills", "context_zh")
    op.alter_column("skills", "context_en", new_column_name="context")

    # ── profiles ──────────────────────────────────────────────
    op.drop_column("profiles", "summary_zh")
    op.alter_column("profiles", "summary_en", new_column_name="summary")
