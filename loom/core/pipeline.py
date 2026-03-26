"""Workflow orchestration - composes Triggers, Steps, and Actions."""

from dataclasses import dataclass, field
from typing import Any

from loom.core.action import Action, ActionError
from loom.core.context import PipelineContext
from loom.core.step import Step, StepError
from loom.core.trigger import Trigger


@dataclass
class Workflow:
    """A workflow is a composition of Trigger, Steps, and Actions.

    Workflows define the flow of data from trigger through steps to actions.
    Each workflow has a name and optional retry/fallback configuration.
    """

    name: str
    trigger: Trigger
    steps: list[Step]
    actions: list[Action]
    description: str = ""

    # Retry configuration
    max_retries: int = 0
    retry_delay_seconds: float = 1.0

    def __repr__(self) -> str:
        step_names = " → ".join(s.name for s in self.steps)
        action_names = ", ".join(a.name for a in self.actions)
        return f"<Workflow: {self.name} [{step_names}] → [{action_names}]>"


@dataclass
class PipelineResult:
    """Result of a pipeline execution."""

    success: bool
    context: PipelineContext
    action_results: dict[str, Any] = field(default_factory=dict)
    error: Exception | None = None


class Pipeline:
    """Executes workflows by running triggers, steps, and actions in sequence."""

    def __init__(self, workflow: Workflow):
        self.workflow = workflow

    async def run(self, context: PipelineContext | None = None) -> PipelineResult:
        """Execute the workflow.

        Args:
            context: Optional initial context. If not provided,
                    the trigger will emit one.

        Returns:
            PipelineResult with success status, final context, and action results
        """
        # Get initial context from trigger if not provided
        if context is None:
            context = await self.workflow.trigger.emit()

        context = context.model_copy(update={"workflow_id": self.workflow.name})

        # Run all steps in sequence
        try:
            context = await self._run_steps(context)
        except StepError as e:
            context = context.add_error(e.step_name, e.message)
            return PipelineResult(success=False, context=context, error=e)

        # Run all actions
        action_results = {}
        try:
            action_results = await self._run_actions(context)
        except ActionError as e:
            context = context.add_error(e.action_name, e.message)
            return PipelineResult(
                success=False,
                context=context,
                action_results=action_results,
                error=e,
            )

        return PipelineResult(
            success=True,
            context=context,
            action_results=action_results,
        )

    async def _run_steps(self, context: PipelineContext) -> PipelineContext:
        """Run all steps in sequence."""
        for step in self.workflow.steps:
            # Validate step requirements
            if not await step.validate(context):
                raise StepError(
                    step.name,
                    f"Validation failed for step {step.name}",
                    recoverable=False,
                )

            # Execute step
            context = context.record_step(step.name)
            context = await step.run(context)

        return context

    async def _run_actions(self, context: PipelineContext) -> dict[str, Any]:
        """Run all actions and collect results."""
        results = {}
        for action in self.workflow.actions:
            result = await action.execute(context)
            results[action.name] = result
        return results
