"""Abrupt process death at durable boundaries, against isolated PG/Redis state."""

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy import func, select, text
from taskiq.message import TaskiqMessage
from test_db_postgresql import pg_engine as pg_engine

from app.config import Settings
from app.db.models import CheckJob, CheckResult, Incident, Monitor, Project, User
from app.db.session import create_session_factory
from app.monitoring.broker import create_broker
from app.monitoring.publisher import publish_pending
from app.monitoring.scheduler import scheduler_tick

pytestmark = [pytest.mark.postgres, pytest.mark.redis]


class RecoveryHarness:
    def __init__(self, engine, redis_url, redis, schema, job_id, monitor_id, project_id):
        self.factory = create_session_factory(engine)
        self.redis_url, self.redis, self.schema = redis_url, redis, schema
        self.job_id, self.monitor_id, self.project_id = job_id, monitor_id, project_id
        self.stream, self.group = "vigil:worker-crash:" + uuid4().hex, "group-" + uuid4().hex
        self.processes = []
        self.broker = create_broker(
            Settings(redis_url=redis_url),
            queue_name=self.stream,
            group_name=self.group,
            idle_timeout=50,
            xread_block=10,
        )

    async def enqueue(self, identifier):
        message = TaskiqMessage(
            task_id=str(uuid4()),
            task_name="vigil.check",
            args=[str(identifier)],
            kwargs={"envelope_version": 1},
            labels={"ack_type": "manual"},
        )
        await self.redis.xadd(self.stream, {"data": self.broker.formatter.dumps(message).message})

    async def publish(self):
        return await publish_pending(self.factory, self.enqueue)

    async def child(self, phase, *, lease_seconds=12, messages=1):
        environment = {
            **os.environ,
            "VIGIL_TEST_REDIS_URL": self.redis_url,
            "VIGIL_PIPELINE_ENABLED": "false",
            "VIGIL_MONITORING_NETWORK_ENABLED": "false",
        }
        helper = Path(__file__).parent / "helpers" / "worker_crash_process.py"
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-u",
            str(helper),
            "--schema",
            self.schema,
            "--stream",
            self.stream,
            "--group",
            self.group,
            "--job-id",
            str(self.job_id),
            "--phase",
            phase,
            "--lease-seconds",
            str(lease_seconds),
            "--messages",
            str(messages),
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self.processes.append(process)
        async with asyncio.timeout(15):
            while True:
                line = await process.stdout.readline()
                assert line, "Own worker exited before its durable checkpoint"
                record = json.loads(line)
                assert record["checkpoint"] != "error", record
                if record["checkpoint"] == ("done" if phase == "complete" else phase):
                    break
        if phase == "complete":
            assert await asyncio.wait_for(process.wait(), 5) == 0
            assert not await process.stderr.read()
        return process, record

    async def kill(self, process):
        assert process in self.processes and process.returncode is None
        process.kill()  # abrupt death of this test's child; no shared worker/server signals
        assert await asyncio.wait_for(process.wait(), 5) != 0

    async def state(self):
        async with self.factory() as db:
            job = await db.get(CheckJob, self.job_id)
            monitor = await db.get(Monitor, self.monitor_id)
            project = await db.get(Project, self.project_id)
            return {
                "status": job.status,
                "executions": job.execution_count,
                "lease_token": job.lease_token,
                "lease_expires": job.lease_expires_at,
                "retry_at": job.retry_at,
                "error_code": job.error_code,
                "health": monitor.health_status,
                "last_checked": monitor.last_checked_at,
                "revision": project.revision,
                "results": await db.scalar(select(func.count()).select_from(CheckResult)),
                "incidents": await db.scalar(select(func.count()).select_from(Incident)),
            }

    async def wait_due(self, field):
        async with asyncio.timeout(16):
            while True:
                async with self.factory() as db:
                    row = await db.get(CheckJob, self.job_id)
                    now = await db.scalar(select(func.clock_timestamp()))
                    deadline = getattr(row, field)
                if deadline is None or now >= deadline:
                    return
                await asyncio.sleep(0.05)

    async def pending(self):
        return (await self.redis.xpending(self.stream, self.group))["pending"]


@pytest_asyncio.fixture
async def recovery(pg_engine):
    redis_url = os.getenv("VIGIL_TEST_REDIS_URL")
    if not redis_url:
        pytest.skip("Set VIGIL_TEST_REDIS_URL for actual worker process recovery")
    redis = Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=3)
    harness = None
    try:
        assert await redis.ping()
        factory = create_session_factory(pg_engine)
        async with factory.begin() as db:
            assert 170000 <= int(await db.scalar(text("SHOW server_version_num"))) < 180000
            schema = await db.scalar(select(func.current_schema()))
            assert re.fullmatch(r"vigil_test_[a-f0-9]{32}", schema)
            now = await db.scalar(select(func.clock_timestamp()))
            owner_id, project_id, monitor_id = uuid4(), uuid4(), uuid4()
            db.add(
                User(id=owner_id, email=f"crash-{owner_id}@example.test", password_hash="synthetic")
            )
            await db.flush()
            db.add(
                Project(
                    id=project_id,
                    owner_id=owner_id,
                    name="Isolated process recovery",
                    public_slug="crash-" + project_id.hex,
                )
            )
            await db.flush()
            db.add(
                Monitor(
                    id=monitor_id,
                    project_id=project_id,
                    name="Synthetic only",
                    url="https://never-executed.invalid/",
                    interval_seconds=3600,
                    timeout_ms=1000,
                    retry_count=0,
                    failure_threshold=1,
                    next_check_at=now,
                )
            )
            await db.flush()
        identifiers = await scheduler_tick(factory)
        assert len(identifiers) == 1
        harness = RecoveryHarness(
            pg_engine, redis_url, redis, schema, identifiers[0], monitor_id, project_id
        )
        await harness.broker.startup()
        assert await harness.publish() == 1
        yield harness
    finally:
        if harness is not None:
            for process in harness.processes:
                if process.returncode is None:
                    process.kill()
                    await asyncio.wait_for(process.wait(), 5)
            await harness.broker.shutdown()
            await redis.delete(harness.stream)
        await redis.aclose()


@pytest.mark.parametrize(
    "phase", ["after_delivery", "after_claim", "before_commit", "after_commit"]
)
async def test_real_worker_crash_recovers_durable_boundaries_without_duplicate_result(
    recovery, phase
):
    child, _ = await recovery.child(phase)
    before = await recovery.state()
    assert await recovery.pending() == 1
    assert before["executions"] == (0 if phase == "after_delivery" else 1)
    assert before["status"] == (
        "pending"
        if phase == "after_delivery"
        else "completed"
        if phase == "after_commit"
        else "running"
    )
    assert before["results"] == before["incidents"] == int(phase == "after_commit")
    assert before["revision"] == int(phase == "after_commit")
    await recovery.kill(child)
    # A new interpreter must reclaim the orphan message without a fresh publish.
    _, recovered = await recovery.child("complete")
    assert recovered["executor_calls"] == int(phase == "after_delivery")
    assert await recovery.pending() == 0
    if phase in {"after_claim", "before_commit"}:
        occupied = await recovery.state()
        assert occupied["status"] == "running" and occupied["results"] == 0
        assert occupied["lease_token"] == before["lease_token"]
        assert await scheduler_tick(recovery.factory) == []
        assert (await recovery.state())["status"] == "running"
        await recovery.wait_due("lease_expires_at")
        assert await scheduler_tick(recovery.factory) == []
        retry = await recovery.state()
        assert retry["status"] == "pending" and retry["error_code"] == "execution_crashed"
        assert retry["health"] is None and retry["results"] == retry["incidents"] == 0
        await recovery.wait_due("retry_at")
        assert await recovery.publish() == 1
        _, finished = await recovery.child("complete")
        assert finished["executor_calls"] == 1
    final = await recovery.state()
    assert final["status"] == "completed" and final["health"] == "offline"
    assert final["executions"] == (2 if phase in {"after_claim", "before_commit"} else 1)
    assert final["results"] == final["incidents"] == 1
    assert await recovery.pending() == 0
    # Replay a new envelope after completion: ACK only, no sample/incident/revision changes.
    await recovery.enqueue(recovery.job_id)
    _, duplicate = await recovery.child("complete")
    assert duplicate["executor_calls"] == 0
    assert await recovery.state() == final
    assert await recovery.pending() == 0


async def test_real_three_worker_crashes_exhaust_without_target_failure_or_lost_cleanup(recovery):
    for attempt in range(1, 4):
        child, _ = await recovery.child("after_claim", lease_seconds=2)
        assert (await recovery.state())["executions"] == attempt
        await recovery.kill(child)
        await recovery.wait_due("lease_expires_at")
        assert await scheduler_tick(recovery.factory) == []
        if attempt < 3:
            assert (await recovery.state())["status"] == "pending"
            await recovery.wait_due("retry_at")
            assert await recovery.publish() == 1
    exhausted = await recovery.state()
    assert exhausted["status"] == "exhausted" and exhausted["executions"] == 3
    assert exhausted["error_code"] == "execution_crashed"
    assert exhausted["results"] == exhausted["incidents"] == 0
    assert exhausted["health"] is None and exhausted["last_checked"] is None
    assert await recovery.publish() == 0
    assert await recovery.redis.xlen(recovery.stream) == 3
    _, drained = await recovery.child("complete", messages=3)
    assert drained["executor_calls"] == 0 and drained["acknowledgements"] == 3
    assert await recovery.pending() == 0
    assert await recovery.state() == exhausted
