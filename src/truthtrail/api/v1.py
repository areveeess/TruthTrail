"""The versioned ``/v1`` mount point that Phases 3 and 4 extend (D-06, D-23).

The router was empty in Phase 2; Phase 3 registers the cascade and stats routes (plan
03-07). It is a ``LimitedRouter``, so every route registered on it is rate limited by
construction, with the ``RATE_LIMIT_V1`` limit.
"""

from collections.abc import Callable, Sequence

from slowapi import Limiter

from truthtrail.api.limits import LimitedRouter
from truthtrail.api.v1_cascades import register_cascades
from truthtrail.api.v1_stats import register_stats
from truthtrail.core.config import get_settings

# Phase 3 and Phase 4 append their registrar functions here. Each registrar adds routes to the
# router it receives (handlers declare a ``request: Request`` parameter) and declares
# ``responses=V1_PROBLEM_RESPONSES`` (422, 429, 500, 503; no 502) so the error shapes appear in
# OpenAPI.
V1_REGISTRARS: list[Callable[[LimitedRouter], None]] = [register_cascades, register_stats]


def build_v1_router(
    limiter: Limiter,
    registrars: Sequence[Callable[[LimitedRouter], None]] | None = None,
) -> LimitedRouter:
    """Return a new ``/v1`` router; ``registrars`` defaults to ``V1_REGISTRARS``."""
    router = LimitedRouter(limiter, lambda: get_settings().rate_limit_v1, prefix="/v1")
    for registrar in V1_REGISTRARS if registrars is None else registrars:
        registrar(router)
    return router
