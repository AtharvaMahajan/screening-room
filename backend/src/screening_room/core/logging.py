"""Logging (M5b): one line per event, JSON in production, readable text locally.

Every line written while a request is handled carries its `request_id` (and the
`user_id` once known), so one request's lines can be found together. Structured
fields go in `extra={"fields": {...}}`:

    logger.info("recommendations served", extra={"fields": {"latency_ms": 87}})

Never put passwords, tokens, cookies, email addresses or search text in a log
line (security.md §9).
"""

import contextvars
import json
import logging
import re
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import FastAPI, Request, Response

logger = logging.getLogger("screening_room.requests")

# The current request's fields. A dict, not separate variables: sync handlers run
# in worker threads with a COPY of the context, but the copy still points at the
# same dict, so what a dependency binds (user_id) reaches the request log line.
_request: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "request_log_context", default=None
)

# Accept a caller's request id (e.g. from a proxy) only if it looks like one.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def bind(**fields: Any) -> None:
    """Add fields (e.g. user_id) to every later log line of the current request."""
    context = _request.get()
    if context is not None:
        context.update(fields)


_default_record_factory = logging.getLogRecordFactory()


def _record_with_context(*args: Any, **kwargs: Any) -> logging.LogRecord:
    """Stamp the request's fields onto each record when it's CREATED, so any handler
    that keeps records for later (test capture, buffering) still has them."""
    record = _default_record_factory(*args, **kwargs)
    record.context = dict(_request.get() or {})
    return record


def _fields(record: logging.LogRecord) -> dict[str, Any]:
    fields: dict[str, Any] = dict(getattr(record, "context", {}))
    fields.update(getattr(record, "fields", {}))
    return fields


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
            **_fields(record),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


class TextFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s: %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        fields = _fields(record)
        if fields:
            line += " " + " ".join(f"{key}={value}" for key, value in fields.items())
        return line


class _OurHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """Marks the handler this module installs, so reconfiguring replaces only it."""


def configure_logging(log_format: Literal["json", "text"], level: str) -> None:
    """Send every logger, uvicorn's included, through one handler in one format.

    Safe to call more than once (tests build many apps): it only replaces the
    handler it added itself, so test-capture handlers stay in place.
    """
    logging.setLogRecordFactory(_record_with_context)
    root = logging.getLogger()
    for existing in [h for h in root.handlers if isinstance(h, _OurHandler)]:
        root.removeHandler(existing)
    handler = _OurHandler(sys.stderr)
    handler.setFormatter(JsonFormatter() if log_format == "json" else TextFormatter())
    root.addHandler(handler)
    root.setLevel(level)

    for name in ("uvicorn", "uvicorn.error"):  # uvicorn's own lines, in our format
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True  # replaced by our request line
    # The HTTP client logs every request with its full URL at INFO; ours logs failures.
    logging.getLogger("httpx2").setLevel(logging.WARNING)


def add_request_logging(app: FastAPI) -> None:
    """One line per request: method, path, route, status, duration. Never the
    query string (it can hold search terms) or any header."""

    @app.middleware("http")
    async def log_request(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex[:16]
        token = _request.set({"request_id": request_id})
        started = time.perf_counter()
        status = 500  # unless a response comes back
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            route = request.scope.get("route")
            fields = {
                "method": request.method,
                "path": request.url.path,
                "route": getattr(route, "path", None),
                "status": status,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }
            level = logging.ERROR if status >= 500 else logging.INFO
            logger.log(level, "request", extra={"fields": fields})
            _request.reset(token)
