"""Real PostgreSQL retention, foreign keys, row locks and CLI transaction tests."""

import argparse
from datetime import timedelta
from itertools import count
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, text, update
from test_db_postgresql import NOW, seed
from test_db_postgresql import pg_engine as pg_engine

from app.db.models import CheckJob, CheckResult, Incident, Monitor, Project, Session
from app.db.session import create_engine, create_session_factory
from app.services import retention
from app.services.retention import retain_batch

SLOT_SEQUENCE = count(1)


async def add_job(
    connection, monitor_id, *, finished_at=None, status="completed", scheduled_at=None
):
    job_id = uuid4()
    scheduled_at = scheduled_at or (finished_at or NOW - timedelta(days=60)) - timedelta(seconds=2)
    scheduled_at -= timedelta(microseconds=next(SLOT_SEQUENCE))
    values = dict(
        id=job_id,
        monitor_id=monitor_id,
        config_version=1,
        config_snapshot={},
        scheduled_at=scheduled_at,
        expires_at=scheduled_at + timedelta(seconds=60),
        budget_ms=13600,
        status=status,
        finished_at=finished_at,
    )
    if status == "running":
        values.update(
            lease_token=uuid4(),
            lease_expires_at=NOW + timedelta(seconds=90),
            started_at=scheduled_at,
            execution_count=1,
        )
    await connection.execute(insert(CheckJob).values(**values))
    return job_id, scheduled_at


async def add_result(connection, monitor_id, *, completed_at=None, finished_at=None):
    completed_at = completed_at or NOW - timedelta(days=31)
    finished_at = finished_at or completed_at
    job_id, scheduled_at = await add_job(
        connection,
        monitor_id,
        finished_at=finished_at,
        scheduled_at=min(finished_at, completed_at) - timedelta(seconds=2),
    )
    result_id = uuid4()
    await connection.execute(
        insert(CheckResult).values(
            id=result_id,
            job_id=job_id,
            monitor_id=monitor_id,
            config_version=1,
            scheduled_at=scheduled_at,
            started_at=completed_at - timedelta(seconds=1),
            completed_at=completed_at,
            outcome="failure",
            cycle_duration_ms=1000,
            queue_delay_ms=0,
            attempt_count=1,
            attempts=[{"error_code": "timeout", "duration_ms": 1000}],
            error_code="timeout",
            health_after="offline",
        )
    )
    return result_id, job_id


async def add_incident(connection, monitor_id, *, ended_at=None, opening=None, closing=None):
    incident_id = uuid4()
    start = min(ended_at or NOW, NOW - timedelta(days=100)) - timedelta(seconds=1)
    await connection.execute(
        insert(Incident).values(
            id=incident_id,
            monitor_id=monitor_id,
            started_at=start,
            detected_at=start,
            ended_at=ended_at,
            end_reason="recovered" if ended_at else None,
            cause_code="timeout",
            failure_threshold_snapshot=3,
            opening_check_id=opening,
            closing_check_id=closing,
        )
    )
    return incident_id


async def add_session(connection, user_id, *, expires_at=None, revoked_at=None, last_seen_at=None):
    session_id = uuid4()
    expires_at = expires_at or NOW - timedelta(days=2)
    last_seen_at = last_seen_at or NOW - timedelta(days=8)
    created_at = min(expires_at, last_seen_at, revoked_at or NOW) - timedelta(days=1)
    await connection.execute(
        insert(Session).values(
            id=session_id,
            user_id=user_id,
            token_hash=uuid4().hex + uuid4().hex,
            csrf_token="csrf-test",
            created_at=created_at,
            last_seen_at=last_seen_at,
            expires_at=expires_at,
            revoked_at=revoked_at,
        )
    )
    return session_id


async def call(engine, **kwargs):
    async with create_session_factory(engine).begin() as db:
        return await retain_batch(db, now=NOW, **kwargs)


async def ids(engine, model):
    async with engine.connect() as connection:
        return set((await connection.scalars(select(model.id))).all())


@pytest.mark.asyncio
async def test_retention_ttls_evidence_null_and_snapshot_unchanged(pg_engine):
    async with pg_engine.begin() as connection:
        user_id, project_id, monitor_id = await seed(connection)
        await connection.execute(
            update(Monitor)
            .where(Monitor.id == monitor_id)
            .values(
                health_status="offline",
                consecutive_failures=3,
                first_failure_at=NOW - timedelta(days=31),
                last_checked_at=NOW - timedelta(days=31),
                last_scheduled_at=NOW - timedelta(days=31),
                last_latency_ms=50,
                last_http_status=503,
                last_outcome="failure",
                last_error_code="timeout",
            )
        )
        old_result, old_job = await add_result(connection, monitor_id)
        recent_result, recent_job = await add_result(
            connection, monitor_id, completed_at=NOW - timedelta(days=1)
        )
        boundary_result, boundary_job = await add_result(
            connection, monitor_id, completed_at=NOW - timedelta(days=30)
        )
        referenced_recent, referenced_old_job = await add_result(
            connection,
            monitor_id,
            completed_at=NOW - timedelta(days=1),
            finished_at=NOW - timedelta(days=31),
        )
        old_result_new_job, new_parent = await add_result(
            connection,
            monitor_id,
            completed_at=NOW - timedelta(days=31),
            finished_at=NOW - timedelta(days=1),
        )
        expired_job, _ = await add_job(
            connection, monitor_id, finished_at=NOW - timedelta(days=31), status="expired"
        )
        cancelled_job, _ = await add_job(
            connection, monitor_id, finished_at=NOW - timedelta(days=31), status="cancelled"
        )
        exhausted_job, _ = await add_job(
            connection, monitor_id, finished_at=NOW - timedelta(days=31), status="exhausted"
        )
        open_incident = await add_incident(connection, monitor_id, opening=old_result)
        closed_evidence = await add_incident(
            connection,
            monitor_id,
            ended_at=NOW - timedelta(days=1),
            opening=old_result,
            closing=old_result,
        )
        old_incident = await add_incident(connection, monitor_id, ended_at=NOW - timedelta(days=91))
        boundary_incident = await add_incident(
            connection, monitor_id, ended_at=NOW - timedelta(days=90)
        )
        # Expired recently, but idle-invalid more than 7d; timestamps select the earlier event.
        idle_old = await add_session(
            connection, user_id, last_seen_at=NOW - timedelta(days=8, seconds=1)
        )
        revoked_old = await add_session(connection, user_id, revoked_at=NOW - timedelta(days=8))
        expired_old = await add_session(connection, user_id, expires_at=NOW - timedelta(days=8))
        boundary_session = await add_session(
            connection, user_id, expires_at=NOW - timedelta(days=7)
        )
        valid_session = await add_session(
            connection, user_id, expires_at=NOW + timedelta(days=1), last_seen_at=NOW
        )
        recent_revocation = await add_session(
            connection, user_id, revoked_at=NOW - timedelta(days=1)
        )
        snapshot = dict(
            (await connection.execute(select(Monitor.__table__).where(Monitor.id == monitor_id)))
            .one()
            ._mapping
        )
        project_snapshot = dict(
            (await connection.execute(select(Project.__table__).where(Project.id == project_id)))
            .one()
            ._mapping
        )

    counts = await call(pg_engine)
    assert counts.check_results == 2
    assert counts.check_jobs == 4
    assert counts.incidents == 1
    assert counts.sessions == 3
    assert await ids(pg_engine, CheckResult) == {recent_result, boundary_result, referenced_recent}
    assert await ids(pg_engine, CheckJob) == {
        recent_job,
        boundary_job,
        referenced_old_job,
        new_parent,
    }
    assert await ids(pg_engine, Incident) == {open_incident, closed_evidence, boundary_incident}
    assert await ids(pg_engine, Session) == {boundary_session, valid_session, recent_revocation}
    async with pg_engine.connect() as connection:
        after = dict(
            (await connection.execute(select(Monitor.__table__).where(Monitor.id == monitor_id)))
            .one()
            ._mapping
        )
        assert after == snapshot
        assert (
            dict(
                (
                    await connection.execute(
                        select(Project.__table__).where(Project.id == project_id)
                    )
                )
                .one()
                ._mapping
            )
            == project_snapshot
        )
        for incident_id in (open_incident, closed_evidence):
            evidence = (
                await connection.execute(
                    select(Incident.opening_check_id, Incident.closing_check_id).where(
                        Incident.id == incident_id
                    )
                )
            ).one()
            assert evidence == (None, None)
    assert counts.computed_at == NOW
    assert old_result not in await ids(pg_engine, CheckResult)
    remaining_jobs = await ids(pg_engine, CheckJob)
    assert all(
        job not in remaining_jobs for job in (old_job, expired_job, cancelled_job, exhausted_job)
    )
    assert old_incident not in await ids(pg_engine, Incident)
    remaining_sessions = await ids(pg_engine, Session)
    assert all(
        session not in remaining_sessions for session in (idle_old, revoked_old, expired_old)
    )
    assert old_result_new_job not in await ids(pg_engine, CheckResult)


@pytest.mark.parametrize("status", ["pending", "running"])
@pytest.mark.asyncio
async def test_open_jobs_never_deleted_even_if_schedule_is_ancient(pg_engine, status):
    async with pg_engine.begin() as connection:
        _, _, monitor_id = await seed(connection)
        job_id, _ = await add_job(connection, monitor_id, status=status)
    assert (await call(pg_engine)).total == 0
    assert await ids(pg_engine, CheckJob) == {job_id}


@pytest.mark.asyncio
async def test_batch_size_limits_each_entity_and_repeated_batches_are_idempotent(pg_engine):
    async with pg_engine.begin() as connection:
        user_id, _, monitor_id = await seed(connection)
        for index in range(3):
            await add_result(
                connection, monitor_id, completed_at=NOW - timedelta(days=31, seconds=index)
            )
            await add_incident(
                connection, monitor_id, ended_at=NOW - timedelta(days=91, seconds=index)
            )
            await add_session(
                connection, user_id, expires_at=NOW - timedelta(days=8, seconds=index)
            )
    first = await call(pg_engine, batch_size=2)
    assert (first.check_results, first.check_jobs, first.incidents, first.sessions) == (2, 2, 2, 2)
    second = await call(pg_engine, batch_size=2)
    assert (second.check_results, second.check_jobs, second.incidents, second.sessions) == (
        1,
        1,
        1,
        1,
    )
    assert (await call(pg_engine, batch_size=2)).total == 0


@pytest.mark.parametrize("kind", ["result", "job", "incident", "session"])
@pytest.mark.asyncio
async def test_retention_skips_occupied_source_rows(pg_engine, kind):
    async with pg_engine.begin() as connection:
        user_id, _, monitor_id = await seed(connection)
        candidates = []
        for index in (2, 1):
            timestamp = NOW - timedelta(days=100, seconds=index)
            if kind == "result":
                candidates.append(
                    (await add_result(connection, monitor_id, completed_at=timestamp))[0]
                )
            elif kind == "job":
                candidates.append((await add_job(connection, monitor_id, finished_at=timestamp))[0])
            elif kind == "incident":
                candidates.append(await add_incident(connection, monitor_id, ended_at=timestamp))
            else:
                candidates.append(
                    await add_session(
                        connection,
                        user_id,
                        expires_at=timestamp,
                        last_seen_at=timestamp - timedelta(days=1),
                    )
                )
    model = {"result": CheckResult, "job": CheckJob, "incident": Incident, "session": Session}[kind]
    async with pg_engine.begin() as owner:
        await owner.execute(select(model.id).where(model.id == candidates[0]).with_for_update())
        async with create_session_factory(pg_engine).begin() as db:
            await db.execute(text("SET LOCAL lock_timeout = '100ms'"))
            counts = await retain_batch(db, now=NOW, batch_size=1)
            assert (
                getattr(
                    counts,
                    {
                        "result": "check_results",
                        "job": "check_jobs",
                        "incident": "incidents",
                        "session": "sessions",
                    }[kind],
                )
                == 1
            )
    assert await ids(pg_engine, model) == {candidates[0]}


@pytest.mark.asyncio
async def test_locked_evidence_skips_result_without_blocking_fk_set_null(pg_engine):
    async with pg_engine.begin() as connection:
        _, _, monitor_id = await seed(connection)
        result_id, job_id = await add_result(connection, monitor_id)
        other_result, other_job = await add_result(
            connection, monitor_id, completed_at=NOW - timedelta(days=32)
        )
        incident_id = await add_incident(connection, monitor_id, opening=result_id)
    async with pg_engine.begin() as owner:
        await owner.execute(select(Incident.id).where(Incident.id == incident_id).with_for_update())
        async with create_session_factory(pg_engine).begin() as db:
            await db.execute(text("SET LOCAL lock_timeout = '100ms'"))
            counts = await retain_batch(db, now=NOW, batch_size=2)
            assert counts.check_results == counts.check_jobs == 1
            assert counts.incidents == 0
    assert await ids(pg_engine, CheckResult) == {result_id}
    assert await ids(pg_engine, CheckJob) == {job_id}
    assert other_result not in await ids(pg_engine, CheckResult)
    assert other_job not in await ids(pg_engine, CheckJob)
    second = await call(pg_engine)
    assert second.check_results == second.check_jobs == 1
    assert await ids(pg_engine, Incident) == {incident_id}


@pytest.mark.asyncio
async def test_concurrent_janitors_take_disjoint_batches(pg_engine):
    async with pg_engine.begin() as connection:
        user_id, _, monitor_id = await seed(connection)
        for index in range(4):
            await add_result(
                connection, monitor_id, completed_at=NOW - timedelta(days=31, seconds=index)
            )
            await add_incident(
                connection, monitor_id, ended_at=NOW - timedelta(days=91, seconds=index)
            )
            await add_session(
                connection, user_id, expires_at=NOW - timedelta(days=8, seconds=index)
            )
    factory = create_session_factory(pg_engine)
    async with factory.begin() as first:
        first_counts = await retain_batch(first, now=NOW, batch_size=2)
        async with factory.begin() as second:
            await second.execute(text("SET LOCAL lock_timeout = '100ms'"))
            second_counts = await retain_batch(second, now=NOW, batch_size=2)
        assert first_counts.total == second_counts.total == 8
    for model in (CheckResult, CheckJob, Incident, Session):
        assert await ids(pg_engine, model) == set()


@pytest.mark.asyncio
async def test_rollback_restores_rows_and_evidence_no_internal_commit(pg_engine):
    async with pg_engine.begin() as connection:
        user_id, _, monitor_id = await seed(connection)
        result_id, job_id = await add_result(connection, monitor_id)
        open_incident = await add_incident(
            connection, monitor_id, opening=result_id, closing=result_id
        )
        old_incident = await add_incident(connection, monitor_id, ended_at=NOW - timedelta(days=91))
        session_id = await add_session(connection, user_id, expires_at=NOW - timedelta(days=8))
    factory = create_session_factory(pg_engine)
    with pytest.raises(RuntimeError, match="before commit"):
        async with factory.begin() as db:
            assert (await retain_batch(db, now=NOW)).total == 4
            # Another connection still sees committed rows while cleanup remains uncommitted.
            assert await ids(pg_engine, CheckResult) == {result_id}
            raise RuntimeError("before commit")
    assert await ids(pg_engine, CheckResult) == {result_id}
    assert await ids(pg_engine, CheckJob) == {job_id}
    assert await ids(pg_engine, Incident) == {open_incident, old_incident}
    assert await ids(pg_engine, Session) == {session_id}
    async with pg_engine.connect() as connection:
        row = (
            await connection.execute(
                select(Incident.opening_check_id, Incident.closing_check_id).where(
                    Incident.id == open_incident
                )
            )
        ).one()
        assert row == (result_id, result_id)


@pytest.mark.asyncio
async def test_session_activity_locked_and_refreshed_is_not_deleted(pg_engine):
    async with pg_engine.begin() as connection:
        user_id, _, _ = await seed(connection)
        session_id = await add_session(connection, user_id, last_seen_at=NOW - timedelta(days=9))
    async with pg_engine.begin() as owner:
        await owner.execute(
            update(Session).where(Session.id == session_id).values(last_seen_at=NOW)
        )
        assert (await call(pg_engine)).sessions == 0
    assert (await call(pg_engine)).sessions == 0
    assert await ids(pg_engine, Session) == {session_id}


@pytest.mark.asyncio
async def test_configured_idle_expiry_and_exact_seven_day_boundary(pg_engine):
    async with pg_engine.begin() as connection:
        user_id, _, _ = await seed(connection)
        stale = await add_session(
            connection, user_id, last_seen_at=NOW - timedelta(days=7, seconds=61)
        )
        boundary = await add_session(
            connection, user_id, last_seen_at=NOW - timedelta(days=7, seconds=60)
        )
    assert (await call(pg_engine, session_idle_seconds=60)).sessions == 1
    assert await ids(pg_engine, Session) == {boundary}
    assert stale not in await ids(pg_engine, Session)


@pytest.mark.asyncio
async def test_cli_real_postgresql_dry_run_rolls_back_and_multiple_batches_commit(
    pg_engine, monkeypatch
):
    async with pg_engine.begin() as connection:
        _, _, monitor_id = await seed(connection)
        for index in range(3):
            await add_result(
                connection, monitor_id, completed_at=NOW - timedelta(days=31, seconds=index)
            )
    monkeypatch.setattr(retention, "create_engine", lambda *args, **kwargs: pg_engine)
    settings = SimpleNamespace(
        database_url=str(pg_engine.url), session_idle_seconds=86400, database_options={}
    )
    dry_args = argparse.Namespace(batch_size=2, max_batches=5, dry_run=True)
    preview = await retention._run_cli(dry_args, settings)
    assert len(preview) == 1 and preview[0].check_results == 2
    assert len(await ids(pg_engine, CheckResult)) == 3
    args = argparse.Namespace(batch_size=2, max_batches=5, dry_run=False)
    applied = await retention._run_cli(args, settings)
    assert [batch.check_results for batch in applied] == [2, 1, 0]
    assert await ids(pg_engine, CheckResult) == set()
    assert await ids(pg_engine, CheckJob) == set()
    assert all(batch.computed_at.tzinfo is not None for batch in applied)


@pytest.mark.asyncio
async def test_retention_requires_caller_transaction_and_aware_time(pg_engine):
    async with create_session_factory(pg_engine)() as db:
        with pytest.raises(ValueError, match="caller-owned"):
            await retain_batch(db, now=NOW)
    async with create_session_factory(pg_engine).begin() as db:
        with pytest.raises(ValueError, match="timezone-aware"):
            await retain_batch(db, now=NOW.replace(tzinfo=None))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"batch_size": 0},
        {"batch_size": 1001},
        {"batch_size": True},
        {"batch_size": 1.5},
        {"session_idle_seconds": 0},
        {"session_idle_seconds": 86401},
        {"session_idle_seconds": True},
    ],
)
@pytest.mark.asyncio
async def test_invalid_limits_do_not_start_cleanup(pg_engine, kwargs):
    async with create_session_factory(pg_engine).begin() as db:
        with pytest.raises(ValueError):
            await retain_batch(db, now=NOW, **kwargs)


@pytest.mark.asyncio
async def test_retention_refuses_sqlite_unit_adapter():
    engine = create_engine("sqlite+aiosqlite:///:memory:", allow_sqlite_for_tests=True)
    try:
        async with create_session_factory(engine).begin() as db:
            with pytest.raises(ValueError, match="real PostgreSQL"):
                await retain_batch(db, now=NOW)
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["run-retention", "--batch-size", "0"],
        ["run-retention", "--batch-size", "1001"],
        ["run-retention", "--max-batches", "0"],
        ["run-retention", "--max-batches", "1001"],
    ],
)
def test_cli_requires_explicit_command_and_bounded_limits(args):
    with pytest.raises(SystemExit) as error:
        retention.main(args)
    assert error.value.code == 2


def test_cli_requires_explicit_database_and_never_prints_connection_secrets(monkeypatch, capsys):
    from app import config

    monkeypatch.setattr(config, "Settings", lambda: SimpleNamespace(model_fields_set=set()))
    with pytest.raises(SystemExit) as error:
        retention.main(["run-retention"])
    assert error.value.code == 2
    assert "explicit VIGIL_DATABASE_URL" in capsys.readouterr().err
    monkeypatch.setattr(
        config,
        "Settings",
        lambda: SimpleNamespace(
            model_fields_set={"database_url"},
            database_url="unused",
            session_idle_seconds=86400,
            database_options={},
        ),
    )

    def fail(*args, **kwargs):
        raise RuntimeError("postgresql://private-user:private-password@private-host/private-db")

    monkeypatch.setattr(retention, "create_engine", fail)
    assert retention.main(["run-retention"]) == 1
    error_text = capsys.readouterr().err
    assert "RuntimeError" in error_text
    assert all(
        secret not in error_text
        for secret in ("private-user", "private-password", "private-host", "private-db")
    )
