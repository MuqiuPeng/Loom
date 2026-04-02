"""Chat session management with context compression."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from loom.llm.client import Claude, Model


class ChatMessage(BaseModel):
    """A single chat message."""

    role: str = Field(..., description="'user' or 'assistant'")
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatSession(BaseModel):
    """Manages a chat conversation with context compression.

    Context compression triggers every 20 turns to keep the context window
    manageable while preserving important information.
    """

    session_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str = Field(default="local")
    language: str = Field(default="zh", description="'zh' or 'en'")
    messages: list[ChatMessage] = Field(default_factory=list)
    summary: str = Field(default="", description="Compressed summary of older messages")
    turn_count: int = Field(default=0)
    current_focus: str = Field(default="", description="What we're currently collecting")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Compression settings
    compression_threshold: int = Field(default=20, description="Compress every N turns")
    keep_recent_turns: int = Field(default=10, description="Keep N most recent turns")

    def add_user_message(self, content: str) -> ChatMessage:
        """Add a user message to the session."""
        msg = ChatMessage(role="user", content=content)
        self.messages.append(msg)
        self.turn_count += 1
        self.updated_at = datetime.utcnow()
        return msg

    def add_assistant_message(self, content: str) -> ChatMessage:
        """Add an assistant message to the session."""
        msg = ChatMessage(role="assistant", content=content)
        self.messages.append(msg)
        self.updated_at = datetime.utcnow()
        return msg

    def should_compress(self) -> bool:
        """Check if context compression should be triggered."""
        return self.turn_count > 0 and self.turn_count % self.compression_threshold == 0

    async def compress_context(self, claude: Claude) -> str:
        """Compress older messages into a summary.

        Keeps the most recent messages and summarizes the rest.

        Returns:
            The new summary
        """
        if len(self.messages) <= self.keep_recent_turns * 2:
            return self.summary

        # Messages to compress (older ones)
        messages_to_compress = self.messages[: -self.keep_recent_turns * 2]
        recent_messages = self.messages[-self.keep_recent_turns * 2 :]

        # Build conversation text for summarization
        conversation_text = ""
        for msg in messages_to_compress:
            if self.language == "en":
                role_label = "User" if msg.role == "user" else "Advisor"
            else:
                role_label = "用户" if msg.role == "user" else "顾问"
            conversation_text += f"{role_label}: {msg.content}\n\n"

        # Include existing summary if any
        if self.language == "en":
            existing_context = f"Previous summary:\n{self.summary}\n\n" if self.summary else ""
            prompt = f"""{existing_context}Conversation transcript:

{conversation_text}

Please summarize the key information collected in this conversation concisely, including:
1. Experiences shared by the candidate (company, time, main work)
2. Tech stack mentioned
3. Quantified achievements
4. Current topic being discussed

Example format:
Candidate has provided:
- Kaihua Software (2023.9-12): Web scraping system, processed 20K documents, using Lambda+S3
- Meituan internship: Currently collecting

Current focus: Specific work content at Meituan internship"""
            system = "You are a conversation summarization assistant, summarizing key information concisely and accurately."
        else:
            existing_context = f"之前的摘要：\n{self.summary}\n\n" if self.summary else ""
            prompt = f"""{existing_context}以下是对话记录：

{conversation_text}

请用简洁的中文总结这段对话中收集到的关键信息，包括：
1. 候选人已分享的经历（公司、时间、主要工作）
2. 提到的技术栈
3. 量化成果
4. 当前正在讨论的话题

输出格式示例：
候选人已提供：
- Kaihua Software (2023.9-12)：爬虫系统，处理2万份文档，使用 Lambda+S3
- Meituan 实习：正在收集中

当前焦点：Meituan 实习的具体工作内容"""
            system = "你是一个对话摘要助手，用简洁准确的方式总结对话中的关键信息。"

        new_summary = await claude.complete(
            prompt=prompt,
            model=Model.HAIKU,
            system=system,
            max_tokens=1024,
        )

        self.summary = new_summary.strip()
        self.messages = recent_messages
        self.updated_at = datetime.utcnow()

        return self.summary

    def get_messages_for_api(self) -> list[dict[str, str]]:
        """Get messages formatted for Claude API.

        Returns:
            List of message dicts with 'role' and 'content'
        """
        return [{"role": m.role, "content": m.content} for m in self.messages]

    def get_context_for_system_prompt(self, existing_experiences: list[dict] | None = None) -> str:
        """Get dynamic context to inject into system prompt.

        Args:
            existing_experiences: Brief list of experiences already in profile

        Returns:
            Formatted context string
        """
        parts = []
        is_en = self.language == "en"

        if self.summary:
            label = "Current collected information summary:" if is_en else "当前已收集信息摘要："
            parts.append(f"{label}\n{self.summary}")

        if self.current_focus:
            label = "Current collection focus:" if is_en else "当前收集焦点："
            parts.append(f"{label}{self.current_focus}")

        if existing_experiences:
            exp_list = []
            for exp in existing_experiences:
                exp_str = f"- {exp.get('company', 'Unknown')} ({exp.get('title', '')})"
                if exp.get("start_date"):
                    exp_str += f" {exp['start_date']}"
                    if exp.get("end_date"):
                        exp_str += f" - {exp['end_date']}"
                exp_list.append(exp_str)
            if exp_list:
                label = "Candidate's existing experiences:" if is_en else "候选人已有的经历："
                parts.append(f"{label}\n" + "\n".join(exp_list))

        return "\n\n".join(parts)


# System prompt templates - bilingual
CHAT_SYSTEM_PROMPT_ZH = """你是一个职业顾问，通过对话帮用户挖掘经历亮点。
目标不是收集信息，而是发现用户自己没意识到的价值。

【重要】语言要求：
- 你必须全程使用中文与用户对话
- 即使用户用英文提问，也请用中文回复
- 所有问题、反馈、确认都使用中文

追问规则（按优先级排序）：
1. 缺少项目背景/商业价值 → 追问目的（"这个项目是要解决什么业务问题？为什么要做这个？"）
   - 简历第一句话必须体现项目的商业价值或业务场景
   - 例如：用户说"做了一个爬虫系统"，要追问"这个爬虫系统是给谁用的？要解决什么业务需求？"
2. 被动语态 → 追问具体贡献（"你具体负责了什么？"）
3. 有规模词无数字 → 追问量化（"大概处理了多少数据/用户？"）
4. 技术决策一句带过 → 追问选型理由和细节
   - 不仅问"为什么选择这个技术"，还要问"这个技术具体怎么用的？解决了什么技术难题？"
   - 例如：用户说"用了 Lambda"，要追问"Lambda 在这个场景下具体怎么用的？有什么技术上的考量？"
5. 提到挑战未展开 → 追问解决过程（"遇到了什么困难？怎么解决的？"）
- 每次只问一个问题，不要连续追问多个问题
- 信息足够时不要为了追问而追问，可以确认并进入下一话题

必须收集的信息（STAR法则）：
- S（情境）：项目背景 + 商业价值/业务目的（为什么要做这个项目？给谁用？解决什么问题？）
- T（任务）：你的角色和具体职责
- A（行动）：具体做了什么 + 技术栈细节（用了什么技术？怎么用的？为什么选这个技术？）
- R（结果）：量化成果或定性影响

阶段判断：
当你认为一段经历的信息已经足够完整时（必须同时满足以下条件），在回复末尾加上特殊标记：[ORGANIZE]
✓ 有明确的项目背景和商业价值/业务目的
✓ 有具体的技术栈及其使用细节
✓ 有具体行动和个人贡献
✓ 有量化结果或清晰的定性结果
不要向用户解释这个标记，也不要在回复中提及它。

对话风格：
- 友好但专业
- 鼓励用户分享细节
- 适时给予正向反馈"""

CHAT_SYSTEM_PROMPT_EN = """You are a career advisor helping users discover highlights in their experiences through conversation.
The goal is not just to collect information, but to help users discover value they might not have realized themselves.

【IMPORTANT】Language requirement:
- You MUST communicate entirely in English
- Even if the user asks in Chinese, please respond in English
- All questions, feedback, and confirmations should be in English

Follow-up rules (in priority order):
1. Missing project context/business value → Ask about purpose ("What business problem was this project solving? Why was it needed?")
   - The first sentence of a resume bullet must reflect business value or context
   - Example: If user says "built a web scraping system", ask "Who was this system for? What business need did it address?"
2. Passive voice → Ask about specific contributions ("What exactly were you responsible for?")
3. Scale words without numbers → Ask for quantification ("Approximately how much data/users did you handle?")
4. Technical decisions mentioned briefly → Ask about selection reasoning AND implementation details
   - Not just "why this technology" but also "how did you use it? What technical challenges did it solve?"
   - Example: If user says "used Lambda", ask "How exactly did you use Lambda in this scenario? What were the technical considerations?"
5. Challenges mentioned without elaboration → Ask about the resolution process ("What difficulties did you encounter? How did you solve them?")
- Ask only one question at a time, don't ask multiple consecutive questions
- When information is sufficient, don't ask follow-ups just for the sake of it; confirm and move to the next topic

Required information (STAR method):
- S (Situation): Project background + business value/purpose (Why was this project needed? Who was it for? What problem did it solve?)
- T (Task): Your role and specific responsibilities
- A (Action): What you did + tech stack details (What technologies? How did you use them? Why those choices?)
- R (Result): Quantified outcomes or qualitative impact

Stage determination:
When you believe an experience's information is sufficiently complete (must satisfy ALL of the following), add a special marker at the end of your response: [ORGANIZE]
✓ Has clear project background and business value/purpose
✓ Has specific tech stack with implementation details
✓ Has specific actions and personal contributions
✓ Has quantified results or clear qualitative outcomes
Do not explain this marker to the user or mention it in your response.

Conversation style:
- Friendly but professional
- Encourage users to share details
- Provide timely positive feedback"""


def build_system_prompt(session: ChatSession, existing_experiences: list[dict] | None = None) -> str:
    """Build the full system prompt with static and dynamic parts.

    Args:
        session: The current chat session
        existing_experiences: Brief list of experiences already in profile

    Returns:
        Complete system prompt
    """
    print(f"[build_system_prompt] Session language: {session.language}")
    static_prompt = CHAT_SYSTEM_PROMPT_EN if session.language == "en" else CHAT_SYSTEM_PROMPT_ZH
    print(f"[build_system_prompt] Using {'ENGLISH' if session.language == 'en' else 'CHINESE'} prompt")
    dynamic_context = session.get_context_for_system_prompt(existing_experiences)

    if dynamic_context:
        return f"{static_prompt}\n\n---\n\n{dynamic_context}"
    return static_prompt


class SessionStore:
    """In-memory session store.

    TODO: Replace with Redis or database persistence for production.
    """

    def __init__(self):
        self._sessions: dict[str, ChatSession] = {}

    def get(self, session_id: str) -> ChatSession | None:
        """Get a session by ID."""
        return self._sessions.get(session_id)

    def create(self, user_id: str = "local", language: str = "zh") -> ChatSession:
        """Create a new session."""
        session = ChatSession(user_id=user_id, language=language)
        self._sessions[session.session_id] = session
        return session

    def get_or_create(
        self, session_id: str | None, user_id: str = "local", language: str = "zh"
    ) -> ChatSession:
        """Get existing session or create new one."""
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]
        return self.create(user_id, language)

    def save(self, session: ChatSession) -> None:
        """Save/update a session."""
        self._sessions[session.session_id] = session

    def delete(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def list_sessions(self, user_id: str = "local") -> list[ChatSession]:
        """List all sessions for a user."""
        return [s for s in self._sessions.values() if s.user_id == user_id]


# Global session store instance
session_store = SessionStore()
