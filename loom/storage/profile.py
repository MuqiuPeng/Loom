"""Profile-related schemas - candidate information.

All text fields that users see on a resume support bilingual (en/zh) variants.
Fields that are proper nouns (company, institution) default zh to the en value.
Fields that are language-agnostic (dates, skill names) stay single-valued.
"""

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

    # Bilingual name / location
    name_en: str = Field(..., description="Full name (English)")
    name_zh: str | None = Field(default=None, description="Full name (Chinese)")

    email: str | None = Field(default=None)
    phone: str | None = Field(default=None, description="Phone (legacy single field)")
    phone_en: str | None = Field(default=None, description="Phone for EN resume")
    phone_zh: str | None = Field(default=None, description="Phone for ZH resume")

    location_en: str | None = Field(default=None, description="Location (English)")
    location_zh: str | None = Field(default=None, description="Location (Chinese)")

    github: str | None = Field(default=None, description="GitHub URL")
    linkedin: str | None = Field(default=None, description="LinkedIn URL")

    # Bilingual summary
    summary_en: str | None = Field(default=None, description="Professional summary (English)")
    summary_zh: str | None = Field(default=None, description="Professional summary (Chinese)")

    # Certifications as JSONB list: [{"year": "2025", "name": "AWS Certified..."}]
    certifications: list[dict] = Field(default_factory=list)


class Skill(BaseEntity):
    """A skill associated with a profile."""

    profile_id: UUID = Field(..., description="FK to Profile")
    name: str = Field(..., description="Skill name, e.g. 'Python' - not translated")
    level: SkillLevel = Field(default=SkillLevel.PROFICIENT)
    category: str | None = Field(
        default=None,
        description="Usage-scenario category: Backend, Frontend, AI/ML, Database, "
        "DevOps/Infra, Testing, etc.",
    )

    # Bilingual context
    context_en: str | None = Field(default=None, description="Usage context (English)")
    context_zh: str | None = Field(default=None, description="Usage context (Chinese)")


class Experience(BaseEntity):
    """Work experience entry."""

    profile_id: UUID = Field(..., description="FK to Profile")

    # Proper nouns - zh defaults to en value
    company_en: str = Field(...)
    company_zh: str | None = Field(default=None, description="Defaults to company_en if None")

    # Bilingual fields
    title_en: str = Field(...)
    title_zh: str | None = Field(default=None)

    location_en: str | None = Field(default=None)
    location_zh: str | None = Field(default=None)

    # Language-agnostic
    start_date: date | None = Field(default=None)
    end_date: date | None = Field(default=None, description="None = current")
    is_visible: bool = Field(
        default=True,
        description="Whether to include in resume generation"
    )


class Education(BaseEntity):
    """Education entry."""

    profile_id: UUID = Field(..., description="FK to Profile")

    # Proper nouns - zh defaults to en value
    institution_en: str = Field(...)
    institution_zh: str | None = Field(default=None, description="Defaults to institution_en if None")

    # Bilingual fields
    degree_en: str | None = Field(default=None)
    degree_zh: str | None = Field(default=None)

    field_en: str | None = Field(default=None, description="Field of study (English)")
    field_zh: str | None = Field(default=None, description="Field of study (Chinese)")

    # Language-agnostic
    start_date: date | None = Field(default=None)
    end_date: date | None = Field(default=None)
