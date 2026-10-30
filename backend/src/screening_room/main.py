"""FastAPI application factory.

Run locally with:
    uv run uvicorn screening_room.main:create_app --factory --reload
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from screening_room import health
from screening_room.config import Settings, get_settings
from screening_room.db import create_db_engine, create_session_factory

# Every router the app serves. tests/unit/test_sync_handlers.py checks each
# route here, so a new module's router is registered by adding it to this list.
ROUTERS: list[APIRouter] = [health.router]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a configured app. Tests pass their own ``settings``."""
    settings = settings or get_settings()
    engine = create_db_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()  # close pooled connections on shutdown

    app = FastAPI(
        title="Screening Room API",
        lifespan=lifespan,
        # Keep everything under /api so the Vite dev proxy (and, later, a single
        # same-origin deployment) only has one prefix to route.
        docs_url="/api/docs",
        swagger_ui_oauth2_redirect_url="/api/docs/oauth2-redirect",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.session_factory = create_session_factory(engine)

    for router in ROUTERS:
        app.include_router(router)
    return app
