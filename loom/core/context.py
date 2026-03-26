"""PipelineContext definition - shared state passed through the pipeline."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class PipelineContext(BaseModel):
    """Context carries user_id, workflow state, and inter-step data.

    All Steps receive and return this context. Steps are stateless;
    all persistence goes through Storage.
    """

    id: UUID = Field(default_factory=uuid4)
    user_id: str = Field(default="default")
    workflow_id: str | None = None

    # Inter-step data storage
    data: dict[str, Any] = Field(default_factory=dict)

    # Execution metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    current_step: str | None = None
    steps_executed: list[str] = Field(default_factory=list)

    # Error tracking
    errors: list[dict[str, Any]] = Field(default_factory=list)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from context data."""
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> "PipelineContext":
        """Set a value in context data, returning new context."""
        new_data = self.data.copy()
        new_data[key] = value
        return self.model_copy(update={"data": new_data})

    def record_step(self, step_name: str) -> "PipelineContext":
        """Record that a step has been executed."""
        return self.model_copy(update={
            "steps_executed": [*self.steps_executed, step_name],
            "current_step": step_name,
        })

    def add_error(self, step: str, error: str, details: dict | None = None) -> "PipelineContext":
        """Record an error that occurred during execution."""
        error_record = {
            "step": step,
            "error": error,
            "details": details or {},
            "timestamp": datetime.utcnow().isoformat(),
        }
        return self.model_copy(update={
            "errors": [*self.errors, error_record],
        })
