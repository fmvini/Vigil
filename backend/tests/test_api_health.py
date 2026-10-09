import httpx

from app.config import Settings
from app.main import create_app


async def test_health_probes_do_not_require_auth(client, api_app):
    assert (await client.get("/health/live")).json() == {"status": "ok"}
    ready = await client.get("/health/ready")
    # Shared API fixtures create ORM metadata, not an Alembic-managed schema.
    if api_app.state.engine.dialect.name == "sqlite":
        assert ready.status_code == 200
        assert ready.json()["dependencies"] == {"database": "ok"}
    else:
        assert ready.status_code == 503
        assert ready.json()["error"]["code"] == "not_ready"
    assert (await client.get("/api/v1/unknown")).json()["error"]["code"] == "not_found"


async def test_readiness_failure_does_not_break_liveness(api_app):
    class FailedEngine:
        def connect(self):
            raise OSError("secret-database-connection-string")

    app = create_app(Settings(), engine=FailedEngine())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://app.test"
    ) as client:
        assert (await client.get("/health/live")).status_code == 200
        result = await client.get("/health/ready")
        assert result.status_code == 503 and result.json()["error"]["code"] == "not_ready"
        assert "secret" not in result.text


async def test_production_cookie_has_host_prefix_and_security_attributes(api_app):
    from conftest import LEGAL_VERSIONS, authenticate

    app = create_app(
        Settings(
            environment="prod",
            database_url="postgresql+asyncpg://user:pass@db/vigil",
            allowed_origins=["https://app.test"],
        ),
        engine=api_app.state.engine,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://app.test",
        headers={"Origin": "https://app.test", "X-Vigil-Request": "browser"},
    ) as client:
        await authenticate(client)
        assert "vigil_session" not in client.cookies
        assert "__Host-vigil_session" in client.cookies
        response = await client.post(
            "/api/v1/auth/login",
            json={
                **LEGAL_VERSIONS,
                "email": "owner@example.com",
                "password": "a strong test password",
            },
        )
        cookie = response.headers["set-cookie"]
        assert "Secure" in cookie and "HttpOnly" in cookie and "Path=/" in cookie
        assert "SameSite=lax" in cookie and "Domain=" not in cookie
        assert (await client.get("/api/v1/auth/me")).status_code == 200
