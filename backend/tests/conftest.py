import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from app.config import Settings
from app.db.base import Base
from app.db.session import create_engine
from app.legal import PRIVACY_VERSION, TERMS_VERSION
from app.main import create_app

LEGAL_VERSIONS = {"terms_version": TERMS_VERSION, "privacy_version": PRIVACY_VERSION}


@pytest.fixture(params=["sqlite", "postgres"])
async def api_app(request):
    """Every API test runs on both adapters when an isolated PostgreSQL URL is supplied."""
    schema = None
    admin = None
    if request.param == "postgres":
        url = os.getenv("VIGIL_TEST_DATABASE_URL")
        if not url:
            pytest.skip("Set VIGIL_TEST_DATABASE_URL to run real PostgreSQL API tests")
        schema = "api_test_" + uuid4().hex
        admin = create_engine(url)
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(url, connect_args={"server_settings": {"search_path": schema}})
    else:
        engine = create_engine("sqlite+aiosqlite:///:memory:", allow_sqlite_for_tests=True)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        app = create_app(Settings(allowed_origins=["https://app.test"]), engine=engine)
        async with app.router.lifespan_context(app):
            yield app
    finally:
        await engine.dispose()
        if admin is not None:
            async with admin.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await admin.dispose()


@pytest.fixture
async def client(api_app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api_app),
        base_url="https://app.test",
        headers={"Origin": "https://app.test", "X-Vigil-Request": "browser"},
    ) as client:
        yield client


async def authenticate(client, email="owner@example.com"):
    credentials = {"email": email, "password": "a strong test password", **LEGAL_VERSIONS}
    registered = await client.post("/api/v1/auth/register", json=credentials)
    assert registered.status_code == 201, registered.text
    login = await client.post("/api/v1/auth/login", json=credentials)
    assert login.status_code == 200, login.text
    client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
    return login.json()


@pytest.fixture
async def authenticated(client):
    await authenticate(client)
    return client


@pytest.fixture
async def project(authenticated):
    response = await authenticated.post(
        "/api/v1/projects", json={"name": "API", "description": "test"}
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def monitor(authenticated, project):
    response = await authenticated.post(
        f"/api/v1/projects/{project['id']}/monitors",
        json={"name": "Health", "url": "https://example.com/health"},
    )
    assert response.status_code == 201, response.text
    return response.json()
