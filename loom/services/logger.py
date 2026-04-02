"""Global singleton logger for Loom — writes to PostgreSQL and stdout."""

import asyncio
import traceback as tb_module
from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class LogEntry(BaseModel):
    """Pydantic schema for a log entry."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str = "local"
    level: str = "info"
    category: str = "system"
    action: str = ""
    message: str = ""
    workflow_run_id: str | None = None
    step_name: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    traceback: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class LoomLogger:
    """Global singleton logger. Writes to DB (fire-and-forget) + stdout."""

    _instance: "LoomLogger | None" = None

    @classmethod
    def get(cls) -> "LoomLogger":
        if cls._instance is None:
            cls._instance = LoomLogger()
        return cls._instance

    async def info(
        self, category: str, action: str, message: str, **kwargs: Any
    ) -> None:
        await self._log("info", category, action, message, **kwargs)

    async def warning(
        self, category: str, action: str, message: str, **kwargs: Any
    ) -> None:
        await self._log("warning", category, action, message, **kwargs)

    async def error(
        self,
        category: str,
        action: str,
        message: str,
        error: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        await self._log("error", category, action, message, error=error, **kwargs)

    async def _log(
        self,
        level: str,
        category: str,
        action: str,
        message: str,
        error: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        entry = LogEntry(
            level=level,
            category=category,
            action=action,
            message=message,
            data=kwargs,
            error=str(error) if error else None,
            traceback=tb_module.format_exc() if error else None,
            workflow_run_id=kwargs.pop("workflow_run_id", None),
            step_name=kwargs.pop("step_name", None),
        )
        # Fire and forget — don't block the caller
        asyncio.create_task(self._save(entry))
        # Also print to stdout
        print(f"[{level.upper()}] {category}.{action}: {message}")

    async def _save(self, entry: LogEntry) -> None:
        try:
            from loom.api import get_storage

            storage = get_storage()
            await storage.save_log_entry(entry)
        except Exception as e:
            print(f"[LOG_ERROR] Failed to save log: {e}")


# Global convenience accessor
logger = LoomLogger.get()
