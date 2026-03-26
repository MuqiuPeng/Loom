"""Core abstractions: Pipeline, Context, Step, Trigger, Action."""

from loom.core.action import Action, ActionError
from loom.core.context import PipelineContext
from loom.core.pipeline import Pipeline, PipelineResult, Workflow
from loom.core.step import Step, StepError
from loom.core.trigger import ManualTrigger, Trigger

__all__ = [
    "Action",
    "ActionError",
    "ManualTrigger",
    "Pipeline",
    "PipelineContext",
    "PipelineResult",
    "Step",
    "StepError",
    "Trigger",
    "Workflow",
]
