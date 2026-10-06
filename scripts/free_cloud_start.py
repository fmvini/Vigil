"""Explicit deployment bootstrap and same-origin web entrypoint.

Only the private vigil schema is created; migrations are applied before serving.
This is never invoked by the API's normal startup or readiness probe.
"""

import asyncio
import json
import os
import sys
from urllib.parse import urlsplit


def configure(environment):
    from free_cloud_checks import configuration

    # Reuse strict provider validation without enabling execution on the API.
    _, values = configuration(environment)
    origin = environment.get("RENDER_EXTERNAL_URL") or environment.get("VIGIL_PUBLIC_ORIGIN", "")
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Provide the exact public HTTPS origin")
    values["VIGIL_ALLOWED_ORIGINS"] = json.dumps([origin.rstrip("/")])
    values["VIGIL_PIPELINE_ENABLED"] = "false"
    values["VIGIL_MONITORING_NETWORK_ENABLED"] = "false"
    values["VIGIL_FRONTEND_DIST"] = environment.get("VIGIL_FRONTEND_DIST", "/app/static")
    if environment.get("VIGIL_DATABASE_SSL_CA_FILE"):
        values["VIGIL_DATABASE_SSL_CA_FILE"] = environment["VIGIL_DATABASE_SSL_CA_FILE"]
    return values


async def initialize_schema():
    from sqlalchemy import text
    from sqlalchemy.pool import NullPool

    from app.config import Settings
    from app.db.session import create_engine

    settings = Settings()
    if settings.database_schema != "vigil" or not settings.database_ssl:
        raise ValueError("Free deployment requires the private vigil schema and verified TLS")
    options = settings.database_options
    options.pop("pool_size")
    options.pop("max_overflow")
    engine = create_engine(settings.database_url, poolclass=NullPool, **options)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            await connection.execute(text("SET LOCAL statement_timeout = '60s'"))
            await connection.execute(text("CREATE SCHEMA IF NOT EXISTS vigil"))
            # Keep the application's schema private to its database owner.
            await connection.execute(text("REVOKE ALL ON SCHEMA vigil FROM PUBLIC"))
    finally:
        await engine.dispose()


def main():
    try:
        os.environ.update(configure(os.environ))
        port = int(os.environ.get("PORT", "8000"))
        if not 1 <= port <= 65535:
            raise ValueError("Invalid listener port")
        asyncio.run(initialize_schema())
        from alembic import command
        from alembic.config import Config

        command.upgrade(Config("/app/alembic.ini"), "head")
    except Exception as error:
        print("cloud_start_failed:" + type(error).__name__, file=sys.stderr, flush=True)
        return 1
    os.execvp(
        "uvicorn",
        [
            "uvicorn",
            "app.web:create_app",
            "--factory",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
            "--no-access-log",
            "--proxy-headers",
        ],
    )


if __name__ == "__main__":
    raise SystemExit(main())
