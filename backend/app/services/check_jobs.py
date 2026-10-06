"""Database-only monitoring pipeline. Call inside caller-owned transactions.

Never retain these sessions/locks while doing HTTP or publishing to a broker.
All timestamps are aware; production defaults use the PostgreSQL clock after locks.
"""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CheckJob, CheckResult, Incident, Monitor, Project
from app.domain.health import HealthState, apply_evaluated_cycle
from app.domain.monitors import CHECK_FIELDS
from app.domain.monitors import cycle_budget_ms as calculate_cycle_budget

OPEN = ("pending", "running")
TARGET_ERRORS = {"timeout", "dns_error", "connection_error", "tls_error", "unexpected_status"}
TECHNICAL_ERRORS = {
    "internal_error",
    "execution_crashed",
    "pool_exhausted",
    "blocked_destination",
    "database_error",
}
SNAPSHOT_FIELDS = tuple(sorted(CHECK_FIELDS))


@dataclass(frozen=True)
class ClaimedJob:
    job_id: UUID
    monitor_id: UUID
    config_version: int
    lease_token: UUID
    lease_expires_at: datetime
    scheduled_at: datetime
    expires_at: datetime
    budget_ms: int
    config_snapshot: dict[str, Any]
    started_at: datetime


@dataclass(frozen=True)
class EvaluatedCycle:
    started_at: datetime
    completed_at: datetime
    outcome: str
    http_status: int | None
    latency_ms: float | None
    cycle_duration_ms: float
    attempt_count: int
    attempts: list[dict[str, Any]]
    error_code: str | None = None


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")


async def _clock(db: AsyncSession, supplied: datetime | None) -> datetime:
    if supplied is not None:
        _aware(supplied)
        return supplied
    return await db.scalar(select(func.clock_timestamp()))


def cycle_budget_ms(timeout_ms: int, retry_count: int, interval_seconds: int) -> int:
    if not 1000 <= timeout_ms <= 15000 or not 0 <= retry_count <= 2:
        raise ValueError("invalid check timeout/retry count")
    budget = calculate_cycle_budget(timeout_ms, retry_count)
    if budget > 50000 or budget >= interval_seconds * 1000:
        raise ValueError("cycle budget must be <=50s and less than the interval")
    return budget


def _invalid(project: Project, monitor: Monitor, job: CheckJob) -> str | None:
    if project.archived_at is not None or monitor.archived_at is not None:
        return "archived"
    if monitor.paused_at is not None:
        return "paused"
    if monitor.config_version != job.config_version:
        return "configuration_changed"
    return None


def _finish_unevaluated(
    monitor: Monitor, job: CheckJob, now: datetime, status: str, error_code: str, *, interrupt=True
) -> None:
    job.status = status
    job.error_code = error_code
    job.finished_at = now
    job.lease_token = None
    job.lease_expires_at = None
    job.retry_at = None
    if interrupt:
        monitor.consecutive_failures = 0
        monitor.first_failure_at = None


async def _lock_job(db: AsyncSession, job_id: UUID, *, skip_locked=False):
    identity = (
        await db.execute(
            select(CheckJob.monitor_id, Monitor.project_id)
            .join(Monitor, Monitor.id == CheckJob.monitor_id)
            .where(CheckJob.id == job_id)
        )
    ).one_or_none()
    if identity is None:
        return None
    project = await db.scalar(
        select(Project)
        .where(Project.id == identity.project_id)
        .with_for_update(skip_locked=skip_locked)
        .execution_options(populate_existing=True)
    )
    if project is None:
        return None
    monitor = await db.scalar(
        select(Monitor)
        .where(Monitor.id == identity.monitor_id)
        .with_for_update(skip_locked=skip_locked)
        .execution_options(populate_existing=True)
    )
    if monitor is None:
        return None
    job = await db.scalar(
        select(CheckJob)
        .where(CheckJob.id == job_id)
        .with_for_update(skip_locked=skip_locked)
        .execution_options(populate_existing=True)
    )
    if job is None:
        return None
    return project, monitor, job


async def schedule_due(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = 100,
    fresh_slot: bool = False,
    minimum_interval_seconds: int = 60,
) -> list[UUID]:
    """Atomically schedule a due slot; opt-in batches start a full interval now."""
    if not 1 <= limit <= 100:
        raise ValueError("scheduler limit must be 1..100")
    if not isinstance(fresh_slot, bool):
        raise ValueError("fresh_slot must be a boolean")
    if (
        isinstance(minimum_interval_seconds, bool)
        or not isinstance(minimum_interval_seconds, int)
        or not 60 <= minimum_interval_seconds <= 3600
    ):
        raise ValueError("minimum_interval_seconds must be an integer from 60 to 3600")
    timestamp = await _clock(db, now)
    monitors = (
        await db.scalars(
            select(Monitor)
            .join(Project)
            .where(
                Project.archived_at.is_(None),
                Monitor.archived_at.is_(None),
                Monitor.paused_at.is_(None),
                Monitor.interval_seconds >= minimum_interval_seconds,
                Monitor.next_check_at <= timestamp,
            )
            .order_by(Monitor.next_check_at, Monitor.id)
            .limit(limit)
            .with_for_update(of=Monitor, skip_locked=True)
            .execution_options(populate_existing=True)
        )
    ).all()
    ids = []
    for monitor in monitors:
        current = await db.scalar(
            select(CheckJob)
            .where(CheckJob.monitor_id == monitor.id, CheckJob.status.in_(OPEN))
            .with_for_update()
        )
        if fresh_slot:
            # Refresh after monitor/job locks, so sparse batches get a full window.
            timestamp = await _clock(db, now)
        if current is not None:
            if current.config_version != monitor.config_version:
                _finish_unevaluated(
                    monitor,
                    current,
                    timestamp,
                    "cancelled",
                    "configuration_changed",
                    interrupt=False,
                )
            elif timestamp >= current.expires_at or (
                current.status == "pending"
                and timestamp + timedelta(milliseconds=current.budget_ms) > current.expires_at
            ):
                _finish_unevaluated(monitor, current, timestamp, "expired", "insufficient_budget")
            else:
                continue
            await db.flush()  # release partial uniqueness before inserting the next job
        skipped = int(
            (timestamp - monitor.next_check_at).total_seconds() // monitor.interval_seconds
        )
        slot = (
            timestamp
            if fresh_slot
            else monitor.next_check_at + timedelta(seconds=skipped * monitor.interval_seconds)
        )
        job = CheckJob(
            id=uuid4(),
            monitor_id=monitor.id,
            config_version=monitor.config_version,
            config_snapshot={field: getattr(monitor, field) for field in SNAPSHOT_FIELDS},
            scheduled_at=slot,
            expires_at=slot + timedelta(seconds=monitor.interval_seconds),
            budget_ms=cycle_budget_ms(
                monitor.timeout_ms, monitor.retry_count, monitor.interval_seconds
            ),
            skipped_slots=skipped,
            status="pending",
        )
        db.add(job)
        monitor.next_check_at = slot + timedelta(seconds=monitor.interval_seconds)
        ids.append(job.id)
    await db.flush()
    return ids


def _retry_or_finish(
    project: Project, monitor: Monitor, job: CheckJob, timestamp: datetime, error_code: str
) -> None:
    project.revision += 1
    delay = timedelta(seconds=1 if job.execution_count <= 1 else 2)
    if job.execution_count >= 3:
        _finish_unevaluated(monitor, job, timestamp, "exhausted", error_code)
    elif timestamp + delay + timedelta(milliseconds=job.budget_ms) > job.expires_at:
        _finish_unevaluated(monitor, job, timestamp, "expired", "insufficient_budget")
    else:
        job.status = "pending"
        job.retry_at = timestamp + delay
        job.published_at = None
        job.error_code = error_code
        job.lease_token = None
        job.lease_expires_at = None
        job.started_at = None


async def claim_job(
    db: AsyncSession, job_id: UUID, *, now: datetime | None = None, lease_seconds: int = 90
) -> ClaimedJob | None:
    if not 1 <= lease_seconds <= 90:
        raise ValueError("lease must be 1..90 seconds")
    locked = await _lock_job(db, job_id)
    if locked is None:
        return None
    project, monitor, job = locked
    if job.status not in OPEN:
        return None
    timestamp = await _clock(db, now)
    reason = _invalid(project, monitor, job)
    if reason:
        _finish_unevaluated(
            monitor,
            job,
            timestamp,
            "cancelled",
            reason,
            interrupt=monitor.config_version == job.config_version,
        )
        project.revision += 1
    elif timestamp >= job.expires_at or (
        job.status == "pending"
        and timestamp + timedelta(milliseconds=job.budget_ms) > job.expires_at
    ):
        _finish_unevaluated(monitor, job, timestamp, "expired", "insufficient_budget")
        project.revision += 1
    elif job.status == "running":
        if job.lease_expires_at > timestamp:
            return None
        _retry_or_finish(project, monitor, job, timestamp, "execution_crashed")
    elif job.execution_count >= 3:
        _finish_unevaluated(monitor, job, timestamp, "exhausted", "execution_limit")
        project.revision += 1
    elif job.scheduled_at > timestamp or (job.retry_at is not None and job.retry_at > timestamp):
        return None
    else:
        job.status = "running"
        job.lease_token = uuid4()
        job.lease_expires_at = min(timestamp + timedelta(seconds=lease_seconds), job.expires_at)
        job.execution_count += 1
        job.started_at = timestamp
        job.retry_at = None
        await db.flush()
        return ClaimedJob(
            job.id,
            job.monitor_id,
            job.config_version,
            job.lease_token,
            job.lease_expires_at,
            job.scheduled_at,
            job.expires_at,
            job.budget_ms,
            deepcopy(job.config_snapshot),
            job.started_at,
        )
    await db.flush()
    return None


def _validate_cycle(result: EvaluatedCycle, job: CheckJob, timestamp: datetime) -> None:
    _aware(result.started_at)
    _aware(result.completed_at)
    if not job.started_at <= result.started_at <= result.completed_at <= timestamp:
        raise ValueError(
            "cycle timestamps must follow the current execution and precede finalization"
        )
    if result.completed_at >= job.expires_at:
        raise ValueError("cycle completed after its deadline")
    if result.outcome not in {"success", "failure"}:
        raise ValueError("internal errors must not be submitted as evaluated outcomes")
    if result.http_status is not None and not 200 <= result.http_status <= 599:
        raise ValueError("invalid final HTTP status")
    for value in (result.latency_ms, result.cycle_duration_ms):
        if value is not None and (not isfinite(value) or value < 0):
            raise ValueError("durations must be finite and nonnegative")
    if result.error_code is not None and result.error_code not in TARGET_ERRORS:
        raise ValueError("invalid target error code")
    if result.outcome == "success":
        if (
            result.http_status != job.config_snapshot["expected_status"]
            or result.latency_ms is None
            or result.error_code is not None
        ):
            raise ValueError("success requires expected status, measured latency and no error")
    elif result.error_code is None:
        raise ValueError("evaluated failure requires a sanitized target error")
    if not 1 <= result.attempt_count <= job.config_snapshot["retry_count"] + 1:
        raise ValueError("attempt count exceeds configured retry limit")
    if len(result.attempts) != result.attempt_count:
        raise ValueError("attempt summary length must equal attempt count")
    for attempt in result.attempts:
        if not isinstance(attempt, dict) or set(attempt) - {
            "http_status",
            "error_code",
            "latency_ms",
            "duration_ms",
        }:
            raise ValueError("attempt summaries contain unsupported/private fields")
        if attempt.get("error_code") is not None and attempt["error_code"] not in TARGET_ERRORS:
            raise ValueError("invalid attempt error code")
        if attempt.get("http_status") is not None and not 200 <= attempt["http_status"] <= 599:
            raise ValueError("invalid attempt HTTP status")
        for field in ("latency_ms", "duration_ms"):
            value = attempt.get(field)
            if value is not None and (not isfinite(value) or value < 0):
                raise ValueError("invalid attempt duration")


async def finalize_job(
    db: AsyncSession,
    job_id: UUID,
    lease_token: UUID,
    result: EvaluatedCycle,
    *,
    now: datetime | None = None,
) -> bool:
    """Apply one evaluated sample, state, incident, revision and job in one commit."""
    locked = await _lock_job(db, job_id)
    if locked is None:
        return False
    project, monitor, job = locked
    if job.status != "running" or job.lease_token != lease_token:
        return False
    timestamp = await _clock(db, now)
    reason = _invalid(project, monitor, job)
    if reason:
        _finish_unevaluated(
            monitor,
            job,
            timestamp,
            "cancelled",
            reason,
            interrupt=monitor.config_version == job.config_version,
        )
        project.revision += 1
        await db.flush()
        return False
    if timestamp >= job.expires_at:
        _finish_unevaluated(monitor, job, timestamp, "expired", "deadline_exceeded")
        project.revision += 1
        await db.flush()
        return False
    if timestamp >= job.lease_expires_at:
        return False  # reconciler invalidates and recovers; old worker cannot finalize
    if monitor.last_scheduled_at is not None and job.scheduled_at <= monitor.last_scheduled_at:
        _finish_unevaluated(monitor, job, timestamp, "cancelled", "stale_slot", interrupt=False)
        await db.flush()
        return False
    _validate_cycle(result, job, timestamp)
    incident = await db.scalar(
        select(Incident)
        .where(Incident.monitor_id == monitor.id, Incident.ended_at.is_(None))
        .with_for_update()
    )
    transition = apply_evaluated_cycle(
        HealthState(
            monitor.health_status,
            monitor.consecutive_failures,
            monitor.first_failure_at,
            monitor.last_checked_at,
        ),
        outcome=result.outcome,
        started_at=result.started_at,
        completed_at=result.completed_at,
        failure_threshold=job.config_snapshot["failure_threshold"],
        attempt_count=result.attempt_count,
        latency_ms=result.latency_ms,
        latency_threshold_ms=job.config_snapshot["latency_threshold_ms"],
        incident_is_open=incident is not None,
    )
    check = CheckResult(
        id=uuid4(),
        job_id=job.id,
        monitor_id=monitor.id,
        config_version=job.config_version,
        scheduled_at=job.scheduled_at,
        started_at=result.started_at,
        completed_at=result.completed_at,
        outcome=result.outcome,
        http_status=result.http_status,
        latency_ms=result.latency_ms,
        cycle_duration_ms=result.cycle_duration_ms,
        queue_delay_ms=(result.started_at - job.scheduled_at).total_seconds() * 1000,
        attempt_count=result.attempt_count,
        attempts=deepcopy(result.attempts),
        error_code=result.error_code,
        health_after=transition.state.health_status,
        degradation_reason=transition.degradation_reason,
    )
    db.add(check)
    await db.flush()  # evidence FK references this result before creating the incident
    if transition.open_incident:
        db.add(
            Incident(
                monitor_id=monitor.id,
                started_at=transition.incident_started_at,
                detected_at=transition.incident_detected_at,
                opening_check_id=check.id,
                cause_code=result.error_code,
                failure_threshold_snapshot=job.config_snapshot["failure_threshold"],
            )
        )
    if transition.close_incident:
        incident.ended_at = result.completed_at
        incident.end_reason = "recovered"
        incident.closing_check_id = check.id
    state = transition.state
    monitor.health_status = state.health_status
    monitor.consecutive_failures = state.consecutive_failures
    monitor.first_failure_at = state.first_failure_at
    monitor.last_checked_at = state.last_checked_at
    monitor.last_scheduled_at = job.scheduled_at
    monitor.last_http_status = result.http_status
    monitor.last_latency_ms = result.latency_ms
    monitor.last_outcome = result.outcome
    monitor.last_error_code = result.error_code
    monitor.last_degradation_reason = transition.degradation_reason
    job.status = "completed"
    job.finished_at = result.completed_at
    job.error_code = None
    job.lease_token = None
    job.lease_expires_at = None
    job.retry_at = None
    project.revision += 1
    await db.flush()
    return True


async def record_job_error(
    db: AsyncSession,
    job_id: UUID,
    lease_token: UUID,
    error_code: str,
    *,
    now: datetime | None = None,
) -> bool:
    """Bound technical retries without fabricating an endpoint failure/result."""
    if error_code not in TECHNICAL_ERRORS:
        raise ValueError("technical error must be a supported sanitized code")
    locked = await _lock_job(db, job_id)
    if locked is None:
        return False
    project, monitor, job = locked
    if job.status != "running" or job.lease_token != lease_token:
        return False
    timestamp = await _clock(db, now)
    if timestamp >= job.lease_expires_at:
        return False
    reason = _invalid(project, monitor, job)
    if reason:
        _finish_unevaluated(
            monitor,
            job,
            timestamp,
            "cancelled",
            reason,
            interrupt=monitor.config_version == job.config_version,
        )
        project.revision += 1
    elif timestamp >= job.expires_at:
        _finish_unevaluated(monitor, job, timestamp, "expired", "deadline_exceeded")
        project.revision += 1
    else:
        _retry_or_finish(project, monitor, job, timestamp, error_code)
    await db.flush()
    return True


async def reconcile_jobs(db: AsyncSession, *, now: datetime | None = None, limit: int = 100) -> int:
    """Expire/cancel invalid work and recover expired leases using DB ownership."""
    if not 1 <= limit <= 100:
        raise ValueError("reconciler limit must be 1..100")
    timestamp = await _clock(db, now)
    insufficient = (CheckJob.status == "pending") & (
        CheckJob.expires_at < timestamp + CheckJob.budget_ms * text("INTERVAL '1 millisecond'")
    )
    ids = (
        await db.scalars(
            select(CheckJob.id)
            .join(Monitor)
            .join(Project)
            .where(
                CheckJob.status.in_(OPEN),
                or_(
                    insufficient,
                    CheckJob.expires_at <= timestamp,
                    (CheckJob.status == "running") & (CheckJob.lease_expires_at <= timestamp),
                    (CheckJob.status == "pending") & (CheckJob.execution_count >= 3),
                    Monitor.config_version != CheckJob.config_version,
                    Monitor.paused_at.is_not(None),
                    Monitor.archived_at.is_not(None),
                    Project.archived_at.is_not(None),
                ),
            )
            .order_by(CheckJob.scheduled_at, CheckJob.id)
            .limit(limit)
        )
    ).all()
    changed = 0
    for job_id in ids:
        locked = await _lock_job(db, job_id, skip_locked=True)
        if locked is None:
            continue
        project, monitor, job = locked
        if job.status not in OPEN:
            continue
        current = await _clock(db, now)
        reason = _invalid(project, monitor, job)
        if reason:
            _finish_unevaluated(
                monitor,
                job,
                current,
                "cancelled",
                reason,
                interrupt=monitor.config_version == job.config_version,
            )
            project.revision += 1
        elif current >= job.expires_at or (
            job.status == "pending"
            and current + timedelta(milliseconds=job.budget_ms) > job.expires_at
        ):
            _finish_unevaluated(monitor, job, current, "expired", "insufficient_budget")
            project.revision += 1
        elif job.status == "running" and job.lease_expires_at <= current:
            _retry_or_finish(project, monitor, job, current, "execution_crashed")
        elif job.status == "pending" and job.execution_count >= 3:
            _finish_unevaluated(monitor, job, current, "exhausted", "execution_limit")
            project.revision += 1
        else:
            continue
        changed += 1
        await db.flush()
    return changed
