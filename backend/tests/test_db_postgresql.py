"""Real PostgreSQL tests, skipped only when VIGIL_TEST_DATABASE_URL is unset.

Every test creates and destroys its own random schema, never the runtime tables.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from io import StringIO
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import delete, func, insert, inspect, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool
from test_db_schema import migration_config

from app.db.base import Base
from app.db.models import CheckJob, CheckResult, Incident, Monitor, Project, Session, User
from app.db.session import create_engine

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)


def migrate(connection, direction):
    config = migration_config()
    config.attributes["connection"] = connection
    getattr(command, direction)(config, "head" if direction == "upgrade" else "base")


@pytest_asyncio.fixture
async def pg_engine():
    url = os.environ.get("VIGIL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("VIGIL_TEST_DATABASE_URL unset: real PostgreSQL unavailable to these tests")
    schema = "vigil_test_" + uuid4().hex
    admin = create_engine(url, poolclass=NullPool)
    scoped = create_engine(
        url,
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema, "timezone": "UTC"}},
    )
    created = False
    try:
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        async with scoped.begin() as connection:
            await connection.run_sync(migrate, "upgrade")
        yield scoped
        async with scoped.begin() as connection:
            await connection.run_sync(migrate, "downgrade")
            tables = await connection.run_sync(lambda c: inspect(c).get_table_names())
            assert tables == ["alembic_version"]
    finally:
        await scoped.dispose()
        if created:
            async with admin.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def seed(connection):
    user_id, project_id, monitor_id = uuid4(), uuid4(), uuid4()
    await connection.execute(
        insert(User).values(id=user_id, email="pg@example.test", password_hash="test-hash")
    )
    await connection.execute(
        insert(Project).values(id=project_id, owner_id=user_id, name="PG", public_slug="pg-test")
    )
    await connection.execute(
        insert(Monitor).values(
            id=monitor_id, project_id=project_id, name="PG", url="https://example.test"
        )
    )
    return user_id, project_id, monitor_id


def job_values(monitor_id, **overrides):
    values = dict(
        id=uuid4(),
        monitor_id=monitor_id,
        config_version=1,
        config_snapshot={"method": "GET"},
        scheduled_at=NOW,
        expires_at=NOW + timedelta(seconds=60),
        budget_ms=13600,
        status="pending",
    )
    values.update(overrides)
    return values


def result_values(job, **overrides):
    values = dict(
        id=uuid4(),
        job_id=job["id"],
        monitor_id=job["monitor_id"],
        config_version=job["config_version"],
        scheduled_at=job["scheduled_at"],
        started_at=NOW,
        completed_at=NOW + timedelta(seconds=1),
        outcome="failure",
        cycle_duration_ms=1000,
        queue_delay_ms=0,
        attempt_count=1,
        attempts=[{"error_code": "timeout"}],
        error_code="timeout",
        health_after="degraded",
    )
    values.update(overrides)
    return values


def incident_values(monitor_id, **overrides):
    values = dict(
        id=uuid4(),
        monitor_id=monitor_id,
        started_at=NOW,
        detected_at=NOW,
        cause_code="timeout",
        failure_threshold_snapshot=3,
    )
    values.update(overrides)
    return values


async def rejects(connection, statement):
    with pytest.raises(IntegrityError):
        async with connection.begin_nested():
            await connection.execute(statement)


@pytest.mark.asyncio
async def test_migration_roundtrip_matches_metadata_and_real_types(pg_engine):
    async with pg_engine.begin() as connection:
        assert (
            await connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0002_incident_evidence_indexes"
        )
        differences = await connection.run_sync(
            lambda c: compare_metadata(
                MigrationContext.configure(c, opts={"compare_type": True}), Base.metadata
            )
        )
        assert differences == []
        types = dict(
            (
                await connection.execute(
                    text(
                        "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='check_jobs'"
                    )
                )
            ).all()
        )
        assert types["id"] == "uuid"
        assert types["scheduled_at"] == "timestamp with time zone"
        assert types["config_snapshot"] == "jsonb"
        assert await connection.scalar(text("SHOW timezone")) == "UTC"


@pytest.mark.asyncio
async def test_offline_sql_scripts_execute_on_real_postgresql(pg_engine):
    async with pg_engine.connect() as connection:
        await connection.run_sync(migrate, "downgrade")
        await connection.execute(text("DROP TABLE alembic_version"))
        await connection.commit()
        output = StringIO()
        command.upgrade(migration_config(output=output), "head", sql=True)
        raw = await connection.get_raw_connection()
        await raw.driver_connection.execute(output.getvalue())
        assert (
            await connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0002_incident_evidence_indexes"
        )
        differences = await connection.run_sync(
            lambda c: compare_metadata(MigrationContext.configure(c), Base.metadata)
        )
        assert differences == []
        await connection.commit()
        output = StringIO()
        command.downgrade(
            migration_config(output=output), "0002_incident_evidence_indexes:base", sql=True
        )
        await raw.driver_connection.execute(output.getvalue())
        assert await connection.run_sync(lambda c: inspect(c).get_table_names()) == [
            "alembic_version"
        ]


@pytest.mark.asyncio
async def test_user_session_unique_normalization_and_temporal_constraints(pg_engine):
    async with pg_engine.begin() as connection:
        user_id, _, _ = await seed(connection)
        await rejects(connection, insert(User).values(email="pg@example.test", password_hash="x"))
        await rejects(connection, insert(User).values(email=" PG@example.test ", password_hash="x"))
        values = dict(
            user_id=user_id,
            token_hash="a" * 64,
            csrf_token="csrf",
            created_at=NOW,
            last_seen_at=NOW,
            expires_at=NOW + timedelta(days=7),
        )
        await connection.execute(insert(Session).values(**values))
        await rejects(connection, insert(Session).values(**values))
        values.update(token_hash="b" * 64, expires_at=NOW - timedelta(seconds=1))
        await rejects(connection, insert(Session).values(**values))


@pytest.mark.parametrize(
    "invalid",
    [
        {"method": "POST"},
        {"interval_seconds": 59},
        {"interval_seconds": 3601},
        {"timeout_ms": 999},
        {"timeout_ms": 15001},
        {"expected_status": 199},
        {"expected_status": 600},
        {"failure_threshold": 0},
        {"failure_threshold": 11},
        {"retry_count": -1},
        {"retry_count": 3},
        {"latency_threshold_ms": 99},
        {"latency_threshold_ms": 5001, "timeout_ms": 5000},
        {"config_version": 0},
        {"consecutive_failures": -1},
        {"health_status": "unknown"},
        {"last_http_status": 100},
        {"last_latency_ms": -1},
        {"paused_at": NOW, "next_check_at": NOW},
    ],
)
@pytest.mark.asyncio
async def test_monitor_constraints(pg_engine, invalid):
    async with pg_engine.begin() as connection:
        _, _, monitor_id = await seed(connection)
        await rejects(connection, update(Monitor).where(Monitor.id == monitor_id).values(**invalid))


@pytest.mark.asyncio
async def test_job_cycle_uniqueness_open_index_and_terminal_constraints(pg_engine):
    async with pg_engine.begin() as connection:
        _, _, monitor_id = await seed(connection)
        first = job_values(monitor_id)
        await connection.execute(insert(CheckJob).values(**first))
        await rejects(
            connection,
            insert(CheckJob).values(
                **job_values(monitor_id, scheduled_at=NOW + timedelta(seconds=1))
            ),
        )
        await rejects(
            connection, update(CheckJob).where(CheckJob.id == first["id"]).values(status="running")
        )
        await rejects(
            connection,
            update(CheckJob).where(CheckJob.id == first["id"]).values(status="completed"),
        )
        await connection.execute(
            update(CheckJob)
            .where(CheckJob.id == first["id"])
            .values(status="completed", finished_at=NOW)
        )
        await rejects(
            connection,
            insert(CheckJob).values(**job_values(monitor_id, status="completed", finished_at=NOW)),
        )
        await connection.execute(
            insert(CheckJob).values(
                **job_values(monitor_id, scheduled_at=NOW + timedelta(seconds=1))
            )
        )


@pytest.mark.parametrize("field", ["monitor_id", "config_version", "scheduled_at"])
@pytest.mark.asyncio
async def test_result_must_match_job_full_identity(pg_engine, field):
    async with pg_engine.begin() as connection:
        _, project_id, monitor_id = await seed(connection)
        another = uuid4()
        await connection.execute(
            insert(Monitor).values(
                id=another, project_id=project_id, name="Other", url="https://example.test"
            )
        )
        job = job_values(monitor_id)
        await connection.execute(insert(CheckJob).values(**job))
        override = {
            "monitor_id": another,
            "config_version": 2,
            "scheduled_at": NOW - timedelta(seconds=1),
        }[field]
        await rejects(
            connection, insert(CheckResult).values(**result_values(job, **{field: override}))
        )
        await connection.execute(insert(CheckResult).values(**result_values(job)))
        await rejects(connection, insert(CheckResult).values(**result_values(job)))


@pytest.mark.asyncio
async def test_incident_order_uniqueness_and_retention_foreign_keys(pg_engine):
    async with pg_engine.begin() as connection:
        _, _, monitor_id = await seed(connection)
        job = job_values(monitor_id)
        result = result_values(job)
        await connection.execute(insert(CheckJob).values(**job))
        await connection.execute(insert(CheckResult).values(**result))
        incident = incident_values(
            monitor_id, opening_check_id=result["id"], closing_check_id=result["id"]
        )
        await connection.execute(insert(Incident).values(**incident))
        await rejects(connection, insert(Incident).values(**incident_values(monitor_id)))
        await rejects(
            connection,
            update(Incident)
            .where(Incident.id == incident["id"])
            .values(ended_at=NOW - timedelta(seconds=1), end_reason="recovered"),
        )
        await rejects(
            connection, update(Incident).where(Incident.id == incident["id"]).values(ended_at=NOW)
        )
        await rejects(connection, delete(CheckJob).where(CheckJob.id == job["id"]))
        await connection.execute(delete(CheckResult).where(CheckResult.id == result["id"]))
        evidence = (
            await connection.execute(
                select(Incident.opening_check_id, Incident.closing_check_id).where(
                    Incident.id == incident["id"]
                )
            )
        ).one()
        assert evidence == (None, None)
        await connection.execute(delete(CheckJob).where(CheckJob.id == job["id"]))
        await connection.execute(
            update(Incident)
            .where(Incident.id == incident["id"])
            .values(ended_at=NOW, end_reason="recovered")
        )
        await connection.execute(insert(Incident).values(**incident_values(monitor_id)))


@pytest.mark.parametrize("kind", ["job", "incident"])
@pytest.mark.asyncio
async def test_concurrent_open_records_block_then_reject(pg_engine, kind):
    async with pg_engine.begin() as connection:
        _, _, monitor_id = await seed(connection)
    model = CheckJob if kind == "job" else Incident
    first = job_values(monitor_id) if kind == "job" else incident_values(monitor_id)
    second = (
        job_values(monitor_id, scheduled_at=NOW + timedelta(seconds=1))
        if kind == "job"
        else incident_values(monitor_id)
    )
    async with pg_engine.connect() as owner, pg_engine.connect() as competitor:
        pid = await competitor.scalar(text("SELECT pg_backend_pid()"))
        await competitor.commit()
        await owner.execute(insert(model).values(**first))

        async def compete():
            with pytest.raises(IntegrityError):
                await competitor.execute(insert(model).values(**second))
            await competitor.rollback()

        task = asyncio.create_task(compete())
        try:
            async with pg_engine.connect() as observer:
                async with asyncio.timeout(5):
                    while not await observer.scalar(
                        text("SELECT cardinality(pg_blocking_pids(:pid)) > 0"), {"pid": pid}
                    ):
                        await asyncio.sleep(0.01)
            assert not task.done()
            await owner.commit()
            await asyncio.wait_for(task, timeout=5)
        finally:
            await owner.rollback()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    async with pg_engine.connect() as connection:
        assert await connection.scalar(select(func.count()).select_from(model)) == 1
