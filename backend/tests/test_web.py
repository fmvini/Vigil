import shutil
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from app.config import Settings
from app.web import create_app


@pytest.fixture
def tmp_path():
    # Windows sandbox ACLs reject pytest's mode-0700 temporary directories.
    directory = (
        Path(__file__).resolve().parents[2]
        / ".cache"
        / "verification"
        / ("web-test-" + uuid4().hex)
    )
    directory.mkdir(parents=True)
    try:
        yield directory
    finally:
        assert directory.name.startswith("web-test-") and directory.parent.name == "verification"
        shutil.rmtree(directory)


def build(tmp_path):
    (tmp_path / "index.html").write_text("<html>Vigil build</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("window.Vigil = true;")
    (tmp_path / "favicon.svg").write_text("<svg></svg>")
    return tmp_path


@pytest.mark.parametrize("case", ["unset", "missing", "empty"])
def test_factory_rejects_missing_build(tmp_path, monkeypatch, case):
    monkeypatch.delenv("VIGIL_FRONTEND_DIST", raising=False)
    directory = None if case == "unset" else tmp_path / "missing" if case == "missing" else tmp_path
    with pytest.raises((ValueError, FileNotFoundError)):
        create_app(frontend_dist=directory)


async def test_same_origin_api_and_spa_keep_missing_assets_and_namespaces_404(tmp_path):
    class Engine:
        def connect(self):
            raise OSError("Database unavailable")

    app = create_app(
        frontend_dist=build(tmp_path), settings=Settings(redis_enabled=False), engine=Engine()
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for path in ["/", "/login", "/status/project", "/project/detail"]:
            response = await client.get(path)
            assert response.status_code == 200 and "Vigil build" in response.text
        assert (await client.get("/assets/app.js")).text == "window.Vigil = true;"
        assert (await client.get("/favicon.svg")).status_code == 200
        for path in [
            "/assets/missing.js",
            "/assets/missing",
            "/missing.css",
            "/brand/missing",
            "/health/no",
            "/api/v1/no",
            "/api",
            "/health",
        ]:
            response = await client.get(path)
            assert response.status_code == 404 and "Vigil build" not in response.text
        assert (await client.get("/health/live")).json() == {"status": "ok"}
        assert (await client.get("/health/ready")).status_code == 503
        config = await client.get("/api/v1/runtime-config")
        assert config.json()["minimum_interval_seconds"] == 60


async def test_static_traversal_cannot_read_outside_build(tmp_path):
    outside = tmp_path / "private.txt"
    outside.write_text("private-sentinel")
    directory = tmp_path / "dist"
    directory.mkdir()
    app = create_app(frontend_dist=build(directory), settings=Settings(redis_enabled=False))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/%2e%2e%2fprivate.txt")
        assert response.status_code == 404 and "private-sentinel" not in response.text
