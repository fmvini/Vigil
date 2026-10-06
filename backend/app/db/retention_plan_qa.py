"""Opt-in, disposable PG17 retention plan experiment; never reads runtime Settings.

Candidate indexes belong only to the marked QA schema. EXPLAIN never uses ANALYZE;
estimated costs and access paths are not measurements of latency or FK triggers.
"""

import argparse
import asyncio
import ipaddress
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import event, insert, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import NullPool

from app.db.models import CheckJob, CheckResult, Incident, Monitor, Project, User
from app.db.session import create_engine
from app.services.retention import retain_batch

NOW = datetime(2026, 10, 5, 12, tzinfo=UTC)
ROWS = 10_000
BASE_REVISION = "0001_initial"
CANDIDATES = {
    "ix_incidents_opening_check_id": "opening_check_id",
    "ix_incidents_closing_check_id": "closing_check_id",
}
PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(cidr) for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


@dataclass(frozen=True)
class Lease:
    token: str
    url: str
    host: str


def lease_config(opt_in, token, host, environ):
    """Only explicit QA inputs are accepted; no runtime/test URL fallback."""
    if opt_in is not True or environ.get("VIGIL_RETENTION_PLAN_QA") != "1":
        raise ValueError("Explicit --qa-opt-in is required")
    try:
        normalized = UUID(token).hex
        owner = UUID(environ.get("VIGIL_RETENTION_QA_TOKEN", "")).hex
        address = ipaddress.ip_address(host)
        url = make_url(environ.get("VIGIL_RETENTION_QA_DATABASE_URL", ""))
    except (ValueError, TypeError, ArgumentError):
        raise ValueError("Invalid explicit QA lease inputs") from None
    if normalized != owner or not any(address in network for network in PRIVATE_NETWORKS):
        raise ValueError("QA token/private lease endpoint mismatch")
    if (
        url.drivername != "postgresql+asyncpg"
        or url.host != host
        or url.port != 5432
        or url.username != "qa"
        or not url.password
        or url.database != "qa"
        or url.query
        or any(
            environ.get(key) != "false"
            for key in ("VIGIL_PIPELINE_ENABLED", "VIGIL_MONITORING_NETWORK_ENABLED")
        )
    ):
        raise ValueError("Explicit private QA URL and disabled gates are required")
    return Lease(normalized, url.render_as_string(hide_password=False), host)


def fixture_id(kind, ordinal):
    return UUID(int=(kind << 96) | ordinal)


def migrate(connection, revision):
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[2] / "migrations")
    )
    config.set_main_option(
        "sqlalchemy.url", "postgresql+asyncpg://offline:unused@localhost/offline"
    )
    config.attributes["connection"] = connection
    command.upgrade(config, revision)


async def verify_server(connection):
    row = (
        await connection.execute(
            text(
                "SELECT current_database(), current_user, current_setting('server_version_num')::int"
            )
        )
    ).one()
    if row[0] != "qa" or row[1] != "qa" or not 170000 <= row[2] < 180000:
        raise ValueError("Lease must be the exclusive qa database/user on PG17")
    return row[2]


async def seed_fixture(connection):
    await connection.execute(
        insert(User),
        [
            {
                "id": fixture_id(1, 1),
                "email": "retention-plan@example.test",
                "password_hash": "fixture",
            }
        ],
    )
    await connection.execute(
        insert(Project),
        [
            {
                "id": fixture_id(2, 1),
                "owner_id": fixture_id(1, 1),
                "name": "Retention QA",
                "public_slug": "retention-qa",
            }
        ],
    )
    await connection.execute(
        insert(Monitor),
        [
            {
                "id": fixture_id(3, i + 1),
                "project_id": fixture_id(2, 1),
                "name": f"Fixture {i}",
                "url": "https://fixture.invalid/",
            }
            for i in range(100)
        ],
    )
    for begin in range(0, ROWS, 500):
        jobs, results, incidents = [], [], []
        for i in range(begin, begin + 500):
            ordinal = i + 1
            monitor = fixture_id(3, i // 100 + 1)
            scheduled = NOW - timedelta(days=31) + timedelta(seconds=i)
            result = fixture_id(5, ordinal)
            jobs.append(
                {
                    "id": fixture_id(4, ordinal),
                    "monitor_id": monitor,
                    "config_version": 1,
                    "config_snapshot": {},
                    "scheduled_at": scheduled,
                    "expires_at": scheduled + timedelta(seconds=60),
                    "budget_ms": 5000,
                    "status": "completed",
                    "finished_at": scheduled + timedelta(seconds=2),
                }
            )
            results.append(
                {
                    "id": result,
                    "job_id": fixture_id(4, ordinal),
                    "monitor_id": monitor,
                    "config_version": 1,
                    "scheduled_at": scheduled,
                    "started_at": scheduled + timedelta(seconds=1),
                    "completed_at": scheduled + timedelta(seconds=2),
                    "outcome": "failure",
                    "cycle_duration_ms": 1000,
                    "queue_delay_ms": 0,
                    "attempt_count": 1,
                    "attempts": [{"error_code": "timeout"}],
                    "error_code": "timeout",
                    "health_after": "offline",
                }
            )
            # Active incidents have opening evidence only, as in finalize_job.
            open_incident = i % 100 == 96
            incidents.append(
                {
                    "id": fixture_id(6, ordinal),
                    "monitor_id": monitor,
                    "started_at": scheduled,
                    "detected_at": scheduled,
                    "ended_at": None if open_incident else NOW - timedelta(days=1),
                    "end_reason": None if open_incident else "recovered",
                    "opening_check_id": result if i % 4 in (0, 2) else None,
                    "closing_check_id": result if i % 4 in (1, 2) else None,
                    "cause_code": "timeout",
                    "failure_threshold_snapshot": 3,
                }
            )
        await connection.execute(insert(CheckJob), jobs)
        await connection.execute(insert(CheckResult), results)
        await connection.execute(insert(Incident), incidents)


async def fingerprint(connection):
    snapshots = {}
    for table in ("users", "projects", "monitors", "check_jobs", "check_results", "incidents"):
        row = (
            await connection.execute(
                text(
                    f"SELECT count(*), md5(string_agg(row_to_json(t)::text, '' ORDER BY id)) FROM {table} t"
                )
            )
        ).one()
        snapshots[table] = {"count": row[0], "digest": row[1]}
    return snapshots


async def fixture_distribution(connection):
    row = (
        (
            await connection.execute(
                text(
                    "SELECT count(*) FILTER (WHERE opening_check_id IS NOT NULL AND closing_check_id IS NULL) AS opening_only, "
                    "count(*) FILTER (WHERE opening_check_id IS NULL AND closing_check_id IS NOT NULL) AS closing_only, "
                    "count(*) FILTER (WHERE opening_check_id=closing_check_id) AS both_same_result, "
                    "count(*) FILTER (WHERE opening_check_id IS NULL AND closing_check_id IS NULL) AS no_evidence, "
                    "count(*) FILTER (WHERE ended_at IS NULL) AS open_incidents, "
                    "count(*) FILTER (WHERE ended_at IS NULL AND closing_check_id IS NOT NULL) AS open_with_closing_evidence "
                    "FROM incidents"
                )
            )
        )
        .mappings()
        .one()
    )
    if row["open_with_closing_evidence"]:
        raise ValueError("Invalid QA fixture: open incident has closing evidence")
    return dict(row)


async def incident_catalog(connection, schema):
    constraints = (
        (
            await connection.execute(
                text(
                    "SELECT conname, pg_get_constraintdef(oid) AS definition FROM pg_constraint "
                    "WHERE conrelid=CAST(:table AS regclass) ORDER BY conname"
                ),
                {"table": f"{schema}.incidents"},
            )
        )
        .mappings()
        .all()
    )
    indexes = (
        (
            await connection.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE schemaname=:schema AND tablename='incidents' ORDER BY indexname"
                ),
                {"schema": schema},
            )
        )
        .mappings()
        .all()
    )
    stats = (
        (
            await connection.execute(
                text("SELECT reltuples, relpages FROM pg_class WHERE oid=CAST(:table AS regclass)"),
                {"table": f"{schema}.incidents"},
            )
        )
        .mappings()
        .one()
    )
    return {
        "constraints": [dict(row) for row in constraints],
        "indexes": [dict(row) for row in indexes],
        "table_stats": dict(stats),
    }


def capture_listener(captured):
    def observe(connection, cursor, statement, parameters, context, executemany):
        if executemany or not statement.lstrip().upper().startswith(("SELECT ", "DELETE ")):
            raise ValueError("Unexpected retention statement in QA capture")
        captured.append((statement, tuple(parameters)))

    return observe


async def capture_retention(engine, batch_size):
    captured = []
    observe = capture_listener(captured)
    async with AsyncSession(engine, expire_on_commit=False) as db:
        await db.begin()
        event.listen(engine.sync_engine, "before_cursor_execute", observe)
        try:
            counts = await retain_batch(db, now=NOW, batch_size=batch_size)
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", observe)
            await db.rollback()
    return captured, asdict(counts)


def plan_nodes(plan):
    node = plan[0]["Plan"]
    return [node] + [
        child for subplan in node.get("Plans", []) for child in plan_nodes([{"Plan": subplan}])
    ]


async def explain(connection, statement, parameters):
    # Driver SQL is the captured parameterized SQL, never interpolated literals.
    value = await connection.exec_driver_sql("EXPLAIN (FORMAT JSON) " + statement, parameters)
    plan = value.scalar_one()
    plan = json.loads(plan) if isinstance(plan, str) else plan
    nodes = plan_nodes(plan)
    return {
        "sql": statement,
        "parameters": parameters,
        "plan": plan,
        "estimated_total_cost": plan[0]["Plan"]["Total Cost"],
        "incident_access": [
            {
                k: node[k]
                for k in ("Node Type", "Relation Name", "Index Name", "Plan Rows", "Total Cost")
                if k in node
            }
            for node in nodes
            if node.get("Relation Name") == "incidents" or node.get("Index Name") in CANDIDATES
        ],
    }


async def drop_owned(admin, schema, marker, report):
    async with admin.begin() as connection:
        await verify_server(connection)
        actual = await connection.scalar(
            text(
                "SELECT obj_description(oid, 'pg_namespace') FROM pg_namespace WHERE nspname=:schema"
            ),
            {"schema": schema},
        )
        exists = await connection.scalar(
            text("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname=:schema)"),
            {"schema": schema},
        )
        if exists and actual != marker:
            raise ValueError("Refusing QA schema cleanup: ownership marker mismatch")
        if exists:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    async with admin.connect() as connection:
        absent = not await connection.scalar(
            text("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname=:schema)"),
            {"schema": schema},
        )
        report["schema_absent_after_cleanup"] = absent
        if not absent:
            raise ValueError("QA schema survived cleanup")


async def run_experiment(lease, report):
    schema = "vigil_retention_" + uuid4().hex
    marker = f"vigil.retention.qa:{lease.token}:{schema}"
    report.update(
        {
            "completed": False,
            "token": lease.token,
            "schema": schema,
            "marker": marker,
            "fixture_rows": ROWS,
            "fixture_clock": NOW,
            "base_revision": BASE_REVISION,
            "explain_analyze": False,
            "scope": "retention_fixture_estimated_plans_only",
            "stages": {},
        }
    )
    options = {
        "poolclass": NullPool,
        "connect_args": {
            "timeout": 5,
            "server_settings": {
                "timezone": "UTC",
                "statement_timeout": "30000",
                "lock_timeout": "1000",
            },
        },
    }
    admin = create_engine(lease.url, **options)
    scoped = create_engine(
        lease.url,
        poolclass=NullPool,
        connect_args={
            "timeout": 5,
            "server_settings": {
                **options["connect_args"]["server_settings"],
                "search_path": schema,
            },
        },
    )
    creation_started = False
    try:
        async with admin.begin() as connection:
            report["postgres_version_num"] = await verify_server(connection)
            # Names/marker are built only from normalized UUIDs, never caller SQL.
            if await connection.scalar(
                text("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname=:schema)"),
                {"schema": schema},
            ):
                raise ValueError("QA namespace already exists; preserve it")
            creation_started = True
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.execute(text(f"COMMENT ON SCHEMA \"{schema}\" IS '{marker}'"))
        async with scoped.begin() as connection:
            assert await connection.scalar(text("SELECT current_schema()")) == schema
            await connection.run_sync(migrate, BASE_REVISION)
            report["applied_revision"] = await connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            await seed_fixture(connection)
            report["fixture_distribution"] = await fixture_distribution(connection)
            original = await fingerprint(connection)
            report["fixture_fingerprint"] = original
        captured = {}
        for batch_size in (1, 100, 1000):
            statements, counts = await capture_retention(scoped, batch_size)
            captured[str(batch_size)] = statements
            report.setdefault("rollback_counts", {})[str(batch_size)] = counts
            async with scoped.connect() as connection:
                if await fingerprint(connection) != original:
                    raise ValueError("Retention rollback changed the fixture")
        # Physical writes from capture happen before BOTH plan stages. Statistics
        # are collected once; identical data/binds/stats are reused for candidates.
        async with scoped.begin() as connection:
            for table in (
                "users",
                "projects",
                "monitors",
                "check_jobs",
                "check_results",
                "incidents",
                "sessions",
            ):
                await connection.execute(text(f'ANALYZE "{schema}"."{table}"'))
        # Capture harmless equality probes separately from real service SQL.
        for column in (Incident.opening_check_id, Incident.closing_check_id):
            records = []
            observe = capture_listener(records)
            async with scoped.connect() as connection:
                event.listen(scoped.sync_engine, "before_cursor_execute", observe)
                try:
                    await connection.execute(select(Incident.id).where(column == fixture_id(5, 1)))
                finally:
                    event.remove(scoped.sync_engine, "before_cursor_execute", observe)
            captured[f"fk_equality_probe_{column.name}"] = records
        for stage in ("baseline", "candidates"):
            async with scoped.begin() as connection:
                if stage == "candidates":
                    for name, column in CANDIDATES.items():
                        await connection.execute(
                            text(
                                f'CREATE INDEX "{name}" ON "{schema}".incidents USING btree ({column}) WHERE {column} IS NOT NULL'
                            )
                        )
                report["stages"][stage] = {
                    group: [
                        await explain(connection, statement, parameters)
                        for statement, parameters in statements
                    ]
                    for group, statements in captured.items()
                }
                report.setdefault("incident_catalog", {})[stage] = await incident_catalog(
                    connection, schema
                )
                if stage == "candidates":
                    report["candidate_sizes_bytes"] = {
                        name: await connection.scalar(
                            text("SELECT pg_relation_size(CAST(:name AS regclass))"),
                            {"name": f"{schema}.{name}"},
                        )
                        for name in CANDIDATES
                    }
                if await fingerprint(connection) != original:
                    raise ValueError("EXPLAIN or index creation changed fixture rows")
        report["fixture_rollback_verified"] = True
    except BaseException as error:
        report["error_class"] = type(error).__name__
        raise
    finally:

        async def cleanup():
            try:
                await scoped.dispose()
                if creation_started:
                    await drop_owned(admin, schema, marker, report)
            finally:
                await admin.dispose()

        task = asyncio.create_task(asyncio.wait_for(cleanup(), timeout=20))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise
    # A completed experiment includes successful ownership-checked cleanup.
    report["completed"] = True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa-opt-in", action="store_true")
    parser.add_argument("--token", required=True)
    parser.add_argument("--lease-host", required=True)
    parser.add_argument("--report-file", required=True, type=Path)
    args = parser.parse_args(argv)
    report = {"protocol_version": 1, "completed": False}
    try:
        lease = lease_config(args.qa_opt_in, args.token, args.lease_host, os.environ)
        # Fail a known filesystem error before connecting. Exclusive publication.
        with args.report_file.open("x", encoding="utf-8") as output:
            try:
                asyncio.run(run_experiment(lease, report))
            finally:
                json.dump(report, output, default=str, allow_nan=False, sort_keys=True)
                output.write("\n")
    except (Exception, KeyboardInterrupt) as error:
        print(json.dumps({"completed": False, "error_class": type(error).__name__}))
        return 1
    print(
        json.dumps(
            {
                "completed": True,
                "schema_absent_after_cleanup": report["schema_absent_after_cleanup"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
