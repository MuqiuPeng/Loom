"""Pipeline execution engine - runs workflows with checkpoint support."""

from datetime import datetime
from typing import Any
from uuid import UUID

from loom.core.context import PipelineContext
from loom.core.registry import step_registry
from loom.storage import RunStatus, StepRun, WorkflowDefinition, WorkflowRun

_logger = None


async def _log(level: str, action: str, message: str, **kw: Any) -> None:
    global _logger
    try:
        if _logger is None:
            from loom.services.logger import logger
            _logger = logger
        method = getattr(_logger, level)
        await method("workflow", action, message, **kw)
    except Exception:
        pass


class StepError(Exception):
    """Exception raised when a step fails."""

    def __init__(self, step_name: str, message: str):
        self.step_name = step_name
        self.message = message
        super().__init__(f"[{step_name}] {message}")


class WorkflowRunner:
    """Executes workflows with checkpoint and resume support.

    Responsibilities:
    1. Execute steps in order defined by WorkflowDefinition.steps
    2. Create WorkflowRun record on start
    3. Create StepRun record before/after each step
    4. Resume from last completed step on failure recovery
    5. Update status on success/failure
    """

    def __init__(
        self,
        workflow_def: WorkflowDefinition,
        storage: "WorkflowStorage | None" = None,
    ):
        self.workflow_def = workflow_def
        self.storage = storage or InMemoryStorage()

    async def run(
        self,
        initial_data: dict[str, Any] | None = None,
        resume_run_id: UUID | None = None,
    ) -> WorkflowRun:
        """Execute the workflow.

        Args:
            initial_data: Initial context data (for new runs)
            resume_run_id: Resume a failed run from checkpoint

        Returns:
            The completed WorkflowRun record
        """
        if resume_run_id:
            return await self._resume(resume_run_id)
        return await self._start_new(initial_data or {})

    async def _start_new(self, initial_data: dict[str, Any]) -> WorkflowRun:
        """Start a new workflow run."""
        workflow_run = WorkflowRun(
            workflow_definition_id=self.workflow_def.id,
            status=RunStatus.RUNNING,
            trigger_data=initial_data,
        )
        await self.storage.save_workflow_run(workflow_run)
        await _log("info", "workflow.start",
            f"Starting workflow {self.workflow_def.name}",
            workflow_run_id=str(workflow_run.id))

        context = PipelineContext(
            workflow_id=str(self.workflow_def.id),
            data=initial_data,
        )
        return await self._execute_steps(workflow_run, context, start_order=0)

    async def _resume(self, run_id: UUID) -> WorkflowRun:
        """Resume a failed workflow run from checkpoint."""
        await _log("info", "workflow.resume", f"Resuming workflow {run_id}",
            workflow_run_id=str(run_id))
        workflow_run = await self.storage.get_workflow_run(run_id)
        if not workflow_run:
            raise ValueError(f"WorkflowRun {run_id} not found")

        if workflow_run.status == RunStatus.COMPLETED:
            return workflow_run

        # Find last completed step
        step_runs = await self.storage.get_step_runs(run_id)
        completed_runs = [
            sr for sr in step_runs
            if sr.status == RunStatus.COMPLETED
        ]

        if not completed_runs:
            # No completed steps, restart from beginning
            context = PipelineContext(
                workflow_id=str(self.workflow_def.id),
                data=workflow_run.trigger_data,
            )
            start_order = 0
        else:
            # Resume from last completed step's output
            last_completed = max(completed_runs, key=lambda sr: sr.order)
            context = PipelineContext(
                workflow_id=str(self.workflow_def.id),
                data=last_completed.output_snapshot,
            )
            start_order = last_completed.order + 1

        # Update workflow run status
        workflow_run.status = RunStatus.RUNNING
        await self.storage.save_workflow_run(workflow_run)

        return await self._execute_steps(workflow_run, context, start_order)

    async def _execute_steps(
        self,
        workflow_run: WorkflowRun,
        context: PipelineContext,
        start_order: int,
    ) -> WorkflowRun:
        """Execute steps starting from given order."""
        steps = sorted(self.workflow_def.steps, key=lambda s: s.get("order", 0))

        for step_config in steps:
            order = step_config.get("order", 0)
            if order < start_order:
                continue

            step_name = step_config["name"]

            # Create step run record
            step_run = StepRun(
                workflow_run_id=workflow_run.id,
                step_name=step_name,
                order=order,
                status=RunStatus.RUNNING,
                input_snapshot=context.data.copy(),
                started_at=datetime.utcnow(),
            )
            await self.storage.save_step_run(step_run)

            await _log("info", "step.start", f"Running step: {step_name}",
                workflow_run_id=str(workflow_run.id), step_name=step_name)

            try:
                step = step_registry.get(step_name)
                step_start = datetime.utcnow()
                context = await step.run(context)

                step_run.status = RunStatus.COMPLETED
                step_run.output_snapshot = context.data.copy()
                step_run.completed_at = datetime.utcnow()
                await self.storage.save_step_run(step_run)

                duration = (step_run.completed_at - step_start).total_seconds()
                await _log("info", "step.complete",
                    f"Step {step_name} completed in {duration:.1f}s",
                    workflow_run_id=str(workflow_run.id),
                    step_name=step_name, duration_seconds=duration)

            except Exception as e:
                step_run.status = RunStatus.FAILED
                step_run.error = str(e)
                step_run.completed_at = datetime.utcnow()
                await self.storage.save_step_run(step_run)

                workflow_run.status = RunStatus.FAILED
                await self.storage.save_workflow_run(workflow_run)

                await _log("error", "step.failed",
                    f"Step {step_name} failed: {str(e)[:200]}",
                    error=e, workflow_run_id=str(workflow_run.id),
                    step_name=step_name)

                raise StepError(step_name, str(e)) from e

        workflow_run.status = RunStatus.COMPLETED
        await self.storage.save_workflow_run(workflow_run)
        total = (datetime.utcnow() - workflow_run.created_at).total_seconds()
        await _log("info", "workflow.complete",
            f"Workflow completed in {total:.1f}s",
            workflow_run_id=str(workflow_run.id))
        return workflow_run


class WorkflowStorage:
    """Abstract interface for workflow persistence."""

    async def save_workflow_run(self, run: WorkflowRun) -> None:
        raise NotImplementedError

    async def get_workflow_run(self, run_id: UUID) -> WorkflowRun | None:
        raise NotImplementedError

    async def save_step_run(self, run: StepRun) -> None:
        raise NotImplementedError

    async def get_step_runs(self, workflow_run_id: UUID) -> list[StepRun]:
        raise NotImplementedError


class InMemoryStorage(WorkflowStorage):
    """In-memory storage for testing and development."""

    def __init__(self):
        self._workflow_runs: dict[UUID, WorkflowRun] = {}
        self._step_runs: dict[UUID, list[StepRun]] = {}

    async def save_workflow_run(self, run: WorkflowRun) -> None:
        self._workflow_runs[run.id] = run

    async def get_workflow_run(self, run_id: UUID) -> WorkflowRun | None:
        return self._workflow_runs.get(run_id)

    async def save_step_run(self, run: StepRun) -> None:
        if run.workflow_run_id not in self._step_runs:
            self._step_runs[run.workflow_run_id] = []
        # Update existing or append new
        runs = self._step_runs[run.workflow_run_id]
        for i, existing in enumerate(runs):
            if existing.id == run.id:
                runs[i] = run
                return
        runs.append(run)

    async def get_step_runs(self, workflow_run_id: UUID) -> list[StepRun]:
        return self._step_runs.get(workflow_run_id, [])
