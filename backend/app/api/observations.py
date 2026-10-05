"""Authenticated observations and explicit public DTOs; no public private data."""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, BeforeValidator, ConfigDict
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import Identity, current_identity
from app.api.errors import ApiError
from app.api.schemas import Page
from app.db.models import CheckResult, Monitor
from app.security import utcnow
from app.services import observations as service
from app.services.resources import owned_monitor, owned_project

router = APIRouter(tags=["observations"])


def require_iso_timestamp(value):
    # Pydantic also accepts numeric epoch strings, silently supplying UTC. The
    # observation API requires ISO input; timezone/window rules stay in service.
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or value.lstrip("+-").replace(".", "", 1).isdigit():
        raise ValueError("Window timestamps must use ISO 8601")
    try:
        datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("Window timestamps must use ISO 8601") from None
    return value


IsoTimestamp = Annotated[datetime, BeforeValidator(require_iso_timestamp)]


async def observation_identity(request: Request) -> Identity:
    # Finish the short auth/activity transaction before acquiring the snapshot
    # connection. Requests must never each hold a connection waiting for another.
    async with request.app.state.session_factory() as session:
        async with session.begin():
            return await current_identity(request, session)


ObservationAuth = Annotated[Identity, Depends(observation_identity)]


@asynccontextmanager
async def observation_session(request: Request):
    # Separate from Auth's activity transaction: all observation reads see the
    # same snapshot without changing isolation/locking of API mutations.
    async with request.app.state.engine.connect() as connection:
        postgres = connection.dialect.name == "postgresql"
        if postgres:
            connection = await connection.execution_options(isolation_level="REPEATABLE READ")
        async with AsyncSession(bind=connection, expire_on_commit=False) as session:
            async with session.begin():
                if postgres:
                    await session.execute(text("SET TRANSACTION READ ONLY"))
                yield session


async def observation_db(request: Request):
    async with observation_session(request) as session:
        yield session


async def private_observation_db(request: Request, auth: ObservationAuth):
    async with observation_session(request) as session:
        yield session


ObservationDB = Annotated[AsyncSession, Depends(private_observation_db, scope="function")]
PublicObservationDB = Annotated[AsyncSession, Depends(observation_db, scope="function")]


class AttemptOut(BaseModel):
    http_status: int | None = None
    error_code: str | None = None
    latency_ms: float | None = None
    duration_ms: float | None = None


class CheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    job_id: UUID
    monitor_id: UUID
    config_version: int
    scheduled_at: datetime
    started_at: datetime
    completed_at: datetime
    outcome: Literal["success", "failure"]
    http_status: int | None
    latency_ms: float | None
    cycle_duration_ms: float
    queue_delay_ms: float
    attempt_count: int
    attempts: list[AttemptOut]
    error_code: str | None
    health_after: Literal["online", "degraded", "offline"]
    degradation_reason: str | None


@router.get("/monitors/{monitor_id}/checks", response_model=Page[CheckOut])
async def checks(
    monitor_id: UUID,
    db: ObservationDB,
    auth: ObservationAuth,
    period: Literal["24h", "7d", "30d"] = "24h",
    from_: IsoTimestamp | None = Query(None, alias="from"),
    to: IsoTimestamp | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    await owned_monitor(db, auth.user.id, monitor_id)
    window = service.observation_window(period, from_, to)
    filters = (
        CheckResult.monitor_id == monitor_id,
        CheckResult.scheduled_at >= window.start,
        CheckResult.scheduled_at < window.end,
    )
    total = await db.scalar(select(func.count()).select_from(CheckResult).where(*filters))
    rows = (
        await db.scalars(
            select(CheckResult)
            .where(*filters)
            .order_by(CheckResult.scheduled_at.desc(), CheckResult.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return Page[CheckOut](items=[CheckOut.model_validate(row) for row in rows], total=total)


@router.get("/monitors/{monitor_id}/metrics")
async def monitor_metrics(
    monitor_id: UUID,
    db: ObservationDB,
    auth: ObservationAuth,
    period: Literal["24h", "7d", "30d"] = "24h",
    from_: IsoTimestamp | None = Query(None, alias="from"),
    to: IsoTimestamp | None = None,
):
    _, monitor = await owned_monitor(db, auth.user.id, monitor_id)
    return await service.metrics(db, [monitor], service.observation_window(period, from_, to))


@router.get("/projects/{project_id}/metrics")
async def project_metrics(
    project_id: UUID,
    db: ObservationDB,
    auth: ObservationAuth,
    period: Literal["24h", "7d", "30d"] = "24h",
    from_: IsoTimestamp | None = Query(None, alias="from"),
    to: IsoTimestamp | None = None,
):
    await owned_project(db, auth.user.id, project_id)
    monitors = (
        await db.scalars(
            select(Monitor).where(Monitor.project_id == project_id, Monitor.archived_at.is_(None))
        )
    ).all()
    return await service.metrics(db, monitors, service.observation_window(period, from_, to))


def _incident(row, *, public: bool) -> dict:
    incident, name = row
    value = {
        "id": incident.id,
        "monitor_id": incident.monitor_id,
        "monitor_name": name,
        "started_at": incident.started_at,
        "detected_at": incident.detected_at,
        "ended_at": incident.ended_at,
        "end_reason": incident.end_reason,
    }
    if not public:
        value.update(
            cause_code=incident.cause_code,
            failure_threshold_snapshot=incident.failure_threshold_snapshot,
            opening_check_id=incident.opening_check_id,
            closing_check_id=incident.closing_check_id,
        )
    return value


@router.get("/projects/{project_id}/incidents")
async def incidents(
    project_id: UUID,
    db: ObservationDB,
    auth: ObservationAuth,
    monitor_id: UUID | None = None,
    state: Literal["all", "open", "closed"] = "all",
    period: Literal["24h", "7d", "30d", "90d"] = "30d",
    from_: IsoTimestamp | None = Query(None, alias="from"),
    to: IsoTimestamp | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    await owned_project(db, auth.user.id, project_id)
    if monitor_id is not None:
        _, monitor = await owned_monitor(db, auth.user.id, monitor_id)
        if monitor.project_id != project_id:
            raise ApiError(404, "not_found", "Monitor not found in this project")
    rows, total = await service.incident_page(
        db,
        project_id,
        service.observation_window(period, from_, to, retention_days=90),
        monitor_id=monitor_id,
        state=state,
        public=False,
        limit=limit,
        offset=offset,
    )
    return {"items": [_incident(row, public=False) for row in rows], "total": total}


@router.get("/public/status/{slug}")
async def public_status(slug: str, db: PublicObservationDB):
    project, monitors = await service.published_project(db, slug)
    now = utcnow()
    summary = service.health_summary(monitors, now)
    # This whitelist deliberately excludes private description, URL and check config.
    items = [
        {
            "id": m.id,
            "name": m.name,
            "health_status": m.health_status,
            "freshness": service.monitor_freshness(m, now),
            "last_checked_at": m.last_checked_at,
        }
        for m in monitors
    ]
    return {
        "name": project.name,
        "slug": project.public_slug,
        "revision": project.revision,
        "computed_at": now,
        **summary,
        "monitors": items,
    }


@router.get("/public/status/{slug}/incidents")
async def public_incidents(
    slug: str,
    db: PublicObservationDB,
    state: Literal["all", "open", "closed"] = "all",
    period: Literal["24h", "7d", "30d", "90d"] = "30d",
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    project, _ = await service.published_project(db, slug)
    rows, total = await service.incident_page(
        db,
        project.id,
        service.observation_window(period, None, None, retention_days=90),
        monitor_id=None,
        state=state,
        public=True,
        limit=limit,
        offset=offset,
    )
    return {"items": [_incident(row, public=True) for row in rows], "total": total}
