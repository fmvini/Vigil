"""Private operational history contracts; PostgreSQL snapshot proof remains separate."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from conftest import authenticate
from sqlalchemy import delete, event, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.jobs import OperationalJobOut
from app.api.observations import observation_session
from app.db.models import CheckJob, Monitor, Project, User
from app.db.session import create_engine
from app.security import utcnow


@pytest.fixture(autouse=True)
async def require_pg17_before_metadata(request):
    # Module-local guard runs before the shared API fixture's CREATE SCHEMA.
    # Only an explicitly supplied, disposable PostgreSQL test URL is considered.
    params = getattr(getattr(request.node, "callspec", None), "params", {})
    url = os.getenv("VIGIL_TEST_DATABASE_URL")
    if params.get("api_app") != "postgres" or not url:
        return
    engine = create_engine(url)
    try:
        async with engine.connect() as connection:
            version = int(await connection.scalar(text("SHOW server_version_num")))
        if not 170000 <= version < 180000:
            pytest.fail("Operational jobs tests require isolated PostgreSQL17 before DDL")
    finally:
        await engine.dispose()


async def seed_jobs(api_app, monitor):
    base = utcnow() - timedelta(hours=1)
    states = [
        "expired",
        "exhausted",
        "expired",
        "completed",
        "cancelled",
        "pending",
        "expired",
        "exhausted",
    ]
    async with api_app.state.session_factory.begin() as db:
        for index, status in enumerate(states):
            scheduled = base + timedelta(seconds=max(0, index - 1))
            if index == 6:
                scheduled = base - timedelta(days=31)
            if index == 7:
                scheduled = base + timedelta(seconds=5)
            db.add(
                CheckJob(
                    id=UUID(int=index + 1),
                    monitor_id=UUID(monitor["id"]),
                    config_version=index + 1,
                    scheduled_at=scheduled,
                    expires_at=scheduled + timedelta(seconds=60),
                    budget_ms=5000,
                    config_snapshot={"url": "https://private-configuration-token.example/secret"},
                    status=status,
                    execution_count=3 if status == "exhausted" else 0,
                    finished_at=None
                    if status == "pending"
                    else base + timedelta(seconds=10)
                    if index == 6
                    else scheduled + timedelta(seconds=1),
                    error_code="execution_limit"
                    if status == "exhausted"
                    else "private-remote-error-password"
                    if index == 2
                    else "insufficient_budget",
                )
            )
        entity = await db.get(Monitor, UUID(monitor["id"]))
        entity.paused_at = utcnow()  # Paused monitors remain visible in operational history.
        entity.next_check_at = None
    return base


async def test_jobs_projection_selection_utc_sanitization_and_no_mutation(
    api_app,
    authenticated,
    project,
    monitor,
):
    await seed_jobs(api_app, monitor)
    path = f"/api/v1/projects/{project['id']}/jobs"
    async with api_app.state.session_factory() as db:
        before = [
            (job.id, job.status, job.error_code, job.config_snapshot)
            for job in (await db.scalars(select(CheckJob).order_by(CheckJob.id))).all()
        ]
    statements = []

    def observe(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(api_app.state.engine.sync_engine, "before_cursor_execute", observe)
    try:
        response = await authenticated.get(path)
    finally:
        event.remove(api_app.state.engine.sync_engine, "before_cursor_execute", observe)
    assert response.status_code == 200, response.text
    value = response.json()
    assert set(value) == {"items", "total", "from", "to", "computed_at", "retention_days"}
    assert value["total"] == 4 and value["retention_days"] == 30
    assert [row["job_id"] for row in value["items"]] == [str(UUID(int=i)) for i in [8, 3, 2, 1]]
    assert {row["status"] for row in value["items"]} == {"exhausted", "expired"}
    for row in value["items"]:
        assert set(row) == {
            "job_id",
            "monitor_id",
            "config_version",
            "status",
            "scheduled_at",
            "finished_at",
            "execution_count",
            "error_code",
        }
        for field in ("scheduled_at", "finished_at"):
            assert datetime.fromisoformat(row[field]).tzinfo == UTC
    assert value["items"][1]["error_code"] is None
    assert value["items"][2]["error_code"] == "execution_limit"
    assert value["items"][2]["execution_count"] == 3
    assert "private-" not in response.text
    for field in ("from", "to", "computed_at"):
        assert datetime.fromisoformat(value[field]).tzinfo == UTC
    jobs_sql = [statement for statement in statements if "from check_jobs" in statement]
    assert len(jobs_sql) == 2
    assert all(
        "config_snapshot" not in sql and "lease_token" not in sql and "url" not in sql
        for sql in jobs_sql
    )
    assert not any(
        sql.lstrip().startswith(("insert ", "update ", "delete ")) and "check_jobs" in sql
        for sql in statements
    )
    async with api_app.state.session_factory() as db:
        after = [
            (job.id, job.status, job.error_code, job.config_snapshot)
            for job in (await db.scalars(select(CheckJob).order_by(CheckJob.id))).all()
        ]
    assert before == after
    assert response.headers["cache-control"] == "no-store"
    for status, expected in [("exhausted", [8, 2]), ("expired", [3, 1])]:
        selected = (await authenticated.get(path, params={"status": status})).json()
        assert [row["job_id"] for row in selected["items"]] == [str(UUID(int=i)) for i in expected]
    # Replacing the sole pending row by running does not make it eligible.
    async with api_app.state.session_factory.begin() as db:
        pending = await db.get(CheckJob, UUID(int=6))
        pending.status, pending.lease_token = "running", uuid4()
        pending.lease_expires_at = pending.expires_at
        pending.started_at, pending.execution_count = pending.scheduled_at, 1
    assert (await authenticated.get(path)).json()["total"] == 4
    metrics = (await authenticated.get(f"/api/v1/monitors/{monitor['id']}/metrics")).json()
    assert metrics["sample_count"] == 0 and metrics["failure_count"] == 0
    assert metrics["uptime_percent"] is None


async def test_jobs_window_ties_pagination_monitor_filter_and_empty_page(
    api_app, authenticated, project, monitor
):
    base = await seed_jobs(api_app, monitor)
    path = f"/api/v1/projects/{project['id']}/jobs"
    params = {
        "from": base.isoformat(),
        "to": (base + timedelta(seconds=5)).isoformat(),
        "limit": 1,
        "offset": 1,
        "monitor_id": monitor["id"],
    }
    result = await authenticated.get(path, params=params)
    assert result.status_code == 200, result.text
    page = result.json()
    assert page["total"] == 3 and [row["job_id"] for row in page["items"]] == [str(UUID(int=2))]
    assert datetime.fromisoformat(page["from"]) == base
    assert datetime.fromisoformat(page["to"]) == base + timedelta(seconds=5)
    empty = (await authenticated.get(path, params={**params, "offset": 20})).json()
    assert empty["total"] == 3 and empty["items"] == []
    defaults = (await authenticated.get(path)).json()
    assert datetime.fromisoformat(defaults["to"]) - datetime.fromisoformat(
        defaults["from"]
    ) == timedelta(days=1)
    month = (await authenticated.get(path, params={"period": "30d"})).json()
    assert month["total"] == 4  # The retained job scheduled >30d ago is outside the window.


async def test_jobs_owner_active_project_and_monitor_authorization(
    api_app, authenticated, project, monitor
):
    await seed_jobs(api_app, monitor)
    path = f"/api/v1/projects/{project['id']}/jobs"
    async with api_app.state.session_factory.begin() as db:
        current = await db.get(Project, UUID(project["id"]))
        other_project = Project(owner_id=current.owner_id, name="Other", public_slug=uuid4().hex)
        foreign_owner = User(
            email="foreign-" + uuid4().hex + "@example.com", password_hash="not-a-login"
        )
        db.add_all([other_project, foreign_owner])
        await db.flush()
        foreign_project = Project(
            owner_id=foreign_owner.id, name="Foreign", public_slug=uuid4().hex
        )
        db.add(foreign_project)
        await db.flush()
        outsiders = [
            Monitor(project_id=other_project.id, name="Outside", url="https://example.com"),
            Monitor(project_id=foreign_project.id, name="Foreign", url="https://example.com"),
            Monitor(
                project_id=current.id,
                name="Archived",
                url="https://example.com",
                archived_at=utcnow(),
            ),
        ]
        db.add_all(outsiders)
        await db.flush()
        outsider_ids = [str(item.id) for item in outsiders]
    errors = []
    for identifier in [*outsider_ids, str(uuid4())]:
        response = await authenticated.get(path, params={"monitor_id": identifier})
        assert response.status_code == 404
        errors.append(response.json())
    assert all(error == errors[0] for error in errors)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api_app),
        base_url="https://app.test",
        headers={"Origin": "https://app.test", "X-Vigil-Request": "browser"},
    ) as other:
        assert (await other.get(path)).status_code == 401
        await authenticate(other, "intruder@example.com")
        assert (await other.get(path)).status_code == 404
    # Archived monitors disappear even without an explicit filter.
    async with api_app.state.session_factory.begin() as db:
        entity = await db.get(Monitor, UUID(monitor["id"]))
        entity.archived_at = utcnow()
    assert (await authenticated.get(path)).json()["total"] == 0
    assert (await authenticated.get(path, params={"monitor_id": monitor["id"]})).json() == errors[0]
    async with api_app.state.session_factory.begin() as db:
        entity = await db.get(Project, UUID(project["id"]))
        entity.archived_at = utcnow()
    assert (await authenticated.get(path)).status_code == 404


async def test_jobs_input_limits_iso_windows_and_empty_history(authenticated, project):
    path = f"/api/v1/projects/{project['id']}/jobs"
    empty = await authenticated.get(path)
    assert empty.status_code == 200 and empty.json()["items"] == [] and empty.json()["total"] == 0
    now = utcnow()
    for params in [
        {"status": "running"},
        {"period": "90d"},
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"from": "1791192852", "to": "1791192852000"},
        {"monitor_id": "private-invalid-id"},
        {"from": now.isoformat()},
        {
            "from": (now - timedelta(hours=1)).replace(tzinfo=None).isoformat(),
            "to": now.replace(tzinfo=None).isoformat(),
        },
        {"from": (now - timedelta(days=31)).isoformat(), "to": now.isoformat()},
        {"from": now.isoformat(), "to": (now + timedelta(hours=1)).isoformat()},
    ]:
        result = await authenticated.get(path, params=params)
        assert result.status_code == 422, (params, result.text)
        assert "private-invalid-id" not in result.text and "1791192852" not in result.text
    assert (await authenticated.get(path, params={"limit": 100, "offset": 0})).status_code == 200


async def test_jobs_offset_overflow_is_a_sanitized_client_error(api_app, authenticated, project):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api_app, raise_app_exceptions=False),
        base_url="https://app.test",
        cookies=authenticated.cookies,
        headers=authenticated.headers,
    ) as client:
        path = f"/api/v1/projects/{project['id']}/jobs"
        for offset in [2**63, 10**100]:
            response = await client.get(path, params={"offset": offset})
            assert response.status_code == 422, response.text
            assert str(offset) not in response.text
            assert response.json()["error"]["details"] == [
                {"field": "query.offset", "type": "less_than_equal"}
            ]
        boundary = await client.get(path, params={"offset": 2**63 - 1})
        assert boundary.status_code == 200 and boundary.json()["items"] == []


def test_jobs_dto_codes_and_offset_timestamp_are_explicit():
    codes = {
        "internal_error",
        "execution_crashed",
        "pool_exhausted",
        "blocked_destination",
        "database_error",
        "insufficient_budget",
        "deadline_exceeded",
        "execution_limit",
    }
    schema = OperationalJobOut.model_json_schema()
    assert set(schema["properties"]["error_code"]["anyOf"][0]["enum"]) == codes
    value = {
        "job_id": uuid4(),
        "monitor_id": uuid4(),
        "config_version": 1,
        "status": "expired",
        "scheduled_at": "2026-10-04T07:00:00-03:00",
        "finished_at": "2026-10-04T07:00:01-03:00",
        "execution_count": 0,
    }
    for code in [*codes, None, "remote-private-error", {"private": "password"}]:
        dto = OperationalJobOut.model_validate({**value, "error_code": code})
        assert dto.error_code == (code if isinstance(code, str) and code in codes else None)
        assert dto.scheduled_at == datetime(2026, 10, 4, 10, tzinfo=UTC)
        assert dto.finished_at == datetime(2026, 10, 4, 10, 0, 1, tzinfo=UTC)


@pytest.mark.postgres
async def test_jobs_postgres_snapshot_is_read_only(api_app, authenticated, project, monitor):
    if api_app.state.engine.dialect.name != "postgresql":
        pytest.skip("Read-only snapshot requires isolated PostgreSQL17")
    await seed_jobs(api_app, monitor)
    request = SimpleNamespace(app=api_app)
    async with observation_session(request) as db:
        assert await db.scalar(text("SHOW transaction_isolation")) == "repeatable read"
        assert await db.scalar(text("SHOW transaction_read_only")) == "on"
        with pytest.raises(DBAPIError) as error:
            await db.execute(
                update(CheckJob).where(CheckJob.id == UUID(int=1)).values(error_code=None)
            )
        assert error.value.orig.sqlstate == "25006"
        await db.rollback()
    async with api_app.state.session_factory() as db:
        assert (await db.get(CheckJob, UUID(int=1))).error_code == "insufficient_budget"


@pytest.mark.postgres
async def test_jobs_postgres_count_page_survive_distinct_writer(
    api_app, authenticated, project, monitor, monkeypatch
):
    if api_app.state.engine.dialect.name != "postgresql":
        pytest.skip("Count/page concurrency requires isolated PostgreSQL17")
    base = await seed_jobs(api_app, monitor)
    reached, committed = asyncio.Event(), asyncio.Event()
    pids = {}
    original = AsyncSession.scalar

    async def interleave(session, statement, *args, **kwargs):
        result = await original(session, statement, *args, **kwargs)
        sql = str(statement).lower()
        if not reached.is_set() and "count(*)" in sql and "from check_jobs" in sql:
            pids["reader"] = await original(session, text("SELECT pg_backend_pid()"))
            reached.set()
            await asyncio.wait_for(committed.wait(), timeout=10)
        return result

    monkeypatch.setattr(AsyncSession, "scalar", interleave)

    async def concurrent_writer():
        await asyncio.wait_for(reached.wait(), timeout=10)
        async with api_app.state.session_factory.begin() as db:
            pids["writer"] = await db.scalar(text("SELECT pg_backend_pid()"))
            await db.execute(delete(CheckJob).where(CheckJob.id == UUID(int=3)))
            db.add(
                CheckJob(
                    id=UUID(int=9),
                    monitor_id=UUID(monitor["id"]),
                    config_version=9,
                    scheduled_at=base + timedelta(seconds=6),
                    expires_at=base + timedelta(seconds=66),
                    budget_ms=5000,
                    config_snapshot={},
                    status="expired",
                    finished_at=base + timedelta(seconds=7),
                    execution_count=0,
                    error_code="deadline_exceeded",
                )
            )
            entity = await db.get(Monitor, UUID(monitor["id"]))
            entity.archived_at, entity.next_check_at = utcnow(), None
        committed.set()

    writer = asyncio.create_task(concurrent_writer())
    try:
        response = await authenticated.get(f"/api/v1/projects/{project['id']}/jobs")
        await writer
    finally:
        writer.cancel()
        await asyncio.gather(writer, return_exceptions=True)
    assert response.status_code == 200, response.text
    assert pids["reader"] != pids["writer"]
    value = response.json()
    assert value["total"] == len(value["items"]) == 4
    assert [row["job_id"] for row in value["items"]] == [str(UUID(int=i)) for i in [8, 3, 2, 1]]
    latest = await authenticated.get(f"/api/v1/projects/{project['id']}/jobs")
    assert latest.json()["total"] == 0 and latest.json()["items"] == []
