"""Operational reads against UUID PostgreSQL schemas and real UUID Redis streams."""

import asyncio
import json
import os
from datetime import timedelta
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import event, insert, select, update
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from test_db_postgresql import NOW, job_values, seed
from test_db_postgresql import pg_engine as pg_engine

from app.db.models import CheckJob, Monitor
from app.monitoring import status


async def jobs(engine):
    specs = [
        {"scheduled_at": NOW - timedelta(seconds=10)},
        {"scheduled_at": NOW - timedelta(seconds=20), "published_at": NOW - timedelta(seconds=30)},
        {"published_at": NOW - timedelta(seconds=29)},
        {"retry_at": NOW + timedelta(seconds=1)},
        {"scheduled_at": NOW + timedelta(seconds=1)},
        {"scheduled_at": NOW - timedelta(seconds=60), "expires_at": NOW},
        {"status": "running", "lease_expires_at": NOW + timedelta(seconds=1)},
        {"status": "running", "lease_expires_at": NOW},
        {"status": "running", "lease_expires_at": NOW - timedelta(seconds=5)},
        {"status": "completed", "finished_at": NOW},
    ]
    async with engine.begin() as db:
        _, project, first_monitor = await seed(db)
        for index, values in enumerate(specs):
            monitor = first_monitor if not index else uuid4()
            if index:
                await db.execute(
                    insert(Monitor).values(
                        id=monitor,
                        project_id=project,
                        name="QA",
                        url="https://private.example/secret",
                    )
                )
            if values.get("status") == "running":
                values.update(lease_token=uuid4(), started_at=NOW, execution_count=1)
            await db.execute(insert(CheckJob).values(**job_values(monitor, **values)))


async def ledger(engine):
    async with engine.connect() as db:
        return (await db.execute(select(CheckJob).order_by(CheckJob.id))).all()


async def test_real_database_counts_cutoffs_and_reads_do_not_change_jobs(pg_engine):
    await jobs(pg_engine)
    before = await ledger(pg_engine)
    result = await status.database_snapshot(pg_engine, now=NOW)
    assert result == {
        "status": "ok",
        "observed_at": NOW.isoformat(),
        "pending_total": 6,
        "pending_due": 3,
        "pending_retry_wait": 1,
        "pending_unpublished_due": 1,
        "pending_republish_due": 1,
        "running_total": 3,
        "running_lease_active": 1,
        "running_lease_expired": 2,
        "expired_open": 1,
        "oldest_pending_due_age_seconds": 20.0,
        "oldest_expired_lease_age_seconds": 5.0,
    }
    assert await ledger(pg_engine) == before
    assert "private.example" not in json.dumps(result)


async def test_real_database_snapshot_completes_while_job_is_locked(pg_engine):
    await jobs(pg_engine)
    async with pg_engine.connect() as locker, locker.begin():
        await locker.execute(select(CheckJob).with_for_update())
        result = await asyncio.wait_for(status.database_snapshot(pg_engine, now=NOW), 2)
        assert result["pending_due"] == 3


async def test_real_snapshot_transaction_rejects_accidental_write(pg_engine):
    await jobs(pg_engine)
    before = await ledger(pg_engine)
    observed = []

    def try_write(connection, cursor, statement, parameters, context, many):
        if "count(*)" not in statement:
            return
        observed.append(connection.exec_driver_sql("SHOW transaction_read_only").scalar())
        with pytest.raises(DBAPIError, match="read-only"):
            with connection.begin_nested():
                connection.execute(update(CheckJob).values(published_at=NOW))

    event.listen(pg_engine.sync_engine, "before_cursor_execute", try_write)
    try:
        assert (await status.database_snapshot(pg_engine, now=NOW))["pending_due"] == 3
    finally:
        event.remove(pg_engine.sync_engine, "before_cursor_execute", try_write)
    assert observed == ["on"]
    assert await ledger(pg_engine) == before


async def test_real_empty_database_uses_database_clock_and_null_ages(pg_engine):
    result = await status.database_snapshot(pg_engine)
    assert result["observed_at"]
    assert result["pending_total"] == result["running_total"] == 0
    assert result["oldest_pending_due_age_seconds"] is None
    assert result["oldest_expired_lease_age_seconds"] is None


@pytest.fixture
async def queue():
    url = os.getenv("VIGIL_TEST_REDIS_URL")
    if not url:
        pytest.skip("VIGIL_TEST_REDIS_URL required for operational queue proofs")
    key = "vigil:qa:status:" + uuid4().hex
    group = "qa-workers-" + uuid4().hex
    async with Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2) as redis:
        assert await redis.ping()
        try:
            yield redis, key, group
        finally:
            await redis.delete(key)


async def test_real_redis_distinguishes_missing_stream_group_and_empty_queue(queue):
    redis, key, group = queue
    assert await status.redis_snapshot(redis, key, group) == {
        "status": "ok",
        "state": "stream_missing",
        "stream_length": 0,
    }
    assert not await redis.exists(key)  # inspection must not initialize a stream
    await redis.xadd(key, {"data": "private-payload"})
    assert await status.redis_snapshot(redis, key, group) == {
        "status": "ok",
        "state": "group_missing",
        "stream_length": 1,
    }
    assert await redis.xinfo_groups(key) == []
    await redis.xgroup_create(key, group, id="$", entries_read=1)
    result = await status.redis_snapshot(redis, key, group)
    assert result["pending_ack"] == result["undelivered_lag"] == 0
    assert result["pel_sample_max_idle_ms"] is None


async def test_real_redis_ack_retention_and_bounded_pending_sample(queue):
    redis, key, group = queue
    await redis.xgroup_create(key, group, id="0-0", mkstream=True)
    ids = [await redis.xadd(key, {"data": "private-payload"}) for _ in range(160)]
    await redis.xreadgroup(group, "private-consumer", {key: ">"}, count=150)
    await redis.xclaim(key, group, "private-recovery", 0, [ids[0]], idle=150_000)
    before = await redis.xpending_range(key, group, "-", "+", 200)
    result = await status.redis_snapshot(redis, key, group)
    assert result["stream_length"] == 160
    assert result["pending_ack"] == 150 and result["undelivered_lag"] == 10
    assert result["consumers_registered"] == 2
    assert result["pel_sample_size"] == result["pel_sample_limit"] == 100
    assert result["pel_sample_truncated"] is True
    assert result["pel_sample_redelivered"] == result["pel_sample_reclaimable"] == 1
    assert result["pel_sample_max_idle_ms"] >= 150_000
    after = await redis.xpending_range(key, group, "-", "+", 200)
    assert [(x["message_id"], x["consumer"], x["times_delivered"]) for x in before] == [
        (x["message_id"], x["consumer"], x["times_delivered"]) for x in after
    ]
    assert "private" not in json.dumps(result)
    await redis.xack(key, group, *ids[:100])
    result = await status.redis_snapshot(redis, key, group)
    assert result["stream_length"] == 160  # retained, acknowledged entries are not backlog
    assert result["pending_ack"] == result["pel_sample_size"] == 50
    assert result["undelivered_lag"] == 10 and not result["pel_sample_truncated"]


async def test_real_redis_unknown_lag_is_not_reported_as_zero(queue):
    redis, key, group = queue
    ids = [await redis.xadd(key, {"data": "qa"}) for _ in range(5)]
    await redis.xgroup_create(key, group, id=ids[1])
    result = await status.redis_snapshot(redis, key, group)
    assert result["undelivered_lag"] is None
    assert result["stream_length"] == 5 and result["pending_ack"] == 0


async def test_real_redis_wrong_type_is_unavailable_without_exposing_or_changing_data(queue):
    redis, key, group = queue
    await redis.set(key, "private-secret")
    result = await status.component_snapshot(
        status.redis_snapshot(redis, key, group), "redis_unavailable"
    )
    assert result == {"status": "unavailable", "error_code": "redis_unavailable"}
    assert await redis.get(key) == b"private-secret"


@pytest.mark.parametrize("failed", ["database", "redis"])
async def test_partial_snapshot_preserves_other_source_without_leaking_exception(
    failed, monkeypatch
):
    async def broken(*args, **kwargs):
        exception = SQLAlchemyError if failed == "database" else RedisError
        raise exception("secret-password postgres://private-host/connection-and-sql")

    async def healthy(*args, **kwargs):
        return {"status": "ok", "count": 42}

    monkeypatch.setattr(status, "database_snapshot", broken if failed == "database" else healthy)
    monkeypatch.setattr(status, "redis_snapshot", broken if failed == "redis" else healthy)

    async def heartbeat(*args, **kwargs):
        return {"status": "ok", "heartbeat_state": "missing", "last_tick_age_seconds": None}

    monkeypatch.setattr(status, "scheduler_snapshot", heartbeat)
    report = await status.snapshot(
        None,
        None,
        stream="secret-name",
        group="secret-group",
        pipeline_enabled=False,
        network_enabled=False,
    )
    assert report["status"] == "partial"
    assert report["database" if failed == "redis" else "queue"] == {"status": "ok", "count": 42}
    assert (
        report["database" if failed == "database" else "queue"]["error_code"]
        == f"{failed}_unavailable"
    )
    assert "secret" not in json.dumps(report)
    assert report["scheduler"]["last_tick_age_seconds"] is None
    assert not report["pipeline_enabled"] and not report["monitoring_network_enabled"]


async def test_component_timeout_cancels_operation_and_external_cancel_propagates(monkeypatch):
    cleaned = []

    async def blocked():
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.append(True)

    monkeypatch.setattr(status, "TIMEOUT_SECONDS", 0.01)
    assert await status.component_snapshot(blocked(), "redis_unavailable") == {
        "status": "unavailable",
        "error_code": "redis_unavailable",
    }
    task = asyncio.create_task(status.component_snapshot(blocked(), "redis_unavailable"))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(cleaned) == 2


def test_cli_configuration_error_does_not_print_credentials(monkeypatch, capsys):
    monkeypatch.setenv("VIGIL_DATABASE_URL", "unsupported://user:secret-password@private-host/db")
    assert status.main() == 1
    assert json.loads(capsys.readouterr().out) == {
        "status": "error",
        "error_code": "configuration_invalid",
    }
