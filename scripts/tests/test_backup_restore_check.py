import copy
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backup_restore_check as backup  # noqa: E402

URL = "postgresql+asyncpg://vigil:qa_password@127.0.0.1:55433/vigil"


def schema_tables(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "backend"))
    from app.db.models import Base

    return tuple(sorted((*Base.metadata.tables, "alembic_version")))


def test_backup_inventory_covers_current_application_schema(monkeypatch):
    assert backup.TABLES == schema_tables(monkeypatch)


@pytest.mark.asyncio
async def test_manifest_fingerprints_legal_rows_and_schema(monkeypatch):
    tables = schema_tables(monkeypatch)

    class Connection:
        legal_rows = [
            json.dumps(
                {
                    "id": "acceptance-" + str(index),
                    "user_id": "owner-id",
                    "terms_version": "2026-10-09",
                    "privacy_version": "2026-10-09",
                    "accepted_at": "2026-10-10T12:00:00+00:00",
                    "action": "login",
                }
            )
            for index in (1, 2)
        ]

        def is_in_transaction(self):
            return True

        async def fetchval(self, query):
            return tables

        async def fetch(self, query, *args):
            if "SELECT version_num" in query:
                return [("0003_legal_acceptances",)]
            if args[0] not in {"legal_acceptances", "public.legal_acceptances"}:
                return []
            if "information_schema.columns" in query:
                return [
                    {"column_name": name}
                    for name in (
                        "id", "user_id", "terms_version", "privacy_version", "accepted_at", "action"
                    )
                ]
            if "pg_constraint" in query:
                return [{"contype": "f", "definition": "FOREIGN KEY (user_id) REFERENCES users(id)"}]
            return [{"indexname": "ix_legal_acceptances_user_accepted_at"}]

        async def cursor(self, query, **kwargs):
            if '"legal_acceptances"' in query:
                assert query.endswith('ORDER BY "id"')
                for row in self.legal_rows:
                    yield (row,)

    db = Connection()
    original = await backup.manifest(db)
    assert original["revision"] == "0003_legal_acceptances"
    legal = original["tables"]["legal_acceptances"]
    assert legal["rows"] == 2
    assert len(legal["columns"]) == 6
    assert legal["constraints"] and legal["indexes"]
    backup.compare_manifests(original, copy.deepcopy(original))
    row = json.loads(db.legal_rows[0])
    row["privacy_version"] = "2026-10-10"
    db.legal_rows = [json.dumps(row), db.legal_rows[1]]
    changed = await backup.manifest(db)
    assert changed["tables"]["legal_acceptances"]["rows"] == legal["rows"]
    assert changed["tables"]["legal_acceptances"]["sha256"] != legal["sha256"]
    with pytest.raises(ValueError, match="differ"):
        backup.compare_manifests(original, changed)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["missing_legal", "unexpected_table"])
async def test_manifest_rejects_schema_drift(monkeypatch, change):
    tables = schema_tables(monkeypatch)
    names = (
        tuple(name for name in tables if name != "legal_acceptances")
        if change == "missing_legal"
        else tuple(sorted((*tables, "unreviewed_table")))
    )

    class Connection:
        async def fetchval(self, query):
            return names

    with pytest.raises(ValueError, match="known Vigil tables"):
        await backup.manifest(Connection())


@pytest.mark.parametrize(
    "url",
    [
        "",
        URL.replace("55433", "55432"),
        URL.replace("55433", "5432"),
        URL.replace("127.0.0.1", "remote.test"),
        URL.replace("/vigil", "/postgres"),
        URL + "?ssl=disable",
        URL + "#fragment",
        URL.replace("postgresql+asyncpg", "mysql"),
        "postgresql://vigil@localhost:55433/vigil",
    ],
)
def test_backup_rejects_any_target_outside_explicit_local_pg17(url):
    with pytest.raises(ValueError):
        backup.parse_target(url)


def test_backup_target_does_not_expose_password_in_repr():
    target = backup.parse_target(URL)
    assert "qa_password" not in repr(target)
    assert target.connection()["password"] == "qa_password"


@pytest.mark.parametrize(
    "name",
    [
        "vigil",
        "postgres",
        "vigil_restore_test_" + "a" * 32,
        "vigil_restore_qa_" + "a" * 31,
        "vigil_restore_qa_" + "z" * 32,
        "vigil_restore_qa_" + "a" * 32 + "; DROP DATABASE vigil",
    ],
)
def test_cleanup_rejects_non_exclusive_database_names(name):
    with pytest.raises(ValueError):
        backup.assert_owned_restore(name, "vigil")


@pytest.mark.parametrize("identifier", ["public;DROP SCHEMA public", "a.b", 'a"b', "../tmp"])
def test_sql_identifier_cannot_inject_statements(identifier):
    with pytest.raises(ValueError):
        backup.identifier(identifier)


@pytest.mark.parametrize("table", ["users", "legal_acceptances"])
@pytest.mark.parametrize("field", ["sha256", "columns", "indexes", "constraints"])
def test_validation_rejects_same_count_with_changed_rows_or_schema(field, table):
    original = {
        "revision": "0003_legal_acceptances",
        "tables": {
            table: {
                "rows": 2,
                "sha256": "original",
                "columns": [],
                "indexes": [],
                "constraints": [],
            }
        },
    }
    restored = copy.deepcopy(original)
    restored["tables"][table][field] = "changed"
    assert original["tables"][table]["rows"] == restored["tables"][table]["rows"]
    with pytest.raises(ValueError, match="differ"):
        backup.compare_manifests(original, restored)


@pytest.mark.asyncio
async def test_command_failure_redacts_native_stderr():
    with pytest.raises(backup.CommandFailed) as error:
        await backup.command(
            sys.executable, "-c", "import sys;sys.stderr.write('private-row');sys.exit(1)"
        )
    assert "private-row" not in str(error.value)


@pytest.mark.asyncio
async def test_timeout_stops_only_its_client():
    with pytest.raises(backup.CommandTimedOut):
        await backup.command(sys.executable, "-c", "import time;time.sleep(60)", timeout=0.1)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_point", ["pg_restore", "rm"])
async def test_cleanup_failures_are_never_reported_as_success(tmp_path, monkeypatch, failure_point):
    monkeypatch.setattr(backup, "PROJECT_ROOT", tmp_path)
    calls = []

    class Connection:
        @asynccontextmanager
        async def transaction(self, **kwargs):
            yield

        async def fetchval(self, query, *args):
            if query.startswith("SELECT EXISTS"):
                return False
            if query.startswith("SHOW"):
                return 170011
            if "system_identifier" in query:
                return "12345"
            return "snapshot-test"

        async def close(self, **kwargs):
            pass

    async def connect(**kwargs):
        return Connection()

    async def manifest(db):
        return {"revision": "0001_initial", "tables": {}}

    async def command(*args, **kwargs):
        calls.append(args)
        if args[:2] == ("docker", "inspect"):
            return json.dumps(
                [
                    {
                        "Config": {
                            "Env": ["POSTGRES_USER=vigil", "POSTGRES_DB=vigil"],
                            "Labels": {
                                "com.docker.compose.project": "vigil",
                                "com.docker.compose.service": "postgres",
                            },
                        }
                    }
                ]
            )
        if "psql" in args:
            return "12345"
        if args[:2] == ("docker", "cp"):
            Path(args[-1]).write_bytes(b"synthetic-dump")
        if failure_point == "pg_restore" and "pg_restore" in args:
            raise backup.CommandTimedOut()
        if failure_point == "rm" and "rm" in args:
            raise backup.CommandFailed()
        return ""

    monkeypatch.setattr(backup.asyncpg, "connect", connect)
    monkeypatch.setattr(backup, "manifest", manifest)
    monkeypatch.setattr(backup, "command", command)
    report, path = await backup.drill(backup.parse_target(URL), "vigil-postgres-1")
    assert path.exists()
    assert report["result"] == "failed"
    assert any("createdb" in args for args in calls)
    if failure_point == "pg_restore":
        assert report["cleanup"] == "pending_review"
        assert report["error_type"] == "CommandTimedOut"
        assert not any("dropdb" in args or "rm" in args for args in calls)
    else:
        assert report["cleanup"] == "confirmed" and report["content_verified"] is True
        assert report["temporary_dump_cleanup_error_type"] == "CommandFailed"
        assert sum("dropdb" in args for args in calls) == 1
        assert sum("rm" in args for args in calls) == 1


@pytest_asyncio.fixture
async def own_schema():
    url = os.getenv("VIGIL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set VIGIL_TEST_DATABASE_URL for PG17 backup snapshot tests")
    target = backup.parse_target(url)
    db = await asyncpg.connect(**target.connection())
    schema = "vigil_backup_test_" + uuid4().hex
    qualified = backup.identifier(schema)
    created = False
    try:
        assert 170000 <= int(await db.fetchval("SHOW server_version_num")) < 180000
        await db.execute(f"CREATE SCHEMA {qualified}")
        created = True
        await db.execute(
            f"CREATE TABLE {qualified}.records (id integer PRIMARY KEY, payload jsonb, at timestamptz)"
        )
        await db.execute(
            f"INSERT INTO {qualified}.records VALUES (2, '{{\"value\":2}}', '2026-10-04T12:00:00Z'), (1, '{{\"value\":1}}', '2026-10-04T13:00:00Z')"
        )
        yield db, target, schema
    finally:
        if created:
            await db.execute(f"DROP SCHEMA {qualified} CASCADE")
        await db.close(timeout=5)


@pytest.mark.asyncio
async def test_real_digest_detects_changed_value_with_same_row_count(own_schema):
    db, _, schema = own_schema
    async with db.transaction(isolation="repeatable_read", readonly=True):
        before = await backup.table_digest(db, schema, "records", "id")
    await db.execute(
        f"UPDATE {backup.identifier(schema)}.records SET payload='{{\"value\":3}}' WHERE id=1"
    )
    async with db.transaction(isolation="repeatable_read", readonly=True):
        after = await backup.table_digest(db, schema, "records", "id")
    assert before["rows"] == after["rows"] == 2
    assert before["sha256"] != after["sha256"]


@pytest.mark.asyncio
async def test_real_exported_snapshot_stays_identical_after_concurrent_commit(own_schema):
    db, target, schema = own_schema
    writer = await asyncpg.connect(**target.connection())
    observer = await asyncpg.connect(**target.connection())
    try:
        async with db.transaction(isolation="repeatable_read", readonly=True):
            snapshot = await db.fetchval("SELECT pg_export_snapshot()")
            before = await backup.table_digest(db, schema, "records", "id")
            await writer.execute(
                f"UPDATE {backup.identifier(schema)}.records SET payload='{{\"value\":99}}' WHERE id=1"
            )
            async with observer.transaction(isolation="repeatable_read", readonly=True):
                await observer.execute(
                    "SET TRANSACTION SNAPSHOT '" + snapshot.replace("'", "''") + "'"
                )
                assert await backup.table_digest(observer, schema, "records", "id") == before
        async with db.transaction(isolation="repeatable_read", readonly=True):
            assert await backup.table_digest(db, schema, "records", "id") != before
    finally:
        await writer.close(timeout=5)
        await observer.close(timeout=5)
