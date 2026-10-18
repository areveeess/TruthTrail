"""Per-client-IP rate limiting (D-10, D-23): the key function and the limiter factory.

slowapi is used through its decorators only. ``SlowAPIMiddleware`` and ``default_limits``
silently skip routes added through ``include_router`` on this FastAPI version (upstream
issue 281), so a route would look limited and not be. ``headers_enabled`` stays off: with it
on, slowapi puts ``Retry-After`` on every 200 response; the 429 handler computes the wait.
The limiter is built per app by ``create_app()`` and lives on ``app.state.limiter``; storage
is in memory, so state is per process and never shared between apps.
"""

import math
import time
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request
from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter
from slowapi import Limiter

from truthtrail.core.errors import UpstreamError

# Process-wide cap on provider calls, independent of who asks. The per-IP limit and the cache
# do not bound distinct queries, so without it a handful of clients can spend the provider's
# free-plan daily quota (about 100 calls, research A6) and lock every user out. Meant to match
# the provider plan; a retried request can cost the provider up to three units, so the cap
# slightly under-counts. In memory, so per process like the other limits.
UPSTREAM_BUDGET = "100/day"


def client_ip(request: Request) -> str:
    """Rate-limit key: the peer address the ASGI server (or trusted proxy middleware) reports."""
    return request.client.host if request.client is not None else "unknown"


def build_limiter() -> Limiter:
    """Return a new in-memory limiter keyed by client IP (one per app).

    ``key_style="endpoint"`` scopes each bucket by route function. slowapi's default (``"url"``)
    scopes it by the concrete request path, so a route with a path parameter such as
    ``/v1/claims/{id}`` would get a fresh bucket per id and never be limited.
    """
    return Limiter(key_func=client_ip, storage_uri="memory://", key_style="endpoint")


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


class UpstreamBudget:
    """A moving-window cap on provider calls shared by every client of one app."""

    def __init__(self, limit: str = UPSTREAM_BUDGET) -> None:
        self._item = parse(limit)
        self._strategy = MovingWindowRateLimiter(MemoryStorage())

    def spend(self) -> None:
        """Count one provider call, or raise a 503 ``UpstreamError`` when the budget is spent.

        Called before the provider is contacted, so an exhausted budget costs no quota. The
        error carries ``Retry-After``: the seconds until the oldest counted call leaves the
        window, at least one.
        """
        if self._strategy.hit(self._item, "upstream"):
            return
        reset_at = self._strategy.get_window_stats(self._item, "upstream").reset_time
        raise UpstreamError(
            503,
            "upstream_budget_exhausted",
            "The service has used its news provider call budget for now.",
            retry_after=max(1, math.ceil(reset_at - time.time())),
        )
