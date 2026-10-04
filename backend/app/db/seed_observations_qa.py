"""Opt-in synthetic QA data, never imported by the product or executing HTTP.

From backend/: set VIGIL_QA_DATABASE_URL explicitly, then run
python -m app.db.seed_observations_qa seed-synthetic-qa --manifest <private path>.
The CLI accepts only local Compose PostgreSQL 17 on port 55433/database vigil.
Every invocation creates a new owner; an existing manifest is never overwritten.
"""

import argparse
import asyncio
import json
import math
import os
import secrets
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url

from app.config import Settings
from app.db.models import CheckJob, CheckResult, Incident, Monitor, Project, User
from app.db.session import create_engine, create_session_factory
from app.domain.health import (
    HealthState,
    MonitorHealth,
    Sample,
    aggregate_health,
    apply_evaluated_cycle,
    freshness,
    summarize_samples,
)
from app.security import PASSWORD_HASHER
from app.services import observations

KIND = "synthetic_persisted_qa"
PERIODS = {"24h": 1, "7d": 7, "30d": 30}
END_REASONS = ("recovered", "configuration_changed", "archived")


def validate_target(url: str, settings: Settings) -> None:
    target = make_url(url)
    if (
        target.drivername != "postgresql+asyncpg"
        or target.host not in ("localhost", "127.0.0.1")
        or target.port != 55433
        or target.database != "vigil"
        or target.query
    ):
        raise ValueError("QA seed requires local Compose PostgreSQL on port 55433/database vigil")
    if (
        settings.environment == "prod"
        or settings.pipeline_enabled
        or settings.monitoring_network_enabled
    ):
        raise ValueError(
            "QA seed requires non-production settings and both execution gates disabled"
        )


def json_value(value):
    return json.loads(
        json.dumps(
            value,
            default=lambda item: item.isoformat() if isinstance(item, datetime) else str(item),
        )
    )


def assert_equivalent(actual, expected, path="fixture"):
    """Compare PostgreSQL DTOs to expected values derived from the raw fixture."""
    if isinstance(expected, dict):
        if actual.keys() != expected.keys():
            raise AssertionError(f"{path}: DTO keys differ")
        for key, value in expected.items():
            assert_equivalent(actual[key], value, f"{path}.{key}")
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            raise AssertionError(f"{path}: lengths differ")
        for index, value in enumerate(expected):
            assert_equivalent(actual[index], value, f"{path}[{index}]")
    elif isinstance(expected, float):
        if actual is None or not math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9):
            raise AssertionError(f"{path}: numeric value differs")
    elif actual != expected:
        raise AssertionError(f"{path}: value differs")


def _expected_metrics(monitors, samples, now, days):
    start = now - timedelta(days=days)
    entries = [sample for monitor in monitors for sample in samples[monitor.id]]

    def statistics(values):
        result = asdict(summarize_samples(values, start=start, end=now))
        result["sample_count"] = result["success_count"] + result["failure_count"]
        return result

    groups = defaultdict(list)
    for sample in entries:
        if start <= sample.scheduled_at < now:
            bucket = sample.scheduled_at.replace(minute=0, second=0, microsecond=0)
            if days > 1:
                bucket = bucket.replace(hour=0)
            groups[bucket].append(sample)
    states = [
        MonitorHealth(
            monitor.health_status,
            freshness(
                now=now,
                interval_seconds=monitor.interval_seconds,
                last_checked_at=monitor.last_checked_at,
                paused=monitor.paused_at is not None,
            ),
        )
        for monitor in monitors
    ]
    health, complete = aggregate_health(states)
    return json_value(
        {
            "from": start,
            "to": now,
            "computed_at": now,
            **statistics(entries),
            "excluded_count": 0,
            "cancelled_count": 0,
            "pending_count": 0,
            "skipped_slots": 0,
            "health_status": health,
            "data_complete": complete,
            "freshness_counts": {
                state: sum(entry.freshness == state for entry in states)
                for state in ("no_data", "fresh", "stale", "paused")
            },
            "bucket_seconds": 3600 if days == 1 else 86400,
            "series": [
                {"bucket_start": bucket, **statistics(groups[bucket])} for bucket in sorted(groups)
            ],
        }
    )


async def _cycles(db, monitor, values, *, administrative_examples=False):
    state = HealthState()
    samples, incidents = [], []
    opened = None
    for index, (scheduled, outcome, latency, attempt_count) in enumerate(values):
        duration = 7000 if attempt_count == 2 else 5000 if outcome == "failure" else 1000
        completed = scheduled + timedelta(milliseconds=duration)
        transition = apply_evaluated_cycle(
            state,
            outcome=outcome,
            started_at=scheduled,
            completed_at=completed,
            failure_threshold=1,
            attempt_count=attempt_count,
            latency_ms=latency,
            latency_threshold_ms=1000,
            incident_is_open=opened is not None,
        )
        attempts = []
        if attempt_count == 2:
            attempts.append({"error_code": "timeout", "duration_ms": 5000})
        attempts.append(
            {"http_status": 200, "latency_ms": latency, "duration_ms": 1000}
            if outcome == "success"
            else {"error_code": "timeout", "duration_ms": 5000}
        )
        job = CheckJob(
            id=uuid4(),
            monitor_id=monitor.id,
            config_version=1,
            config_snapshot={
                "fixture_kind": KIND,
                "external_checks_executed": False,
                "url": monitor.url,
                "method": "GET",
                "interval_seconds": 3600,
                "timeout_ms": 5000,
                "expected_status": 200,
                "failure_threshold": 1,
                "retry_count": 1,
                "latency_threshold_ms": 1000,
            },
            scheduled_at=scheduled,
            expires_at=scheduled + timedelta(hours=1),
            budget_ms=13600,
            status="completed",
            execution_count=1,
            started_at=scheduled,
            finished_at=completed,
            created_at=scheduled,
            updated_at=completed,
        )
        db.add(job)
        await db.flush()
        result = CheckResult(
            id=uuid4(),
            job_id=job.id,
            monitor_id=monitor.id,
            config_version=1,
            scheduled_at=scheduled,
            started_at=scheduled,
            completed_at=completed,
            outcome=outcome,
            http_status=200 if outcome == "success" else None,
            latency_ms=latency,
            cycle_duration_ms=duration,
            queue_delay_ms=0,
            attempt_count=attempt_count,
            attempts=attempts,
            error_code=None if outcome == "success" else "timeout",
            health_after=transition.state.health_status,
            degradation_reason=transition.degradation_reason,
        )
        db.add(result)
        await db.flush()
        if transition.open_incident:
            opened = Incident(
                id=uuid4(),
                monitor_id=monitor.id,
                started_at=transition.incident_started_at,
                detected_at=completed,
                opening_check_id=result.id,
                cause_code="timeout",
                failure_threshold_snapshot=1,
                created_at=completed,
                updated_at=completed,
            )
            incidents.append(opened)
        if transition.close_incident:
            reason = END_REASONS[(index // 2) % 3] if administrative_examples else "recovered"
            opened.ended_at = completed
            opened.end_reason = reason
            opened.closing_check_id = result.id if reason == "recovered" else None
            opened.updated_at = completed
            opened = None
        samples.append(Sample(scheduled, outcome, latency))
        state = transition.state
        monitor.health_status = state.health_status
        monitor.consecutive_failures = state.consecutive_failures
        monitor.first_failure_at = state.first_failure_at
        monitor.last_checked_at = completed
        monitor.last_scheduled_at = scheduled
        monitor.last_http_status = result.http_status
        monitor.last_latency_ms = latency
        monitor.last_outcome = outcome
        monitor.last_error_code = result.error_code
        monitor.last_degradation_reason = transition.degradation_reason
    db.add_all(incidents)
    await db.flush()
    return samples, incidents


def _incident_counts(incidents):
    closed = sum(incident.ended_at is not None for incident in incidents)
    return {"all": len(incidents), "open": len(incidents) - closed, "closed": closed}


async def seed_fixture(db, *, now: datetime | None = None):
    """Insert a new isolated QA owner within a caller-owned PostgreSQL transaction."""
    if db.get_bind().dialect.name != "postgresql" or not db.in_transaction():
        raise ValueError("QA fixture requires a caller-owned PostgreSQL transaction")
    now = now or await db.scalar(select(func.clock_timestamp()))
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("QA fixture requires timezone-aware time")
    now = now.astimezone(UTC).replace(microsecond=0)
    suffix = uuid4().hex
    password = "Vigil-QA-" + secrets.token_urlsafe(24)
    created = now - timedelta(days=4)
    owner = User(
        id=uuid4(),
        email=f"qa.observations.{suffix}@example.com",
        password_hash=PASSWORD_HASHER.hash(password),
        created_at=created,
        updated_at=now,
    )
    db.add(owner)
    await db.flush()
    project = Project(
        id=uuid4(),
        owner_id=owner.id,
        name="QA sintética — Observações " + suffix[:8],
        description="Fixture sintética persistida de QA. Nenhuma chamada HTTP foi executada.",
        public_slug="qa-synthetic-" + suffix,
        public_status_enabled=True,
        created_at=created,
        updated_at=now,
    )
    db.add(project)
    await db.flush()
    names = {
        "target": "QA sintética — Histórico e retries",
        "offline": "QA sintética — Offline recente",
        "stale": "QA sintética — Leitura antiga",
        "paused": "QA sintética — Pausado",
        "no_data": "QA sintética — Sem dados",
        "private": "QA sintética — Sentinela privada",
    }
    monitors = {
        role: Monitor(
            id=uuid4(),
            project_id=project.id,
            name=name,
            url=f"https://qa-{role}.invalid/never-executed",
            interval_seconds=3600,
            failure_threshold=1,
            is_public=role in ("target", "offline", "no_data"),
            next_check_at=None,
            paused_at=now - timedelta(minutes=1) if role == "paused" else None,
            created_at=created,
            updated_at=now,
        )
        for role, name in names.items()
    }
    db.add_all(monitors.values())
    await db.flush()
    target = [
        (
            now - timedelta(hours=71 - index, minutes=5),
            "failure" if index % 2 == 0 else "success",
            None if index % 2 == 0 else float(100 + 10 * (index // 2)),
            2 if index % 8 == 7 else 1,
        )
        for index in range(72)
    ]
    definitions = {
        "target": target,
        "offline": [(now - timedelta(minutes=2), "failure", None, 1)],
        "stale": [(now - timedelta(hours=5), "success", 700.0, 1)],
        "paused": [(now - timedelta(minutes=10), "success", 900.0, 1)],
        "no_data": [],
        "private": [(now - timedelta(minutes=4), "failure", None, 1)],
    }
    samples, incidents = {}, {}
    for role, monitor in monitors.items():
        samples[monitor.id], incidents[monitor.id] = await _cycles(
            db, monitor, definitions[role], administrative_examples=role == "target"
        )
    project.revision = sum(len(values) for values in samples.values())
    await db.flush()
    all_monitors = list(monitors.values())
    public_monitors = [monitor for monitor in all_monitors if monitor.is_public]
    expected = {
        "per_monitor": {
            str(monitor.id): {
                period: _expected_metrics([monitor], samples, now, days)
                for period, days in PERIODS.items()
            }
            for monitor in all_monitors
        },
        "project": {
            period: _expected_metrics(all_monitors, samples, now, days)
            for period, days in PERIODS.items()
        },
        "public": {
            period: _expected_metrics(public_monitors, samples, now, days)
            for period, days in PERIODS.items()
        },
        "incidents_by_period": {},
    }
    for period, days in PERIODS.items():
        start = now - timedelta(days=days)
        selected = {
            monitor.id: [
                incident
                for incident in incidents[monitor.id]
                if incident.started_at < now
                and (incident.ended_at is None or incident.ended_at > start)
            ]
            for monitor in all_monitors
        }
        expected["incidents_by_period"][period] = {
            "project": _incident_counts([item for values in selected.values() for item in values]),
            "public": _incident_counts(
                [item for monitor in public_monitors for item in selected[monitor.id]]
            ),
            "per_monitor": {
                str(monitor.id): _incident_counts(selected[monitor.id]) for monitor in all_monitors
            },
        }
    expected["incidents"] = expected["incidents_by_period"]["30d"]
    manifest = json_value(
        {
            "fixture_version": 1,
            "fixture_kind": KIND,
            "external_checks_executed": False,
            "seed_timestamp": now,
            "fresh_until": min(
                monitor.last_checked_at + timedelta(hours=2)
                for monitor in all_monitors
                if monitor.last_checked_at and monitor_freshness(monitor, now) == "fresh"
            ),
            "database": {
                "name": await db.scalar(select(func.current_database())),
                "schema": await db.scalar(select(func.current_schema())),
            },
            "login": {"email": owner.email, "password": password},
            "owner_id": owner.id,
            "project": {"id": project.id, "name": project.name, "public_slug": project.public_slug},
            "monitors": [
                {
                    "id": monitor.id,
                    "role": role,
                    "name": monitor.name,
                    "is_public": monitor.is_public,
                    "health_status": monitor.health_status,
                    "freshness": monitor_freshness(monitor, now),
                    "checks_total": len(samples[monitor.id]),
                    "incidents_total": len(incidents[monitor.id]),
                }
                for role, monitor in monitors.items()
            ],
            "expected": expected,
            "notes": [
                "Synthetic persisted QA snapshots, not real availability measurements or HTTP checks.",
                "Historical administrative incident reasons are synthetic DTO examples, not executed lifecycle actions.",
                "Expected DTOs use seed_timestamp; live period timestamps advance. Compare statistics/series independently of from/to/computed_at.",
                "Freshness expires at fresh_until. All next_check_at values are NULL; reseed with a new private manifest for a later smoke.",
                "The CLI never reuses owners, overwrites manifests, enables gates, starts jobs or contacts monitor URLs.",
            ],
        }
    )
    await verify_fixture(db, manifest)
    return manifest


def monitor_freshness(monitor, now):
    return freshness(
        now=now,
        interval_seconds=monitor.interval_seconds,
        last_checked_at=monitor.last_checked_at,
        paused=monitor.paused_at is not None,
    )


async def verify_fixture(db, manifest):
    project_id = UUID(manifest["project"]["id"])
    monitors = (await db.scalars(select(Monitor).where(Monitor.project_id == project_id))).all()
    now = datetime.fromisoformat(manifest["seed_timestamp"])
    for period, days in PERIODS.items():
        window = observations.Window(now - timedelta(days=days), now, now)
        for monitor in monitors:
            actual = json_value(await observations.metrics(db, [monitor], window))
            assert_equivalent(actual, manifest["expected"]["per_monitor"][str(monitor.id)][period])
        actual = json_value(await observations.metrics(db, monitors, window))
        assert_equivalent(actual, manifest["expected"]["project"][period])
        public = [monitor for monitor in monitors if monitor.is_public]
        actual = json_value(await observations.metrics(db, public, window))
        assert_equivalent(actual, manifest["expected"]["public"][period])
        for scope, public_only in (("project", False), ("public", True)):
            for state in ("all", "open", "closed"):
                _, total = await observations.incident_page(
                    db,
                    project_id,
                    window,
                    monitor_id=None,
                    state=state,
                    public=public_only,
                    limit=20,
                    offset=0,
                )
                if total != manifest["expected"]["incidents_by_period"][period][scope][state]:
                    raise AssertionError("Persisted incident count differs from fixture")


async def run_seed(url, manifest_path):
    engine = create_engine(url)
    try:
        async with create_session_factory(engine).begin() as db:
            version = int(await db.scalar(text("SHOW server_version_num")))
            if (
                not 170000 <= version < 180000
                or await db.scalar(select(func.current_schema())) != "public"
            ):
                raise ValueError("CLI QA seed requires PostgreSQL 17 and namespace public")
            manifest = await seed_fixture(db)
            manifest["database"].update(host="127.0.0.1", port=55433, server_version_num=version)
        async with create_session_factory(engine).begin() as db:
            await verify_fixture(db, manifest)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with manifest_path.open("x", encoding="utf-8") as output:
            json.dump(manifest, output, ensure_ascii=False, indent=2)
            output.write("\n")
        return manifest
    finally:
        await engine.dispose()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["seed-synthetic-qa"])
    parser.add_argument("--database-env", default="VIGIL_QA_DATABASE_URL")
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    url = os.environ.get(args.database_env)
    if not url:
        parser.error("Set an explicit QA database URL in the requested environment variable")
    if args.manifest.exists():
        parser.error("Private manifest already exists; use a new path for a new isolated QA owner")
    try:
        validate_target(url, Settings(database_url=url))
        result = asyncio.run(run_seed(url, args.manifest))
    except Exception as error:
        print(
            f"QA seed failed: {type(error).__name__}; inspect target and private manifest",
            file=__import__("sys").stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "fixture_kind": KIND,
                "external_checks_executed": False,
                "project_id": result["project"]["id"],
                "manifest": str(args.manifest.resolve()),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
