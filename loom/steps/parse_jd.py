"""ParseJDStep - extracts structured data from job description text."""

from typing import TYPE_CHECKING

from loom.core.context import PipelineContext
from loom.core.pipeline import StepError
from loom.core.registry import step_registry
from loom.core.step import Step
from loom.llm import Claude, Model

if TYPE_CHECKING:
    from loom.storage.repository import DataStorage

PARSE_JD_PROMPT = """Analyze the following job description and extract structured information.

JOB DESCRIPTION:
{jd_text}

---

Extract and return a JSON object with these fields:
- company: Company name (string or null)
- title: Job title (string)
- required_skills: Array of hard technical skills explicitly required
- preferred_skills: Array of nice-to-have technical skills
- key_requirements: Array of key qualifications (experience, education, etc.)
- tech_stack: Array of specific technologies, frameworks, tools mentioned
- experience_years: Years of experience required (number or null)
- soft_requirements: Array of soft skills (communication, teamwork, etc.)

Rules:
- required_skills should ONLY contain hard technical skills (Python, SQL, etc.)
- Do NOT include soft skills in required_skills or preferred_skills
- Soft skills go in soft_requirements
- If a field is not mentioned, use null for single values or [] for arrays
- Be precise: only extract what is explicitly stated

Return ONLY the JSON object, no explanation."""


class ParseJDStep(Step):
    """Parse a job description into structured data.

    Input: context.data["jd_raw_text"] - raw job description text
    Output: context.data["jd_parsed"] - structured JD data dict
    """

    @property
    def name(self) -> str:
        return "parse-jd"

    def __init__(
        self,
        claude: Claude | None = None,
        storage: "DataStorage | None" = None,
    ):
        self.claude = claude or Claude()
        self.storage = storage
        # Configure Claude with storage for usage tracking
        if storage:
            self.claude.set_storage(storage)

    async def run(self, context: PipelineContext) -> PipelineContext:
        jd_text = context.data.get("jd_raw_text")
        if not jd_text:
            raise StepError(self.name, "context.data['jd_raw_text'] is required")

        self.claude.set_context(
            workflow_run_id=context.workflow_id,
            step_name=self.name,
            user_id=context.user_id,
        )

        try:
            from loom.services.logger import logger
            await logger.info("workflow", "step.parse_jd.input",
                f"Parsing JD ({len(jd_text)} chars)",
                step_name=self.name, jd_preview=jd_text[:150])
        except Exception:
            pass

        prompt = PARSE_JD_PROMPT.format(jd_text=jd_text)

        try:
            parsed = await self.claude.extract_json(
                prompt=prompt,
                model=Model.HAIKU,
            )
        except ValueError as e:
            raise StepError(self.name, f"Failed to parse JD: {e}")

        if not parsed.get("title"):
            raise StepError(self.name, "Could not extract job title from JD")

        try:
            from loom.services.logger import logger
            await logger.info("workflow", "step.parse_jd.output",
                f"Parsed: {parsed.get('title')} at {parsed.get('company')}, "
                f"{len(parsed.get('required_skills', []))} required skills",
                step_name=self.name)
        except Exception:
            pass

        new_data = {**context.data, "jd_parsed": parsed}
        return context.model_copy(update={"data": new_data})


# Register step
step_registry.register("parse-jd", ParseJDStep)
