"""Organizer module - detects [ORGANIZE] marker and extracts structured data."""

import re
from datetime import date
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from loom.llm.client import Claude, Model
from loom.storage import (
    Bullet,
    BulletType,
    Confidence,
    DataStorage,
    Experience,
    Profile,
)
from loom.chat.session import ChatMessage, ChatSession


ORGANIZE_MARKER = "[ORGANIZE]"


class ExtractedBullet(BaseModel):
    """Extracted bullet point from conversation."""

    raw_text: str  # Primary text in conversation language
    raw_text_zh: str = ""  # Chinese version
    raw_text_en: str = ""  # English version
    type: str  # Maps to BulletType
    star_data: dict[str, Any] = Field(default_factory=dict)
    tech_stack: list[dict[str, Any]] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class ExtractedExperience(BaseModel):
    """Extracted experience from conversation."""

    company: str
    title: str
    location: str | None = None
    start_date: str | None = None  # YYYY-MM-DD format
    end_date: str | None = None
    bullets: list[ExtractedBullet] = Field(default_factory=list)


class OrganizeResult(BaseModel):
    """Result of organizing conversation into structured data."""

    experience: ExtractedExperience
    message: str = Field(default="", description="Confirmation message to user")


def detect_organize_marker(text: str) -> tuple[bool, str]:
    """Detect and remove [ORGANIZE] marker from text.

    Args:
        text: The assistant's response text

    Returns:
        Tuple of (marker_found, cleaned_text)
    """
    if ORGANIZE_MARKER in text:
        cleaned = text.replace(ORGANIZE_MARKER, "").strip()
        return True, cleaned
    return False, text


def _get_recent_conversation(session: ChatSession, max_messages: int = 20) -> str:
    """Get recent conversation text for extraction.

    Args:
        session: The chat session
        max_messages: Maximum number of messages to include

    Returns:
        Formatted conversation text
    """
    recent = session.messages[-max_messages:] if len(session.messages) > max_messages else session.messages
    is_en = session.language == "en"

    lines = []
    for msg in recent:
        if is_en:
            role_label = "Candidate" if msg.role == "user" else "Advisor"
        else:
            role_label = "候选人" if msg.role == "user" else "顾问"
        lines.append(f"{role_label}: {msg.content}")

    return "\n\n".join(lines)


# Bilingual extraction prompt - always outputs both Chinese and English
EXTRACTION_PROMPT_BILINGUAL = """从以下对话中提取这段经历的结构化信息，并同时生成中英文双语版本。
Extract structured information from this conversation and generate bilingual (Chinese and English) versions.

对话记录 / Conversation transcript:
{conversation}

请提取以下信息并以 JSON 格式返回（必须同时包含中英文）：
Please extract and return in JSON format (must include both Chinese and English):

{{
  "experience": {{
    "company": "公司名称 / Company name",
    "title": "职位名称 / Job title",
    "location": "工作地点 / Work location (if available)",
    "start_date": "YYYY-MM-DD 格式 / YYYY-MM-DD format (if available)",
    "end_date": "YYYY-MM-DD 格式，null表示至今 / YYYY-MM-DD format, null means present",
    "bullets": [
      {{
        "raw_text_zh": "中文版本：用一句话描述成果，格式：通过[行动]实现了[结果]",
        "raw_text_en": "English version: Describe achievement in one sentence, format: Achieved [result] by [action]",
        "type": "bullet类型：business_impact/technical_design/implementation/scale/collaboration/problem_solving",
        "star_data": {{
          "situation_zh": "项目背景+商业价值（中文）：必须说明为什么要做这个项目、解决什么业务问题、给谁用",
          "situation_en": "Project context + business value (English): Must explain why this project was needed, what business problem it solved, who it was for",
          "task_zh": "具体职责（中文）：你在项目中的角色和任务",
          "task_en": "Your role (English): Your specific role and responsibilities in the project",
          "action_zh": "具体行动（中文）",
          "action_en": "Specific actions taken (English)",
          "tech_details_zh": "技术实现细节（中文）：具体使用了什么技术、怎么用的、为什么选这个技术、解决了什么技术问题",
          "tech_details_en": "Technical implementation details (English): What technologies were used, how they were applied, why they were chosen, what technical problems they solved",
          "result_quantified": "量化结果 / Quantified results (if available)",
          "result_qualitative_zh": "定性结果（中文）",
          "result_qualitative_en": "Qualitative results (English)"
        }},
        "tech_stack": [
          {{
            "name": "技术名称 / Technology name",
            "role": "primary/infrastructure/tool",
            "usage": "具体用途描述 / Specific usage description"
          }}
        ],
        "keywords": ["关键词/keyword1", "关键词/keyword2"]
      }}
    ]
  }}
}}

STAR 法则说明 / STAR Method Explanation:
- S (Situation): 必须包含商业价值/业务目的，解释项目为什么存在
  Must include business value/purpose, explain why the project exists
  示例/Example: "为了解决客户投诉响应慢的问题" / "To address slow customer complaint response times"
- T (Task): 你的具体角色和职责
  Your specific role and responsibilities
- A (Action): 你做了什么 + 技术栈的具体使用方式
  What you did + specific tech stack usage details
- R (Result): 量化成果或清晰的定性影响
  Quantified outcomes or clear qualitative impact

Bullet 类型说明 / Bullet type descriptions:
- business_impact: 直接业务价值 / Direct business value (revenue, efficiency, cost)
- technical_design: 架构设计、技术选型 / Architecture design, technology selection
- implementation: 功能实现、代码开发 / Feature implementation, code development
- scale: 规模、性能、可扩展性 / Scale, performance, scalability
- collaboration: 团队协作、跨部门合作 / Team collaboration, cross-department cooperation
- problem_solving: 解决难题、排查问题 / Solving challenges, troubleshooting

提取规则 / Extraction rules:
1. raw_text_zh 和 raw_text_en 必须都填写，用专业简历语言重写
   Both raw_text_zh and raw_text_en are required, rewrite in professional resume language
2. 每个独立的成果/项目应该是一个单独的 bullet
   Each independent achievement/project should be a separate bullet
3. 如果对话中提到多个不同的成果，都要提取
   If multiple achievements are mentioned, extract all of them
4. 技术栈要从对话中提取实际提到的技术，并说明具体用途
   Extract tech stack from technologies actually mentioned, with specific usage descriptions
5. 日期如果只有年月，用该月1日（如 2023-09-01）
   If date only has year and month, use the 1st of that month
6. situation 必须包含商业价值，不能只是泛泛的"需要处理数据"，而是"为了解决XX业务问题"
   situation MUST include business value, not just vague "needed to process data", but "to solve XX business problem"
7. tech_details 必须说明技术怎么用的，不能只列技术名称
   tech_details MUST explain how technologies were used, not just list names"""

EXTRACTION_SYSTEM_BILINGUAL = """你是一个双语简历数据提取专家，擅长从对话中提取结构化的职业经历信息，并生成中英文双语版本。
You are a bilingual resume data extraction expert, skilled at extracting structured career experience information and generating both Chinese and English versions.

你的输出必须是有效的 JSON，不要包含任何解释或 markdown 格式。
Your output must be valid JSON, without any explanation or markdown formatting.

重要：raw_text_zh 必须是纯中文，raw_text_en 必须是纯英文。
Important: raw_text_zh must be in Chinese only, raw_text_en must be in English only."""


def get_extraction_prompt(language: str) -> tuple[str, str]:
    """Get extraction prompt and system message.

    Now always returns bilingual prompt regardless of language setting.
    """
    return EXTRACTION_PROMPT_BILINGUAL, EXTRACTION_SYSTEM_BILINGUAL


async def extract_experience_from_conversation(
    session: ChatSession,
    claude: Claude,
) -> OrganizeResult:
    """Extract structured experience data from conversation.

    Args:
        session: The chat session containing the conversation
        claude: Claude client for extraction

    Returns:
        OrganizeResult with extracted experience and confirmation message
    """
    conversation_text = _get_recent_conversation(session)

    # Get bilingual extraction prompts
    prompt_template, system_prompt = get_extraction_prompt(session.language)
    prompt = prompt_template.format(conversation=conversation_text)

    result = await claude.extract_json(
        prompt=prompt,
        model=Model.SONNET,  # Use Sonnet for better extraction quality
        system=system_prompt,
    )

    # Parse the extracted data
    exp_data = result.get("experience", {})

    bullets = []
    for b in exp_data.get("bullets", []):
        # Get bilingual text
        raw_text_zh = b.get("raw_text_zh", "")
        raw_text_en = b.get("raw_text_en", "")

        # Primary text based on conversation language
        raw_text = raw_text_zh if session.language == "zh" else raw_text_en

        bullets.append(ExtractedBullet(
            raw_text=raw_text,
            raw_text_zh=raw_text_zh,
            raw_text_en=raw_text_en,
            type=b.get("type", "implementation"),
            star_data=b.get("star_data", {}),
            tech_stack=b.get("tech_stack", []),
            keywords=b.get("keywords", []),
        ))

    experience = ExtractedExperience(
        company=exp_data.get("company", "Unknown"),
        title=exp_data.get("title", ""),
        location=exp_data.get("location"),
        start_date=exp_data.get("start_date"),
        end_date=exp_data.get("end_date"),
        bullets=bullets,
    )

    # Generate message in appropriate language
    if session.language == "en":
        message = f"Organized experience at {experience.company} with {len(bullets)} highlights."
    else:
        message = f"已整理 {experience.company} 的经历，包含 {len(bullets)} 条亮点。"

    return OrganizeResult(
        experience=experience,
        message=message,
    )


def _parse_date(date_str: str | None) -> date | None:
    """Parse date string to date object."""
    if not date_str:
        return None
    try:
        # Handle YYYY-MM-DD
        if len(date_str) == 10:
            return date.fromisoformat(date_str)
        # Handle YYYY-MM
        if len(date_str) == 7:
            return date.fromisoformat(f"{date_str}-01")
        # Handle YYYY
        if len(date_str) == 4:
            return date.fromisoformat(f"{date_str}-01-01")
    except ValueError:
        pass
    return None


def _map_bullet_type(type_str: str) -> BulletType:
    """Map string type to BulletType enum."""
    mapping = {
        "business_impact": BulletType.BUSINESS_IMPACT,
        "technical_design": BulletType.TECHNICAL_DESIGN,
        "implementation": BulletType.IMPLEMENTATION,
        "scale": BulletType.SCALE,
        "collaboration": BulletType.COLLABORATION,
        "problem_solving": BulletType.PROBLEM_SOLVING,
    }
    return mapping.get(type_str.lower(), BulletType.IMPLEMENTATION)


async def save_extracted_experience(
    result: OrganizeResult,
    storage: DataStorage,
    profile_id: UUID,
    user_id: str = "local",
) -> dict[str, Any]:
    """Save extracted experience and bullets to storage.

    Args:
        result: The extraction result
        storage: Data storage instance
        profile_id: Profile ID to associate with
        user_id: User ID

    Returns:
        Dict with saved experience info
    """
    exp_data = result.experience

    # Create Experience
    experience = Experience(
        user_id=user_id,
        profile_id=profile_id,
        company_en=exp_data.company,
        title_en=exp_data.title,
        location_en=exp_data.location,
        start_date=_parse_date(exp_data.start_date),
        end_date=_parse_date(exp_data.end_date),
    )
    await storage.save_experience(experience)

    # Create Bullets with bilingual content stored in star_data
    saved_bullets = []
    for i, b in enumerate(exp_data.bullets):
        # Merge bilingual text into star_data for storage
        star_data_with_bilingual = {
            **b.star_data,
            "raw_text_zh": b.raw_text_zh,
            "raw_text_en": b.raw_text_en,
        }

        bullet = Bullet(
            user_id=user_id,
            experience_id=experience.id,
            type=_map_bullet_type(b.type),
            priority=i + 1,
            content_en=b.raw_text_en,
            content_zh=b.raw_text_zh,
            raw_text=b.raw_text,  # Primary text in conversation language
            star_data=star_data_with_bilingual,
            tech_stack=b.tech_stack,
            jd_keywords=b.keywords,
            confidence=Confidence.HIGH,
        )
        await storage.save_bullet(bullet)
        saved_bullets.append({
            "id": str(bullet.id),
            "raw_text": bullet.raw_text,
            "raw_text_zh": b.raw_text_zh,
            "raw_text_en": b.raw_text_en,
            "type": bullet.type.value,
        })

    return {
        "experience_id": str(experience.id),
        "company": experience.company_en,
        "title": experience.title_en,
        "bullets_count": len(saved_bullets),
        "bullets": saved_bullets,
    }


class Organizer:
    """Handles the organize flow when [ORGANIZE] marker is detected."""

    def __init__(self, claude: Claude, storage: DataStorage):
        self.claude = claude
        self.storage = storage

    async def process(
        self,
        session: ChatSession,
        profile_id: UUID,
        user_id: str = "local",
    ) -> dict[str, Any]:
        """Process the organize flow.

        1. Extract structured data from conversation
        2. Save to storage
        3. Return saved info

        Args:
            session: The chat session
            profile_id: Profile ID to save under
            user_id: User ID

        Returns:
            Dict with saved experience info
        """
        # Extract structured data
        result = await extract_experience_from_conversation(session, self.claude)

        # Save to storage
        saved = await save_extracted_experience(
            result,
            self.storage,
            profile_id,
            user_id,
        )

        # Update session focus
        session.current_focus = ""

        return {
            "message": result.message,
            "saved": saved,
        }
