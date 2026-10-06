import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.domain.monitors import validate_check_config
from app.main import create_app


@pytest.mark.parametrize("minimum,cadence", [(60, None), (300, 300), (900, 900), (3600, 1)])
async def test_public_runtime_config_is_exact_no_store_and_needs_no_database(minimum, cadence):
    class UnavailableEngine:
        def connect(self):
            raise AssertionError("Public configuration must not connect")

    app = create_app(
        Settings(
            minimum_interval_seconds=minimum,
            scheduled_checks_interval_seconds=cadence,
            database_url="postgresql+asyncpg://private:secret@db/vigil",
            redis_enabled=False,
        ),
        engine=UnavailableEngine(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/runtime-config")
    assert response.status_code == 200
    assert response.json() == {
        "minimum_interval_seconds": minimum,
        "scheduled_checks_interval_seconds": cadence,
    }
    assert response.headers["cache-control"] == "no-store"
    assert "private" not in response.text and "secret" not in response.text


@pytest.mark.parametrize(
    "fields",
    [
        {"minimum_interval_seconds": 59},
        {"minimum_interval_seconds": 3601},
        {"minimum_interval_seconds": 300.0},
        {"scheduled_checks_interval_seconds": True},
        {"scheduled_checks_interval_seconds": 0},
        {"scheduled_checks_interval_seconds": 1.5},
        {"database_pool_size": 0},
        {"database_max_overflow": -1},
        {"database_schema": "public,private"},
    ],
)
def test_deployment_settings_reject_invalid_types_and_ranges(fields):
    with pytest.raises(ValidationError):
        Settings(**fields)


def test_configured_minimum_is_applied_to_check_config():
    from app.api.schemas import MonitorCreate

    configuration = MonitorCreate(name="Test", url="https://example.com").model_dump()
    validate_check_config(configuration)
    with pytest.raises(ValueError, match="minimum"):
        validate_check_config(configuration, minimum_interval_seconds=300)


async def test_cloud_interval_create_default_and_update_fail_without_mutation(
    api_app, authenticated, project
):
    api_app.state.settings.minimum_interval_seconds = 300
    path = f"/api/v1/projects/{project['id']}/monitors"
    payload = {"name": "Target", "url": "https://example.com"}
    rejected = await authenticated.post(path, json={**payload, "interval_seconds": 60})
    assert rejected.status_code == 422
    assert rejected.json()["error"]["details"] == [
        {"field": "interval_seconds", "type": "greater_than_equal"}
    ]
    created = await authenticated.post(path, json=payload)
    assert created.status_code == 201 and created.json()["interval_seconds"] == 300
    monitor = created.json()
    endpoint = f"/api/v1/monitors/{monitor['id']}"
    failed = await authenticated.patch(endpoint, json={"interval_seconds": 299, "name": "Changed"})
    assert failed.status_code == 422
    after = (await authenticated.get(endpoint)).json()
    assert after["interval_seconds"] == 300 and after["name"] == "Target"
    assert after["config_version"] == monitor["config_version"]
    assert (await authenticated.patch(endpoint, json={"interval_seconds": 600})).status_code == 200


async def test_legacy_monitor_is_readable_but_update_requires_minimum(
    api_app, authenticated, monitor
):
    api_app.state.settings.minimum_interval_seconds = 300
    path = f"/api/v1/monitors/{monitor['id']}"
    assert (await authenticated.get(path)).json()["interval_seconds"] == 60
    assert (await authenticated.patch(path, json={"name": "Renamed"})).status_code == 422
    assert (
        await authenticated.patch(path, json={"name": "Renamed", "interval_seconds": 300})
    ).status_code == 200


async def test_no_redis_mode_mutations_and_local_subscription_do_not_create_client(
    api_app, monkeypatch
):
    from conftest import authenticate

    from app import main

    def forbidden(*args, **kwargs):
        raise AssertionError("Disabled Redis must not create clients")

    monkeypatch.setattr(main.Redis, "from_url", forbidden)
    app = create_app(
        Settings(redis_enabled=False, allowed_origins=["https://app.test"]),
        engine=api_app.state.engine,
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="https://app.test",
            headers={"Origin": "https://app.test", "X-Vigil-Request": "browser"},
        ) as client,
    ):
        login = await authenticate(client)
        from uuid import UUID

        subscription = app.state.event_hub.subscribe(UUID(login["user"]["id"]))
        created = await client.post("/api/v1/projects", json={"name": "Local"})
        assert created.status_code == 201
        assert subscription.queue.get_nowait()["type"] == "project.updated"
        assert app.state.event_hub.task is None
