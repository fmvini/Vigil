"""Native product EventSource recovery through an exclusively owned UI/proxy."""

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "tests"))

from test_api_replicas import Replica  # noqa: E402
from test_db_postgresql import pg_engine as pg_engine  # noqa: E402

from app.db.session import create_session_factory  # noqa: E402


class Browser:
    def __init__(self, process):
        self.process = process

    async def command(self, command, **data):
        self.process.stdin.write((json.dumps({"command": command, **data}) + "\n").encode())
        await self.process.stdin.drain()
        line = await asyncio.wait_for(self.process.stdout.readline(), 25)
        assert line, "Own browser helper exited before response"
        result = json.loads(line)
        assert result["ok"], result
        return result

    async def close(self):
        try:
            if self.process.returncode is None:
                assert (await self.command("stop"))["stopped"]
            assert await asyncio.wait_for(self.process.wait(), 15) == 0
            stderr = await self.process.stderr.read()
            if stderr:
                directory = ROOT / ".cache" / "verification"
                directory.mkdir(parents=True, exist_ok=True)
                (directory / "reconnect-browser-stderr.log").write_bytes(stderr)
            assert not stderr
        finally:
            if self.process.returncode is None:
                self.process.kill()  # only own helper; context normally closes its Edge child
                await self.process.wait()
            self.process.stdin.close()
            await self.process.stdin.wait_closed()


async def test_real_native_browser_reconnect_recovers_gap_and_replacement(pg_engine, request):
    if not os.getenv("VIGIL_TEST_REDIS_URL"):
        pytest.skip("Redis URL required for native browser recovery")
    if not shutil.which("node"):
        pytest.skip("Node/Playwright/Edge required for native browser recovery")
    async with create_session_factory(pg_engine)() as db:
        schema = await db.scalar(select(func.current_schema()))
    process = await asyncio.create_subprocess_exec(
        "node",
        str(ROOT / "frontend" / "scripts" / "reconnect-browser-process.mjs"),
        cwd=ROOT / "frontend",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    browser, replicas = Browser(process), []
    try:
        line = await asyncio.wait_for(process.stdout.readline(), 30)
        assert line, "Owned UI/browser did not start"
        ready = json.loads(line)
        assert ready["ready"] is True
        for _ in range(2):
            replicas.append(await Replica.start(schema, browser_origin=ready["ui"]))
        failed, survivor = replicas
        identity = await browser.command("connect", api=failed.base)
        await failed.crash()
        assert (await browser.command("observe_failure"))["closed"]
        assert (await browser.command("gap_commit", api=survivor.base))["revision"] == 1
        assert (await browser.command("restore", api=survivor.base))["revision"] == 1
        await failed.restart()
        assert (await browser.command("cutover", api=failed.base))["connected"]
        async with asyncio.timeout(10):
            while not (await failed.command("stats"))["connected"]:
                await asyncio.sleep(0.01)
        assert (await browser.command("final_commit", api=survivor.base))["revision"] == 2
        assert (await browser.command("logout"))["passed"]
        async with asyncio.timeout(10):
            while any([(await replica.command("stats"))["owners"] for replica in replicas]):
                await asyncio.sleep(0.02)
        request.node.user_properties.extend(
            [
                ("native_browser", "Edge"),
                ("restored_revision", 1),
                ("replacement_revision", 2),
                ("initial_event_sources", identity["initialConstructors"]),
            ]
        )
    finally:
        # Close the UI first; then every own API, even if another teardown fails.
        errors = []
        try:
            await browser.close()
        except BaseException as error:
            errors.append(error)
        errors.extend(
            await asyncio.gather(*(replica.close() for replica in replicas), return_exceptions=True)
        )
        for error in errors:
            if isinstance(error, BaseException):
                raise error
