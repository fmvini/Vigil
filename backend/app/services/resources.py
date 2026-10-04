import secrets
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.api.schemas import MonitorCreate, MonitorOut
from app.db.models import CheckJob, Incident, Monitor, Project, User
from app.domain.health import freshness
from app.domain.monitors import CHECK_FIELDS
from app.security import aware, utcnow


def queue_invalidation(db, project, monitor=None):
    event = {
        "type": "monitor.updated" if monitor else "project.updated",
        "owner_id": str(project.owner_id),
        "project_id": str(project.id),
        "revision": project.revision,
    }
    if monitor:
        event["monitor_id"] = str(monitor.id)
    db.info.setdefault("events", []).append(event)


async def owned_project(
    db: AsyncSession, owner_id: UUID, project_id: UUID, *, lock=False, include_archived=False
) -> Project:
    statement = select(Project).where(Project.id == project_id, Project.owner_id == owner_id)
    if not include_archived:
        statement = statement.where(Project.archived_at.is_(None))
    if lock:
        statement = statement.with_for_update()
    project = await db.scalar(statement.execution_options(populate_existing=True))
    if project is None:
        raise ApiError(404, "not_found", "Project not found")
    return project


async def owned_monitor(
    db: AsyncSession, owner_id: UUID, monitor_id: UUID, *, lock=False, include_archived=False
) -> tuple[Project, Monitor]:
    # Resolve ownership first without locking; then obey Project -> Monitor lock order.
    project_id = await db.scalar(
        select(Monitor.project_id)
        .join(Project)
        .where(Monitor.id == monitor_id, Project.owner_id == owner_id)
    )
    if project_id is None:
        raise ApiError(404, "not_found", "Monitor not found")
    project = await owned_project(
        db, owner_id, project_id, lock=lock, include_archived=include_archived
    )
    statement = select(Monitor).where(Monitor.id == monitor_id, Monitor.project_id == project.id)
    if not include_archived:
        statement = statement.where(Monitor.archived_at.is_(None))
    if lock:
        statement = statement.with_for_update()
    monitor = await db.scalar(statement.execution_options(populate_existing=True))
    if monitor is None:
        raise ApiError(404, "not_found", "Monitor not found")
    return project, monitor


async def lock_owner(db: AsyncSession, owner_id: UUID) -> None:
    # All resource creations lock the owner BEFORE checking quotas or locking projects.
    owner = await db.scalar(select(User).where(User.id == owner_id).with_for_update())
    if owner is None or not owner.is_active:
        raise ApiError(401, "unauthenticated", "Authentication required")


async def create_project(db: AsyncSession, owner_id: UUID, data) -> Project:
    await lock_owner(db, owner_id)
    count = await db.scalar(
        select(func.count())
        .select_from(Project)
        .where(Project.owner_id == owner_id, Project.archived_at.is_(None))
    )
    if count >= 5:
        raise ApiError(409, "quota_exceeded", "Limit of 5 active projects reached")
    project = Project(
        owner_id=owner_id, public_slug="project-" + secrets.token_hex(16), **data.model_dump()
    )
    db.add(project)
    await db.flush()
    queue_invalidation(db, project)
    return project


async def create_monitor(db: AsyncSession, owner_id: UUID, project_id: UUID, data) -> Monitor:
    await lock_owner(db, owner_id)
    project = await owned_project(db, owner_id, project_id, lock=True)
    count = await db.scalar(
        select(func.count())
        .select_from(Monitor)
        .where(Monitor.project_id == project_id, Monitor.archived_at.is_(None))
    )
    owner_count = await db.scalar(
        select(func.count())
        .select_from(Monitor)
        .join(Project)
        .where(
            Project.owner_id == owner_id,
            Project.archived_at.is_(None),
            Monitor.archived_at.is_(None),
        )
    )
    if count >= 20 or owner_count >= 100:
        raise ApiError(409, "quota_exceeded", "Active monitor quota reached")
    monitor = Monitor(project_id=project_id, next_check_at=utcnow(), **data.model_dump())
    db.add(monitor)
    project.revision += 1
    await db.flush()
    await db.refresh(monitor)
    queue_invalidation(db, project, monitor)
    return monitor


async def cancel_jobs(db: AsyncSession, monitor: Monitor, now) -> None:
    await db.execute(
        update(CheckJob)
        .where(CheckJob.monitor_id == monitor.id, CheckJob.status.in_(["pending", "running"]))
        .values(
            status="cancelled",
            finished_at=now,
            lease_token=None,
            lease_expires_at=None,
            error_code="administrative_change",
        )
    )


async def close_incidents(db: AsyncSession, monitor: Monitor, now, reason: str) -> None:
    await db.execute(
        update(Incident)
        .where(Incident.monitor_id == monitor.id, Incident.ended_at.is_(None))
        .values(ended_at=now, end_reason=reason)
    )


def reset_sequence(monitor: Monitor) -> None:
    monitor.consecutive_failures = 0
    monitor.first_failure_at = None


def reset_snapshot(monitor: Monitor) -> None:
    reset_sequence(monitor)
    for field in (
        "health_status",
        "last_checked_at",
        "last_scheduled_at",
        "last_http_status",
        "last_latency_ms",
        "last_outcome",
        "last_error_code",
        "last_degradation_reason",
    ):
        setattr(monitor, field, None)


async def patch_monitor(db: AsyncSession, project: Project, monitor: Monitor, data) -> Monitor:
    changes = data.model_dump(exclude_unset=True)
    merged = {field: getattr(monitor, field) for field in MonitorCreate.model_fields}
    merged.update(changes)
    try:
        checked = MonitorCreate.model_validate(merged)
    except ValidationError as exc:
        details = [
            {"field": ".".join(str(v) for v in e["loc"]), "type": e["type"]} for e in exc.errors()
        ]
        raise ApiError(422, "validation_error", "Invalid monitor configuration", details) from None
    changes = {field: getattr(checked, field) for field in changes}
    changed = {field for field, value in changes.items() if getattr(monitor, field) != value}
    if not changed:
        return monitor
    now = utcnow()
    if changed & CHECK_FIELDS:
        monitor.config_version += 1
        await cancel_jobs(db, monitor, now)
        await close_incidents(db, monitor, now, "configuration_changed")
        reset_snapshot(monitor)
        monitor.next_check_at = now if monitor.paused_at is None else None
    for field, value in changes.items():
        setattr(monitor, field, value)
    project.revision += 1
    await db.flush()
    await db.refresh(monitor)
    queue_invalidation(db, project, monitor)
    return monitor


async def archive_monitor(db: AsyncSession, project: Project, monitor: Monitor) -> None:
    if monitor.archived_at is not None:
        return
    now = utcnow()
    monitor.archived_at = now
    monitor.next_check_at = None
    monitor.is_public = False
    monitor.config_version += 1
    reset_sequence(monitor)
    await cancel_jobs(db, monitor, now)
    await close_incidents(db, monitor, now, "archived")
    project.revision += 1

    queue_invalidation(db, project, monitor)


async def archive_project(db: AsyncSession, project: Project) -> None:
    if project.archived_at is not None:
        return
    monitors = (
        await db.scalars(
            select(Monitor)
            .where(Monitor.project_id == project.id, Monitor.archived_at.is_(None))
            .order_by(Monitor.id)
            .with_for_update()
        )
    ).all()
    for monitor in monitors:
        await archive_monitor(db, project, monitor)
    project.archived_at = utcnow()
    project.public_status_enabled = False
    project.revision += 1
    queue_invalidation(db, project)


async def set_paused(db: AsyncSession, project: Project, monitor: Monitor, paused: bool) -> Monitor:
    if (monitor.paused_at is not None) == paused:
        return monitor
    now = utcnow()
    monitor.config_version += 1
    monitor.paused_at = now if paused else None
    monitor.next_check_at = None if paused else now
    reset_sequence(monitor)
    await cancel_jobs(db, monitor, now)
    project.revision += 1
    await db.flush()
    await db.refresh(monitor)
    queue_invalidation(db, project, monitor)
    return monitor


def monitor_output(monitor: Monitor) -> MonitorOut:
    result = MonitorOut.model_validate(monitor)
    result.is_paused = monitor.paused_at is not None
    result.freshness = freshness(
        now=utcnow(),
        interval_seconds=monitor.interval_seconds,
        last_checked_at=aware(monitor.last_checked_at) if monitor.last_checked_at else None,
        paused=result.is_paused,
    )
    return result
