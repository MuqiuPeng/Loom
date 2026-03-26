"""Claude API client wrapper."""

import json
import os
from enum import Enum

from anthropic import AsyncAnthropic
from pydantic import BaseModel


class Model(str, Enum):
    """Available Claude models.

    Use Haiku for high-frequency, low-reasoning tasks (extraction, matching).
    Use Sonnet for generation, reasoning, and conversation.
    """

    HAIKU = "claude-haiku-4-5-20251001"
    SONNET = "claude-sonnet-4-20250514"


class Claude:
    """Async Claude API client.

    Claude handles reasoning, Python handles flow.
    API key is read from ANTHROPIC_API_KEY environment variable.
    """

    def __init__(self, api_key: str | None = None):
        self.client = AsyncAnthropic(
            api_key=api_key or os.getenv("ANTHROPIC_API_KEY")
        )

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
        messages = [{"role": "user", "content": prompt}]

        response = await self.client.messages.create(
            model=model.value,
            max_tokens=max_tokens,
            system=system or "",
            messages=messages,
        )

        return response.content[0].text

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
        extraction_system = f"""{system or ''}

You must respond with valid JSON only.
No markdown code blocks, no explanation, just the JSON object.""".strip()

        response = await self.complete(
            prompt=prompt,
            model=model,
            system=extraction_system,
            max_tokens=4096,
        )

        # Clean response - remove markdown if present
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines (```json and ```)
            text = "\n".join(lines[1:-1])

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON response: {e}\nResponse: {text}")
