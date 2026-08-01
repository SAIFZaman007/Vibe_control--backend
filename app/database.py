"""
Database layer.

Uses SQLAlchemy 2.0 with SQLite by default. The session dependency
(`get_db`) is injected into every route that needs database access, ensuring
sessions are always opened and closed correctly.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# `check_same_thread` is only needed for SQLite because it is used across the
# threads FastAPI spawns. Postgres/MySQL do not need this argument.
connect_args = (
    {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,  # gracefully recover dropped connections in production
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base that all ORM models inherit from."""

    pass


def get_db():
    """FastAPI dependency that yields a database session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    Create all tables. Called on application startup.

    For a real production system you would replace this with Alembic
    migrations; for an MVP / SQLite setup, create_all is clean and sufficient.
    """
    # Import models so they are registered on the metadata before create_all.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
