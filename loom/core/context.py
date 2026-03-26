"""PipelineContext - shared state passed through the pipeline."""

from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class PipelineContext(BaseModel):
    """Context carries user_id, workflow state, and inter-step data.

    Steps are stateless. All state flows through Context.
    All persistence goes through Storage.
    """

    id: UUID = Field(default_factory=uuid4)
    user_id: str = Field(default="default")
    workflow_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
