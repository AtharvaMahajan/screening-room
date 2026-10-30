"""Guard test for ADR-0006: route handlers must be plain `def` functions.

FastAPI runs `def` handlers in a thread pool, so blocking database or TMDB calls
are safe there. The same call inside an `async def` handler would block the
event loop and stall every other request.
"""

import inspect

from fastapi.routing import APIRoute

from screening_room.main import ROUTERS

# Add a route here only if it does no blocking I/O, and say why.
ASYNC_ALLOWLIST: set[str] = set()


def test_no_route_handler_is_a_coroutine() -> None:
    routes = [route for router in ROUTERS for route in router.routes if isinstance(route, APIRoute)]
    # Guards against the test silently checking nothing.
    assert routes, "expected at least one API route"

    offenders = [
        route.path
        for route in routes
        if inspect.iscoroutinefunction(route.endpoint) and route.path not in ASYNC_ALLOWLIST
    ]

    assert offenders == [], f"async def handlers not in ASYNC_ALLOWLIST: {offenders}"
