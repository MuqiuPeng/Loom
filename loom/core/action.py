"""Action interface - receives final Context, produces side effects."""

from abc import ABC, abstractmethod
from typing import Any

from loom.core.context import PipelineContext


class Action(ABC):
    """An Action receives final Context and produces side effects.

    Examples: store to DB, send email, export PDF, notify chat.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this action."""
        ...

    @abstractmethod
    async def execute(self, context: PipelineContext) -> Any:
        """Execute the action.

        Args:
            context: The final pipeline context

        Returns:
            Action-specific result (file path, message ID, URL, etc.)
        """
        ...
