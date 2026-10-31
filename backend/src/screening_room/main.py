"""FastAPI application factory.

Run locally with (see README.md for why --reload-dir matters):
    uv run uvicorn screening_room.main:create_app --factory --reload --reload-dir src
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI

from screening_room import health
from screening_room.config import Settings, get_settings
from screening_room.core.errors import ERROR_RESPONSES, register_error_handlers
from screening_room.db import create_db_engine, create_session_factory
from screening_room.modules.catalog import router as catalog_router
from screening_room.modules.catalog.providers.tmdb.client import TmdbClient
from screening_room.modules.catalog.providers.tmdb.provider import TmdbProvider
from screening_room.modules.discovery import router as discovery_router
from screening_room.modules.identity import router as identity_router
from screening_room.modules.identity.csrf import csrf_protect
from screening_room.modules.library import router as library_router
from screening_room.modules.profile import router as profile_router

# Every router the app serves. tests/unit/test_sync_handlers.py checks each
# route here, so a new module's router is registered by adding it to this list.
ROUTERS: list[APIRouter] = [
    health.router,
    identity_router.router,
    catalog_router.router,
    profile_router.router,
    discovery_router.router,
    library_router.router,
]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a configured app. Tests pass their own ``settings``."""
    settings = settings or get_settings()
    engine = create_db_engine(settings.database_url)
    # Without a token the app still runs; title pages show the data we have.
    tmdb_client = (
        TmdbClient(
            settings.tmdb_api_token.get_secret_value(),
            rate_limit_rps=settings.tmdb_rate_limit_rps,
            max_attempts=2,  # user-facing: at most one retry (catalog-ingestion.md §10)
        )
        if settings.tmdb_api_token
        else None
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()  # close pooled connections on shutdown
        if tmdb_client is not None:
            tmdb_client.close()

    app = FastAPI(
        title="Screening Room API",
        lifespan=lifespan,
        # Keep everything under /api so the Vite dev proxy (and, later, a single
        # same-origin deployment) only has one prefix to route.
        docs_url="/api/docs",
        swagger_ui_oauth2_redirect_url="/api/docs/oauth2-redirect",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        # Every route can fail with the standard error format; say so in OpenAPI.
        responses=ERROR_RESPONSES,
        # Name each operation after its handler function ("health"), rather than
        # FastAPI's default "health_api_health_get", for readable generated types.
        generate_unique_id_function=lambda route: route.name,
        # Runs before every route's own dependencies, so CSRF and Origin are
        # checked before any route-level authentication (security.md §5.3).
        # Safe methods (GET, HEAD, OPTIONS) return immediately.
        dependencies=[Depends(csrf_protect)],
    )
    app.state.settings = settings
    app.state.session_factory = create_session_factory(engine)
    app.state.catalog_provider = TmdbProvider(tmdb_client) if tmdb_client else None
    register_error_handlers(app)

    for router in ROUTERS:
        app.include_router(router)
    return app
