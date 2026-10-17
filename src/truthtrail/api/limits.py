"""Per-client-IP rate limiting (D-10, D-23): the key function and the limiter factory.

slowapi is used through its decorators only. ``SlowAPIMiddleware`` and ``default_limits``
silently skip routes added through ``include_router`` on this FastAPI version (upstream
issue 281), so a route would look limited and not be. ``headers_enabled`` stays off: with it
on, slowapi puts ``Retry-After`` on every 200 response; the 429 handler computes the wait.
The limiter is built per app by ``create_app()`` and lives on ``app.state.limiter``; storage
is in memory, so state is per process and never shared between apps.
"""

from fastapi import Request
from slowapi import Limiter


def client_ip(request: Request) -> str:
    """Rate-limit key: the peer address the ASGI server (or trusted proxy middleware) reports."""
    return request.client.host if request.client is not None else "unknown"


def build_limiter() -> Limiter:
    """Return a new in-memory limiter keyed by client IP (one per app)."""
    return Limiter(key_func=client_ip, storage_uri="memory://")
