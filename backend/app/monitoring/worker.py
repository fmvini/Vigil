"""Claim/execute/finalize with short transactions; caller ACKs only after return."""

import asyncio
import logging
import time
from uuid import UUID

from sqlalchemy import select

from app.db.models import Monitor, Project
from app.monitoring.executor import OperationalError
from app.observability import activity
from app.services.check_jobs import claim_job, finalize_job, record_job_error


async def process_job(factory, executor, job_id: UUID, *, signal=None) -> bool:
    started = time.monotonic()
    async with factory.begin() as db:
        claimed = await claim_job(db, job_id)
    # This commit precedes HTTP. No session/row lock is retained while awaiting the target.
    if claimed is None:
        activity("job_not_claimed", component="worker", job_id=job_id)
        return True  # terminal, missing, occupied or not eligible; DB reconciler is authoritative.
    activity(
        "job_claimed",
        component="worker",
        job_id=job_id,
        monitor_id=claimed.monitor_id,
        start_delay_ms=max(0, (claimed.started_at - claimed.scheduled_at).total_seconds() * 1000),
    )
    error = None
    try:
        result = await executor.run(claimed)
    except OperationalError as exc:
        error = exc.code
    except asyncio.CancelledError:
        activity("job_cancelled", component="worker", job_id=job_id, monitor_id=claimed.monitor_id)
        raise  # retain unacked delivery and durable lease for recovery
    except Exception:
        error = "internal_error"
    async with factory.begin() as db:
        if error is None:
            applied = await finalize_job(db, job_id, claimed.lease_token, result)
        else:
            applied = await record_job_error(db, job_id, claimed.lease_token, error)
        event = None
        if applied:
            record = (
                await db.execute(
                    select(Project.id, Project.owner_id, Project.revision)
                    .join(Monitor, Monitor.project_id == Project.id)
                    .where(Monitor.id == claimed.monitor_id)
                )
            ).one()
            event = {
                "type": "monitor.updated",
                "monitor_id": str(claimed.monitor_id),
                "project_id": str(record.id),
                "owner_id": str(record.owner_id),
                "revision": record.revision,
            }
    # PostgreSQL is committed now; logs/signals must not imply application before this point.
    activity(
        "job_finalized" if applied else "job_state_not_applied",
        component="worker",
        job_id=job_id,
        monitor_id=claimed.monitor_id,
        outcome="operational_error" if error is not None else result.outcome,
        error_code=error if error is not None else result.error_code,
        attempt_count=None if error is not None else result.attempt_count,
        duration_ms=(time.monotonic() - started) * 1000,
    )
    if signal is not None and event is not None:
        try:
            await signal(event)
        except Exception:
            activity(
                "signal_failed_after_commit",
                level=logging.WARNING,
                component="worker",
                job_id=job_id,
                monitor_id=claimed.monitor_id,
            )
    return True
