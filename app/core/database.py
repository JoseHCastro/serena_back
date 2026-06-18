"""
Database engine and session management module.

Configures the SQLAlchemy async engine, provides the declarative Base
for all ORM models, and exposes a FastAPI dependency for session injection.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base class inherited by all SQLAlchemy ORM models.

    Registering models here makes them discoverable by Alembic's
    autogenerate feature. Every model file must be imported in
    alembic/env.py for this to work correctly.
    """


# ---------------------------------------------------------------------------
# Async Engine
# ---------------------------------------------------------------------------
connect_args = {}
if "render.com" in settings.DATABASE_URL:
    connect_args["ssl"] = True

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,       # Logs SQL statements in debug mode
    pool_pre_ping=True,        # Validates connections before handing them out
    pool_size=10,              # Base number of persistent connections
    max_overflow=20,           # Extra connections allowed beyond pool_size
    connect_args=connect_args,
)

# ---------------------------------------------------------------------------
# Session Factory
# ---------------------------------------------------------------------------
AsyncSessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,    # Avoids lazy-load errors after commit
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that provides a database session per request.

    Opens an AsyncSession, yields it to the route handler, commits on
    success, rolls back on exception, and always closes the session.

    Yields:
        AsyncSession: An active, transactional database session.

    Raises:
        Exception: Re-raises any exception after rolling back the transaction.

    Example:
        ```python
        @router.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(User))
        ```
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
