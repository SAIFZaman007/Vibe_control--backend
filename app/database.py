"""
Database layer supporting both SQLite (dev) and Async PostgreSQL/asyncpg (prod).
"""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Handle SQLite connect args if running locally
connect_args = (
    {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)

# Use create_async_engine for asyncpg / async SQLite
engine = create_async_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,  # Gracefully recover dropped connections
)

# Async session factory.
# NOTE: `autocommit` was removed in SQLAlchemy 2.0 — sessions never autocommit,
# so we simply don't pass it. `expire_on_commit=False` keeps ORM objects usable
# after commit (important when returning them from a request handler).
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Declarative base that all ORM models inherit from."""

    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI async dependency yielding a database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """
    Create all tables asynchronously on application startup.
    """
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)