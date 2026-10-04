"""QA tooling guards and persisted observations in an isolated PostgreSQL schema."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from test_db_postgresql import pg_engine  # noqa: F401

from app.config import Settings
from app.db.models import CheckJob, CheckResult, Incident, Monitor, Project, User
from app.db.seed_observations_qa import main, seed_fixture, validate_target, verify_fixture
from app.db.session import create_session_factory

URL = "postgresql+asyncpg://vigil:test@127.0.0.1:55433/vigil"
NOW = datetime(2026, 10, 4, 19, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "url",
    [
        URL.replace("55433", "55432"),
        URL.replace("127.0.0.1", "remote.example.com"),
        URL.replace("/vigil", "/other"),
        URL + "?ssl=disable",
        URL.replace("postgresql+asyncpg", "postgresql"),
    ],
)
def test_seed_refuses_non_qa_targets(url):
    with pytest.raises(ValueError, match="local Compose PostgreSQL"):
        validate_target(url, Settings(_env_file=None))


@pytest.mark.parametrize(
    "settings",
    [
        {"pipeline_enabled": True},
        {"monitoring_network_enabled": True},
        {"environment": "prod", "database_url": URL, "allowed_origins": ["https://qa.test"]},
    ],
)
def test_seed_refuses_production_or_enabled_execution(settings):
    with pytest.raises(ValueError, match="both execution gates disabled"):
        validate_target(URL, Settings(_env_file=None, **settings))


def test_seed_preserves_existing_private_manifest(tmp_path, monkeypatch):
    manifest = tmp_path / "private.json"
    manifest.write_text("original", encoding="utf-8")
    monkeypatch.setenv("VIGIL_QA_DATABASE_URL", URL)
    with pytest.raises(SystemExit) as error:
        main(["seed-synthetic-qa", "--manifest", str(manifest)])
    assert error.value.code == 2
    assert manifest.read_text(encoding="utf-8") == "original"


async def test_seed_metrics_public_filter_and_caller_rollback(pg_engine):  # noqa: F811
    factory = create_session_factory(pg_engine)
    async with factory() as db:
        async with db.begin():
            manifest = await seed_fixture(db, now=NOW)
            await verify_fixture(db, manifest)
            target = next(m for m in manifest["monitors"] if m["role"] == "target")
            metrics = manifest["expected"]["per_monitor"][target["id"]]
            assert metrics["24h"]["sample_count"] == 24
            assert metrics["7d"]["sample_count"] == 72
            assert metrics["7d"]["uptime_percent"] == 50
            assert metrics["7d"]["average_latency_ms"] == 275
            assert metrics["7d"]["p95_latency_ms"] == pytest.approx(432.5)
            assert manifest["expected"]["project"]["7d"]["sample_count"] == 76
            assert manifest["expected"]["public"]["7d"]["sample_count"] == 73
            assert manifest["expected"]["incidents"]["project"] == {
                "all": 38,
                "open": 2,
                "closed": 36,
            }
            assert manifest["expected"]["incidents"]["public"]["open"] == 1
            assert (
                await db.scalar(
                    select(func.count()).select_from(CheckJob).where(CheckJob.status != "completed")
                )
                == 0
            )
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(Monitor)
                    .where(Monitor.next_check_at.is_not(None))
                )
                == 0
            )
            assert manifest["external_checks_executed"] is False
            await db.rollback()
        for model in (User, Project, Monitor, CheckJob, CheckResult, Incident):
            assert await db.scalar(select(func.count()).select_from(model)) == 0
