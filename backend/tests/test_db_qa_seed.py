"""Synthetic QA fixtures use real migrations, isolated owners and caller transactions."""

from datetime import timedelta
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from sqlalchemy import func, select
from test_db_postgresql import NOW, seed
from test_db_postgresql import pg_engine as pg_engine

from app.config import Settings
from app.db.models import CheckJob, CheckResult, Incident, Monitor, Project, User
from app.db.seed_observations_qa import main, seed_fixture, validate_target, verify_fixture
from app.db.session import create_session_factory
from app.main import create_app
from app.security import verify_password

URL = "postgresql+asyncpg://qa:private-password@127.0.0.1:55433/vigil"


@pytest.mark.parametrize(
    "url",
    [
        URL.replace("55433", "55432"),
        URL.replace("55433", "5432"),
        URL.replace("127.0.0.1", "remote.invalid"),
        URL.replace("/vigil", "/other"),
        URL + "?search_path=other",
        URL.replace("postgresql+asyncpg", "postgresql"),
        "sqlite+aiosqlite:///:memory:",
    ],
)
def test_cli_target_guard_rejects_runtime_and_other_databases(url):
    with pytest.raises(ValueError, match="local Compose"):
        validate_target(url, Settings(database_url=URL))


@pytest.mark.parametrize(
    "settings",
    [
        Settings(database_url=URL, environment="prod", allowed_origins=["https://qa.test"]),
        Settings(database_url=URL, pipeline_enabled=True),
        Settings(database_url=URL, monitoring_network_enabled=True),
    ],
)
def test_seed_refuses_production_and_external_execution_gates(settings):
    with pytest.raises(ValueError, match="gates disabled"):
        validate_target(URL, settings)


def test_seed_requires_explicit_database_and_preserves_private_manifest(monkeypatch):
    monkeypatch.delenv("VIGIL_QA_DATABASE_URL", raising=False)
    output = Path("existing-private-fixture.json")
    with pytest.raises(SystemExit) as error:
        main(["seed-synthetic-qa", "--manifest", str(output)])
    assert error.value.code == 2
    monkeypatch.setenv("VIGIL_QA_DATABASE_URL", URL)
    monkeypatch.setattr(Path, "exists", lambda path: True)

    def reject_manifest_write(*args, **kwargs):
        raise AssertionError("Existing private fixture must not be opened or overwritten")

    monkeypatch.setattr(Path, "open", reject_manifest_write)
    with pytest.raises(SystemExit) as error:
        main(["seed-synthetic-qa", "--manifest", str(output)])
    assert error.value.code == 2


@pytest.mark.asyncio
async def test_fixture_persists_exact_global_metrics_isolation_and_public_subset(pg_engine):
    factory = create_session_factory(pg_engine)
    async with pg_engine.begin() as connection:
        existing_owner, existing_project, existing_monitor = await seed(connection)
        before = (
            await connection.execute(
                select(Monitor.__table__).where(Monitor.id == existing_monitor)
            )
        ).one()
    async with factory.begin() as db:
        fixture = await seed_fixture(db)
    async with factory.begin() as db:
        await verify_fixture(db, fixture)
        unchanged = (
            await db.execute(select(Monitor.__table__).where(Monitor.id == existing_monitor))
        ).one()
        assert unchanged == before
        assert (await db.get(Project, existing_project)).owner_id == existing_owner
        owner = await db.get(User, UUID(fixture["owner_id"]))
        assert owner.id != existing_owner
        assert verify_password(fixture["login"]["password"], owner.password_hash)
        assert await db.scalar(select(func.count()).select_from(User)) == 2
        qa_monitors = (
            await db.scalars(
                select(Monitor).where(Monitor.project_id == UUID(fixture["project"]["id"]))
            )
        ).all()
        assert len(qa_monitors) == 6
        assert all(m.url.startswith("https://qa-") and ".invalid/" in m.url for m in qa_monitors)
        assert all(m.next_check_at is None and m.interval_seconds == 3600 for m in qa_monitors)
        assert await db.scalar(select(func.count()).select_from(CheckResult)) == 76
        assert (
            await db.scalar(
                select(func.count()).select_from(CheckJob).where(CheckJob.status != "completed")
            )
            == 0
        )
        assert await db.scalar(select(func.count()).select_from(Incident)) == 38
        assert (
            await db.scalar(
                select(func.count())
                .select_from(CheckResult)
                .where(CheckResult.degradation_reason == "retry_recovered")
            )
            == 9
        )
    target = next(m for m in fixture["monitors"] if m["role"] == "target")
    assert target["checks_total"] == 72 and target["incidents_total"] == 36
    assert target["health_status"] == "degraded" and target["freshness"] == "fresh"
    periods = fixture["expected"]["per_monitor"][target["id"]]
    assert periods["24h"]["sample_count"] == 24
    assert periods["7d"]["sample_count"] == periods["30d"]["sample_count"] == 72
    assert periods["24h"]["p95_latency_ms"] == pytest.approx(444.5)
    assert periods["7d"]["p95_latency_ms"] == pytest.approx(432.5)
    assert periods["7d"]["average_latency_ms"] == 275
    assert fixture["external_checks_executed"] is False
    project = fixture["expected"]["project"]
    assert project["24h"]["sample_count"] == 28
    assert project["24h"]["uptime_percent"] == 50
    assert project["24h"]["p95_latency_ms"] == pytest.approx(770)
    assert project["7d"]["p95_latency_ms"] == pytest.approx(487.5)
    assert project["7d"]["sample_count"] == 76
    assert fixture["expected"]["public"]["7d"]["sample_count"] == 73
    assert fixture["expected"]["incidents"]["project"] == {"all": 38, "open": 2, "closed": 36}
    assert fixture["expected"]["incidents"]["public"] == {"all": 37, "open": 1, "closed": 36}
    assert len(periods["24h"]["series"]) > 1 and len(periods["7d"]["series"]) >= 3

    # Use the product API against committed fixture rows, without monitor HTTP calls.
    settings = Settings(environment="test", allowed_origins=["https://qa.test"])
    app = create_app(settings, engine=pg_engine)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="https://qa.test",
            headers={"Origin": "https://qa.test", "X-Vigil-Request": "browser"},
        ) as client:
            login = await client.post("/api/v1/auth/login", json=fixture["login"])
            assert login.status_code == 200
            assert (await client.get(f"/api/v1/projects/{existing_project}")).status_code == 404
            metrics = await client.get(f"/api/v1/monitors/{target['id']}/metrics?period=24h")
            assert metrics.status_code == 200 and metrics.json()["sample_count"] == 24
            first = await client.get(f"/api/v1/monitors/{target['id']}/checks?period=7d&limit=20")
            second = await client.get(
                f"/api/v1/monitors/{target['id']}/checks?period=7d&limit=20&offset=20"
            )
            assert first.json()["total"] == second.json()["total"] == 72
            assert len(first.json()["items"]) == len(second.json()["items"]) == 20
            assert {row["id"] for row in first.json()["items"]}.isdisjoint(
                row["id"] for row in second.json()["items"]
            )
            closed = await client.get(
                f"/api/v1/projects/{fixture['project']['id']}/incidents?monitor_id={target['id']}&state=closed&period=7d&offset=20"
            )
            assert closed.status_code == 200 and closed.json()["total"] == 36
            assert len(closed.json()["items"]) == 16
            public = await client.get(f"/api/v1/public/status/{fixture['project']['public_slug']}")
            assert public.status_code == 200
            assert {m["id"] for m in public.json()["monitors"]} == {
                m["id"] for m in fixture["monitors"] if m["is_public"]
            }
            sentinel = next(m for m in fixture["monitors"] if m["role"] == "private")
            assert sentinel["id"] not in public.text and sentinel["name"] not in public.text
            incidents = await client.get(
                f"/api/v1/public/status/{fixture['project']['public_slug']}/incidents?state=open"
            )
            assert incidents.json()["total"] == 1


@pytest.mark.asyncio
async def test_seed_rollback_removes_only_new_fixture_and_no_internal_commit(pg_engine):
    factory = create_session_factory(pg_engine)
    async with pg_engine.begin() as connection:
        existing_owner, _, _ = await seed(connection)
    with pytest.raises(RuntimeError, match="rollback QA"):
        async with factory.begin() as db:
            await seed_fixture(db, now=NOW + timedelta(hours=1))
            raise RuntimeError("rollback QA")
    async with factory() as db:
        assert (await db.scalars(select(User.id))).all() == [existing_owner]
        for model in (Project, Monitor):
            assert await db.scalar(select(func.count()).select_from(model)) == 1
        for model in (CheckJob, CheckResult, Incident):
            assert await db.scalar(select(func.count()).select_from(model)) == 0
