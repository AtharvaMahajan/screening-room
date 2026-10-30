"""One error format for every failure (project-structure.md §7).

Every error response has the same shape, whatever caused it:

    {"error": {"code": "not_found", "message": "Not Found"}}

`code` is stable and machine-readable, so the frontend can branch on it.
`message` is for people. Validation errors (422) also list the fields that
failed under `details`.

Domain code raises `AppError`. The handlers below also translate the errors
FastAPI and Starlette raise themselves (unknown route, invalid body, crash).
"""

import logging
from collections.abc import Mapping
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


# --- Response schema (also appears in OpenAPI, and so in the frontend types) ---


class FieldError(BaseModel):
    field: str  # dotted location, e.g. "body.email"
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[FieldError] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


# Documents the error format on every route. Declaring "4XX" also stops FastAPI
# from adding its own 422 schema, which wouldn't match what we actually return.
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    "4XX": {"model": ErrorResponse, "description": "Client error"},
    "5XX": {"model": ErrorResponse, "description": "Server error"},
}


# --- The exception domain code raises -------------------------------------------


class AppError(Exception):
    """An expected failure with a stable code, e.g. AppError(404, "title_not_found", ...)."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


# --- Handlers ---------------------------------------------------------------------


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: list[FieldError] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(exclude_none=True),  # omit "details" when there are none
        headers=headers,
    )


def _status_code_name(status_code: int) -> str:
    """404 -> "not_found", 405 -> "method_not_allowed"."""
    try:
        return HTTPStatus(status_code).phrase.lower().replace(" ", "_").replace("-", "_")
    except ValueError:
        return "http_error"


def handle_app_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return _error_response(exc.status_code, exc.code, exc.message)


def handle_http_exception(_: Request, exc: Exception) -> JSONResponse:
    """Errors raised by the framework: unknown route (404), wrong method (405), ..."""
    assert isinstance(exc, StarletteHTTPException)
    message = exc.detail if isinstance(exc.detail, str) else HTTPStatus(exc.status_code).phrase
    # Keep headers such as `Allow` on a 405.
    return _error_response(
        exc.status_code, _status_code_name(exc.status_code), message, headers=exc.headers
    )


def handle_validation_error(_: Request, exc: Exception) -> JSONResponse:
    """Invalid path, query or body (422)."""
    assert isinstance(exc, RequestValidationError)
    details = [
        FieldError(field=".".join(str(part) for part in error["loc"]), message=error["msg"])
        for error in exc.errors()
        # Deliberately not copying error["input"]: it echoes what the client sent,
        # which could be a password.
    ]
    return _error_response(422, "validation_failed", "The request is invalid.", details)


def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    """A bug. Log it in full; tell the client nothing about the internals."""
    logger.exception("Unhandled error", exc_info=exc)
    return _error_response(500, "internal_error", "An unexpected error occurred.")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
