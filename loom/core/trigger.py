"""Trigger interface - emits a PipelineContext to start a workflow."""

from abc import ABC, abstractmethod

from loom.core.context import PipelineContext


class Trigger(ABC):
    """A Trigger emits a PipelineContext to start a workflow.

    Examples: manual invocation, scheduled cron, email received, git hook.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this trigger."""
        ...

    @abstractmethod
    async def emit(self) -> PipelineContext:
        """Emit a context to start a workflow.

        Returns:
            A new PipelineContext to begin the pipeline
        """
        ...
