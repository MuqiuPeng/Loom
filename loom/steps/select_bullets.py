"""SelectBulletsStep - Claude-powered semantic selection of bullets and projects."""

import json
import logging
from typing import Any
from uuid import UUID

from loom.core.context import PipelineContext
from loom.core.registry import step_registry
from loom.core.step import Step
from loom.llm import Claude, Model
from loom.storage.bullet import Bullet, BulletType, Confidence
from loom.storage.profile import Experience
from loom.storage.repository import (
    BulletRepository,
    DataStorage,
    InMemoryDataStorage,
    ProfileRepository,
)

logger = logging.getLogger(__name__)

# Low-value content patterns — code-level filter (kept as safety net)
LOW_VALUE_PATTERNS = [
    "git branching", "git workflow", "branch strateg",
    "daily standup", "sprint planning", "used jira",
    "familiar with", "experience using", "exposure to",
    "participated in meetings",
    "followed best practices", "maintained documentation",
]

MAX_BULLETS_PER_EXPERIENCE = 4
MAX_TOTAL_BULLETS = 16

# ── Prompts ──────────────────────────────────────────────────────────

BULLET_SCORE_SYSTEM = """\
You are a senior recruiter scoring resume bullets for relevance to a specific job.
Score each bullet 0-100 based on how directly it demonstrates what the JD requires.

Scoring guide:
90-100: Directly demonstrates a core JD requirement in the same domain
70-89:  Strong relevance, clearly useful evidence for this role
50-69:  Partial relevance, some overlap in skills or domain
30-49:  Different domain but has transferable skills
0-29:   Unrelated to this specific role

IMPORTANT: Score the actual WORK described, not just keyword matches.
Building a tool for a domain != expertise in that domain.

Return ONLY valid JSON:
{
  "scores": [
    {"id": "bullet_id", "score": 85, "reasoning": "one sentence"}
  ]
}"""

BULLET_SCORE_USER = """\
Score each bullet for relevance to this job.

== JD ==
Required Skills: {required_skills}
Key Requirements: {key_requirements}
JD Focus: {jd_focus}

== BULLETS ==
{bullets_json}

Return JSON only."""

PROJECT_SCORE_SYSTEM = """\
You are a senior recruiter scoring projects for relevance to a specific job.
Score each project 0-100 based on how compelling it would be as evidence for this role.

Scoring guide:
90-100: Project directly demonstrates core JD requirements in same domain
70-89:  Strong overlap in domain and skills
50-69:  Some relevant aspects
30-49:  Different domain, transferable skills only
0-29:   Unrelated to this role

IMPORTANT: Building a TOOL for a domain != expertise in that domain.
"Built A/B testing platform" = software engineering, NOT A/B testing expertise.
"Ran A/B tests, analyzed significance" = direct A/B testing experience.

Return ONLY valid JSON:
{
  "scores": [
    {"name": "ProjectName", "score": 85, "reasoning": "one sentence"}
  ]
}"""

PROJECT_SCORE_USER = """\
Score each project for relevance to this job.

== JD ==
Required Skills: {required_skills}
Key Requirements: {key_requirements}
JD Focus: {jd_focus}

== PROJECTS ==
{projects_json}

Return JSON only."""


class SelectBulletsStep(Step):
    """Select most relevant bullets and projects using Claude semantic scoring.

    Uses 2 Haiku calls: one for bullets, one for projects.
    Falls back to rule-based scoring on failure.

    Input:
        context.data["jd_parsed"]
        context.data["match_result"]

    Output:
        context.data["selected_bullets"]
        context.data["integration_pool"]
    """

    @property
    def name(self) -> str:
        return "select-bullets"

    def __init__(self, storage: DataStorage | None = None, claude: Claude | None = None):
        self.storage = storage or InMemoryDataStorage()
        self.claude = claude or Claude()
        self.bullet_repo = BulletRepository(self.storage)
        self.profile_repo = ProfileRepository(self.storage)
        if storage:
            self.claude.set_storage(storage)

    async def run(self, context: PipelineContext) -> PipelineContext:
        jd_parsed = context.data.get("jd_parsed")
        if not jd_parsed:
            raise ValueError("context.data['jd_parsed'] is required")

        match_result = context.data.get("match_result", {})
        jd_focus = match_result.get("jd_focus", [])

        self.claude.set_context(
            workflow_run_id=context.workflow_id,
            step_name=self.name,
            user_id=context.user_id,
        )

        # Get all bullets
        exp_bullets = await self.bullet_repo.get_all_bullets_for_user(context.user_id)

        if not exp_bullets:
            result = self._build_empty_result("No bullets found in profile")
            new_data = {
                **context.data,
                "selected_bullets": result,
                "integration_pool": {"projects": [], "all_experiences": []},
            }
            return context.model_copy(update={"data": new_data})

        # ── Step 1: Filter bullets ───────────────────────────────

        filtered_exp_bullets: list[tuple[Experience, list[Bullet]]] = []
        for exp, bullets in exp_bullets:
            filtered = self._filter_bullets(bullets)
            if filtered:
                filtered_exp_bullets.append((exp, filtered))

        # ── Step 2: Claude scores bullets ────────────────────────

        bullet_scores = await self._score_bullets_claude(
            filtered_exp_bullets, jd_parsed, jd_focus,
        )

        # ── Step 3: Select top bullets per experience ────────────

        by_experience: dict[str, list[dict]] = {}
        total_count = 0
        skills_covered: set[str] = set()

        for exp, bullets in filtered_exp_bullets:
            if total_count >= MAX_TOTAL_BULLETS:
                break

            selected = self._select_by_score(exp, bullets, bullet_scores)
            if selected:
                remaining = MAX_TOTAL_BULLETS - total_count
                selected = selected[:remaining]
                by_experience[str(exp.id)] = selected
                total_count += len(selected)

                for b in selected:
                    for tech in b.get("tech_stack", []):
                        tech_name = tech.get("name") if isinstance(tech, dict) else str(tech)
                        skills_covered.add(tech_name)

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

        # ── Step 4: Build integration pool ───────────────────────

        integration_pool = await self._build_integration_pool(
            context.user_id, exp_bullets,
        )

        # ── Step 5: Claude scores projects ───────────────────────

        project_scores = await self._score_projects_claude(
            integration_pool.get("projects", []), jd_parsed, jd_focus,
        )
        integration_pool["project_scores"] = project_scores

        # ── Log ──────────────────────────────────────────────────

        try:
            from loom.services.logger import logger as _lg
            pool_projects = integration_pool.get("projects", [])
            await _lg.info("workflow", "step.select_bullets.integration_pool",
                f"Integration pool: {len(pool_projects)} projects",
                step_name=self.name,
                total_projects=len(pool_projects),
                project_names=[p.get("name", "") for p in pool_projects])

            # Log bullet scores per experience
            bullet_log: dict[str, list[dict]] = {}
            for exp, bullets in filtered_exp_bullets:
                company = exp.company_en or ""
                bullet_log[company] = [
                    {"content_preview": (b.content_en or "")[:60], "score": bullet_scores.get(str(b.id), 50)}
                    for b in bullets
                ]

            await _lg.info("workflow", "step.select_bullets.output",
                f"Selected {total_count} bullets across "
                f"{len(by_experience)} experiences, "
                f"{len(covered)} skills covered, {len(gaps)} gaps",
                step_name=self.name, total_count=total_count,
                num_projects=len(pool_projects),
                bullet_scores=bullet_log,
                project_scores=project_scores)
        except Exception:
            pass

        new_data = {
            **context.data,
            "selected_bullets": result,
            "integration_pool": integration_pool,
        }
        return context.model_copy(update={"data": new_data})

    # ── Claude scoring ───────────────────────────────────────────

    async def _score_bullets_claude(
        self,
        exp_bullets: list[tuple[Experience, list[Bullet]]],
        jd_parsed: dict,
        jd_focus: list[str],
    ) -> dict[str, int]:
        """Score all bullets in one Haiku call. Returns {bullet_id: score}."""

        bullets_for_prompt = []
        for exp, bullets in exp_bullets:
            for b in bullets:
                bullets_for_prompt.append({
                    "id": str(b.id),
                    "experience": exp.company_en,
                    "content": b.content_en or b.raw_text or "",
                    "type": b.type.value if hasattr(b.type, "value") else str(b.type),
                })

        prompt = BULLET_SCORE_USER.format(
            required_skills=", ".join(jd_parsed.get("required_skills", [])),
            key_requirements="; ".join(jd_parsed.get("key_requirements", [])[:5]),
            jd_focus=", ".join(jd_focus) or "general",
            bullets_json=json.dumps(bullets_for_prompt, indent=2, ensure_ascii=False),
        )

        try:
            result = await self.claude.extract_json(
                prompt=prompt, model=Model.HAIKU, system=BULLET_SCORE_SYSTEM,
            )
            scores = {}
            for s in result.get("scores", []):
                scores[s["id"]] = s.get("score", 50)
            return scores
        except Exception as e:
            logger.warning("Claude bullet scoring failed, using fallback: %s", e)
            return self._fallback_bullet_scores(exp_bullets, jd_parsed)

    async def _score_projects_claude(
        self,
        projects: list[dict],
        jd_parsed: dict,
        jd_focus: list[str],
    ) -> list[dict]:
        """Score all projects in one Haiku call. Returns [{name, score, reasoning}]."""

        if not projects:
            return []

        projects_for_prompt = []
        for p in projects:
            tech_names = [t.get("name", "") if isinstance(t, dict) else str(t) for t in p.get("tech_stack", [])]
            bullet_previews = [
                (b.get("content_en") or b.get("content") or "")[:100]
                for b in p.get("bullets", [])[:3]
            ]
            projects_for_prompt.append({
                "name": p.get("name", ""),
                "description": p.get("description", ""),
                "tech_stack": tech_names,
                "bullets": bullet_previews,
            })

        prompt = PROJECT_SCORE_USER.format(
            required_skills=", ".join(jd_parsed.get("required_skills", [])),
            key_requirements="; ".join(jd_parsed.get("key_requirements", [])[:5]),
            jd_focus=", ".join(jd_focus) or "general",
            projects_json=json.dumps(projects_for_prompt, indent=2, ensure_ascii=False),
        )

        try:
            result = await self.claude.extract_json(
                prompt=prompt, model=Model.HAIKU, system=PROJECT_SCORE_SYSTEM,
            )
            return result.get("scores", [])
        except Exception as e:
            logger.warning("Claude project scoring failed: %s", e)
            return []

    # ── Selection logic ──────────────────────────────────────────

    def _select_by_score(
        self,
        exp: Experience,
        bullets: list[Bullet],
        scores: dict[str, int],
    ) -> list[dict]:
        """Select top bullets for an experience based on Claude scores."""

        scored = [(b, scores.get(str(b.id), 50)) for b in bullets]
        # Filter out very low scores
        scored = [(b, s) for b, s in scored if s >= 30]
        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        # Take top N
        selected = scored[:MAX_BULLETS_PER_EXPERIENCE]

        return [
            {
                "bullet_id": str(b.id),
                "type": b.type.value if hasattr(b.type, "value") else str(b.type),
                "raw_text": b.raw_text,
                "content_en": b.content_en,
                "star_data": b.star_data,
                "tech_stack": b.tech_stack,
                "score": score,
            }
            for b, score in selected
        ]

    # ── Fallback scoring ─────────────────────────────────────────

    def _fallback_bullet_scores(
        self,
        exp_bullets: list[tuple[Experience, list[Bullet]]],
        jd_parsed: dict,
    ) -> dict[str, int]:
        """Rule-based fallback if Claude scoring fails."""
        required = set(s.lower() for s in jd_parsed.get("required_skills", []))
        scores: dict[str, int] = {}
        for _, bullets in exp_bullets:
            for b in bullets:
                score = 50  # base
                for tech in b.tech_stack:
                    name = tech.get("name", "") if isinstance(tech, dict) else str(tech)
                    if name.lower() in required:
                        score += 10
                if b.type == BulletType.BUSINESS_IMPACT:
                    score += 5
                scores[str(b.id)] = min(score, 100)
        return scores

    # ── Filters ──────────────────────────────────────────────────

    def _filter_bullets(self, bullets: list[Bullet]) -> list[Bullet]:
        return [
            b for b in bullets
            if b.is_visible
            and not (b.confidence == Confidence.LOW and b.missing)
            and not self._is_low_value(b)
        ]

    @staticmethod
    def _is_low_value(bullet: Bullet) -> bool:
        text = (bullet.content_en or bullet.raw_text or "").lower()
        if len(text) > 150:
            return False
        return any(p in text for p in LOW_VALUE_PATTERNS)

    # ── Integration pool ─────────────────────────────────────────

    async def _build_integration_pool(
        self,
        user_id: str,
        exp_bullets: list[tuple[Experience, list[Bullet]]],
    ) -> dict:
        profile_data = await self.profile_repo.get_full_profile(user_id)

        def _serialize_proj(proj: dict) -> dict:
            return {
                "name": proj.get("name") or "",
                "description": proj.get("description") or "",
                "tech_stack": proj.get("tech_stack", []),
                "bullets": [
                    {
                        "content_en": b.get("content") or b.get("content_en") or "",
                        "type": b.get("type"),
                        "star_data": b.get("star_data", {}),
                        "tech_stack": b.get("tech_stack", []),
                    }
                    for b in proj.get("bullets", [])
                ],
            }

        # Separate linked projects (under visible experiences) from standalone
        experience_extras: dict[str, dict] = {}
        for exp_data in (profile_data.get("experiences", []) if profile_data else []):
            if not exp_data.get("is_visible", True):
                continue  # hidden experience → skip its linked projects too
            linked = exp_data.get("projects", [])
            if linked:
                # Filter out hidden projects within visible experiences
                visible_linked = [p for p in linked if p.get("is_visible", True)]
                if visible_linked:
                    experience_extras[exp_data["id"]] = {
                        "company": exp_data.get("company", ""),
                        "linked_projects": [_serialize_proj(p) for p in visible_linked],
                    }

        # Standalone projects only — filter hidden
        standalone_projects = [
            _serialize_proj(p)
            for p in (profile_data.get("projects", []) if profile_data else [])
            if p.get("is_visible", True)
        ]

        # All experiences with full bullet data
        all_experiences = []
        for exp, bullets in exp_bullets:
            all_experiences.append({
                "experience_id": str(exp.id),
                "company": exp.company_en or "",
                "title": exp.title_en or "",
                "all_bullets": [
                    {
                        "content_en": b.content_en or "",
                        "type": b.type.value if hasattr(b.type, "value") else str(b.type),
                        "star_data": b.star_data or {},
                        "tech_stack": b.tech_stack or [],
                    }
                    for b in bullets
                ],
            })

        return {
            "projects": standalone_projects,  # for Phase 2 project selection
            "experience_extras": experience_extras,  # for Phase 1 enrichment
            "all_experiences": all_experiences,
        }

    def _build_empty_result(self, reason: str) -> dict:
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


step_registry.register("select-bullets", SelectBulletsStep)
