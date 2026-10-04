import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.db.models import Session, User
from app.security import aware, token_hash, utcnow


async def get_db(request: Request):
    async with request.app.state.session_factory() as db:
        async with db.begin():
            yield db
        for event in db.info.get("events", []):
            await request.app.state.event_hub.emit(event)


DB = Annotated[AsyncSession, Depends(get_db, scope="function")]


def browser_mutation(request: Request) -> None:
    if request.headers.get("origin") not in request.app.state.settings.allowed_origins:
        raise ApiError(403, "origin_forbidden", "An authorized Origin is required")
    if request.headers.get("x-vigil-request") != "browser":
        raise ApiError(403, "browser_request_required", "X-Vigil-Request: browser is required")
    if request.url.path in {"/api/v1/auth/register", "/api/v1/auth/login"}:
        if (
            request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            != "application/json"
        ):
            raise ApiError(415, "json_required", "Content-Type: application/json is required")


@dataclass
class Identity:
    user: User
    session: Session


async def current_identity(request: Request, db: DB) -> Identity:
    settings = request.app.state.settings
    token = request.cookies.get(settings.cookie_name)
    if not token or len(token) > 128:
        raise ApiError(401, "unauthenticated", "Authentication required")
    record = (
        await db.execute(
            select(Session, User)
            .join(User, User.id == Session.user_id)
            .where(Session.token_hash == token_hash(token))
        )
    ).first()
    now = utcnow()
    if record is None:
        raise ApiError(401, "unauthenticated", "Authentication required")
    session, user = record
    if (
        not user.is_active
        or session.revoked_at is not None
        or aware(session.expires_at) <= now
        or aware(session.last_seen_at) + timedelta(seconds=settings.session_idle_seconds) <= now
    ):
        raise ApiError(401, "unauthenticated", "Session is no longer valid")
    if aware(session.last_seen_at) + timedelta(minutes=5) <= now:
        # Conditional activity update never clears revoked_at or changes absolute expiry.
        session.last_seen_at = now
    return Identity(user, session)


Auth = Annotated[Identity, Depends(current_identity)]


async def mutation_identity(request: Request, auth: Auth) -> Identity:
    browser_mutation(request)
    supplied = request.headers.get("x-csrf-token", "")
    if (
        not supplied
        or len(supplied) > 128
        or not secrets.compare_digest(supplied.encode(), auth.session.csrf_token.encode())
    ):
        raise ApiError(403, "csrf_invalid", "A valid CSRF token is required")
    return auth


MutationAuth = Annotated[Identity, Depends(mutation_identity)]
