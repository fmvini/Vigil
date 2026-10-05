"""Read-only projection of terminal operational jobs; never load check configuration."""

from typing import Literal, get_args
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CheckJob, Monitor
from app.services.observations import Window

JobSelection = Literal["all", "exhausted", "expired"]
OperationalCode = Literal[
    "internal_error",
    "execution_crashed",
    "pool_exhausted",
    "blocked_destination",
    "database_error",
    "insufficient_budget",
    "deadline_exceeded",
    "execution_limit",
]
OPERATIONAL_CODES = frozenset(get_args(OperationalCode))


async def job_page(
    db: AsyncSession,
    project_id: UUID,
    window: Window,
    *,
    status: JobSelection,
    monitor_id: UUID | None,
    limit: int,
    offset: int,
):
    # Authorization and count/page all run in the caller's observation snapshot.
    statuses = ("exhausted", "expired") if status == "all" else (status,)
    conditions = [
        Monitor.project_id == project_id,
        Monitor.archived_at.is_(None),
        CheckJob.status.in_(statuses),
        CheckJob.scheduled_at >= window.start,
        CheckJob.scheduled_at < window.end,
    ]
    if monitor_id is not None:
        conditions.append(CheckJob.monitor_id == monitor_id)
    total = await db.scalar(
        select(func.count()).select_from(CheckJob).join(Monitor).where(*conditions)
    )
    rows = (
        await db.execute(
            select(
                CheckJob.id.label("job_id"),
                CheckJob.monitor_id,
                CheckJob.config_version,
                CheckJob.status,
                CheckJob.scheduled_at,
                CheckJob.finished_at,
                CheckJob.execution_count,
                CheckJob.error_code,
            )
            .join(Monitor)
            .where(*conditions)
            .order_by(CheckJob.scheduled_at.desc(), CheckJob.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return rows, total
