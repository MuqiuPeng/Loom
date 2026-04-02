"""Storage schemas for Loom.

Organized into:
- base: BaseEntity (inherited by all)
- execution: WorkflowDefinition, WorkflowRun, StepRun
- profile: Profile, Skill, Experience, Education
- bullet: Bullet, BulletType, STARData
- project: Project
- resume: JDRecord, ResumeArtifact
- usage: TokenUsage, UsageSummary (LLM usage tracking)
- repository: ProfileRepository, JDRepository, UsageRepository, DataStorage
- postgres: PostgresDataStorage (PostgreSQL implementation)
- database: Async engine and session management
- models: SQLAlchemy ORM models
- init_db: Database initialization utilities
"""

from loom.storage.base import BaseEntity
from loom.storage.bullet import Bullet, BulletType, Confidence, STARData, TechStackItem
from loom.storage.execution import (
    RunStatus,
    StepConfig,
    StepRun,
    TriggerType,
    WorkflowDefinition,
    WorkflowRun,
)
from loom.storage.profile import Education, Experience, Profile, Skill, SkillLevel
from loom.storage.project import Project
from loom.storage.repository import (
    BulletRepository,
    DataStorage,
    ExperienceRepository,
    InMemoryDataStorage,
    JDRepository,
    ProfileRepository,
    ResumeRepository,
    UsageRepository,
)
from loom.storage.resume import JDRecord, ResumeArtifact
from loom.storage.usage import TokenUsage, UsageSummary

__all__ = [
    # Base
    "BaseEntity",
    # Execution
    "WorkflowDefinition",
    "WorkflowRun",
    "StepRun",
    "StepConfig",
    "RunStatus",
    "TriggerType",
    # Profile
    "Profile",
    "Skill",
    "SkillLevel",
    "Experience",
    "Education",
    # Bullet
    "Bullet",
    "BulletType",
    "STARData",
    "TechStackItem",
    "Confidence",
    # Project
    "Project",
    # Resume
    "JDRecord",
    "ResumeArtifact",
    # Usage
    "TokenUsage",
    "UsageSummary",
    # Repository
    "ProfileRepository",
    "JDRepository",
    "BulletRepository",
    "ExperienceRepository",
    "ResumeRepository",
    "UsageRepository",
    "DataStorage",
    "InMemoryDataStorage",
]


# Lazy imports for PostgreSQL support (requires asyncpg)
def __getattr__(name: str):
    if name == "PostgresDataStorage":
        from loom.storage.postgres import PostgresDataStorage
        return PostgresDataStorage
    if name == "PostgresDataStorageContext":
        from loom.storage.postgres import PostgresDataStorageContext
        return PostgresDataStorageContext
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
