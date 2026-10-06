"""Dedicated scheduler/publication process (explicitly gated pending real Redis proof)."""

import asyncio

from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff

from app.db.session import create_engine, create_session_factory
from app.monitoring.heartbeat import scheduler_key, write_scheduler_tick
from app.monitoring.publisher import scheduler_publisher_loop
from app.monitoring.tasks import broker, check_task, settings
from app.observability import configure_activity_logging


async def main():
    if not settings.pipeline_enabled:
        raise RuntimeError(
            "Pipeline disabled: complete the real Redis ACK/reclaim experiment first"
        )
    configure_activity_logging()
    engine = create_engine(settings.database_url, **settings.database_options)
    factory = create_session_factory(engine)
    await broker.startup()
    try:

        async def publish(job_id):
            await check_task.kiq(job_id, envelope_version=1)

        async with Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=1,
            socket_timeout=1,
            max_connections=2,
            retry=Retry(NoBackoff(), 0),
        ) as redis:
            key = scheduler_key(settings.redis_stream_name, settings.redis_consumer_group)

            async def heartbeat(**observation):
                await write_scheduler_tick(redis, key, **observation)

            await scheduler_publisher_loop(factory, publish, asyncio.Event(), heartbeat=heartbeat)
    finally:
        await broker.shutdown()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
