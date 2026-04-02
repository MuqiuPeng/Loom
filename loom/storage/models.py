"""SQLAlchemy ORM models for PostgreSQL persistence.

Maps to the Pydantic schemas in base.py, profile.py, bullet.py, etc.
Uses JSONB for complex nested structures.
"""

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from loom.storage.bullet import BulletType, Confidence
from loom.storage.execution import RunStatus, TriggerType
from loom.storage.profile import SkillLevel


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class ProfileModel(Base):
    """ORM model for Profile."""

    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(String(100), default="local", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Bilingual name
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    name_zh: Mapped[str | None] = mapped_column(String(255), nullable=True)

    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phone_en: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phone_zh: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Bilingual location
    location_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location_zh: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Links
    github: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linkedin: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Bilingual summary
    summary_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_zh: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Certifications (JSONB list)
    certifications: Mapped[list] = mapped_column(JSONB, default=list)

    # Relationships
    skills: Mapped[list["SkillModel"]] = relationship(back_populates="profile")
    experiences: Mapped[list["ExperienceModel"]] = relationship(back_populates="profile")
    education: Mapped[list["EducationModel"]] = relationship(back_populates="profile")
    projects: Mapped[list["ProjectModel"]] = relationship(back_populates="profile")


class SkillModel(Base):
    """ORM model for Skill."""

    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(String(100), default="local", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    profile_id: Mapped[str] = mapped_column(Uuid, ForeignKey("profiles.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[SkillLevel] = mapped_column(
        Enum(SkillLevel), default=SkillLevel.PROFICIENT
    )

    category: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Bilingual context
    context_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_zh: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationship
    profile: Mapped["ProfileModel"] = relationship(back_populates="skills")


class ExperienceModel(Base):
    """ORM model for Experience."""

    __tablename__ = "experiences"

    id: Mapped[str] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(String(100), default="local", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    profile_id: Mapped[str] = mapped_column(Uuid, ForeignKey("profiles.id"), nullable=False)

    # Bilingual fields
    company_en: Mapped[str] = mapped_column(String(255), nullable=False)
    company_zh: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title_en: Mapped[str] = mapped_column(String(255), nullable=False)
    title_zh: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location_zh: Mapped[str | None] = mapped_column(String(255), nullable=True)

    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    profile: Mapped["ProfileModel"] = relationship(back_populates="experiences")
    bullets: Mapped[list["BulletModel"]] = relationship(back_populates="experience")


class EducationModel(Base):
    """ORM model for Education."""

    __tablename__ = "education"

    id: Mapped[str] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(String(100), default="local", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    profile_id: Mapped[str] = mapped_column(Uuid, ForeignKey("profiles.id"), nullable=False)

    # Bilingual fields
    institution_en: Mapped[str] = mapped_column(String(255), nullable=False)
    institution_zh: Mapped[str | None] = mapped_column(String(255), nullable=True)
    degree_en: Mapped[str | None] = mapped_column(String(100), nullable=True)
    degree_zh: Mapped[str | None] = mapped_column(String(100), nullable=True)
    field_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    field_zh: Mapped[str | None] = mapped_column(String(255), nullable=True)

    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Relationship
    profile: Mapped["ProfileModel"] = relationship(back_populates="education")


class BulletModel(Base):
    """ORM model for Bullet."""

    __tablename__ = "bullets"

    id: Mapped[str] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(String(100), default="local", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    experience_id: Mapped[str] = mapped_column(
        Uuid, ForeignKey("experiences.id"), nullable=False
    )
    type: Mapped[BulletType] = mapped_column(
        Enum(BulletType), default=BulletType.IMPLEMENTATION
    )
    priority: Mapped[int] = mapped_column(Integer, default=3)

    # Bilingual display text
    content_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_zh: Mapped[str | None] = mapped_column(Text, nullable=True)

    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    star_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    tech_stack: Mapped[list] = mapped_column(JSONB, default=list)
    jd_keywords: Mapped[list] = mapped_column(JSONB, default=list)

    confidence: Mapped[Confidence] = mapped_column(
        Enum(Confidence), default=Confidence.MEDIUM
    )
    missing: Mapped[list] = mapped_column(JSONB, default=list)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationship
    experience: Mapped["ExperienceModel"] = relationship(back_populates="bullets")


class ProjectModel(Base):
    """ORM model for Project."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(String(100), default="local", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    profile_id: Mapped[str] = mapped_column(Uuid, ForeignKey("profiles.id"), nullable=False)
    experience_id: Mapped[str | None] = mapped_column(
        Uuid, ForeignKey("experiences.id"), nullable=True
    )
    education_id: Mapped[str | None] = mapped_column(
        Uuid, ForeignKey("education.id"), nullable=True
    )

    # Bilingual fields
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    name_zh: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_zh: Mapped[str | None] = mapped_column(Text, nullable=True)
    role_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role_zh: Mapped[str | None] = mapped_column(String(255), nullable=True)

    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    tech_stack: Mapped[list] = mapped_column(JSONB, default=list)
    bullets: Mapped[list] = mapped_column(JSONB, default=list)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)

    # Repo tracking
    local_repo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    auto_update: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    profile: Mapped["ProfileModel"] = relationship(back_populates="projects")
    experience: Mapped["ExperienceModel | None"] = relationship()


class JDRecordModel(Base):
    """ORM model for JDRecord."""

    __tablename__ = "jd_records"

    id: Mapped[str] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(String(100), default="local", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    required_skills: Mapped[list] = mapped_column(JSONB, default=list)
    preferred_skills: Mapped[list] = mapped_column(JSONB, default=list)
    key_requirements: Mapped[list] = mapped_column(JSONB, default=list)

    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationships
    resume_artifacts: Mapped[list["ResumeArtifactModel"]] = relationship(
        back_populates="jd_record"
    )


class ResumeArtifactModel(Base):
    """ORM model for ResumeArtifact."""

    __tablename__ = "resume_artifacts"

    id: Mapped[str] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(String(100), default="local", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    jd_record_id: Mapped[str | None] = mapped_column(
        Uuid, ForeignKey("jd_records.id"), nullable=True
    )
    workflow_run_id: Mapped[str | None] = mapped_column(
        Uuid, nullable=True  # No FK - workflow may not exist in DB
    )

    language: Mapped[str] = mapped_column(String(10), default="en")
    content_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_tex: Mapped[str | None] = mapped_column(Text, nullable=True)

    pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    starred: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="completed")
    generation_progress: Mapped[str | None] = mapped_column(String(100), nullable=True)  # kept for migration compat

    # Relationship (only jd_record has FK)
    jd_record: Mapped["JDRecordModel | None"] = relationship(back_populates="resume_artifacts")


class TaskModel(Base):
    """ORM model for async Task tracking."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(String(100), default="local", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    input_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    output_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class WorkflowDefinitionModel(Base):
    """ORM model for WorkflowDefinition."""

    __tablename__ = "workflow_definitions"

    id: Mapped[str] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(String(100), default="local", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    steps: Mapped[list] = mapped_column(JSONB, default=list)
    trigger_type: Mapped[TriggerType] = mapped_column(
        Enum(TriggerType), default=TriggerType.MANUAL
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    workflow_runs: Mapped[list["WorkflowRunModel"]] = relationship(
        back_populates="workflow_definition"
    )


class WorkflowRunModel(Base):
    """ORM model for WorkflowRun."""

    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(String(100), default="local", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    workflow_definition_id: Mapped[str] = mapped_column(
        Uuid, ForeignKey("workflow_definitions.id"), nullable=False
    )
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), default=RunStatus.PENDING)
    trigger_data: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Relationships
    workflow_definition: Mapped["WorkflowDefinitionModel"] = relationship(
        back_populates="workflow_runs"
    )
    step_runs: Mapped[list["StepRunModel"]] = relationship(back_populates="workflow_run")


class StepRunModel(Base):
    """ORM model for StepRun."""

    __tablename__ = "step_runs"

    id: Mapped[str] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(String(100), default="local", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    workflow_run_id: Mapped[str] = mapped_column(
        Uuid, ForeignKey("workflow_runs.id"), nullable=False
    )
    step_name: Mapped[str] = mapped_column(String(100), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), default=RunStatus.PENDING)
    input_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    output_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationship
    workflow_run: Mapped["WorkflowRunModel"] = relationship(back_populates="step_runs")


class TokenUsageModel(Base):
    """ORM model for TokenUsage - tracks LLM API token consumption."""

    __tablename__ = "token_usages"

    id: Mapped[str] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(String(100), default="local", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # API call details
    model: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)

    # Cost (stored as string for precision)
    input_cost_usd: Mapped[str] = mapped_column(String(50), default="0")
    output_cost_usd: Mapped[str] = mapped_column(String(50), default="0")
    total_cost_usd: Mapped[str] = mapped_column(String(50), default="0")

    # Context for aggregation (no FK constraint - workflow may not exist in DB)
    workflow_run_id: Mapped[str | None] = mapped_column(Uuid, nullable=True, index=True)
    step_name: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    caller: Mapped[str] = mapped_column(String(100), default="unknown")


class LogEntryModel(Base):
    """ORM model for system log entries."""

    __tablename__ = "log_entries"

    id: Mapped[str] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(String(100), default="local", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    level: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    workflow_run_id: Mapped[str | None] = mapped_column(Uuid, nullable=True, index=True)
    step_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
