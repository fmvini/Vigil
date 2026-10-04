"""Database pipeline integration tests, always against real PostgreSQL migrations."""

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text, update
from test_db_postgresql import NOW, seed
from test_db_postgresql import pg_engine as pg_engine

from app.api.schemas import MonitorPatch
from app.db.models import CheckJob, CheckResult, Incident, Monitor, Project
from app.db.session import create_session_factory
from app.services.check_jobs import (
    EvaluatedCycle,
    claim_job,
    cycle_budget_ms,
    finalize_job,
    reconcile_jobs,
    record_job_error,
    schedule_due,
)
from app.services.resources import owned_monitor, patch_monitor, set_paused


async def setup_monitor(engine, **values):
    async with engine.begin() as connection:
        user_id, project_id, monitor_id = await seed(connection)
        await connection.execute(
            update(Monitor).where(Monitor.id == monitor_id).values(next_check_at=NOW, **values)
        )
    return user_id, project_id, monitor_id


async def call(engine, function, *args, **kwargs):
    async with create_session_factory(engine).begin() as db:
        return await function(db, *args, **kwargs)


def evaluated(claim, *, outcome="success", latency=100, attempts=1, duration=1000):
    start = claim.started_at
    status = 200 if outcome == "success" else None
    error = None if outcome == "success" else "timeout"
    summaries = [{"error_code": "timeout", "duration_ms": 5000}] * (attempts - 1)
    summaries += [
        {"http_status": status, "error_code": error, "latency_ms": latency, "duration_ms": duration}
    ]
    return EvaluatedCycle(
        start,
        start + timedelta(seconds=1),
        outcome,
        status,
        latency,
        duration,
        attempts,
        summaries,
        error,
    )


def test_cycle_budget_worst_case_jitter():
    assert cycle_budget_ms(5000, 1, 60) == 13600
    assert cycle_budget_ms(15000, 2, 60) == 49800
    assert cycle_budget_ms(1000, 0, 60) == 4000
    with pytest.raises(ValueError):
        cycle_budget_ms(15000, 2, 49)


@pytest.mark.asyncio
async def test_schedule_latest_slot_snapshot_and_duplicate_tick(pg_engine):
    _, _, monitor_id = await setup_monitor(pg_engine)
    late = NOW + timedelta(seconds=185)
    ids = await call(pg_engine, schedule_due, now=late)
    assert len(ids) == 1
    assert await call(pg_engine, schedule_due, now=late) == []
    async with create_session_factory(pg_engine)() as db:
        job, monitor = await db.get(CheckJob, ids[0]), await db.get(Monitor, monitor_id)
        assert job.scheduled_at == NOW + timedelta(seconds=180)
        assert job.skipped_slots == 3
        assert job.expires_at == NOW + timedelta(seconds=240)
        assert monitor.next_check_at == job.expires_at
        assert job.budget_ms == 13600
        assert job.config_snapshot["url"] == "https://example.test"
        assert job.config_snapshot["expected_status"] == 200
        assert job.config_snapshot["latency_threshold_ms"] == 1000
        assert job.config_version == monitor.config_version == 1


@pytest.mark.asyncio
async def test_scheduler_skips_locked_monitor_in_second_transaction(pg_engine):
    await setup_monitor(pg_engine)
    factory = create_session_factory(pg_engine)
    async with factory.begin() as first:
        ids = await schedule_due(first, now=NOW)
        async with factory.begin() as second:
            assert await asyncio.wait_for(schedule_due(second, now=NOW), 2) == []
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(CheckJob)) == len(ids) == 1


@pytest.mark.asyncio
async def test_schedule_rollback_does_not_advance_or_leave_job(pg_engine):
    _, _, monitor_id = await setup_monitor(pg_engine)
    factory = create_session_factory(pg_engine)
    with pytest.raises(RuntimeError):
        async with factory.begin() as db:
            assert await schedule_due(db, now=NOW)
            raise RuntimeError("transaction aborted")
    async with factory() as db:
        assert (await db.get(Monitor, monitor_id)).next_check_at == NOW
        assert await db.scalar(select(func.count()).select_from(CheckJob)) == 0


@pytest.mark.asyncio
async def test_finalize_idempotent_health_incident_and_recovery(pg_engine):
    _, project_id, monitor_id = await setup_monitor(pg_engine, failure_threshold=1)
    job_id = (await call(pg_engine, schedule_due, now=NOW))[0]
    claim = await call(pg_engine, claim_job, job_id, now=NOW)
    failure = evaluated(claim, outcome="failure", latency=None)
    assert await call(
        pg_engine, finalize_job, job_id, claim.lease_token, failure, now=failure.completed_at
    )
    assert not await call(
        pg_engine, finalize_job, job_id, claim.lease_token, failure, now=failure.completed_at
    )
    async with create_session_factory(pg_engine)() as db:
        monitor = await db.get(Monitor, monitor_id)
        assert monitor.health_status == "offline"
        assert monitor.consecutive_failures == 1
        assert (await db.get(Project, project_id)).revision == 1
        incident = await db.scalar(select(Incident))
        assert incident.started_at == NOW
        assert incident.detected_at == failure.completed_at
        assert incident.ended_at is None
        assert await db.scalar(select(func.count()).select_from(CheckResult)) == 1
    second_time = NOW + timedelta(seconds=60)
    next_id = (await call(pg_engine, schedule_due, now=second_time))[0]
    recovered = await call(pg_engine, claim_job, next_id, now=second_time)
    success = evaluated(recovered, latency=1500, attempts=2)
    assert await call(
        pg_engine, finalize_job, next_id, recovered.lease_token, success, now=success.completed_at
    )
    async with create_session_factory(pg_engine)() as db:
        assert (await db.get(Monitor, monitor_id)).health_status == "degraded"
        result = await db.scalar(select(CheckResult).where(CheckResult.job_id == next_id))
        assert result.degradation_reason == "retry_recovered"
        assert result.queue_delay_ms == 0
        incident = await db.scalar(select(Incident))
        assert incident.end_reason == "recovered"
        assert incident.ended_at == success.completed_at
        assert incident.closing_check_id == result.id
        assert (await db.get(Project, project_id)).revision == 2


@pytest.mark.asyncio
async def test_finalize_transaction_rollback_is_atomic(pg_engine):
    _, project_id, monitor_id = await setup_monitor(pg_engine, failure_threshold=1)
    job_id = (await call(pg_engine, schedule_due, now=NOW))[0]
    claim = await call(pg_engine, claim_job, job_id, now=NOW)
    result = evaluated(claim, outcome="failure", latency=None)
    factory = create_session_factory(pg_engine)
    with pytest.raises(RuntimeError):
        async with factory.begin() as db:
            assert await finalize_job(
                db, job_id, claim.lease_token, result, now=result.completed_at
            )
            raise RuntimeError("failure before commit")
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(CheckResult)) == 0
        assert await db.scalar(select(func.count()).select_from(Incident)) == 0
        assert (await db.get(CheckJob, job_id)).status == "running"
        assert (await db.get(Monitor, monitor_id)).health_status is None
        assert (await db.get(Project, project_id)).revision == 0
    assert await call(
        pg_engine, finalize_job, job_id, claim.lease_token, result, now=result.completed_at
    )


@pytest.mark.asyncio
async def test_running_job_near_deadline_not_expired_by_duplicate_or_reconciler(pg_engine):
    await setup_monitor(pg_engine)
    job_id = (await call(pg_engine, schedule_due, now=NOW))[0]
    claim = await call(pg_engine, claim_job, job_id, now=NOW)
    near = NOW + timedelta(seconds=50)
    assert await call(pg_engine, claim_job, job_id, now=near) is None
    assert await call(pg_engine, reconcile_jobs, now=near) == 0
    result = evaluated(claim)
    assert await call(pg_engine, finalize_job, job_id, claim.lease_token, result, now=near)


@pytest.mark.asyncio
async def test_expired_lease_retry_token_fences_old_worker(pg_engine):
    await setup_monitor(pg_engine, interval_seconds=3600)
    job_id = (await call(pg_engine, schedule_due, now=NOW))[0]
    first = await call(pg_engine, claim_job, job_id, now=NOW, lease_seconds=2)
    stale_time = NOW + timedelta(seconds=3)
    assert not await call(
        pg_engine, finalize_job, job_id, first.lease_token, evaluated(first), now=stale_time
    )
    assert await call(pg_engine, reconcile_jobs, now=stale_time) == 1
    assert await call(pg_engine, claim_job, job_id, now=stale_time) is None
    second_time = stale_time + timedelta(seconds=1)
    second = await call(pg_engine, claim_job, job_id, now=second_time)
    assert second.lease_token != first.lease_token
    assert not await call(
        pg_engine, finalize_job, job_id, first.lease_token, evaluated(first), now=second_time
    )
    result = evaluated(second)
    assert await call(
        pg_engine, finalize_job, job_id, second.lease_token, result, now=result.completed_at
    )
    async with create_session_factory(pg_engine)() as db:
        assert (await db.get(CheckJob, job_id)).execution_count == 2
        assert await db.scalar(select(func.count()).select_from(CheckResult)) == 1


@pytest.mark.asyncio
async def test_technical_retry_max_three_and_exclusion_preserves_offline(pg_engine):
    _, _, monitor_id = await setup_monitor(
        pg_engine,
        interval_seconds=3600,
        health_status="offline",
        consecutive_failures=3,
        first_failure_at=NOW,
    )
    job_id = (await call(pg_engine, schedule_due, now=NOW))[0]
    current = NOW
    for execution in range(1, 4):
        claim = await call(pg_engine, claim_job, job_id, now=current)
        assert claim is not None
        assert await call(
            pg_engine, record_job_error, job_id, claim.lease_token, "internal_error", now=current
        )
        assert await call(pg_engine, claim_job, job_id, now=current) is None
        current += timedelta(seconds=1 if execution == 1 else 2)
    async with create_session_factory(pg_engine)() as db:
        job = await db.get(CheckJob, job_id)
        assert job.execution_count == 3
        assert job.status == "exhausted"
        assert job.lease_token is None
        monitor = await db.get(Monitor, monitor_id)
        assert monitor.health_status == "offline"
        assert monitor.consecutive_failures == 0
        assert monitor.last_checked_at is None
        assert await db.scalar(select(func.count()).select_from(CheckResult)) == 0


@pytest.mark.asyncio
async def test_transient_technical_retry_keeps_sequence_when_cycle_eventually_evaluated(pg_engine):
    _, _, monitor_id = await setup_monitor(
        pg_engine,
        interval_seconds=3600,
        failure_threshold=2,
        health_status="degraded",
        consecutive_failures=1,
        first_failure_at=NOW - timedelta(seconds=60),
    )
    job_id = (await call(pg_engine, schedule_due, now=NOW))[0]
    first = await call(pg_engine, claim_job, job_id, now=NOW)
    assert await call(
        pg_engine, record_job_error, job_id, first.lease_token, "internal_error", now=NOW
    )
    second = await call(pg_engine, claim_job, job_id, now=NOW + timedelta(seconds=1))
    result = evaluated(second, outcome="failure", latency=None)
    assert await call(
        pg_engine, finalize_job, job_id, second.lease_token, result, now=result.completed_at
    )
    async with create_session_factory(pg_engine)() as db:
        assert (await db.get(Monitor, monitor_id)).health_status == "offline"
        assert await db.scalar(select(func.count()).select_from(Incident)) == 1


@pytest.mark.parametrize("change", ["pause", "configuration"])
@pytest.mark.asyncio
async def test_administrative_api_cancel_fences_worker(pg_engine, change):
    user_id, _, monitor_id = await setup_monitor(pg_engine)
    job_id = (await call(pg_engine, schedule_due, now=NOW))[0]
    claim = await call(pg_engine, claim_job, job_id, now=NOW)
    async with create_session_factory(pg_engine).begin() as db:
        project, monitor = await owned_monitor(db, user_id, monitor_id, lock=True)
        if change == "pause":
            await set_paused(db, project, monitor, True)
        else:
            await patch_monitor(db, project, monitor, MonitorPatch(expected_status=201))
    result = evaluated(claim)
    assert not await call(
        pg_engine, finalize_job, job_id, claim.lease_token, result, now=result.completed_at
    )
    async with create_session_factory(pg_engine)() as db:
        job = await db.get(CheckJob, job_id)
        assert job.status == "cancelled"
        assert job.lease_token is None
        assert await db.scalar(select(func.count()).select_from(CheckResult)) == 0


@pytest.mark.parametrize(
    "invalid", ["version", "paused", "archived", "deadline", "insufficient_budget"]
)
@pytest.mark.asyncio
async def test_claim_revalidation_cancels_or_expires_without_result(pg_engine, invalid):
    _, _, monitor_id = await setup_monitor(pg_engine, consecutive_failures=1, first_failure_at=NOW)
    job_id = (await call(pg_engine, schedule_due, now=NOW))[0]
    claim_at = NOW
    async with pg_engine.begin() as connection:
        if invalid == "version":
            await connection.execute(
                update(Monitor).where(Monitor.id == monitor_id).values(config_version=2)
            )
        elif invalid in {"paused", "archived"}:
            field = "paused_at" if invalid == "paused" else "archived_at"
            await connection.execute(
                update(Monitor)
                .where(Monitor.id == monitor_id)
                .values(**{field: NOW, "next_check_at": None})
            )
        elif invalid == "deadline":
            claim_at += timedelta(seconds=60)
        else:
            claim_at += timedelta(seconds=50)
    assert await call(pg_engine, claim_job, job_id, now=claim_at) is None
    async with create_session_factory(pg_engine)() as db:
        job = await db.get(CheckJob, job_id)
        assert job.status == (
            "expired" if invalid in {"deadline", "insufficient_budget"} else "cancelled"
        )
        assert await db.scalar(select(func.count()).select_from(CheckResult)) == 0
        assert (await db.get(Monitor, monitor_id)).health_status is None


@pytest.mark.asyncio
async def test_scheduler_expiry_releases_open_index_and_breaks_failure_sequence(pg_engine):
    _, _, monitor_id = await setup_monitor(pg_engine, consecutive_failures=2, first_failure_at=NOW)
    old_id = (await call(pg_engine, schedule_due, now=NOW))[0]
    new_time = NOW + timedelta(seconds=60)
    new_id = (await call(pg_engine, schedule_due, now=new_time))[0]
    assert old_id != new_id
    async with create_session_factory(pg_engine)() as db:
        assert (await db.get(CheckJob, old_id)).status == "expired"
        assert (await db.get(CheckJob, new_id)).status == "pending"
        assert (await db.get(Monitor, monitor_id)).consecutive_failures == 0
        assert await db.scalar(select(func.count()).select_from(CheckResult)) == 0


@pytest.mark.parametrize("operation", ["claim", "finalize"])
@pytest.mark.asyncio
async def test_concurrent_claim_and_finalize_have_one_effect(pg_engine, operation):
    await setup_monitor(pg_engine, failure_threshold=1)
    job_id = (await call(pg_engine, schedule_due, now=NOW))[0]
    existing = None
    if operation == "finalize":
        existing = await call(pg_engine, claim_job, job_id, now=NOW)
    factory = create_session_factory(pg_engine)
    async with factory.begin() as first, factory() as second:
        if operation == "claim":
            first_result = await claim_job(first, job_id, now=NOW)
            task = asyncio.create_task(claim_job(second, job_id, now=NOW))
        else:
            result = evaluated(existing, outcome="failure", latency=None)
            first_result = await finalize_job(
                first, job_id, existing.lease_token, result, now=result.completed_at
            )
            task = asyncio.create_task(
                finalize_job(second, job_id, existing.lease_token, result, now=result.completed_at)
            )
        try:
            async with pg_engine.connect() as observer:
                async with asyncio.timeout(5):
                    while not await observer.scalar(
                        text(
                            "SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE cardinality(pg_blocking_pids(pid)) > 0 AND datname=current_database())"
                        )
                    ):
                        await asyncio.sleep(0.01)
            assert first_result
            assert not task.done()
            await first.commit()
            second_result = await asyncio.wait_for(task, 5)
            assert second_result is None if operation == "claim" else second_result is False
            await second.commit()
        finally:
            await first.rollback()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    async with factory() as db:
        job = await db.get(CheckJob, job_id)
        assert job.execution_count == 1
        if operation == "finalize":
            assert await db.scalar(select(func.count()).select_from(CheckResult)) == 1
            assert await db.scalar(select(func.count()).select_from(Incident)) == 1


@pytest.mark.parametrize(
    "malformation", ["private_attempt", "infinite_latency", "wrong_status", "internal_failure"]
)
@pytest.mark.asyncio
async def test_invalid_or_private_results_rejected_atomically(pg_engine, malformation):
    await setup_monitor(pg_engine)
    job_id = (await call(pg_engine, schedule_due, now=NOW))[0]
    claim = await call(pg_engine, claim_job, job_id, now=NOW)
    values = dict(evaluated(claim).__dict__)
    if malformation == "private_attempt":
        values["attempts"] = [{"url": "https://secret.example"}]
    elif malformation == "infinite_latency":
        values["latency_ms"] = float("inf")
    elif malformation == "wrong_status":
        values["http_status"] = 500
    else:
        values.update(outcome="failure", error_code="internal_error")
    with pytest.raises(ValueError):
        await call(
            pg_engine,
            finalize_job,
            job_id,
            claim.lease_token,
            EvaluatedCycle(**values),
            now=NOW + timedelta(seconds=1),
        )
    async with create_session_factory(pg_engine)() as db:
        assert (await db.get(CheckJob, job_id)).status == "running"
        assert await db.scalar(select(func.count()).select_from(CheckResult)) == 0
