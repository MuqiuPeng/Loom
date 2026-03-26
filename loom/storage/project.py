"""Project schema - project experience entries."""

from typing import Any
from uuid import UUID

from pydantic import Field

from loom.storage.base import BaseEntity


class Project(BaseEntity):
    """A project entry in the profile."""

    profile_id: UUID = Field(..., description="FK to Profile")
    name: str = Field(...)
    description: str | None = Field(default=None)
    role: str | None = Field(default=None, description="Role in the project")
    tech_stack: list[dict[str, Any]] = Field(
        default_factory=list,
        description="JSONB: [{name, role, ecosystem_group}]"
    )
    bullets: list[dict[str, Any]] = Field(
        default_factory=list,
        description="JSONB: Project-specific achievements"
    )
    is_visible: bool = Field(default=True)
