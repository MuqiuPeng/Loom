"""Base entity for all database models."""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from loom.current_user import get_current_user


class BaseEntity(BaseModel):
    """Base class for all persistent entities.

    All tables inherit these fields.

    `user_id` defaults to whoever's request is in flight rather than to a
    fixed string. Callers that know the owner still pass it explicitly; this
    is the safety net for the ones that don't, and the reason a row created
    deep inside a request — a placeholder artifact, a parsed JD — lands on the
    right account instead of on a shared placeholder. Outside a request it
    resolves to LOOM_DEFAULT_USER_ID.
    """

    id: UUID = Field(default_factory=uuid4)
    user_id: str = Field(default_factory=get_current_user)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
