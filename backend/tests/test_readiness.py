"""Revision gate SQL on controlled SQLite and disposable PostgreSQL UUID schemas."""

import asyncio
import os
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from alembic.script import ScriptDirectory
from alembic.script.revision import Revision, RevisionMap
from sqlalchemy import event, text

from app.config import Settings
from app.db.session import create_engine
from app.main import create_app
from app.readiness import migration_head


class RuntimeEngine:
    # A non-SQLite adapter ensures controlled SQL exercises the runtime revision gate.
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self, engine):
        self.engine = engine

    def connect(self):
        return self.engine.connect()


@pytest.fixture(params=["sqlite", "postgres"])
async def readiness_engine(request):
    admin, schema, engine = None, None, None
    schema_created = False
    try:
        if request.param == "postgres":
            url = os.getenv("VIGIL_TEST_DATABASE_URL")
            if not url:
                pytest.skip("Set VIGIL_TEST_DATABASE_URL for isolated PostgreSQL readiness tests")
            schema = "readiness_test_" + uuid4().hex
            admin = create_engine(url)
            async with admin.begin() as connection:
                await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            schema_created = True
            engine = create_engine(url, connect_args={"server_settings": {"search_path": schema}})
        else:
            engine = create_engine("sqlite+aiosqlite:///:memory:", allow_sqlite_for_tests=True)
        yield engine
    finally:
        if engine is not None:
            await engine.dispose()
        if admin is not None:
            try:
                if schema_created:
                    async with admin.begin() as connection:
                        await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            finally:
                await admin.dispose()


async def probe(app, path="/health/ready"):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://app.test"
    ) as client:
        return await client.get(path)


@pytest.mark.parametrize("state", ["missing", "empty", "old", "unknown", "multiple", "head"])
async def test_runtime_revision_gate_is_read_only_and_sanitized(readiness_engine, state):
    head = migration_head()
    if state != "missing":
        async with readiness_engine.begin() as connection:
            await connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(64))"))
            values = {
                "empty": [],
                "old": ["0001_initial"],
                "unknown": ["private-unknown-revision"],
                "multiple": [head, "private-unknown-revision"],
                "head": [head],
            }[state]
            for revision in values:
                await connection.execute(
                    text("INSERT INTO alembic_version VALUES (:revision)"), {"revision": revision}
                )
    statements = []

    def observe(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(readiness_engine.sync_engine, "before_cursor_execute", observe)
    try:
        app = create_app(Settings(), engine=RuntimeEngine(readiness_engine))
        assert statements == []  # Construction/import does not open or migrate the database.
        assert (await probe(app, "/health/live")).json() == {"status": "ok"}
        response = await probe(app)
    finally:
        event.remove(readiness_engine.sync_engine, "before_cursor_execute", observe)
    assert statements == ["select 1", "select version_num from alembic_version limit 2"]
    assert response.status_code == (200 if state == "head" else 503)
    if state == "head":
        assert response.json() == {"status": "ok", "dependencies": {"database": "ok"}}
    else:
        assert response.json() == {
            "error": {"code": "not_ready", "message": "Database is not ready", "details": None}
        }
    assert "private-" not in response.text and head not in response.text


@pytest.mark.parametrize("configuration", ["missing", "multiple"])
async def test_invalid_packaged_migrations_fail_readiness_only(
    readiness_engine, monkeypatch, configuration
):
    from app import main

    def invalid_head():
        if configuration == "multiple":
            raise ValueError("private-ambiguous-migration-path")
        return None

    monkeypatch.setattr(main, "migration_head", invalid_head)
    app = create_app(Settings(), engine=RuntimeEngine(readiness_engine))
    assert (await probe(app, "/health/live")).status_code == 200
    response = await probe(app)
    assert response.status_code == 503 and response.json()["error"]["code"] == "not_ready"
    assert "private-" not in response.text


def test_head_uses_packaged_migrations_independent_of_cwd(monkeypatch):
    expected = migration_head()
    monkeypatch.chdir("app")
    assert migration_head() == expected


@pytest.mark.parametrize("heads", [[], ["first", "second"]])
def test_invalid_packaged_heads_are_rejected(monkeypatch, heads):
    from app import readiness

    scripts = ScriptDirectory("migrations")
    scripts.revision_map = RevisionMap(lambda: iter(Revision(head, None) for head in heads))
    monkeypatch.setattr(readiness, "ScriptDirectory", lambda path: scripts)
    with pytest.raises(Exception, match="[Mm]ultiple heads|head is missing"):
        readiness.migration_head()


@pytest.mark.parametrize("stage", ["connect", "query"])
@pytest.mark.parametrize("cancel", [False, True])
async def test_deadline_and_external_cancellation_cover_connection_and_revision(stage, cancel):
    reached, cleaned = asyncio.Event(), asyncio.Event()

    async def block():
        reached.set()
        await asyncio.Event().wait()

    class Connection:
        async def execute(self, statement):
            if "alembic_version" in str(statement):
                await block()

    class Engine:
        dialect = SimpleNamespace(name="postgresql")

        @asynccontextmanager
        async def connect(self):
            try:
                if stage == "connect":
                    await block()
                yield Connection()
            finally:
                cleaned.set()

    app = create_app(Settings(readiness_timeout_seconds=0.05 if not cancel else 3), engine=Engine())
    operation = asyncio.create_task(probe(app))
    try:
        await asyncio.wait_for(reached.wait(), 1)
        if cancel:
            operation.cancel()
            with pytest.raises(asyncio.CancelledError):
                await operation
        else:
            result = await asyncio.wait_for(operation, 1)
            assert result.status_code == 503 and result.json()["error"]["code"] == "not_ready"
        assert cleaned.is_set()
        assert (await probe(app, "/health/live")).status_code == 200
    finally:
        operation.cancel()
        await asyncio.gather(operation, return_exceptions=True)


async def test_explicit_sqlite_test_engine_keeps_connectivity_probe(readiness_engine):
    if readiness_engine.dialect.name != "sqlite":
        pytest.skip("SQLite-only test adapter exemption")
    app = create_app(Settings(), engine=readiness_engine)
    assert (await probe(app)).status_code == 200


async def test_owned_sqlite_engine_does_not_bypass_revision_gate(monkeypatch, readiness_engine):
    from app import main

    if readiness_engine.dialect.name != "sqlite":
        pytest.skip("SQLite-only owned engine guard")
    monkeypatch.setattr(main, "create_engine", lambda *args, **kwargs: readiness_engine)
    app = create_app(Settings(environment="test", database_url="sqlite+aiosqlite:///:memory:"))
    assert (await probe(app)).status_code == 503
