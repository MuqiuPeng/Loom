"""Resume-related schemas - JD records and generated artifacts."""

from typing import Any
from uuid import UUID

from pydantic import Field

from loom.storage.base import BaseEntity


class JDRecord(BaseEntity):
    """Parsed job description record."""

    company: str | None = Field(default=None)
    title: str = Field(...)
    raw_text: str = Field(..., description="Original JD text")

    # Extracted requirements (JSONB)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    key_requirements: list[str] = Field(
        default_factory=list,
        description="Key qualifications and requirements"
    )

    # Matching results
    match_score: float | None = Field(
        default=None,
        description="Latest match score (0-100)"
    )


class ResumeArtifact(BaseEntity):
    """Generated resume artifact."""

    jd_record_id: UUID = Field(..., description="FK to JDRecord")
    workflow_run_id: UUID | None = Field(
        default=None,
        description="FK to WorkflowRun that generated this"
    )

    language: str = Field(default="en", description="'en' or 'zh'")
    content_md: str | None = Field(
        default=None,
        description="Generated Markdown content"
    )
    content_tex: str | None = Field(
        default=None,
        description="Generated LaTeX content"
    )
