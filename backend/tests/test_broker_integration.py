"""Real Redis Streams evidence; only UUID-namespaced test streams are changed."""

import asyncio
import os
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select
from taskiq.acks import AckableMessage
from taskiq.message import TaskiqMessage
from taskiq.receiver import Receiver
from test_worker import SuccessExecutor, scheduled_job

from app.config import Settings
from app.db.models import CheckJob, CheckResult
from app.monitoring.broker import create_broker
from app.monitoring.tasks import check_task

pytestmark = pytest.mark.redis


@pytest.fixture
async def real_redis():
    url = os.getenv("VIGIL_TEST_REDIS_URL")
    if not url:
        pytest.skip("Set VIGIL_TEST_REDIS_URL to prove real Redis integration")
    redis = Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
    try:
        assert await redis.ping()
        yield url, redis
    finally:
        await redis.aclose()


@asynccontextmanager
async def isolated_brokers(url, redis):
    stream, group = "vigil:test:" + uuid4().hex, "group-" + uuid4().hex
    brokers = [
        create_broker(
            Settings(redis_url=url),
            queue_name=stream,
            group_name=group,
            idle_timeout=20,
            xread_block=10,
        )
        for _ in range(2)
    ]
    try:
        for broker in brokers:
            await broker.startup()
        yield stream, group, brokers
    finally:
        for broker in brokers:
            await broker.shutdown()
        await redis.delete(stream)


def encoded(broker, job_id=None):
    return broker.formatter.dumps(
        TaskiqMessage(
            task_id=str(uuid4()),
            task_name="vigil.check",
            args=[str(job_id or uuid4())],
            kwargs={"envelope_version": 1},
            labels={"ack_type": "when_received"},
        )
    ).message


async def test_real_pending_cursor_reclaim_all_messages_without_new_publish(real_redis):
    url, redis = real_redis
    async with isolated_brokers(url, redis) as (stream, group, brokers):
        first, second = brokers
        second.unacknowledged_batch_size = 2
        payloads = [encoded(first) for _ in range(5)]
        for payload in payloads:
            await redis.xadd(stream, {"data": payload})
        listener = first.listen()
        try:
            delivered = [await asyncio.wait_for(anext(listener), 3) for _ in payloads]
            assert (await redis.xpending(stream, group))["pending"] == 5
            assert all(
                first.formatter.loads(m.data).labels == {"ack_type": "manual"} for m in delivered
            )
        finally:
            await listener.aclose()  # crash-equivalent loss of consumer; no ACK was issued
        await asyncio.sleep(0.05)
        recovered = second.listen()
        seen = []
        try:
            for _ in payloads:
                message = await asyncio.wait_for(anext(recovered), 3)
                seen.append(first.formatter.loads(message.data).task_id)
                await message.ack()
                await message.ack()  # duplicate ACK is idempotent on the real PEL
            assert set(seen) == {first.formatter.loads(p).task_id for p in payloads}
            assert len(seen) == len(set(seen))
            assert (await redis.xpending(stream, group))["pending"] == 0
            assert await redis.xlen(stream) == 5  # ACK does not delete durable stream entries
        finally:
            await recovered.aclose()


async def test_real_invalid_envelope_is_acked_without_disclosing_payload(real_redis, caplog):
    url, redis = real_redis
    async with isolated_brokers(url, redis) as (stream, group, brokers):
        broker = brokers[0]
        await redis.xadd(stream, {"data": b"test-private-password-not-an-envelope"})
        await redis.xadd(stream, {"data": encoded(broker)})
        listener = broker.listen()
        try:
            delivery = await asyncio.wait_for(anext(listener), 3)
            assert (await redis.xpending(stream, group))["pending"] == 1
            await delivery.ack()
            assert (await redis.xpending(stream, group))["pending"] == 0
            assert "invalid_job_envelope_discarded" in caplog.text
            assert "test-private-password" not in caplog.text
        finally:
            await listener.aclose()


@pytest.mark.parametrize("failure", [False, True], ids=["committed", "rollback"])
async def test_real_receiver_ack_follows_postgresql_commit(
    real_redis, api_app, monitor, monkeypatch, failure
):
    identifier = await scheduled_job(api_app, monitor)
    factory = api_app.state.session_factory
    url, redis = real_redis
    async with isolated_brokers(url, redis) as (stream, group, brokers):
        broker, recovery_broker = brokers
        broker.register_task(check_task.original_func, task_name="vigil.check", ack_type="manual")

        class Executor(SuccessExecutor):
            async def run(self, claim):
                assert (await redis.xpending(stream, group))["pending"] == 1
                return await super().run(claim)  # independently verifies committed PG lease

        broker.state.factory = factory
        broker.state.executor = Executor(factory)
        broker.state.redis = redis
        if failure:
            from app.monitoring import worker

            finalize = worker.finalize_job

            async def fail_after_flush(*args, **kwargs):
                await finalize(*args, **kwargs)
                raise RuntimeError("controlled_finalize_rollback")

            monkeypatch.setattr(worker, "finalize_job", fail_after_flush)
        payload = encoded(broker, identifier)
        await redis.xadd(stream, {"data": payload})
        listener = broker.listen()
        acknowledgements = []
        try:
            message = await asyncio.wait_for(anext(listener), 3)

            async def ack():
                async with factory() as db:
                    assert (await db.get(CheckJob, identifier)).status == "completed"
                    assert await db.scalar(select(func.count()).select_from(CheckResult)) == 1
                assert (await redis.xpending(stream, group))["pending"] == 1
                await message.ack()
                acknowledgements.append(True)

            await Receiver(broker).callback(
                AckableMessage(data=message.data, ack=ack), raise_err=True
            )
            assert acknowledgements == ([] if failure else [True])
            assert (await redis.xpending(stream, group))["pending"] == int(failure)
            async with factory() as db:
                assert (await db.get(CheckJob, identifier)).status == (
                    "running" if failure else "completed"
                )
                assert await db.scalar(select(func.count()).select_from(CheckResult)) == (
                    0 if failure else 1
                )
        finally:
            await listener.aclose()
        if failure:
            await asyncio.sleep(0.05)
            recovered = recovery_broker.listen()
            try:
                delivery = await asyncio.wait_for(anext(recovered), 3)
                assert recovery_broker.formatter.loads(delivery.data).args == [str(identifier)]
                assert (await redis.xpending(stream, group))["pending"] == 1
                # No ACK here: durable PG lease/reconciliation, not Pub/Sub, controls retry.
            finally:
                await recovered.aclose()
