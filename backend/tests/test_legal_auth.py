"""Required legal versions, append-only success records and auth atomicity."""

from datetime import timedelta
from uuid import UUID

import httpx
import pytest
from conftest import LEGAL_VERSIONS, authenticate
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session as ORMSession

from app.db.models import LegalAcceptance, Session, User
from app.legal import PRIVACY_VERSION, TERMS_VERSION
from app.security import PASSWORD_HASHER, aware, token_hash, utcnow


def credentials(email="owner@example.com", password="a strong test password"):
    return {"email": email, "password": password, **LEGAL_VERSIONS}


async def counts(app):
    async with app.state.session_factory() as db:
        return tuple(
            [
                await db.scalar(select(func.count()).select_from(model))
                for model in (User, Session, LegalAcceptance)
            ]
        )


@pytest.mark.parametrize("endpoint", ["register", "login"])
@pytest.mark.parametrize("field", ["terms_version", "privacy_version"])
@pytest.mark.parametrize(
    "value",
    ["missing", None, True, False, 20261009, "2026-10-08", "", " 2026-10-09 ", [], {}],
)
async def test_legal_version_must_be_present_and_exact(client, api_app, endpoint, field, value):
    payload = credentials()
    if value == "missing":
        del payload[field]
    else:
        payload[field] = value
    response = await client.post(f"/api/v1/auth/{endpoint}", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert any(detail["field"] == f"body.{field}" for detail in response.json()["error"]["details"])
    assert "set-cookie" not in response.headers
    assert await counts(api_app) == (0, 0, 0)


async def test_valid_operations_append_owner_records_without_touching_prior_acceptances(
    client, api_app
):
    started = utcnow()
    registered = await client.post("/api/v1/auth/register", json=credentials())
    assert registered.status_code == 201
    assert await counts(api_app) == (1, 0, 1)
    owner = UUID(registered.json()["id"])
    async with api_app.state.session_factory() as db:
        acceptance = await db.scalar(select(LegalAcceptance))
        original = (acceptance.id, acceptance.accepted_at, acceptance.action)
    for _ in range(2):
        response = await client.post("/api/v1/auth/login", json=credentials())
        assert response.status_code == 200
    ended = utcnow()
    assert await counts(api_app) == (1, 2, 3)
    async with api_app.state.session_factory() as db:
        records = list(await db.scalars(select(LegalAcceptance)))
        assert len({record.id for record in records}) == 3
        assert sorted(record.action for record in records) == ["login", "login", "register"]
        for record in records:
            assert record.user_id == owner
            assert record.terms_version == TERMS_VERSION == "2026-10-09"
            assert record.privacy_version == PRIVACY_VERSION == "2026-10-09"
            assert started <= aware(record.accepted_at) <= ended
        stored = await db.get(LegalAcceptance, original[0])
        assert (stored.id, stored.accepted_at, stored.action) == original

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api_app),
        base_url="https://app.test",
        headers={"Origin": "https://app.test", "X-Vigil-Request": "browser"},
    ) as other:
        other_session = await authenticate(other, "other@example.com")
        other_owner = UUID(other_session["user"]["id"])
        assert (await client.get("/api/v1/auth/me")).json()["user"]["id"] == str(owner)
    async with api_app.state.session_factory() as db:
        records = list(await db.scalars(select(LegalAcceptance)))
        assert sum(record.user_id == owner for record in records) == 3
        assert sum(record.user_id == other_owner for record in records) == 2
    # Reading an existing session and logging out do not create new acceptance.
    current = await client.get("/api/v1/auth/me")
    client.headers["X-CSRF-Token"] = current.json()["csrf_token"]
    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    assert await counts(api_app) == (2, 3, 5)


@pytest.mark.parametrize("failure", ["duplicate", "wrong_password", "missing_user", "inactive"])
async def test_failed_authentication_does_not_append_acceptance(authenticated, api_app, failure):
    endpoint, payload, status = "login", credentials(), 401
    if failure == "duplicate":
        endpoint, status = "register", 409
    elif failure == "wrong_password":
        payload["password"] = "incorrect password"
    elif failure == "missing_user":
        payload["email"] = "missing@example.com"
    else:
        async with api_app.state.session_factory.begin() as db:
            (await db.scalar(select(User))).is_active = False
    token = authenticated.cookies["vigil_session"]
    response = await authenticated.post(f"/api/v1/auth/{endpoint}", json=payload)
    assert response.status_code == status
    assert "set-cookie" not in response.headers
    assert authenticated.cookies["vigil_session"] == token
    assert await counts(api_app) == (1, 1, 2)
    async with api_app.state.session_factory() as db:
        assert (await db.scalar(select(Session))).revoked_at is None


@pytest.mark.parametrize("endpoint", ["register", "login"])
async def test_rejected_legal_versions_preserve_existing_session(authenticated, api_app, endpoint):
    token = authenticated.cookies["vigil_session"]
    csrf = authenticated.headers["X-CSRF-Token"]
    payload = credentials("new@example.com" if endpoint == "register" else "owner@example.com")
    payload.pop("privacy_version")
    response = await authenticated.post(f"/api/v1/auth/{endpoint}", json=payload)
    assert response.status_code == 422
    assert "set-cookie" not in response.headers
    assert authenticated.cookies["vigil_session"] == token
    assert await counts(api_app) == (1, 1, 2)
    assert (await authenticated.get("/api/v1/auth/me")).json()["csrf_token"] == csrf
    assert (
        await authenticated.post("/api/v1/projects", json={"name": "still valid"})
    ).status_code == 201


async def test_login_preserves_same_user_session_on_another_device(authenticated, api_app):
    old_token = authenticated.cookies["vigil_session"]
    old_csrf = authenticated.headers["X-CSRF-Token"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api_app),
        base_url="https://app.test",
        headers={"Origin": "https://app.test", "X-Vigil-Request": "browser"},
    ) as other:
        response = await other.post("/api/v1/auth/login", json=credentials())
        assert response.status_code == 200
        assert other.cookies["vigil_session"] != old_token
        assert (await other.get("/api/v1/auth/me")).status_code == 200
    assert (await authenticated.get("/api/v1/auth/me")).json()["csrf_token"] == old_csrf
    assert await counts(api_app) == (1, 2, 3)
    async with api_app.state.session_factory() as db:
        assert (
            await db.scalar(select(Session).where(Session.token_hash == token_hash(old_token)))
        ).revoked_at is None


async def test_existing_session_without_legal_record_stays_valid(client, api_app):
    now, token, csrf = utcnow(), "existing-session-token", "existing-csrf-token"
    async with api_app.state.session_factory.begin() as db:
        user = User(email="legacy@example.com", password_hash="legacy hash")
        db.add(user)
        await db.flush()
        db.add(
            Session(
                user_id=user.id,
                token_hash=token_hash(token),
                csrf_token=csrf,
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )
    client.cookies.set("vigil_session", token)
    client.headers["X-CSRF-Token"] = csrf
    current = await client.get("/api/v1/auth/me")
    assert current.status_code == 200 and current.json()["csrf_token"] == csrf
    assert (
        await client.post("/api/v1/projects", json={"name": "legacy session"})
    ).status_code == 201
    assert await counts(api_app) == (1, 1, 0)


@pytest.mark.parametrize("failure", ["acceptance_insert", "commit"])
async def test_registration_and_acceptance_rollback_together(client, api_app, failure):
    def fail_insert(mapper, connection, target):
        assert target.accepted_at.tzinfo is not None
        raise IntegrityError("legal acceptance insert", {}, Exception("private-db-sentinel"))

    def fail_commit(db):
        if db.bind is api_app.state.engine.sync_engine:
            raise OperationalError("commit", {}, Exception("private-db-sentinel"))

    target, name, callback = (
        (LegalAcceptance, "after_insert", fail_insert)
        if failure == "acceptance_insert"
        else (ORMSession, "before_commit", fail_commit)
    )
    event.listen(target, name, callback)
    try:
        response = await client.post("/api/v1/auth/register", json=credentials())
    finally:
        event.remove(target, name, callback)
    assert response.status_code == 503
    assert "private-db-sentinel" not in response.text
    assert "set-cookie" not in response.headers
    assert await counts(api_app) == (0, 0, 0)


@pytest.mark.parametrize("failure", ["acceptance_insert", "session_insert", "commit"])
async def test_failed_login_rolls_back_acceptance_session_rotation_and_rehash(
    authenticated, api_app, monkeypatch, failure
):
    token = authenticated.cookies["vigil_session"]
    async with api_app.state.session_factory() as db:
        password_hash = (await db.scalar(select(User))).password_hash
    # Exercise rollback of a password rehash in the same authentication transaction.
    monkeypatch.setattr(type(PASSWORD_HASHER), "check_needs_rehash", lambda self, _: True)

    def fail_insert(mapper, connection, target):
        raise OperationalError("insert", {}, Exception("private-db-sentinel"))

    def fail_commit(db):
        if db.bind is api_app.state.engine.sync_engine:
            raise OperationalError("commit", {}, Exception("private-db-sentinel"))

    target, name, callback = (
        (ORMSession, "before_commit", fail_commit)
        if failure == "commit"
        else (
            Session if failure == "session_insert" else LegalAcceptance,
            "after_insert",
            fail_insert,
        )
    )
    event.listen(target, name, callback)
    try:
        response = await authenticated.post("/api/v1/auth/login", json=credentials())
    finally:
        event.remove(target, name, callback)
    assert response.status_code == 503
    assert "private-db-sentinel" not in response.text
    assert "set-cookie" not in response.headers
    assert authenticated.cookies["vigil_session"] == token
    assert await counts(api_app) == (1, 1, 2)
    async with api_app.state.session_factory() as db:
        session = await db.scalar(select(Session).where(Session.token_hash == token_hash(token)))
        assert session.revoked_at is None
        assert (await db.scalar(select(User))).password_hash == password_hash
    assert (await authenticated.get("/api/v1/auth/me")).status_code == 200
