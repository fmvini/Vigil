"""Explicit engine/session factories; no connections or schema changes at import."""

import re
import ssl
from typing import Any

import certifi
from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(
    database_url: str,
    *,
    allow_sqlite_for_tests: bool = False,
    database_ssl: bool = False,
    database_ssl_ca_file: str | None = None,
    database_schema: str | None = None,
    pool_size: int = 5,
    max_overflow: int = 5,
    **kwargs: Any,
) -> AsyncEngine:
    """Configure connections only; TLS/schema options never bootstrap a database.

    Explicit TLS uses verified certificates and hostnames, with custom CA or certifi.
    Keep the real TLS hostname in the URL when routing TCP through a private relay.
    Pool sizes apply to the default PostgreSQL pool, not NullPool or SQLite tests.
    """
    url = make_url(database_url)
    sqlite_test = url.drivername == "sqlite+aiosqlite" and allow_sqlite_for_tests
    if url.drivername != "postgresql+asyncpg" and not sqlite_test:
        raise ValueError(
            "Runtime requires postgresql+asyncpg; SQLite is allowed only in explicit tests"
        )
    if not isinstance(database_ssl, bool):
        raise ValueError("database_ssl must be a boolean")
    if database_ssl_ca_file is not None and not database_ssl:
        raise ValueError("database_ssl_ca_file requires database_ssl")
    validate_schema(database_schema)
    if sqlite_test and (database_ssl or database_schema is not None):
        raise ValueError("Database TLS/schema options require PostgreSQL")
    if (
        isinstance(pool_size, bool)
        or not isinstance(pool_size, int)
        or pool_size < 1
        or isinstance(max_overflow, bool)
        or not isinstance(max_overflow, int)
        or max_overflow < 0
    ):
        raise ValueError("pool_size must be positive and max_overflow nonnegative integers")
    connect_args = dict(kwargs.get("connect_args", {}))
    if database_ssl:
        if set(url.query) & {
            "ssl",
            "sslmode",
            "sslrootcert",
            "sslcert",
            "sslkey",
            "sslpassword",
            "channel_binding",
        } or ("ssl" in connect_args):
            raise ValueError("Configure TLS with database_ssl/database_ssl_ca_file only")
        connect_args["ssl"] = ssl.create_default_context(
            cafile=database_ssl_ca_file if database_ssl_ca_file is not None else certifi.where()
        )
    if database_schema is not None:
        server_settings = dict(connect_args.get("server_settings", {}))
        if server_settings.get("search_path", database_schema) != database_schema:
            raise ValueError("database_schema conflicts with connection search_path")
        server_settings["search_path"] = database_schema
        connect_args["server_settings"] = server_settings
    if connect_args:
        kwargs["connect_args"] = connect_args
    options: dict[str, Any] = {"pool_pre_ping": True}
    if not sqlite_test and "poolclass" not in kwargs:
        options.update(pool_size=pool_size, max_overflow=max_overflow, pool_timeout=30)
    options.update(kwargs)
    engine = create_async_engine(url, **options)
    if database_schema is not None:

        @event.listens_for(engine.sync_engine, "connect")
        def configure_schema(connection: Any, _: Any) -> None:
            # Some hosted proxies discard startup parameters. Apply this on the
            # physical asyncpg connection outside a transaction so rollback keeps
            # the schema, with no public fallback and no schema creation.
            connection.run_async(
                lambda driver: driver.execute(f'SET SESSION search_path TO "{database_schema}"')
            )

    if sqlite_test:

        @event.listens_for(engine.sync_engine, "connect")
        def enable_foreign_keys(connection: Any, _: Any) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def validate_schema(schema: str | None) -> None:
    """A single unquoted PostgreSQL identifier, safe in offline search_path SQL."""
    if schema is not None and (
        not isinstance(schema, str) or re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", schema) is None
    ):
        raise ValueError("database_schema must be a lowercase PostgreSQL identifier (1..63 chars)")


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create one session per request/task; caller owns transaction and disposal."""
    return async_sessionmaker(engine, expire_on_commit=False)
