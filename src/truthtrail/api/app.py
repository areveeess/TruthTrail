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
from truthtrail.api.problems import register_problem_handlers
from truthtrail.core.config import get_settings

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


def create_app() -> FastAPI:
    """Build a new application; two calls never share routes or state."""
    app = FastAPI(
        title="TruthTrail API",
        version="0.1.0",
        description=APP_DESCRIPTION,
        lifespan=lifespan,
    )
    register_problem_handlers(app)
    app.include_router(build_analyze_router())
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )
    return app
