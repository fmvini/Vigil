"""Actual PG17 migration/catalog/integrity; no prescribed query plan or timing."""

import asyncio
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, insert, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
from test_db_postgresql import NOW, incident_values, job_values, result_values, seed

from app.db import retention_plan_qa as qa
from app.db.models import CheckJob, CheckResult, Incident, Monitor, Project
from app.db.session import create_engine

HEAD = "0002_incident_evidence_indexes"


def downgrade(connection, target):
    config = Config()
    config.set_main_option(
        "script_location", str(qa.Path(__file__).resolve().parents[1] / "migrations")
    )
    config.set_main_option(
        "sqlalchemy.url", "postgresql+asyncpg://offline:unused@localhost/offline"
    )
    config.attributes["connection"] = connection
    command.downgrade(config, target)


@pytest_asyncio.fixture
async def marked_pg17():
    url = os.environ.get("VIGIL_RETENTION_QA_DATABASE_URL")
    if not url:
        pytest.skip("Requires explicit disposable PG17 retention QA lease")
    lease = qa.lease_config(
        True, os.environ.get("VIGIL_RETENTION_QA_TOKEN"), make_url(url).host, os.environ
    )
    schema = "vigil_retention_test_" + uuid4().hex
    marker = f"vigil.retention.qa:{lease.token}:{schema}"
    admin = create_engine(url, poolclass=NullPool)
    scoped = create_engine(
        url,
        poolclass=NullPool,
        connect_args={
            "server_settings": {
                "search_path": schema,
                "timezone": "UTC",
                "statement_timeout": "30000",
                "lock_timeout": "1000",
            }
        },
    )
    started = False
    try:
        async with admin.begin() as connection:
            await qa.verify_server(connection)
            if await connection.scalar(
                text("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname=:schema)"),
                {"schema": schema},
            ):
                raise ValueError("Existing schema must be preserved")
            started = True
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.execute(text(f"COMMENT ON SCHEMA \"{schema}\" IS '{marker}'"))
        async with scoped.begin() as connection:
            await connection.run_sync(qa.migrate, qa.BASE_REVISION)
        yield scoped, schema
    finally:

        async def cleanup():
            try:
                await scoped.dispose()
                if started:
                    report = {}
                    await qa.drop_owned(admin, schema, marker, report)
                    assert report["schema_absent_after_cleanup"]
            finally:
                await admin.dispose()

        task = asyncio.create_task(asyncio.wait_for(cleanup(), 20))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise


async def populate(connection):
    user, project, monitor = await seed(connection)
    results = []
    for version in (1, 2):
        job = job_values(monitor, config_version=version, status="completed", finished_at=NOW)
        await connection.execute(insert(CheckJob).values(**job))
        result = result_values(job)
        await connection.execute(insert(CheckResult).values(**result))
        results.append(result["id"])
    closed = incident_values(
        monitor,
        opening_check_id=results[0],
        closing_check_id=results[1],
        ended_at=NOW,
        end_reason="recovered",
    )
    opened = incident_values(
        monitor, opening_check_id=results[0], closing_check_id=None, ended_at=None, end_reason=None
    )
    await connection.execute(insert(Incident), [closed, opened])
    return project, monitor, results


async def assert_catalog(connection, schema, expected_indexes):
    catalog = await qa.incident_catalog(connection, schema)
    definitions = {row["indexname"]: row["indexdef"] for row in catalog["indexes"]}
    assert set(qa.CANDIDATES) & set(definitions) == expected_indexes
    for name in expected_indexes:
        column = qa.CANDIDATES[name]
        assert f"USING btree ({column}) WHERE ({column} IS NOT NULL)" in definitions[name]
        assert "UNIQUE INDEX" not in definitions[name]
    for column in qa.CANDIDATES.values():
        nullable = await connection.scalar(
            text(
                "SELECT is_nullable FROM information_schema.columns WHERE table_schema=:schema "
                "AND table_name='incidents' AND column_name=:column"
            ),
            {"schema": schema, "column": column},
        )
        assert nullable == "YES"
        assert any(
            row["definition"]
            == f"FOREIGN KEY ({column}) REFERENCES check_results(id) ON DELETE SET NULL"
            for row in catalog["constraints"]
        )
    return catalog


@pytest.mark.postgres
async def test_index_upgrade_downgrade_preserves_rows_constraints_and_base(marked_pg17):
    engine, schema = marked_pg17
    async with engine.begin() as connection:
        await populate(connection)
        baseline = await qa.fingerprint(connection)
        base_catalog = await assert_catalog(connection, schema, set())
        assert (
            await connection.scalar(text("SELECT version_num FROM alembic_version"))
            == qa.BASE_REVISION
        )
        await connection.run_sync(qa.migrate, HEAD)
        catalog = await assert_catalog(connection, schema, set(qa.CANDIDATES))
        assert catalog["constraints"] == base_catalog["constraints"]
        assert await qa.fingerprint(connection) == baseline
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
        await connection.run_sync(downgrade, qa.BASE_REVISION)
        assert (
            await connection.scalar(text("SELECT version_num FROM alembic_version"))
            == qa.BASE_REVISION
        )
        restored = await assert_catalog(connection, schema, set())
        assert restored["constraints"] == base_catalog["constraints"]
        assert restored["indexes"] == base_catalog["indexes"]
        assert await qa.fingerprint(connection) == baseline
        await connection.run_sync(qa.migrate, HEAD)
        await assert_catalog(connection, schema, set(qa.CANDIDATES))


@pytest.mark.postgres
async def test_transactional_index_ddl_and_set_null_rollback(marked_pg17):
    engine, schema = marked_pg17
    async with engine.begin() as connection:
        project, monitor, results = await populate(connection)
        baseline = await qa.fingerprint(connection)
    # The ordinary CREATE INDEX and Alembic revision update both roll back.
    async with engine.connect() as connection:
        transaction = await connection.begin()
        await connection.run_sync(qa.migrate, HEAD)
        await assert_catalog(connection, schema, set(qa.CANDIDATES))
        await transaction.rollback()
    async with engine.begin() as connection:
        assert (
            await connection.scalar(text("SELECT version_num FROM alembic_version"))
            == qa.BASE_REVISION
        )
        await assert_catalog(connection, schema, set())
        assert await qa.fingerprint(connection) == baseline
        await connection.run_sync(qa.migrate, HEAD)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        await connection.execute(delete(CheckResult).where(CheckResult.id.in_(results)))
        evidence = (
            await connection.execute(select(Incident.opening_check_id, Incident.closing_check_id))
        ).all()
        assert len(evidence) == 2 and all(
            opening is None and closing is None for opening, closing in evidence
        )
        assert await connection.scalar(select(Project.id).where(Project.id == project)) == project
        assert await connection.scalar(select(Monitor.id).where(Monitor.id == monitor)) == monitor
        await transaction.rollback()
    async with engine.begin() as connection:
        assert await qa.fingerprint(connection) == baseline
        await connection.execute(delete(CheckResult).where(CheckResult.id.in_(results)))
    async with engine.connect() as connection:
        evidence = (
            await connection.execute(select(Incident.opening_check_id, Incident.closing_check_id))
        ).all()
        assert len(evidence) == 2 and all(
            opening is None and closing is None for opening, closing in evidence
        )
        assert await connection.scalar(select(Project.id).where(Project.id == project)) == project
        assert await connection.scalar(select(Monitor.id).where(Monitor.id == monitor)) == monitor
