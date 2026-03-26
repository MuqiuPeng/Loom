"""Profile-related schemas - candidate information."""

from datetime import date
from enum import Enum
from uuid import UUID

from pydantic import Field

from loom.storage.base import BaseEntity


class SkillLevel(str, Enum):
    """Proficiency level for a skill."""

    EXPERT = "expert"
    PROFICIENT = "proficient"
    FAMILIAR = "familiar"


class Profile(BaseEntity):
    """Candidate's basic information."""

    name: str = Field(...)
    email: str | None = Field(default=None)
    phone: str | None = Field(default=None)
    location: str | None = Field(default=None)
    summary: str | None = Field(default=None, description="Professional summary")


class Skill(BaseEntity):
    """A skill associated with a profile."""

    profile_id: UUID = Field(..., description="FK to Profile")
    name: str = Field(..., description="Skill name, e.g. 'Python'")
    level: SkillLevel = Field(default=SkillLevel.PROFICIENT)
    context: str | None = Field(
        default=None,
        description="Usage context description"
    )


class Experience(BaseEntity):
    """Work experience entry."""

    profile_id: UUID = Field(..., description="FK to Profile")
    company: str = Field(...)
    title: str = Field(...)
    location: str | None = Field(default=None)
    start_date: date | None = Field(default=None)
    end_date: date | None = Field(default=None, description="None = current")
    is_visible: bool = Field(
        default=True,
        description="Whether to include in resume generation"
    )


class Education(BaseEntity):
    """Education entry."""

    profile_id: UUID = Field(..., description="FK to Profile")
    institution: str = Field(...)
    degree: str | None = Field(default=None)
    field: str | None = Field(default=None, description="Field of study")
    start_date: date | None = Field(default=None)
    end_date: date | None = Field(default=None)
