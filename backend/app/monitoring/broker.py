"""Candidate Taskiq Streams adapter: manual ACK and reclaim even on an idle queue.

Runtime startup stays disabled by default until the real Redis experiment passes.
The pinned upstream listen() only reclaims after a nonempty fresh batch.
"""

import logging
from uuid import UUID

from redis.asyncio import Redis
from taskiq.acks import AckableMessage
from taskiq_redis import RedisStreamBroker

from app.config import Settings

logger = logging.getLogger(__name__)


class VigilStreamBroker(RedisStreamBroker):
    def _safe_envelope(self, data):
        if len(data) > 4096:
            raise ValueError("oversized envelope")
        envelope = self.formatter.loads(data)
        if (
            envelope.task_name != "vigil.check"
            or len(envelope.args) != 1
            or set(envelope.kwargs) - {"envelope_version"}
            or type(envelope.kwargs.get("envelope_version", 1)) is not int
            or envelope.kwargs.get("envelope_version", 1) != 1
        ):
            raise ValueError("invalid job envelope")
        envelope.args = [str(UUID(envelope.args[0]))]
        envelope.task_id = str(UUID(envelope.task_id))
        # Receiver labels cannot override manual ACK or inject deserialization work.
        envelope.labels = {"ack_type": "manual"}
        envelope.labels_types = None
        return self.formatter.dumps(envelope).message

    async def _delivery(self, identifier, fields, redis):
        try:
            data = self._safe_envelope(fields[b"data"])
        except Exception:
            logger.warning("invalid_job_envelope_discarded")
            await redis.xack(self.queue_name, self.consumer_group_name, identifier)
            return None
        return self._message(identifier, data)

    def _message(self, identifier, data):
        async def ack():
            async with Redis(connection_pool=self.connection_pool) as redis:
                await redis.xack(self.queue_name, self.consumer_group_name, identifier)

        return AckableMessage(data=data, ack=ack)

    async def listen(self):
        cursor = "0-0"
        async with Redis(connection_pool=self.connection_pool) as redis:
            while True:
                fetched = await redis.xreadgroup(
                    self.consumer_group_name,
                    self.consumer_name,
                    {self.queue_name: ">"},
                    block=self.block,
                    noack=False,
                    count=self.count,
                )
                for _, messages in fetched or []:
                    for identifier, fields in messages:
                        delivery = await self._delivery(identifier, fields, redis)
                        if delivery is not None:
                            yield delivery
                # XAUTOCLAIM is atomic; no application Redis lock can get stranded on crash.
                # The scan cursor progresses through the PEL rather than always restarting.
                pending = await redis.xautoclaim(
                    self.queue_name,
                    self.consumer_group_name,
                    self.consumer_name,
                    min_idle_time=self.idle_timeout,
                    start_id=cursor,
                    count=self.unacknowledged_batch_size,
                )
                cursor = pending[0]
                for identifier, fields in pending[1]:
                    delivery = await self._delivery(identifier, fields, redis)
                    if delivery is not None:
                        yield delivery


def create_broker(
    settings: Settings, *, queue_name=None, group_name=None, idle_timeout=120000, xread_block=1000
):
    return VigilStreamBroker(
        url=settings.redis_url,
        queue_name=queue_name or settings.redis_stream_name,
        consumer_group_name=group_name or settings.redis_consumer_group,
        consumer_id="0-0",
        maxlen=None,
        idle_timeout=idle_timeout,
        xread_count=50,
        xread_block=xread_block,
        unacknowledged_batch_size=100,
        max_connection_pool_size=60,
        socket_connect_timeout=3,
        socket_timeout=5,
    )
