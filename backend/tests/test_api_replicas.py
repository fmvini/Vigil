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
from redis.asyncio import Redis
from sqlalchemy import func, select
from test_db_postgresql import pg_engine as pg_engine

from app.db.session import create_session_factory

pytestmark = [pytest.mark.postgres, pytest.mark.redis]
HEADERS = {"Origin": "http://vigil-qa.test", "X-Vigil-Request": "browser"}


class Replica:
    def __init__(self, process, port):
        self.process, self.base = process, f"http://127.0.0.1:{port}"
        self.lock = asyncio.Lock()

    async def command(self, command, **data):
        async with self.lock:
            self.process.stdin.write((json.dumps({"command": command, **data}) + "\n").encode())
            await self.process.stdin.drain()
            line = await asyncio.wait_for(self.process.stdout.readline(), 10)
            assert line, "Own replica exited before telemetry reply"
            return json.loads(line)

    async def close(self):
        if self.process.returncode is None:
            try:
                assert await self.command("stop") == {"closed": True, "subscriptions": 0}
                assert await asyncio.wait_for(self.process.wait(), 10) == 0
                stderr = await self.process.stderr.read()
                if stderr:
                    report = Path(__file__).resolve().parents[2] / ".cache" / "verification"
                    report.mkdir(parents=True, exist_ok=True)
                    (report / f"replica-stderr-{self.process.pid}.log").write_bytes(stderr)
                assert not stderr
            finally:
                if self.process.returncode is None:
                    self.process.kill()  # only this fixture's child; never runtime API/server
                    await self.process.wait()
                self.process.stdin.close()
                await self.process.stdin.wait_closed()


@pytest_asyncio.fixture
async def replicas(pg_engine):
    url = os.getenv("VIGIL_TEST_REDIS_URL")
    if not url:
        pytest.skip("Set VIGIL_TEST_REDIS_URL for actual API replicas")
    async with Redis.from_url(url) as redis:
        assert await redis.ping()
    async with create_session_factory(pg_engine)() as db:
        schema = await db.scalar(select(func.current_schema()))
    processes, result = [], []
    try:
        for _ in range(3):
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-u",
                str(Path(__file__).parent / "helpers" / "api_replica_process.py"),
                "--schema",
                schema,
                env={
                    **os.environ,
                    "VIGIL_PIPELINE_ENABLED": "false",
                    "VIGIL_MONITORING_NETWORK_ENABLED": "false",
                },
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            processes.append(process)
            line = await asyncio.wait_for(process.stdout.readline(), 20)
            assert line, "Own replica exited before startup"
            ready = json.loads(line)
            assert ready["ready"] is True
            result.append(Replica(process, ready["port"]))
        yield result
    finally:
        cleanup_results = await asyncio.gather(
            *(replica.close() for replica in result), return_exceptions=True
        )
        for process in processes:
            if process.returncode is None:
                process.kill()
                await process.wait()
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

    async def close(self):
        self.task.cancel()
        result = await asyncio.gather(self.task, return_exceptions=True)
        assert result[0] is None or isinstance(result[0], asyncio.CancelledError), result


async def wait_for(predicate, readers=(), *, timeout=15):
    async with asyncio.timeout(timeout):
        while not predicate():
            for reader in readers:
                if reader.task.done():
                    await reader.task  # report parser/isolation error instead of hiding timeout
                    raise AssertionError("Unexpected SSE EOF")
            await asyncio.sleep(0.01)


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
