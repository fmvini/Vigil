"""Controlled scheduler contracts; PostgreSQL locking is covered separately."""

from datetime import timedelta
from uuid import uuid4

import pytest
from test_db_postgresql import NOW

from app.db.models import Monitor
from app.services import check_jobs


class SchedulerSession:
    def __init__(self, monitor):
        self.monitor = monitor
        self.job = None
        self.events = []
        self.selection = None

    async def scalars(self, statement):
        self.selection = statement
        self.events.append("monitor_lock")
        assert statement._for_update_arg is not None

        class Rows:
            def all(inner):
                return [self.monitor]

        return Rows()

    async def scalar(self, statement):
        self.events.append("job_lock")
        assert statement._for_update_arg is not None
        return None

    def add(self, job):
        self.job = job

    async def flush(self):
        self.events.append("flush")


def monitor():
    return Monitor(
        id=uuid4(),
        name="Unit",
        url="https://example.test",
        next_check_at=NOW,
        interval_seconds=60,
        timeout_ms=5000,
        retry_count=1,
        config_version=1,
    )


@pytest.mark.parametrize("delay", [0, 59, 60, 185, 300])
@pytest.mark.parametrize("fresh", [False, True])
async def test_fresh_window_and_default_phase_at_boundaries(delay, fresh):
    db = SchedulerSession(monitor())
    current = NOW + timedelta(seconds=delay)
    ids = await check_jobs.schedule_due(db, now=current, fresh_slot=fresh)
    expected = current if fresh else NOW + timedelta(seconds=(delay // 60) * 60)
    assert ids == [db.job.id]
    assert db.job.scheduled_at == expected
    assert db.job.expires_at == expected + timedelta(seconds=60)
    assert db.monitor.next_check_at == db.job.expires_at
    assert db.job.skipped_slots == delay // 60
    assert db.job.budget_ms == 13600


async def test_fresh_slot_refreshes_database_clock_after_both_locks(monkeypatch):
    db = SchedulerSession(monitor())
    timestamps = iter([NOW + timedelta(seconds=59), NOW + timedelta(seconds=62)])

    async def clock(session, supplied):
        assert session is db and supplied is None
        db.events.append("database_clock")
        return next(timestamps)

    monkeypatch.setattr(check_jobs, "_clock", clock)
    await check_jobs.schedule_due(db, fresh_slot=True)
    assert db.events == ["database_clock", "monitor_lock", "job_lock", "database_clock", "flush"]
    assert db.job.scheduled_at == NOW + timedelta(seconds=62)
    assert db.job.expires_at == NOW + timedelta(seconds=122)
    assert db.job.skipped_slots == 1


@pytest.mark.parametrize("invalid", [None, 1, "true"])
async def test_fresh_flag_requires_boolean_before_query(invalid):
    with pytest.raises(ValueError, match="fresh_slot"):
        await check_jobs.schedule_due(None, fresh_slot=invalid)


@pytest.mark.parametrize("invalid", [True, 59, 3601, 60.0, "300", None])
async def test_minimum_interval_rejected_before_query(invalid):
    with pytest.raises(ValueError, match="minimum_interval_seconds"):
        await check_jobs.schedule_due(None, minimum_interval_seconds=invalid)


async def test_cloud_minimum_is_applied_in_locked_selection():
    db = SchedulerSession(monitor())
    await check_jobs.schedule_due(db, now=NOW, minimum_interval_seconds=300, fresh_slot=True)
    compiled = db.selection.compile()
    assert "monitors.interval_seconds >=" in str(compiled)
    assert compiled.params["interval_seconds_1"] == 300
