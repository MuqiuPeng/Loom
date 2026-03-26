"""Base Step interface - receives Context, runs logic, returns updated Context."""

from abc import ABC, abstractmethod

from loom.core.context import PipelineContext


class Step(ABC):
    """Base class for all Steps in the pipeline.

    A Step receives Context, runs logic, and returns updated Context.
    Steps are stateless - all persistence goes through Storage.

    Design principle: One Step, one responsibility.
    If you find yourself writing "and" in a Step's description, split it.
    """

    name: str = "base_step"
    description: str = ""

    @abstractmethod
    async def run(self, context: PipelineContext) -> PipelineContext:
        """Execute the step logic.

        Args:
            context: The pipeline context with current state

        Returns:
            Updated pipeline context

        Raises:
            StepError: If the step fails in an expected way
        """
        ...

    async def validate(self, context: PipelineContext) -> bool:
        """Validate that the context has required data for this step.

        Override this method to add validation logic.
        """
        return True

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self.name}>"


class StepError(Exception):
    """Base exception for step failures."""

    def __init__(self, step_name: str, message: str, recoverable: bool = False):
        self.step_name = step_name
        self.message = message
        self.recoverable = recoverable
        super().__init__(f"[{step_name}] {message}")
