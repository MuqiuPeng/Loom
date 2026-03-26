"""MatchProfileStep - semantic matching between profile and JD."""

import json
from typing import Any
from uuid import UUID

from loom.core.context import PipelineContext
from loom.core.pipeline import StepError
from loom.core.registry import step_registry
from loom.core.step import Step
from loom.llm import Claude, Model
from loom.storage.repository import (
    DataStorage,
    InMemoryDataStorage,
    JDRepository,
    ProfileRepository,
)

MATCH_SYSTEM_PROMPT = """You are a senior recruiter evaluating candidate-job fit.
Analyze the candidate's complete experience to determine match with the job requirements.
Be thorough: look for evidence in work experience, not just skill labels."""

MATCH_USER_PROMPT = """## Candidate Profile

### Basic Info
{profile_info}

### Skills
{skills_info}

### Work Experience
{experience_info}

### Projects
{projects_info}

---

## Job Requirements

### Required Skills (hard skills)
{required_skills}

### Preferred Skills
{preferred_skills}

### Key Requirements
{key_requirements}

### Soft Requirements
{soft_requirements}

---

## Matching Rules

1. Semantic equivalence counts as match:
   "Python experience" = "Python" = "Python programming"

2. Experience can prove skills:
   Data analysis work experience → satisfies "statistical analysis skills"

3. soft_requirements should be listed separately, NOT in hard_skill_gaps

4. partially_matched: requirements with related but incomplete evidence

5. Score (1-10) based on hard skills match ONLY:
   - 8-10: 90%+ of required_skills matched
   - 6-7: 70%+ of required_skills matched
   - 4-5: 50%+ of required_skills matched
   - 1-3: below 50% of required_skills matched

---

Return a JSON object with this exact structure:
{{
  "matched": [
    {{"requirement": "skill name", "evidence": "specific evidence from experience"}}
  ],
  "hard_skill_gaps": ["skill1", "skill2"],
  "soft_requirements": ["communication", "teamwork"],
  "partially_matched": [
    {{"requirement": "requirement", "evidence": "partial evidence"}}
  ],
  "score": 7,
  "reasoning": "brief explanation of the score"
}}

Return ONLY the JSON, no markdown code blocks, no explanation."""


class MatchProfileStep(Step):
    """Match candidate profile against job description.

    Input:
        context.data["jd_parsed"] - structured JD from ParseJDStep
        context.data["jd_record_id"] - optional JDRecord id to update

    Output:
        context.data["match_result"] - matching results dict
    """

    @property
    def name(self) -> str:
        return "match-profile"

    def __init__(
        self,
        claude: Claude | None = None,
        storage: DataStorage | None = None,
    ):
        self.claude = claude or Claude()
        self.storage = storage or InMemoryDataStorage()
        self.profile_repo = ProfileRepository(self.storage)
        self.jd_repo = JDRepository(self.storage)

    async def run(self, context: PipelineContext) -> PipelineContext:
        # Get parsed JD
        jd_parsed = context.data.get("jd_parsed")
        if not jd_parsed:
            raise StepError(self.name, "context.data['jd_parsed'] is required")

        # Get full profile
        profile_data = await self.profile_repo.get_full_profile(context.user_id)
        if not profile_data:
            raise StepError(
                self.name,
                "No profile found. Please complete your profile first."
            )

        # Build prompt
        prompt = self._build_prompt(profile_data, jd_parsed)

        # Call Claude for matching
        try:
            match_result = await self.claude.extract_json(
                prompt=prompt,
                model=Model.HAIKU,
                system=MATCH_SYSTEM_PROMPT,
            )
        except ValueError as e:
            raise StepError(self.name, f"Failed to parse match result: {e}")

        # Validate result
        if "score" not in match_result:
            raise StepError(self.name, "Match result missing 'score' field")

        # Update JDRecord if id provided
        jd_record_id = context.data.get("jd_record_id")
        if jd_record_id:
            await self.jd_repo.update_match_score(
                UUID(jd_record_id) if isinstance(jd_record_id, str) else jd_record_id,
                match_result["score"],
            )

        # Write result to context
        new_data = {**context.data, "match_result": match_result}
        return context.model_copy(update={"data": new_data})

    def _build_prompt(
        self,
        profile: dict[str, Any],
        jd: dict[str, Any],
    ) -> str:
        """Build the matching prompt from profile and JD data."""

        # Format profile info
        p = profile["profile"]
        profile_info = f"Name: {p['name']}\n"
        if p.get("summary"):
            profile_info += f"Summary: {p['summary']}\n"

        # Format skills
        skills_info = "\n".join([
            f"- {s['name']} ({s['level']})"
            + (f": {s['context']}" if s.get('context') else "")
            for s in profile.get("skills", [])
        ]) or "No skills listed"

        # Format experiences with bullets
        experience_parts = []
        for exp in profile.get("experiences", []):
            exp_text = f"**{exp['title']}** at {exp['company']}"
            if exp.get("start_date"):
                exp_text += f" ({exp['start_date']} - {exp.get('end_date', 'present')})"
            exp_text += "\n"

            for bullet in exp.get("bullets", []):
                exp_text += f"  • {bullet['raw_text']}\n"
                if bullet.get("star_data"):
                    star = bullet["star_data"]
                    if star.get("result_quantified"):
                        exp_text += f"    Result: {star['result_quantified']}\n"

            experience_parts.append(exp_text)

        experience_info = "\n".join(experience_parts) or "No experience listed"

        # Format projects
        project_parts = []
        for proj in profile.get("projects", []):
            proj_text = f"**{proj['name']}**"
            if proj.get("role"):
                proj_text += f" ({proj['role']})"
            proj_text += "\n"
            if proj.get("description"):
                proj_text += f"  {proj['description']}\n"
            if proj.get("tech_stack"):
                tech = ", ".join([t.get("name", str(t)) for t in proj["tech_stack"]])
                proj_text += f"  Tech: {tech}\n"
            project_parts.append(proj_text)

        projects_info = "\n".join(project_parts) or "No projects listed"

        # Format JD requirements
        required_skills = ", ".join(jd.get("required_skills", [])) or "None specified"
        preferred_skills = ", ".join(jd.get("preferred_skills", [])) or "None specified"
        key_requirements = "\n".join([
            f"- {r}" for r in jd.get("key_requirements", [])
        ]) or "None specified"
        soft_requirements = ", ".join(jd.get("soft_requirements", [])) or "None specified"

        return MATCH_USER_PROMPT.format(
            profile_info=profile_info,
            skills_info=skills_info,
            experience_info=experience_info,
            projects_info=projects_info,
            required_skills=required_skills,
            preferred_skills=preferred_skills,
            key_requirements=key_requirements,
            soft_requirements=soft_requirements,
        )


# Register step
step_registry.register("match-profile", MatchProfileStep)
