"""The versioned ``/v1`` mount point that Phases 3 and 4 extend (D-06, D-23).

The router is empty in Phase 2 (it adds nothing to the OpenAPI document). It is a
``LimitedRouter``, so every route a later phase registers on it is rate limited by
construction, with the ``RATE_LIMIT_V1`` limit.
"""

from collections.abc import Callable, Sequence

from slowapi import Limiter

from truthtrail.api.limits import LimitedRouter
from truthtrail.core.config import get_settings

# Phase 3 and Phase 4 append their registrar functions here. Each registrar adds routes to the
# router it receives (handlers declare a ``request: Request`` parameter) and declares
# ``responses=PROBLEM_RESPONSES`` so the error shapes appear in OpenAPI.
V1_REGISTRARS: list[Callable[[LimitedRouter], None]] = []


def build_v1_router(
    limiter: Limiter,
    registrars: Sequence[Callable[[LimitedRouter], None]] | None = None,
) -> LimitedRouter:
    """Return a new ``/v1`` router; ``registrars`` defaults to ``V1_REGISTRARS``."""
    router = LimitedRouter(limiter, lambda: get_settings().rate_limit_v1, prefix="/v1")
    for registrar in V1_REGISTRARS if registrars is None else registrars:
        registrar(router)
    return router
