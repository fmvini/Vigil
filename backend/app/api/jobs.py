"""Private history of Vigil processing failures, independent of target health."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.api.errors import ApiError
from app.api.observations import IsoTimestamp, ObservationAuth, ObservationDB
from app.db.models import Monitor
from app.security import aware
from app.services.observations import observation_window
from app.services.operational_jobs import OPERATIONAL_CODES, JobSelection, OperationalCode, job_page
from app.services.resources import owned_project

router = APIRouter(tags=["operational jobs"])


class OperationalJobOut(BaseModel):
    job_id: UUID
    monitor_id: UUID
    config_version: int = Field(ge=1)
    status: Literal["exhausted", "expired"]
    scheduled_at: datetime
    finished_at: datetime  # Terminal job constraints require completion, even without a result.
    execution_count: int = Field(ge=0, le=3)  # Worker claims, not HTTP retry attempts.
    error_code: OperationalCode | None

    @field_validator("scheduled_at", "finished_at")
    @classmethod
    def utc_timestamp(cls, value):
        return aware(value)

    @field_validator("error_code", mode="before")
    @classmethod
    def safe_code(cls, value):
        return value if isinstance(value, str) and value in OPERATIONAL_CODES else None


class OperationalJobsPage(BaseModel):
    items: list[OperationalJobOut]
    total: int = Field(ge=0)
    from_: datetime = Field(serialization_alias="from")
    to: datetime
    computed_at: datetime
    retention_days: Literal[30] = 30


@router.get("/projects/{project_id}/jobs", response_model=OperationalJobsPage)
async def jobs(
    project_id: UUID,
    db: ObservationDB,
    auth: ObservationAuth,
    status: JobSelection = "all",
    monitor_id: UUID | None = None,
    period: Literal["24h", "7d", "30d"] = "24h",
    from_: IsoTimestamp | None = Query(None, alias="from"),
    to: IsoTimestamp | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=2**63 - 1),
):
    await owned_project(db, auth.user.id, project_id)
    if (
        monitor_id is not None
        and await db.scalar(
            select(Monitor.id).where(
                Monitor.id == monitor_id,
                Monitor.project_id == project_id,
                Monitor.archived_at.is_(None),
            )
        )
        is None
    ):
        raise ApiError(404, "not_found", "Monitor not found")
    window = observation_window(period, from_, to)
    rows, total = await job_page(
        db, project_id, window, status=status, monitor_id=monitor_id, limit=limit, offset=offset
    )
    return OperationalJobsPage(
        items=[OperationalJobOut.model_validate(row._mapping) for row in rows],
        total=total,
        from_=window.start,
        to=window.end,
        computed_at=window.computed_at,
    )
