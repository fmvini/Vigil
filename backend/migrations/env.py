"""PostgreSQL-only migrations: offline SQL or async online execution."""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from app.db import models  # noqa: F401 -- register all tables
from app.db.base import Base
from app.db.session import create_engine

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

database_url = config.get_main_option("sqlalchemy.url") or os.environ.get("VIGIL_DATABASE_URL")
if not database_url:
    raise RuntimeError("Set VIGIL_DATABASE_URL to a postgresql+asyncpg URL before running Alembic")
if make_url(database_url).drivername != "postgresql+asyncpg":
    raise ValueError("Alembic migrations require PostgreSQL via asyncpg")


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_online():
    engine = create_engine(database_url, poolclass=NullPool)
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
    )
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    migrate(config.attributes["connection"])
else:
    asyncio.run(run_online())
