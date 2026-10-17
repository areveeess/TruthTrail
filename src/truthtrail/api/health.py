"""Liveness (``/health``) and readiness (``/ready``) at the root, unauthenticated (D-06, D-07).

``/health`` is an ``async def`` that touches nothing, so it answers whenever the process
serves requests. ``/ready`` is a sync ``def`` so blocking dependency checks (the Phase 3
database check) run in the threadpool. The registry is read from ``app.state.readiness``.
A failed readiness answer names only the failed checks; exception text is never read.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from truthtrail.api.problems import READINESS_503
from truthtrail.core.errors import problem_body, problem_response
from truthtrail.schemas.models import Health, Ready


def build_health_router() -> APIRouter:
    """Return a new router carrying ``GET /health`` and ``GET /ready`` (one per app)."""
    router = APIRouter()

    @router.get(
        "/health",
        response_model=Health,
        summary="Liveness: the process is serving requests",
    )
    async def health() -> Health:
        """Return ok whenever the process serves requests, whatever its dependencies do."""
        return Health(status="ok")

    @router.get(
        "/ready",
        response_model=Ready,
        responses={503: READINESS_503},
        summary="Readiness: every registered dependency check passes",
    )
    def ready(request: Request) -> Ready | JSONResponse:
        """Return 200 when every registered dependency check passes, otherwise 503."""
        results: dict[str, bool] = request.app.state.readiness.run()
        failed = sorted(name for name, ok in results.items() if not ok)
        if failed:
            body = problem_body(
                503,
                f"Not ready: {', '.join(failed)}.",
                "not_ready",
                source_status="not_ready",
            )
            return problem_response(503, body)
        return Ready(status="ready", checks=dict.fromkeys(results, "ok"))

    return router
