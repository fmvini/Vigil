import json
import logging
from typing import Annotated
from uuid import UUID

from redis.asyncio import Redis
from taskiq import Context, TaskiqDepends, TaskiqEvents, TaskiqState

from app.config import Settings
from app.db.session import create_engine, create_session_factory
from app.monitoring.broker import create_broker
from app.monitoring.executor import CheckExecutor
from app.monitoring.worker import process_job

settings = Settings()
broker = create_broker(settings)
logger = logging.getLogger(__name__)


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def startup(state: TaskiqState):
    if not settings.pipeline_enabled or not settings.monitoring_network_enabled:
        raise RuntimeError(
            "Pipeline/network disabled; complete real Redis and egress validation first"
        )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    state.engine = create_engine(settings.database_url)
    state.factory = create_session_factory(state.engine)
    state.executor = CheckExecutor()
    state.redis = Redis.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=3)


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def shutdown(state: TaskiqState):
    if hasattr(state, "engine"):
        await state.engine.dispose()
    if hasattr(state, "redis"):
        await state.redis.aclose()


@broker.task(task_name="vigil.check", ack_type="manual")
async def check_task(
    job_id: str, context: Annotated[Context, TaskiqDepends()], envelope_version: int = 1
):
    try:
        identifier = UUID(job_id)
        if envelope_version != 1:
            raise ValueError("unsupported envelope")
    except (ValueError, TypeError, AttributeError):
        logger.warning("invalid_job_envelope")
        await context.ack()
        return

    async def signal(event):
        await context.state.redis.publish("vigil:updates", json.dumps(event))

    try:
        should_ack = await process_job(
            context.state.factory, context.state.executor, identifier, signal=signal
        )
    except Exception:
        # No ACK for failed claim/finalize/commit; never log SQL params or remote errors.
        logger.warning("job_persistence_failed", extra={"job_id": str(identifier)})
        return
    if should_ack:
        await context.ack()
