"""Bounded PostgreSQL retention; run separately from scheduler/API startup.

``retain_batch`` requires a caller-owned transaction and never commits it.
Only terminal history and sessions invalid for more than seven days are removed.
"""

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, exists, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import NullPool

from app.db.models import CheckJob, CheckResult, Incident, Session
from app.db.session import create_engine, create_session_factory

TERMINAL_JOBS = ("completed", "expired", "cancelled", "exhausted")
MAX_BATCH_SIZE = 1000
MAX_BATCHES = 1000


@dataclass(frozen=True)
class RetentionCounts:
    computed_at: datetime
    check_results: int = 0
    check_jobs: int = 0
    incidents: int = 0
    sessions: int = 0

    @property
    def total(self) -> int:
        return self.check_results + self.check_jobs + self.incidents + self.sessions


def _validate_limits(batch_size: int, session_idle_seconds: int) -> None:
    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or not 1 <= batch_size <= MAX_BATCH_SIZE
    ):
        raise ValueError(f"batch_size must be an integer from 1 to {MAX_BATCH_SIZE}")
    if (
        isinstance(session_idle_seconds, bool)
        or not isinstance(session_idle_seconds, int)
        or not 60 <= session_idle_seconds <= 86400
    ):
        raise ValueError("session_idle_seconds must be an integer from 60 to 86400")


async def _delete_batch(
    db: AsyncSession, model: Any, eligible: Any, ordering: Any, batch_size: int
) -> int:
    ids = (
        await db.scalars(
            select(model.id)
            .where(eligible)
            .order_by(ordering, model.id)
            .limit(batch_size)
            .with_for_update(of=model, skip_locked=True)
        )
    ).all()
    if not ids:
        return 0
    # A new READ COMMITTED snapshot rechecks child references after parent locks.
    deleted = (
        await db.scalars(
            delete(model)
            .where(model.id.in_(ids), eligible)
            .returning(model.id)
            .execution_options(synchronize_session=False)
        )
    ).all()
    return len(deleted)


async def _delete_results(db: AsyncSession, cutoff: datetime, batch_size: int) -> int:
    terminal_job = exists(
        select(CheckJob.id).where(
            CheckJob.id == CheckResult.job_id, CheckJob.status.in_(TERMINAL_JOBS)
        )
    )
    eligible = (CheckResult.completed_at < cutoff) & terminal_job
    ids = (
        await db.scalars(
            select(CheckResult.id)
            .where(eligible)
            .order_by(CheckResult.completed_at, CheckResult.id)
            .limit(batch_size)
            .with_for_update(of=CheckResult, skip_locked=True)
        )
    ).all()
    if not ids:
        return 0

    references = or_(Incident.opening_check_id.in_(ids), Incident.closing_check_id.in_(ids))
    # SET NULL updates evidence rows. Acquire those locks without waiting for an
    # administrative edit/finalization. A bounded fanout also covers malformed
    # history: any reference we cannot lock makes that result ineligible this pass.
    evidence_ids = (
        await db.scalars(
            select(Incident.id)
            .where(references)
            .order_by(Incident.id)
            .limit(2 * batch_size)
            .with_for_update(of=Incident, skip_locked=True)
        )
    ).all()
    unowned_reference = exists(
        select(Incident.id).where(
            or_(
                Incident.opening_check_id == CheckResult.id,
                Incident.closing_check_id == CheckResult.id,
            ),
            Incident.id.not_in(evidence_ids),
        )
    )
    deleted = (
        await db.scalars(
            delete(CheckResult)
            .where(CheckResult.id.in_(ids), eligible, ~unowned_reference)
            .returning(CheckResult.id)
            .execution_options(synchronize_session=False)
        )
    ).all()
    return len(deleted)


async def retain_batch(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    batch_size: int = 100,
    session_idle_seconds: int = 86400,
) -> RetentionCounts:
    """Delete at most ``batch_size`` rows per entity, skipping occupied rows.

    TTL starts at result completion, job finish, incident closure, or the first
    session invalidation (absolute expiry/revocation/last activity + idle limit).
    Exact cutoff rows remain until they are strictly older than the retention.
    ``now`` is an aware test clock; production uses PostgreSQL clock_timestamp.
    Monitor snapshots and active jobs stay untouched. Open incidents are retained;
    only their evidence foreign keys may become NULL during result cleanup.
    """
    _validate_limits(batch_size, session_idle_seconds)
    if db.get_bind().dialect.name != "postgresql":
        raise ValueError("retention requires real PostgreSQL")
    if not db.in_transaction():
        raise ValueError("retain_batch requires a caller-owned transaction (factory.begin())")
    if now is None:
        now = await db.scalar(select(func.clock_timestamp()))
    elif now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("retention timestamp must be timezone-aware")

    history_cutoff = now - timedelta(days=30)
    incident_cutoff = now - timedelta(days=90)
    session_cutoff = now - timedelta(days=7)
    results = await _delete_results(db, history_cutoff, batch_size)
    no_result = ~exists(select(CheckResult.id).where(CheckResult.job_id == CheckJob.id))
    jobs = await _delete_batch(
        db,
        CheckJob,
        CheckJob.status.in_(TERMINAL_JOBS) & (CheckJob.finished_at < history_cutoff) & no_result,
        CheckJob.finished_at,
        batch_size,
    )
    incidents = await _delete_batch(
        db,
        Incident,
        Incident.ended_at < incident_cutoff,
        Incident.ended_at,
        batch_size,
    )
    sessions = await _delete_batch(
        db,
        Session,
        or_(
            Session.expires_at < session_cutoff,
            Session.revoked_at < session_cutoff,
            Session.last_seen_at < session_cutoff - timedelta(seconds=session_idle_seconds),
        ),
        Session.created_at,
        batch_size,
    )
    return RetentionCounts(now, results, jobs, incidents, sessions)


async def _run_cli(args: argparse.Namespace, settings: Any) -> list[RetentionCounts]:
    engine = create_engine(settings.database_url, poolclass=NullPool, **settings.database_options)
    batches = []
    try:
        factory = create_session_factory(engine)
        for _ in range(args.max_batches):
            async with factory.begin() as db:
                # SKIP LOCKED avoids row waits. Timeouts also bound relation locks
                # and foreign-key maintenance under unexpected concurrent writes.
                await db.execute(text("SET LOCAL lock_timeout = '1s'"))
                await db.execute(text("SET LOCAL statement_timeout = '10s'"))
                counts = await retain_batch(
                    db,
                    batch_size=args.batch_size,
                    session_idle_seconds=settings.session_idle_seconds,
                )
                if args.dry_run:
                    await db.rollback()
            batches.append(counts)
            if counts.total == 0 or args.dry_run:
                break
    finally:
        await engine.dispose()
    return batches


def _bounded_integer(maximum: int):
    def parse(value: str) -> int:
        try:
            number = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError("value must be an integer") from None
        if not 1 <= number <= maximum:
            raise argparse.ArgumentTypeError(f"value must be from 1 to {maximum}")
        return number

    return parse


def main(argv: list[str] | None = None) -> int:
    """CLI: python -m app.services.retention run-retention [--dry-run]."""
    parser = argparse.ArgumentParser(description="Bounded PostgreSQL history retention")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("run-retention")
    command.add_argument("--batch-size", type=_bounded_integer(MAX_BATCH_SIZE), default=100)
    command.add_argument("--max-batches", type=_bounded_integer(MAX_BATCHES), default=1)
    command.add_argument(
        "--dry-run", action="store_true", help="Execute one batch and roll back all changes"
    )
    args = parser.parse_args(argv)
    from app.config import Settings

    try:
        settings = Settings()
        if "database_url" not in settings.model_fields_set:
            parser.error("Set an explicit VIGIL_DATABASE_URL (environment or .env)")
        batches = asyncio.run(_run_cli(args, settings))
    except Exception as error:
        # Do not emit SQL/connection parameters or credentials from DB exceptions.
        print(
            f"Retention failed: {type(error).__name__}; current batch rolled back", file=sys.stderr
        )
        return 1
    totals = {
        key: sum(getattr(batch, key) for batch in batches)
        for key in ("check_results", "check_jobs", "incidents", "sessions")
    }
    print(
        json.dumps(
            {
                "committed": not args.dry_run,
                "batches": len(batches),
                "totals": totals,
                "last_batch": asdict(batches[-1]),
            },
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
