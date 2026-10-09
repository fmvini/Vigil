"""Real SSE TCP pressure; own Uvicorn process/schema, no runtime server changes."""

import asyncio
import json
import os
import socket
import time
from contextlib import AsyncExitStack
from uuid import uuid4

import httpx
import pytest
from conftest import LEGAL_VERSIONS
from redis.asyncio import Redis
from test_api_replicas import HEADERS, Frames
from test_api_replicas import replicas as replicas
from test_db_postgresql import pg_engine as pg_engine

pytestmark = [pytest.mark.postgres, pytest.mark.redis]


async def account(stack, base):
    client = await stack.enter_async_context(
        httpx.AsyncClient(base_url=base, headers=HEADERS, timeout=5)
    )
    credentials = {
        **LEGAL_VERSIONS,
        "email": f"tcp-{uuid4().hex}@example.com",
        "password": "isolated TCP QA password",
    }
    response = await client.post("/api/v1/auth/register", json=credentials)
    assert response.status_code == 201
    owner = response.json()["id"]
    response = await client.post("/api/v1/auth/login", json=credentials)
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    response = await client.post("/api/v1/projects", json={"name": "TCP fixture"})
    assert response.status_code == 201
    return client, owner, response.json()["id"]


@pytest.mark.parametrize("replicas", [{"count": 1, "socket_buffer_bytes": 4096}], indirect=True)
async def test_physical_tcp_backpressure_releases_slot_without_stalling_other_owner(
    replicas, request
):
    replica = replicas[0]
    async with AsyncExitStack() as stack:
        blocked, owner, project = await account(stack, replica.base)
        healthy, healthy_owner, healthy_project = await account(stack, replica.base)
        redis = await stack.enter_async_context(Redis.from_url(os.environ["VIGIL_TEST_REDIS_URL"]))
        reader = None
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as raw:
            raw.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
            raw.setblocking(False)
            loop = asyncio.get_running_loop()
            await loop.sock_connect(raw, ("127.0.0.1", int(replica.base.rsplit(":", 1)[1])))
            client_port = str(raw.getsockname()[1])
            cookie = "; ".join(f"{key}={value}" for key, value in blocked.cookies.items())
            await loop.sock_sendall(
                raw,
                (
                    "GET /api/v1/events HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                    f"Cookie: {cookie}\r\nOrigin: http://vigil-qa.test\r\n\r\n"
                ).encode(),
            )
            prefix = b""
            async with asyncio.timeout(5):
                while b"\r\n\r\n" not in prefix:
                    part = await loop.sock_recv(raw, 4096)
                    assert part
                    prefix += part
            assert prefix.startswith(b"HTTP/1.1 200 OK\r\n")
            response = await stack.enter_async_context(
                healthy.stream("GET", "/api/v1/events", timeout=None)
            )
            assert response.status_code == 200
            reader = Frames(response, healthy_project)
            try:
                async with asyncio.timeout(10):
                    while not (await replica.command("stats"))["connected"]:
                        await asyncio.sleep(0.01)
                started, signals, paused, paused_bytes = time.perf_counter(), 0, None, 0
                # Raw client reads no body. A small real receive/send buffer makes
                # the transport hit its actual high-water mark in bounded time.
                while signals < 4096:
                    async with redis.pipeline(transaction=False) as pipeline:
                        for _ in range(16):
                            signals += 1
                            pipeline.publish(
                                "vigil:updates",
                                json.dumps(
                                    {
                                        "type": "project.updated",
                                        "owner_id": owner,
                                        "project_id": project,
                                        "revision": signals,
                                    }
                                ),
                            )
                        await pipeline.execute()
                    await asyncio.sleep(0.02)
                    stats = await replica.command("stats")
                    transport = stats["transports"].get(client_port)
                    if transport and transport["write_paused"]:
                        assert transport["buffered_bytes"] > 0
                        paused_bytes = transport["buffered_bytes"]
                        paused = time.perf_counter()
                        break
                assert paused is not None, "Did not create physical TCP write pressure"
                # The write that crosses the transport high-water mark can still
                # finish. Keep data pending afterward, so the application's send
                # deadline is active rather than waiting for the next heartbeat.
                async with redis.pipeline(transaction=False) as pipeline:
                    for offset in range(16):
                        pipeline.publish(
                            "vigil:updates",
                            json.dumps(
                                {
                                    "type": "project.updated",
                                    "owner_id": owner,
                                    "project_id": project,
                                    "revision": signals + offset + 1,
                                }
                            ),
                        )
                    await pipeline.execute()
                response = await healthy.patch(
                    "/api/v1/projects/" + healthy_project, json={"name": "Healthy during pressure"}
                )
                assert response.status_code == 200 and response.json()["revision"] == 1
                async with asyncio.timeout(5):
                    while 1 not in reader.revisions():
                        if reader.task.done():
                            await reader.task
                            raise AssertionError("Healthy SSE disconnected under pressure")
                        await asyncio.sleep(0.01)
                async with asyncio.timeout(15):
                    while owner in (await replica.command("stats"))["owners"]:
                        await asyncio.sleep(0.05)
                released = time.perf_counter()
                assert 8 <= released - paused <= 13
                stats = await replica.command("stats")
                assert stats["owners"][healthy_owner] == 1 and not reader.task.done()
                # Timeout closes the actual transport. Drain already buffered
                # bytes only after the slot is released, then require real EOF.
                drained = len(prefix)
                async with asyncio.timeout(5):
                    while part := await loop.sock_recv(raw, 65536):
                        drained += len(part)
                        assert drained < 2_000_000
                async with blocked.stream("GET", "/api/v1/events", timeout=None) as response:
                    assert response.status_code == 200
                response = await blocked.get("/api/v1/projects/" + project)
                assert response.status_code == 200 and response.json()["revision"] == 0
                request.node.user_properties.extend(
                    [
                        ("signals_until_transport_pause", signals),
                        ("additional_signals_after_pause", 16),
                        ("transport_buffered_bytes_at_pause", paused_bytes),
                        (
                            "client_receive_buffer_bytes",
                            raw.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF),
                        ),
                        ("pause_after_seconds", round(paused - started, 3)),
                        ("slot_release_after_pause_seconds", round(released - paused, 3)),
                        ("buffered_bytes_drained", drained),
                    ]
                )
                replica.expected_send_timeouts = 1
            finally:
                if reader is not None:
                    await reader.close()
