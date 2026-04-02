"""Initial schema - all tables

Revision ID: 001
Revises:
Create Date: 2026-03-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types
    op.execute("CREATE TYPE skilllevel AS ENUM ('expert', 'proficient', 'familiar')")
    op.execute(
        "CREATE TYPE bullettype AS ENUM ('business_impact', 'technical_design', "
        "'implementation', 'scale', 'collaboration', 'problem_solving')"
    )
    op.execute("CREATE TYPE confidence AS ENUM ('high', 'medium', 'low')")
    op.execute(
        "CREATE TYPE triggertype AS ENUM ('manual', 'email', 'git-hook', 'scheduled')"
    )
    op.execute(
        "CREATE TYPE runstatus AS ENUM ('pending', 'running', 'failed', 'completed')"
    )

    # Create profiles table
    op.create_table(
        "profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(100), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_profiles_user_id", "profiles", ["user_id"])

    # Create skills table
    op.create_table(
        "skills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "level",
            postgresql.ENUM("expert", "proficient", "familiar", name="skilllevel", create_type=False),
            nullable=False,
        ),
        sa.Column("context", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_skills_user_id", "skills", ["user_id"])

    # Create experiences table
    op.create_table(
        "experiences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("company", sa.String(255), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_visible", sa.Boolean(), default=True),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_experiences_user_id", "experiences", ["user_id"])

    # Create education table
    op.create_table(
        "education",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("institution", sa.String(255), nullable=False),
        sa.Column("degree", sa.String(100), nullable=True),
        sa.Column("field", sa.String(255), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_education_user_id", "education", ["user_id"])

    # Create bullets table
    op.create_table(
        "bullets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("experience_id", sa.Uuid(), nullable=False),
        sa.Column(
            "type",
            postgresql.ENUM(
                "business_impact", "technical_design", "implementation",
                "scale", "collaboration", "problem_solving",
                name="bullettype", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), default=3),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("star_data", postgresql.JSONB(), default=dict),
        sa.Column("tech_stack", postgresql.JSONB(), default=list),
        sa.Column("jd_keywords", postgresql.JSONB(), default=list),
        sa.Column(
            "confidence",
            postgresql.ENUM("high", "medium", "low", name="confidence", create_type=False),
            nullable=False,
        ),
        sa.Column("missing", postgresql.JSONB(), default=list),
        sa.Column("is_visible", sa.Boolean(), default=True),
        sa.ForeignKeyConstraint(["experience_id"], ["experiences.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bullets_user_id", "bullets", ["user_id"])

    # Create projects table
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("role", sa.String(255), nullable=True),
        sa.Column("tech_stack", postgresql.JSONB(), default=list),
        sa.Column("bullets", postgresql.JSONB(), default=list),
        sa.Column("is_visible", sa.Boolean(), default=True),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])

    # Create jd_records table
    op.create_table(
        "jd_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("required_skills", postgresql.JSONB(), default=list),
        sa.Column("preferred_skills", postgresql.JSONB(), default=list),
        sa.Column("key_requirements", postgresql.JSONB(), default=list),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_jd_records_user_id", "jd_records", ["user_id"])

    # Create workflow_definitions table
    op.create_table(
        "workflow_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("description", sa.Text(), default=""),
        sa.Column("steps", postgresql.JSONB(), default=list),
        sa.Column(
            "trigger_type",
            postgresql.ENUM(
                "manual", "email", "git-hook", "scheduled",
                name="triggertype", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_definitions_user_id", "workflow_definitions", ["user_id"])

    # Create workflow_runs table
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("workflow_definition_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending", "running", "failed", "completed",
                name="runstatus", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("trigger_data", postgresql.JSONB(), default=dict),
        sa.ForeignKeyConstraint(["workflow_definition_id"], ["workflow_definitions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_runs_user_id", "workflow_runs", ["user_id"])

    # Create step_runs table
    op.create_table(
        "step_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("step_name", sa.String(100), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending", "running", "failed", "completed",
                name="runstatus", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("input_snapshot", postgresql.JSONB(), default=dict),
        sa.Column("output_snapshot", postgresql.JSONB(), default=dict),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_step_runs_user_id", "step_runs", ["user_id"])

    # Create resume_artifacts table
    op.create_table(
        "resume_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("jd_record_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=True),
        sa.Column("language", sa.String(10), default="en"),
        sa.Column("content_md", sa.Text(), nullable=True),
        sa.Column("content_tex", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["jd_record_id"], ["jd_records.id"]),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_resume_artifacts_user_id", "resume_artifacts", ["user_id"])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table("resume_artifacts")
    op.drop_table("step_runs")
    op.drop_table("workflow_runs")
    op.drop_table("workflow_definitions")
    op.drop_table("jd_records")
    op.drop_table("projects")
    op.drop_table("bullets")
    op.drop_table("education")
    op.drop_table("experiences")
    op.drop_table("skills")
    op.drop_table("profiles")

    # Drop enum types
    op.execute("DROP TYPE runstatus")
    op.execute("DROP TYPE triggertype")
    op.execute("DROP TYPE confidence")
    op.execute("DROP TYPE bullettype")
    op.execute("DROP TYPE skilllevel")
