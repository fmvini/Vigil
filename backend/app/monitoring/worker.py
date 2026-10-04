"""Claim/execute/finalize with short transactions; caller ACKs only after return."""

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select

from app.db.models import Monitor, Project
from app.monitoring.executor import OperationalError
from app.services.check_jobs import claim_job, finalize_job, record_job_error

logger = logging.getLogger(__name__)


async def process_job(factory, executor, job_id: UUID, *, signal=None) -> bool:
    async with factory.begin() as db:
        claimed = await claim_job(db, job_id)
    # This commit precedes HTTP. No session/row lock is retained while awaiting the target.
    if claimed is None:
        return True  # terminal, missing, occupied or not eligible; DB reconciler is authoritative.
    error = None
    try:
        result = await executor.run(claimed)
    except OperationalError as exc:
        error = exc.code
    except asyncio.CancelledError:
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
    # PostgreSQL is committed now; Pub/Sub failure cannot undo state or force another GET.
    if signal is not None and event is not None:
        try:
            await signal(event)
        except Exception:
            logger.warning("signal_failed_after_commit", extra={"job_id": str(job_id)})
    return True
