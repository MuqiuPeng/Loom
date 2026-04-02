"""Project schema - project experience entries.

Bilingual support for name, description, and role fields.
tech_stack and bullets (JSONB) are language-agnostic.
"""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from loom.storage.base import BaseEntity


class Project(BaseEntity):
    """A project entry in the profile.

    Projects can be linked to an Experience (work projects) or standalone
    (personal/side projects with experience_id=None).
    """

    profile_id: UUID = Field(..., description="FK to Profile")
    experience_id: UUID | None = Field(
        default=None,
        description="FK to Experience. None = personal/side project.",
    )
    education_id: UUID | None = Field(
        default=None,
        description="FK to Education. For thesis/academic projects.",
    )

    # Bilingual fields
    name_en: str = Field(...)
    name_zh: str | None = Field(default=None)

    description_en: str | None = Field(default=None)
    description_zh: str | None = Field(default=None)

    role_en: str | None = Field(default=None, description="Role in the project (English)")
    role_zh: str | None = Field(default=None, description="Role in the project (Chinese)")

    # Dates
    start_date: date | None = Field(default=None)
    end_date: date | None = Field(default=None, description="None = ongoing")

    # Language-agnostic
    tech_stack: list[dict[str, Any]] = Field(
        default_factory=list,
        description="JSONB: [{name, role, ecosystem_group}]"
    )
    bullets: list[dict[str, Any]] = Field(
        default_factory=list,
        description="JSONB: Project-specific achievements"
    )
    is_visible: bool = Field(default=True)

    # Repo tracking
    local_repo_path: str | None = Field(default=None, description="Absolute path to local repo")
    last_analyzed_at: datetime | None = Field(default=None, description="Last /analyze-repo time")
    auto_update: bool = Field(default=False, description="Reserved for future auto-update")
