"""Translation service for bilingual (EN/ZH) content.

Uses Claude Haiku for cost-effective, high-quality translation.
Preserves technical terms, numbers, and percentages.
"""

import json
import logging

from loom.llm.client import Claude, Model
from loom.storage.bullet import Bullet
from loom.storage.profile import Experience

logger = logging.getLogger(__name__)

# Technical terms that should never be translated
KEEP_ENGLISH = [
    "Python", "Java", "JavaScript", "TypeScript", "Go", "Rust", "C++", "C#",
    "React", "Vue", "Angular", "Next.js", "Node.js", "Django", "FastAPI", "Flask",
    "AWS", "GCP", "Azure", "Docker", "Kubernetes", "Terraform",
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "Kafka",
    "GraphQL", "REST", "API", "SDK", "CI/CD", "DevOps", "MLOps",
    "Git", "GitHub", "GitLab", "Jenkins", "Airflow", "Spark",
    "Linux", "macOS", "iOS", "Android",
    "LLM", "GPT", "BERT", "NLP", "ML", "AI",
    "S3", "EC2", "Lambda", "ECS", "RDS", "SQS", "SNS",
    "HTTP", "HTTPS", "TCP", "gRPC", "WebSocket",
    "JSON", "YAML", "XML", "CSV", "SQL", "NoSQL",
    "OAuth", "JWT", "SSO", "RBAC",
    "SLA", "SLO", "SLI", "QPS", "TPS", "P99", "P95",
]

TRANSLATION_SYSTEM_PROMPT = """You are a professional translator specializing in tech industry resumes.
Translate English to Chinese (Simplified).

Rules:
1. Keep ALL technical terms in English: {keep_english}
2. Keep numbers, percentages, and metrics exactly as-is (e.g. "50%", "$2M", "10x")
3. Preserve the strength of action verbs — do not weaken them.
   Examples: "Architected" -> "架构设计并实现" (NOT "参与了")
            "Spearheaded" -> "主导" (NOT "参与")
            "Reduced ... by 40%" -> "将...降低了40%" (NOT "优化了...")
4. Keep the same level of specificity. If the English is specific, the Chinese must be equally specific.
5. Output must be natural Chinese that a native speaker would write on their resume."""

BULLET_BATCH_PROMPT = """Translate these resume bullet points from English to Chinese.

Context: {context}

Bullet points to translate:
{bullets_json}

Return a JSON array where each element has "index" and "zh" keys.
Example: [{{"index": 0, "zh": "使用 Python 和 FastAPI 构建了..."}}]

Remember: Keep tech terms in English, preserve numbers/metrics, maintain action verb strength."""


class TranslationService:
    """Translates resume content between English and Chinese using Claude Haiku."""

    def __init__(self, claude: Claude | None = None):
        self._claude = claude or Claude()

    async def translate_to_zh(
        self,
        field_name: str,
        content_en: str,
        context: str = "",
    ) -> str:
        """Translate a single English text field to Chinese.

        Args:
            field_name: Name of the field being translated (for logging)
            content_en: English text to translate
            context: Optional context to improve translation quality

        Returns:
            Chinese translation, or the original English on failure
        """
        if not content_en or not content_en.strip():
            return ""

        keep_list = ", ".join(KEEP_ENGLISH[:30])  # Truncate for prompt size
        system = TRANSLATION_SYSTEM_PROMPT.format(keep_english=keep_list)

        prompt = f"Translate this {field_name} to Chinese:\n\n{content_en}"
        if context:
            prompt = f"Context: {context}\n\n{prompt}"

        try:
            result = await self._claude.complete(
                prompt=prompt,
                model=Model.HAIKU,
                system=system,
                max_tokens=1024,
            )
            try:
                from loom.services.logger import logger as loom_log
                await loom_log.info("claude_api", "translation.complete",
                    f"Translated '{field_name}' ({len(content_en)} chars)",
                    field_name=field_name, char_len=len(content_en))
            except Exception:
                pass
            return result.strip()
        except Exception as e:
            logger.exception("Translation failed for field '%s'", field_name)
            try:
                from loom.services.logger import logger as loom_log
                await loom_log.warning("claude_api", "translation.failed",
                    f"Translation failed for '{field_name}': {e}",
                    error=e, field_name=field_name)
            except Exception:
                pass
            return ""

    async def translate_experience(self, experience: Experience) -> Experience:
        """Translate all text fields in an Experience to Chinese.

        Translates title_en -> title_zh and company_en -> company_zh
        (if not already set manually).

        Returns a new Experience with _zh fields populated.
        """
        updates = {}

        if experience.title_en and not experience.title_zh:
            updates["title_zh"] = await self.translate_to_zh(
                "job title",
                experience.title_en,
                context=f"Company: {experience.company_en}",
            )

        if experience.company_en and not experience.company_zh:
            # Company names: only translate if it has a well-known Chinese name
            updates["company_zh"] = await self.translate_to_zh(
                "company name",
                experience.company_en,
                context="If the company has a well-known Chinese name, use it. "
                "Otherwise keep the English name.",
            )

        if experience.location_en and not experience.location_zh:
            updates["location_zh"] = await self.translate_to_zh(
                "location",
                experience.location_en,
            )

        if updates:
            return experience.model_copy(update=updates)
        return experience

    async def translate_bullets(
        self,
        bullets: list[Bullet],
        context: str = "",
    ) -> list[Bullet]:
        """Batch-translate bullet points from English to Chinese.

        Translates content_en -> content_zh for bullets that don't have
        a Chinese translation yet. Uses a single API call for efficiency.

        Args:
            bullets: List of Bullet objects to translate
            context: Optional context (e.g. company + title) for quality

        Returns:
            New list of Bullet objects with content_zh populated
        """
        # Filter to only bullets needing translation
        needs_translation = [
            (i, b) for i, b in enumerate(bullets)
            if b.content_en and not b.content_zh
        ]

        if not needs_translation:
            return bullets

        # Build batch payload
        batch = [
            {"index": i, "en": b.content_en}
            for i, b in needs_translation
        ]

        keep_list = ", ".join(KEEP_ENGLISH[:30])
        system = TRANSLATION_SYSTEM_PROMPT.format(keep_english=keep_list)

        prompt = BULLET_BATCH_PROMPT.format(
            context=context or "Resume bullet points",
            bullets_json=json.dumps(batch, ensure_ascii=False),
        )

        try:
            translated, _ = await self._claude.extract_json_with_usage(
                prompt=prompt,
                model=Model.HAIKU,
                system=system,
            )

            # Build index -> zh mapping
            zh_map: dict[int, str] = {}
            if isinstance(translated, list):
                for item in translated:
                    zh_map[item["index"]] = item["zh"]
            elif isinstance(translated, dict) and "translations" in translated:
                for item in translated["translations"]:
                    zh_map[item["index"]] = item["zh"]

            # Apply translations
            result = list(bullets)
            for orig_index, bullet in needs_translation:
                if orig_index in zh_map:
                    result[orig_index] = bullet.model_copy(
                        update={"content_zh": zh_map[orig_index]}
                    )

            return result

        except Exception:
            logger.exception("Batch bullet translation failed")
            return bullets
