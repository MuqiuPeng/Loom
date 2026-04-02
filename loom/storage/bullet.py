"""Bullet schema - STAR-structured experience highlights.

Bilingual support: content_en / content_zh for display text.
raw_text is the original user input, kept permanently and language-agnostic.
"""

from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import Field

from loom.storage.base import BaseEntity


class BulletType(str, Enum):
    """Type of achievement/highlight."""

    BUSINESS_IMPACT = "business_impact"
    TECHNICAL_DESIGN = "technical_design"
    IMPLEMENTATION = "implementation"
    SCALE = "scale"
    COLLABORATION = "collaboration"
    PROBLEM_SOLVING = "problem_solving"


class Confidence(str, Enum):
    """Confidence level of extracted information."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class STARData(BaseEntity):
    """STAR structure for a bullet point."""

    situation: str | None = Field(default=None)
    task: str | None = Field(default=None)
    action: str | None = Field(default=None)
    result_quantified: str | None = Field(
        default=None,
        description="Quantified result with numbers"
    )
    result_qualitative: str | None = Field(
        default=None,
        description="Qualitative impact description"
    )


class TechStackItem(BaseEntity):
    """A technology in a bullet's tech stack."""

    name: str = Field(..., description="Technology name")
    role: str | None = Field(
        default=None,
        description="Role in the solution, e.g. 'orchestration'"
    )
    ecosystem_group: str | None = Field(
        default=None,
        description="Grouping for narrative, e.g. 'AWS'"
    )


class Bullet(BaseEntity):
    """A STAR-structured experience highlight.

    Bullets are the atomic units for resume generation.
    They're matched against JD requirements and selected
    based on relevance.
    """

    experience_id: UUID = Field(..., description="FK to Experience")
    type: BulletType = Field(default=BulletType.IMPLEMENTATION)
    priority: int = Field(
        default=3,
        ge=1,
        le=5,
        description="1=highest, 5=lowest"
    )

    # Bilingual display text
    content_en: str | None = Field(
        default=None,
        description="English display text for the bullet"
    )
    content_zh: str | None = Field(
        default=None,
        description="Chinese display text for the bullet"
    )

    # Original input - permanently preserved, language-agnostic
    raw_text: str = Field(
        ...,
        description="User's original description, always preserved"
    )
    star_data: dict[str, Any] = Field(
        default_factory=dict,
        description="JSONB: {situation, task, action, result_quantified, result_qualitative}"
    )

    # Matching metadata - language-agnostic
    tech_stack: list[dict[str, Any]] = Field(
        default_factory=list,
        description="JSONB: [{name, role, ecosystem_group}]"
    )
    jd_keywords: list[str] = Field(
        default_factory=list,
        description="JSONB: Keywords this bullet can cover"
    )

    # Quality indicators
    confidence: Confidence = Field(default=Confidence.MEDIUM)
    missing: list[str] = Field(
        default_factory=list,
        description="JSONB: What information is still needed"
    )

    is_visible: bool = Field(default=True)
