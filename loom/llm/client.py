"""Claude API client wrapper."""

import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from anthropic import AsyncAnthropic
from pydantic import BaseModel

if TYPE_CHECKING:
    from loom.storage.repository import DataStorage


class Model(str, Enum):
    """Available Claude models.

    Use Haiku for high-frequency, low-reasoning tasks (extraction, matching).
    Use Sonnet for generation, reasoning, and conversation.
    """

    HAIKU = "claude-haiku-4-5-20251001"
    SONNET = "claude-sonnet-4-20250514"


@dataclass
class CompletionResult:
    """Result of a Claude API call with usage information."""

    text: str
    input_tokens: int
    output_tokens: int
    model: str

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class Claude:
    """Async Claude API client with usage tracking.

    Claude handles reasoning, Python handles flow.
    API key is read from ANTHROPIC_API_KEY environment variable.

    Usage tracking:
        - Set storage via set_storage() to enable persistent tracking
        - Set workflow context via set_context() for aggregation
    """

    def __init__(self, api_key: str | None = None):
        self.client = AsyncAnthropic(
            api_key=api_key or os.getenv("ANTHROPIC_API_KEY")
        )
        self._storage: "DataStorage | None" = None
        self._workflow_run_id: UUID | None = None
        self._step_name: str | None = None
        self._user_id: str = "local"

    def set_storage(self, storage: "DataStorage") -> "Claude":
        """Set storage backend for usage tracking. Returns self for chaining."""
        self._storage = storage
        return self

    def set_context(
        self,
        workflow_run_id: UUID | None = None,
        step_name: str | None = None,
        user_id: str = "local",
    ) -> "Claude":
        """Set workflow context for usage aggregation. Returns self for chaining."""
        self._workflow_run_id = workflow_run_id
        self._step_name = step_name
        self._user_id = user_id
        return self

    def clear_context(self) -> "Claude":
        """Clear workflow context. Returns self for chaining."""
        self._workflow_run_id = None
        self._step_name = None
        return self

    async def _record_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        caller: str = "complete",
    ) -> None:
        """Record token usage to storage if available."""
        if not self._storage:
            return

        from loom.storage.usage import TokenUsage

        usage = TokenUsage.create(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            workflow_run_id=self._workflow_run_id,
            step_name=self._step_name,
            caller=caller,
            user_id=self._user_id,
        )
        await self._storage.save_token_usage(usage)

    async def complete(
        self,
        prompt: str,
        *,
        model: Model = Model.SONNET,
        system: str | None = None,
        max_tokens: int = 4096,
    ) -> str:
        """Get a text completion from Claude.

        Args:
            prompt: The user message
            model: Which model to use
            system: Optional system prompt
            max_tokens: Maximum tokens in response

        Returns:
            The assistant's response text
        """
        result = await self.complete_with_usage(
            prompt=prompt,
            model=model,
            system=system,
            max_tokens=max_tokens,
        )
        return result.text

    async def complete_with_usage(
        self,
        prompt: str,
        *,
        model: Model = Model.SONNET,
        system: str | None = None,
        max_tokens: int = 4096,
    ) -> CompletionResult:
        """Get a text completion with detailed usage information.

        Args:
            prompt: The user message
            model: Which model to use
            system: Optional system prompt
            max_tokens: Maximum tokens in response

        Returns:
            CompletionResult with text and token counts
        """
        messages = [{"role": "user", "content": prompt}]

        response = await self.client.messages.create(
            model=model.value,
            max_tokens=max_tokens,
            system=system or "",
            messages=messages,
        )

        result = CompletionResult(
            text=response.content[0].text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=model.value,
        )

        # Record usage if storage is configured
        await self._record_usage(
            model=model.value,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            caller="complete",
        )

        # Log the API call
        try:
            from loom.services.logger import logger
            await logger.info(
                "claude_api", "complete",
                f"Claude {model.value} call completed",
                model=model.value,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                total_tokens=result.total_tokens,
                system_prompt=system or "",
                prompt=prompt,
                response=result.text,
                step_name=self._step_name,
                workflow_run_id=str(self._workflow_run_id) if self._workflow_run_id else None,
            )
        except Exception:
            pass  # never let logging break the main flow

        return result

    async def extract_json(
        self,
        prompt: str,
        *,
        model: Model = Model.HAIKU,
        system: str | None = None,
    ) -> dict:
        """Extract structured JSON data from Claude.

        Args:
            prompt: The user message with content to extract from
            model: Which model to use (default Haiku for extraction)
            system: Optional system prompt

        Returns:
            Parsed JSON dict

        Raises:
            ValueError: If response is not valid JSON
        """
        result = await self.extract_json_with_usage(
            prompt=prompt,
            model=model,
            system=system,
        )
        return result[0]

    async def extract_json_with_usage(
        self,
        prompt: str,
        *,
        model: Model = Model.HAIKU,
        system: str | None = None,
    ) -> tuple[dict, CompletionResult]:
        """Extract structured JSON data with usage information.

        Args:
            prompt: The user message with content to extract from
            model: Which model to use (default Haiku for extraction)
            system: Optional system prompt

        Returns:
            Tuple of (parsed JSON dict, CompletionResult)

        Raises:
            ValueError: If response is not valid JSON
        """
        extraction_system = f"""{system or ''}

You must respond with valid JSON only.
No markdown code blocks, no explanation, just the JSON object.""".strip()

        result = await self.complete_with_usage(
            prompt=prompt,
            model=model,
            system=extraction_system,
            max_tokens=4096,
        )

        # Clean response - remove markdown if present
        text = result.text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])

        parsed = self._robust_json_parse(text)
        return parsed, result

    @staticmethod
    def _robust_json_parse(text: str) -> dict:
        """Parse JSON with multiple fallback strategies."""
        # 1. Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 2. Extract first complete JSON object using brace matching
        try:
            start = text.index("{")
            depth = 0
            in_string = False
            escape_next = False
            for i in range(start, len(text)):
                c = text[i]
                if escape_next:
                    escape_next = False
                    continue
                if c == "\\":
                    escape_next = True
                    continue
                if c == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start : i + 1]
                        return json.loads(candidate)
        except (ValueError, json.JSONDecodeError):
            pass

        # 3. Try json_repair library
        try:
            import json_repair
            repaired = json_repair.repair_json(text, return_objects=True)
            if isinstance(repaired, dict):
                return repaired
        except Exception:
            pass

        # 4. Strip control characters and retry
        try:
            import re
            cleaned = re.sub(r"[\x00-\x1f\x7f]", " ", text)
            start = cleaned.index("{")
            end = cleaned.rindex("}") + 1
            return json.loads(cleaned[start:end])
        except (ValueError, json.JSONDecodeError):
            pass

        raise ValueError(f"Failed to parse JSON after all strategies. First 300 chars: {text[:300]}")
