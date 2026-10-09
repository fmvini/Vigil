"""Serve an explicitly supplied React build beside the API on the same origin."""

import os
import re
from pathlib import Path

from fastapi import Request
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles

from app.api.errors import ApiError
from app.main import create_app as create_api


def create_app(*, frontend_dist=None, settings=None, engine=None):
    directory = frontend_dist or os.environ.get("VIGIL_FRONTEND_DIST")
    if not directory:
        raise ValueError("An explicit frontend build directory is required")
    root = Path(directory).resolve(strict=True)
    if not root.is_dir() or not (root / "index.html").is_file():
        raise ValueError("Frontend build must contain index.html")
    app = create_api(settings, engine=engine)
    # A missing asset is a 404, never a successful SPA HTML response.
    if (root / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=root / "assets"), name="frontend-assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str, request: Request):
        if path.split("/", 1)[0] in {"api", "health", "assets"}:
            raise ApiError(404, "not_found", "Not found")
        candidate = (root / path).resolve()
        if not candidate.is_relative_to(root):
            raise ApiError(404, "not_found", "Not found")
        if candidate.is_file():
            return FileResponse(candidate)
        # Keep this route contract aligned with App.tsx and DemoApp.tsx. Unknown
        # pages still load React's shared 404 screen, with a real HTTP 404 status.
        known_page = (
            path == ""
            or re.fullmatch(r"(?:(?:privacy|terms|cookies|demo)/?|(?:demo/)?status/[^/]+/?)", path)
            is not None
        )
        if (
            not known_page
            and path
            and ("." in Path(path).name or path.split("/", 1)[0] in {"brand"})
        ):
            raise ApiError(404, "not_found", "Not found")
        return FileResponse(
            root / "index.html",
            status_code=200 if known_page else 404,
            headers={"Cache-Control": "no-cache"},
        )

    return app
