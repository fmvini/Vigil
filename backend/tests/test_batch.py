import asyncio
import json
from collections import Counter
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.config import Settings
from app.monitoring import batch
from app.security import utcnow


def settings(**kwargs):
    return Settings(
        pipeline_enabled=True,
        monitoring_network_enabled=True,
        redis_enabled=False,
        minimum_interval_seconds=900,
        **kwargs,
    )


def protected(monkeypatch):
    monkeypatch.setattr(batch.sys, "platform", "linux")
    monkeypatch.setattr(batch.os, "getuid", lambda: 10001, raising=False)
    monkeypatch.setattr(batch.os, "getgid", lambda: 10001, raising=False)
    monkeypatch.setenv("VIGIL_EGRESS_READY", "1")
    monkeypatch.setenv("VIGIL_WORKER_NAMESPACE", "dedicated")

    class Files:
        def __init__(self, path):
            self.path = path

        def is_file(self):
            return True

        def read_text(self):
            return "NoNewPrivs:\t1\nCapInh:\t0\nCapPrm:\t0\nCapEff:\t0\nCapBnd:\t0\nCapAmb:\t0"

    monkeypatch.setattr(batch, "Path", Files)


def test_os_guard_accepts_protected_linux_state(monkeypatch):
    protected(monkeypatch)
    batch.require_protected_egress()


@pytest.mark.parametrize("problem", ["windows", "root", "gid", "marker", "namespace", "cap", "nnp"])
def test_os_guard_refuses_unprotected_or_spoofed_environment(monkeypatch, problem):
    protected(monkeypatch)
    if problem == "windows":
        monkeypatch.setattr(batch.sys, "platform", "win32")
    elif problem == "root":
        monkeypatch.setattr(batch.os, "getuid", lambda: 0)
    elif problem == "gid":
        monkeypatch.setattr(batch.os, "getgid", lambda: 0)
    elif problem == "marker":
        monkeypatch.delenv("VIGIL_EGRESS_READY")
    elif problem == "namespace":
        monkeypatch.setenv("VIGIL_WORKER_NAMESPACE", "host")
    else:
        value = (
            "NoNewPrivs: 1\nCapInh:0\nCapPrm:0\nCapEff:1\nCapBnd:0\nCapAmb:0"
            if problem == "cap"
            else "NoNewPrivs:0\nCapInh:0\nCapPrm:0\nCapEff:0\nCapBnd:0\nCapAmb:0"
        )
        monkeypatch.setattr(batch.Path, "read_text", lambda self: value)
    with pytest.raises(ValueError):
        batch.require_protected_egress()


@pytest.mark.parametrize(
    "limits",
    [
        {"max_seconds": 91},
        {"max_seconds": 5},
        {"max_seconds": True},
        {"concurrency": 0},
        {"concurrency": 51},
        {"concurrency": 6},
        {"max_jobs": 0},
        {"max_jobs": True},
        {"retention_batches": 4},
    ],
)
async def test_batch_limits_are_validated_before_engine_creation(limits, monkeypatch):
    monkeypatch.setattr(batch, "create_engine", lambda *a, **kw: pytest.fail("Engine created"))
    with pytest.raises(ValueError):
        await batch.run_batch(settings(), **limits)


@pytest.mark.parametrize("pipeline,network", [(False, False), (True, False), (False, True)])
async def test_batch_gates_are_required_before_any_database(pipeline, network, monkeypatch):
    monkeypatch.setattr(batch, "create_engine", lambda *a, **kw: pytest.fail("Engine created"))
    with pytest.raises(ValueError):
        await batch.run_batch(
            Settings(pipeline_enabled=pipeline, monitoring_network_enabled=network)
        )


@pytest.fixture
def controlled(monkeypatch):
    states, statements, scheduled, observations = {}, [], [], []

    class Database:
        async def scalar(self, statement):
            return utcnow() if "clock_timestamp" in str(statement) else 0

        async def execute(self, statement):
            statements.append(str(statement))
            return SimpleNamespace(all=lambda: list(Counter(states.values()).items()))

    class Factory:
        @asynccontextmanager
        async def begin(self):
            yield Database()

        @asynccontextmanager
        async def __call__(self):
            yield Database()

    factory = Factory()
    monkeypatch.setattr(batch, "create_session_factory", lambda engine: factory)

    async def readiness(*args, **kwargs):
        observations.append("readiness")

    async def reconcile(db):
        observations.append("reconcile")

    async def schedule(db, **kwargs):
        scheduled.append(kwargs)
        assert observations[0] == "readiness"
        return []

    async def pending(factory, minimum, excluded, limit=100):
        assert minimum == 900
        return utcnow(), [
            (identifier, 1000, None, "https://one.example")
            for identifier, state in states.items()
            if state == "pending" and identifier not in excluded
        ]

    async def retention(*args, **kwargs):
        observations.append("retention")
        return SimpleNamespace(check_results=1, check_jobs=2, incidents=0, sessions=0, total=3)

    monkeypatch.setattr(batch, "database_ready", readiness)
    monkeypatch.setattr(batch, "reconcile_jobs", reconcile)
    monkeypatch.setattr(batch, "schedule_due", schedule)
    monkeypatch.setattr(batch, "pending_jobs", pending)
    monkeypatch.setattr(batch, "retain_batch", retention)
    return SimpleNamespace(
        states=states, statements=statements, scheduled=scheduled, observations=observations
    )


async def test_batch_admission_concurrency_retention_and_no_broker_import(controlled, monkeypatch):
    controlled.states.update({uuid4(): "pending" for _ in range(12)})
    activity = {"active": 0, "maximum": 0}

    async def process(factory, executor, identifier, *, signal):
        assert signal is None
        activity["active"] += 1
        activity["maximum"] = max(activity["maximum"], activity["active"])
        try:
            await asyncio.sleep(0.01)
            controlled.states[identifier] = "completed"
            return True
        finally:
            activity["active"] -= 1

    monkeypatch.setattr(batch, "process_job", process)
    report = await batch.run_batch(settings(), engine=object(), executor=object(), concurrency=5)
    assert report["status"] == "ok" and report["jobs_admitted"] == 12
    assert report["job_states"] == {"completed": 12} and report["attempts"] == 12
    assert activity["maximum"] == 5 and activity["active"] == 0
    assert report["retention"]["check_jobs"] == 2
    assert all(
        call["fresh_slot"] and call["minimum_interval_seconds"] == 900
        for call in controlled.scheduled
    )
    assert any("lock_timeout" in sql for sql in controlled.statements)
    assert any("statement_timeout" in sql for sql in controlled.statements)
    # Loading batch itself has no dependency on the Redis Taskiq task module.
    assert "app.monitoring.tasks" not in batch.__dict__


async def test_ack_boolean_is_not_reported_as_evaluated_check(controlled, monkeypatch):
    identifier = uuid4()
    controlled.states[identifier] = "pending"

    async def process(*args, **kwargs):
        controlled.states[identifier] = "expired"
        return True

    monkeypatch.setattr(batch, "process_job", process)
    report = await batch.run_batch(
        settings(), engine=object(), executor=object(), retention_batches=0
    )
    assert report["status"] == "partial" and report["job_states"] == {"expired": 1}


async def test_persistence_failure_cancels_other_admissions(controlled, monkeypatch):
    identifiers = [uuid4(), uuid4()]
    controlled.states.update({identifier: "pending" for identifier in identifiers})
    closed = []

    async def process(factory, executor, identifier, **kwargs):
        try:
            if identifier == identifiers[0]:
                await asyncio.sleep(0)
                raise OSError("private-database-password")
            await asyncio.Event().wait()
        finally:
            closed.append(identifier)

    monkeypatch.setattr(batch, "process_job", process)
    report = await batch.run_batch(settings(), engine=object(), executor=object())
    assert report["status"] == "error" and report["stage"] == "execution"
    assert report["error_code"] == "execution_failed" and "private" not in json.dumps(report)
    assert set(closed) == set(identifiers)
    assert "retention" not in controlled.observations


async def test_external_cancellation_cleans_active_operations(controlled, monkeypatch):
    identifier = uuid4()
    controlled.states[identifier] = "pending"
    reached, closed = asyncio.Event(), asyncio.Event()

    async def process(*args, **kwargs):
        reached.set()
        try:
            await asyncio.Event().wait()
        finally:
            closed.set()

    monkeypatch.setattr(batch, "process_job", process)
    operation = asyncio.create_task(batch.run_batch(settings(), engine=object(), executor=object()))
    await asyncio.wait_for(reached.wait(), 1)
    operation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await operation
    assert closed.is_set()


def test_cli_errors_are_sanitized_and_fail_before_database(monkeypatch, capsys):
    def failure():
        raise ValueError("private-database-password")

    monkeypatch.setattr(batch, "require_protected_egress", failure)
    assert batch.main([]) == 1
    output = capsys.readouterr().out
    assert "batch_failed" in output and "private" not in output


async def test_internal_deadline_cancels_work_and_returns_partial(controlled, monkeypatch):
    cleaned = asyncio.Event()

    async def blocked(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    monkeypatch.setattr(batch, "_execute", blocked)
    report = await asyncio.wait_for(
        batch.run_batch(settings(), engine=object(), executor=object(), max_seconds=5.02), 0.5
    )
    assert cleaned.is_set() and report["status"] == "partial" and report["deadline_reached"]
    assert report["stage"] == "execution" and report["error_code"] == "batch_deadline_exceeded"


async def test_failed_head_probe_prevents_scheduling_and_executor(controlled, monkeypatch):
    async def unavailable(*args, **kwargs):
        raise ValueError("private-schema-revision")

    monkeypatch.setattr(batch, "database_ready", unavailable)
    report = await batch.run_batch(settings(), engine=object(), executor=object())
    assert report["status"] == "error" and report["stage"] == "preflight"
    assert report["error_code"] == "preflight_failed" and "private" not in json.dumps(report)
    assert controlled.scheduled == [] and controlled.observations == []


async def test_preflight_own_deadline_is_not_global_deadline(controlled, monkeypatch):
    async def cold_database(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(batch, "database_ready", cold_database)
    report = await asyncio.wait_for(
        batch.run_batch(settings(readiness_timeout_seconds=0.02), engine=object()), 0.5
    )
    assert report["status"] == "error" and report["error_code"] == "preflight_timeout"
    assert report["stage"] == "preflight" and report["deadline_reached"] is False
    assert controlled.scheduled == [] and "retention" not in controlled.observations


async def test_global_deadline_during_preflight_is_global(controlled, monkeypatch):
    async def blocked(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(batch, "database_ready", blocked)
    report = await asyncio.wait_for(
        batch.run_batch(settings(readiness_timeout_seconds=10), engine=object(), max_seconds=5.02),
        0.5,
    )
    assert report["status"] == "partial" and report["error_code"] == "batch_deadline_exceeded"
    assert report["stage"] == "preflight" and report["deadline_reached"] is True


@pytest.mark.parametrize("stage", ["preflight", "execution", "summary", "retention"])
@pytest.mark.parametrize("failure", [TimeoutError, batch.DatabaseTimeoutError])
async def test_operation_timeout_preserves_stage_and_never_claims_global_deadline(
    controlled, monkeypatch, stage, failure
):
    async def timeout(*args, **kwargs):
        raise failure("private-password-and-hostname")

    if stage == "summary":

        async def execute(*args, **kwargs):
            class Unavailable:
                @asynccontextmanager
                async def __call__(self):
                    raise failure("private-password-and-hostname")
                    yield

            monkeypatch.setattr(type(args[0]), "__call__", Unavailable.__call__)

        monkeypatch.setattr(batch, "_execute", execute)
    else:
        monkeypatch.setattr(
            batch,
            {"preflight": "database_ready", "execution": "_execute", "retention": "retain_batch"}[
                stage
            ],
            timeout,
        )
    report = await batch.run_batch(settings(), engine=object(), executor=object())
    assert report["status"] == ("partial" if stage == "retention" else "error")
    assert report["stage"] == stage and report["error_code"] == f"{stage}_timeout"
    assert report["deadline_reached"] is False and "private" not in json.dumps(report)


async def test_retention_timeout_keeps_only_already_committed_counts(controlled, monkeypatch):
    calls = 0

    async def retention(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise TimeoutError("private-database")
        return SimpleNamespace(check_results=1, check_jobs=2, incidents=0, sessions=0, total=3)

    monkeypatch.setattr(batch, "retain_batch", retention)
    report = await batch.run_batch(settings(), engine=object(), retention_batches=2)
    assert report["status"] == "partial" and report["error_code"] == "retention_timeout"
    assert report["retention"] == {
        "check_results": 1,
        "check_jobs": 2,
        "incidents": 0,
        "sessions": 0,
    }
    assert report["deadline_reached"] is False


async def test_remote_retention_round_trips_can_exceed_two_seconds(controlled, monkeypatch):
    original = batch.retain_batch

    async def remote(*args, **kwargs):
        await asyncio.sleep(2.05)
        return await original(*args, **kwargs)

    monkeypatch.setattr(batch, "retain_batch", remote)
    report = await batch.run_batch(settings(), engine=object(), executor=object())
    assert report["status"] == "ok" and report["retention"]["check_jobs"] == 2
    assert report["deadline_reached"] is False


@pytest.mark.parametrize("readiness", [3, 10])
async def test_owned_engine_uses_readiness_connection_timeout_and_preserves_limits(
    controlled, monkeypatch, readiness
):
    captured, disposed = {}, []

    class Engine:
        async def dispose(self):
            disposed.append(True)

    def engine(url, **kwargs):
        captured.update(kwargs)
        return Engine()

    config = settings(
        readiness_timeout_seconds=readiness,
        database_ssl=True,
        database_schema="vigil",
        database_pool_size=2,
        database_max_overflow=0,
    )
    monkeypatch.setattr(batch, "create_engine", engine)
    report = await batch.run_batch(config, retention_batches=0)
    assert report["status"] == "ok" and report["stage"] == "complete" and disposed == [True]
    assert captured == {
        **config.database_options,
        "pool_timeout": 3,
        "connect_args": {
            "timeout": readiness,
            "command_timeout": 5,
            "server_settings": {"statement_timeout": "5000", "lock_timeout": "1000"},
        },
    }


@pytest.mark.parametrize("status", ["partial", "error"])
def test_cli_unsuccessful_reports_exit_one_without_private_error(monkeypatch, capsys, status):
    monkeypatch.setattr(batch, "require_protected_egress", lambda: None)
    monkeypatch.setattr(
        batch, "Settings", lambda: settings(database_url="postgresql+asyncpg://test")
    )

    async def run(*args, **kwargs):
        return {"status": status, "stage": "preflight", "error_code": "preflight_timeout"}

    monkeypatch.setattr(batch, "run_batch", run)
    assert batch.main([]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report == {"status": status, "stage": "preflight", "error_code": "preflight_timeout"}
