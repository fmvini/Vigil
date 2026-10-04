"""Real Pub/Sub using isolated owners; never stop/flush the shared Redis server."""

import asyncio
import json
import os
import socket
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff

from app.services.events import EventHub, event_stream

pytestmark = pytest.mark.redis


@pytest.fixture
async def redis_url():
    url = os.getenv("VIGIL_TEST_REDIS_URL")
    if not url:
        pytest.skip("Set VIGIL_TEST_REDIS_URL to prove real Redis Pub/Sub")
    async with Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2) as redis:
        assert await redis.ping()
    return url


def client(url):
    return Redis.from_url(
        url, socket_connect_timeout=0.2, socket_timeout=2, retry=Retry(NoBackoff(), 0)
    )


def signal(owner, project, revision=1):
    return {
        "type": "monitor.updated",
        "owner_id": str(owner),
        "project_id": str(project),
        "monitor_id": str(uuid4()),
        "revision": revision,
    }


async def wait_connected(hub):
    async with asyncio.timeout(5):
        while not hub.connected:
            await asyncio.sleep(0.01)


@asynccontextmanager
async def redis_proxy(url):
    """Transparent TCP routing owned only by this test; shutdown cuts its clients."""
    target = urlsplit(url)
    assert target.scheme == "redis", "This socket outage test requires plain local Redis"
    writers, tasks = set(), set()

    async def relay(reader, writer):
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()

    async def handle(reader, writer):
        task = asyncio.current_task()
        tasks.add(task)
        peers = [writer]
        writers.add(writer)
        try:
            remote_reader, remote_writer = await asyncio.open_connection(
                target.hostname, target.port or 6379
            )
            peers.append(remote_writer)
            writers.add(remote_writer)
            async with asyncio.TaskGroup() as group:
                group.create_task(relay(reader, remote_writer))
                group.create_task(relay(remote_reader, writer))
        except (ConnectionError, ExceptionGroup):
            pass
        finally:
            for peer in peers:
                peer.close()
                writers.discard(peer)
            tasks.discard(task)

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    credentials = target.netloc.rsplit("@", 1)[0] + "@" if "@" in target.netloc else ""
    proxy_url = urlunsplit(target._replace(netloc=f"{credentials}127.0.0.1:{port}"))

    async def cut():
        server.close()
        for writer in tuple(writers):
            writer.close()
        pending = tuple(tasks)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        await server.wait_closed()

    try:
        yield proxy_url, cut
    finally:
        await cut()


async def test_real_pubsub_fanout_owner_whitelist_echo_and_resource_cleanup(redis_url):
    hubs = [EventHub(redis_factory=lambda: client(redis_url)) for _ in range(2)]
    owner, project = uuid4(), uuid4()
    own = [hub.subscribe(owner) for hub in hubs]
    foreign = hubs[1].subscribe(uuid4())
    try:
        await asyncio.gather(*(wait_connected(hub) for hub in hubs))
        await hubs[0].emit(signal(owner, project))
        payloads = [await asyncio.wait_for(s.queue.get(), 3) for s in own]
        assert payloads[0] == payloads[1]
        assert set(payloads[0]) == {"type", "project_id", "monitor_id", "revision"}
        assert foreign.queue.empty()
        # Barrier on the same Pub/Sub TCP stream proves the preceding self echo was handled.
        await hubs[0].emit(signal(owner, project, revision=2))
        assert (await asyncio.wait_for(own[1].queue.get(), 3))["revision"] == 2
        assert own[0].queue.qsize() == 1
        assert own[0].queue.get_nowait()["revision"] == 2
        await hubs[1].emit(signal(owner, project, revision=3))
        assert (await asyncio.wait_for(own[0].queue.get(), 3))["revision"] == 3
        assert own[0].queue.empty()
    finally:
        await asyncio.gather(*(hub.close() for hub in hubs))
    assert all(hub.task is None and hub.redis is None and not hub.subscriptions for hub in hubs)


async def test_real_pubsub_across_independent_python_processes(redis_url):
    owner, project = uuid4(), uuid4()
    helper = Path(__file__).parent / "helpers" / "redis_event_process.py"
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-u",
        str(helper),
        redis_url,
        str(owner),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    publisher = EventHub(redis_factory=lambda: client(redis_url))
    try:
        ready = await asyncio.wait_for(process.stdout.readline(), 10)
        assert json.loads(ready) == {"ready": True}
        # Parent has no subscriptions/listener. Delivery must be Redis, not local dispatch.
        await publisher.emit(signal(owner, project, revision=7))
        payload = json.loads(await asyncio.wait_for(process.stdout.readline(), 10))
        assert payload["project_id"] == str(project) and payload["revision"] == 7
        assert "owner_id" not in payload and "source" not in payload
        assert publisher.task is None and publisher.subscriptions == {}
        assert await asyncio.wait_for(process.wait(), 5) == 0
        assert not await process.stderr.read()
    finally:
        await publisher.close()
        if process.returncode is None:
            process.kill()  # only the child created by this test
            await process.wait()


async def test_real_socket_unavailable_then_reconnect_keeps_local_and_snapshot(redis_url):
    async with redis_proxy(redis_url) as (proxy_url, cut):
        await assert_outage_recovery(redis_url, proxy_url, cut)


async def assert_outage_recovery(redis_url, proxy_url, cut):
    # Hold an unlistening loopback port: refusal is real and cannot affect shared Redis.
    unavailable = socket.socket()
    unavailable.bind(("127.0.0.1", 0))
    bad_url = f"redis://127.0.0.1:{unavailable.getsockname()[1]}/0"
    endpoint = proxy_url
    created = []

    def factory():
        redis = client(endpoint)
        created.append(redis)
        return redis

    hub = EventHub(redis_factory=factory, reconnect_seconds=0.02)
    publisher = EventHub(redis_factory=lambda: client(redis_url))
    owner, project = uuid4(), uuid4()
    subscription = hub.subscribe(owner)

    class Request:
        async def is_disconnected(self):
            return False

    async def valid():
        return True

    stream = event_stream(Request(), hub, subscription, valid, snapshot_seconds=0.02)
    try:
        await wait_connected(hub)
        endpoint = bad_url
        # Cut only the test proxy and its connections. The shared Redis stays up.
        await cut()
        async with asyncio.timeout(5):
            while hub.connected or len(created) < 2:
                await asyncio.sleep(0.01)
        await publisher.emit(signal(owner, project))  # absent subscriber; no replay expected
        await hub.emit(signal(owner, project, revision=2))
        assert subscription.queue.get_nowait()["revision"] == 2
        assert b"connected" in await anext(stream)
        assert b"periodic" in await asyncio.wait_for(anext(stream), 1)
        endpoint = redis_url
        await wait_connected(hub)
        await publisher.emit(signal(owner, project, revision=3))
        assert (await asyncio.wait_for(subscription.queue.get(), 3))["revision"] == 3
    finally:
        await stream.aclose()
        await hub.close()
        await publisher.close()
        unavailable.close()
    assert hub.task is None and hub.redis is None and not hub.subscriptions
