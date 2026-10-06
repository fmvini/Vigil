"""Synthetic executors on UUID PG schemas; never resolve or call monitor targets."""

from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select, text

from app.config import Settings
from app.db.models import CheckJob, CheckResult, Monitor
from app.monitoring.batch import run_batch
from app.monitoring.executor import OperationalError
from app.readiness import migration_head
from app.security import utcnow
from app.services.check_jobs import EvaluatedCycle


@pytest.fixture
async def batch_fixture(api_app, authenticated, project):
    if api_app.state.engine.dialect.name != "postgresql":
        pytest.skip("Batch requires PostgreSQL, SQLite variant is intentionally unsupported")
    async with api_app.state.engine.begin() as db:
        # Shared fixtures create ORM metadata; declare a version only in this owned schema
        # to exercise the revision gate. This is not migration/catalog parity proof.
        await db.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(64) PRIMARY KEY)"))
        await db.execute(
            text("INSERT INTO alembic_version VALUES (:head)"), {"head": migration_head()}
        )
    monitors = []
    for index in range(3):
        response = await authenticated.post(
            f"/api/v1/projects/{project['id']}/monitors",
            json={
                "name": f"Synthetic {index}",
                "url": "https://no-network.example",
                "interval_seconds": 900,
            },
        )
        assert response.status_code == 201
        monitors.append(response.json())
    async with api_app.state.session_factory.begin() as db:
        for monitor in monitors:
            entity = await db.get(Monitor, UUID(monitor["id"]))
            entity.next_check_at = utcnow() - timedelta(seconds=898)
    settings = Settings(
        pipeline_enabled=True,
        monitoring_network_enabled=True,
        redis_enabled=False,
        minimum_interval_seconds=900,
    )
    return api_app, settings, monitors


class SyntheticSuccess:
    def __init__(self, factory):
        self.factory, self.calls = factory, 0

    async def run(self, claim):
        self.calls += 1
        async with self.factory() as db:
            job = await db.get(CheckJob, claim.job_id)
            assert job.status == "running" and job.lease_token == claim.lease_token
            # A late runner gets a fresh full interval, not the two seconds left on old slots.
            assert (job.expires_at - job.scheduled_at).total_seconds() == 900
            assert (job.scheduled_at - utcnow()).total_seconds() > -10
        now = utcnow()
        return EvaluatedCycle(
            claim.started_at,
            now,
            "success",
            200,
            10.0,
            10.0,
            1,
            [{"http_status": 200, "latency_ms": 10.0, "duration_ms": 10.0}],
        )


async def test_batch_real_pg_fresh_slots_commit_results_retention_and_no_duplicate(batch_fixture):
    app, settings, monitors = batch_fixture
    executor = SyntheticSuccess(app.state.session_factory)
    report = await run_batch(settings, engine=app.state.engine, executor=executor, concurrency=2)
    assert report["status"] == "ok" and report["job_states"] == {"completed": 3}
    assert executor.calls == 3
    async with app.state.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(CheckResult)) == 3
        jobs = (await db.scalars(select(CheckJob))).all()
        assert all(job.execution_count == 1 for job in jobs)
    second = await run_batch(settings, engine=app.state.engine, executor=executor)
    assert second["jobs_admitted"] == 0 and executor.calls == 3


async def test_batch_real_pg_operational_retries_do_not_create_target_failures(batch_fixture):
    app, settings, _ = batch_fixture
    calls = []

    class Blocked:
        async def run(self, claim):
            calls.append(claim.job_id)
            raise OperationalError("blocked_destination")

    report = await run_batch(
        settings, engine=app.state.engine, executor=Blocked(), retention_batches=0
    )
    assert report["status"] == "partial" and report["job_states"] == {"exhausted": 3}
    assert len(calls) == 9
    async with app.state.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(CheckResult)) == 0
        jobs = (await db.scalars(select(CheckJob))).all()
        assert all(
            job.execution_count == 3 and job.error_code == "blocked_destination" for job in jobs
        )


async def test_batch_real_pg_legacy_monitor_below_minimum_is_not_scheduled(batch_fixture):
    app, settings, monitors = batch_fixture
    async with app.state.session_factory.begin() as db:
        monitor = await db.get(Monitor, UUID(monitors[0]["id"]))
        monitor.interval_seconds = 60
    executor = SyntheticSuccess(app.state.session_factory)
    report = await run_batch(
        settings, engine=app.state.engine, executor=executor, retention_batches=0
    )
    assert report["job_states"] == {"completed": 2} and executor.calls == 2
