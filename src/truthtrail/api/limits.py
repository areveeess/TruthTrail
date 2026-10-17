"""Per-client-IP rate limiting (D-10, D-23): the key function and the limiter factory.

slowapi is used through its decorators only. ``SlowAPIMiddleware`` and ``default_limits``
silently skip routes added through ``include_router`` on this FastAPI version (upstream
issue 281), so a route would look limited and not be. ``headers_enabled`` stays off: with it
on, slowapi puts ``Retry-After`` on every 200 response; the 429 handler computes the wait.
The limiter is built per app by ``create_app()`` and lives on ``app.state.limiter``; storage
is in memory, so state is per process and never shared between apps.
"""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request
from slowapi import Limiter


def client_ip(request: Request) -> str:
    """Rate-limit key: the peer address the ASGI server (or trusted proxy middleware) reports."""
    return request.client.host if request.client is not None else "unknown"


def build_limiter() -> Limiter:
    """Return a new in-memory limiter keyed by client IP (one per app)."""
    return Limiter(key_func=client_ip, storage_uri="memory://")


class LimitedRouter(APIRouter):
    """An ``APIRouter`` that rate limits every route registered on it (fail closed, D-23).

    Forgetting a limit on a ``/v1`` route is therefore impossible: ``add_api_route`` wraps the
    endpoint with ``limiter.limit(limit)`` before FastAPI sees it. The limit is a callable
    evaluated per request, so building the router never reads the environment.

    A handler registered here must declare a ``request: Request`` parameter; slowapi raises at
    registration otherwise, which is the intended loud failure. Each route gets its own bucket
    keyed by module and function name, so route function names must be unique within a module.
    """

    def __init__(self, limiter: Limiter, limit: Callable[[], str], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._limiter = limiter
        self._limit = limit

    def add_api_route(self, path: str, endpoint: Callable[..., Any], **kwargs: Any) -> None:
        super().add_api_route(path, self._limiter.limit(self._limit)(endpoint), **kwargs)
