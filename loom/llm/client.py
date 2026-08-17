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
    SONNET = "claude-sonnet-5"


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
        self._storage: DataStorage | None = None
        self._workflow_run_id: UUID | None = None
        self._step_name: str | None = None
        self._user_id: str = "local"

    @classmethod
    def tracked(cls, step_name: str | None = None) -> "Claude":
        """A client whose usage actually gets recorded.

        `Claude()` on its own silently discards usage: _record_usage returns
        early when no storage is attached, and only the resume-tailor steps
        ever called set_storage. Everything built later — site harvesting,
        demo generation, outreach drafts — was therefore invisible in the
        token totals, which matters most for demo generation because it is
        the most expensive call in the product.

        `step_name` is what separates those callers in the usage table.
        """
        client = cls()
        try:
            from loom.api import get_storage

            client.set_storage(get_storage())
        except Exception:
            # Usage tracking must never be the reason a generation fails.
            return client
        if step_name:
            client.set_context(step_name=step_name)
        return client

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
        max_tokens: int = 8192,
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
        max_tokens: int = 8192,
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

        # Claude Sonnet 5 runs adaptive thinking by default; max_tokens caps
        # thinking + response text together. These pipeline calls are structured
        # extraction tasks, so cap effort at "medium" to keep thinking spend
        # from starving the text output.
        kwargs: dict = {}
        if model is Model.SONNET:
            kwargs["output_config"] = {"effort": "medium"}

        response = await self.client.messages.create(
            model=model.value,
            max_tokens=max_tokens,
            system=system or "",
            messages=messages,
            **kwargs,
        )

        # Reasoning models may emit thinking blocks before the text block
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )

        result = CompletionResult(
            text=text,
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

    async def extract_model(
        self,
        prompt: str,
        schema: type["BaseModel"],
        *,
        model: Model = Model.HAIKU,
        system: str | None = None,
        max_tokens: int = 8192,
        retries: int = 1,
    ) -> "BaseModel":
        """Return an instance of `schema`, or raise.

        extract_json asks the model nicely for JSON and parses whatever comes
        back, so a missing field or a string where a list belongs degrades to
        an empty value that every caller then has to guard against with .get().
        The failure is silent, which is the wrong shape for a pipeline step —
        a menu that came back malformed should say so, not look like a shop
        with no menu.

        Here the Pydantic model is turned into a tool schema and the tool call
        is forced, so the API itself constrains the shape; the result is then
        validated, and a validation error is handed back for one retry rather
        than swallowed.
        """
        from pydantic import ValidationError

        tool = {
            "name": "record",
            "description": f"Record the extracted {schema.__name__}.",
            "input_schema": schema.model_json_schema(),
        }
        messages: list[dict] = [{"role": "user", "content": prompt}]

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            response = await self.client.messages.create(
                model=model.value,
                max_tokens=max_tokens,
                system=system or "",
                messages=messages,
                tools=[tool],
                tool_choice={"type": "tool", "name": "record"},
            )
            await self._record_usage(
                model.value,
                response.usage.input_tokens,
                response.usage.output_tokens,
                caller="extract_model",
            )

            payload = next(
                (b.input for b in response.content if getattr(b, "type", "") == "tool_use"),
                None,
            )
            if payload is None:
                last_error = ValueError("model returned no tool call")
                continue

            try:
                return schema.model_validate(payload)
            except ValidationError as e:
                last_error = e
                if attempt == retries:
                    break
                # Hand the model its own output and the complaint about it.
                messages += [
                    {"role": "assistant", "content": [
                        {"type": "tool_use", "id": "retry", "name": "record",
                         "input": payload}
                    ]},
                    {"role": "user", "content": [
                        {"type": "tool_result", "tool_use_id": "retry",
                         "is_error": True,
                         "content": f"That didn't validate: {e}. Correct it."}
                    ]},
                ]

        raise ValueError(f"could not extract {schema.__name__}: {last_error}")

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
            max_tokens=8192,
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
