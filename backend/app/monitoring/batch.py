"""Bounded, durable one-shot execution without importing a Redis/Taskiq broker."""

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import func, select, text
from sqlalchemy.exc import TimeoutError as DatabaseTimeoutError

from app.config import Settings
from app.db.models import CheckJob, Monitor, Project
from app.db.session import create_engine, create_session_factory
from app.monitoring.executor import CheckExecutor
from app.monitoring.worker import process_job
from app.observability import configure_activity_logging
from app.readiness import database_ready, migration_head
from app.services.check_jobs import reconcile_jobs, schedule_due
from app.services.retention import retain_batch


def require_protected_egress():
    if (
        sys.platform != "linux"
        or os.getuid() != 10001
        or os.getgid() != 10001
        or os.environ.get("VIGIL_EGRESS_READY") != "1"
        or os.environ.get("VIGIL_WORKER_NAMESPACE") != "dedicated"
        or not Path("/.dockerenv").is_file()
    ):
        raise ValueError("Batch requires the protected Linux worker container")
    status = dict(
        line.split(":", 1)
        for line in Path("/proc/self/status").read_text().splitlines()
        if ":" in line
    )
    if status.get("NoNewPrivs", "").strip() != "1" or any(
        int(status.get(name, "1"), 16) != 0
        for name in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
    ):
        raise ValueError("Batch requires dropped capabilities and no-new-privileges")


async def pending_jobs(factory, minimum_interval_seconds, excluded, limit=100):
    async with factory() as db:
        now = await db.scalar(select(func.clock_timestamp()))
        rows = (
            await db.execute(
                select(CheckJob.id, CheckJob.budget_ms, CheckJob.retry_at, Monitor.url)
                .join(Monitor, Monitor.id == CheckJob.monitor_id)
                .join(Project, Project.id == Monitor.project_id)
                .where(
                    CheckJob.status == "pending",
                    CheckJob.scheduled_at <= now,
                    CheckJob.expires_at > now,
                    CheckJob.expires_at
                    >= now + CheckJob.budget_ms * text("INTERVAL '1 millisecond'"),
                    Monitor.interval_seconds >= minimum_interval_seconds,
                    Monitor.archived_at.is_(None),
                    Monitor.paused_at.is_(None),
                    Project.archived_at.is_(None),
                    CheckJob.id.not_in(excluded),
                )
                .order_by(CheckJob.scheduled_at, CheckJob.id)
                .limit(limit)
            )
        ).all()
    return now, rows


async def _execute(factory, executor, settings, report, *, concurrency, max_jobs, deadline):
    active, visited, host_slots = {}, set(), {}
    loop = asyncio.get_running_loop()

    async def execute(identifier, host):
        slot = host_slots.setdefault(host, asyncio.Semaphore(5))
        async with slot:  # Admission precedes claim/lease; never queue claimed work.
            await process_job(factory, executor, identifier, signal=None)

    try:
        while loop.time() < deadline:
            for identifier, operation in list(active.items()):
                if operation.done():
                    await operation  # Persistence errors must fail the run, not appear successful.
                    del active[identifier]
            capacity = concurrency - len(active)
            waiting = None
            if capacity:
                async with factory.begin() as db:
                    await reconcile_jobs(db)
                now, rows = await pending_jobs(
                    factory, settings.minimum_interval_seconds, list(active)
                )
                # Durable backlog gets admission before creating additional jobs.
                ready = [row for row in rows if row[2] is None or row[2] <= now]
                if (
                    len(ready) < capacity
                    and len(visited) < max_jobs
                    and deadline - loop.time() > 51
                ):
                    async with factory.begin() as db:
                        # Total admissions <=5 also bounds each host before job creation.
                        # Reserve the maximum 50s cycle before creating a fresh job.
                        await schedule_due(
                            db,
                            limit=min(capacity - len(ready), max_jobs - len(visited)),
                            fresh_slot=True,
                            minimum_interval_seconds=settings.minimum_interval_seconds,
                        )
                    now, rows = await pending_jobs(
                        factory, settings.minimum_interval_seconds, list(active)
                    )
                for identifier, budget_ms, retry_at, url in rows:
                    if identifier not in visited and len(visited) >= max_jobs:
                        continue
                    if budget_ms / 1000 + 1 > deadline - loop.time():
                        report["deferred"] += 1
                        continue
                    if retry_at is not None and retry_at > now:
                        delay = (retry_at - now).total_seconds()
                        waiting = delay if waiting is None else min(waiting, delay)
                        continue
                    visited.add(identifier)
                    active[identifier] = asyncio.create_task(
                        execute(identifier, urlsplit(url).hostname)
                    )
                    report["attempts"] += 1
                    capacity -= 1
                    if not capacity:
                        break
            if not active:
                if waiting is None:
                    break
                await asyncio.sleep(min(waiting, 1))
            else:
                await asyncio.wait(
                    active.values(), timeout=0.1, return_when=asyncio.FIRST_COMPLETED
                )
        report["jobs_admitted"] = len(visited)
        if active:
            report["deadline_reached"] = True
    finally:
        for operation in active.values():
            operation.cancel()
        await asyncio.gather(*active.values(), return_exceptions=True)
        report["jobs_admitted"] = len(visited)
    # Count durable final states, not process_job's ACK-eligibility boolean.
    if visited:
        async with factory() as db:
            statuses = (
                await db.execute(
                    select(CheckJob.status, func.count())
                    .where(CheckJob.id.in_(visited))
                    .group_by(CheckJob.status)
                )
            ).all()
        report["job_states"] = dict(statuses)


async def run_batch(
    settings,
    *,
    engine=None,
    executor=None,
    max_seconds=90,
    concurrency=5,
    max_jobs=100,
    retention_batches=1,
):
    """Injected engines/executors support isolated tests; CLI always checks OS protection."""
    if not settings.pipeline_enabled or not settings.monitoring_network_enabled:
        raise ValueError("Batch requires explicit pipeline and network gates")
    if isinstance(max_seconds, bool) or not 5 < max_seconds <= 90:
        raise ValueError("Batch duration must be greater than 5 and at most 90 seconds")
    for value, low, high in ((concurrency, 1, 5), (max_jobs, 1, 1000), (retention_batches, 0, 3)):
        if type(value) is not int or not low <= value <= high:
            raise ValueError("Invalid batch limits")
    owned_engine = engine is None
    if owned_engine:
        engine = create_engine(
            settings.database_url,
            **settings.database_options,
            pool_timeout=3,
            connect_args={
                "timeout": settings.readiness_timeout_seconds,
                "command_timeout": 5,
                "server_settings": {"statement_timeout": "5000", "lock_timeout": "1000"},
            },
        )
    report = {
        "status": "ok",
        "stage": "preflight",
        "attempts": 0,
        "jobs_admitted": 0,
        "job_states": {},
        "deferred": 0,
        "deadline_reached": False,
        "retention": {},
        "backlog": {},
    }
    factory = create_session_factory(engine)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max_seconds - 5  # Reserve bounded engine shutdown time.
    run_timeout = asyncio.timeout(max_seconds - 5)
    try:
        async with run_timeout:
            async with asyncio.timeout(settings.readiness_timeout_seconds):
                await database_ready(engine, expected_head=migration_head())
            report["stage"] = "execution"
            await _execute(
                factory,
                executor or CheckExecutor(),
                settings,
                report,
                concurrency=concurrency,
                max_jobs=max_jobs,
                deadline=deadline,
            )
            report["stage"] = "summary"
            async with factory() as db:
                now = await db.scalar(select(func.clock_timestamp()))
                eligible = (
                    Monitor.archived_at.is_(None),
                    Monitor.paused_at.is_(None),
                    Project.archived_at.is_(None),
                )
                due = await db.scalar(
                    select(func.count())
                    .select_from(Monitor)
                    .join(Project)
                    .where(
                        *eligible,
                        Monitor.interval_seconds >= settings.minimum_interval_seconds,
                        Monitor.next_check_at <= now,
                    )
                )
                pending = await db.scalar(
                    select(func.count())
                    .select_from(CheckJob)
                    .join(Monitor)
                    .join(Project)
                    .where(
                        *eligible,
                        Monitor.interval_seconds >= settings.minimum_interval_seconds,
                        CheckJob.status.in_(("pending", "running")),
                    )
                )
                legacy = await db.scalar(
                    select(func.count())
                    .select_from(Monitor)
                    .join(Project)
                    .where(
                        *eligible,
                        Monitor.interval_seconds < settings.minimum_interval_seconds,
                    )
                )
                report["backlog"] = {
                    "due_monitors": due,
                    "open_jobs": pending,
                    "below_minimum_monitors": legacy,
                }
            report["stage"] = "retention"
            counts = Counter()
            for _ in range(retention_batches):
                if deadline - loop.time() < 2:
                    break
                # Include remote round trips across the bounded multi-query batch.
                # Per-statement limits and the global run deadline remain intact.
                async with asyncio.timeout(min(10, deadline - loop.time())), factory.begin() as db:
                    await db.execute(text("SET LOCAL lock_timeout = '1s'"))
                    await db.execute(text("SET LOCAL statement_timeout = '1s'"))
                    result = await retain_batch(
                        db, batch_size=100, session_idle_seconds=settings.session_idle_seconds
                    )
                counts.update(
                    {
                        key: getattr(result, key)
                        for key in ("check_results", "check_jobs", "incidents", "sessions")
                    }
                )
                # Only committed batches contribute, including when a later batch fails.
                report["retention"] = dict(counts)
                if result.total == 0:
                    break
            report["stage"] = "complete"
    except (TimeoutError, DatabaseTimeoutError):
        if run_timeout.expired():
            report.update(
                status="partial", error_code="batch_deadline_exceeded", deadline_reached=True
            )
        else:
            report.update(
                status="partial" if report["stage"] == "retention" else "error",
                error_code=f"{report['stage']}_timeout",
            )
    except Exception:
        report.update(status="error", error_code=f"{report['stage']}_failed")
    finally:
        if owned_engine:
            try:
                async with asyncio.timeout(5):
                    await engine.dispose()
            except Exception as error:
                code = "cleanup_timeout" if isinstance(error, TimeoutError) else "cleanup_failed"
                if report["status"] == "ok":
                    report.update(status="error", stage="cleanup", error_code=code)
                else:
                    report["cleanup_error_code"] = code
    if report["status"] == "ok" and (
        report["deadline_reached"]
        or report["deferred"]
        or any(report["backlog"].values())
        or any(
            report["job_states"].get(state, 0)
            for state in ("pending", "running", "expired", "exhausted")
        )
    ):
        report["status"] = "partial"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Bounded protected monitoring batch")
    parser.add_argument("--max-seconds", type=float, default=90)
    parser.add_argument("--concurrency", type=int, default=5, help="1..5 concurrent admissions")
    parser.add_argument("--max-jobs", type=int, default=100)
    parser.add_argument("--retention-batches", type=int, default=1)
    args = parser.parse_args(argv)
    stage = "protection"
    try:
        require_protected_egress()
        stage = "configuration"
        settings = Settings()
        if "database_url" not in settings.model_fields_set:
            raise ValueError("Batch requires an explicit database URL")
        configure_activity_logging()
        stage = "initialization"
        report = asyncio.run(run_batch(settings, **vars(args)))
    except Exception:
        report = {"status": "error", "stage": stage, "error_code": "batch_failed"}
    print(json.dumps(report, separators=(",", ":")))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
