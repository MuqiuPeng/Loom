"""Base Trigger interface - emits a PipelineContext to start a workflow."""

from abc import ABC, abstractmethod
from typing import AsyncIterator

from loom.core.context import PipelineContext


class Trigger(ABC):
    """Base class for all Triggers.

    A Trigger emits a PipelineContext to start a workflow.
    Triggers can be: manual, scheduled, email-received, git-hook, etc.
    """

    name: str = "base_trigger"
    description: str = ""

    @abstractmethod
    async def emit(self) -> PipelineContext:
        """Emit a single context to start a workflow.

        Returns:
            A new PipelineContext to start the workflow
        """
        ...

    async def listen(self) -> AsyncIterator[PipelineContext]:
        """Listen for events and yield contexts.

        For triggers that can fire multiple times (e.g., email listener),
        override this method to yield contexts as events occur.

        Default implementation just emits once.
        """
        yield await self.emit()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self.name}>"


class ManualTrigger(Trigger):
    """A trigger that is invoked manually with optional initial data."""

    name: str = "manual"
    description: str = "Manually triggered workflow"

    def __init__(self, initial_data: dict | None = None, user_id: str = "default"):
        self.initial_data = initial_data or {}
        self.user_id = user_id

    async def emit(self) -> PipelineContext:
        return PipelineContext(
            user_id=self.user_id,
            data=self.initial_data,
        )
