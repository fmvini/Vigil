"""Invalid client input must fail validation before mutation or SQL binding."""

import httpx
import pytest


async def test_project_null_name_is_validation_error_without_mutation(
    authenticated, api_app, project
):
    path = f"/api/v1/projects/{project['id']}"
    # Observe the production 500 response instead of re-raising the validator bug.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api_app, raise_app_exceptions=False),
        base_url="https://app.test",
        headers=authenticated.headers,
        cookies=authenticated.cookies,
    ) as client:
        rejected = await client.patch(
            path, json={"name": None, "description": "Must not be stored"}
        )
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["error"]["code"] == "validation_error"
    assert "Must not be stored" not in rejected.text
    current = (await authenticated.get(path)).json()
    assert current == project


@pytest.mark.parametrize("route", ["projects", "monitors", "checks", "incidents", "public"])
@pytest.mark.parametrize("offset", [0, 2**63 - 1, 2**63])
async def test_list_offsets_fit_database_bigint(authenticated, project, monitor, route, offset):
    published = await authenticated.patch(
        f"/api/v1/projects/{project['id']}", json={"public_status_enabled": True}
    )
    assert published.status_code == 200
    paths = {
        "projects": "/api/v1/projects",
        "monitors": f"/api/v1/projects/{project['id']}/monitors",
        "checks": f"/api/v1/monitors/{monitor['id']}/checks",
        "incidents": f"/api/v1/projects/{project['id']}/incidents",
        "public": f"/api/v1/public/status/{project['public_slug']}/incidents",
    }
    response = await authenticated.get(paths[route], params={"offset": offset})
    if offset > 2**63 - 1:
        assert response.status_code == 422, response.text
        assert response.json()["error"]["details"] == [
            {"field": "query.offset", "type": "less_than_equal"}
        ]
    else:
        assert response.status_code == 200, response.text
        assert response.json()["total"] == (1 if route in {"projects", "monitors"} else 0)
        if offset:
            assert response.json()["items"] == []
