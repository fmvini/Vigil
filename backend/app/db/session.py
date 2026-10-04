"""Explicit engine/session factories; no connections or schema changes at import."""

from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(
    database_url: str, *, allow_sqlite_for_tests: bool = False, **kwargs: Any
) -> AsyncEngine:
    url = make_url(database_url)
    sqlite_test = url.drivername == "sqlite+aiosqlite" and allow_sqlite_for_tests
    if url.drivername != "postgresql+asyncpg" and not sqlite_test:
        raise ValueError(
            "Runtime requires postgresql+asyncpg; SQLite is allowed only in explicit tests"
        )
    options: dict[str, Any] = {"pool_pre_ping": True}
    if not sqlite_test and "poolclass" not in kwargs:
        options.update(pool_size=5, max_overflow=5, pool_timeout=30)
    options.update(kwargs)
    engine = create_async_engine(url, **options)
    if sqlite_test:

        @event.listens_for(engine.sync_engine, "connect")
        def enable_foreign_keys(connection: Any, _: Any) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create one session per request/task; caller owns transaction and disposal."""
    return async_sessionmaker(engine, expire_on_commit=False)
