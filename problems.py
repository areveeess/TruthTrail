"""RFC 9457 problem+json rendering for every error the API can return.

All errors share one shape: ``type`` (``about:blank``), ``title`` (the HTTP status
phrase), integer ``status``, human ``detail`` and a stable machine-readable
``code``, plus the provenance members ``synthetic`` (false), ``source_status`` and
``data_as_of`` (null) so an error can never be mistaken for data.

Nothing here puts a credential, a provider URL, a query string or an exception
message into a body or a log line.
"""

import logging
from http import HTTPStatus
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import ConfigurationError

logger = logging.getLogger(__name__)

PROBLEM_MEDIA_TYPE = "application/problem+json"


class UpstreamError(Exception):
    """The news provider failed or answered badly.

    ``status`` is the HTTP status this API answers with (502 for a bad answer, 503
    for unreachable or throttling). ``str(exc)`` is only ``"<upstream> <code>"`` so
    it can never hold a URL or a key.
    """

    def __init__(
        self,
        status: int,
        code: str,
        detail: str,
        retry_after: Optional[int] = None,
        upstream: str = "gnews",
    ) -> None:
        super().__init__(f"{upstream} {code}")
        self.status = status
        self.code = code
        self.detail = detail
        self.retry_after = retry_after
        self.upstream = upstream


def problem_body(
    status: int, detail: str, code: str, *, source_status: str, **extensions: Any
) -> dict:
    """Build an RFC 9457 body with the provenance members always present."""
    return {
        "type": "about:blank",
        "title": HTTPStatus(status).phrase,
        "status": status,
        "detail": detail,
        "code": code,
        **extensions,
        "synthetic": False,
        "source_status": source_status,
        "data_as_of": None,
    }


def problem_response(
    status: int, body: dict, headers: Optional[dict] = None
) -> JSONResponse:
    """Render a problem body with the problem+json media type."""
    return JSONResponse(
        body, status_code=status, media_type=PROBLEM_MEDIA_TYPE, headers=headers
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


def register_problem_handlers(app: FastAPI) -> None:
    """Install every problem+json exception handler on the app."""
    app.add_exception_handler(UpstreamError, _upstream_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(ConfigurationError, _configuration_error_handler)
    app.add_exception_handler(Exception, _unexpected_error_handler)
