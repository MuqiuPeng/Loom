"""Step interface - receives Context, returns updated Context."""

from abc import ABC, abstractmethod

from loom.core.context import PipelineContext


class Step(ABC):
    """A Step receives Context, runs logic, and returns updated Context.

    Design principle: One Step, one responsibility.
    If you find yourself writing "and" in a Step's description, split it.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this step."""
        ...

    @abstractmethod
    async def run(self, context: PipelineContext) -> PipelineContext:
        """Execute the step logic.

        Args:
            context: The pipeline context with current state

        Returns:
            Updated pipeline context
        """
        ...
