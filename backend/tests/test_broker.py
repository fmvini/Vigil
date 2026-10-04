import asyncio
import os
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from taskiq.message import BrokerMessage, TaskiqMessage

from app.config import Settings
from app.monitoring.broker import create_broker


def envelope(broker):
    return broker.formatter.dumps(
        TaskiqMessage(
            task_id=str(uuid4()),
            task_name="vigil.check",
            args=[str(uuid4())],
            kwargs={"envelope_version": 1},
            labels={"ack_type": "manual"},
        )
    ).message


async def test_candidate_reclaims_on_empty_queue_and_progresses_cursor(monkeypatch):
    from app.monitoring import broker as module

    calls = []
    broker = create_broker(Settings())
    data = envelope(broker)
    pending = [[b"9-0", []], [b"0-0", [(b"7-0", {b"data": data})]]]

    class FakeRedis:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def xreadgroup(self, *args, **kwargs):
            assert not kwargs["noack"]
            return []

        async def xautoclaim(self, *args, **kwargs):
            calls.append(kwargs["start_id"])
            return pending.pop(0)

        async def xack(self, *args):
            calls.append("ACK")

    monkeypatch.setattr(module, "Redis", FakeRedis)
    listener = broker.listen()
    message = await anext(listener)
    assert calls == ["0-0", b"9-0"]
    assert message.data == data
    await message.ack()
    assert calls[-1] == "ACK"
    await listener.aclose()
    await broker.connection_pool.disconnect()


async def test_envelope_forces_manual_ack_and_rejects_private_payload(caplog):
    broker = create_broker(Settings())
    valid = TaskiqMessage(
        task_id=str(uuid4()),
        task_name="vigil.check",
        args=[str(uuid4())],
        kwargs={},
        labels={"ack_type": "when_received"},
    )
    sanitized = broker.formatter.loads(broker._safe_envelope(broker.formatter.dumps(valid).message))
    assert sanitized.labels == {"ack_type": "manual"} and sanitized.labels_types is None

    class FakeRedis:
        def __init__(self):
            self.acked = []

        async def xack(self, *args):
            self.acked.append(args[-1])

    redis = FakeRedis()
    assert (
        await broker._delivery("bad-id", {b"data": b"private-password-should-not-be-logged"}, redis)
        is None
    )
    assert redis.acked == ["bad-id"]
    assert "private-password" not in caplog.text
    await broker.connection_pool.disconnect()


@pytest.mark.redis
async def test_real_redis_messages_before_group_ack_and_idle_reclaim():
    url = os.getenv("VIGIL_TEST_REDIS_URL")
    if not url:
        pytest.skip("Real Redis unavailable; ACK/reclaim integration remains unverified")
    stream = "vigil:test:" + uuid4().hex
    group = "vigil-test-group"
    settings = Settings(redis_url=url)
    first = create_broker(
        settings, queue_name=stream, group_name=group, idle_timeout=10, xread_block=10
    )
    second = create_broker(
        settings, queue_name=stream, group_name=group, idle_timeout=10, xread_block=10
    )
    redis = Redis.from_url(url)
    listener1 = listener2 = None
    try:
        # Publish BEFORE creation of the consumer group to prove id=0-0 behavior.
        data = envelope(first)
        await first.kick(
            BrokerMessage(task_id=str(uuid4()), task_name="vigil.check", message=data, labels={})
        )
        await first.startup()
        listener1 = first.listen()
        message = await asyncio.wait_for(anext(listener1), 2)
        assert message.data == data
        assert (await redis.xpending(stream, group))["pending"] == 1
        await listener1.aclose()
        await second.startup()
        await asyncio.sleep(0.03)
        listener2 = second.listen()
        recovered = await asyncio.wait_for(anext(listener2), 2)
        assert recovered.data == data  # reclaimed despite no fresh message
        assert (await redis.xpending(stream, group))["pending"] == 1
        await recovered.ack()
        assert (await redis.xpending(stream, group))["pending"] == 0
    finally:
        if listener1:
            await listener1.aclose()
        if listener2:
            await listener2.aclose()
        await first.shutdown()
        await second.shutdown()
        await redis.delete(stream)
        await redis.aclose()
