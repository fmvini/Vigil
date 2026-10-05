import asyncio
import logging
import time
from datetime import timedelta

from sqlalchemy import func, or_, select, update

from app.db.models import CheckJob
from app.monitoring.scheduler import scheduler_tick
from app.observability import activity


async def publish_pending(factory, publish, *, now=None, limit=100) -> int:
    if not 1 <= limit <= 100:
        raise ValueError("publication limit must be 1..100")
    async with factory.begin() as db:
        timestamp = now or await db.scalar(select(func.clock_timestamp()))
        jobs = (
            await db.execute(
                select(
                    CheckJob.id,
                    CheckJob.config_version,
                    CheckJob.execution_count,
                    CheckJob.retry_at,
                )
                .where(
                    CheckJob.status == "pending",
                    CheckJob.scheduled_at <= timestamp,
                    CheckJob.expires_at > timestamp,
                    or_(CheckJob.retry_at.is_(None), CheckJob.retry_at <= timestamp),
                    or_(
                        CheckJob.published_at.is_(None),
                        CheckJob.published_at <= timestamp - timedelta(seconds=30),
                    ),
                )
                .order_by(CheckJob.scheduled_at, CheckJob.id)
                .limit(limit)
            )
        ).all()
    published = 0
    for identifier, version, execution_count, retry_at in jobs:
        # No transaction while publishing; crash between send and mark can duplicate delivery.
        await publish(str(identifier))
        async with factory.begin() as db:
            await db.execute(
                update(CheckJob)
                .where(
                    CheckJob.id == identifier,
                    CheckJob.config_version == version,
                    CheckJob.status == "pending",
                    CheckJob.execution_count == execution_count,
                    CheckJob.retry_at == retry_at,
                )
                .values(published_at=timestamp)
            )
        published += 1
    return published


async def scheduler_publisher_loop(factory, publish, stop: asyncio.Event, *, tick_seconds=1.0):
    if tick_seconds <= 0:
        raise ValueError("tick interval must be positive")
    while not stop.is_set():
        started = time.monotonic()
        try:
            scheduled = await scheduler_tick(factory)
            published = await publish_pending(factory, publish)
            activity(
                "scheduler_tick",
                component="scheduler",
                scheduled_count=len(scheduled),
                published_count=published,
                duration_ms=(time.monotonic() - started) * 1000,
            )
        except Exception:
            activity(
                "scheduler_tick_failed",
                level=logging.WARNING,
                component="scheduler",
                duration_ms=(time.monotonic() - started) * 1000,
            )
        try:
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
        except TimeoutError:
            pass
