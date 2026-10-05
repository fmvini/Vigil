"""Dedicated scheduler/publication process (explicitly gated pending real Redis proof)."""

import asyncio

from app.db.session import create_engine, create_session_factory
from app.monitoring.publisher import scheduler_publisher_loop
from app.monitoring.tasks import broker, check_task, settings
from app.observability import configure_activity_logging


async def main():
    if not settings.pipeline_enabled:
        raise RuntimeError(
            "Pipeline disabled: complete the real Redis ACK/reclaim experiment first"
        )
    configure_activity_logging()
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)
    await broker.startup()
    try:

        async def publish(job_id):
            await check_task.kiq(job_id, envelope_version=1)

        await scheduler_publisher_loop(factory, publish, asyncio.Event())
    finally:
        await broker.shutdown()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
