"""Controlled Linux QA campaign: real Receiver/PG17/Redis/verified TLS, never runtime startup.

Only /health on sockets.example.com -> the namespace's own 93.184.216.34 is used.
Stdout is one sanitized JSON report. Test instrumentation adds observation overhead;
this campaign does not establish an availability or latency SLA.
"""

import argparse
import asyncio
import contextvars
import importlib.metadata
import ipaddress
import json
import logging
import math
import os
import platform
import re
import socket
import ssl
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from redis.asyncio import Redis  # noqa: E402
from redis.asyncio.retry import Retry  # noqa: E402
from redis.backoff import NoBackoff  # noqa: E402
from sqlalchemy import event, func, select, text  # noqa: E402
from sqlalchemy.orm import Session as SyncSession  # noqa: E402
from taskiq.acks import AckableMessage  # noqa: E402
from taskiq.message import TaskiqMessage  # noqa: E402
from taskiq.receiver import Receiver  # noqa: E402

from app.config import Settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.models import CheckJob, CheckResult, Monitor, Project, User  # noqa: E402
from app.db.session import create_engine, create_session_factory  # noqa: E402
from app.monitoring.broker import create_broker  # noqa: E402
from app.monitoring.executor import CheckExecutor, ConcurrencyLimits  # noqa: E402
from app.monitoring.publisher import publish_pending  # noqa: E402
from app.monitoring.tasks import check_task  # noqa: E402
from app.monitoring.transport import PinnedNetworkBackend, SafeTransport  # noqa: E402
from app.services.check_jobs import schedule_due  # noqa: E402

HOST, ADDRESS = "sockets.example.com", "93.184.216.34"
CURRENT = contextvars.ContextVar("pipeline_load_record", default=None)
CLEANUP_STEP_SECONDS, CLEANUP_TOTAL_SECONDS = 5, 30


class CampaignError(Exception):
    """A fixed public error code; never report database/socket exceptions or inputs."""


def exception_code(error):
    if isinstance(error, CampaignError) and re.fullmatch(r"[a-z_]{1,64}", str(error)):
        return str(error)
    if isinstance(error, BaseExceptionGroup):
        for nested in error.exceptions:
            code = exception_code(nested)
            if code != "campaign_failed":
                return code
    if isinstance(error, TimeoutError):
        return "campaign_timeout"
    return "campaign_failed"


def exception_types(error):
    """Class names only, including bounded unique leaves of nested TaskGroups."""
    names = []

    def visit(item):
        name = type(item).__name__
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name):
            name = "Exception"
        if name not in names and len(names) < 16:
            names.append(name)
        if isinstance(item, BaseExceptionGroup):
            for nested in item.exceptions:
                visit(nested)

    visit(error)
    return names


@dataclass(frozen=True)
class Config:
    run_id: str
    jobs: int = 100
    duration_seconds: float = 60
    callback_limit: int = 50
    drain_timeout_seconds: float = 30
    ca_file: Path = Path("/fixtures/ca.pem")
    report_file: Path | None = None

    def __post_init__(self):
        try:
            normalized = UUID(self.run_id).hex
        except (ValueError, TypeError, AttributeError):
            raise CampaignError("invalid_run_id") from None
        object.__setattr__(self, "run_id", normalized)
        if (
            type(self.jobs) is not int
            or not 1 <= self.jobs <= 2000
            or type(self.callback_limit) is not int
            or not 1 <= self.callback_limit <= 50
        ):
            raise CampaignError("invalid_limits")
        if (
            not math.isfinite(self.duration_seconds)
            or not 0 <= self.duration_seconds <= 600
            or not math.isfinite(self.drain_timeout_seconds)
            or not 1 <= self.drain_timeout_seconds <= 120
        ):
            raise CampaignError("invalid_duration")
        if self.report_file is not None:
            resolved = self.report_file.resolve()
            if Path("/tmp") not in resolved.parents:
                raise CampaignError("invalid_report_path")

    @property
    def schema(self):
        return "vigil_test_" + self.run_id

    @property
    def stream(self):
        return "vigil:pipeline-load:" + self.run_id

    @property
    def group(self):
        return "group-" + self.run_id


def quantiles(values):
    ordered = sorted(values)
    if any(not math.isfinite(value) or value < 0 for value in ordered):
        raise CampaignError("invalid_measurement")

    def percentile(fraction):
        if not ordered:
            return None
        position = (len(ordered) - 1) * fraction
        low, high = math.floor(position), math.ceil(position)
        return ordered[low] + (ordered[high] - ordered[low]) * (position - low)

    return {
        "sample_count": len(ordered),
        **{name: percentile(value) for name, value in [("p50", 0.5), ("p95", 0.95), ("p99", 0.99)]},
    }


@dataclass
class Record:
    scheduled: float
    schedule_transaction_ms: float | None = None
    publication_started: float | None = None
    published: float | None = None
    delivered: float | None = None
    claim_commit: float | None = None
    http_finished: float | None = None
    result_commit: float | None = None
    acknowledged: float | None = None
    xack_started: float | None = None
    xack_confirmed: float | None = None
    redis_id: bytes | str | None = None
    phase: str = "claim"
    commit_call_ms: float | None = None
    finalize_after_executor_ms: float | None = None
    queue_delay_ms: float | None = None
    http_ms: float | None = None
    verified_result: bool = False
    visibility_verified: bool = False
    writer_pids: set = field(default_factory=set)

    def validate_order(self):
        sequence = [
            self.scheduled,
            self.publication_started,
            self.delivered,
            self.claim_commit,
            self.http_finished,
            self.result_commit,
            self.xack_started,
            self.xack_confirmed,
            self.acknowledged,
        ]
        if (
            any(value is None for value in sequence)
            or any(left > right for left, right in zip(sequence, sequence[1:]))
            or self.published is None
            or self.published < self.publication_started
            or not self.verified_result
            or not self.visibility_verified
        ):
            raise CampaignError("stage_order_violation")
        # XADD confirmation can arrive after consumer delivery; do not impose false ordering.


class CallbackPool:
    """Bounded owned callback tasks, with awaited cancellation and collected failures."""

    def __init__(self, limit):
        self.slots = asyncio.Semaphore(limit)
        self.tasks, self.errors = set(), []
        self.active = self.maximum = 0
        self.closed = False

    async def submit(self, operation):
        await self.slots.acquire()
        if self.closed:
            self.slots.release()
            raise CampaignError("callbacks_closed")

        async def invoke():
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            try:
                return await operation()
            finally:
                self.active -= 1

        task = asyncio.create_task(invoke())
        self.tasks.add(task)

        def done(completed):
            self.tasks.discard(completed)
            self.slots.release()  # includes cancellation before invoke's first instruction
            if not completed.cancelled() and completed.exception() is not None:
                self.errors.append(completed.exception())

        task.add_done_callback(done)

    async def close(self, *, cancel=False):
        self.closed = True
        if cancel:
            for task in tuple(self.tasks):
                task.cancel()
        await asyncio.gather(*tuple(self.tasks), return_exceptions=True)


class ObservedLimits(ConcurrencyLimits):
    """Unchanged product admission; counts execution slots, not 50 physical sockets."""

    def __init__(self):
        super().__init__()  # product defaults: global50, host5, acquire deadline1s
        self.active = self.maximum = 0

    @asynccontextmanager
    async def slot(self, host):
        async with super().slot(host):
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            try:
                yield
            finally:
                self.active -= 1


class CampaignSession(SyncSession):
    pass


@event.listens_for(CampaignSession, "before_commit")
def before_commit(session):
    record = CURRENT.get()
    if record is not None:
        record.writer_pids.add(session.connection().connection.driver_connection.get_server_pid())
        session.info["load_commit"] = (record, record.phase, time.monotonic())


@event.listens_for(CampaignSession, "after_commit")
def after_commit(session):
    observation = session.info.pop("load_commit", None)
    if observation is not None:
        record, phase, started = observation
        completed = time.monotonic()
        if phase == "claim":
            record.claim_commit = completed
        elif phase == "finalize":
            record.result_commit = completed
            record.commit_call_ms = (completed - started) * 1000
            record.finalize_after_executor_ms = (completed - record.http_finished) * 1000


async def resolver(host, port):
    if host != HOST or port != 443:
        raise CampaignError("unexpected_destination")
    return [ADDRESS]


class ObservedExecutor(CheckExecutor):
    """Delegates all execution to the real product executor/transport."""

    async def run(self, claimed):
        record = CURRENT.get()
        if record is None or record.claim_commit is None:
            raise CampaignError("claim_not_committed")
        record.phase = "http"
        result = await super().run(claimed)
        record.http_finished = time.monotonic()
        record.http_ms = result.cycle_duration_ms
        record.phase = "finalize"
        return result


def transport(ca_file):
    instance = SafeTransport(backend=PinnedNetworkBackend(resolver=resolver))
    instance.pool._ssl_context.load_verify_locations(cafile=str(ca_file))
    if (
        not instance.pool._ssl_context.check_hostname
        or instance.pool._ssl_context.verify_mode != ssl.CERT_REQUIRED
    ):
        raise CampaignError("tls_verification_disabled")
    return instance


def environment(config):
    if sys.platform != "linux" or os.environ.get("VIGIL_TEST_PIPELINE_LOAD_QA") != "1":
        raise CampaignError("qa_opt_in_required")
    settings = Settings(_env_file=None)
    if settings.pipeline_enabled or settings.monitoring_network_enabled:
        raise CampaignError("runtime_gates_must_be_false")
    if os.environ.get("VIGIL_EGRESS_QA_TOKEN") != config.run_id:
        raise CampaignError("qa_token_mismatch")
    if os.getuid() != 10001 or os.getgid() != 10001:
        raise CampaignError("qa_uid_required")
    status = Path("/proc/self/status").read_text()
    if any(
        int(line.split(":", 1)[1], 16) for line in status.splitlines() if line.startswith("Cap")
    ):
        raise CampaignError("qa_capabilities_required")
    if Path("/proc/sys/net/ipv4/ip_nonlocal_bind").read_text().strip() != "0":
        raise CampaignError("nonlocal_bind_forbidden")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((ADDRESS, 0))  # no traffic: listener address must belong to this namespace
    except OSError:
        raise CampaignError("fixture_address_not_local") from None
    if not config.ca_file.is_file():
        raise CampaignError("fixture_ca_missing")
    database_url = os.environ.get("VIGIL_TEST_DATABASE_URL", "")
    redis_url = os.environ.get("VIGIL_TEST_REDIS_URL", "")
    if not database_url.startswith("postgresql+asyncpg://") or not redis_url.startswith("redis://"):
        raise CampaignError("integration_urls_required")
    controls = [urlsplit(database_url), urlsplit(redis_url)]
    try:
        if (
            controls[0].username != "qa"
            or controls[0].path != "/qa"
            or (controls[0].port or 5432) != 5432
            or (controls[1].port or 6379) != 6379
            or controls[1].path != "/0"
        ):
            raise ValueError
        for target in controls:
            address = ipaddress.ip_address(target.hostname)
            if address.version != 4 or not any(
                address in ipaddress.ip_network(network)
                for network in ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
            ):
                raise ValueError
    except ValueError:
        raise CampaignError("qa_control_endpoints_required") from None
    return database_url, redis_url


async def reserve_namespace(redis, stream, owner_key, marker):
    # Reservation and collision check are one operation; no EXISTS/SET-NX race.
    return bool(
        await redis.eval(
            """
        if redis.call('EXISTS', KEYS[1], KEYS[2]) ~= 0 then return 0 end
        redis.call('SET', KEYS[2], ARGV[1])
        return 1
        """,
            2,
            stream,
            owner_key,
            marker,
        )
    )


def sources():
    result = {"python": platform.python_version(), "postgresql": None, "redis": None}
    for name in ["taskiq", "httpx", "httpcore"]:
        result[name] = importlib.metadata.version(name)
    return result


class Campaign:
    def __init__(self, config):
        self.config = config
        self.records = {}
        self.callbacks = CallbackPool(config.callback_limit)
        self.limits = ObservedLimits()
        self.sources = sources()
        self.backlog = {
            "max_lag": 0,
            "max_pel": 0,
            "max_pg_open": 0,
            "max_scheduled_not_acknowledged": 0,
            "final_lag": None,
            "final_pel": None,
            "final_pg_open": None,
            "samples": 0,
            "sampling_interval_ms": 50,
        }
        self.cleanup = {"schema": "not_created", "redis": "not_created"}
        self.failure_code = None
        self.failure_stage = None
        self.exception_type = None
        self.exception_types = []
        self.stage = "initialization"
        self.errors = self.results = 0
        self.successes = 0
        self.started, self.cpu_started = time.monotonic(), time.process_time()
        self.marker = "pipeline_load_" + uuid4().hex
        self.schema_owned = self.redis_owned = False
        self.admin = self.engine = self.verify_engine = self.redis = self.broker = None
        self.database = {
            "size_before_bytes": None,
            "size_after_bytes": None,
            "schema_before_bytes": None,
            "schema_after_bytes": None,
            "row_counts": {"monitors": 0, "jobs": 0, "results": 0},
            "measurement_before_cleanup": True,
        }

    def report(self):
        records = list(self.records.values())
        ordered = bool(records)
        for record in records:
            try:
                record.validate_order()
            except CampaignError:
                ordered = False

        def elapsed(start, end):
            return quantiles(
                [
                    (getattr(record, end) - getattr(record, start)) * 1000
                    for record in records
                    if getattr(record, start) is not None
                    and getattr(record, end) is not None
                    and getattr(record, end) >= getattr(record, start)
                ]
            )

        counts = {
            "programmed": self.config.jobs,
            "scheduled": len(records),
            "published": sum(r.published is not None for r in records),
            "claimed": sum(r.claim_commit is not None for r in records),
            "committed": sum(r.verified_result for r in records),
            "acknowledged": sum(r.acknowledged is not None for r in records),
            "xack_confirmed": sum(r.xack_confirmed is not None for r in records),
            "results": self.results,
            "errors": self.errors + int(self.failure_code is not None),
        }
        success = (
            self.failure_code is None
            and not self.callbacks.errors
            and all(
                counts[name] == self.config.jobs
                for name in [
                    "scheduled",
                    "published",
                    "claimed",
                    "committed",
                    "acknowledged",
                    "xack_confirmed",
                    "results",
                ]
            )
            and self.successes == self.config.jobs
            and counts["errors"] == 0
            and self.cleanup == {"schema": "confirmed", "redis": "confirmed"}
            and self.backlog["final_lag"] == self.backlog["final_pel"] == 0
            and self.backlog["final_pg_open"] == 0
            and all(r.visibility_verified for r in records)
            and ordered
        )
        wall = time.monotonic() - self.started
        peak_rss = None
        if sys.platform == "linux":
            import resource

            peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        report = {
            "protocol_version": 1,
            "success": success,
            "run_id": self.config.run_id,
            "counts": counts,
            "cleanup": self.cleanup,
            "sources": self.sources,
            "latencies_ms": {
                "schedule_transaction": quantiles(
                    [
                        r.schedule_transaction_ms
                        for r in records
                        if r.schedule_transaction_ms is not None
                    ]
                ),
                "publication": elapsed("publication_started", "published"),
                "schedule_to_delivery": elapsed("scheduled", "delivered"),
                "delivery_to_claim_commit": elapsed("delivered", "claim_commit"),
                "claim_to_executor_return": elapsed("claim_commit", "http_finished"),
                "result_commit_to_xack": elapsed("result_commit", "xack_confirmed"),
                "xack_round_trip": elapsed("xack_started", "xack_confirmed"),
                "ack_observation": elapsed("xack_confirmed", "acknowledged"),
                "schedule_commit_to_xack": elapsed("scheduled", "xack_confirmed"),
                "queue_delay": quantiles(
                    [r.queue_delay_ms for r in records if r.queue_delay_ms is not None]
                ),
                "http": quantiles([r.http_ms for r in records if r.http_ms is not None]),
                "commit": quantiles(
                    [r.commit_call_ms for r in records if r.commit_call_ms is not None]
                ),
                "finalize_after_executor": quantiles(
                    [
                        r.finalize_after_executor_ms
                        for r in records
                        if r.finalize_after_executor_ms is not None
                    ]
                ),
            },
            "metric_scopes": {
                "schedule_transaction": "schedule_due transaction through commit; batch time repeated per job",
                "publication": "broker kick through XADD confirmation; delivery may precede confirmation",
                "schedule_to_delivery": "schedule commit through broker delivery, includes publication",
                "delivery_to_claim_commit": "broker delivery through claim commit, includes callback admission",
                "claim_to_executor_return": "claim commit through executor return, includes HTTP admission",
                "result_commit_to_xack": "result commit through XACK reply, includes signal/visibility checks",
                "xack_round_trip": "product message ACK call through Redis XACK confirmation",
                "ack_observation": "XACK reply through post-ACK PEL read and verification",
                "schedule_commit_to_xack": "schedule commit through XACK reply, excludes schedule transaction",
                "queue_delay": "persisted due-to-cycle-start, includes admission",
                "http": "cycle_duration_ms, includes closure, excludes admission",
                "commit": "commit_call_ms, before_commit through after_commit; residual flush only",
                "finalize_after_executor": "executor return through result commit, including locks/SQL",
            },
            "invariants": {
                "stage_order_verified": ordered,
                "commit_visibility_separate_connection": bool(records)
                and all(r.visibility_verified for r in records),
            },
            "concurrency": {
                "callback_limit": self.config.callback_limit,
                "max_callbacks": self.callbacks.maximum,
                "max_http": self.limits.maximum,
                "host_limit": 5,
                "global_executor_limit": 50,
            },
            "backlog": self.backlog,
            "database": self.database,
            "resources": {
                "wall_seconds": wall,
                "cpu_seconds": time.process_time() - self.cpu_started,
                "peak_rss_bytes": peak_rss,
                "scope": "helper_process_only",
            },
            "campaign": {
                "jobs": self.config.jobs,
                "duration_seconds": self.config.duration_seconds,
                "requested_jobs_per_minute": (
                    self.config.jobs * 60 / self.config.duration_seconds
                    if self.config.duration_seconds
                    else None
                ),
            },
            "failure_code": self.failure_code,
            "failure_stage": self.failure_stage,
            "exception_type": self.exception_type,
            "exception_types": self.exception_types,
            "limitations": [
                "local QA, no SLA",
                "per-ACK reads and sampling add observation overhead",
                "max_http counts executor slots; callback50 does not imply50 concurrent HTTP",
                "PG/Redis backlog maxima are sampled; in-flight counters are exact",
                "commit_call excludes earlier explicit flush/locks; do not sum phase percentiles",
                "wall includes provision/seed/drain/cleanup; configured rate is not observed throughput",
                "sampling interval is delay after reads; PG/Redis snapshots are not jointly atomic",
                "schema uses metadata, not migrations; database bytes include all schemas/catalogs",
                "schema relation bytes include indexes/TOAST, not payload/WAL; one project serializes DB locks",
                "ownership is for exclusive disposable QA services whose participants honor markers",
            ],
        }
        measurements_complete = all(
            metric["sample_count"] == self.config.jobs for metric in report["latencies_ms"].values()
        )
        report["invariants"]["measurement_samples_complete"] = measurements_complete
        report["success"] = success and measurements_complete
        return report

    def note_failure(self, error, stage):
        if self.failure_stage is None:
            self.failure_stage = stage  # call sites supply fixed stage names only
            self.exception_types = exception_types(error)
            self.exception_type = self.exception_types[0]
        elif isinstance(error, BaseExceptionGroup):
            self.exception_types = list(
                dict.fromkeys(self.exception_types + exception_types(error))
            )[:16]

    async def observed(self, stage, operation):
        try:
            return await operation()
        except Exception as error:
            self.note_failure(error, stage)
            raise

    async def provision(self, database_url, redis_url):
        self.stage = "postgres_connect"
        self.admin = create_engine(
            database_url,
            connect_args={
                "server_settings": {"statement_timeout": "10000", "lock_timeout": "2000"}
            },
        )
        async with self.admin.begin() as db:
            version = await db.scalar(text("SHOW server_version_num"))
            if int(version) // 10000 != 17:
                raise CampaignError("postgresql17_required")
            self.sources["postgresql"] = (await db.scalar(text("SHOW server_version"))).split()[0]
            self.database["size_before_bytes"] = await db.scalar(
                text("SELECT pg_database_size(current_database())")
            )
            self.stage = "schema_create"
            await db.execute(text(f'CREATE SCHEMA "{self.config.schema}"'))
            await db.execute(text(f"COMMENT ON SCHEMA \"{self.config.schema}\" IS '{self.marker}'"))
            self.schema_owned = True  # cleanup also handles rolled-back/uncertain DDL commit
        self.engine = create_engine(
            database_url,
            connect_args={
                "server_settings": {
                    "search_path": self.config.schema,
                    "timezone": "UTC",
                    "statement_timeout": "10000",
                    "lock_timeout": "2000",
                }
            },
        )
        self.stage = "schema_models"
        async with self.engine.begin() as db:
            if await db.scalar(text("SELECT current_schema()")) != self.config.schema:
                raise CampaignError("schema_search_path_mismatch")
            await db.run_sync(Base.metadata.create_all)
        self.factory = create_session_factory(self.engine)
        self.factory.configure(sync_session_class=CampaignSession)
        self.verify_engine = create_engine(
            database_url,
            pool_size=1,
            max_overflow=0,
            connect_args={
                "server_settings": {
                    "search_path": self.config.schema,
                    "timezone": "UTC",
                    "statement_timeout": "10000",
                    "lock_timeout": "2000",
                }
            },
        )
        self.verify_factory = create_session_factory(self.verify_engine)
        self.stage = "schema_measure"
        self.database["schema_before_bytes"] = await self.schema_bytes()
        self.stage = "redis_connect"
        self.redis = Redis.from_url(
            redis_url, socket_connect_timeout=2, socket_timeout=3, retry=Retry(NoBackoff(), 0)
        )
        self.sources["redis"] = (await self.redis.info("server"))["redis_version"]
        self.owner_key = self.config.stream + ":owner"
        self.stage = "redis_reserve"
        if not await reserve_namespace(self.redis, self.config.stream, self.owner_key, self.marker):
            raise CampaignError("redis_namespace_exists")
        self.redis_owned = True
        self.broker = create_broker(
            Settings(redis_url=redis_url, _env_file=None),
            queue_name=self.config.stream,
            group_name=self.config.group,
        )
        self.broker.register_task(
            check_task.original_func, task_name="vigil.check", ack_type="manual"
        )
        self.broker.state.factory = self.factory
        self.broker.state.redis = self.redis
        self.broker.state.executor = ObservedExecutor(
            transport_factory=lambda: transport(self.config.ca_file), limits=self.limits
        )
        original_message = self.broker._message

        def observed_message(identifier, data):
            identifier_job = UUID(self.broker.formatter.loads(data).args[0])
            record = self.records.get(identifier_job)
            if record is None or record.delivered is not None:
                raise CampaignError("unexpected_delivery")
            record.redis_id, record.delivered = identifier, time.monotonic()
            return original_message(identifier, data)  # real AckableMessage and XACK

        self.broker._message = observed_message
        self.stage = "broker_startup"
        await self.broker.startup()
        self.receiver = Receiver(self.broker, max_async_tasks=self.config.callback_limit)

    async def seed(self):
        async with self.factory.begin() as db:
            origin = await db.scalar(select(func.clock_timestamp()))
            self.origin_mono = time.monotonic() + 0.5
            origin += timedelta(seconds=0.5)
            user = User(
                email="load-" + self.config.run_id + "@qa.invalid", password_hash="qa-not-login"
            )
            db.add(user)
            await db.flush()
            project = Project(
                owner_id=user.id, name="QA load", public_slug="load-" + self.config.run_id
            )
            db.add(project)
            await db.flush()
            for index in range(self.config.jobs):
                db.add(
                    Monitor(
                        project_id=project.id,
                        name="QA",
                        url=f"https://{HOST}/health",
                        interval_seconds=3600,
                        timeout_ms=3000,
                        retry_count=0,
                        next_check_at=origin
                        + timedelta(
                            seconds=(index * self.config.duration_seconds / self.config.jobs)
                        ),
                    )
                )

    async def produce(self):
        while len(self.records) < self.config.jobs:
            due = (
                self.origin_mono
                + len(self.records) * self.config.duration_seconds / self.config.jobs
            )
            await asyncio.sleep(max(0, due - time.monotonic()))
            schedule_started = time.monotonic()
            async with self.factory.begin() as db:
                identifiers = await schedule_due(db)
            committed_at = time.monotonic()
            for identifier in identifiers:
                if identifier in self.records:
                    raise CampaignError("duplicate_schedule")
                self.records[identifier] = Record(
                    scheduled=committed_at,
                    schedule_transaction_ms=(committed_at - schedule_started) * 1000,
                )
            self.backlog["max_scheduled_not_acknowledged"] = max(
                self.backlog["max_scheduled_not_acknowledged"],
                sum(r.acknowledged is None for r in self.records.values()),
            )

            async def publish(job_id):
                record = self.records[UUID(job_id)]
                if record.publication_started is not None:
                    raise CampaignError("duplicate_publish")
                record.publication_started = time.monotonic()
                message = TaskiqMessage(
                    task_id=str(uuid4()),
                    task_name="vigil.check",
                    args=[job_id],
                    kwargs={"envelope_version": 1},
                    labels={"ack_type": "manual"},
                )
                await self.broker.kick(self.broker.formatter.dumps(message))
                record.published = time.monotonic()

            await publish_pending(self.factory, publish)
            if not identifiers:
                await asyncio.sleep(0.005)  # tolerate clock/request alignment without future jobs

    async def callback(self, message):
        identifier = UUID(self.broker.formatter.loads(message.data).args[0])
        record = self.records[identifier]
        token = CURRENT.set(record)
        try:

            async def ack():
                if record.result_commit is None:
                    raise CampaignError("ack_before_commit")
                async with self.verify_factory() as db:
                    pid = await db.scalar(select(func.pg_backend_pid()))
                    if not record.writer_pids or pid in record.writer_pids:
                        raise CampaignError("commit_verifier_connection_not_distinct")
                    job = await db.get(CheckJob, identifier)
                    result = await db.scalar(
                        select(CheckResult).where(CheckResult.job_id == identifier)
                    )
                    if job is None or job.status != "completed" or result is None:
                        raise CampaignError("result_not_committed")
                    record.queue_delay_ms = result.queue_delay_ms
                    record.verified_result = True
                    record.visibility_verified = True
                pending = await self.redis.xpending_range(
                    self.config.stream, self.config.group, record.redis_id, record.redis_id, 1
                )
                if len(pending) != 1:
                    raise CampaignError("delivery_not_pending")
                record.xack_started = time.monotonic()
                await message.ack()
                record.xack_confirmed = time.monotonic()
                if await self.redis.xpending_range(
                    self.config.stream, self.config.group, record.redis_id, record.redis_id, 1
                ):
                    raise CampaignError("ack_not_applied")
                record.acknowledged = time.monotonic()
                record.validate_order()

            await self.receiver.callback(AckableMessage(data=message.data, ack=ack), raise_err=True)
            if record.acknowledged is None:
                raise CampaignError("callback_not_acknowledged")
        except Exception as error:
            self.note_failure(error, "callback")
            raise
        finally:
            CURRENT.reset(token)

    async def consume(self):
        listener = self.broker.listen()
        try:
            for _ in range(self.config.jobs):
                message = await anext(listener)
                await self.callbacks.submit(lambda delivered=message: self.callback(delivered))
        finally:
            await listener.aclose()

    async def sample(self):
        groups = await self.redis.xinfo_groups(self.config.stream)
        group = next(item for item in groups if item["name"] == self.config.group.encode())
        lag, pending = group.get("lag"), group["pending"]
        if lag is None:
            raise CampaignError("redis_lag_unknown")
        async with self.factory() as db:
            opened = await db.scalar(
                select(func.count())
                .select_from(CheckJob)
                .where(CheckJob.status.in_(["pending", "running"]))
            )
        self.backlog.update(final_lag=lag, final_pel=pending)
        self.backlog["final_pg_open"] = opened
        self.backlog["max_lag"] = max(self.backlog["max_lag"], lag)
        self.backlog["max_pel"] = max(self.backlog["max_pel"], pending)
        self.backlog["max_pg_open"] = max(self.backlog["max_pg_open"], opened)
        self.backlog["samples"] += 1

    async def sample_loop(self, stop):
        while not stop.is_set():
            await self.sample()
            try:
                await asyncio.wait_for(stop.wait(), 0.05)
            except TimeoutError:
                pass

    async def execute(self):
        stop = asyncio.Event()
        try:
            async with asyncio.timeout(
                self.config.duration_seconds + self.config.drain_timeout_seconds + 5
            ):
                async with asyncio.TaskGroup() as group:
                    producer = group.create_task(self.observed("producer", self.produce))
                    consumer = group.create_task(self.observed("consumer", self.consume))
                    group.create_task(self.observed("sampler", lambda: self.sample_loop(stop)))
                    await asyncio.gather(producer, consumer)
                    await self.callbacks.close()
                    if self.callbacks.errors:
                        raise CampaignError("callback_failed")
                    await self.observed("collect_final", self.collect_final)
                    await self.observed("sample_final", self.sample)
                    stop.set()
        finally:
            await self.callbacks.close(cancel=True)

    async def collect_final(self):
        async with self.factory() as db:
            self.results = await db.scalar(select(func.count()).select_from(CheckResult))
            self.successes = await db.scalar(
                select(func.count())
                .select_from(CheckResult)
                .where(CheckResult.outcome == "success", CheckResult.http_status == 200)
            )
            self.database["size_after_bytes"] = await db.scalar(
                text("SELECT pg_database_size(current_database())")
            )
            for label, model in [
                ("monitors", Monitor),
                ("jobs", CheckJob),
                ("results", CheckResult),
            ]:
                self.database["row_counts"][label] = await db.scalar(
                    select(func.count()).select_from(model)
                )
        self.database["schema_after_bytes"] = await self.schema_bytes()
        self.errors = self.results - self.successes
        if self.results != self.config.jobs or self.successes != self.config.jobs:
            raise CampaignError("non_success_results")

    async def schema_bytes(self):
        async with self.engine.connect() as db:
            return int(
                await db.scalar(
                    text(
                        "SELECT COALESCE(sum(pg_total_relation_size(c.oid)),0) "
                        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE n.nspname=:name AND c.relkind='r'"
                    ),
                    {"name": self.config.schema},
                )
            )

    async def purge_redis(self):
        if self.redis_owned:
            script = """
                if redis.call('GET', KEYS[2]) ~= ARGV[1] then return 0 end
                local kind = redis.call('TYPE', KEYS[1]).ok
                if kind ~= 'stream' and kind ~= 'none' then return 0 end
                if kind == 'stream' then
                    for _, group in ipairs(redis.call('XINFO', 'GROUPS', KEYS[1])) do
                        if group[2] ~= ARGV[2] then return 0 end
                    end
                end
                redis.call('DEL', KEYS[1], KEYS[2])
                return 1
                """
            removed = await self.redis.eval(
                script, 2, self.config.stream, self.owner_key, self.marker, self.config.group
            )
            if removed != 1 or await self.redis.exists(self.config.stream, self.owner_key):
                raise CampaignError("redis_cleanup_guard")
            self.cleanup["redis"] = "confirmed"

    async def drop_schema(self):
        if self.schema_owned:
            async with self.admin.begin() as db:
                namespace = (
                    await db.execute(
                        text(
                            "SELECT obj_description(oid, 'pg_namespace') FROM pg_namespace WHERE nspname=:name"
                        ),
                        {"name": self.config.schema},
                    )
                ).one_or_none()
                if namespace is not None:
                    if namespace[0] != self.marker:
                        raise CampaignError("schema_cleanup_guard")
                    await db.execute(text(f'DROP SCHEMA "{self.config.schema}" CASCADE'))
            async with self.admin.connect() as db:
                if await db.scalar(
                    text("SELECT 1 FROM pg_namespace WHERE nspname=:name"),
                    {"name": self.config.schema},
                ):
                    raise CampaignError("schema_cleanup_not_confirmed")
            self.cleanup["schema"] = "confirmed"

    async def release(self):
        failures = set()

        async def step(resource, operation):
            try:
                async with asyncio.timeout(CLEANUP_STEP_SECONDS):
                    await operation()
            except Exception as error:
                failures.add(resource)
                if self.failure_code is None:
                    self.note_failure(error, "cleanup_" + resource)

        try:
            async with asyncio.timeout(CLEANUP_TOTAL_SECONDS):
                await step("schema", lambda: self.callbacks.close(cancel=True))
                if self.broker is not None:
                    await step("redis", self.broker.shutdown)
                await step("redis", self.purge_redis)
                if self.redis is not None:
                    await step("redis", self.redis.aclose)
                # Disposal failures cannot skip the separately guarded DROP attempt.
                if self.engine is not None:
                    await step("schema", self.engine.dispose)
                if self.verify_engine is not None:
                    await step("schema", self.verify_engine.dispose)
                await step("schema", self.drop_schema)
                if self.admin is not None:
                    await step("schema", self.admin.dispose)
        except TimeoutError as error:
            failures.update(["schema", "redis"])
            if self.failure_code is None:
                self.note_failure(error, "cleanup_deadline")
        finally:
            for resource in failures:
                self.cleanup[resource] = "failed"
            if failures and self.failure_code is None:
                self.failure_code = "cleanup_failed"

    async def run(self):
        try:
            self.stage = "environment"
            urls = environment(self.config)
            self.stage = "provision"
            await self.provision(*urls)
            self.stage = "seed"
            await self.seed()
            self.stage = "execute"
            await self.execute()
        except asyncio.CancelledError as error:
            self.failure_code = "campaign_cancelled"
            self.note_failure(error, self.stage)
            raise
        except Exception as error:
            self.failure_code = exception_code(error)
            self.note_failure(error, self.stage)
        finally:
            await self.release()
        return self.report()


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CampaignError("invalid_arguments")


def main():
    logging.disable(logging.CRITICAL)  # QA child only; no private Receiver/SQL exceptions to stderr
    parser = Parser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--jobs", type=int, default=100)
    parser.add_argument("--duration-seconds", type=float, default=60)
    parser.add_argument("--callback-limit", type=int, default=50)
    parser.add_argument("--drain-timeout-seconds", type=float, default=30)
    parser.add_argument("--ca-file", type=Path, default=Path("/fixtures/ca.pem"))
    parser.add_argument("--report-file", type=Path)
    stage = "arguments"
    try:
        config = Config(**vars(parser.parse_args()))
        stage = "campaign"
        report = asyncio.run(Campaign(config).run())
        if config.report_file is not None:
            try:
                config.report_file.write_text(json.dumps(report, allow_nan=False) + "\n")
            except OSError as error:
                report["success"] = False
                report["failure_code"] = "report_write_failed"
                report["failure_stage"] = "report_write"
                report["exception_types"] = exception_types(error)
                report["exception_type"] = report["exception_types"][0]
                report["counts"]["errors"] += 1
    except (CampaignError, KeyboardInterrupt) as error:
        report = {
            "protocol_version": 1,
            "success": False,
            "failure_code": (
                exception_code(error) if isinstance(error, CampaignError) else "campaign_cancelled"
            ),
            "failure_stage": stage,
            "exception_type": exception_types(error)[0],
            "exception_types": exception_types(error),
        }
    except Exception as error:
        report = {
            "protocol_version": 1,
            "success": False,
            "failure_code": "helper_failed",
            "failure_stage": stage,
            "exception_type": exception_types(error)[0],
            "exception_types": exception_types(error),
        }
    print(json.dumps(report, allow_nan=False), flush=True)
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
