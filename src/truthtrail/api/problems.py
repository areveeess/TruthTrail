"""RFC 9457 problem+json exception handlers and OpenAPI declarations.

The body shape, ``UpstreamError`` and the rendering helpers live in
``truthtrail.core.errors`` so services never import from this layer. Nothing here
puts a credential, a provider URL, a query string or an exception message into a
body or a log line.
"""

import logging
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from truthtrail.core.config import ConfigurationError
from truthtrail.core.errors import (
    PROBLEM_MEDIA_TYPE,
    UpstreamError,
    problem_body,
    problem_response,
)
from truthtrail.schemas.models import Problem

logger = logging.getLogger(__name__)


def _problem_declaration(description: str, **extra: Any) -> dict:
    """OpenAPI response entry: the Problem model plus explicit problem+json content.

    Keep both: a bare ``content`` entry without the model renders an empty schema.
    """
    return {
        "model": Problem,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": {"$ref": "#/components/schemas/Problem"}}},
        **extra,
    }


# Error responses a route declares so /openapi.json matches what the handlers return.
PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    422: _problem_declaration("Invalid request (problem details)."),
    500: _problem_declaration("Configuration or unexpected error (problem details)."),
    502: _problem_declaration("The news provider answered badly (problem details)."),
    503: _problem_declaration(
        "The news provider is unreachable or rate limiting; see Retry-After (problem details).",
        headers={
            "Retry-After": {
                "description": "Seconds to wait before retrying.",
                "schema": {"type": "integer"},
            }
        },
    ),
}


async def _upstream_error_handler(request: Request, exc: UpstreamError) -> JSONResponse:
    """Render an adapter failure; 503s carry Retry-After."""
    body = problem_body(
        exc.status,
        exc.detail,
        exc.code,
        source_status="upstream_error",
        upstream=exc.upstream,
    )
    headers = (
        {"Retry-After": str(exc.retry_after)} if exc.retry_after is not None else None
    )
    return problem_response(exc.status, body, headers)


async def _validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Render a 422 listing only where and why; the offending input is never echoed."""
    errors = [
        {"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]}
        for err in exc.errors()
    ]
    body = problem_body(
        422,
        "Request validation failed.",
        "invalid_request",
        source_status="invalid_request",
        errors=errors,
    )
    return problem_response(422, body)


async def _http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Render router errors (404, 405, ...) and keep headers such as Allow."""
    body = problem_body(
        exc.status_code, str(exc.detail), "http_error", source_status="error"
    )
    return problem_response(exc.status_code, body, exc.headers)


async def _configuration_error_handler(
    request: Request, exc: ConfigurationError
) -> JSONResponse:
    """Render a missing configuration, reachable only when the lifespan was bypassed."""
    logger.error("request rejected: service is not configured")
    body = problem_body(
        500,
        "The service is not configured.",
        "not_configured",
        source_status="not_configured",
    )
    return problem_response(500, body)


async def _unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render any other failure with a generic detail; only the class name is logged."""
    logger.error("unexpected error: %s", type(exc).__name__)
    body = problem_body(
        500, "Unexpected error.", "internal_error", source_status="error"
    )
    return problem_response(500, body)


def _problem_only_openapi(app: FastAPI) -> Callable[[], dict[str, Any]]:
    """Wrap ``app.openapi`` so declared errors list only application/problem+json.

    FastAPI also adds an application/json entry whenever a response declares a
    ``model``; the handlers never answer that media type, so it is removed.
    """
    build = app.openapi

    def openapi() -> dict[str, Any]:
        schema = build()
        for item in schema.get("paths", {}).values():
            for operation in item.values():
                for code, response in operation.get("responses", {}).items():
                    content = response.get("content", {})
                    if code in {"422", "500", "502", "503"} and PROBLEM_MEDIA_TYPE in content:
                        content.pop("application/json", None)
        return schema

    return openapi


def register_problem_handlers(app: FastAPI) -> None:
    """Install every problem+json exception handler on the app."""
    app.openapi = _problem_only_openapi(app)  # type: ignore[method-assign]
    app.add_exception_handler(UpstreamError, _upstream_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(ConfigurationError, _configuration_error_handler)
    app.add_exception_handler(Exception, _unexpected_error_handler)
