"""The application factory: every call builds a new, independent FastAPI app.

Per-app construction keeps tests isolated and gives later plans a place to hang the
readiness registry, limiter and cache off ``app.state``. Strict ``Settings`` are read
only in the lifespan (a missing key stops startup with uvicorn exit code 3), never here.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from truthtrail.api.analyze import build_analyze_router
from truthtrail.api.catchall import CatchAllMiddleware
from truthtrail.api.health import build_health_router
from truthtrail.api.problems import register_problem_handlers
from truthtrail.core.boot import get_boot_settings
from truthtrail.core.config import get_settings
from truthtrail.core.readiness import ReadinessRegistry

APP_DESCRIPTION = (
    "Prototype under reconstruction. Labels the most recent matching news headline "
    "(the provider is asked for one article per query) with a keyword-baseline flag. "
    "Nothing is ranked or sorted. "
    "Every result is a flag for human review, not a verdict on whether a claim is true. "
    "Every response carries "
    "provenance (synthetic, data_as_of, source_status). Synthetic demo data is served "
    "only when DEMO_MODE=true and is labelled synthetic: true."
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    get_settings()  # fail fast: a missing key stops startup before any upstream call
    yield


def register_default_checks(registry: ReadinessRegistry) -> None:
    """Extension hook: register the default dependency checks on a new registry.

    Empty in Phase 2. Phase 3 registers the ``database`` check and Phase 4 the ``model``
    check here, so ``/ready`` starts failing closed when either dependency is unavailable.
    """


def create_app() -> FastAPI:
    """Build a new application; two calls never share routes or state."""
    app = FastAPI(
        title="TruthTrail API",
        version="0.1.0",
        description=APP_DESCRIPTION,
        lifespan=lifespan,
    )
    register_problem_handlers(app)
    registry = ReadinessRegistry()
    app.state.readiness = registry
    register_default_checks(registry)
    app.include_router(build_health_router())
    app.include_router(build_analyze_router())
    boot = get_boot_settings()
    # Ordering rule: the LAST middleware added is the OUTERMOST. The catch-all is added first
    # so it sits just inside CORSMiddleware; an unexpected error is then rendered as a 500
    # problem+json before the response passes back out through CORS and gains its headers.
    app.add_middleware(CatchAllMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=boot.cors_origins,
        allow_methods=["GET", "HEAD", "OPTIONS"],
        allow_credentials=False,
    )
    return app
