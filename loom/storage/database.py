"""Database connection management for PostgreSQL.

Provides async SQLAlchemy engine and session factory.
Uses DATABASE_URL from environment variables.
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DEFAULT_URL = "postgresql+asyncpg://postgres:postgres@localhost:5434/loom"

# Global engine instance
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_url() -> str:
    """Get database URL — reads from env at call time, not import time."""
    return os.environ.get("DATABASE_URL", DEFAULT_URL)


def get_engine() -> AsyncEngine:
    """Get or create the async database engine."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            _get_url(),
            echo=os.getenv("DB_ECHO", "").lower() == "true",
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session as an async context manager."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_engine() -> None:
    """Close the database engine and cleanup connections."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def init_engine(url: str | None = None) -> AsyncEngine:
    """Initialize the database engine with optional custom URL."""
    global _engine, _session_factory

    if url:
        os.environ["DATABASE_URL"] = url

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None

    return get_engine()
