import secrets
from datetime import timedelta

from anyio import to_thread
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import DB, Auth, MutationAuth, browser_mutation
from app.api.errors import ApiError
from app.api.schemas import AuthOut, Credentials, UserOut
from app.db.models import LegalAcceptance, Session, User
from app.security import DUMMY_HASH, PASSWORD_HASHER, token_hash, utcnow, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register", status_code=201, response_model=UserOut, dependencies=[Depends(browser_mutation)]
)
async def register(data: Credentials, request: Request, db: DB):
    password_hash = await to_thread.run_sync(
        PASSWORD_HASHER.hash, data.password, limiter=request.app.state.password_limiter
    )
    user = User(email=str(data.email), password_hash=password_hash)
    try:
        db.add(user)
        await db.flush()
    except IntegrityError:
        raise ApiError(409, "conflict", "Email is already registered") from None
    # The request transaction owns both writes, including a failed final commit.
    db.add(
        LegalAcceptance(
            user_id=user.id,
            terms_version=data.terms_version,
            privacy_version=data.privacy_version,
            accepted_at=utcnow(),
            action="register",
        )
    )
    await db.flush()
    return UserOut.model_validate(user)


@router.post("/login", response_model=AuthOut, dependencies=[Depends(browser_mutation)])
async def login(data: Credentials, request: Request, response: Response, db: DB):
    user = await db.scalar(select(User).where(User.email == str(data.email)))
    valid = await to_thread.run_sync(
        verify_password,
        data.password,
        user.password_hash if user else DUMMY_HASH,
        limiter=request.app.state.password_limiter,
    )
    if not valid or user is None or not user.is_active:
        raise ApiError(401, "invalid_credentials", "Invalid email or password")
    if PASSWORD_HASHER.check_needs_rehash(user.password_hash):
        user.password_hash = await to_thread.run_sync(
            PASSWORD_HASHER.hash, data.password, limiter=request.app.state.password_limiter
        )
    settings = request.app.state.settings
    now = utcnow()
    db.add(
        LegalAcceptance(
            user_id=user.id,
            terms_version=data.terms_version,
            privacy_version=data.privacy_version,
            accepted_at=now,
            action="login",
        )
    )
    # Successful login rotates this browser's existing credential; other devices stay valid.
    old_token = request.cookies.get(settings.cookie_name)
    if old_token:
        old_session = await db.scalar(
            select(Session).where(
                Session.token_hash == token_hash(old_token), Session.revoked_at.is_(None)
            )
        )
        if old_session:
            old_session.revoked_at = now
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(
        Session(
            user_id=user.id,
            token_hash=token_hash(token),
            csrf_token=csrf,
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(seconds=settings.session_absolute_seconds),
        )
    )
    await db.flush()
    response.set_cookie(
        settings.cookie_name,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        max_age=settings.session_absolute_seconds,
    )
    response.headers["Cache-Control"] = "no-store"
    return AuthOut(user=UserOut.model_validate(user), csrf_token=csrf)


@router.get("/me", response_model=AuthOut)
async def me(response: Response, auth: Auth):
    response.headers["Cache-Control"] = "no-store"
    return AuthOut(user=UserOut.model_validate(auth.user), csrf_token=auth.session.csrf_token)


@router.post("/logout", status_code=204)
async def logout(request: Request, auth: MutationAuth):
    auth.session.revoked_at = utcnow()
    settings = request.app.state.settings
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.delete_cookie(
        settings.cookie_name, path="/", secure=settings.cookie_secure, httponly=True, samesite="lax"
    )
    return response
