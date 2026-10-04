"""Bounded ephemeral SSE fan-out. REST snapshots remain the source of truth."""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal
from uuid import UUID, uuid4

from anyio import CancelScope
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select

from app.api.errors import ApiError
from app.db.models import Session, User
from app.security import aware, utcnow

logger = logging.getLogger(__name__)


class Invalidation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["project.updated", "monitor.updated", "incident.opened", "incident.closed"]
    owner_id: UUID
    project_id: UUID
    monitor_id: UUID | None = None
    incident_id: UUID | None = None
    revision: int = Field(ge=0, strict=True)
    source: str | None = Field(default=None, max_length=36)


@dataclass(eq=False)
class Subscription:
    owner_id: UUID
    queue: asyncio.Queue


class EventHub:
    def __init__(
        self, *, redis_factory=None, max_connections=3, queue_size=32, reconnect_seconds=2.0
    ):
        self.redis_factory = redis_factory
        self.max_connections = max_connections
        self.queue_size = queue_size
        self.reconnect_seconds = reconnect_seconds
        self.subscriptions = {}
        self.source = str(uuid4())
        self.task = None
        self.redis = None
        self.connected = False
        self.closed = False

    def subscribe(self, owner_id: UUID) -> Subscription:
        if self.closed:
            raise ApiError(503, "sse_unavailable", "Event stream is shutting down")
        entries = self.subscriptions.setdefault(owner_id, set())
        if len(entries) >= self.max_connections:
            raise ApiError(
                429,
                "sse_connection_limit",
                f"Limit of {self.max_connections} SSE connections per account reached",
            )
        subscription = Subscription(owner_id, asyncio.Queue(maxsize=self.queue_size))
        entries.add(subscription)
        if self.task is None and self.redis_factory is not None and not self.closed:
            self.task = asyncio.create_task(self._listen())
        return subscription

    def unsubscribe(self, subscription: Subscription):
        entries = self.subscriptions.get(subscription.owner_id)
        if entries is not None:
            entries.discard(subscription)
            if not entries:
                del self.subscriptions[subscription.owner_id]

    def dispatch(self, event):
        try:
            event = Invalidation.model_validate(event)
        except ValidationError:
            logger.warning("invalid_pubsub_signal")
            return
        payload = event.model_dump(mode="json", exclude_none=True)
        payload.pop("owner_id")
        payload.pop("source", None)
        for subscription in tuple(self.subscriptions.get(event.owner_id, ())):
            queue = subscription.queue
            if queue.full():
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait({"type": "snapshot.required", "reason": "backpressure"})
            else:
                queue.put_nowait(payload)

    async def emit(self, event):
        # Called only after the transaction commits. Local delivery also works without Redis.
        try:
            event = Invalidation.model_validate(event)
        except ValidationError:
            logger.warning("invalid_pubsub_signal")
            return
        self.dispatch(event)
        if self.redis_factory is None or self.closed:
            return
        # This API process may have no local streams while another replica has subscribers.
        # Publishing must not depend on starting the local Pub/Sub listener.
        redis = self.redis
        owned = redis is None
        try:
            async with asyncio.timeout(1):
                if owned:
                    redis = self.redis_factory()
                await redis.publish(
                    "vigil:updates",
                    json.dumps(
                        {**event.model_dump(mode="json", exclude_none=True), "source": self.source}
                    ),
                )
        except Exception:
            logger.warning("pubsub_publish_unavailable")
        finally:
            if owned and redis is not None:
                try:
                    async with asyncio.timeout(1):
                        await redis.aclose()
                except Exception:
                    logger.warning("pubsub_cleanup_failed")

    async def _listen(self):
        try:
            while not self.closed:
                try:
                    self.redis = self.redis_factory()
                    async with self.redis.pubsub() as pubsub:
                        await pubsub.subscribe("vigil:updates")
                        self.connected = True
                        while not self.closed:
                            message = await pubsub.get_message(
                                ignore_subscribe_messages=True, timeout=1
                            )
                            if message is None:
                                await asyncio.sleep(0.01)
                                continue
                            data = message.get("data")
                            if not isinstance(data, (bytes, str)) or len(data) > 4096:
                                continue
                            try:
                                event = json.loads(data)
                            except (ValueError, TypeError):
                                logger.warning("invalid_pubsub_signal")
                                continue
                            if isinstance(event, dict) and event.get("source") != self.source:
                                self.dispatch(event)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.warning("pubsub_unavailable_snapshot_fallback")
                finally:
                    self.connected = False
                    if self.redis is not None:
                        try:
                            async with asyncio.timeout(1):
                                await self.redis.aclose()
                        except Exception:
                            logger.warning("pubsub_cleanup_failed")
                        self.redis = None
                await asyncio.sleep(self.reconnect_seconds)
        finally:
            self.connected = False

    async def close(self):
        self.closed = True
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
        self.subscriptions.clear()


async def session_valid(factory, session_id, user_id, settings) -> bool:
    try:
        # StreamingResponse/HTTP middleware use AnyIO level cancellation. A
        # disconnect must not repeatedly cancel SQLAlchemy's rollback/check-in.
        # Keep the DB read and close bounded by the existing asyncio deadline.
        with CancelScope(shield=True):
            async with asyncio.timeout(5), factory() as db:
                row = (
                    await db.execute(
                        select(Session, User)
                        .join(User, User.id == Session.user_id)
                        .where(Session.id == session_id, Session.user_id == user_id)
                    )
                ).first()
        if row is None:
            return False
        session, user = row
        now = utcnow()
        return bool(
            user.is_active
            and session.revoked_at is None
            and aware(session.expires_at) > now
            and aware(session.last_seen_at) + timedelta(seconds=settings.session_idle_seconds) > now
        )
    except Exception:
        logger.warning("sse_session_check_unavailable")
        return False


def encode_event(event) -> bytes:
    kind = event["type"]
    data = {key: value for key, value in event.items() if key != "type"}
    return f"event: {kind}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n".encode()


async def event_stream(
    request,
    hub,
    subscription,
    session_check,
    *,
    snapshot_seconds=30.0,
    heartbeat_seconds=15.0,
    session_check_seconds=30.0,
):
    loop = asyncio.get_running_loop()
    now = loop.time()
    snapshot_at, heartbeat_at, check_at = (
        now + snapshot_seconds,
        now + heartbeat_seconds,
        now + session_check_seconds,
    )
    try:
        # Recheck after auth commit and before sending even the initial invalidation.
        if hub.closed or await request.is_disconnected() or not await session_check():
            return
        check_at = loop.time() + session_check_seconds
        yield encode_event({"type": "snapshot.required", "reason": "connected"})
        while not hub.closed:
            if await request.is_disconnected():
                return
            now = loop.time()
            if now >= check_at:
                if not await session_check():
                    return
                check_at = now + session_check_seconds
            if now >= snapshot_at:
                yield encode_event({"type": "snapshot.required", "reason": "periodic"})
                snapshot_at = now + snapshot_seconds
            if now >= heartbeat_at:
                yield b": heartbeat\n\n"
                heartbeat_at = now + heartbeat_seconds
            timeout = max(0.001, min(snapshot_at, heartbeat_at, check_at) - loop.time())
            try:
                event = await asyncio.wait_for(subscription.queue.get(), timeout=timeout)
                # A queued signal can race the validation deadline; never bypass revalidation.
                if loop.time() >= check_at:
                    if not await session_check():
                        return
                    check_at = loop.time() + session_check_seconds
                yield encode_event(event)
            except TimeoutError:
                pass
    finally:
        hub.unsubscribe(subscription)
