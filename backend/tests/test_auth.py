from datetime import timedelta

import httpx
import pytest
from conftest import authenticate
from sqlalchemy import select

from app.db.models import Session, User
from app.security import token_hash, utcnow


async def test_registration_normalizes_email_and_does_not_log_in(client, api_app):
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "  Owner@Example.COM  ", "password": "a strong test password"},
    )
    assert response.status_code == 201
    assert set(response.json()) == {"id", "email", "created_at"}
    assert response.json()["email"] == "owner@example.com"
    assert "set-cookie" not in response.headers
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    duplicate = await client.post(
        "/api/v1/auth/register",
        json={"email": "owner@example.com", "password": "a strong test password"},
    )
    assert duplicate.status_code == 409
    async with api_app.state.session_factory() as db:
        user = await db.scalar(select(User))
        assert user.password_hash.startswith("$argon2id$")
        assert "a strong test password" not in user.password_hash


async def test_login_me_logout_revokes_cookie_and_stored_token(client, api_app):
    login = await authenticate(client)
    token = client.cookies["vigil_session"]
    cookie = (
        await client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "a strong test password"},
        )
    ).headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/" in cookie
    current = await client.get("/api/v1/auth/me")
    assert current.json()["user"] == login["user"]
    assert current.headers["cache-control"] == "no-store"
    client.headers["X-CSRF-Token"] = current.json()["csrf_token"]
    async with api_app.state.session_factory() as db:
        old = await db.scalar(select(Session).where(Session.token_hash == token_hash(token)))
        assert old.revoked_at is not None  # login rotation
        assert old.token_hash != token
    new_token = client.cookies["vigil_session"]
    logout = await client.post("/api/v1/auth/logout")
    assert logout.status_code == 204 and not logout.content
    assert "vigil_session" not in client.cookies
    client.cookies.set("vigil_session", new_token)
    assert (await client.get("/api/v1/auth/me")).status_code == 401


@pytest.mark.parametrize(
    "email,password",
    [
        ("missing@example.com", "a strong test password"),
        ("owner@example.com", "incorrect password"),
    ],
)
async def test_invalid_credentials_are_generic(authenticated, email, password):
    response = await authenticated.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


@pytest.mark.parametrize("kind", ["idle", "absolute", "disabled"])
async def test_expiry_and_disabled_user_reject_session(authenticated, api_app, kind):
    now = utcnow()
    async with api_app.state.session_factory.begin() as db:
        session = await db.scalar(select(Session))
        session.created_at = now - timedelta(days=8)
        if kind == "idle":
            session.last_seen_at = now - timedelta(hours=25)
        if kind == "absolute":
            session.expires_at = now - timedelta(seconds=1)
        if kind == "disabled":
            user = await db.scalar(select(User))
            user.is_active = False
    assert (await authenticated.get("/api/v1/auth/me")).status_code == 401


@pytest.mark.parametrize(
    "header,value,code",
    [
        ("Origin", "https://evil.test", "origin_forbidden"),
        ("Origin", "", "origin_forbidden"),
        ("X-Vigil-Request", "", "browser_request_required"),
        ("X-CSRF-Token", "", "csrf_invalid"),
        ("X-CSRF-Token", "wrong", "csrf_invalid"),
    ],
)
async def test_authenticated_mutations_require_origin_browser_and_csrf(
    authenticated, header, value, code
):
    authenticated.headers[header] = value
    response = await authenticated.post("/api/v1/projects", json={"name": "blocked"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == code


async def test_unauthenticated_registration_protection_and_safe_validation(client):
    client.headers["Origin"] = "https://evil.test"
    result = await client.post(
        "/api/v1/auth/register",
        json={"email": "owner@example.com", "password": "a strong test password"},
    )
    assert result.status_code == 403
    client.headers["Origin"] = "https://app.test"
    result = await client.post(
        "/api/v1/auth/register",
        content='{"email":"owner@example.com","password":"very-secret-password"}',
        headers={"Content-Type": "text/plain"},
    )
    assert result.status_code == 415
    result = await client.post(
        "/api/v1/auth/register", json={"email": "bad-email", "password": "secret"}
    )
    assert result.status_code == 422
    assert "secret" not in result.text and "bad-email" not in result.text


async def test_csrf_token_is_bound_to_session(authenticated, api_app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api_app),
        base_url="https://app.test",
        headers={"Origin": "https://app.test", "X-Vigil-Request": "browser"},
    ) as other:
        other_login = await authenticate(other, "other@example.com")
        authenticated.headers["X-CSRF-Token"] = other_login["csrf_token"]
        assert (
            await authenticated.post("/api/v1/projects", json={"name": "blocked"})
        ).status_code == 403


async def test_activity_refresh_does_not_extend_absolute_expiry(authenticated, api_app):
    async with api_app.state.session_factory.begin() as db:
        session = await db.scalar(select(Session))
        session.created_at = utcnow() - timedelta(hours=1)
        session.last_seen_at = utcnow() - timedelta(minutes=10)
        expiry = session.expires_at
    assert (await authenticated.get("/api/v1/auth/me")).status_code == 200
    async with api_app.state.session_factory() as db:
        session = await db.scalar(select(Session))
        assert session.expires_at == expiry
        assert session.last_seen_at > utcnow().replace(
            tzinfo=session.last_seen_at.tzinfo
        ) - timedelta(minutes=1)
