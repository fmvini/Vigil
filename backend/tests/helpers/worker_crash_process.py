"""Killable test-only Receiver: real PG/Redis, synthetic executor, no HTTP.

Never start the production worker or change runtime gates. The shortened lease
is an explicit supported claim_job parameter in this process only.
"""

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from redis.asyncio import Redis  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from taskiq.acks import AckableMessage  # noqa: E402
from taskiq.receiver import Receiver  # noqa: E402

from app.config import Settings  # noqa: E402
from app.db.models import CheckJob  # noqa: E402
from app.db.session import create_engine, create_session_factory  # noqa: E402
from app.monitoring import worker  # noqa: E402
from app.monitoring.broker import create_broker  # noqa: E402
from app.monitoring.tasks import check_task  # noqa: E402
from app.services.check_jobs import EvaluatedCycle  # noqa: E402


def checkpoint(name, **data):
    print(json.dumps({"checkpoint": name, **data}), flush=True)


async def run(args):
    assert re.fullmatch(r"vigil_test_[a-f0-9]{32}", args.schema)
    assert re.fullmatch(r"vigil:worker-crash:[a-f0-9]{32}", args.stream)
    assert re.fullmatch(r"group-[a-f0-9]{32}", args.group)
    identifier = UUID(args.job_id)
    settings = Settings(_env_file=None)
    assert not settings.pipeline_enabled and not settings.monitoring_network_enabled
    engine = create_engine(
        os.environ["VIGIL_TEST_DATABASE_URL"],
        connect_args={
            "server_settings": {
                "search_path": args.schema,
                "timezone": "UTC",
                "statement_timeout": "10000",
                "lock_timeout": "2000",
            }
        },
    )
    factory = create_session_factory(engine)
    redis_url = os.environ["VIGIL_TEST_REDIS_URL"]
    redis = Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=3)
    broker = create_broker(
        Settings(redis_url=redis_url, _env_file=None),
        queue_name=args.stream,
        group_name=args.group,
        idle_timeout=50,
        xread_block=10,
    )
    original_claim, original_finalize = worker.claim_job, worker.finalize_job

    async def short_claim(db, job_id):
        return await original_claim(db, job_id, lease_seconds=args.lease_seconds)

    async def interrupted_finalize(*parameters, **kwargs):
        applied = await original_finalize(*parameters, **kwargs)
        assert applied
        checkpoint("before_commit")
        await asyncio.Event().wait()

    class SyntheticExecutor:
        calls = 0

        async def run(self, claim):
            self.calls += 1
            assert claim.job_id == identifier
            async with factory() as db:
                job = await db.get(CheckJob, identifier)
                assert job.status == "running" and job.lease_token == claim.lease_token
                completed = await db.scalar(select(func.clock_timestamp()))
            checkpoint("after_claim", lease_token=str(claim.lease_token))
            if args.phase == "after_claim":
                await asyncio.Event().wait()
            return EvaluatedCycle(
                claim.started_at,
                completed,
                "failure",
                None,
                None,
                10.0,
                1,
                [{"error_code": "timeout", "duration_ms": 10.0}],
                "timeout",
            )

    class Signals:
        async def publish(self, channel, payload):
            assert channel == "vigil:updates"
            if args.phase == "after_commit":
                checkpoint("after_commit")
                await asyncio.Event().wait()
            return await redis.publish(channel, payload)

    executor = SyntheticExecutor()
    worker.claim_job = short_claim
    if args.phase == "before_commit":
        worker.finalize_job = interrupted_finalize
    broker.register_task(check_task.original_func, task_name="vigil.check", ack_type="manual")
    broker.state.factory, broker.state.executor, broker.state.redis = factory, executor, Signals()
    listener = None
    acknowledged = 0
    try:
        await broker.startup()
        listener = broker.listen()
        for _ in range(args.messages):
            message = await asyncio.wait_for(anext(listener), 10)
            assert broker.formatter.loads(message.data).args == [str(identifier)]
            checkpoint("after_delivery", consumer=broker.consumer_name)
            if args.phase == "after_delivery":
                await asyncio.Event().wait()

            async def ack():
                nonlocal acknowledged
                await message.ack()
                acknowledged += 1

            await Receiver(broker, max_async_tasks=1).callback(
                AckableMessage(data=message.data, ack=ack), raise_err=True
            )
        assert acknowledged == args.messages
    finally:
        if listener is not None:
            await listener.aclose()
        await broker.shutdown()
        await redis.aclose()
        await engine.dispose()
    checkpoint("done", executor_calls=executor.calls, acknowledgements=acknowledged)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--stream", required=True)
    parser.add_argument("--group", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument(
        "--phase",
        choices=["after_delivery", "after_claim", "before_commit", "after_commit", "complete"],
        required=True,
    )
    parser.add_argument("--lease-seconds", type=int, default=12)
    parser.add_argument("--messages", type=int, default=1)
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except Exception as error:
        checkpoint("error", error_type=type(error).__name__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
