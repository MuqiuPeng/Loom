"""Base entity for all database models."""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class BaseEntity(BaseModel):
    """Base class for all persistent entities.

    All tables inherit these fields.
    user_id defaults to "local" for single-user mode,
    pre-structured for future multi-tenancy migration.
    """

    id: UUID = Field(default_factory=uuid4)
    user_id: str = Field(default="local")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
