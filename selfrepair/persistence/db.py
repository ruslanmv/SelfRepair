"""Database engine and session management.

Uses async SQLAlchemy 2.0 via asyncpg. Sync Alembic migrations use psycopg
(see migrations/env.py).
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base for all ORM models."""


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine(database_url: str) -> AsyncEngine:
    """Build (or return) the singleton async engine.

    `database_url` should look like postgresql+asyncpg://user:pass@host/db.
    """
    global _engine
    if _engine is None:
        _engine = create_async_engine(database_url, pool_pre_ping=True)
    return _engine


def get_sessionmaker(database_url: str) -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(database_url),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _sessionmaker


def _reset_for_tests() -> None:
    """Test-only: forget the cached engine/sessionmaker."""
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None
