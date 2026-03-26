"""Storage schemas for Loom.

Organized into:
- base: BaseEntity (inherited by all)
- execution: WorkflowDefinition, WorkflowRun, StepRun
- profile: Profile, Skill, Experience, Education
- bullet: Bullet, BulletType, STARData
- project: Project
- resume: JDRecord, ResumeArtifact
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
from loom.storage.resume import JDRecord, ResumeArtifact

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
]
