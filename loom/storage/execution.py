"""Execution state schemas - workflow definitions and run tracking."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import Field

from loom.storage.base import BaseEntity


class TriggerType(str, Enum):
    """Types of workflow triggers."""

    MANUAL = "manual"
    EMAIL = "email"
    GIT_HOOK = "git-hook"
    SCHEDULED = "scheduled"


class RunStatus(str, Enum):
    """Status of a workflow or step run."""

    PENDING = "pending"
    RUNNING = "running"
    FAILED = "failed"
    COMPLETED = "completed"


class StepConfig(BaseEntity):
    """Configuration for a step within a workflow definition."""

    name: str = Field(..., description="Step class name, e.g. 'ParseJDStep'")
    order: int = Field(..., description="Execution order, starting from 0")
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Step-specific configuration"
    )


class WorkflowDefinition(BaseEntity):
    """Workflow definition - stored in database for dynamic configuration.

    Defines what steps a workflow contains and how it's triggered.
    """

    name: str = Field(..., description="Unique workflow name, e.g. 'resume-tailor'")
    description: str = Field(default="")
    steps: list[dict[str, Any]] = Field(
        default_factory=list,
        description="JSONB: [{name, order, config}]"
    )
    trigger_type: TriggerType = Field(default=TriggerType.MANUAL)
    is_active: bool = Field(default=True)


class WorkflowRun(BaseEntity):
    """A single execution instance of a workflow.

    Tracks the overall status and links to step runs.
    """

    workflow_definition_id: UUID = Field(..., description="FK to WorkflowDefinition")
    status: RunStatus = Field(default=RunStatus.PENDING)
    trigger_data: dict[str, Any] = Field(
        default_factory=dict,
        description="JSONB: Original input data from trigger"
    )


class StepRun(BaseEntity):
    """Execution record for a single step.

    Stores input/output snapshots for checkpoint resume.

    Resume logic:
    1. Find last completed StepRun for a WorkflowRun
    2. Take its output_snapshot to restore context
    3. Continue from the next step
    """

    workflow_run_id: UUID = Field(..., description="FK to WorkflowRun")
    step_name: str = Field(..., description="Name of the step executed")
    order: int = Field(..., description="Execution order")
    status: RunStatus = Field(default=RunStatus.PENDING)
    input_snapshot: dict[str, Any] = Field(
        default_factory=dict,
        description="JSONB: Complete context snapshot before execution"
    )
    output_snapshot: dict[str, Any] = Field(
        default_factory=dict,
        description="JSONB: Complete context snapshot after execution"
    )
    error: str | None = Field(default=None, description="Error message if failed")
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
