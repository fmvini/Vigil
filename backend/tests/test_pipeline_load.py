"""Small callback bursts and QA guards; no HTTP outside the manual Linux namespace.

These tests cover helper orchestration, not a synthetic CheckExecutor campaign.
Wire/PG17/Redis evidence is produced by Maestro's disposable Linux integration.
"""

import asyncio
import json
import os
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from helpers import pipeline_load_process as load
from sqlalchemy.exc import ProgrammingError


@pytest.fixture
def config():
    return load.Config(run_id=uuid4().hex, jobs=10, duration_seconds=0)


@pytest.mark.parametrize(
    "change",
    [
        {"run_id": "vigil_shared;DROP"},
        {"jobs": 0},
        {"jobs": 2001},
        {"jobs": True},
        {"callback_limit": 0},
        {"callback_limit": 51},
        {"duration_seconds": -1},
        {"duration_seconds": float("nan")},
        {"drain_timeout_seconds": float("inf")},
        {"drain_timeout_seconds": 0},
    ],
)
def test_invalid_campaign_limits_fail_before_resources(config, change):
    with pytest.raises(load.CampaignError):
        replace(config, **change)


def test_names_are_fixed_uuid_namespaces(config):
    dashed = str(uuid4())
    normalized = replace(config, run_id=dashed)
    assert normalized.schema == "vigil_test_" + dashed.replace("-", "")
    assert normalized.stream == "vigil:pipeline-load:" + normalized.run_id
    assert normalized.group == "group-" + normalized.run_id
    defaults = load.Config(config.run_id)
    assert defaults.jobs == 100 and defaults.duration_seconds == 60
    assert defaults.callback_limit == 50


def test_quantiles_are_interpolated_and_empty_samples_are_unknown():
    assert load.quantiles([]) == {"sample_count": 0, "p50": None, "p95": None, "p99": None}
    assert load.quantiles([30, 10, 20]) == {
        "sample_count": 3,
        "p50": 20,
        "p95": 29,
        "p99": pytest.approx(29.8),
    }
    assert load.quantiles([20])["p99"] == 20
    with pytest.raises(load.CampaignError, match="invalid_measurement"):
        load.quantiles([float("nan")])


async def test_small_callback_burst_is_bounded_and_drains():
    pool = load.CallbackPool(3)
    completed = []

    async def operation(index):
        await asyncio.sleep(0.01)
        completed.append(index)

    for index in range(12):
        await pool.submit(lambda value=index: operation(value))
    await pool.close()
    assert sorted(completed) == list(range(12))
    assert pool.maximum == 3 and pool.active == 0
    assert not pool.tasks and not pool.errors and pool.slots._value == 3


@pytest.mark.parametrize("started", [False, True])
async def test_callback_cancellation_awaits_owned_tasks_and_releases_admission(started):
    pool = load.CallbackPool(2)
    closed = []

    async def operation():
        try:
            await asyncio.Event().wait()
        finally:
            closed.append(True)

    await pool.submit(operation)
    await pool.submit(operation)
    if started:
        await asyncio.sleep(0)
    await pool.close(cancel=True)
    assert pool.active == 0 and pool.slots._value == 2
    assert not pool.tasks and not pool.errors
    assert len(closed) == (2 if started else 0)


async def test_shutdown_rejects_waiting_submission_and_collects_failure():
    pool = load.CallbackPool(1)

    async def blocked():
        await asyncio.Event().wait()

    await pool.submit(blocked)
    waiting = asyncio.create_task(pool.submit(blocked))
    await asyncio.sleep(0)
    await pool.close(cancel=True)
    with pytest.raises(load.CampaignError, match="callbacks_closed"):
        await waiting
    assert pool.slots._value == 1

    failures = load.CallbackPool(1)

    async def fail():
        raise RuntimeError("callback failure")

    await failures.submit(fail)
    await failures.close()
    assert len(failures.errors) == 1 and failures.active == 0


async def test_real_product_host_admission_remains_five_slots():
    limits = load.ObservedLimits()

    async def operation():
        async with limits.slot(load.HOST):
            await asyncio.sleep(0.01)

    await asyncio.gather(*(operation() for _ in range(12)))
    assert limits.maximum == 5 and limits.active == 0
    assert limits.hosts == {} and limits.global_slots._value == 50


def record():
    return load.Record(
        scheduled=1,
        schedule_transaction_ms=50,
        queue_delay_ms=17,
        http_ms=22,
        commit_call_ms=3,
        finalize_after_executor_ms=1000,
        publication_started=2,
        published=3,
        delivered=2.5,
        claim_commit=4,
        http_finished=5,
        result_commit=6,
        xack_started=6.25,
        xack_confirmed=6.5,
        acknowledged=7,
        verified_result=True,
        visibility_verified=True,
    )


def test_order_checks_commit_before_ack_without_false_xadd_confirmation_order():
    completed = record()
    completed.validate_order()  # Redis delivery may precede XADD reply at producer
    completed.acknowledged = 5.5
    with pytest.raises(load.CampaignError, match="stage_order_violation"):
        completed.validate_order()
    completed.acknowledged = 7
    completed.verified_result = False
    with pytest.raises(load.CampaignError):
        completed.validate_order()


async def test_dns_override_is_only_fixed_fixture_hostname():
    assert await load.resolver("sockets.example.com", 443) == ["93.184.216.34"]
    for host, port in [("other.example.com", 443), ("sockets.example.com", 80)]:
        with pytest.raises(load.CampaignError, match="unexpected_destination"):
            await load.resolver(host, port)


def test_shared_gates_and_missing_optin_refuse_before_namespace_or_connection(config, monkeypatch):
    monkeypatch.setattr(load.sys, "platform", "linux")
    monkeypatch.delenv("VIGIL_TEST_PIPELINE_LOAD_QA", raising=False)
    with pytest.raises(load.CampaignError, match="qa_opt_in_required"):
        load.environment(config)
    monkeypatch.setenv("VIGIL_TEST_PIPELINE_LOAD_QA", "1")
    monkeypatch.setenv("VIGIL_PIPELINE_ENABLED", "true")
    with pytest.raises(load.CampaignError, match="runtime_gates_must_be_false"):
        load.environment(config)


async def test_failure_report_preserves_original_error_and_still_awaits_cleanup(
    config, monkeypatch
):
    campaign = load.Campaign(config)
    cleanup = []
    monkeypatch.setattr(load, "environment", lambda _: ("unused-db", "unused-redis"))

    async def fail(*args):
        raise RuntimeError("private-dsn-and-password-never-output")

    async def release():
        await asyncio.sleep(0)
        cleanup.append(True)
        campaign.cleanup["schema"] = "failed"

    monkeypatch.setattr(campaign, "provision", fail)
    monkeypatch.setattr(campaign, "release", release)
    report = await campaign.run()
    assert cleanup == [True]
    assert not report["success"] and report["failure_code"] == "campaign_failed"
    assert report["failure_stage"] == "provision"
    assert report["exception_type"] == "RuntimeError"
    assert report["exception_types"] == ["RuntimeError"]
    assert report["cleanup"]["schema"] == "failed"
    assert "private-dsn" not in json.dumps(report)


async def test_nested_taskgroup_diagnostics_only_include_class_names(config, monkeypatch):
    campaign = load.Campaign(config)
    monkeypatch.setattr(load, "environment", lambda _: ("unused-db", "unused-redis"))

    async def fail(*args):
        raise ExceptionGroup(
            "private SQL DSN password",
            [
                RuntimeError("postgresql://private"),
                ExceptionGroup("private nested", [ValueError("secret SQL")]),
                load.CampaignError("sampler_failed"),
            ],
        )

    monkeypatch.setattr(campaign, "provision", fail)
    report = await campaign.run()
    assert report["failure_stage"] == "provision"
    assert report["failure_code"] == "sampler_failed"
    assert report["exception_type"] == "ExceptionGroup"
    assert report["exception_types"] == [
        "ExceptionGroup",
        "RuntimeError",
        "ValueError",
        "CampaignError",
    ]
    serialized = json.dumps(report)
    for private in ["private", "password", "secret SQL", "postgresql://"]:
        assert private not in serialized


def test_exception_class_names_are_sanitized_and_bounded():
    unsafe = type("private-dsn://password", (Exception,), {})
    assert load.exception_types(unsafe("private")) == ["Exception"]
    errors = [type("FixtureError" + str(index), (Exception,), {})("private") for index in range(20)]
    assert len(load.exception_types(ExceptionGroup("private", errors))) == 16


async def test_external_cancellation_still_awaits_cleanup(config, monkeypatch):
    campaign = load.Campaign(config)
    ready, released = asyncio.Event(), asyncio.Event()
    monkeypatch.setattr(load, "environment", lambda _: ("unused-db", "unused-redis"))

    async def provision(*args):
        ready.set()
        await asyncio.Event().wait()

    async def release():
        await asyncio.sleep(0)
        released.set()

    monkeypatch.setattr(campaign, "provision", provision)
    monkeypatch.setattr(campaign, "release", release)
    task = asyncio.create_task(campaign.run())
    await ready.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert released.is_set() and campaign.failure_code == "campaign_cancelled"


async def test_sampler_failure_during_final_collection_is_not_discarded(config, monkeypatch):
    campaign = load.Campaign(config)
    collecting, cancelled = asyncio.Event(), asyncio.Event()

    async def completed():
        return

    async def collect():
        collecting.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def sampler(stop):
        await collecting.wait()  # producer/consumer already finished; final SQL is in progress
        raise load.CampaignError("sampler_failed")

    monkeypatch.setattr(campaign, "produce", completed)
    monkeypatch.setattr(campaign, "consume", completed)
    monkeypatch.setattr(campaign, "collect_final", collect)
    monkeypatch.setattr(campaign, "sample_loop", sampler)
    with pytest.raises(ExceptionGroup) as raised:
        await asyncio.wait_for(campaign.execute(), 1)
    assert load.exception_code(raised.value) == "sampler_failed"
    assert campaign.failure_stage == "sampler"
    assert campaign.exception_type == "CampaignError"
    assert cancelled.is_set() and campaign.callbacks.closed
    assert not campaign.callbacks.tasks


@pytest.mark.parametrize("timeout", [False, True])
async def test_cleanup_attempts_drop_after_dispose_failure_preserving_primary_error(
    config, monkeypatch, timeout
):
    campaign = load.Campaign(config)
    campaign.failure_code = "sampler_failed"
    calls = []

    async def dispose():
        calls.append("dispose")
        if timeout:
            await asyncio.Event().wait()
        raise RuntimeError("private-dispose-error")

    async def drop():
        calls.append("drop")
        campaign.cleanup["schema"] = "confirmed"

    campaign.engine = SimpleNamespace(dispose=dispose)
    monkeypatch.setattr(campaign, "drop_schema", drop)
    monkeypatch.setattr(load, "CLEANUP_STEP_SECONDS", 0.01)
    await asyncio.wait_for(campaign.release(), 1)
    assert calls == ["dispose", "drop"]
    assert campaign.cleanup["schema"] == "failed"
    assert campaign.failure_code == "sampler_failed"


@pytest.mark.redis
async def test_real_redis_namespace_reservation_race_and_foreign_stream_cleanup(config):
    url = os.getenv("VIGIL_TEST_REDIS_URL")
    if not url:
        pytest.skip("Set VIGIL_TEST_REDIS_URL for real namespace reservation proof")
    campaign = load.Campaign(config)
    redis = load.Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
    stream, owner = config.stream, config.stream + ":owner"
    campaign.owner_key = owner
    markers = ["test_" + uuid4().hex, "test_" + uuid4().hex]
    try:
        assert not await redis.exists(stream, owner)
        reservations = await asyncio.gather(
            *(load.reserve_namespace(redis, stream, owner, marker) for marker in markers)
        )
        assert sum(reservations) == 1
        winner = markers[reservations.index(True)]
        assert await redis.get(owner) == winner.encode()
        await redis.delete(owner)
        message_id = await redis.xadd(stream, {"fixture": "foreign"})
        assert not await load.reserve_namespace(redis, stream, owner, campaign.marker)
        assert not await redis.exists(owner)
        campaign.redis, campaign.redis_owned = redis, True
        with pytest.raises(load.CampaignError, match="redis_cleanup_guard"):
            await campaign.purge_redis()
        assert await redis.xrange(stream) == [(message_id, {b"fixture": b"foreign"})]
        assert campaign.cleanup["redis"] == "not_created"
    finally:
        # Exact UUID keys created by this test, never scan/flush or another campaign.
        await redis.delete(stream, owner)
        await redis.aclose()


@pytest.fixture
async def pg17_namespace(config):
    url = os.getenv("VIGIL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set VIGIL_TEST_DATABASE_URL for real PostgreSQL17 namespace guards")
    campaign = load.Campaign(config)
    admin = load.create_engine(url)
    owned = False
    try:
        async with admin.begin() as db:
            version = await db.scalar(load.text("SHOW server_version_num"))
            # Fail rather than skip when a supplied integration endpoint is not PG17.
            assert int(version) // 10000 == 17, "Namespace guard tests require PostgreSQL17"
            await db.execute(load.text(f'CREATE SCHEMA "{config.schema}"'))
            owned = True
            await db.execute(load.text(f'CREATE TABLE "{config.schema}".sentinel (id integer)'))
            await db.execute(load.text(f'INSERT INTO "{config.schema}".sentinel VALUES (17)'))
        campaign.admin, campaign.schema_owned = admin, True
        yield campaign, url
    finally:
        if owned:
            async with admin.begin() as db:
                # Only the UUID namespace created by this fixture, never a shared schema.
                await db.execute(load.text(f'DROP SCHEMA IF EXISTS "{config.schema}" CASCADE'))
        await admin.dispose()


@pytest.mark.postgres
async def test_real_pg17_existing_namespace_is_preserved_before_redis(config, pg17_namespace):
    owner, url = pg17_namespace
    challenger = load.Campaign(config)
    try:
        with pytest.raises(ProgrammingError) as raised:
            await challenger.provision(url, "unused-redis-must-not-be-connected")
        assert (
            raised.value.orig.sqlstate == "42P06"
        )  # duplicate_schema, not another provision error
        assert challenger.schema_owned is False
        assert challenger.redis is None
        assert challenger.stage == "schema_create"
        async with owner.admin.connect() as db:
            assert await db.scalar(load.text(f'SELECT id FROM "{config.schema}".sentinel')) == 17
    finally:
        await challenger.release()
    assert challenger.cleanup["schema"] == "not_created"


@pytest.mark.postgres
@pytest.mark.parametrize("marker", [None, "foreign_marker"])
async def test_real_pg17_cleanup_refuses_missing_or_changed_marker(config, pg17_namespace, marker):
    campaign, _ = pg17_namespace
    if marker is not None:
        async with campaign.admin.begin() as db:
            await db.execute(load.text(f"COMMENT ON SCHEMA \"{config.schema}\" IS '{marker}'"))
    with pytest.raises(load.CampaignError, match="schema_cleanup_guard"):
        await campaign.drop_schema()
    assert campaign.cleanup["schema"] == "not_created"
    async with campaign.admin.connect() as db:
        assert await db.scalar(load.text(f'SELECT id FROM "{config.schema}".sentinel')) == 17


@pytest.mark.postgres
async def test_real_pg17_cleanup_confirms_matching_owner_and_rolled_back_create(
    config, pg17_namespace
):
    campaign, _ = pg17_namespace
    async with campaign.admin.begin() as db:
        await db.execute(load.text(f"COMMENT ON SCHEMA \"{config.schema}\" IS '{campaign.marker}'"))
    await campaign.drop_schema()
    assert campaign.cleanup["schema"] == "confirmed"
    # Reproduce CREATE/COMMENT rollback instead of treating simple absence as rollback proof.
    async with campaign.admin.connect() as db:
        transaction = await db.begin()
        await db.execute(load.text(f'CREATE SCHEMA "{config.schema}"'))
        await db.execute(load.text(f"COMMENT ON SCHEMA \"{config.schema}\" IS '{campaign.marker}'"))
        await transaction.rollback()
    async with campaign.admin.connect() as db:
        assert not await db.scalar(
            load.text("SELECT 1 FROM pg_namespace WHERE nspname=:name"), {"name": config.schema}
        )
    campaign.cleanup["schema"] = "not_created"
    await campaign.drop_schema()
    assert campaign.cleanup["schema"] == "confirmed"


def test_report_separates_counts_slots_backlog_and_measurements(config):
    campaign = load.Campaign(replace(config, jobs=1))
    completed = record()
    completed.queue_delay_ms, completed.http_ms, completed.commit_call_ms = 17, 22, 3
    campaign.records[uuid4()] = completed
    campaign.results = campaign.successes = 1
    campaign.cleanup = {"schema": "confirmed", "redis": "confirmed"}
    campaign.backlog.update(final_lag=0, final_pel=0, final_pg_open=0)
    report = campaign.report()
    assert report["success"]
    assert all(value == 1 for key, value in report["counts"].items() if key != "errors")
    assert report["counts"]["errors"] == 0
    assert report["latencies_ms"]["queue_delay"]["p95"] == 17
    assert report["latencies_ms"]["schedule_transaction"]["p95"] == 50
    for name, expected in {
        "publication": 1000,
        "schedule_to_delivery": 1500,
        "delivery_to_claim_commit": 1500,
        "claim_to_executor_return": 1000,
        "result_commit_to_xack": 500,
        "xack_round_trip": 250,
        "ack_observation": 500,
        "schedule_commit_to_xack": 5500,
    }.items():
        assert report["latencies_ms"][name] == {
            "sample_count": 1,
            "p50": expected,
            "p95": expected,
            "p99": expected,
        }
        assert name in report["metric_scopes"]
    assert report["invariants"]["stage_order_verified"] is True
    assert report["invariants"]["measurement_samples_complete"] is True
    assert len(report["latencies_ms"]) == 13
    assert all(metric["sample_count"] == 1 for metric in report["latencies_ms"].values())
    assert report["concurrency"]["callback_limit"] == 50
    assert report["concurrency"]["host_limit"] == 5
    assert report["backlog"]["final_pel"] == report["backlog"]["final_lag"] == 0
    assert "httpx" in report["sources"] and "httpcore" in report["sources"]


@pytest.mark.parametrize(
    "change",
    [
        {"xack_confirmed": None},
        {"xack_confirmed": 5.5},
        {"xack_started": 5.5},
        {"visibility_verified": False},
        {"claim_commit": 5.5},
    ],
)
def test_report_cannot_succeed_with_incomplete_or_reversed_stages(config, change):
    campaign = load.Campaign(replace(config, jobs=1))
    campaign.records[uuid4()] = replace(record(), **change)
    campaign.results = campaign.successes = 1
    campaign.cleanup = {"schema": "confirmed", "redis": "confirmed"}
    campaign.backlog.update(final_lag=0, final_pel=0, final_pg_open=0)
    report = campaign.report()
    assert not report["success"]
    assert report["invariants"]["stage_order_verified"] is False
    json.dumps(report, allow_nan=False)  # Preserve useful partial diagnostics after failure.


@pytest.mark.parametrize(
    "missing",
    [
        "schedule_transaction_ms",
        "queue_delay_ms",
        "http_ms",
        "commit_call_ms",
        "finalize_after_executor_ms",
    ],
)
def test_report_requires_complete_measurements_in_addition_to_stage_order(config, missing):
    campaign = load.Campaign(replace(config, jobs=1))
    campaign.records[uuid4()] = replace(record(), **{missing: None})
    campaign.results = campaign.successes = 1
    campaign.cleanup = {"schema": "confirmed", "redis": "confirmed"}
    campaign.backlog.update(final_lag=0, final_pel=0, final_pg_open=0)
    report = campaign.report()
    assert report["invariants"]["stage_order_verified"] is True
    assert report["invariants"]["measurement_samples_complete"] is False
    assert not report["success"]


def test_cli_rejection_emits_one_json_without_private_arguments(config, monkeypatch, capsys):
    monkeypatch.setattr(load.logging, "disable", lambda _: None)
    monkeypatch.setattr(
        load.sys,
        "argv",
        ["helper", "--run-id", config.run_id, "--private-argument", "private-password"],
    )
    assert load.main() == 1
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1 and captured.err == ""
    assert json.loads(captured.out)["failure_code"] == "invalid_arguments"
    assert json.loads(captured.out)["failure_stage"] == "arguments"
    assert json.loads(captured.out)["exception_type"] == "CampaignError"
    assert "private-password" not in captured.out
