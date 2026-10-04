import asyncio
from datetime import timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from conftest import authenticate
from sqlalchemy import func, select

from app.db.models import CheckJob, Incident, Monitor, Project
from app.security import utcnow


async def test_project_crud_pagination_and_archive(authenticated, project):
    project_id = project["id"]
    second = await authenticated.post("/api/v1/projects", json={"name": "Second"})
    assert second.status_code == 201
    listing = (await authenticated.get("/api/v1/projects?limit=1&offset=1")).json()
    assert listing["total"] == 2 and len(listing["items"]) == 1
    detail = await authenticated.get(f"/api/v1/projects/{project_id}")
    assert detail.json()["name"] == "API"
    patch = await authenticated.patch(
        f"/api/v1/projects/{project_id}", json={"name": "Updated", "description": None}
    )
    assert patch.status_code == 200 and patch.json()["description"] is None
    assert patch.json()["revision"] == 1
    for _ in range(2):
        archived = await authenticated.delete(f"/api/v1/projects/{project_id}")
        assert archived.status_code == 204 and not archived.content
    assert (await authenticated.get(f"/api/v1/projects/{project_id}")).status_code == 404
    assert (await authenticated.get("/api/v1/projects")).json()["total"] == 1


async def test_monitor_crud_defaults_pause_resume_and_null_threshold(authenticated, monitor):
    monitor_id = monitor["id"]
    assert monitor["health_status"] is None and monitor["freshness"] == "no_data"
    assert monitor["method"] == "GET" and monitor["timeout_ms"] == 5000
    assert monitor["config_version"] == 1 and monitor["next_check_at"] is not None
    for action, paused in [("pause", True), ("pause", True), ("resume", False)]:
        response = await authenticated.post(f"/api/v1/monitors/{monitor_id}/{action}")
        assert response.status_code == 200
        assert response.json()["is_paused"] == paused
        assert (response.json()["next_check_at"] is None) == paused
        assert response.json()["freshness"] == ("paused" if paused else "no_data")
    patch = await authenticated.patch(
        f"/api/v1/monitors/{monitor_id}", json={"latency_threshold_ms": None}
    )
    assert patch.status_code == 200 and patch.json()["latency_threshold_ms"] is None
    for _ in range(2):
        assert (await authenticated.delete(f"/api/v1/monitors/{monitor_id}")).status_code == 204
    assert (await authenticated.get(f"/api/v1/monitors/{monitor_id}")).status_code == 404
    listing = await authenticated.get(f"/api/v1/projects/{monitor['project_id']}/monitors")
    assert listing.json() == {"items": [], "total": 0}


async def test_project_and_monitor_are_isolated_for_all_operations(
    authenticated, api_app, project, monitor
):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api_app),
        base_url="https://app.test",
        headers={"Origin": "https://app.test", "X-Vigil-Request": "browser"},
    ) as other:
        await authenticate(other, "other@example.com")
        assert (await other.get("/api/v1/projects")).json() == {"items": [], "total": 0}
        p, m = project["id"], monitor["id"]
        requests = [
            ("GET", f"/projects/{p}", None),
            ("PATCH", f"/projects/{p}", {"name": "stolen"}),
            ("DELETE", f"/projects/{p}", None),
            ("GET", f"/projects/{p}/monitors", None),
            ("POST", f"/projects/{p}/monitors", {"name": "stolen", "url": "https://example.com"}),
            ("GET", f"/monitors/{m}", None),
            ("PATCH", f"/monitors/{m}", {"name": "stolen"}),
            ("DELETE", f"/monitors/{m}", None),
            ("POST", f"/monitors/{m}/pause", None),
            ("POST", f"/monitors/{m}/resume", None),
        ]
        for method, path, body in requests:
            response = await other.request(method, "/api/v1" + path, json=body)
            assert response.status_code == 404, (method, path, response.text)
            assert response.json()["error"]["code"] == "not_found"
    assert (await authenticated.get(f"/api/v1/monitors/{monitor['id']}")).json()["name"] == "Health"


async def test_patch_validates_merged_configuration_and_does_not_mutate_on_error(
    authenticated, monitor
):
    path = f"/api/v1/monitors/{monitor['id']}"
    valid = await authenticated.patch(path, json={"latency_threshold_ms": 4000})
    version = valid.json()["config_version"]
    invalid = await authenticated.patch(path, json={"timeout_ms": 2000})
    assert invalid.status_code == 422
    assert "url" not in invalid.text
    assert (await authenticated.get(path)).json()["timeout_ms"] == 5000
    assert (await authenticated.get(path)).json()["config_version"] == version
    for payload in [{"url": None}, {"name": None}, {"is_public": None}, {"config_version": 1}]:
        assert (await authenticated.patch(path, json=payload)).status_code == 422


async def seed_running_job_and_incident(api_app, monitor_id):
    now = utcnow() - timedelta(seconds=1)
    async with api_app.state.session_factory.begin() as db:
        monitor = await db.get(Monitor, UUID(monitor_id))
        monitor.health_status = "offline"
        monitor.consecutive_failures = 3
        monitor.first_failure_at = now - timedelta(seconds=10)
        monitor.last_checked_at = now
        monitor.last_outcome = "failure"
        job = CheckJob(
            monitor_id=monitor.id,
            config_version=monitor.config_version,
            config_snapshot={},
            scheduled_at=now,
            expires_at=now + timedelta(seconds=60),
            budget_ms=13600,
            status="running",
            lease_token=uuid4(),
            lease_expires_at=now + timedelta(seconds=90),
            started_at=now,
            execution_count=1,
        )
        incident = Incident(
            monitor_id=monitor.id,
            started_at=now - timedelta(seconds=10),
            detected_at=now,
            cause_code="timeout",
            failure_threshold_snapshot=3,
        )
        db.add_all([job, incident])
        await db.flush()
        return job.id, incident.id


async def test_pause_invalidates_lease_preserves_health_and_incident(
    authenticated, api_app, monitor
):
    job_id, incident_id = await seed_running_job_and_incident(api_app, monitor["id"])
    response = await authenticated.post(f"/api/v1/monitors/{monitor['id']}/pause")
    assert response.json()["health_status"] == "offline"
    assert response.json()["consecutive_failures"] == 0
    async with api_app.state.session_factory() as db:
        job = await db.get(CheckJob, job_id)
        incident = await db.get(Incident, incident_id)
        assert job.status == "cancelled" and job.lease_token is None and job.finished_at is not None
        assert incident.ended_at is None
    resumed = await authenticated.post(f"/api/v1/monitors/{monitor['id']}/resume")
    assert resumed.json()["health_status"] == "offline"


@pytest.mark.parametrize(
    "action,reason",
    [
        ("configuration", "configuration_changed"),
        ("archive", "archived"),
        ("project_archive", "archived"),
    ],
)
async def test_administrative_changes_cancel_jobs_and_close_incidents(
    authenticated, api_app, monitor, action, reason
):
    job_id, incident_id = await seed_running_job_and_incident(api_app, monitor["id"])
    path = f"/api/v1/monitors/{monitor['id']}"
    if action == "configuration":
        response = await authenticated.patch(path, json={"expected_status": 204})
        assert response.status_code == 200 and response.json()["health_status"] is None
    elif action == "archive":
        assert (await authenticated.delete(path)).status_code == 204
    else:
        assert (
            await authenticated.delete(f"/api/v1/projects/{monitor['project_id']}")
        ).status_code == 204
    async with api_app.state.session_factory() as db:
        job = await db.get(CheckJob, job_id)
        incident = await db.get(Incident, incident_id)
        row = await db.get(Monitor, UUID(monitor["id"]))
        assert job.status == "cancelled" and job.lease_token is None
        assert incident.end_reason == reason and incident.ended_at is not None
        if action != "configuration":
            assert row.archived_at is not None and row.next_check_at is None and not row.is_public


async def test_name_only_patch_preserves_job_health_and_version(authenticated, api_app, monitor):
    job_id, incident_id = await seed_running_job_and_incident(api_app, monitor["id"])
    response = await authenticated.patch(
        f"/api/v1/monitors/{monitor['id']}", json={"name": "Renamed"}
    )
    assert response.json()["config_version"] == 1 and response.json()["health_status"] == "offline"
    async with api_app.state.session_factory() as db:
        assert (await db.get(CheckJob, job_id)).status == "running"
        assert (await db.get(Incident, incident_id)).ended_at is None


async def test_project_quota_frees_slot_after_archive(authenticated, project):
    for n in range(4):
        assert (
            await authenticated.post("/api/v1/projects", json={"name": str(n)})
        ).status_code == 201
    assert (await authenticated.post("/api/v1/projects", json={"name": "over"})).status_code == 409
    assert (await authenticated.delete(f"/api/v1/projects/{project['id']}")).status_code == 204
    assert (
        await authenticated.post("/api/v1/projects", json={"name": "replacement"})
    ).status_code == 201


async def test_paused_monitors_count_towards_quota_archived_do_not(authenticated, project, monitor):
    for n in range(19):
        result = await authenticated.post(
            f"/api/v1/projects/{project['id']}/monitors",
            json={"name": str(n), "url": "https://example.com"},
        )
        assert result.status_code == 201
    await authenticated.post(f"/api/v1/monitors/{monitor['id']}/pause")
    path = f"/api/v1/projects/{project['id']}/monitors"
    assert (
        await authenticated.post(path, json={"name": "over", "url": "https://example.com"})
    ).status_code == 409
    await authenticated.delete(f"/api/v1/monitors/{monitor['id']}")
    assert (
        await authenticated.post(path, json={"name": "replacement", "url": "https://example.com"})
    ).status_code == 201


async def test_concurrent_project_creations_respect_postgresql_quota(authenticated, api_app):
    if api_app.state.engine.dialect.name != "postgresql":
        pytest.skip("SQLite does not implement PostgreSQL row locks")
    results = await asyncio.gather(
        *(authenticated.post("/api/v1/projects", json={"name": str(n)}) for n in range(10))
    )
    assert sorted(r.status_code for r in results) == [201] * 5 + [409] * 5
    async with api_app.state.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(Project)) == 5


async def test_concurrent_monitor_creations_respect_postgresql_quota(
    authenticated, api_app, project
):
    if api_app.state.engine.dialect.name != "postgresql":
        pytest.skip("SQLite does not implement PostgreSQL row locks")
    results = await asyncio.gather(
        *(
            authenticated.post(
                f"/api/v1/projects/{project['id']}/monitors",
                json={"name": str(n), "url": "https://example.com"},
            )
            for n in range(25)
        )
    )
    assert sorted(r.status_code for r in results) == [201] * 20 + [409] * 5
    async with api_app.state.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(Monitor)) == 20
