import asyncio
from contextlib import asynccontextmanager

from anyio import CapacityLimiter
from fastapi import FastAPI
from redis.asyncio import Redis

from app.api.auth import router as auth_router
from app.api.errors import ApiError, install_handlers
from app.api.events import router as events_router
from app.api.jobs import router as jobs_router
from app.api.observations import router as observations_router
from app.api.resources import router as resource_router
from app.config import Settings
from app.db.session import create_engine, create_session_factory
from app.observability import RequestActivityMiddleware, configure_activity_logging
from app.readiness import database_ready, migration_head
from app.services.events import EventHub


def create_app(settings: Settings | None = None, *, engine=None) -> FastAPI:
    settings = settings or Settings()
    owned_engine = engine is None
    if engine is None:
        engine = create_engine(
            settings.database_url, allow_sqlite_for_tests=settings.environment == "test"
        )
    sqlite_test_engine = (
        not owned_engine and getattr(getattr(engine, "dialect", None), "name", None) == "sqlite"
    )
    try:
        expected_head = migration_head()
    except Exception:
        # Missing/ambiguous packaged migrations fail readiness, not liveness/import.
        expected_head = None

    @asynccontextmanager
    async def lifespan(app):
        yield
        await app.state.event_hub.close()
        if owned_engine:
            await engine.dispose()

    app = FastAPI(
        title="Vigil API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.environment == "prod" else "/docs",
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.password_limiter = CapacityLimiter(4)
    app.state.event_hub = EventHub(
        redis_factory=lambda: Redis.from_url(
            settings.redis_url, socket_connect_timeout=1, socket_timeout=2, max_connections=5
        )
    )
    install_handlers(app)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(resource_router, prefix="/api/v1")
    app.include_router(observations_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")
    app.include_router(events_router, prefix="/api/v1")

    @app.middleware("http")
    async def private_response_headers(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/v1"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/health/live", tags=["health"])
    async def live():
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def ready():
        try:
            async with asyncio.timeout(settings.readiness_timeout_seconds):
                await database_ready(
                    engine, expected_head=expected_head, sqlite_test_engine=sqlite_test_engine
                )
        except Exception:
            raise ApiError(503, "not_ready", "Database is not ready") from None
        return {"status": "ok", "dependencies": {"database": "ok"}}

    # FastAPI's included routers may preserve the original APIRoute in scope.
    # Match declared route identities rather than reading raw paths or private internals.
    routes = {id(route): route.path for route in app.routes if hasattr(route, "path")}
    for router in (auth_router, resource_router, observations_router, jobs_router, events_router):
        routes.update({id(route): "/api/v1" + route.path for route in router.routes})
    app.add_middleware(RequestActivityMiddleware, route_templates=routes)
    return app


configure_activity_logging()
app = create_app()
