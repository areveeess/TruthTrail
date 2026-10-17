"""RFC 9457 problem+json exception handlers and OpenAPI declarations.

The body shape, ``UpstreamError`` and the rendering helpers live in
``truthtrail.core.errors`` so services never import from this layer. Nothing here
puts a credential, a provider URL, a query string or an exception message into a
body or a log line.

There is deliberately no handler for ``Exception``: it would render in Starlette's
outermost ServerErrorMiddleware, outside CORS, so its 500 would carry no CORS headers.
``truthtrail.api.catchall.CatchAllMiddleware`` renders unexpected errors instead.
"""

import logging
import math
import time
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
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


def _problem_declaration(description: str, **extra: Any) -> dict[str, Any]:
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
    429: _problem_declaration(
        "Too many requests from this client; see Retry-After (problem details).",
        headers={
            "Retry-After": {
                "description": "Seconds to wait before retrying.",
                "schema": {"type": "integer"},
            }
        },
    ),
}


# The /ready 503 (a failed dependency check) never sends Retry-After, so unlike the provider
# 503 above it declares no headers.
READINESS_503: dict[str, Any] = _problem_declaration(
    "A registered dependency check failed (problem details)."
)


async def _upstream_error_handler(request: Request, exc: UpstreamError) -> JSONResponse:
    """Render an adapter failure; 503s carry Retry-After."""
    body = problem_body(
        exc.status,
        exc.detail,
        exc.code,
        source_status="upstream_error",
        upstream=exc.upstream,
    )
    headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after is not None else None
    return problem_response(exc.status, body, headers)


async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Render a 429 with a Retry-After computed from the limiter's window (D-23).

    The wait is the time until the window of the limit that was hit resets, at least one
    second. The body never contains the client address or the limit key.
    """
    limiter = request.app.state.limiter
    item, args = request.state.view_rate_limit
    reset_at, _remaining = limiter.limiter.get_window_stats(item, *args)
    retry = max(1, math.ceil(reset_at - time.time()))
    body = problem_body(429, "Rate limit exceeded.", "rate_limited", source_status="rate_limited")
    return problem_response(429, body, {"Retry-After": str(retry)})


async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Render a 422 listing only where and why; the offending input is never echoed."""
    errors = [
        {"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]} for err in exc.errors()
    ]
    body = problem_body(
        422,
        "Request validation failed.",
        "invalid_request",
        source_status="invalid_request",
        errors=errors,
    )
    return problem_response(422, body)


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Render router errors (404, 405, ...) and keep headers such as Allow."""
    body = problem_body(exc.status_code, str(exc.detail), "http_error", source_status="error")
    return problem_response(exc.status_code, body, exc.headers)


async def _configuration_error_handler(request: Request, exc: ConfigurationError) -> JSONResponse:
    """Render a missing configuration, reachable only when the lifespan was bypassed."""
    logger.error("request rejected: service is not configured")
    body = problem_body(
        500,
        "The service is not configured.",
        "not_configured",
        source_status="not_configured",
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
                    if (
                        code in {"422", "429", "500", "502", "503"}
                        and PROBLEM_MEDIA_TYPE in content
                    ):
                        content.pop("application/json", None)
        return schema

    return openapi


def register_problem_handlers(app: FastAPI) -> None:
    """Install every problem+json exception handler on the app."""
    app.openapi = _problem_only_openapi(app)  # type: ignore[method-assign]
    # Decorator form: ``add_exception_handler`` is typed for ``Exception`` handlers only (variance),
    # ``exception_handler`` is not. The registration order is behaviour: keep it.
    app.exception_handler(UpstreamError)(_upstream_error_handler)
    # RateLimitExceeded is an HTTPException subclass; Starlette picks the handler by class
    # MRO, so this dedicated handler wins over the generic HTTP one below.
    app.exception_handler(RateLimitExceeded)(_rate_limit_handler)
    app.exception_handler(RequestValidationError)(_validation_error_handler)
    app.exception_handler(StarletteHTTPException)(_http_exception_handler)
    app.exception_handler(ConfigurationError)(_configuration_error_handler)
