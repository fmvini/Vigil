"""Own Redis keys and PG schemas; never start the shared scheduler or checks."""

import asyncio
import json
import os
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select, update
from test_db_postgresql import pg_engine as pg_engine
from test_db_postgresql import seed

from app.config import Settings
from app.db.models import CheckJob, Monitor
from app.db.session import create_session_factory
from app.monitoring import heartbeat, publisher, status


@pytest.fixture
async def observation():
    url = os.getenv("VIGIL_TEST_REDIS_URL")
    if not url:
        pytest.skip("VIGIL_TEST_REDIS_URL required to prove persisted scheduler heartbeat")
    stream = "vigil:qa:heartbeat:" + uuid4().hex
    group = "qa-" + uuid4().hex
    key = heartbeat.scheduler_key(stream, group)
    async with Redis.from_url(
        url, socket_timeout=2, socket_connect_timeout=2, max_connections=3
    ) as redis:
        assert await redis.ping()
        try:
            yield redis, key, stream, group
        finally:
            await redis.delete(key, stream)


async def write(redis, key, *, success=True, scheduled=4, published=3):
    await heartbeat.write_scheduler_tick(
        redis,
        key,
        success=success,
        duration_ms=2.5,
        scheduled_count=scheduled if success else None,
        published_count=published if success else None,
    )


async def test_real_success_failure_and_readonly_observation_preserve_last_success(observation):
    redis, key, _, _ = observation
    await write(redis, key)
    before, ttl = await redis.hgetall(key), await redis.pttl(key)
    result = await heartbeat.scheduler_snapshot(redis, key)
    assert result["heartbeat_state"] == "fresh" and result["last_tick_age_seconds"] < 2
    assert (
        result["last_success_scheduled_count"] == 4 and result["last_success_published_count"] == 3
    )
    assert await redis.hgetall(key) == before
    assert 0 < await redis.pttl(key) <= ttl <= 120_000
    await write(redis, key, success=False)
    result = await heartbeat.scheduler_snapshot(redis, key)
    assert result["heartbeat_state"] == "tick_failed"
    assert result["last_attempt_outcome"] == "error"
    assert result["last_success_scheduled_count"] == 4
    assert await redis.hget(key, "last_success_ms") == before[b"last_success_ms"]


async def test_real_first_failure_and_expiration_do_not_invent_success(observation):
    redis, key, _, _ = observation
    await write(redis, key, success=False)
    result = await heartbeat.scheduler_snapshot(redis, key)
    assert result["heartbeat_state"] == "tick_failed"
    assert result["last_tick_age_seconds"] is result["last_success_scheduled_count"] is None
    await redis.pexpire(key, 10)
    await asyncio.sleep(0.03)
    result = await heartbeat.scheduler_snapshot(redis, key)
    assert result["heartbeat_state"] == "missing" and result["last_tick_age_seconds"] is None
    assert not await redis.exists(key)


async def test_real_stale_and_clock_skew_use_redis_clock(observation):
    redis, key, _, _ = observation
    await write(redis, key)
    clock = await redis.time()
    now = clock[0] * 1000 + clock[1] // 1000
    for timestamp, expected in ((now - 6000, "stale"), (now + 60_000, "clock_skew")):
        await redis.hset(key, mapping={"last_attempt_ms": timestamp, "last_success_ms": timestamp})
        result = await heartbeat.scheduler_snapshot(redis, key)
        assert result["heartbeat_state"] == expected
        if expected == "clock_skew":
            assert result["last_tick_age_seconds"] is result["last_attempt_age_seconds"] is None


async def test_real_heartbeat_without_ttl_is_invalid_and_invalid_write_preserves_data(observation):
    redis, key, _, _ = observation
    await write(redis, key)
    before = await redis.hgetall(key)
    with pytest.raises(ValueError):
        await heartbeat.write_scheduler_tick(
            redis, key, success=True, duration_ms=float("nan"), scheduled_count=1, published_count=1
        )
    with pytest.raises(ValueError):
        await write(redis, key, scheduled=-1)
    assert await redis.hgetall(key) == before
    await redis.persist(key)
    assert await heartbeat.scheduler_snapshot(redis, key) == {
        "status": "unavailable",
        "error_code": "scheduler_heartbeat_invalid",
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", "secret"),
        ("outcome", "private-url"),
        ("duration_ms", "NaN"),
        ("duration_ms", "Inf"),
        ("scheduled_count", "1000"),
        ("last_success_ms", "private-password"),
    ],
)
async def test_real_malformed_heartbeat_is_sanitized(observation, field, value):
    redis, key, _, _ = observation
    await write(redis, key)
    await redis.hset(key, field, value)
    assert await heartbeat.scheduler_snapshot(redis, key) == {
        "status": "unavailable",
        "error_code": "scheduler_heartbeat_invalid",
    }


async def test_real_concurrent_writers_have_atomic_pairs_and_private_namespaces(observation):
    redis, key, stream, group = observation
    other = heartbeat.scheduler_key(stream + ":other", group)
    try:
        await write(redis, other, scheduled=0, published=0)
        await write(redis, key, scheduled=50, published=50)

        async def observe():
            for _ in range(40):
                result = await heartbeat.scheduler_snapshot(redis, key)
                assert result["heartbeat_state"] == "fresh"
                assert (
                    result["last_success_scheduled_count"] + result["last_success_published_count"]
                    == 100
                )

        async def writer(offset):
            for index in range(offset, 40, 2):
                await write(redis, key, scheduled=index, published=100 - index)

        # Two schedulers plus one reader reuse three sockets, matching the feature.
        # A cold burst of 40 sockets tests connection admission, not hash atomicity.
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(observe())
            tasks.create_task(writer(0))
            tasks.create_task(writer(1))
        assert (await heartbeat.scheduler_snapshot(redis, other))[
            "last_success_scheduled_count"
        ] == 0
        assert key != other and stream not in key and group not in key
    finally:
        await redis.delete(other)


async def test_real_tick_observation_follows_postgresql_publication_commit(pg_engine, observation):
    redis, key, stream, _ = observation
    async with pg_engine.begin() as db:
        _, _, monitor = await seed(db)
        await db.execute(
            update(Monitor)
            .where(Monitor.id == monitor)
            .values(next_check_at=func.clock_timestamp())
        )
    stop = asyncio.Event()

    async def publish(identifier):
        await redis.xadd(stream, {"job_id": identifier})

    async def record(**fields):
        assert fields["success"] and fields["scheduled_count"] == fields["published_count"] == 1
        async with pg_engine.connect() as db:
            assert (await db.execute(select(CheckJob.published_at))).scalar_one() is not None
        await heartbeat.write_scheduler_tick(redis, key, **fields)
        stop.set()

    await publisher.scheduler_publisher_loop(
        create_session_factory(pg_engine), publish, stop, heartbeat=record
    )
    assert (await heartbeat.scheduler_snapshot(redis, key))["heartbeat_state"] == "fresh"
    assert await redis.xlen(stream) == 1
    report = await status.snapshot(
        pg_engine,
        redis,
        stream=stream,
        group="qa-uninitialized",
        pipeline_enabled=False,
        network_enabled=False,
    )
    # A different group must not inherit another scheduler's heartbeat.
    assert report["scheduler"]["heartbeat_state"] == "missing"
    assert report["queue"]["state"] == "group_missing"
    report = await status.snapshot(
        pg_engine,
        redis,
        stream=stream,
        group=observation[3],
        pipeline_enabled=False,
        network_enabled=False,
    )
    assert report["scheduler"]["heartbeat_state"] == "fresh"
    assert report["database"]["pending_total"] == 1


async def test_tick_failure_records_failure_without_error_text(observation, monkeypatch):
    redis, key, _, _ = observation
    stop = asyncio.Event()

    async def fail(factory):
        raise RuntimeError("private-password private-url")

    async def record(**fields):
        assert fields["success"] is False
        await heartbeat.write_scheduler_tick(redis, key, **fields)
        stop.set()

    monkeypatch.setattr(publisher, "scheduler_tick", fail)
    await publisher.scheduler_publisher_loop(None, None, stop, heartbeat=record)
    report = await heartbeat.scheduler_snapshot(redis, key)
    assert report["heartbeat_state"] == "tick_failed" and "private" not in json.dumps(report)


@pytest.mark.parametrize("failure", ["error", "timeout"])
async def test_observation_failure_does_not_stop_next_ticks_and_is_bounded(failure, monkeypatch):
    stop, records, attempts = asyncio.Event(), [], []

    async def schedule(factory):
        return []

    async def publish(factory, callback):
        return 0

    async def record(**fields):
        attempts.append(fields)
        if len(attempts) == 3:
            stop.set()
        if failure == "error":
            raise RuntimeError("private-password")
        await asyncio.Event().wait()

    monkeypatch.setattr(publisher, "scheduler_tick", schedule)
    monkeypatch.setattr(publisher, "publish_pending", publish)
    monkeypatch.setattr(publisher, "HEARTBEAT_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(
        publisher, "activity", lambda event, **fields: records.append({"event": event, **fields})
    )
    await asyncio.wait_for(
        publisher.scheduler_publisher_loop(None, None, stop, heartbeat=record, tick_seconds=0.001),
        1,
    )
    assert len(attempts) == 3 and all(item["success"] for item in attempts)
    assert sum(item["event"] == "scheduler_heartbeat_failed" for item in records) == 3
    assert "private" not in json.dumps(records)


async def test_external_cancellation_during_observation_propagates(monkeypatch):
    entered = asyncio.Event()

    async def schedule(factory):
        return []

    async def publish(factory, callback):
        return 0

    async def record(**fields):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(publisher, "scheduler_tick", schedule)
    monkeypatch.setattr(publisher, "publish_pending", publish)
    task = asyncio.create_task(
        publisher.scheduler_publisher_loop(None, None, asyncio.Event(), heartbeat=record)
    )
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_disabled_entrypoint_never_creates_heartbeat_client(monkeypatch):
    from app.monitoring import run

    def forbidden(*args, **kwargs):
        raise AssertionError("Disabled scheduler must not connect")

    monkeypatch.setattr(run, "settings", Settings(pipeline_enabled=False))
    monkeypatch.setattr(run, "create_engine", forbidden)
    monkeypatch.setattr(run.Redis, "from_url", forbidden)
    with pytest.raises(RuntimeError, match="Pipeline disabled"):
        await run.main()


async def test_real_entrypoint_wires_heartbeat_to_exclusive_queue(
    pg_engine, observation, monkeypatch
):
    from app.monitoring import run
    from app.monitoring.broker import create_broker

    redis, key, stream, group = observation
    settings = Settings(
        redis_url=os.environ["VIGIL_TEST_REDIS_URL"],
        redis_stream_name=stream,
        redis_consumer_group=group,
        pipeline_enabled=True,
        monitoring_network_enabled=False,
    )
    own_broker = create_broker(settings)

    class NoChecks:
        async def kiq(self, *args, **kwargs):
            raise AssertionError("Empty own schema must not publish checks")

    async def one_tick(factory, publish, stop, *, heartbeat):
        async def observe(**data):
            await heartbeat(**data)
            stop.set()

        await publisher.scheduler_publisher_loop(factory, publish, stop, heartbeat=observe)

    monkeypatch.setattr(run, "settings", settings)
    monkeypatch.setattr(run, "broker", own_broker)
    monkeypatch.setattr(run, "check_task", NoChecks())
    monkeypatch.setattr(run, "create_engine", lambda url: pg_engine)
    monkeypatch.setattr(run, "scheduler_publisher_loop", one_tick)
    await run.main()
    result = await heartbeat.scheduler_snapshot(redis, key)
    assert result["heartbeat_state"] == "fresh"
    assert result["last_success_published_count"] == 0
    assert await redis.xlen(stream) == 0
    assert (await redis.xinfo_groups(stream))[0]["name"] == group.encode()
