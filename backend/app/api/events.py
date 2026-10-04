import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.dependencies import Identity, current_identity
from app.api.errors import ApiError
from app.services.events import event_stream, session_valid

router = APIRouter(tags=["events"])


async def event_identity(request: Request) -> Identity:
    # Finish auth/activity commit and release its connection before reserving a stream slot.
    async with request.app.state.session_factory() as db:
        async with db.begin():
            return await current_identity(request, db)


EventAuth = Annotated[Identity, Depends(event_identity)]


class EventResponse(StreamingResponse):
    def __init__(self, stream, *, hub, subscription, send_timeout_seconds=10.0, **kwargs):
        self.hub, self.subscription = hub, subscription
        self.send_timeout_seconds = send_timeout_seconds
        super().__init__(stream, **kwargs)

    async def __call__(self, scope, receive, send):
        async def bounded_send(message):
            async with asyncio.timeout(self.send_timeout_seconds):
                await send(message)

        try:
            await super().__call__(scope, receive, bounded_send)
        finally:
            self.hub.unsubscribe(self.subscription)
            await self.body_iterator.aclose()


@router.get(
    "/events",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def events(request: Request, auth: EventAuth):
    # Native EventSource authenticates via same-origin HttpOnly cookie, never URL credentials.
    if request.query_params:
        raise ApiError(400, "invalid_event_request", "SSE does not accept query parameters")
    origin = request.headers.get("origin")
    if origin is not None and origin not in request.app.state.settings.allowed_origins:
        raise ApiError(403, "origin_forbidden", "Origin is not authorized")
    hub = request.app.state.event_hub
    subscription = hub.subscribe(auth.user.id)
    session_id, user_id = auth.session.id, auth.user.id

    async def check():
        return await session_valid(
            request.app.state.session_factory, session_id, user_id, request.app.state.settings
        )

    stream = event_stream(request, hub, subscription, check)
    return EventResponse(
        stream,
        hub=hub,
        subscription=subscription,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
