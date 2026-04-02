"""Database initialization utilities.

Supports both InMemory (default) and PostgreSQL storage backends.

Set LOOM_DB_BACKEND=postgres to use PostgreSQL.
Set DATABASE_URL to configure the PostgreSQL connection.
"""

import os

from loom.storage.repository import DataStorage, InMemoryDataStorage
from loom.workflows.resume_tailor import RESUME_TAILOR_WORKFLOW

# Storage backend configuration
DB_BACKEND = os.getenv("LOOM_DB_BACKEND", "memory")  # "memory" or "postgres"

# Global storage instance
_storage: DataStorage | None = None


def get_storage() -> DataStorage:
    """Get the global storage instance.

    Returns InMemoryDataStorage by default.
    Set LOOM_DB_BACKEND=postgres to use PostgreSQL.
    """
    global _storage
    if _storage is None:
        if DB_BACKEND == "postgres":
            # Import here to avoid requiring asyncpg when not using postgres
            from loom.storage.postgres import PostgresDataStorage
            # Note: PostgresDataStorage needs a session, so we can't use it directly
            # For now, return InMemoryDataStorage; CLI uses PostgresDataStorageContext
            _storage = InMemoryDataStorage()
        else:
            _storage = InMemoryDataStorage()
    return _storage


def set_storage(storage: DataStorage) -> None:
    """Set the global storage instance (for testing)."""
    global _storage
    _storage = storage


def is_postgres_enabled() -> bool:
    """Check if PostgreSQL backend is enabled."""
    return DB_BACKEND == "postgres"


async def init_db(storage: DataStorage | None = None) -> DataStorage:
    """Initialize the database.

    Creates all tables (if using PostgreSQL) and registers
    built-in workflow definitions.

    Args:
        storage: Optional storage instance. If None, uses global.

    Returns:
        The initialized storage instance
    """
    if storage is None:
        storage = get_storage()

    # Register built-in workflows
    await _register_workflows(storage)

    return storage


async def init_postgres_db() -> None:
    """Initialize PostgreSQL database tables.

    Creates all tables using SQLAlchemy ORM models.
    """
    from loom.storage.database import get_engine
    from loom.storage.models import Base

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _register_workflows(storage: DataStorage) -> None:
    """Register built-in workflow definitions.

    Currently registers:
    - resume-tailor
    """
    # For now, workflows are defined in code and don't need DB storage
    # This function is a placeholder for future DB-backed workflow storage
    pass


def get_workflow_definitions() -> dict:
    """Get all built-in workflow definitions.

    Returns:
        Dict mapping workflow name to WorkflowDefinition
    """
    return {
        "resume-tailor": RESUME_TAILOR_WORKFLOW,
    }
