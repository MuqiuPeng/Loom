"""SelectBulletsStep - selects most relevant bullets for JD."""

from typing import Any
from uuid import UUID

from loom.core.context import PipelineContext
from loom.core.registry import step_registry
from loom.core.step import Step
from loom.storage.bullet import Bullet, BulletType, Confidence
from loom.storage.profile import Experience
from loom.storage.repository import BulletRepository, DataStorage, InMemoryDataStorage

# Type ordering for sorting within each experience
TYPE_ORDER = {
    BulletType.BUSINESS_IMPACT: 0,
    BulletType.TECHNICAL_DESIGN: 1,
    BulletType.SCALE: 1,
    BulletType.IMPLEMENTATION: 2,
    BulletType.PROBLEM_SOLVING: 2,
    BulletType.COLLABORATION: 3,
}

# Keywords for detecting JD focus areas
SCALE_KEYWORDS = {"scale", "performance", "throughput", "latency", "optimization", "efficient"}
DESIGN_KEYWORDS = {"architect", "design", "system", "infrastructure", "framework"}
COLLAB_KEYWORDS = {"team", "collaborate", "lead", "mentor", "coordinate", "cross-functional"}

# Limits
MAX_BULLETS_PER_EXPERIENCE = 3
MAX_TOTAL_BULLETS = 12


class SelectBulletsStep(Step):
    """Select most relevant bullets based on JD matching.

    This step uses pure logic (no Claude calls) to select bullets,
    controlling token costs for the generation step.

    Input:
        context.data["jd_parsed"]    - structured JD data
        context.data["match_result"] - matching results

    Output:
        context.data["selected_bullets"] - selected bullets by experience
    """

    @property
    def name(self) -> str:
        return "select-bullets"

    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or InMemoryDataStorage()
        self.bullet_repo = BulletRepository(self.storage)

    async def run(self, context: PipelineContext) -> PipelineContext:
        jd_parsed = context.data.get("jd_parsed")
        if not jd_parsed:
            raise ValueError("context.data['jd_parsed'] is required")

        match_result = context.data.get("match_result", {})

        # Get all bullets for user
        exp_bullets = await self.bullet_repo.get_all_bullets_for_user(context.user_id)

        if not exp_bullets:
            # No bullets found - return empty result
            result = self._build_empty_result("No bullets found in profile")
            new_data = {**context.data, "selected_bullets": result}
            return context.model_copy(update={"data": new_data})

        # Detect JD focus areas
        jd_focus = self._detect_jd_focus(jd_parsed)

        # Process each experience
        by_experience: dict[str, list[dict]] = {}
        total_count = 0
        skills_covered: set[str] = set()

        for exp, bullets in exp_bullets:
            if total_count >= MAX_TOTAL_BULLETS:
                break

            selected = self._select_for_experience(
                exp, bullets, jd_parsed, jd_focus
            )

            if selected:
                # Respect global limit
                remaining = MAX_TOTAL_BULLETS - total_count
                selected = selected[:remaining]

                by_experience[str(exp.id)] = selected
                total_count += len(selected)

                # Track skills covered
                for b in selected:
                    for tech in b.get("tech_stack", []):
                        tech_name = tech.get("name") if isinstance(tech, dict) else str(tech)
                        skills_covered.add(tech_name)

        # Build coverage info
        required_skills = set(jd_parsed.get("required_skills", []))
        covered = skills_covered & required_skills
        gaps = required_skills - skills_covered

        result = {
            "by_experience": by_experience,
            "total_count": total_count,
            "selection_reasoning": {
                "jd_focus": jd_focus,
                "coverage": {
                    "required_skills_covered": list(covered),
                    "gaps_not_covered": list(gaps),
                },
            },
        }

        new_data = {**context.data, "selected_bullets": result}
        return context.model_copy(update={"data": new_data})

    def _detect_jd_focus(self, jd_parsed: dict) -> list[str]:
        """Detect JD focus areas from key_requirements."""
        focus = []
        requirements_text = " ".join(
            jd_parsed.get("key_requirements", [])
        ).lower()

        if any(kw in requirements_text for kw in SCALE_KEYWORDS):
            focus.append("scale")
        if any(kw in requirements_text for kw in DESIGN_KEYWORDS):
            focus.append("technical_design")
        if any(kw in requirements_text for kw in COLLAB_KEYWORDS):
            focus.append("collaboration")

        return focus

    def _select_for_experience(
        self,
        exp: Experience,
        bullets: list[Bullet],
        jd_parsed: dict,
        jd_focus: list[str],
    ) -> list[dict]:
        """Select and sort bullets for a single experience."""

        # Phase 1: Filter
        filtered = self._filter_bullets(bullets)
        if not filtered:
            return []

        # Phase 2: Score
        scored = [
            (b, self._score_bullet(b, jd_parsed, jd_focus))
            for b in filtered
        ]

        # Phase 3: Select
        selected = self._select_top_bullets(scored)

        # Phase 4: Sort
        sorted_bullets = self._sort_bullets(selected)

        # Convert to output format
        return [
            {
                "bullet_id": str(b.id),
                "type": b.type.value,
                "raw_text": b.raw_text,
                "star_data": b.star_data,
                "tech_stack": b.tech_stack,
                "score": score,
            }
            for b, score in sorted_bullets
        ]

    def _filter_bullets(self, bullets: list[Bullet]) -> list[Bullet]:
        """Phase 1: Filter out invisible and low-confidence bullets."""
        return [
            b for b in bullets
            if b.is_visible
            and not (b.confidence == Confidence.LOW and b.missing)
        ]

    def _score_bullet(
        self,
        bullet: Bullet,
        jd_parsed: dict,
        jd_focus: list[str],
    ) -> int:
        """Phase 2: Calculate relevance score for a bullet."""
        # Base score from priority (1=highest priority, so invert)
        score = 6 - bullet.priority  # priority 1 → 5, priority 5 → 1

        required_skills = set(s.lower() for s in jd_parsed.get("required_skills", []))
        preferred_skills = set(s.lower() for s in jd_parsed.get("preferred_skills", []))
        key_requirements = " ".join(jd_parsed.get("key_requirements", [])).lower()

        # Tech stack matching
        for tech in bullet.tech_stack:
            tech_name = tech.get("name", "") if isinstance(tech, dict) else str(tech)
            tech_lower = tech_name.lower()
            if tech_lower in required_skills:
                score += 2
            elif tech_lower in preferred_skills:
                score += 1

        # JD keywords matching
        for keyword in bullet.jd_keywords:
            if keyword.lower() in key_requirements:
                score += 1

        # Type bonus based on JD focus
        if bullet.type == BulletType.BUSINESS_IMPACT:
            score += 1  # Always bonus for business impact

        if "scale" in jd_focus and bullet.type == BulletType.SCALE:
            score += 2
        if "technical_design" in jd_focus and bullet.type == BulletType.TECHNICAL_DESIGN:
            score += 2
        if "collaboration" in jd_focus and bullet.type == BulletType.COLLABORATION:
            score += 2

        return score

    def _select_top_bullets(
        self,
        scored: list[tuple[Bullet, int]],
    ) -> list[tuple[Bullet, int]]:
        """Phase 3: Select top bullets with business_impact priority."""

        # Separate business_impact bullets
        business_impact = [
            (b, s) for b, s in scored
            if b.type == BulletType.BUSINESS_IMPACT
        ]
        others = [
            (b, s) for b, s in scored
            if b.type != BulletType.BUSINESS_IMPACT
        ]

        # Sort by score descending
        business_impact.sort(key=lambda x: x[1], reverse=True)
        others.sort(key=lambda x: x[1], reverse=True)

        selected = []

        # Must include top business_impact if available
        if business_impact:
            selected.append(business_impact[0])

        # Fill remaining slots
        remaining_slots = MAX_BULLETS_PER_EXPERIENCE - len(selected)
        selected.extend(others[:remaining_slots])

        return selected

    def _sort_bullets(
        self,
        bullets: list[tuple[Bullet, int]],
    ) -> list[tuple[Bullet, int]]:
        """Phase 4: Sort bullets by type order."""
        return sorted(
            bullets,
            key=lambda x: TYPE_ORDER.get(x[0].type, 99),
        )

    def _build_empty_result(self, reason: str) -> dict:
        """Build empty result with reasoning."""
        return {
            "by_experience": {},
            "total_count": 0,
            "selection_reasoning": {
                "jd_focus": [],
                "coverage": {
                    "required_skills_covered": [],
                    "gaps_not_covered": [],
                },
                "note": reason,
            },
        }


# Register step
step_registry.register("select-bullets", SelectBulletsStep)
