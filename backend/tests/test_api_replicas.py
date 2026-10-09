"""Three actual HTTP API processes sharing PG/Redis; synthetic owners, no checks."""

import asyncio
import json
import os
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path
from statistics import median
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from conftest import LEGAL_VERSIONS
from redis.asyncio import Redis
from sqlalchemy import func, select
from test_db_postgresql import pg_engine as pg_engine

from app.db.session import create_session_factory

pytestmark = [pytest.mark.postgres, pytest.mark.redis]
HEADERS = {"Origin": "http://vigil-qa.test", "X-Vigil-Request": "browser"}


class Replica:
    def __init__(self, process, port, schema, socket_buffer_bytes=0, browser_origin=None):
        self.process, self.base = process, f"http://127.0.0.1:{port}"
        self.lock = asyncio.Lock()
        self.expected_send_timeouts = 0
        self.schema, self.socket_buffer_bytes = schema, socket_buffer_bytes
        self.crashed = False
        self.browser_origin = browser_origin

    @classmethod
    async def start(cls, schema, *, socket_buffer_bytes=0, browser_origin=None):
        extra = ["--browser-origin", browser_origin] if browser_origin is not None else []
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-u",
            str(Path(__file__).parent / "helpers" / "api_replica_process.py"),
            "--schema",
            schema,
            "--socket-buffer-bytes",
            str(socket_buffer_bytes),
            *extra,
            env={
                **os.environ,
                "VIGIL_PIPELINE_ENABLED": "false",
                "VIGIL_MONITORING_NETWORK_ENABLED": "false",
            },
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        replica = cls(process, 0, schema, socket_buffer_bytes, browser_origin)
        try:
            line = await asyncio.wait_for(process.stdout.readline(), 20)
            assert line, "Own replica exited before startup"
            ready = json.loads(line)
            assert ready["ready"] is True
            replica.base = f"http://127.0.0.1:{ready['port']}"
            return replica
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            await replica.stderr()
            await replica.close_stdin()
            raise

    async def stderr(self):
        stderr = await self.process.stderr.read()
        if stderr:
            report = Path(
                os.environ.get(
                    "VIGIL_TEST_ARTIFACTS_DIR",
                    str(Path(__file__).resolve().parents[2] / ".cache" / "verification"),
                )
            )
            report.mkdir(parents=True, exist_ok=True)
            (report / f"replica-stderr-{self.process.pid}.log").write_bytes(stderr)
        return stderr

    async def close_stdin(self):
        self.process.stdin.close()
        try:
            await self.process.stdin.wait_closed()
        except (BrokenPipeError, ConnectionResetError):
            pass  # own pipe can already be closed after deliberately killing its child

    async def crash(self):
        assert self.process.returncode is None
        self.process.kill()  # only this fixture's process object, never runtime/server PID
        await asyncio.wait_for(self.process.wait(), 5)
        self.crashed = True
        await self.close_stdin()
        assert self.process.returncode != 0 and not await self.stderr()

    async def restart(self):
        assert self.crashed and self.process.returncode is not None
        replacement = await type(self).start(
            self.schema,
            socket_buffer_bytes=self.socket_buffer_bytes,
            browser_origin=self.browser_origin,
        )
        self.process, self.base, self.crashed = replacement.process, replacement.base, False

    async def command(self, command, **data):
        async with self.lock:
            self.process.stdin.write((json.dumps({"command": command, **data}) + "\n").encode())
            await self.process.stdin.drain()
            line = await asyncio.wait_for(self.process.stdout.readline(), 10)
            assert line, "Own replica exited before telemetry reply"
            return json.loads(line)

    async def close(self):
        if self.process.returncode is not None:
            if not self.crashed:
                await self.stderr()
            await self.close_stdin()
            assert self.crashed, "Owned API exited unexpectedly"
            return
        if self.process.returncode is None:
            try:
                diagnostics = (await self.command("stats"))["errors"]
                assert await self.command("stop") == {"closed": True, "subscriptions": 0}
                assert await asyncio.wait_for(self.process.wait(), 10) == 0
                stderr = await self.stderr()
                assert diagnostics == {
                    "send_timeouts": self.expected_send_timeouts,
                    "unexpected": 0,
                }
                if self.expected_send_timeouts:
                    # Keep the complete original stderr as evidence. Only an
                    # EventResponse deadline observed on its actual traceback is
                    # expected; pool warnings or another server error still fail.
                    assert (
                        stderr.count(b"Exception in ASGI application")
                        == self.expected_send_timeouts
                    )
                    assert stderr.rstrip().endswith(b"TimeoutError")
                    assert not any(
                        word in stderr
                        for word in (b"SAWarning", b"sqlalchemy", b"WARNING:", b"Exception ignored")
                    )
                else:
                    assert not stderr
            finally:
                if self.process.returncode is None:
                    self.process.kill()  # only this fixture's child; never runtime API/server
                    await self.process.wait()
                await self.close_stdin()


@pytest_asyncio.fixture
async def replicas(pg_engine, request):
    url = os.getenv("VIGIL_TEST_REDIS_URL")
    if not url:
        pytest.skip("Set VIGIL_TEST_REDIS_URL for actual API replicas")
    async with Redis.from_url(url) as redis:
        assert await redis.ping()
    async with create_session_factory(pg_engine)() as db:
        schema = await db.scalar(select(func.current_schema()))
    result = []
    options = getattr(request, "param", {})
    try:
        for _ in range(options.get("count", 3)):
            result.append(
                await Replica.start(
                    schema, socket_buffer_bytes=options.get("socket_buffer_bytes", 0)
                )
            )
        yield result
    finally:
        cleanup_results = await asyncio.gather(
            *(replica.close() for replica in result), return_exceptions=True
        )
        for cleanup_result in cleanup_results:
            if isinstance(cleanup_result, BaseException):
                raise cleanup_result


class Frames:
    def __init__(self, response, project):
        self.response, self.project = response, project
        self.frames = []
        self.task = asyncio.create_task(self.read())

    async def read(self):
        kind, data = None, []
        async for line in self.response.aiter_lines():
            if line.startswith("event: "):
                kind = line[7:]
            elif line.startswith("data: "):
                data.append(line[6:])
            elif not line and kind and data:
                payload = json.loads("\n".join(data))
                assert "owner_id" not in payload and "source" not in payload
                if kind == "project.updated":
                    assert set(payload) == {"project_id", "revision"}
                    assert payload["project_id"] == self.project, "Owner isolation failed over TCP"
                else:
                    assert kind == "snapshot.required"
                self.frames.append((kind, payload, time.perf_counter()))
                kind, data = None, []

    def revisions(self):
        return [data["revision"] for kind, data, _ in self.frames if kind == "project.updated"]

    async def close(self, *, expected_disconnect=False):
        self.task.cancel()
        result = await asyncio.gather(self.task, return_exceptions=True)
        allowed = (
            (asyncio.CancelledError, httpx.ReadError, httpx.RemoteProtocolError)
            if expected_disconnect
            else (asyncio.CancelledError,)
        )
        assert result[0] is None or isinstance(result[0], allowed), result


async def wait_for(predicate, readers=(), *, timeout=15):
    async with asyncio.timeout(timeout):
        while not predicate():
            for reader in readers:
                if reader.task.done():
                    await reader.task  # report parser/isolation error instead of hiding timeout
                    raise AssertionError("Unexpected SSE EOF")
            await asyncio.sleep(0.01)


@pytest.mark.parametrize("replicas", [{"count": 2}], indirect=True)
async def test_real_api_crash_reconnect_snapshot_and_replacement_rejoins_fanout(replicas, request):
    failed, survivor = replicas
    readers, created, original = [], [], None
    crashed = False
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(httpx.AsyncClient(headers=HEADERS, timeout=5))
        credentials = {
            **LEGAL_VERSIONS,
            "email": f"recovery-{uuid4().hex}@example.com",
            "password": "isolated replica recovery password",
        }
        response = await client.post(failed.base + "/api/v1/auth/register", json=credentials)
        assert response.status_code == 201
        owner = response.json()["id"]
        response = await client.post(failed.base + "/api/v1/auth/login", json=credentials)
        assert response.status_code == 200
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        response = await client.post(
            failed.base + "/api/v1/projects", json={"name": "Replica recovery fixture"}
        )
        assert response.status_code == 201
        project = response.json()["id"]

        async def stream(replica):
            response = await stack.enter_async_context(
                client.stream("GET", replica.base + "/api/v1/events", timeout=None)
            )
            assert response.status_code == 200
            reader = Frames(response, project)
            created.append(reader)
            await wait_for(
                lambda: any(
                    kind == "snapshot.required" and data["reason"] == "connected"
                    for kind, data, _ in reader.frames
                ),
                [reader],
            )
            return reader

        try:
            original = await stream(failed)
            readers.append(await stream(survivor))
            old_pid = failed.process.pid
            started = time.perf_counter()
            await failed.crash()
            crashed = True
            async with asyncio.timeout(5):
                while not original.task.done():
                    await asyncio.sleep(0.01)
            result = (await asyncio.gather(original.task, return_exceptions=True))[0]
            assert result is None or isinstance(
                result, (httpx.ReadError, httpx.RemoteProtocolError)
            )
            assert not readers[0].task.done()
            response = await client.patch(
                survivor.base + "/api/v1/projects/" + project,
                json={"name": "Commit during lost stream"},
            )
            assert response.status_code == 200 and response.json()["revision"] == 1
            await wait_for(lambda: 1 in readers[0].revisions(), readers)
            # The missed hint has no replay. A newly connected stream requests
            # a REST snapshot, which recovers the durable commit made in the gap.
            reconnected = await stream(survivor)
            readers.append(reconnected)
            assert reconnected.revisions() == []
            response = await client.get(survivor.base + "/api/v1/projects/" + project)
            assert response.status_code == 200 and response.json()["revision"] == 1
            await failed.restart()
            assert failed.process.pid != old_pid
            replacement = await stream(failed)
            readers.append(replacement)
            response = await client.get(failed.base + "/api/v1/projects/" + project)
            assert response.status_code == 200 and response.json()["revision"] == 1
            async with asyncio.timeout(10):
                while not (await failed.command("stats"))["connected"]:
                    await asyncio.sleep(0.01)
            response = await client.patch(
                survivor.base + "/api/v1/projects/" + project,
                json={"name": "Commit after replacement"},
            )
            assert response.status_code == 200 and response.json()["revision"] == 2
            await wait_for(lambda: all(2 in reader.revisions() for reader in readers), readers)
            assert reconnected.revisions() == replacement.revisions() == [2]
            assert (await failed.command("stats"))["owners"] == {owner: 1}
            assert (await survivor.command("stats"))["owners"] == {owner: 2}
            request.node.user_properties.extend(
                [
                    ("reconnect_snapshot_revision", 1),
                    ("replacement_fanout_revision", 2),
                    ("recovery_seconds", round(time.perf_counter() - started, 3)),
                ]
            )
        finally:
            results = await asyncio.gather(
                *(
                    reader.close(expected_disconnect=reader is original and crashed)
                    for reader in created
                ),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, BaseException):
                    raise result


async def test_real_three_api_replicas_owner_fanout_bounded_queues_and_local_quota(
    replicas, request
):
    def record_property(name, value):
        request.node.user_properties.append((name, value))

    all_readers, accounts = [], []
    async with AsyncExitStack() as stack:
        redis = await stack.enter_async_context(Redis.from_url(os.environ["VIGIL_TEST_REDIS_URL"]))
        try:
            for index in range(6):
                client = await stack.enter_async_context(
                    httpx.AsyncClient(
                        base_url=replicas[0].base,
                        headers=HEADERS,
                        timeout=10,
                        limits=httpx.Limits(max_connections=32),
                    )
                )
                credentials = {
                    **LEGAL_VERSIONS,
                    "email": f"replica-{uuid4().hex}@example.com",
                    "password": "a strong isolated QA password",
                }
                response = await client.post("/api/v1/auth/register", json=credentials)
                assert response.status_code == 201
                owner = response.json()["id"]
                response = await client.post("/api/v1/auth/login", json=credentials)
                assert response.status_code == 200
                client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
                response = await client.post(
                    "/api/v1/projects", json={"name": f"Replica QA {index}"}
                )
                assert response.status_code == 201
                project = response.json()["id"]
                readers = []
                if index == 0:
                    for replica in replicas:
                        assert await replica.command("slow", owner=owner) == {"reserved": True}
                for replica in replicas:
                    for _ in range(2 if index == 0 else 3):
                        response = await stack.enter_async_context(
                            client.stream("GET", replica.base + "/api/v1/events", timeout=None)
                        )
                        assert response.status_code == 200
                        assert response.headers["content-type"].startswith("text/event-stream")
                        assert response.headers["cache-control"] == "no-store"
                        reader = Frames(response, project)
                        readers.append(reader)
                        all_readers.append(reader)
                    denied = await client.get(replica.base + "/api/v1/events")
                    assert (
                        denied.status_code == 429
                        and denied.json()["error"]["code"] == "sse_connection_limit"
                    )
                accounts.append(
                    {"owner": owner, "project": project, "client": client, "readers": readers}
                )
            await wait_for(
                lambda: all(
                    any(
                        kind == "snapshot.required" and payload["reason"] == "connected"
                        for kind, payload, _ in reader.frames
                    )
                    for reader in all_readers
                ),
                all_readers,
            )
            async with asyncio.timeout(10):
                while not all(
                    [(await replica.command("stats"))["connected"] for replica in replicas]
                ):
                    await asyncio.sleep(0.01)
            # Real commits through alternating replicas must invalidate every TCP stream.
            for revision in range(1, 4):
                for account in accounts:
                    response = await account["client"].patch(
                        replicas[(revision - 1) % 3].base
                        + "/api/v1/projects/"
                        + account["project"],
                        json={"name": f"Committed {revision}"},
                    )
                    assert response.status_code == 200 and response.json()["revision"] == revision
                await wait_for(
                    lambda: all(revision in reader.revisions() for reader in all_readers),
                    all_readers,
                )
            for reader in all_readers:
                assert reader.revisions() == [1, 2, 3]
            # Paced real Redis fanout: six owners, 51 HTTP streams, 600 signals.
            sent = {}
            started = time.perf_counter()
            for cycle in range(100):
                async with redis.pipeline(transaction=False) as pipeline:
                    for account in accounts:
                        sent[(account["project"], 1000 + cycle)] = time.perf_counter()
                        pipeline.publish(
                            "vigil:updates",
                            json.dumps(
                                {
                                    "type": "project.updated",
                                    "owner_id": account["owner"],
                                    "project_id": account["project"],
                                    "revision": 1000 + cycle,
                                }
                            ),
                        )
                    await pipeline.execute()
                await asyncio.sleep(0.02)
            await wait_for(
                lambda: all(1099 in reader.revisions() for reader in all_readers), all_readers
            )
            elapsed = time.perf_counter() - started
            latencies = []
            for reader in all_readers:
                assert [revision for revision in reader.revisions() if revision >= 1000] == list(
                    range(1000, 1100)
                )
                latencies.extend(
                    (at - sent[(reader.project, payload["revision"])]) * 1000
                    for kind, payload, at in reader.frames
                    if kind == "project.updated" and payload["revision"] >= 1000
                )
            # Unconsumed subscriptions must stay bounded and retain a reconciliation signal.
            target = accounts[0]
            async with redis.pipeline(transaction=False) as pipeline:
                for revision in range(2000, 3000):
                    pipeline.publish(
                        "vigil:updates",
                        json.dumps(
                            {
                                "type": "project.updated",
                                "owner_id": target["owner"],
                                "project_id": target["project"],
                                "revision": revision,
                            }
                        ),
                    )
                await pipeline.execute()
            await wait_for(
                lambda: all(2999 in reader.revisions() for reader in target["readers"]), all_readers
            )
            for replica in replicas:
                stats = await replica.command("stats")
                assert all(count == 3 for count in stats["owners"].values())
                assert stats["slow"][target["owner"]]["size"] <= 32
                assert stats["slow"][target["owner"]]["maxsize"] == 32
                records = (await replica.command("drain", owner=target["owner"]))["records"]
                assert any(
                    row == {"type": "snapshot.required", "reason": "backpressure"}
                    for row in records
                )
                assert records[-1]["revision"] == 2999
                assert await replica.command("drop", owner=target["owner"]) == {"released": True}
                # The released slot is immediately reusable over the real HTTP endpoint.
                async with target["client"].stream(
                    "GET", replica.base + "/api/v1/events", timeout=None
                ) as response:
                    assert response.status_code == 200
            # REST remains authoritative: load signals never manufacture persisted revisions.
            for replica in replicas:
                response = await target["client"].get(
                    replica.base + "/api/v1/projects/" + target["project"]
                )
                assert response.status_code == 200 and response.json()["revision"] == 3
                response = await accounts[1]["client"].get(
                    replica.base + "/api/v1/projects/" + target["project"]
                )
                assert response.status_code == 404
            record_property("replicas", 3)
            record_property("owners", 6)
            record_property("http_streams", len(all_readers))
            record_property("paced_signals", 600)
            record_property("paced_deliveries", len(latencies))
            record_property("paced_elapsed_seconds", round(elapsed, 3))
            record_property("latency_p50_ms", round(median(latencies), 3))
            record_property(
                "latency_p95_ms", round(sorted(latencies)[int(0.95 * (len(latencies) - 1))], 3)
            )
            record_property("burst_signals", 1000)
            # Logout through one replica revokes the shared session in all three.
            revoked_at = time.perf_counter()
            response = await target["client"].post(replicas[1].base + "/api/v1/auth/logout")
            assert response.status_code == 204
            await asyncio.wait_for(
                asyncio.gather(*(reader.task for reader in target["readers"])), 40
            )
            record_property("revocation_seconds", round(time.perf_counter() - revoked_at, 3))
            for replica in replicas:
                response = await target["client"].get(replica.base + "/api/v1/auth/me")
                assert response.status_code == 401
            assert all(
                not reader.task.done() for account in accounts[1:] for reader in account["readers"]
            )
        finally:
            for reader in all_readers:
                await reader.close()
    # TCP disconnect releases all real HTTP slots before stopping owned processes.
    async with asyncio.timeout(10):
        while any([(await replica.command("stats"))["owners"] for replica in replicas]):
            await asyncio.sleep(0.02)
