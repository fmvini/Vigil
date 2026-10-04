import asyncio
from datetime import timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from conftest import authenticate
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CheckJob, CheckResult, Incident, Monitor
from app.security import utcnow


async def seed_history(
    api_app, monitor, *, success_count=9, failure_count=1, latency_scale=100, minimal_attempt=False
):
    base = utcnow().replace(minute=20, second=0, microsecond=0) - timedelta(hours=2)
    async with api_app.state.session_factory.begin() as db:
        entity = await db.get(Monitor, UUID(monitor["id"]))
        for index in range(success_count + failure_count):
            succeeded = index < success_count
            scheduled = base + timedelta(seconds=index)
            completed = scheduled + timedelta(seconds=1)
            job = CheckJob(
                id=uuid4(),
                monitor_id=entity.id,
                config_version=entity.config_version,
                scheduled_at=scheduled,
                expires_at=scheduled + timedelta(seconds=60),
                budget_ms=13600,
                config_snapshot={"url": entity.url},
                status="completed",
                started_at=scheduled,
                finished_at=completed,
                execution_count=1,
            )
            db.add(job)
            await db.flush()
            db.add(
                CheckResult(
                    job_id=job.id,
                    monitor_id=entity.id,
                    config_version=entity.config_version,
                    scheduled_at=scheduled,
                    started_at=scheduled,
                    completed_at=completed,
                    outcome="success" if succeeded else "failure",
                    http_status=200 if succeeded else 500,
                    latency_ms=(index + 1) * latency_scale if succeeded else 99999,
                    cycle_duration_ms=1000,
                    queue_delay_ms=0,
                    attempt_count=1,
                    attempts=[{"error_code": "timeout"}]
                    if minimal_attempt
                    else [
                        {
                            "http_status": 200 if succeeded else 500,
                            "duration_ms": 1000,
                            "latency_ms": 100,
                            "url": "private must never escape",
                        }
                    ],
                    error_code=None if succeeded else "unexpected_status",
                    health_after="online" if succeeded else "degraded",
                )
            )
        entity.health_status = "online"
        entity.last_checked_at = utcnow() - timedelta(seconds=5)
        return base


async def test_metrics_empty_is_null_with_quality_counts(authenticated, project, monitor):
    result = await authenticated.get(f"/api/v1/monitors/{monitor['id']}/metrics")
    assert result.status_code == 200, result.text
    value = result.json()
    assert value["uptime_percent"] is value["average_latency_ms"] is value["p95_latency_ms"] is None
    assert value["sample_count"] == value["latency_sample_count"] == 0
    assert value["series"] == [] and value["health_status"] is None
    assert value["freshness_counts"]["no_data"] == 1 and not value["data_complete"]
    project_value = (await authenticated.get(f"/api/v1/projects/{project['id']}/metrics")).json()
    assert project_value["uptime_percent"] is None


async def test_metrics_raw_percentile_failure_latency_excluded_and_series(
    authenticated,
    api_app,
    monitor,
):
    await seed_history(api_app, monitor)
    value = (await authenticated.get(f"/api/v1/monitors/{monitor['id']}/metrics")).json()
    assert value["success_count"] == 9 and value["failure_count"] == 1
    assert value["sample_count"] == 10 and value["uptime_percent"] == 90
    assert value["latency_sample_count"] == 9
    assert value["average_latency_ms"] == 500 and value["p95_latency_ms"] == pytest.approx(860)
    assert len(value["series"]) == 1
    assert value["series"][0]["p95_latency_ms"] == pytest.approx(860)


async def test_project_metrics_weight_samples_not_monitor_averages(
    authenticated,
    api_app,
    project,
    monitor,
):
    await seed_history(api_app, monitor, success_count=9, failure_count=0)
    second = (
        await authenticated.post(
            f"/api/v1/projects/{project['id']}/monitors",
            json={"name": "Second", "url": "https://example.com"},
        )
    ).json()
    await seed_history(api_app, second, success_count=0, failure_count=1)
    value = (await authenticated.get(f"/api/v1/projects/{project['id']}/metrics")).json()
    assert value["uptime_percent"] == 90  # averaging per-monitor uptime would incorrectly give 50
    assert value["p95_latency_ms"] == pytest.approx(860)


async def test_quality_jobs_are_not_target_failures(authenticated, api_app, monitor):
    async with api_app.state.session_factory.begin() as db:
        now = utcnow() - timedelta(minutes=5)
        for index, state in enumerate(("expired", "exhausted", "cancelled", "pending")):
            scheduled = now + timedelta(seconds=index)
            db.add(
                CheckJob(
                    monitor_id=UUID(monitor["id"]),
                    config_version=1,
                    scheduled_at=scheduled,
                    expires_at=scheduled + timedelta(seconds=60),
                    budget_ms=13600,
                    config_snapshot={},
                    status=state,
                    skipped_slots=index,
                    finished_at=None if state == "pending" else scheduled + timedelta(seconds=1),
                )
            )
    value = (await authenticated.get(f"/api/v1/monitors/{monitor['id']}/metrics")).json()
    assert value["excluded_count"] == 2 and value["cancelled_count"] == 1
    assert value["pending_count"] == 1 and value["skipped_slots"] == 6
    assert value["failure_count"] == 0 and value["uptime_percent"] is None


async def test_check_pagination_half_open_window_and_attempt_whitelist(
    authenticated,
    api_app,
    monitor,
):
    base = await seed_history(api_app, monitor)
    path = f"/api/v1/monitors/{monitor['id']}/checks"
    page = (await authenticated.get(path, params={"limit": 3, "offset": 3})).json()
    assert page["total"] == 10 and len(page["items"]) == 3
    assert "url" not in page["items"][0]["attempts"][0]
    bounded = (
        await authenticated.get(
            path, params={"from": base.isoformat(), "to": (base + timedelta(seconds=9)).isoformat()}
        )
    ).json()
    assert bounded["total"] == 9 and all(row["outcome"] == "success" for row in bounded["items"])


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-10-04T00:00:00Z"},
        {"from": "2026-10-04T00:00:00", "to": "2026-10-04T01:00:00"},
        {"from": "2000-01-01T00:00:00Z", "to": "2000-01-02T00:00:00Z"},
        {"period": "90d"},
    ],
)
async def test_invalid_metric_window_rejected(authenticated, monitor, params):
    result = await authenticated.get(f"/api/v1/monitors/{monitor['id']}/metrics", params=params)
    assert result.status_code == 422


async def test_all_private_observations_authorize_owner(authenticated, api_app, project, monitor):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api_app),
        base_url="https://app.test",
        headers={"Origin": "https://app.test", "X-Vigil-Request": "browser"},
    ) as other:
        await authenticate(other, "intruder@example.com")
        for path in (
            f"/monitors/{monitor['id']}/checks",
            f"/monitors/{monitor['id']}/metrics",
            f"/projects/{project['id']}/metrics",
            f"/projects/{project['id']}/incidents",
        ):
            assert (await other.get("/api/v1" + path)).status_code == 404


async def test_global_percentile_uses_distinct_monitor_distributions(
    authenticated,
    api_app,
    project,
    monitor,
):
    await seed_history(api_app, monitor, success_count=9, failure_count=0)
    second = (
        await authenticated.post(
            f"/api/v1/projects/{project['id']}/monitors",
            json={"name": "Slow", "url": "https://example.com"},
        )
    ).json()
    await seed_history(api_app, second, success_count=1, failure_count=0, latency_scale=10000)
    value = (await authenticated.get(f"/api/v1/projects/{project['id']}/metrics")).json()
    assert value["average_latency_ms"] == 1450
    assert value["p95_latency_ms"] == pytest.approx(5905)
    assert value["series"][0]["p95_latency_ms"] == pytest.approx(5905)


async def test_history_accepts_minimal_attempt_summary(authenticated, api_app, monitor):
    await seed_history(api_app, monitor, success_count=0, failure_count=1, minimal_attempt=True)
    result = await authenticated.get(f"/api/v1/monitors/{monitor['id']}/checks")
    assert result.status_code == 200
    assert result.json()["items"][0]["attempts"][0]["duration_ms"] is None


async def test_metric_snapshot_survives_concurrent_commit(
    authenticated,
    api_app,
    project,
    monitor,
    monkeypatch,
):
    if api_app.state.engine.dialect.name != "postgresql":
        pytest.skip("Snapshot isolation concurrency requires PostgreSQL")
    await seed_history(api_app, monitor, success_count=1, failure_count=0)
    second = (
        await authenticated.post(
            f"/api/v1/projects/{project['id']}/monitors",
            json={"name": "Concurrent", "url": "https://example.com"},
        )
    ).json()
    reached = asyncio.Event()
    committed = asyncio.Event()
    original = AsyncSession.execute

    async def interleave(session, statement, *args, **kwargs):
        result = await original(session, statement, *args, **kwargs)
        if not reached.is_set() and "avg(check_results.latency_ms)" in str(statement):
            reached.set()
            await asyncio.wait_for(committed.wait(), timeout=10)
        return result

    monkeypatch.setattr(AsyncSession, "execute", interleave)

    async def concurrent_writer():
        await asyncio.wait_for(reached.wait(), timeout=10)
        await seed_history(api_app, second, success_count=1, failure_count=0)
        committed.set()

    writer = asyncio.create_task(concurrent_writer())
    try:
        response = await authenticated.get(f"/api/v1/projects/{project['id']}/metrics")
        await writer
    finally:
        writer.cancel()
        await asyncio.gather(writer, return_exceptions=True)
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["sample_count"] == sum(point["sample_count"] for point in value["series"]) == 1
    latest = (await authenticated.get(f"/api/v1/projects/{project['id']}/metrics")).json()
    assert latest["sample_count"] == 2


async def test_public_opt_in_dto_excludes_private_monitors_and_fields(
    authenticated,
    api_app,
    project,
    monitor,
):
    public_path = f"/api/v1/public/status/{project['public_slug']}"
    assert (await authenticated.get(public_path)).status_code == 404
    await authenticated.patch(
        f"/api/v1/projects/{project['id']}",
        json={"public_status_enabled": True, "description": "private description"},
    )
    hidden = (await authenticated.get(public_path)).json()
    assert hidden["monitors"] == []
    await authenticated.patch(f"/api/v1/monitors/{monitor['id']}", json={"is_public": True})
    await authenticated.post(f"/api/v1/monitors/{monitor['id']}/pause")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api_app), base_url="https://app.test"
    ) as visitor:
        result = await visitor.get(public_path)
        assert result.status_code == 200
        value = result.json()
        assert len(value["monitors"]) == 1 and value["monitors"][0]["freshness"] == "paused"
        assert value["health_status"] is None
        for field in (
            "url",
            "email",
            "description",
            "expected_status",
            "retry_count",
            "error_code",
            "attempts",
        ):
            assert field not in value and field not in value["monitors"][0]
        assert "private description" not in result.text and monitor["url"] not in result.text
        await authenticated.patch(
            f"/api/v1/projects/{project['id']}", json={"public_status_enabled": False}
        )
        assert (await visitor.get(public_path)).status_code == 404


async def test_incidents_overlap_window_filter_and_public_whitelist(
    authenticated,
    api_app,
    project,
    monitor,
):
    await authenticated.patch(
        f"/api/v1/projects/{project['id']}", json={"public_status_enabled": True}
    )
    await authenticated.patch(f"/api/v1/monitors/{monitor['id']}", json={"is_public": True})
    async with api_app.state.session_factory.begin() as db:
        now = utcnow()
        db.add(
            Incident(
                monitor_id=UUID(monitor["id"]),
                started_at=now - timedelta(days=40),
                detected_at=now - timedelta(days=40) + timedelta(minutes=2),
                cause_code="timeout",
                failure_threshold_snapshot=3,
            )
        )
    private = (
        await authenticated.get(f"/api/v1/projects/{project['id']}/incidents?state=open")
    ).json()
    assert private["total"] == 1 and private["items"][0]["cause_code"] == "timeout"
    public = (
        await authenticated.get(f"/api/v1/public/status/{project['public_slug']}/incidents")
    ).json()
    assert public["total"] == 1
    assert set(public["items"][0]) == {
        "id",
        "monitor_id",
        "monitor_name",
        "started_at",
        "detected_at",
        "ended_at",
        "end_reason",
    }
    assert (
        await authenticated.get(f"/api/v1/projects/{project['id']}/incidents?state=closed")
    ).json()["total"] == 0
    await authenticated.delete(f"/api/v1/monitors/{monitor['id']}")
    assert (
        await authenticated.get(f"/api/v1/public/status/{project['public_slug']}/incidents")
    ).json()["total"] == 0
