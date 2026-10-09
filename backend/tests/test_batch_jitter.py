"""Executable jitter/admission tests without external network or PostgreSQL."""

import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event
from test_batch import controlled as controlled
from test_batch import settings

from app.db.base import Base
from app.db.models import CheckJob, Monitor, Project, User
from app.db.session import create_engine, create_session_factory
from app.monitoring import batch
from app.security import utcnow


@pytest.fixture
def jitter(controlled, monkeypatch):
    clock = SimpleNamespace(now=0, due=23, sleeps=[], queries=[], schedules=[], changed=False)
    real_sleep = asyncio.sleep
    factory = batch.create_session_factory(None)
    identifier = uuid4()

    async def future(*args):
        clock.queries.append(clock.now)
        return clock.due - clock.now if clock.due > clock.now else None

    async def sleep(delay):
        clock.sleeps.append(delay)
        clock.now += delay
        await real_sleep(0)

    async def schedule(db, **kwargs):
        clock.schedules.append(clock.now)
        assert kwargs["fresh_slot"] and kwargs["minimum_interval_seconds"] == 900
        if clock.now >= clock.due and not clock.changed and not controlled.states:
            controlled.states[identifier] = "pending"

    async def process(factory, executor, job_id, **kwargs):
        assert clock.now >= clock.due  # No admission based on the pre-sleep clock.
        controlled.states[job_id] = "completed"

    monkeypatch.setattr(
        batch.asyncio, "get_running_loop", lambda: SimpleNamespace(time=lambda: clock.now)
    )
    monkeypatch.setattr(batch.asyncio, "sleep", sleep)
    monkeypatch.setattr(batch, "next_monitor_delay", future)
    monkeypatch.setattr(batch, "schedule_due", schedule)
    monkeypatch.setattr(batch, "process_job", process)

    async def run(*, deadline=85, max_jobs=100):
        report = {"attempts": 0, "deferred": 0, "deadline_reached": False}
        await batch._execute(
            factory,
            object(),
            settings(),
            report,
            concurrency=5,
            max_jobs=max_jobs,
            deadline=deadline,
        )
        return report

    clock.run = run
    return clock


async def test_jitter_23_seconds_waits_and_revalidates_before_admission(jitter):
    result = await jitter.run()
    assert jitter.sleeps == [23]
    assert jitter.schedules == [0, 23, 23]
    assert result["jobs_admitted"] == 1 and result["job_states"] == {"completed": 1}


@pytest.mark.parametrize("delay,waits", [(30, [30]), (30.000001, []), (0, []), (-1, [])])
async def test_future_wait_window_boundaries(jitter, delay, waits):
    jitter.due = delay
    await jitter.run()
    assert jitter.sleeps == waits


@pytest.mark.parametrize("deadline", [74, 73.999, 51])
async def test_wait_requires_strict_remaining_budget(jitter, deadline):
    result = await jitter.run(deadline=deadline)
    assert jitter.sleeps == [] and result["jobs_admitted"] == 0


async def test_query_roundtrip_time_is_charged_to_wait_budget(jitter, monkeypatch):
    async def slow_query(*args):
        jitter.now = 12
        return 23

    monkeypatch.setattr(batch, "next_monitor_delay", slow_query)
    assert (await jitter.run())["jobs_admitted"] == 0
    assert jitter.sleeps == []  # 85-12 <= 23+51.


async def test_change_during_sleep_does_not_create_job_from_old_due(jitter, monkeypatch):
    original = batch.asyncio.sleep

    async def paused(delay):
        await original(delay)
        jitter.changed = True

    monkeypatch.setattr(batch.asyncio, "sleep", paused)
    result = await jitter.run()
    assert jitter.sleeps == [23] and jitter.schedules == [0, 23]
    assert result["jobs_admitted"] == 0


async def test_cumulative_future_wait_is_bounded(jitter, monkeypatch):
    async def moved_due(delay):
        jitter.sleeps.append(delay)
        jitter.now += delay
        jitter.due = jitter.now + 8

    monkeypatch.setattr(batch.asyncio, "sleep", moved_due)
    assert (await jitter.run())["jobs_admitted"] == 0
    assert jitter.sleeps == [23]  # Another 8s would exceed the cumulative 30s.


async def test_max_jobs_does_not_wait_for_more_admissions(jitter, controlled):
    controlled.states[uuid4()] = "pending"
    # Existing work is already due; only the future admission checks its due clock.
    jitter.due = 0
    result = await jitter.run(max_jobs=1)
    assert result["jobs_admitted"] == 1 and jitter.queries == [] and jitter.sleeps == []


async def test_pending_backlog_prevents_future_monitor_wait(jitter, controlled):
    # A job which cannot fit is deferred; do not also wait for new work.
    controlled.states[uuid4()] = "pending"
    result = await jitter.run(deadline=1)
    assert result["deferred"] == 1 and jitter.queries == [] and jitter.sleeps == []


async def test_cancellation_during_future_wait_propagates(jitter, monkeypatch):
    sleeping, cleaned = asyncio.Event(), asyncio.Event()

    async def blocked_sleep(delay):
        sleeping.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    monkeypatch.setattr(batch.asyncio, "sleep", blocked_sleep)
    task = asyncio.create_task(jitter.run())
    await asyncio.wait_for(sleeping.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned.is_set() and jitter.schedules == [0]


async def test_future_sleep_happens_after_query_session_closes(jitter, monkeypatch):
    open_sessions = []
    original_sleep = batch.asyncio.sleep

    @asynccontextmanager
    async def session():
        open_sessions.append(True)
        try:
            yield
        finally:
            open_sessions.pop()

    async def future(*args):
        async with session():
            delay = jitter.due - jitter.now
        return delay

    async def sleep(delay):
        assert open_sessions == []
        await original_sleep(delay)

    monkeypatch.setattr(batch, "next_monitor_delay", future)
    monkeypatch.setattr(batch.asyncio, "sleep", sleep)
    assert (await jitter.run())["jobs_admitted"] == 1


async def test_active_work_prevents_future_query(jitter, controlled, monkeypatch):
    controlled.states[uuid4()] = "pending"
    active = []
    started = asyncio.Event()

    async def process(factory, executor, identifier, **kwargs):
        active.append(True)
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            active.pop()

    async def future(*args):
        pytest.fail("Future query while processing active work")

    monkeypatch.setattr(batch, "process_job", process)
    monkeypatch.setattr(batch, "next_monitor_delay", future)
    task = asyncio.create_task(jitter.run())
    await asyncio.wait_for(started.wait(), 1)
    assert active
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not active and jitter.sleeps == []


@pytest.mark.parametrize(
    "excluded",
    [
        None,
        "paused",
        "monitor_archived",
        "project_archived",
        "legacy",
        "pending",
        "running",
        "null",
        "due",
        "multiple",
    ],
)
async def test_actual_future_query_filters_and_releases_session(excluded):
    engine = create_engine("sqlite+aiosqlite:///:memory:", allow_sqlite_for_tests=True)
    now = utcnow().replace(tzinfo=None)
    calls, opened = [], []

    @event.listens_for(engine.sync_engine, "connect")
    def clock(connection, _):
        def timestamp():
            calls.append(True)
            return now.isoformat(" ")

        connection.create_function("clock_timestamp", 0, timestamp)

    factory = create_session_factory(engine)
    try:
        async with engine.begin() as db:
            await db.run_sync(Base.metadata.create_all)
        async with factory.begin() as db:
            user = User(email="jitter@example.test", password_hash="unused")
            db.add(user)
            await db.flush()
            project = Project(owner_id=user.id, name="Jitter", public_slug="jitter")
            db.add(project)
            await db.flush()
            monitor = Monitor(
                project_id=project.id,
                name="Jitter",
                url="https://example.test",
                interval_seconds=900,
                next_check_at=now + timedelta(seconds=23),
            )
            db.add(monitor)
            if excluded == "paused":
                monitor.paused_at = now
                monitor.next_check_at = None
            elif excluded == "monitor_archived":
                monitor.archived_at = now
                monitor.next_check_at = None
            elif excluded == "project_archived":
                project.archived_at = now
            elif excluded == "legacy":
                monitor.interval_seconds = 60
            elif excluded in {"null", "due"}:
                monitor.next_check_at = None if excluded == "null" else now
            await db.flush()
            if excluded in {"pending", "running", "multiple"}:
                db.add(
                    CheckJob(
                        monitor_id=monitor.id,
                        config_version=1,
                        config_snapshot={},
                        scheduled_at=now,
                        expires_at=now + timedelta(seconds=900),
                        budget_ms=1000,
                        status="pending" if excluded == "multiple" else excluded,
                        lease_token=uuid4() if excluded == "running" else None,
                        lease_expires_at=now + timedelta(seconds=90)
                        if excluded == "running"
                        else None,
                        started_at=now if excluded == "running" else None,
                        execution_count=1 if excluded == "running" else 0,
                    )
                )
            if excluded == "multiple":
                # An open job excludes only its own monitor. Select the nearest
                # future time among the remaining monitors, independent of order.
                for delay in (49, 11):
                    db.add(
                        Monitor(
                            project_id=project.id,
                            name=f"Future {delay}",
                            url="https://example.test",
                            interval_seconds=900,
                            next_check_at=now + timedelta(seconds=delay),
                        )
                    )

        @asynccontextmanager
        async def tracked():
            opened.append(True)
            try:
                async with factory() as db:
                    yield db
            finally:
                opened.pop()

        delay = await batch.next_monitor_delay(tracked, 900)
        expected = 23 if excluded is None else 11 if excluded == "multiple" else None
        assert delay == expected
        assert opened == [] and calls == [True]
    finally:
        await engine.dispose()
