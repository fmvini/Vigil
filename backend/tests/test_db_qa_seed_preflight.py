"""Filesystem/transaction ordering; no PostgreSQL connection or seed execution."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.db import seed_observations_qa as seed


async def test_invalid_manifest_parent_refuses_before_engine_or_seed(monkeypatch):
    # Existing repository file avoids pytest temporary-directory ACL differences.
    parent = Path(__file__).resolve().parents[1] / "pyproject.toml"
    assert parent.is_file()
    manifest = parent / "qa-never-written.json"

    def reject_engine(url):
        pytest.fail("Invalid manifest parent must be rejected before database access")

    monkeypatch.setattr(seed, "create_engine", reject_engine)
    with pytest.raises(OSError):
        await seed.run_seed("unused-url", manifest)
    assert parent.is_file()


@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_seed_failure_rolls_back_and_disposes_without_manifest_write(monkeypatch, failure):
    events = []

    class Engine:
        async def dispose(self):
            events.append("dispose")

    class DB:
        async def scalar(self, statement):
            return 170011 if str(statement).startswith("SHOW") else "public"

    class Factory:
        @asynccontextmanager
        async def begin(self):
            events.append("begin")
            try:
                yield DB()
            except BaseException:
                events.append("rollback")
                raise
            else:
                events.append("commit")

    def create_engine(url):
        events.append("engine")
        return Engine()

    async def fail(db):
        events.append("seed")
        raise failure()

    def mkdir(**kwargs):
        events.append("mkdir")

    def reject_open(*args, **kwargs):
        pytest.fail("Failed/cancelled seed must not write a manifest")

    manifest = SimpleNamespace(parent=SimpleNamespace(mkdir=mkdir), open=reject_open)
    monkeypatch.setattr(seed, "create_engine", create_engine)
    monkeypatch.setattr(seed, "create_session_factory", lambda _: Factory())
    monkeypatch.setattr(seed, "seed_fixture", fail)
    with pytest.raises(failure):
        await seed.run_seed("unused-url", manifest)
    assert events == ["mkdir", "engine", "begin", "seed", "rollback", "dispose"]
