"""Bounded observation queries. PostgreSQL computes percentiles over raw samples."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.db.models import CheckJob, CheckResult, Incident, Monitor, Project
from app.domain.health import MonitorHealth, aggregate_health, freshness
from app.security import aware, utcnow


@dataclass(frozen=True)
class Window:
    start: datetime
    end: datetime
    computed_at: datetime


def observation_window(
    period: str, start: datetime | None, end: datetime | None, *, retention_days: int = 30
) -> Window:
    now = utcnow()
    if (start is None) != (end is None):
        raise ApiError(422, "invalid_window", "Provide both from and to")
    if start is None:
        days = {"24h": 1, "7d": 7, "30d": 30, "90d": 90}.get(period)
        if days is None or days > retention_days:
            raise ApiError(422, "invalid_window", "Period exceeds the resource retention")
        end = now
        start = now - timedelta(days=days)
    assert end is not None
    if any(value.tzinfo is None or value.utcoffset() is None for value in (start, end)):
        raise ApiError(422, "invalid_window", "Window timestamps require timezone offsets")
    if start >= end or end > now or start < now - timedelta(days=retention_days):
        raise ApiError(
            422, "invalid_window", f"Window must be within the last {retention_days} days"
        )
    return Window(start.astimezone(UTC), end.astimezone(UTC), now)


def monitor_freshness(monitor: Monitor, now: datetime):
    return freshness(
        now=now,
        interval_seconds=monitor.interval_seconds,
        last_checked_at=aware(monitor.last_checked_at) if monitor.last_checked_at else None,
        paused=monitor.paused_at is not None,
    )


def health_summary(monitors: Sequence[Monitor], now: datetime) -> dict:
    entries = [MonitorHealth(m.health_status, monitor_freshness(m, now)) for m in monitors]
    health, complete = aggregate_health(entries)
    return {
        "health_status": health,
        "data_complete": complete,
        "freshness_counts": {
            value: sum(e.freshness == value for e in entries)
            for value in ("no_data", "fresh", "stale", "paused")
        },
    }


def _aggregations(postgres: bool):
    success = CheckResult.outcome == "success"
    return (
        func.count().filter(success).label("success_count"),
        func.count().filter(CheckResult.outcome == "failure").label("failure_count"),
        func.count(CheckResult.latency_ms).filter(success).label("latency_sample_count"),
        func.avg(CheckResult.latency_ms).filter(success).label("average_latency_ms"),
        (
            func.percentile_cont(0.95).within_group(CheckResult.latency_ms).filter(success)
            if postgres
            else literal(None)
        ).label("p95_latency_ms"),
    )


def _stats(row) -> dict:
    values = dict(row._mapping)
    evaluated = values["success_count"] + values["failure_count"]
    values["sample_count"] = evaluated
    values["uptime_percent"] = 100 * values["success_count"] / evaluated if evaluated else None
    return values


def _percentile(values: Sequence[float]) -> float | None:
    # SQLite is only a test adapter. Runtime always uses PostgreSQL percentile_cont.
    if not values:
        return None
    ordered = sorted(values)
    position = 0.95 * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


async def metrics(db: AsyncSession, monitors: Sequence[Monitor], window: Window) -> dict:
    ids = [m.id for m in monitors]
    conditions = (
        CheckResult.monitor_id.in_(ids),
        CheckResult.scheduled_at >= window.start,
        CheckResult.scheduled_at < window.end,
    )
    postgres = db.bind.dialect.name == "postgresql"
    row = (await db.execute(select(*_aggregations(postgres)).where(*conditions))).one()
    summary = _stats(row)
    if not postgres:
        latencies = (
            await db.scalars(
                select(CheckResult.latency_ms).where(
                    *conditions,
                    CheckResult.outcome == "success",
                    CheckResult.latency_ms.is_not(None),
                )
            )
        ).all()
        summary["p95_latency_ms"] = _percentile(latencies)
    job_stats = (
        await db.execute(
            select(
                func.count()
                .filter(CheckJob.status.in_(("expired", "exhausted")))
                .label("excluded_count"),
                func.count().filter(CheckJob.status == "cancelled").label("cancelled_count"),
                func.count()
                .filter(CheckJob.status.in_(("pending", "running")))
                .label("pending_count"),
                func.coalesce(func.sum(CheckJob.skipped_slots), 0).label("skipped_slots"),
            ).where(
                CheckJob.monitor_id.in_(ids),
                CheckJob.scheduled_at >= window.start,
                CheckJob.scheduled_at < window.end,
            )
        )
    ).one()
    bucket_seconds = 3600 if window.end - window.start <= timedelta(days=1) else 86400
    if postgres:
        bucket = func.date_trunc(
            "hour" if bucket_seconds == 3600 else "day", CheckResult.scheduled_at, "UTC"
        )
    else:
        bucket = func.strftime(
            "%Y-%m-%d %H:00:00" if bucket_seconds == 3600 else "%Y-%m-%d 00:00:00",
            CheckResult.scheduled_at,
        )
    rows = (
        await db.execute(
            select(bucket.label("bucket_start"), *_aggregations(postgres))
            .where(*conditions)
            .group_by(bucket)
            .order_by(bucket)
        )
    ).all()
    series = []
    for entry in rows:
        stats = _stats(entry)
        if not postgres:
            timestamp = datetime.fromisoformat(stats["bucket_start"]).replace(tzinfo=UTC)
            stats["bucket_start"] = timestamp
            values = (
                await db.scalars(
                    select(CheckResult.latency_ms).where(
                        *conditions,
                        bucket == entry.bucket_start,
                        CheckResult.outcome == "success",
                        CheckResult.latency_ms.is_not(None),
                    )
                )
            ).all()
            stats["p95_latency_ms"] = _percentile(values)
        series.append(stats)
    return {
        "from": window.start,
        "to": window.end,
        "computed_at": window.computed_at,
        **summary,
        **dict(job_stats._mapping),
        **health_summary(monitors, window.computed_at),
        "bucket_seconds": bucket_seconds,
        "series": series,
    }


async def incident_page(
    db: AsyncSession,
    project_id: UUID,
    window: Window,
    *,
    monitor_id: UUID | None,
    state: str,
    public: bool,
    limit: int,
    offset: int,
):
    conditions = [
        Monitor.project_id == project_id,
        Monitor.archived_at.is_(None),
        Incident.started_at < window.end,
        or_(Incident.ended_at.is_(None), Incident.ended_at > window.start),
    ]
    if monitor_id is not None:
        conditions.append(Monitor.id == monitor_id)
    if public:
        conditions.append(Monitor.is_public.is_(True))
    if state == "open":
        conditions.append(Incident.ended_at.is_(None))
    elif state == "closed":
        conditions.append(Incident.ended_at.is_not(None))
    total = await db.scalar(
        select(func.count()).select_from(Incident).join(Monitor).where(*conditions)
    )
    rows = (
        await db.execute(
            select(Incident, Monitor.name)
            .join(Monitor)
            .where(*conditions)
            .order_by(Incident.started_at.desc(), Incident.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return rows, total


async def published_project(db: AsyncSession, slug: str) -> tuple[Project, list[Monitor]]:
    project = await db.scalar(
        select(Project).where(
            Project.public_slug == slug,
            Project.public_status_enabled.is_(True),
            Project.archived_at.is_(None),
        )
    )
    if project is None:
        raise ApiError(404, "not_found", "Status page not found")
    monitors = (
        await db.scalars(
            select(Monitor)
            .where(
                Monitor.project_id == project.id,
                Monitor.is_public.is_(True),
                Monitor.archived_at.is_(None),
            )
            .order_by(Monitor.created_at, Monitor.id)
        )
    ).all()
    return project, monitors
