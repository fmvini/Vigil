"""Offline engine/TLS/schema contracts; never connect to a deployment database."""

import asyncio
import inspect
import os
import ssl
from io import StringIO
from uuid import uuid4

import asyncpg
import certifi
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool
from test_db_schema import migration_config

from app.db import session
from app.db.base import Base

URL = "postgresql+asyncpg://example:unused@pooler.example.invalid:5432/postgres"


@pytest.fixture
def capture_engine(monkeypatch):
    calls = []
    original = session.create_async_engine

    def construct(url, **options):
        calls.append((url, options))
        return original(url, **options)

    monkeypatch.setattr(session, "create_async_engine", construct)
    return calls


def test_schema_listener_awaits_driver_and_propagates_failure(monkeypatch):
    listeners, statements = [], []

    def listen(target, name):
        def register(callback):
            listeners.append(callback)
            return callback

        return register

    monkeypatch.setattr(session.event, "listens_for", listen)
    session.create_engine(URL)
    assert listeners == []
    session.create_engine(URL, database_schema="vigil")
    assert len(listeners) == 1

    class Driver:
        async def execute(self, sql):
            await asyncio.sleep(0)
            statements.append(sql)
            raise RuntimeError("connection configuration failed")

    class Adapter:
        def run_async(self, operation):
            return asyncio.run(operation(Driver()))

    with pytest.raises(RuntimeError, match="configuration failed"):
        listeners[0](Adapter(), None)
    assert statements == ['SET SESSION search_path TO "vigil"']


async def test_schema_is_set_even_when_proxy_discards_startup_parameter(monkeypatch):
    url = os.environ.get("VIGIL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires explicit PostgreSQL URL; no DDL or data mutations")
    original = session.create_async_engine

    def proxy(url, **options):
        arguments = dict(options.get("connect_args", {}))
        server = dict(arguments.get("server_settings", {}))
        server.pop("search_path", None)
        arguments["server_settings"] = server
        options["connect_args"] = arguments
        return original(url, **options)

    monkeypatch.setattr(session, "create_async_engine", proxy)
    engine = session.create_engine(url, database_schema="vigil_missing_test", pool_size=1)
    try:
        for _ in range(2):
            async with engine.connect() as connection:
                assert await connection.scalar(text("SHOW search_path")) == "vigil_missing_test"
                assert await connection.scalar(text("SELECT current_schema()")) is None
                await connection.rollback()
                assert await connection.scalar(text("SHOW search_path")) == "vigil_missing_test"
    finally:
        await engine.dispose()


def test_default_pool_and_cloud_limits_without_connecting(capture_engine):
    session.create_engine(URL)
    assert capture_engine[-1][1] == {
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 5,
        "pool_timeout": 30,
    }
    session.create_engine(URL, pool_size=2, max_overflow=0, pool_timeout=3)
    assert capture_engine[-1][1] == {
        "pool_pre_ping": True,
        "pool_size": 2,
        "max_overflow": 0,
        "pool_timeout": 3,
    }


def test_null_pool_accepts_common_size_options_without_forwarding_them(capture_engine):
    session.create_engine(URL, poolclass=NullPool, pool_size=2, max_overflow=0)
    assert capture_engine[-1][1] == {"pool_pre_ping": True, "poolclass": NullPool}


@pytest.mark.parametrize("custom_ca", [False, True])
def test_tls_has_ca_and_hostname_verification(capture_engine, monkeypatch, custom_ca):
    original = ssl.create_default_context
    cafiles = []

    def context(*args, **kwargs):
        cafiles.append(kwargs["cafile"])
        return original(*args, **kwargs)

    monkeypatch.setattr(session.ssl, "create_default_context", context)
    session.create_engine(
        URL,
        database_ssl=True,
        database_ssl_ca_file=certifi.where() if custom_ca else None,
    )
    assert cafiles == [certifi.where()]
    url, options = capture_engine[-1]
    tls = options["connect_args"]["ssl"]
    assert tls.check_hostname is True
    assert tls.verify_mode == ssl.CERT_REQUIRED
    assert tls.cert_store_stats()["x509_ca"] > 0
    assert url.host == "pooler.example.invalid"  # TCP relay must retain this TLS hostname.


def test_missing_ca_fails_before_engine_creation(capture_engine):
    with pytest.raises(FileNotFoundError):
        session.create_engine(URL, database_ssl=True, database_ssl_ca_file="missing-ca-file.pem")
    assert capture_engine == []


@pytest.mark.parametrize(
    "options",
    [
        {"database_ssl": "true"},
        {"database_ssl_ca_file": "ca.pem"},
        {"database_ssl": True, "connect_args": {"ssl": False}},
        {"pool_size": True},
        {"pool_size": 0},
        {"pool_size": 1.5},
        {"max_overflow": True},
        {"max_overflow": -1},
    ],
)
def test_invalid_or_conflicting_options_fail_before_engine(capture_engine, options):
    with pytest.raises(ValueError):
        session.create_engine(URL, **options)
    assert capture_engine == []


@pytest.mark.parametrize(
    "query", ["ssl=require", "sslmode=verify-full", "sslrootcert=ca.pem", "channel_binding=require"]
)
def test_explicit_tls_refuses_competing_url_settings(capture_engine, query):
    with pytest.raises(ValueError, match="Configure TLS"):
        session.create_engine(URL + "?" + query, database_ssl=True)
    assert capture_engine == []


def test_schema_and_timeouts_merge_without_mutating_caller(capture_engine):
    connect_args = {
        "timeout": 3,
        "command_timeout": 5,
        "server_settings": {"statement_timeout": "5000", "lock_timeout": "1000"},
    }
    session.create_engine(
        URL, database_schema="vigil", database_ssl=True, connect_args=connect_args
    )
    options = capture_engine[-1][1]["connect_args"]
    assert options["server_settings"] == {
        "statement_timeout": "5000",
        "lock_timeout": "1000",
        "search_path": "vigil",
    }
    assert "search_path" not in connect_args["server_settings"]
    assert "ssl" not in connect_args
    assert options["timeout"] == 3 and options["command_timeout"] == 5


@pytest.mark.parametrize(
    "schema", ["", "public,vigil", "vigil;DROP SCHEMA public", '"vigil"', "a" * 64, "Vigil", 1]
)
def test_schema_refused_before_any_engine_or_offline_ddl(capture_engine, monkeypatch, schema):
    with pytest.raises(ValueError, match="identifier"):
        session.create_engine(URL, database_schema=schema)
    assert capture_engine == []
    monkeypatch.setenv("VIGIL_DATABASE_SCHEMA", str(schema))
    output = StringIO()
    with pytest.raises(ValueError, match="identifier"):
        command.upgrade(migration_config(output=output), "head", sql=True)
    assert output.getvalue() == ""


def test_conflicting_search_path_is_refused(capture_engine):
    with pytest.raises(ValueError, match="search_path"):
        session.create_engine(
            URL,
            database_schema="vigil",
            connect_args={"server_settings": {"search_path": "public"}},
        )
    assert capture_engine == []


def test_sqlite_test_rejects_postgres_tls_and_schema(capture_engine):
    for option in ({"database_ssl": True}, {"database_schema": "vigil"}):
        with pytest.raises(ValueError, match="PostgreSQL"):
            session.create_engine(
                "sqlite+aiosqlite:///:memory:", allow_sqlite_for_tests=True, **option
            )
    assert capture_engine == []


def test_asyncpg_accepts_final_tls_kwargs_without_libpq_url_options():
    dialect = session.create_engine(URL, database_ssl=True, database_schema="vigil").dialect
    args, options = dialect.create_connect_args(make_url(URL))
    inspect.signature(asyncpg.connect).bind_partial(
        *args,
        **options,
        ssl=ssl.create_default_context(cafile=certifi.where()),
        server_settings={"search_path": "vigil"},
    )


def test_private_schema_offline_upgrade_and_downgrade(monkeypatch):
    monkeypatch.setenv("VIGIL_DATABASE_SCHEMA", "vigil")
    output = StringIO()
    command.upgrade(migration_config(output=output), "head", sql=True)
    sql = output.getvalue()
    assert sql.index('SET LOCAL search_path TO "vigil"') < sql.index("CREATE TABLE")
    assert "CREATE TABLE vigil.alembic_version" in sql
    assert "INSERT INTO vigil.alembic_version" in sql
    assert "0003_legal_acceptances" in sql
    assert "CREATE SCHEMA" not in sql
    assert "public." not in sql
    output = StringIO()
    command.downgrade(migration_config(output=output), "0003_legal_acceptances:base", sql=True)
    sql = output.getvalue()
    assert 'SET LOCAL search_path TO "vigil"' in sql
    assert "DELETE FROM vigil.alembic_version" in sql
    assert "CREATE SCHEMA" not in sql and "public." not in sql


@pytest.mark.parametrize("bootstrap", [False, True])
async def test_private_schema_migration_requires_explicit_bootstrap_and_matches_head(
    monkeypatch, bootstrap
):
    url = os.environ.get("VIGIL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires explicit PostgreSQL URL; schema UUID only")
    schema = "vigil_cloud_test_" + uuid4().hex
    monkeypatch.setenv("VIGIL_DATABASE_SCHEMA", schema)
    admin = session.create_engine(url, poolclass=NullPool)
    scoped = session.create_engine(url, database_schema=schema, pool_size=2, max_overflow=0)
    created = False
    public_catalog = text(
        "SELECT oid, relname FROM pg_class WHERE relnamespace='public'::regnamespace ORDER BY oid"
    )
    schema_exists = text("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname=:schema)")
    try:
        async with admin.begin() as connection:
            public_before = (await connection.execute(public_catalog)).all()
            assert not await connection.scalar(schema_exists, {"schema": schema})
            if bootstrap:
                await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
                created = True

        def migrate(connection):
            config = migration_config()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        if not bootstrap:
            async with scoped.connect() as connection:
                assert await connection.scalar(text("SELECT current_schema()")) is None
                await connection.rollback()
            with pytest.raises(DBAPIError) as error:
                async with scoped.begin() as connection:
                    await connection.run_sync(migrate)
            assert error.value.orig.sqlstate == "3F000"  # Missing schema, no automatic bootstrap.
        else:
            async with scoped.begin() as connection:
                await connection.run_sync(migrate)
                assert await connection.scalar(text("SELECT current_schema()")) == schema
                assert (
                    await connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == "0003_legal_acceptances"
                )
                assert (
                    await connection.scalar(
                        text(
                            "SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.oid='alembic_version'::regclass"
                        )
                    )
                    == schema
                )
                differences = await connection.run_sync(
                    lambda c: compare_metadata(MigrationContext.configure(c), Base.metadata)
                )
                assert differences == []
        async with admin.connect() as connection:
            assert (await connection.execute(public_catalog)).all() == public_before
    finally:
        await scoped.dispose()
        try:
            if created:
                async with admin.begin() as connection:
                    await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            async with admin.connect() as connection:
                assert not await connection.scalar(schema_exists, {"schema": schema})
        finally:
            await admin.dispose()
