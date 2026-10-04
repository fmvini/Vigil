from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from taskiq.acks import AckableMessage
from taskiq.message import TaskiqMessage
from taskiq.receiver import Receiver

from app.db.models import CheckJob, CheckResult
from app.monitoring.executor import OperationalError
from app.monitoring.tasks import broker, check_task
from app.monitoring.worker import process_job
from app.security import utcnow
from app.services.check_jobs import EvaluatedCycle, schedule_due


async def scheduled_job(api_app, monitor):
    if api_app.state.engine.dialect.name != "postgresql":
        pytest.skip("Transactional worker requires real PostgreSQL")
    async with api_app.state.session_factory.begin() as db:
        jobs = await schedule_due(db)
    assert len(jobs) == 1
    return jobs[0]


class SuccessExecutor:
    def __init__(self, factory):
        self.factory = factory
        self.calls = 0

    async def run(self, claim):
        self.calls += 1
        # An independent transaction sees the committed lease before HTTP starts.
        async with self.factory() as db:
            job = await db.get(CheckJob, claim.job_id)
            assert job.status == "running" and job.lease_token == claim.lease_token
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


async def test_worker_commits_before_signal_and_duplicate_does_not_repeat_http(api_app, monitor):
    identifier = await scheduled_job(api_app, monitor)
    factory = api_app.state.session_factory
    executor = SuccessExecutor(factory)
    events = []

    async def signal(event):
        async with factory() as db:
            assert await db.scalar(select(func.count()).select_from(CheckResult)) == 1
            assert (await db.get(CheckJob, identifier)).status == "completed"
        events.append(event)
        raise RuntimeError("PubSub failed after commit")

    assert await process_job(factory, executor, identifier, signal=signal)
    assert await process_job(factory, executor, identifier, signal=signal)
    assert executor.calls == 1 and len(events) == 1
    assert events[0]["monitor_id"] == monitor["id"]


async def test_internal_policy_errors_do_not_create_target_result(api_app, monitor):
    identifier = await scheduled_job(api_app, monitor)

    class BlockedExecutor:
        async def run(self, claim):
            raise OperationalError("blocked_destination")

    assert await process_job(api_app.state.session_factory, BlockedExecutor(), identifier)
    async with api_app.state.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(CheckResult)) == 0
        job = await db.get(CheckJob, identifier)
        assert job.status == "pending" and job.retry_at is not None
        assert job.error_code == "blocked_destination"


async def test_manual_taskiq_ack_occurs_after_postgresql_commit(api_app, monitor):
    identifier = await scheduled_job(api_app, monitor)
    factory = api_app.state.session_factory

    class SignalRedis:
        async def publish(self, channel, data):
            return 0

    broker.state.factory = factory
    broker.state.executor = SuccessExecutor(factory)
    broker.state.redis = SignalRedis()
    acknowledged = []

    async def ack():
        async with factory() as db:
            assert (await db.get(CheckJob, identifier)).status == "completed"
            assert await db.scalar(select(func.count()).select_from(CheckResult)) == 1
        acknowledged.append(True)

    envelope = TaskiqMessage(
        task_id=str(identifier),
        task_name="vigil.check",
        labels={"ack_type": "manual"},
        args=[str(identifier)],
        kwargs={"envelope_version": 1},
    )
    encoded = broker.formatter.dumps(envelope).message
    await Receiver(broker).callback(AckableMessage(data=encoded, ack=ack), raise_err=True)
    assert acknowledged == [True]


async def test_failed_finalize_rolls_back_and_taskiq_does_not_ack(api_app, monitor, monkeypatch):
    identifier = await scheduled_job(api_app, monitor)
    factory = api_app.state.session_factory
    from app.monitoring import worker

    original_finalize = worker.finalize_job

    async def fail_after_flush(*args, **kwargs):
        await original_finalize(*args, **kwargs)
        raise RuntimeError("simulated failure before commit")

    monkeypatch.setattr(worker, "finalize_job", fail_after_flush)
    broker.state.factory = factory
    broker.state.executor = SuccessExecutor(factory)
    broker.state.redis = SimpleNamespace()
    acknowledged = []

    async def ack():
        acknowledged.append(True)

    envelope = TaskiqMessage(
        task_id=str(identifier),
        task_name="vigil.check",
        labels={"ack_type": "manual"},
        args=[str(identifier)],
        kwargs={},
    )
    await Receiver(broker).callback(
        AckableMessage(data=broker.formatter.dumps(envelope).message, ack=ack)
    )
    assert acknowledged == []
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(CheckResult)) == 0
        assert (await db.get(CheckJob, identifier)).status == "running"


async def test_administrative_pause_during_http_rejects_finalization(
    api_app, monitor, authenticated
):
    identifier = await scheduled_job(api_app, monitor)
    factory = api_app.state.session_factory

    class PauseExecutor(SuccessExecutor):
        async def run(self, claim):
            result = await super().run(claim)
            response = await authenticated.post(f"/api/v1/monitors/{monitor['id']}/pause")
            assert response.status_code == 200
            return result

    assert await process_job(factory, PauseExecutor(factory), identifier)
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(CheckResult)) == 0
        assert (await db.get(CheckJob, identifier)).status == "cancelled"


async def test_cancellation_leaves_running_lease_for_recovery(api_app, monitor):
    import asyncio

    identifier = await scheduled_job(api_app, monitor)

    class CancelledExecutor:
        async def run(self, claim):
            raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await process_job(api_app.state.session_factory, CancelledExecutor(), identifier)
    async with api_app.state.session_factory() as db:
        job = await db.get(CheckJob, identifier)
        assert job.status == "running" and job.lease_token is not None


async def test_invalid_uuid_envelope_is_discarded_without_database():
    acknowledgements = []

    async def ack():
        acknowledgements.append(True)

    context = SimpleNamespace(ack=ack)
    await check_task.original_func("invalid-id", context)
    assert acknowledgements == [True]
