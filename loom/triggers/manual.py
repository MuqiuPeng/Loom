"""ManualTrigger - simplest trigger for direct user input."""

from typing import Any
from uuid import uuid4

from loom.core.context import PipelineContext
from loom.core.trigger import Trigger
from loom.core.trigger_registry import trigger_registry


class ManualTrigger(Trigger):
    """Manual trigger - receives user data directly to start a workflow.

    The simplest trigger type. Used for:
    - CLI invocations
    - API calls
    - Testing pipelines

    Does not involve any external systems.
    """

    @property
    def name(self) -> str:
        return "manual"

    def __init__(self, user_id: str = "local"):
        self.user_id = user_id
        self._data: dict[str, Any] = {}

    def set_data(self, data: dict[str, Any]) -> "ManualTrigger":
        """Set the data to include in the emitted context.

        Args:
            data: Data dict to pass to the workflow

        Returns:
            self for chaining
        """
        self._data = data
        return self

    async def emit(self) -> PipelineContext:
        """Emit a PipelineContext with the provided data.

        Returns:
            New PipelineContext with workflow_id and user data
        """
        workflow_id = str(uuid4())

        return PipelineContext(
            user_id=self.user_id,
            workflow_id=workflow_id,
            data=self._data.copy(),
        )


# Register trigger
trigger_registry.register("manual", ManualTrigger)
