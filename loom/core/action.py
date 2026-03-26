"""Base Action interface - receives final Context, produces side effects."""

from abc import ABC, abstractmethod
from typing import Any

from loom.core.context import PipelineContext


class Action(ABC):
    """Base class for all Actions.

    An Action receives final Context and produces side effects.
    Actions are the end of a workflow: store, send, export, notify.
    """

    name: str = "base_action"
    description: str = ""

    @abstractmethod
    async def execute(self, context: PipelineContext) -> Any:
        """Execute the action.

        Args:
            context: The final pipeline context

        Returns:
            Action-specific result (e.g., file path, message ID, URL)
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self.name}>"


class ActionError(Exception):
    """Base exception for action failures."""

    def __init__(self, action_name: str, message: str, retryable: bool = False):
        self.action_name = action_name
        self.message = message
        self.retryable = retryable
        super().__init__(f"[{action_name}] {message}")
