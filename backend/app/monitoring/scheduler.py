"""Standalone DB scheduler tick; broker publication belongs to the Backend."""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.check_jobs import reconcile_jobs, schedule_due


async def scheduler_tick(factory: async_sessionmaker[AsyncSession]) -> list:
    async with factory.begin() as db:
        await reconcile_jobs(db)
        return await schedule_due(db)


async def run_scheduler(
    factory: async_sessionmaker[AsyncSession], stop: asyncio.Event, *, tick_seconds: float = 1.0
) -> None:
    """Run in one dedicated process, never in API replica startup.

    Database failures propagate to the supervisor; no HTTP/broker I/O is done here.
    """
    if tick_seconds <= 0:
        raise ValueError("tick interval must be positive")
    while not stop.is_set():
        await scheduler_tick(factory)
        try:
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
        except TimeoutError:
            pass
