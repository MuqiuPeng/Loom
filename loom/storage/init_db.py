"""Database initialization utilities."""

from loom.storage.repository import DataStorage, InMemoryDataStorage
from loom.workflows.resume_tailor import RESUME_TAILOR_WORKFLOW

# Global storage instance (will be replaced with PostgreSQL later)
_storage: DataStorage | None = None


def get_storage() -> DataStorage:
    """Get the global storage instance."""
    global _storage
    if _storage is None:
        _storage = InMemoryDataStorage()
    return _storage


def set_storage(storage: DataStorage) -> None:
    """Set the global storage instance (for testing)."""
    global _storage
    _storage = storage


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
