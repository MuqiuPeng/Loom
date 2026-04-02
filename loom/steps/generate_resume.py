"""GenerateResumeStep - 4-phase resume generation pipeline.

Phase 1: Per-experience bullet generation (Haiku, isolated)
Phase 2: Per-project bullet generation (Haiku, isolated)
Phase 3: Integration review (Sonnet, sees all)
Phase 4: One-page enforcement (Python, no Claude)
"""

import logging
import re
from pathlib import Path
from typing import Any
from uuid import UUID

from jinja2 import Environment

from loom.core.context import PipelineContext
from loom.core.registry import step_registry
from loom.core.step import Step
from loom.llm import Claude, Model
from loom.storage.profile import Experience
from loom.storage.repository import (
    BulletRepository,
    DataStorage,
    ExperienceRepository,
    InMemoryDataStorage,
    ProfileRepository,
    ResumeRepository,
)
from loom.storage.resume import ResumeArtifact

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# ── Phase 1 prompts: per-experience bullet generation ────────────────

BULLET_PATTERNS = """
## Professional bullet sentence patterns

### business_impact (first bullet)
Pattern: "[Verb] [user group] to [outcome] by building [system] that [capability]"
Examples:
- "Enabled retail investors with no coding background to design and backtest custom trading strategies — built Python indicator pipeline computing 60+ technical indicators on 5 years of OHLC data"
- "Reduced procurement intelligence bottleneck for regional agencies across China — built automated pipeline collecting and normalizing 20,000+ government bidding records into queryable format"

### technical_design
Pattern: "Designed [component] using [approach], enabling [technical outcome]"
Examples:
- "Designed dependency-aware computation pipeline where each indicator declares its inputs — enabling automatic topological execution ordering and selective cache reuse"
- "Architected serverless crawling infrastructure using AWS Lambda for parallel extraction and Step Functions for orchestration — decoupling ingestion rate from infrastructure scaling"

### implementation
Pattern: "Built [component] in [technology] that [behavior], enabling [capability]"
Examples:
- "Built Node.js validation pipeline normalizing heterogeneous procurement data — standardizing bidding amounts, dates, and location hierarchies from 30+ provincial sources"
- "Built containerized deployment pipeline with GitHub Actions, ECS, and CloudFront — enabling zero-downtime releases through blue-green container replacement"

### scale
Pattern: "[System] processes [scale metric], [outcome]"
Examples:
- "Indicator pipeline processes 5 years of daily OHLC data across 3 markets in under 2 seconds per indicator — enabling real-time strategy iteration"

### problem_solving
Pattern: "Resolved [challenge] by [approach] — [outcome]"
Examples:
- "Resolved time-series alignment inconsistency by enforcing canonical timeline on all computation outputs — eliminating visualization desynchronization"

### research (academic projects)
First bullet: "Investigated [research question] by [methodology] — [key finding]"
Subsequent: "[Built/Designed] [component] to [enable measurement], [result]"
Examples:
- "Investigated whether embedding PDE constraints into neural network loss functions improves accuracy over data-only approaches — validated against analytical solutions"
- "Designed end-to-end ECG digitization pipeline to enable clinicians to convert paper records into structured diagnostic data"

## Application rules
1. Never start two bullets in same section with same verb
2. Preferred verbs: business_impact=Enabled/Empowered/Reduced, technical_design=Designed/Architected, implementation=Built/Implemented, research=Investigated/Validated
3. Avoid: "Worked on", "Helped with", "Responsible for", two consecutive "Built", generic closers without numbers
"""

PHASE1_SYSTEM = """\
You are writing resume bullets for ONE specific work experience.
Use ONLY the provided star_data and tech_stack for this role.

## Strict boundary rule
Only reference technologies and achievements that appear in the provided
bullets_material for THIS role. Do NOT invent, infer, or import skills
from elsewhere. If a technology is not in this role's tech_stack, do not
mention it — even if it seems relevant to the JD.

## Business Context Reliability
The situation field in star_data may be inferred rather than stated by the
candidate. Treat result_quantified/result_qualitative as ground truth.
If situation seems generic, use the action and result to reconstruct
business value bottom-up.

## First bullet rule (mandatory)
The FIRST bullet MUST follow this structure:
"[What was built/done] enabling [specific user group] to [achieve specific \
outcome] — [key technical means]"
Example: "Built quantitative platform enabling retail investors with no \
coding background to design and backtest trading strategies across 5 markets"
If star_data lacks clear user info, frame it as: who benefits + what problem \
it solves. Do not skip this — the first bullet sets the narrative.

## First bullet completeness check
The first bullet MUST contain BOTH halves:
Half 1 (WHO+WHAT): "[User group] to [specific outcome]"
Half 2 (HOW): "— [key technical means, 1-2 technologies max]"
INCOMPLETE: "Enabled 10-person team to explore strategies across 5 years of data"
COMPLETE: "Enabled 10-person team to explore strategies across 5 years of data \
— built Python indicator pipeline computing 60+ indicators with dependency-aware ordering"
If Half 2 is missing, add key technical means after a dash.

## Content to NEVER Include
- Basic version control (Git workflow, branch strategy, code review)
- Standard responsive design (CSS, mobile/desktop compatibility)
- Generic collaboration ("worked with cross-functional teams") without
  engineering decisions
- Tool familiarity without depth ("familiar with X")
- Process compliance ("followed Agile", "used Jira", "daily standups")
- Standard dev workflow ("set up CI/CD", "wrote unit tests") unless there
  is genuine complexity

If the only material for a bullet falls into the above, skip it.
Fewer strong bullets beat more weak ones.

## Writing rules

### Business value first
First bullet MUST open with user/business impact, not technology.

### One deep concept per bullet
Do not stack multiple advanced concepts. Choose one, go deep.

### Numbers must earn their place
Only include numbers reflecting real engineering challenge or business impact.

### Tech stack must form an ecosystem narrative, not a tag list

### Verb hierarchy
Architected / Designed -> system-level decisions
Built / Implemented / Developed -> execution
Reduced / Improved / Accelerated -> outcomes
Never: Assisted / Participated / Helped / Contributed to

### 2-minute rule
Every bullet must be explainable for 2+ minutes in an interview.
If not, simplify the claim.

## Bullet length constraint
Each bullet: 120-140 characters maximum (1-2 printed lines).
Structure: [One clear achievement or decision] — [key technical means, max 2-3 technologies]
One idea per bullet. One dash maximum.
If a bullet has more than one dash or more than two commas, it is too long — split it.

## Bullet count rules
Minimum bullets per experience:
- Most recent role: 3-4 bullets
- All other roles: 3 bullets (no exceptions)

If source material only supports 2 strong bullets, generate a third from a
DIFFERENT angle: problem_solving (hardest technical challenge), scale (data
volume, user count, performance), or collaboration (cross-functional impact).

## Deduplication check
Before finalizing, scan your bullets for this role:
- Same technology as main subject in two bullets → merge or reframe one
- Same outcome described differently → keep the stronger, replace the other
Never repeat the same achievement. Each bullet must cover a distinct aspect.

## Output
Return ONLY valid JSON:
{
  "bullets": [
    {
      "content": "bullet text in PLAIN TEXT — no Markdown, no LaTeX",
      "type": "business_impact|technical_design|implementation|scale|collaboration|problem_solving",
      "source_material": "brief note on which star_data this came from"
    }
  ]
}

CRITICAL: bullet content must be PLAIN TEXT. No **, *, `, ---. No LaTeX.
""" + BULLET_PATTERNS

PHASE1_USER = """\
Write 2-{max_bullets} resume bullets for this experience, targeting the JD.
Use more if strong content exists, fewer if thin. Never pad.

== TARGET JOB ==
Title: {jd_title}
Company: {jd_company}
Required Skills: {jd_required}
Key Requirements: {jd_key_requirements}
Focus Areas: {jd_focus}

== THIS EXPERIENCE ==
Company: {company}
Title: {title}
Period: {period}

== SOURCE MATERIALS (use as raw facts, do NOT copy content_en) ==
{bullets_material}

== TECH STACK FOR THIS ROLE ==
{tech_stack}

== LANGUAGE ==
{language}

Return JSON only."""

# ── Phase 2 prompts: per-project bullet generation ───────────────────

PHASE2_SYSTEM = """\
You are writing resume bullets for ONE specific personal/side project.
Use ONLY the provided project data.

## First bullet rule (mandatory)
For academic/research projects, the first bullet MUST state the research \
question or problem: "[Research question or problem], demonstrated by \
[approach] and [what was validated/achieved]"
For other projects: "[What was built] enabling [user group] to [outcome]"
Do NOT start with implementation details — start with what problem it solves.

## Rules
- First bullet: business value, user impact, or research problem
- Second bullet: most technically distinctive aspect
- Max 2 bullets
- PLAIN TEXT only. No Markdown, no LaTeX.
- Only reference technologies in this project's tech_stack.

## 2-minute rule applies.

## Bullet length: 120-140 chars max. One idea per bullet. One dash maximum.

## Output
Return ONLY valid JSON:
{
  "bullets": [
    {"content": "...", "type": "business_impact|technical_design|..."}
  ]
}
""" + BULLET_PATTERNS

PHASE2_USER = """\
Write 1-2 resume bullets for this project, targeting the JD.

== TARGET JOB ==
Required Skills: {jd_required}
Focus Areas: {jd_focus}

== PROJECT ==
Name: {name}
Description: {description}
Tech Stack: {tech_stack}

== SOURCE MATERIALS ==
{bullets_material}

== LANGUAGE ==
{language}

Return JSON only."""

# ── Phase 3 prompts: integration review ──────────────────────────────

PHASE3_SYSTEM = """\
You are reviewing a complete resume draft against the candidate's real STAR
source material. Your job is to fact-check, fix distortions, remove redundancy,
and fill critical gaps.

## Review checklist (check in order):

1. FACT-CHECK AGAINST SOURCE MATERIAL
   For each generated bullet, compare it against the source_material star_data
   for that company/project. Ask: "Does this bullet faithfully represent what
   the candidate actually did and achieved?"

   Common distortions to catch:
   - Business value described doesn't match actual users or outcomes in star_data
   - Technical complexity overstated or understated
   - Achievement attributed to wrong scope (candidate vs team)
   - Technology mentioned that doesn't appear in that role's tech_stack

   If a bullet misrepresents the source material:
   -> Rewrite based on star_data facts
   -> Note the correction in review_notes

2. COMPLETENESS CHECK
   Is the most important fact from each role's star_data (usually
   result_quantified or the core user value) present in the bullets?
   If not, add it to the most relevant bullet for that role.

3. REDUNDANCY CHECK
   Identify bullets across all sections that express the same capability.
   Action: Keep the strongest one, mark others for removal.

   HARD CONSTRAINT: Never reduce any experience below 2 bullets.
   The most recent experience must keep at least 3 bullets.
   If removing a "redundant" bullet would violate this, keep it.

4. JD COVERAGE CHECK
   Check if required_skills are covered by existing bullets.
   For each uncovered required skill:
   - If a bullet could be lightly adjusted to demonstrate it — suggest the edit
   - If not — leave the gap, do NOT invent content

5. FLOW CHECK
   Does the resume tell a coherent story about the candidate's progression?
   Minor wording adjustments only — no full rewrites.

## Output
Return ONLY valid JSON:
{
  "approved": {
    "experiences": {
      "Company Name": ["bullet1", "bullet2", ...],
      ...
    },
    "projects": {
      "Project Name": ["bullet1", "bullet2"],
      ...
    }
  },
  "removed": [
    {"section": "...", "bullet": "...", "reason": "..."}
  ],
  "corrections": [
    {"section": "...", "original": "...", "corrected": "...", "reason": "..."}
  ],
  "review_notes": "brief summary of changes made"
}

CRITICAL: All bullet text must be PLAIN TEXT. No Markdown, no LaTeX."""

PHASE3_USER = """\
Review this resume draft against the source material and apply the checklist.

== ALL GENERATED BULLETS ==
{all_bullets_json}

== SOURCE MATERIAL (ground truth — use to fact-check bullets) ==
{source_material_json}

== CANDIDATE SKILLS (full tech stack across all roles) ==
{candidate_tech_stack}

== JD REQUIREMENTS ==
Required Skills: {jd_required}
Skill Gaps (not yet covered): {hard_skill_gaps}
Key Requirements: {jd_key_requirements}

Return JSON only."""

# ── Phase 3b prompts: scrutiny + rewrite ─────────────────────────────

SCRUTINY_SYSTEM = """\
You are a senior technical recruiter with 10 years experience at top-tier \
tech companies. You are reviewing resume bullets with a critical eye.

For each bullet, answer three questions:

1. CREDIBILITY: If asked to elaborate in an interview, could the candidate \
defend this for 2+ minutes with specific technical details?
Red flags: vague claims ("built scalable system"), advanced terms without \
mechanism ("optimized performance" — how?), tech listed without purpose.

2. SPECIFICITY: Could this bullet describe ANY engineer, or does it describe \
THIS candidate specifically?
Generic fails: "Designed REST API for data processing"
Specific passes: "Built FastAPI service processing 60+ indicator calculations \
against 5 years of OHLC data with sub-second response"

3. IMPACT: Is there a clear connection between technical work and a \
business/user outcome?
Tech without impact fails: "Designed FastAPI REST service layer"
Tech with impact passes: "Designed FastAPI service enabling 10 non-technical \
traders to run custom indicator calculations without code"

4. HALLUCINATION CHECK: Any specific metric, percentage, multiplier, or \
time-based claim MUST be traceable to the source star_data provided. \
Flag as hallucinated if: specific percentage not in star_data (e.g. "75%"), \
specific multiplier (e.g. "2x faster"), specific time duration (e.g. "from \
8 hours to 2 hours"), specific count not in star_data (e.g. "50+ engineers"). \
Do NOT flag: numbers that appear verbatim in star_data, numbers from JD, \
ranges matching star_data (e.g. "60+ indicators" if star_data says same), \
qualitative improvements without numbers (e.g. "reduced manual overhead"). \
Fabricated numbers are worse than vague language — always severity=high.

5. DUPLICATE CHECK (semantic level): Two bullets in the SAME section are \
duplicates if they describe the same work artifact OR the same user outcome, \
even if wording differs. Same primary technology doing the same job → duplicate.

6. CONTENT OVERLAP CHECK: Two bullets overlap if bullet B describes something \
already fully covered by bullet A, even with different words. Example: \
A: "Built Python indicator pipeline processing 5 years of OHLC data with 60+ indicators" \
B: "Developed Python indicator computation pipeline processing 5 years of daily OHLC data integrating 60+ technical indicators" \
→ B is fully covered by A → severity=high. The weaker bullet must be replaced \
with a genuinely DIFFERENT aspect of the work (different artifact, different outcome).

7. FIRST BULLET COMPLETENESS: The first bullet of each section must contain \
BOTH user/problem context AND technical means (after a dash). If either half \
is missing → severity=high.

Severity: high = fails 2+ questions OR hallucination=fail OR duplicate/overlap \
OR incomplete first bullet, \
medium = fails exactly 1 question (no hallucination), low = minor wording.

Return ONLY valid JSON:
{
  "issues": [
    {
      "section": "Company Name",
      "bullet_index": 0,
      "original": "the bullet text",
      "credibility": "pass|fail",
      "specificity": "pass|fail",
      "impact": "pass|fail",
      "hallucination": "pass|fail",
      "hallucinated_claim": "the specific number if hallucination=fail, else null",
      "severity": "high|medium|low",
      "critique": "one sentence explaining the problem"
    }
  ],
  "pass_count": 10,
  "fail_count": 2,
  "round": 1
}"""

SCRUTINY_USER = """\
Review these resume bullets. Round {round}.

== BULLETS ==
{bullets_json}

== SOURCE MATERIAL (ground truth) ==
{source_material_json}

Return JSON only."""

REWRITE_SYSTEM = """\
You are rewriting a resume bullet that failed quality review. Fix ONLY \
the specific issues identified by the reviewer. Keep content accurate \
to the source material. Max 140 characters. PLAIN TEXT only. \
The bullet MUST be a complete sentence — never end mid-phrase.

CRITICAL: Do NOT rewrite this bullet to cover the same topic as the \
other bullets listed below. Each bullet must be about a DIFFERENT aspect.

If a hallucinated metric is flagged: you MUST remove it. Options in order: \
1) Replace with a verified number from star_data, 2) Replace with qualitative \
description (e.g. "75% faster" → "significantly reduced"), 3) Restructure \
to not need a number. Do NOT invent a replacement number.

Return ONLY valid JSON:
{"rewritten": "new bullet text", "changes_made": "brief note on what changed"}"""

REWRITE_USER = """\
Rewrite this bullet to fix the critique.

Original: {original}
Critique: {critique}
Severity: {severity}
Type: {bullet_type}
{hallucination_note}
Other bullets in this section (do NOT duplicate these):
{other_bullets}

Source STAR data:
{star_data_json}

Return JSON only."""

MAX_SCRUTINY_ROUNDS = 5

# ── LaTeX helpers ────────────────────────────────────────────────────

_LATEX_SPECIAL = [
    ('&', r'\&'), ('%', r'\%'), ('$', r'\$'),
    ('#', r'\#'), ('_', r'\_'), ('~', r'\~{}'), ('^', r'\^{}'),
]


def _escape_special(text: str) -> str:
    for char, repl in _LATEX_SPECIAL:
        text = text.replace(char, repl)
    return text


def md_to_latex(text: str) -> str:
    if not text:
        return ""
    text = _escape_special(text)
    text = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', text)
    text = re.sub(r'\*(.+?)\*', r'\\textit{\1}', text)
    text = re.sub(r'`(.+?)`', r'\\texttt{\1}', text)
    return text


def apply_latex_emphasis(text: str, bold_terms: list[str], italic_terms: list[str]) -> str:
    """Apply \\textbf{} for tech terms and \\textit{} for proper nouns.

    Terms are already sorted by length descending (longer first).
    """
    # Phase 1: italics (company names)
    for term in italic_terms:
        escaped = _escape_special(term)
        pattern = r'(?<!\\textbf\{)(?<!\\textit\{)' + re.escape(escaped) + r'(?!\})'
        replacement = r'\\textit{' + escaped + '}'
        text = re.sub(pattern, replacement, text)

    # Phase 2: bold (tech terms)
    for term in bold_terms:
        escaped = _escape_special(term)
        pattern = r'(?<!\\textbf\{)(?<!\\textit\{)(?<!\{)' + re.escape(escaped) + r'(?!\})'
        replacement = r'\\textbf{' + escaped + '}'
        text = re.sub(pattern, replacement, text)

    return text


def make_latex_processor(profile_data: dict):
    """Create a latex filter function with dynamic terms from profile data."""
    from loom.prompts.emphasis_terms import get_bold_terms, get_italic_terms

    bold = get_bold_terms(profile_data)
    italic = get_italic_terms(profile_data)

    def process(text: str) -> str:
        text = md_to_latex(text)
        text = apply_latex_emphasis(text, bold, italic)
        return text

    return process


# ── Date formatting ──────────────────────────────────────────────────

DEGREE_ABBREV = {
    "Master of Computer Science": ("M.S.", "Computer Science"),
    "Master of Science": ("M.S.", ""),
    "Master of Arts": ("M.A.", ""),
    "Master of Engineering": ("M.Eng.", ""),
    "Bachelor of Applied Mathematics": ("B.S.", "Applied Mathematics"),
    "Bachelor of Science": ("B.S.", ""),
    "Bachelor of Arts": ("B.A.", ""),
    "Bachelor of Engineering": ("B.Eng.", ""),
    "Doctor of Philosophy": ("Ph.D.", ""),
}


def _format_degree(degree: str) -> tuple[str, str]:
    """Convert full degree to (abbreviation, subject).

    Returns e.g. ("M.S.", "Computer Science") for "Master of Computer Science".
    """
    for full, (abbrev, subject) in DEGREE_ABBREV.items():
        if degree.startswith(full):
            return abbrev, subject
    return degree, ""


def _format_date(date_str: str | None) -> str:
    if not date_str:
        return ""
    parts = date_str.split("-")
    return f"{parts[1]}/{parts[0]}" if len(parts) >= 2 else date_str


def _format_period(start: str | None, end: str | None) -> str:
    s = _format_date(start)
    if not s:
        return ""
    e = _format_date(end)
    return f"{s} -- {e}" if e else f"{s} -- Present"


# ── Line estimation ──────────────────────────────────────────────────

MAX_ONE_PAGE_LINES = 90  # allow 1 to 1.5 pages
MIN_BULLETS_MOST_RECENT = 3
MIN_BULLETS_OTHER = 3


def estimate_lines(sections: dict) -> int:
    lines = 3.0
    lines += 2 + len(sections.get("skills", [])) * 1.5
    lines += 2 + len(sections.get("education", [])) * 1.5
    for exp in sections.get("experiences", []):
        lines += 2.5
        for b in exp.get("bullets", []):
            char_len = len(b) if isinstance(b, str) else 100
            lines += max(1.5, char_len / 55)
    if sections.get("projects"):
        lines += 2
        for proj in sections["projects"]:
            lines += 2
            for b in proj.get("bullets", []):
                char_len = len(b) if isinstance(b, str) else 100
                lines += max(1.5, char_len / 55)
    return int(lines)


# ── Step ─────────────────────────────────────────────────────────────


class GenerateResumeStep(Step):
    """4-phase resume generation: generate -> project -> review -> enforce."""

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
        self.bullet_repo = BulletRepository(self.storage)
        self.resume_repo = ResumeRepository(self.storage)
        self.claude.set_storage(self.storage)

        self._tex_source = (PROMPTS_DIR / "resume_template.tex").read_text(encoding="utf-8")
        self._md_template = Environment().from_string(
            (PROMPTS_DIR / "resume_template.md").read_text(encoding="utf-8")
        )

    async def run(self, context: PipelineContext) -> PipelineContext:
        selected_bullets = context.data.get("selected_bullets", {})
        jd_parsed = context.data.get("jd_parsed", {})
        match_result = context.data.get("match_result", {})
        integration_pool = context.data.get("integration_pool", {})
        language = context.data.get("language", "en")

        self.claude.set_context(
            workflow_run_id=context.workflow_id,
            step_name=self.name,
            user_id=context.user_id,
        )

        profile_data = await self.profile_repo.get_full_profile(context.user_id)
        if not profile_data:
            artifact = await self._create_empty_artifact(context, "No profile found")
            new_data = {**context.data, "resume_artifact_id": str(artifact.id)}
            return context.model_copy(update={"data": new_data})

        by_experience = selected_bullets.get("by_experience", {})
        if not by_experience:
            artifact = await self._create_empty_artifact(context, "No bullets selected")
            new_data = {**context.data, "resume_artifact_id": str(artifact.id)}
            return context.model_copy(update={"data": new_data})

        jd_focus = selected_bullets.get("selection_reasoning", {}).get("jd_focus", [])
        jd_req = {
            "required_skills": jd_parsed.get("required_skills", []),
            "preferred_skills": jd_parsed.get("preferred_skills", []),
            "key_requirements": jd_parsed.get("key_requirements", []),
            "jd_focus": jd_focus,
        }

        # Sort experiences by date, take max 3
        all_exp_bullets = await self.bullet_repo.get_all_bullets_for_user(context.user_id)
        exp_order = [exp.id for exp, _ in all_exp_bullets]
        exp_ids = [UUID(eid) for eid in by_experience.keys()]
        experiences = await self.exp_repo.get_experiences_by_ids(exp_ids)
        sorted_exp_ids = sorted(
            exp_ids,
            key=lambda eid: exp_order.index(eid) if eid in exp_order else 999,
        )  # include all selected experiences; Phase 4 trims if needed

        # ── Phase 1: Per-experience bullet generation ────────────

        phase1_results: dict[str, list[str]] = {}
        phase1_exp_data: list[dict] = []

        for i, exp_id in enumerate(sorted_exp_ids):
            exp = experiences.get(exp_id)
            if not exp:
                continue

            exp_id_str = str(exp_id)
            selected = by_experience.get(exp_id_str, [])
            is_most_recent = (i == 0)
            max_bullets = 4 if is_most_recent else 3

            # Get linked project material for this experience
            exp_extras = integration_pool.get("experience_extras", {}).get(exp_id_str, {})

            bullets = await self._phase1_experience(
                exp, selected, jd_parsed, jd_req, max_bullets, language,
                linked_projects=exp_extras.get("linked_projects", []),
            )

            company = exp.company_en or "Unknown"
            phase1_results[company] = bullets
            phase1_exp_data.append({"experience": exp, "bullets": bullets})

        try:
            from loom.services.logger import logger as _lg
            total_p1 = sum(len(b) for b in phase1_results.values())
            await _lg.info("workflow", "step.generate.phase1",
                f"Phase 1 done: {total_p1} bullets for {len(phase1_results)} experiences",
                step_name=self.name,
                per_company={k: len(v) for k, v in phase1_results.items()})
        except Exception:
            pass

        # ── Phase 2: Per-project bullet generation ───────────────

        bullet_text = " ".join(
            b for bs in phase1_results.values() for b in bs
        ).lower()

        # Use Claude project scores from SelectBulletsStep
        claude_project_scores = integration_pool.get("project_scores", [])
        top_projects = self._select_projects_by_score(
            integration_pool.get("projects", []),
            claude_project_scores,
        )

        try:
            from loom.services.logger import logger as _lg
            selected_names = [p["name"] for p in top_projects]
            await _lg.info("workflow", "step.generate.phase2.selection",
                f"Project selection: {len(selected_names)} selected from {len(claude_project_scores)} scored",
                step_name=self.name,
                all_projects_scored=claude_project_scores,
                selected=selected_names,
                rejected=[s for s in claude_project_scores if s.get("name") not in selected_names])
        except Exception:
            pass

        phase2_results: dict[str, list[str]] = {}
        for proj_data in top_projects:
            proj_name = proj_data["name"]
            bullets = await self._phase2_project(proj_data, jd_req, language)
            if bullets:
                phase2_results[proj_name] = bullets

        try:
            from loom.services.logger import logger as _lg
            await _lg.info("workflow", "step.generate.phase2",
                f"Phase 2 done: {sum(len(v) for v in phase2_results.values())} "
                f"bullets for {len(phase2_results)} projects "
                f"(selected from {len(top_projects)} candidates)",
                step_name=self.name,
                projects=list(phase2_results.keys()))
        except Exception:
            pass

        # ── Phase 3: Integration review ──────────────────────────

        phase3_results, removed, review_notes = await self._phase3_review(
            phase1_results, phase2_results, profile_data, jd_parsed, match_result,
            by_experience, integration_pool, experiences,
        )

        try:
            from loom.services.logger import logger as _lg
            await _lg.info("workflow", "step.generate.phase3",
                f"Phase 3 done: {len(removed)} bullets removed. {review_notes[:150]}",
                step_name=self.name, removed_count=len(removed),
                review_notes=review_notes[:300])
        except Exception:
            pass

        # ── Phase 3b: Scrutiny + Rewrite loop ────────────────────

        # Build source_material for scrutiny (reuse from phase3)
        scrutiny_source: dict[str, Any] = {}
        for exp_id_str, selected in by_experience.items():
            exp = experiences.get(UUID(exp_id_str))
            if not exp:
                continue
            company = exp.company_en or "Unknown"
            scrutiny_source[company] = {
                "bullets_star_data": [
                    {
                        "type": b.get("type", "unknown"),
                        "action": b.get("star_data", {}).get("action", ""),
                        "result_quantified": b.get("star_data", {}).get("result_quantified", ""),
                        "result_qualitative": b.get("star_data", {}).get("result_qualitative", ""),
                    }
                    for b in selected
                ],
            }

        phase3b_results, phase3b_debug = await self._phase3b_scrutiny(
            phase3_results, scrutiny_source,
        )

        # Update phase1_exp_data bullets with scrutiny results
        for exp_data in phase1_exp_data:
            company = exp_data["experience"].company_en or ""
            if company in phase3b_results:
                exp_data["bullets"] = phase3b_results[company]

        # ── Phase 4: One-page enforcement ────────────────────────

        tpl_ctx = self._build_template_context(
            profile_data, phase1_exp_data, phase3b_results, jd_parsed,
        )
        exp_relevance = match_result.get("experience_relevance", {})
        lines_before = estimate_lines(tpl_ctx)
        projects_before = len(tpl_ctx.get("projects", []))
        tpl_ctx, phase4_log = self._enforce_one_page(tpl_ctx, exp_relevance)
        final_line_estimate = estimate_lines(tpl_ctx)
        phase4_log["line_estimate_before"] = lines_before
        phase4_log["line_estimate_after"] = final_line_estimate
        phase4_log["projects_before"] = projects_before
        phase4_log["projects_after"] = len(tpl_ctx.get("projects", []))

        try:
            from loom.services.logger import logger as _lg
            n_exp = len(tpl_ctx.get("experiences", []))
            n_proj = len(tpl_ctx.get("projects", []))
            await _lg.info("workflow", "step.generate.phase4",
                f"Phase 4 done: {n_exp} exp + {n_proj} proj, "
                f"estimated {final_line_estimate} lines",
                step_name=self.name, line_estimate=final_line_estimate,
                **phase4_log)
        except Exception:
            pass

        # Render templates — tex filter uses dynamic terms from profile
        content_md = self._md_template.render(**tpl_ctx)
        latex_filter = make_latex_processor(profile_data)
        tex_env = Environment()
        tex_env.filters["latex"] = latex_filter
        tex_template = tex_env.from_string(self._tex_source)
        content_tex = tex_template.render(**tpl_ctx)

        # Save artifact
        jd_record_id = context.data.get("jd_record_id")
        artifact = ResumeArtifact(
            jd_record_id=UUID(jd_record_id) if jd_record_id else None,
            workflow_run_id=UUID(context.workflow_id) if context.workflow_id else None,
            language=language,
            content_md=content_md,
            content_tex=content_tex,
        )
        await self.resume_repo.save_artifact(artifact)

        # Save debug info
        debug = {
            "phase1": phase1_results,
            "phase2": phase2_results,
            "phase3_review": {
                "approved_experiences": {
                    k: v for k, v in phase3_results.items()
                    if k not in phase2_results
                },
                "approved_projects": {
                    k: v for k, v in phase3_results.items()
                    if k in phase2_results
                },
            },
            "phase3_removed": removed,
            "phase3_review_notes": review_notes,
            "phase3b": phase3b_debug,
            "final_line_estimate": final_line_estimate,
        }

        new_data = {
            **context.data,
            "resume_artifact_id": str(artifact.id),
            "generation_debug": debug,
        }
        return context.model_copy(update={"data": new_data})

    # ── Phase 1 ──────────────────────────────────────────────────

    async def _phase1_experience(
        self,
        exp: Experience,
        selected_bullets: list[dict],
        jd_parsed: dict,
        jd_req: dict,
        max_bullets: int,
        language: str,
        linked_projects: list[dict] | None = None,
    ) -> list[str]:
        """Generate bullets for one experience using only its own data."""

        materials = []
        for b in selected_bullets:
            star = b.get("star_data", {})
            m = f"- Type: {b.get('type', 'unknown')}\n"
            if star.get("situation"):
                m += f"  Situation: {star['situation']}\n"
            if star.get("task"):
                m += f"  Task: {star['task']}\n"
            if star.get("action"):
                m += f"  Action: {star['action']}\n"
            if star.get("result_quantified"):
                m += f"  Result (quantified): {star['result_quantified']}\n"
            if star.get("result_qualitative"):
                m += f"  Result (qualitative): {star['result_qualitative']}\n"
            raw = b.get("raw_text") or b.get("content_en", "")
            if raw:
                m += f"  content_en (reference only): {raw}\n"
            materials.append(m)

        tech_parts = set()
        for b in selected_bullets:
            for t in b.get("tech_stack", []):
                if isinstance(t, dict) and t.get("name"):
                    role = t.get("role", "")
                    tech_parts.add(f"{t['name']}" + (f" ({role})" if role else ""))
                elif isinstance(t, str):
                    tech_parts.add(t)

        period = _format_period(
            str(exp.start_date) if exp.start_date else None,
            str(exp.end_date) if exp.end_date else None,
        )

        # Build linked project material section
        linked_section = ""
        if linked_projects:
            linked_parts = []
            for proj in linked_projects:
                proj_name = proj.get("name", "")
                for b in proj.get("bullets", [])[:3]:
                    content = b.get("content_en") or ""
                    star = b.get("star_data", {})
                    part = f"- From project built during this role:\n"
                    if star.get("action"):
                        part += f"  Action: {star['action']}\n"
                    if star.get("result_quantified"):
                        part += f"  Result: {star['result_quantified']}\n"
                    if content:
                        part += f"  Reference: {content[:150]}\n"
                    linked_parts.append(part)
                # Also add project tech stack
                for t in proj.get("tech_stack", []):
                    name = t.get("name", "") if isinstance(t, dict) else str(t)
                    if name:
                        tech_parts.add(name)
            if linked_parts:
                proj_names = [p.get("name", "") for p in linked_projects if p.get("name")]
                coverage_req = ""
                if len(proj_names) > 1:
                    coverage_req = (
                        f"\n\nCOVERAGE REQUIREMENT: This role has {len(proj_names)} linked projects: "
                        f"{', '.join(proj_names)}. Each must be represented in at least one bullet. "
                        "Do NOT write multiple bullets about the same project while leaving another uncovered."
                    )
                linked_section = (
                    "\n\n== LINKED PROJECT MATERIAL (built during this role, "
                    "integrate into bullets, do NOT mention project names) ==\n"
                    + "\n".join(linked_parts) + coverage_req
                )

        prompt = PHASE1_USER.format(
            max_bullets=max_bullets,
            jd_title=jd_parsed.get("title", "Unknown"),
            jd_company=jd_parsed.get("company", "Unknown"),
            jd_required=", ".join(jd_req["required_skills"]) or "Not specified",
            jd_key_requirements="; ".join(jd_req["key_requirements"][:5]) or "Not specified",
            jd_focus=", ".join(jd_req["jd_focus"]) or "General",
            company=exp.company_en,
            title=exp.title_en,
            period=period,
            bullets_material="\n".join(materials) or "None",
            tech_stack=", ".join(tech_parts) or "Not specified",
            language="English" if language == "en" else "Chinese",
        ) + linked_section

        try:
            result = await self.claude.extract_json(
                prompt=prompt, model=Model.HAIKU, system=PHASE1_SYSTEM,
            )
            bullets_raw = result.get("bullets", [])
            # Extract content from structured or plain format
            bullets = []
            for b in bullets_raw[:max_bullets]:
                text = b.get("content", "") if isinstance(b, dict) else str(b)
                if text:
                    # Soft truncate: prefer cutting at dash, otherwise keep full
                    # Phase 3b will catch quality issues on long bullets
                    if len(text) > 180:
                        dash_pos = text[:160].rfind(" — ")
                        if dash_pos > 60:
                            text = text[:dash_pos]
                        # Otherwise keep full — don't create incomplete sentences
                    bullets.append(text)
            return bullets
        except Exception as e:
            logger.warning("Phase 1 failed for %s: %s", exp.company_en, e)
            return [b.get("raw_text", "") for b in selected_bullets][:max_bullets]

    # ── Phase 2 ──────────────────────────────────────────────────

    async def _phase2_project(
        self,
        proj: dict,
        jd_req: dict,
        language: str,
    ) -> list[str]:
        """Generate bullets for one project using only its own data."""

        materials = []
        for b in proj.get("bullets", [])[:4]:
            content = b.get("content_en") or b.get("content") or ""
            btype = b.get("type", "unknown")
            star = b.get("star_data", {})
            m = f"- Type: {btype}\n"
            if star.get("action"):
                m += f"  Action: {star['action']}\n"
            if star.get("result_quantified"):
                m += f"  Result: {star['result_quantified']}\n"
            if content:
                m += f"  content_en (reference): {content[:200]}\n"
            materials.append(m)

        tech_names = [
            t.get("name", "") if isinstance(t, dict) else str(t)
            for t in proj.get("tech_stack", [])
        ]

        prompt = PHASE2_USER.format(
            jd_required=", ".join(jd_req["required_skills"]) or "Not specified",
            jd_focus=", ".join(jd_req["jd_focus"]) or "General",
            name=proj.get("name", ""),
            description=proj.get("description", "") or "N/A",
            tech_stack=", ".join(tech_names) or "Not specified",
            bullets_material="\n".join(materials) or "None",
            language="English" if language == "en" else "Chinese",
        )

        try:
            result = await self.claude.extract_json(
                prompt=prompt, model=Model.HAIKU, system=PHASE2_SYSTEM,
            )
            bullets_raw = result.get("bullets", [])
            bullets = []
            for b in bullets_raw[:2]:
                if isinstance(b, dict):
                    bullets.append(b.get("content", ""))
                else:
                    bullets.append(str(b))
            return [b for b in bullets if b]
        except Exception as e:
            logger.warning("Phase 2 failed for %s: %s", proj.get("name"), e)
            return []

    # ── Phase 3 ──────────────────────────────────────────────────

    async def _phase3_review(
        self,
        phase1: dict[str, list[str]],
        phase2: dict[str, list[str]],
        profile_data: dict,
        jd_parsed: dict,
        match_result: dict,
        by_experience: dict[str, list[dict]],
        integration_pool: dict,
        experiences_map: dict,
    ) -> tuple[dict[str, list[str]], list[dict], str]:
        """Review all bullets against STAR source material.

        Returns (approved_bullets_by_section, removed_list, review_notes).
        Falls back to phase1+phase2 if review fails.
        """
        import json

        all_bullets = {
            "experiences": phase1,
            "projects": phase2,
        }

        # Build source_material: STAR ground truth for each company/project
        source_material: dict[str, Any] = {"experiences": {}, "projects": {}}

        for exp_id_str, selected in by_experience.items():
            exp = experiences_map.get(UUID(exp_id_str))
            if not exp:
                continue
            company = exp.company_en or "Unknown"
            star_entries = []
            for b in selected:
                star = b.get("star_data", {})
                tech = b.get("tech_stack", [])
                tech_names = [
                    t.get("name", "") if isinstance(t, dict) else str(t)
                    for t in tech
                ]
                star_entries.append({
                    "type": b.get("type", "unknown"),
                    "situation": star.get("situation", ""),
                    "task": star.get("task", ""),
                    "action": star.get("action", ""),
                    "result_quantified": star.get("result_quantified", ""),
                    "result_qualitative": star.get("result_qualitative", ""),
                    "tech_stack": tech_names,
                })
            source_material["experiences"][company] = {
                "bullets_star_data": star_entries,
            }

        for proj in integration_pool.get("projects", []):
            proj_name = proj.get("name", "")
            if proj_name not in phase2:
                continue
            proj_stars = []
            for b in proj.get("bullets", [])[:4]:
                star = b.get("star_data", {})
                proj_stars.append({
                    "type": b.get("type", "unknown"),
                    "action": star.get("action", "") if isinstance(star, dict) else "",
                    "result": star.get("result_quantified", "") if isinstance(star, dict) else "",
                    "content_en": b.get("content_en") or b.get("content") or "",
                })
            source_material["projects"][proj_name] = {
                "bullets_source": proj_stars,
            }

        # Collect all tech from profile
        all_tech = set()
        for s in profile_data.get("skills", []):
            all_tech.add(s.get("name", ""))

        prompt = PHASE3_USER.format(
            all_bullets_json=json.dumps(all_bullets, indent=2, ensure_ascii=False),
            source_material_json=json.dumps(source_material, indent=2, ensure_ascii=False),
            candidate_tech_stack=", ".join(sorted(all_tech)),
            jd_required=", ".join(jd_parsed.get("required_skills", [])),
            hard_skill_gaps=", ".join(match_result.get("hard_skill_gaps", [])),
            jd_key_requirements="; ".join(jd_parsed.get("key_requirements", [])[:5]),
        )

        try:
            result = await self.claude.extract_json(
                prompt=prompt, model=Model.SONNET, system=PHASE3_SYSTEM,
            )

            approved = result.get("approved", {})
            removed = result.get("removed", [])
            corrections = result.get("corrections", [])
            notes = result.get("review_notes", "")

            if corrections:
                notes += f" [{len(corrections)} fact corrections applied]"

            flat: dict[str, list[str]] = {}
            for company, bullets in approved.get("experiences", {}).items():
                flat[company] = bullets
            for proj, bullets in approved.get("projects", {}).items():
                flat[proj] = bullets

            # Enforce minimum: Phase 3 must not drop experiences below 3 bullets.
            # Restore from Phase 1 originals if it did.
            for company in phase1:
                if company in flat and len(flat[company]) < 3:
                    # Restore from phase1, picking bullets Phase 3 removed
                    existing = set(flat[company])
                    for orig in phase1[company]:
                        if orig not in existing and len(flat[company]) < 3:
                            flat[company].append(orig)

            return flat, removed + corrections, notes

        except Exception as e:
            logger.warning("Phase 3 review failed, using raw results: %s", e)
            merged = {**phase1, **phase2}
            return merged, [], f"Review skipped: {e}"

    # ── Phase 3b: Scrutiny + Rewrite loop ──────────────────────

    async def _phase3b_scrutiny(
        self,
        approved: dict[str, list[str]],
        source_material: dict[str, Any],
    ) -> tuple[dict[str, list[str]], dict]:
        """Iterative scrutiny: review bullets, rewrite high-severity, repeat.

        Returns (final_bullets, debug_info).
        Falls back to input on failure.
        """
        import json

        current = {k: list(v) for k, v in approved.items()}
        all_issues: list[dict] = []
        rounds_used = 0
        last_pass = 0
        last_fail = 0

        for round_num in range(1, MAX_SCRUTINY_ROUNDS + 1):
            rounds_used = round_num

            # 1. Scrutiny
            prompt = SCRUTINY_USER.format(
                round=round_num,
                bullets_json=json.dumps(current, indent=2, ensure_ascii=False),
                source_material_json=json.dumps(source_material, indent=2, ensure_ascii=False),
            )

            try:
                result = await self.claude.extract_json(
                    prompt=prompt, model=Model.SONNET, system=SCRUTINY_SYSTEM,
                )
            except Exception as e:
                logger.warning("Phase 3b scrutiny failed round %d: %s", round_num, e)
                break

            issues = result.get("issues", [])
            last_pass = result.get("pass_count", 0)
            last_fail = result.get("fail_count", 0)
            high = [i for i in issues if i.get("severity") == "high"]
            all_issues.extend(issues)

            try:
                from loom.services.logger import logger as _lg
                hallucination_count = sum(1 for i in issues if i.get("hallucination") == "fail")
                await _lg.info("workflow", "step.generate.phase3b.scrutiny",
                    f"Round {round_num}: {len(issues)} issues, {len(high)} high, "
                    f"{hallucination_count} hallucinations",
                    step_name=self.name, round=round_num,
                    total_issues=len(issues), high_count=len(high),
                    hallucination_count=hallucination_count,
                    pass_count=last_pass, fail_count=last_fail)
            except Exception:
                pass

            # 2. No high severity — done
            if not high:
                break

            # 3. Rewrite each high-severity bullet
            for issue in high:
                section = issue.get("section", "")
                idx = issue.get("bullet_index", 0)
                if section not in current or idx >= len(current[section]):
                    continue

                # Get star_data for this section
                star_json = json.dumps(
                    source_material.get(section, {}).get("bullets_star_data", []),
                    ensure_ascii=False,
                )

                # Build list of other bullets in same section (for dedup)
                other = [b for i2, b in enumerate(current[section]) if i2 != idx]

                # Build hallucination note if applicable
                is_hallucination = issue.get("hallucination") == "fail"
                hallucinated_claim = issue.get("hallucinated_claim", "")
                h_note = ""
                if is_hallucination and hallucinated_claim:
                    h_note = (f"HALLUCINATED METRIC: \"{hallucinated_claim}\" — "
                              f"this number is NOT in the source data. Remove it.")

                rewrite_prompt = REWRITE_USER.format(
                    original=issue.get("original", current[section][idx]),
                    critique=issue.get("critique", ""),
                    severity="high",
                    bullet_type=issue.get("type", "implementation"),
                    hallucination_note=h_note,
                    other_bullets="\n".join(f"- {b}" for b in other) or "None",
                    star_data_json=star_json,
                )

                try:
                    rw = await self.claude.extract_json(
                        prompt=rewrite_prompt, model=Model.SONNET, system=REWRITE_SYSTEM,
                    )
                    new_text = rw.get("rewritten", "")
                    if new_text:
                        # Truncate if needed
                        # Don't truncate rewrites — they should already be <140 chars
                        current[section][idx] = new_text

                    try:
                        from loom.services.logger import logger as _lg
                        await _lg.info("workflow", "step.generate.phase3b.rewrite",
                            f"Rewrote bullet in {section}" + (" [hallucination fix]" if is_hallucination else ""),
                            step_name=self.name, section=section, bullet_index=idx,
                            original=issue.get("original", "")[:80],
                            rewritten=new_text[:80],
                            critique=issue.get("critique", ""),
                            changes=rw.get("changes_made", ""),
                            hallucination_fix=is_hallucination,
                            hallucinated_claim=hallucinated_claim or None)
                    except Exception:
                        pass

                except Exception as e:
                    logger.warning("Phase 3b rewrite failed for %s[%d]: %s", section, idx, e)

            # 4. Max rounds warning
            if round_num == MAX_SCRUTINY_ROUNDS:
                try:
                    from loom.services.logger import logger as _lg
                    await _lg.warning("workflow", "step.generate.phase3b.max_rounds",
                        f"Reached {MAX_SCRUTINY_ROUNDS} rounds, some issues may remain",
                        step_name=self.name)
                except Exception:
                    pass

        debug = {
            "rounds_used": rounds_used,
            "all_issues": all_issues,
            "final_pass_rate": f"{last_pass}/{last_pass + last_fail}",
        }

        try:
            from loom.services.logger import logger as _lg
            await _lg.info("workflow", "step.generate.phase3b.complete",
                f"Phase 3b done: {rounds_used} round(s), "
                f"pass rate {last_pass}/{last_pass + last_fail}",
                step_name=self.name, **debug)
        except Exception:
            pass

        return current, debug

    # ── Phase 4: Template + one-page ─────────────────────────────

    def _build_template_context(
        self,
        profile: dict,
        phase1_exp_data: list[dict],
        approved: dict[str, list[str]],
        jd_parsed: dict,
    ) -> dict:
        """Build Jinja2 template context from approved bullets."""
        p = profile["profile"]

        candidate = {
            "name": p.get("name") or "",
            "email": p.get("email") or "",
            "phone": p.get("phone") or "",
            "location": p.get("location") or "",
            "linkedin": "", "linkedin_handle": "",
            "github": "", "github_handle": "",
        }

        # Skills — smart grouping with context (sources: bullets + all projects)
        skill_groups = self._generate_skill_groups(
            profile.get("skills", []), jd_parsed, approved, profile,
        )

        # Education
        education_list = []
        for edu in profile.get("education", []):
            degree = edu.get("degree") or ""
            field = edu.get("field") or ""
            abbrev, subject = _format_degree(degree)
            # Build "M.S. in Computer Science (Machine Learning and Big Data)"
            degree_line = abbrev
            if subject:
                degree_line += f" in {subject}"
            if field:
                degree_line += f" ({field})"
            education_list.append({
                "degree": f"{degree} in {field}" if field else degree,
                "degree_abbrev": degree_line,
                "field": None,  # already included in degree_abbrev
                "institution": edu.get("institution") or "",
                "period": _format_period(edu.get("start_date"), edu.get("end_date")),
            })

        # Experiences — use approved bullets, fall back to phase1
        exp_list = []
        for exp_data in phase1_exp_data:
            exp: Experience = exp_data["experience"]
            company = exp.company_en or ""
            bullets = approved.get(company, exp_data["bullets"])
            period = _format_period(
                str(exp.start_date) if exp.start_date else None,
                str(exp.end_date) if exp.end_date else None,
            )
            exp_list.append({
                "title": exp.title_en or "",
                "company": company,
                "period": period,
                "bullets": list(bullets),
            })

        # Projects — from approved
        project_list = []
        for proj_name, bullets in approved.items():
            # Skip if it's an experience (already handled)
            if any(e["company"] == proj_name for e in exp_list):
                continue
            if bullets:
                project_list.append({
                    "name": proj_name,
                    "tech_stack": [],  # tech visible in bullets themselves
                    "bullets": list(bullets),
                })

        return {
            "candidate": candidate,
            "skills": skill_groups,
            "education": education_list,
            "certifications": self._get_certifications(profile),
            "experiences": exp_list,
            "projects": project_list,
        }

    @staticmethod
    def _get_certifications(profile: dict) -> list[dict]:
        """Extract certifications from profile data."""
        p = profile.get("profile", {})
        # certifications stored as list of {year, name} on profile
        raw = p.get("certifications") or []
        if isinstance(raw, list):
            return [{"year": c.get("year", ""), "name": c.get("name", "")} for c in raw if c.get("name")]
        return []

    @staticmethod
    def _select_projects_by_score(
        projects: list[dict],
        scores: list[dict],
    ) -> list[dict]:
        """Select top projects using Claude semantic scores."""
        score_map = {s.get("name", ""): s.get("score", 0) for s in scores}

        scored = []
        for proj in projects:
            name = proj.get("name", "")
            score = score_map.get(name, 0)
            if score >= 50:  # min threshold
                scored.append((score, proj))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Take top 2, or top 1 if only 1 qualifies
        selected = [p for _, p in scored[:2]]

        # If nothing scored >= 50, take the single highest
        if not selected and scores:
            best = max(scores, key=lambda s: s.get("score", 0))
            best_name = best.get("name", "")
            for proj in projects:
                if proj.get("name") == best_name:
                    selected = [proj]
                    break

        return selected

    def _select_projects(
        self,
        projects: list[dict],
        jd_parsed: dict,
        bullet_text: str,
    ) -> list[dict]:
        """Select top 1-2 projects by technical depth scoring."""
        required = set(s.lower() for s in jd_parsed.get("required_skills", []))
        preferred = set(s.lower() for s in jd_parsed.get("preferred_skills", []))
        jd_skills = required | preferred

        depth_kw = {"pipeline", "engine", "sandbox", "execution", "compiler",
                     "parser", "scheduler", "orchestrat", "algorithm", "concurrent"}
        arch_kw = {"architect", "design", "distributed", "microservice", "real-time", "async"}
        crud_kw = {"crud", "basic form", "simple api", "todo", "blog"}

        scored = []
        for proj in projects:
            tech_names = [
                t.get("name", "") if isinstance(t, dict) else str(t)
                for t in proj.get("tech_stack", [])
            ]
            proj_text = " ".join([
                proj.get("name", ""), proj.get("description", ""),
                " ".join(b.get("content_en") or b.get("content") or "" for b in proj.get("bullets", [])),
            ]).lower()

            score = 0
            if any(kw in proj_text for kw in depth_kw):
                score += 3
            if any(w in proj_text for w in ("user", "production", "deploy", "serving")):
                score += 3
            jd_new = sum(1 for t in tech_names if t.lower() in jd_skills and t.lower() not in bullet_text)
            score += min(jd_new * 2, 4)
            if any(kw in proj_text for kw in arch_kw):
                score += 2
            if re.search(r'\d+[,.]?\d*\s*(?:%|users|records|requests|ms|seconds)', proj_text):
                score += 1
            if any(kw in proj_text for kw in crud_kw):
                score -= 2
            if len(proj.get("bullets", [])) <= 1 and len(tech_names) <= 2:
                score -= 2

            if score > 0:
                scored.append((score, proj))

        scored.sort(key=lambda x: x[0], reverse=True)
        selected = [p for _, p in scored[:2]]
        # Attach debug info for logging
        self._last_project_scores = [
            {"name": p.get("name", ""), "score": s} for s, p in scored
        ]
        return selected

    def _generate_skill_groups(
        self,
        all_skills: list[dict],
        jd_parsed: dict,
        approved_bullets: dict[str, list[str]],
        profile: dict | None = None,
    ) -> list[dict]:
        """Generate max 4 skill groups with context, ATS-optimized.

        Sources: bullet text + ALL project tech stacks (linked + standalone).
        """
        required = set(s.lower() for s in jd_parsed.get("required_skills", []))
        preferred = set(s.lower() for s in jd_parsed.get("preferred_skills", []))
        jd_skills = required | preferred

        # Collect evidence text from bullets + all projects
        evidence_parts = [b for bs in approved_bullets.values() for b in bs]
        if profile:
            # Add standalone project tech names
            for proj in profile.get("projects", []):
                for t in proj.get("tech_stack", []):
                    name = t.get("name", "") if isinstance(t, dict) else str(t)
                    if name:
                        evidence_parts.append(name)
            # Add experience-linked project tech names
            for exp in profile.get("experiences", []):
                for proj in exp.get("projects", []):
                    for t in proj.get("tech_stack", []):
                        name = t.get("name", "") if isinstance(t, dict) else str(t)
                        if name:
                            evidence_parts.append(name)
        bullet_text = " ".join(evidence_parts).lower()

        # Build skill lookup by category
        by_cat: dict[str, list[str]] = {}
        for s in all_skills:
            cat = (s.get("category") or "Other").strip()
            by_cat.setdefault(cat, []).append(s["name"])

        # Define group templates with context generators
        GROUP_DEFS = [
            {
                "label": "Full-Stack",
                "alt_labels": ["Backend", "Frontend"],
                "cats": ["Backend", "Frontend"],
                "contexts": {
                    "backend_heavy": "production web applications with API design and database optimization",
                    "frontend_heavy": "interactive data platforms with real-time visualization",
                    "balanced": "production platforms with AWS deployment and real-time data visualization",
                },
            },
            {
                "label": "Data & Analytics",
                "alt_labels": ["Data Processing"],
                "cats": ["Data Processing", "Database"],
                "contexts": {
                    "default": "time-series processing and quantitative strategy backtesting",
                },
            },
            {
                "label": "Cloud & DevOps",
                "alt_labels": ["DevOps/Infra"],
                "cats": ["DevOps/Infra"],
                "contexts": {
                    "default": "serverless pipelines and containerized deployments on AWS",
                },
            },
            {
                "label": "AI & Automation",
                "alt_labels": ["AI/ML"],
                "cats": ["AI/ML"],
                "contexts": {
                    "default": "agentic pipeline design and LLM integration",
                },
            },
        ]

        # Decide JD emphasis
        jd_text = " ".join(jd_parsed.get("required_skills", []) +
                           jd_parsed.get("key_requirements", [])).lower()
        is_backend = any(w in jd_text for w in ("backend", "api", "server", "database", "sql"))
        is_frontend = any(w in jd_text for w in ("frontend", "react", "ui", "ux", "javascript"))
        is_data = any(w in jd_text for w in ("data", "analytics", "pipeline", "etl", "pandas"))
        is_ai = any(w in jd_text for w in ("ai", "ml", "llm", "machine learning", "nlp"))

        # Build groups
        groups: list[dict] = []
        used_skills: set[str] = set()

        for gdef in GROUP_DEFS:
            # Collect skills from matching categories
            techs: list[str] = []
            for cat in gdef["cats"]:
                for name in by_cat.get(cat, []):
                    if name not in used_skills:
                        nl = name.lower()
                        # Only include if: appears in bullets, or is JD required/preferred
                        in_bullets = nl in bullet_text
                        in_jd = nl in jd_skills
                        if in_bullets or in_jd:
                            techs.append(name)

            if not techs:
                continue

            # Sort: JD-required first, then preferred, then rest
            def skill_sort_key(name: str) -> int:
                nl = name.lower()
                if nl in required:
                    return 0
                if nl in preferred:
                    return 1
                return 2

            techs.sort(key=skill_sort_key)

            # ATS: ensure JD skills in this category domain appear
            for jd_s in jd_parsed.get("required_skills", []):
                jd_sl = jd_s.lower()
                if jd_sl not in {t.lower() for t in techs}:
                    # Check if this JD skill belongs to this group's domain
                    for cat in gdef["cats"]:
                        cat_names = {n.lower() for n in by_cat.get(cat, [])}
                        if jd_sl in cat_names and jd_s not in used_skills:
                            techs.append(jd_s)

            if not techs:
                continue

            # Pick context
            contexts = gdef["contexts"]
            if "Full-Stack" in gdef["label"]:
                if is_backend and not is_frontend:
                    ctx = contexts.get("backend_heavy", contexts.get("default", ""))
                elif is_frontend and not is_backend:
                    ctx = contexts.get("frontend_heavy", contexts.get("default", ""))
                else:
                    ctx = contexts.get("balanced", contexts.get("default", ""))
                # Adjust label
                if is_backend and not is_frontend:
                    label = "Backend"
                elif is_frontend and not is_backend:
                    label = "Frontend"
                else:
                    label = gdef["label"]
            else:
                ctx = contexts.get("default", "")
                label = gdef["label"]

            # Skip groups with no JD relevance and only 1-2 techs
            has_jd_match = any(t.lower() in jd_skills for t in techs)
            if not has_jd_match and len(techs) <= 2:
                continue

            content = ", ".join(techs[:8])
            if ctx:
                content += f" — {ctx}"

            groups.append({"category": label, "content": content})
            used_skills.update(techs)

            if len(groups) >= 4:
                break

        # Score and sort: JD-most-relevant group first
        def group_relevance(g: dict) -> int:
            score = 0
            for tech in g["content"].split(" — ")[0].split(", "):
                if tech.strip().lower() in required:
                    score += 2
                elif tech.strip().lower() in preferred:
                    score += 1
            return score

        groups.sort(key=group_relevance, reverse=True)
        return groups

    def _enforce_one_page(
        self, ctx: dict, exp_relevance: dict[str, Any],
    ) -> tuple[dict, dict]:
        """Relevance-driven one-page enforcement.

        Trim order: lowest relevance first. Never remove most recent experience.
        Always keep at least 2 experiences. Returns (ctx, log_info).
        """
        log = {
            "experiences_removed": [],
            "experiences_compressed": {},
            "relevance_scores": {},
        }

        # Build relevance map: company → score
        relevance: dict[str, int] = {}
        for company_key, data in exp_relevance.items():
            score = data.get("score", 5) if isinstance(data, dict) else 5
            relevance[company_key] = score

        exps = ctx.get("experiences", [])
        for exp in exps:
            company = exp.get("company", "")
            if company not in relevance:
                relevance[company] = 5  # default mid-score
            log["relevance_scores"][company] = relevance[company]

        if estimate_lines(ctx) <= MAX_ONE_PAGE_LINES:
            return ctx, log

        # 1. Remove projects (lowest cost)
        if ctx.get("projects"):
            ctx["projects"] = []
            if estimate_lines(ctx) <= MAX_ONE_PAGE_LINES:
                return ctx, log

        # 2. Compress least relevant experiences to 2 bullets
        exps_by_relevance = sorted(
            range(len(exps)),
            key=lambda i: relevance.get(exps[i].get("company", ""), 5),
        )

        for i in exps_by_relevance:
            if i == 0:
                continue  # never compress most recent (index 0)
            company = exps[i].get("company", "")
            current_count = len(exps[i].get("bullets", []))
            if current_count > 2:
                exps[i]["bullets"] = exps[i]["bullets"][:2]
                log["experiences_compressed"][company] = 2
                if estimate_lines(ctx) <= MAX_ONE_PAGE_LINES:
                    return ctx, log

        # 3. Remove least relevant experience entirely (if score < 4, keep >= 2 exps)
        if len(exps) > 2:
            for i in exps_by_relevance:
                if i == 0:
                    continue  # never remove most recent
                company = exps[i].get("company", "")
                score = relevance.get(company, 5)
                if score < 4 and len(exps) > 2:
                    log["experiences_removed"].append(company)
                    exps.pop(i)
                    ctx["experiences"] = exps
                    if estimate_lines(ctx) <= MAX_ONE_PAGE_LINES:
                        return ctx, log
                    break  # re-sort after removal

        # 4. Last resort: trim most recent to 3
        if exps and len(exps[0].get("bullets", [])) > MIN_BULLETS_MOST_RECENT:
            exps[0]["bullets"] = exps[0]["bullets"][:MIN_BULLETS_MOST_RECENT]

        return ctx, log

    async def _create_empty_artifact(self, context: PipelineContext, reason: str) -> ResumeArtifact:
        jd_record_id = context.data.get("jd_record_id")
        artifact = ResumeArtifact(
            jd_record_id=UUID(jd_record_id) if jd_record_id else UUID(int=0),
            language=context.data.get("language", "en"),
            content_md=f"# Resume\n\n*Warning: {reason}*\n",
            content_tex=rf"\documentclass{{article}}\begin{{document}}Warning: {reason}\end{{document}}",
        )
        await self.resume_repo.save_artifact(artifact)
        return artifact


step_registry.register("generate-resume", GenerateResumeStep)
