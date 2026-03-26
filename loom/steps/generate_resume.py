"""GenerateResumeStep - generates tailored resume from selected bullets."""

import re
from typing import Any
from uuid import UUID

from loom.core.context import PipelineContext
from loom.core.registry import step_registry
from loom.core.step import Step
from loom.llm import Claude, Model
from loom.storage.profile import Experience
from loom.storage.repository import (
    DataStorage,
    ExperienceRepository,
    InMemoryDataStorage,
    ProfileRepository,
    ResumeRepository,
)
from loom.storage.resume import ResumeArtifact

# System prompt for bullet generation
BULLET_SYSTEM_PROMPT = """You are an expert resume writer creating impactful bullet points.

Writing rules:
1. First bullet MUST show business value with numbers
   Format: [Quantified result] achieved by [technical approach]

2. Create tech ecosystem narrative, not tag lists:
   - Each technology should explain what problem it solved
   - Connect multiple techs with enabling/allowing/to show causality
   - BAD: Used Lambda, S3, and Step Functions
   - GOOD: Orchestrated document processing via Step Functions,
     with Lambda handling parallel parsing and S3 storing outputs

3. Use strong action verbs matching seniority:
   - Architecture: Architected / Designed / Led
   - Implementation: Built / Implemented / Developed
   - Optimization: Reduced / Improved / Accelerated
   - NEVER: Assisted / Participated / Helped

4. Keep bullets concise (1-2 lines) but impactful."""

BULLET_USER_PROMPT = """Generate 3-4 resume bullet points for this experience.

## Experience Context
Company: {company}
Title: {title}
Period: {period}

## Raw Materials (STAR format)
{star_materials}

## Tech Stack
{tech_stack}

## JD Focus Areas
{jd_focus}

## Target Language
{language}

Return JSON only: {{"bullets": ["bullet1", "bullet2", "bullet3"]}}"""

# LaTeX special characters that need escaping
LATEX_SPECIAL_CHARS = {
    '&': r'\&',
    '%': r'\%',
    '$': r'\$',
    '#': r'\#',
    '_': r'\_',
    '{': r'\{',
    '}': r'\}',
    '~': r'\textasciitilde{}',
    '^': r'\textasciicircum{}',
}


class GenerateResumeStep(Step):
    """Generate tailored resume from selected bullets.

    Two-phase generation:
    1. Generate polished bullets for each experience (Claude calls)
    2. Assemble full resume using templates (Python only)

    Input:
        context.data["jd_parsed"]
        context.data["match_result"]
        context.data["selected_bullets"]
        context.data["jd_record_id"]

    Output:
        context.data["resume_artifact_id"] - saved artifact ID
    """

    @property
    def name(self) -> str:
        return "generate-resume"

    def __init__(
        self,
        claude: Claude | None = None,
        storage: DataStorage | None = None,
    ):
        self.claude = claude or Claude()
        self.storage = storage or InMemoryDataStorage()
        self.profile_repo = ProfileRepository(self.storage)
        self.exp_repo = ExperienceRepository(self.storage)
        self.resume_repo = ResumeRepository(self.storage)

    async def run(self, context: PipelineContext) -> PipelineContext:
        selected_bullets = context.data.get("selected_bullets", {})
        jd_parsed = context.data.get("jd_parsed", {})
        match_result = context.data.get("match_result", {})
        language = context.data.get("language", "en")

        # Get profile info
        profile_data = await self.profile_repo.get_full_profile(context.user_id)
        if not profile_data:
            # Generate empty resume with warning
            artifact = await self._create_empty_artifact(
                context, "No profile found"
            )
            new_data = {**context.data, "resume_artifact_id": str(artifact.id)}
            return context.model_copy(update={"data": new_data})

        by_experience = selected_bullets.get("by_experience", {})

        if not by_experience:
            # No bullets selected - generate empty resume
            artifact = await self._create_empty_artifact(
                context, "No bullets selected"
            )
            new_data = {**context.data, "resume_artifact_id": str(artifact.id)}
            return context.model_copy(update={"data": new_data})

        # Get JD focus for bullet generation
        jd_focus = selected_bullets.get("selection_reasoning", {}).get("jd_focus", [])

        # Phase 1: Generate polished bullets for each experience
        exp_ids = [UUID(eid) for eid in by_experience.keys()]
        experiences = await self.exp_repo.get_experiences_by_ids(exp_ids)

        generated_experiences = []
        for exp_id_str, bullets in by_experience.items():
            exp_id = UUID(exp_id_str)
            exp = experiences.get(exp_id)
            if not exp:
                continue

            polished_bullets = await self._generate_bullets_for_experience(
                exp, bullets, jd_focus, language
            )

            generated_experiences.append({
                "experience": exp,
                "bullets": polished_bullets,
            })

        # Phase 2: Assemble resume using templates
        content_md = self._generate_markdown(
            profile_data, generated_experiences, match_result, jd_parsed
        )
        content_tex = self._generate_latex(
            profile_data, generated_experiences, match_result, jd_parsed
        )

        # Save artifact
        jd_record_id = context.data.get("jd_record_id")
        artifact = ResumeArtifact(
            jd_record_id=UUID(jd_record_id) if jd_record_id else UUID(int=0),
            workflow_run_id=UUID(context.workflow_id) if context.workflow_id else None,
            language=language,
            content_md=content_md,
            content_tex=content_tex,
        )
        await self.resume_repo.save_artifact(artifact)

        new_data = {**context.data, "resume_artifact_id": str(artifact.id)}
        return context.model_copy(update={"data": new_data})

    async def _generate_bullets_for_experience(
        self,
        exp: Experience,
        bullets: list[dict],
        jd_focus: list[str],
        language: str,
    ) -> list[str]:
        """Phase 1: Generate polished bullets for one experience."""

        # Format STAR materials
        star_materials = []
        for b in bullets:
            star = b.get("star_data", {})
            material = f"- Type: {b.get('type', 'unknown')}\n"
            material += f"  Raw: {b.get('raw_text', '')}\n"
            if star.get("situation"):
                material += f"  Situation: {star['situation']}\n"
            if star.get("action"):
                material += f"  Action: {star['action']}\n"
            if star.get("result_quantified"):
                material += f"  Result: {star['result_quantified']}\n"
            star_materials.append(material)

        # Format tech stack
        tech_stack_parts = []
        for b in bullets:
            for tech in b.get("tech_stack", []):
                if isinstance(tech, dict):
                    name = tech.get("name", "")
                    role = tech.get("role", "")
                    if name:
                        tech_stack_parts.append(f"{name}" + (f" ({role})" if role else ""))
                else:
                    tech_stack_parts.append(str(tech))
        tech_stack_str = ", ".join(set(tech_stack_parts)) or "Not specified"

        # Format period
        period = ""
        if exp.start_date:
            period = str(exp.start_date)
            if exp.end_date:
                period += f" – {exp.end_date}"
            else:
                period += " – Present"

        prompt = BULLET_USER_PROMPT.format(
            company=exp.company,
            title=exp.title,
            period=period,
            star_materials="\n".join(star_materials),
            tech_stack=tech_stack_str,
            jd_focus=", ".join(jd_focus) if jd_focus else "General",
            language="English" if language == "en" else "Chinese",
        )

        try:
            result = await self.claude.extract_json(
                prompt=prompt,
                model=Model.SONNET,  # Use Sonnet for generation
                system=BULLET_SYSTEM_PROMPT,
            )
            return result.get("bullets", [])
        except Exception:
            # Fallback to raw text if generation fails
            return [b.get("raw_text", "") for b in bullets]

    def _generate_markdown(
        self,
        profile: dict,
        experiences: list[dict],
        match_result: dict,
        jd_parsed: dict,
    ) -> str:
        """Phase 2a: Generate Markdown resume."""
        p = profile["profile"]

        # Header
        lines = [
            f"# {p['name']}",
            "",
        ]

        # Contact info
        contact_parts = []
        if p.get("email"):
            contact_parts.append(p["email"])
        if p.get("phone"):
            contact_parts.append(p["phone"])
        if p.get("location"):
            contact_parts.append(p["location"])
        if contact_parts:
            lines.append(" | ".join(contact_parts))
            lines.append("")

        # Summary if exists
        if p.get("summary"):
            lines.append("## Summary")
            lines.append("")
            lines.append(p["summary"])
            lines.append("")

        # Experience
        lines.append("## Experience")
        lines.append("")

        for exp_data in experiences:
            exp = exp_data["experience"]
            bullets = exp_data["bullets"]

            period = ""
            if exp.start_date:
                period = str(exp.start_date)
                if exp.end_date:
                    period += f" – {exp.end_date}"
                else:
                    period += " – Present"

            lines.append(f"### {exp.title} — {exp.company}")
            if period:
                lines.append(f"*{period}*")
            lines.append("")

            for bullet in bullets:
                lines.append(f"- {bullet}")
            lines.append("")

        # Skills section
        skills_covered = match_result.get("matched", [])
        if skills_covered:
            lines.append("## Skills")
            lines.append("")
            skill_names = [s.get("requirement", s) if isinstance(s, dict) else s for s in skills_covered]
            lines.append(", ".join(skill_names))
            lines.append("")

        return "\n".join(lines)

    def _generate_latex(
        self,
        profile: dict,
        experiences: list[dict],
        match_result: dict,
        jd_parsed: dict,
    ) -> str:
        """Phase 2b: Generate LaTeX resume."""
        p = profile["profile"]

        # Escape special characters
        def escape(text: str) -> str:
            if not text:
                return ""
            for char, replacement in LATEX_SPECIAL_CHARS.items():
                text = text.replace(char, replacement)
            return text

        lines = [
            r"\documentclass[11pt,a4paper]{article}",
            r"\usepackage[margin=0.75in]{geometry}",
            r"\usepackage{enumitem}",
            r"\usepackage{titlesec}",
            r"\usepackage{hyperref}",
            r"\setlist[itemize]{nosep,left=0pt}",
            r"\titleformat{\section}{\large\bfseries}{}{0em}{}[\titlerule]",
            r"\titleformat{\subsection}{\bfseries}{}{0em}{}",
            r"\pagestyle{empty}",
            r"\begin{document}",
            "",
            r"\begin{center}",
            rf"\textbf{{\Large {escape(p['name'])}}}\\[0.3em]",
        ]

        # Contact info
        contact_parts = []
        if p.get("email"):
            contact_parts.append(escape(p["email"]))
        if p.get("phone"):
            contact_parts.append(escape(p["phone"]))
        if p.get("location"):
            contact_parts.append(escape(p["location"]))
        if contact_parts:
            lines.append(" $|$ ".join(contact_parts))

        lines.extend([
            r"\end{center}",
            "",
        ])

        # Experience section
        lines.append(r"\section*{Experience}")
        lines.append("")

        for exp_data in experiences:
            exp = exp_data["experience"]
            bullets = exp_data["bullets"]

            period = ""
            if exp.start_date:
                period = str(exp.start_date)
                if exp.end_date:
                    period += f" -- {exp.end_date}"
                else:
                    period += " -- Present"

            lines.append(rf"\subsection*{{{escape(exp.title)} --- {escape(exp.company)}}}")
            if period:
                lines.append(rf"\textit{{{period}}}")
            lines.append("")
            lines.append(r"\begin{itemize}")
            for bullet in bullets:
                lines.append(rf"  \item {escape(bullet)}")
            lines.append(r"\end{itemize}")
            lines.append("")

        # Skills section
        skills_covered = match_result.get("matched", [])
        if skills_covered:
            lines.append(r"\section*{Skills}")
            skill_names = [s.get("requirement", s) if isinstance(s, dict) else s for s in skills_covered]
            lines.append(escape(", ".join(skill_names)))
            lines.append("")

        lines.append(r"\end{document}")

        return "\n".join(lines)

    async def _create_empty_artifact(
        self,
        context: PipelineContext,
        reason: str,
    ) -> ResumeArtifact:
        """Create an empty artifact with warning."""
        jd_record_id = context.data.get("jd_record_id")
        artifact = ResumeArtifact(
            jd_record_id=UUID(jd_record_id) if jd_record_id else UUID(int=0),
            language=context.data.get("language", "en"),
            content_md=f"# Resume\n\n*Warning: {reason}*\n",
            content_tex=rf"\documentclass{{article}}\begin{{document}}Warning: {reason}\end{{document}}",
        )
        await self.resume_repo.save_artifact(artifact)
        return artifact


# Register step
step_registry.register("generate-resume", GenerateResumeStep)
