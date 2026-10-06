"""PostgreSQL-only migrations: offline SQL or async online execution."""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from app.db import models  # noqa: F401 -- register all tables
from app.db.base import Base
from app.db.session import create_engine, validate_schema

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

database_url = config.get_main_option("sqlalchemy.url") or os.environ.get("VIGIL_DATABASE_URL")
if not database_url:
    raise RuntimeError("Set VIGIL_DATABASE_URL to a postgresql+asyncpg URL before running Alembic")
if make_url(database_url).drivername != "postgresql+asyncpg":
    raise ValueError("Alembic migrations require PostgreSQL via asyncpg")

database_schema = os.environ.get("VIGIL_DATABASE_SCHEMA")
validate_schema(database_schema)


def migrate(connection):
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        compare_type=True,
        version_table_schema=database_schema,
    )
    with context.begin_transaction():
        if database_schema is not None:
            # Also scope explicitly injected migration connections; no public fallback.
            context.execute(f'SET LOCAL search_path TO "{database_schema}"')
        context.run_migrations()


async def run_online():
    ssl_value = os.environ.get("VIGIL_DATABASE_SSL", "false").lower()
    if ssl_value not in {"true", "false", "1", "0"}:
        raise ValueError("VIGIL_DATABASE_SSL must be true/false or 1/0")
    engine = create_engine(
        database_url,
        poolclass=NullPool,
        database_ssl=ssl_value in {"true", "1"},
        database_ssl_ca_file=os.environ.get("VIGIL_DATABASE_SSL_CA_FILE"),
        database_schema=database_schema,
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(migrate)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=database_url,
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=database_schema,
    )
    with context.begin_transaction():
        if database_schema is not None:
            context.execute(f'SET LOCAL search_path TO "{database_schema}"')
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    migrate(config.attributes["connection"])
else:
    asyncio.run(run_online())
