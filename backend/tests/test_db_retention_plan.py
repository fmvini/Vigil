"""Lease, ownership and failure contracts for the real-PG plan experiment."""

import asyncio
import io
import json
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from app.db import retention_plan_qa as qa

TOKEN = uuid4().hex
HOST = "172.25.0.2"


def environment():
    return {
        "VIGIL_RETENTION_PLAN_QA": "1",
        "VIGIL_RETENTION_QA_TOKEN": TOKEN,
        "VIGIL_RETENTION_QA_DATABASE_URL": f"postgresql+asyncpg://qa:fixture@{HOST}:5432/qa",
        "VIGIL_PIPELINE_ENABLED": "false",
        "VIGIL_MONITORING_NETWORK_ENABLED": "false",
    }


@pytest.mark.parametrize(
    "change",
    [
        {"VIGIL_RETENTION_PLAN_QA": "0"},
        {"VIGIL_RETENTION_QA_TOKEN": uuid4().hex},
        {"VIGIL_RETENTION_QA_DATABASE_URL": ""},
        {"VIGIL_RETENTION_QA_DATABASE_URL": "private-invalid-url"},
        {"VIGIL_RETENTION_QA_DATABASE_URL": "postgresql+asyncpg://qa:fixture@127.0.0.1:5432/qa"},
        {"VIGIL_RETENTION_QA_DATABASE_URL": f"postgresql+asyncpg://qa:fixture@{HOST}:5433/qa"},
        {"VIGIL_RETENTION_QA_DATABASE_URL": f"postgresql+asyncpg://qa:fixture@{HOST}:5432/runtime"},
        {"VIGIL_RETENTION_QA_DATABASE_URL": f"postgresql+asyncpg://qa:fixture@{HOST}:5432/qa?x=y"},
        {"VIGIL_MONITORING_NETWORK_ENABLED": "true"},
    ],
)
def test_invalid_lease_refused_before_engine(change):
    env = {**environment(), **change}
    with pytest.raises(ValueError):
        qa.lease_config(True, TOKEN, HOST, env)


def test_no_runtime_or_shared_test_url_fallback():
    env = environment()
    url = env.pop("VIGIL_RETENTION_QA_DATABASE_URL")
    env.update(VIGIL_DATABASE_URL=url, VIGIL_TEST_DATABASE_URL=url)
    with pytest.raises(ValueError):
        qa.lease_config(True, TOKEN, HOST, env)
    with pytest.raises(ValueError):
        qa.lease_config(False, TOKEN, HOST, environment())
    assert qa.lease_config(True, TOKEN, HOST, environment()).token == TOKEN


async def test_fixture_open_evidence_is_plausible_and_all_references_match_monitor():
    rows = {}

    class FixtureConnection:
        async def execute(self, statement, parameters):
            rows.setdefault(statement.table.name, []).extend(parameters)

    await qa.seed_fixture(FixtureConnection())
    incidents = rows["incidents"]
    results = {row["id"]: row for row in rows["check_results"]}
    assert len(incidents) == len(results) == len(rows["check_jobs"]) == 10_000
    assert len(rows["monitors"]) == 100
    opened = [row for row in incidents if row["ended_at"] is None]
    assert len(opened) == 100
    assert all(row["opening_check_id"] and row["closing_check_id"] is None for row in opened)
    assert sum(row["opening_check_id"] is not None for row in incidents) == 5000
    assert sum(row["closing_check_id"] is not None for row in incidents) == 5000
    for incident in incidents:
        for name in ("opening_check_id", "closing_check_id"):
            if incident[name] is not None:
                assert results[incident[name]]["monitor_id"] == incident["monitor_id"]


class Result:
    def __init__(self, row):
        self.row = row

    def one(self):
        return self.row


class Connection:
    def __init__(self, version=170011, marker=None):
        self.version = version
        self.marker = marker
        self.exists = False
        self.statements = []

    async def execute(self, statement, parameters=None):
        sql = str(statement)
        self.statements.append(sql)
        if "current_setting" in sql:
            return Result(("qa", "qa", self.version))
        if sql.startswith("CREATE SCHEMA"):
            self.exists = True
        if sql.startswith("COMMENT ON SCHEMA"):
            self.marker = sql.split(" IS '", 1)[1][:-1]
        if sql.startswith("DROP SCHEMA"):
            self.exists = False
        return Result(())

    async def scalar(self, statement, parameters=None):
        sql = str(statement)
        if "obj_description" in sql:
            return self.marker
        if "EXISTS" in sql:
            return self.exists
        if "current_schema" in sql:
            return self.schema
        if "version_num" in sql:
            return qa.BASE_REVISION
        raise AssertionError(sql)

    async def run_sync(self, function, *args):
        pass


class Engine:
    def __init__(self, connection):
        self.connection = connection
        self.disposed = False

    @asynccontextmanager
    async def begin(self):
        yield self.connection

    @asynccontextmanager
    async def connect(self):
        yield self.connection

    async def dispose(self):
        self.disposed = True


async def test_major17_is_required_before_any_ddl(monkeypatch):
    connection = Connection(version=180000)
    engines = []

    def engine(*args, **kwargs):
        instance = Engine(connection)
        engines.append(instance)
        return instance

    monkeypatch.setattr(qa, "create_engine", engine)
    report = {}
    with pytest.raises(ValueError, match="PG17"):
        await qa.run_experiment(qa.lease_config(True, TOKEN, HOST, environment()), report)
    assert not any("CREATE" in sql or "DROP" in sql for sql in connection.statements)
    assert all(item.disposed for item in engines)


@pytest.mark.parametrize("error", [RuntimeError, asyncio.CancelledError])
async def test_failure_or_cancellation_cleans_owned_schema_and_disposes(monkeypatch, error):
    admin = Connection()
    engines = []

    def engine(*args, **kwargs):
        connection = admin if not engines else Connection()
        if engines:
            connection.schema = kwargs["connect_args"]["server_settings"]["search_path"]
        instance = Engine(connection)
        engines.append(instance)
        return instance

    async def fail(connection):
        raise error("private-error")

    monkeypatch.setattr(qa, "create_engine", engine)
    monkeypatch.setattr(qa, "seed_fixture", fail)
    report = {}
    with pytest.raises(error):
        await qa.run_experiment(qa.lease_config(True, TOKEN, HOST, environment()), report)
    assert report["error_class"] == error.__name__
    assert report["schema_absent_after_cleanup"]
    assert not admin.exists and all(item.disposed for item in engines)
    assert sum(sql.startswith("DROP SCHEMA") for sql in admin.statements) == 1


@pytest.mark.parametrize("marker", [None, "foreign-marker"])
async def test_missing_or_foreign_marker_preserved(marker):
    connection = Connection(marker=marker)
    connection.exists = True
    with pytest.raises(ValueError, match="marker mismatch"):
        await qa.drop_owned(Engine(connection), "vigil_retention_" + uuid4().hex, "expected", {})
    assert connection.exists
    assert not any(sql.startswith("DROP") for sql in connection.statements)


@pytest.mark.parametrize("cleanup_fails", [False, True])
async def test_report_completes_only_after_successful_cleanup(monkeypatch, cleanup_fails):
    admin = Connection()
    engines = []
    original_cleanup = qa.drop_owned

    class PlanConnection(Connection):
        async def scalar(self, statement, parameters=None):
            if "pg_relation_size" in str(statement):
                return 0
            return await super().scalar(statement, parameters)

    def engine(*args, **kwargs):
        connection = admin if not engines else PlanConnection()
        if engines:
            connection.schema = kwargs["connect_args"]["server_settings"]["search_path"]
        instance = Engine(connection)
        instance.sync_engine = object()
        engines.append(instance)
        return instance

    async def no_fixture(connection):
        pass

    async def snapshot(*args):
        return {}

    async def capture(*args):
        return [], {}

    report = {"completed": True}

    async def cleanup(admin_engine, schema, marker, current_report):
        assert current_report["completed"] is False
        assert current_report["fixture_rollback_verified"] is True
        if cleanup_fails:
            raise RuntimeError("private-cleanup-error")
        await original_cleanup(admin_engine, schema, marker, current_report)

    monkeypatch.setattr(qa, "create_engine", engine)
    monkeypatch.setattr(qa, "seed_fixture", no_fixture)
    monkeypatch.setattr(qa, "fingerprint", snapshot)
    monkeypatch.setattr(qa, "fixture_distribution", snapshot)
    monkeypatch.setattr(qa, "capture_retention", capture)
    monkeypatch.setattr(qa, "incident_catalog", snapshot)
    monkeypatch.setattr(qa.event, "listen", lambda *args: None)
    monkeypatch.setattr(qa.event, "remove", lambda *args: None)
    monkeypatch.setattr(qa, "drop_owned", cleanup)
    lease = qa.lease_config(True, TOKEN, HOST, environment())
    if cleanup_fails:
        with pytest.raises(RuntimeError, match="private-cleanup-error"):
            await qa.run_experiment(lease, report)
        assert report["completed"] is False
        assert "schema_absent_after_cleanup" not in report
        assert admin.exists
    else:
        await qa.run_experiment(lease, report)
        assert report["completed"] is True
        assert report["schema_absent_after_cleanup"] is True
        assert not admin.exists
    assert all(instance.disposed for instance in engines)


async def test_explain_preserves_driver_parameters_without_analyze():
    captured = []
    expected_parameters = (uuid4(),)

    class DriverConnection:
        async def exec_driver_sql(self, statement, parameters):
            captured.append((statement, parameters))

            class Plan:
                def scalar_one(self):
                    return [
                        {
                            "Plan": {
                                "Node Type": "Seq Scan",
                                "Relation Name": "incidents",
                                "Total Cost": 123,
                                "Plan Rows": 1,
                            }
                        }
                    ]

            return Plan()

    plan = await qa.explain(
        DriverConnection(),
        "SELECT id FROM incidents WHERE opening_check_id=$1::UUID",
        expected_parameters,
    )
    assert captured[0][0].startswith("EXPLAIN (FORMAT JSON) SELECT")
    assert "ANALYZE" not in captured[0][0]
    assert captured[0][1] is expected_parameters
    assert plan["estimated_total_cost"] == 123


def test_cli_error_output_contains_only_error_class(monkeypatch, capsys):
    for key, value in environment().items():
        monkeypatch.setenv(key, value)

    class Output(io.StringIO):
        def __exit__(self, *args):
            pass

    output = Output()
    monkeypatch.setattr(qa.Path, "open", lambda *args, **kwargs: output)

    async def fail(lease, report):
        raise RuntimeError("private-DSN-secret")

    monkeypatch.setattr(qa, "run_experiment", fail)
    assert (
        qa.main(
            ["--qa-opt-in", "--token", TOKEN, "--lease-host", HOST, "--report-file", "report.json"]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().out) == {
        "completed": False,
        "error_class": "RuntimeError",
    }
    assert "private-DSN-secret" not in output.getvalue()
