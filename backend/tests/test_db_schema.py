"""Offline migration and ORM contract tests; these do not prove PostgreSQL behavior."""

from datetime import datetime
from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import DateTime, Uuid
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.db.models import Monitor, Project, Session, User
from app.db.session import create_engine, create_session_factory

BACKEND = Path(__file__).resolve().parents[1]


def migration_config(url="postgresql+asyncpg://offline:offline@localhost/offline", output=None):
    config = Config(str(BACKEND / "alembic.ini"), output_buffer=output)
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def test_offline_upgrade_and_downgrade_sql():
    output = StringIO()
    command.upgrade(migration_config(output=output), "head", sql=True)
    sql = output.getvalue()
    for table in (
        "users",
        "legal_acceptances",
        "sessions",
        "projects",
        "monitors",
        "check_jobs",
        "check_results",
        "incidents",
    ):
        assert f"CREATE TABLE {table}" in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql
    assert " UUID " in sql
    assert "JSONB" in sql
    assert "FOREIGN KEY(job_id, monitor_id, config_version, scheduled_at)" in sql
    assert "CREATE UNIQUE INDEX uq_check_jobs_open_monitor" in sql
    assert "WHERE status IN ('pending', 'running')" in sql
    assert "CREATE UNIQUE INDEX uq_incidents_open_monitor" in sql
    assert "WHERE ended_at IS NULL" in sql
    assert "ON DELETE SET NULL" in sql
    output = StringIO()
    command.downgrade(migration_config(output=output), "0001_initial:base", sql=True)
    sql = output.getvalue()
    assert sql.index("DROP TABLE incidents") < sql.index("DROP TABLE check_results")
    assert sql.index("DROP TABLE check_results") < sql.index("DROP TABLE check_jobs")
    assert sql.index("DROP TABLE monitors") < sql.index("DROP TABLE projects")


def test_migration_rejects_sqlite_even_offline():
    with pytest.raises(ValueError, match="PostgreSQL"):
        command.upgrade(migration_config("sqlite+aiosqlite:///:memory:"), "head", sql=True)


def test_schema_uuid_and_timezone_contract():
    assert set(Base.metadata.tables) == {
        "users",
        "legal_acceptances",
        "sessions",
        "projects",
        "monitors",
        "check_jobs",
        "check_results",
        "incidents",
    }
    for table in Base.metadata.tables.values():
        assert isinstance(table.c.id.type, Uuid)
        for column in table.columns:
            if isinstance(column.type, DateTime):
                assert column.type.timezone is True
    assert Session.__table__.c.token_hash.type.__class__.__name__ == "Text"
    assert "freshness" not in Monitor.__table__.c


@pytest.mark.parametrize(
    "url",
    [
        "sqlite+aiosqlite:///:memory:",
        "postgresql://localhost/vigil",
        "mysql+aiomysql://localhost/vigil",
    ],
)
def test_runtime_requires_postgresql_asyncpg(url):
    with pytest.raises(ValueError, match="Runtime requires"):
        create_engine(url)


@pytest.mark.asyncio
async def test_engine_factory_and_explicit_sqlite_unit_test_defaults():
    engine = create_engine("sqlite+aiosqlite:///:memory:", allow_sqlite_for_tests=True)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = create_session_factory(engine)
        async with factory.begin() as session:
            user = User(email="unit@example.test", password_hash="not-a-real-password")
            session.add(user)
            await session.flush()
            project = Project(owner_id=user.id, name="Unit", public_slug="unit")
            session.add(project)
            await session.flush()
            monitor = Monitor(
                project_id=project.id,
                name="Unit",
                url="https://example.test",
                latency_threshold_ms=None,
            )
            session.add(monitor)
            await session.flush()
            assert monitor.latency_threshold_ms is None
            assert monitor.config_version == 1
            assert monitor.interval_seconds == 60
            assert monitor.timeout_ms == 5000
            assert monitor.retry_count == 1
            assert monitor.health_status is None
        assert user.id is not None  # no expiration after commit
        assert isinstance(user.created_at, datetime)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgresql_engine_supports_null_pool_without_connecting():
    engine = create_engine("postgresql+asyncpg://vigil:unused@localhost/vigil", poolclass=NullPool)
    assert isinstance(engine.pool, NullPool)
    await engine.dispose()
