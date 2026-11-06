"""The application factory: every call builds a new, independent FastAPI app.

Per-app construction keeps tests isolated and gives later plans a place to hang the
readiness registry, limiter and cache off ``app.state``. Strict ``Settings`` are read
only in the lifespan (a missing key stops startup with uvicorn exit code 3), never here.

Database wiring (Phase 3, D-19, D-25, D-27, RESEARCH F-11). ``create_app(engine=...)`` accepts
an injected engine (tests, a caller that owns one); otherwise the lifespan builds one from
``DATABASE_URL`` unless ``DEMO_MODE`` is on, owns it and disposes it at shutdown. Whether the
``database`` readiness check exists is decided at construction from the injected engine or the
``BootSettings`` presence flags, and the check reads ``app.state.engine`` lazily, so an app
whose lifespan never ran (``TestClient(app)`` without ``with``) fails closed instead of
pretending to be ready. Apps without a database (tests, ``DEMO_MODE``) register no check.
"""

import time
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine import Engine
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from truthtrail.api import analyze
from truthtrail.api.analyze import build_analyze_router
from truthtrail.api.cache import AnalyzeCache
from truthtrail.api.catchall import CatchAllMiddleware
from truthtrail.api.db_errors import register_db_error_handlers
from truthtrail.api.health import build_health_router
from truthtrail.api.limits import LimitedRouter, UpstreamBudget, build_limiter
from truthtrail.api.problems import register_problem_handlers
from truthtrail.api.v1 import build_v1_router
from truthtrail.api.v1_cache import V1Cache
from truthtrail.api.v1_deps import utc_now
from truthtrail.core.boot import get_boot_settings
from truthtrail.core.config import get_settings
from truthtrail.core.policy import get_policy
from truthtrail.core.readiness import ReadinessRegistry
from truthtrail.db.engine import create_db_engine
from truthtrail.db.health import database_ready

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
    settings = get_settings()  # fail fast: a missing key stops startup before any upstream call
    if settings.demo_mode:
        # Fail fast on a corrupt fixture (D-19, IN-02): a cascade violation raises here and
        # uvicorn exits with "Application startup failed". Called through the module so a
        # patched loader is honoured; with demo mode off nothing is loaded.
        analyze.load_demo_fixture()
    # The engine is built lazily (no connection is opened here), so an unreachable database
    # never stops startup: /ready reports it. An injected engine belongs to its creator.
    if app.state.engine is None and not settings.demo_mode and settings.database_url is not None:
        app.state.engine = create_db_engine(settings.database_url, role="api")
        app.state.engine_owned = True
    try:
        yield
    finally:
        if app.state.engine_owned:
            app.state.engine.dispose()
            app.state.engine = None
            app.state.engine_owned = False


def register_default_checks(
    registry: ReadinessRegistry,
    get_engine: Callable[[], Engine | None] | None = None,
) -> None:
    """Extension hook: register the default dependency checks on a new registry.

    Phase 3 registers ``database`` when the app has a database, i.e. when ``get_engine`` is
    given (``create_app`` passes it for an injected engine, or for ``DATABASE_URL`` set without
    ``DEMO_MODE``). The check fails closed when the getter returns None (the lifespan has not
    built the engine) and otherwise calls ``database_ready``. Phase 4 registers ``model`` here,
    so ``/ready`` fails closed when either dependency is unavailable.
    """
    if get_engine is not None:
        getter = get_engine

        def database() -> bool:
            engine = getter()
            return engine is not None and database_ready(engine)

        registry.register("database", database)


def create_app(
    *,
    engine: Engine | None = None,
    cache_timer: Callable[[], float] | None = None,
    v1_registrars: Sequence[Callable[[LimitedRouter], None]] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> FastAPI:
    """Build a new application; two calls never share routes or state.

    ``engine`` injects a database engine that the app uses but never disposes (its creator
    does). ``cache_timer`` replaces the monotonic clock of the ``/analyze`` and ``/v1`` caches
    (used by tests so expiry never sleeps). ``v1_registrars`` replaces the default
    ``V1_REGISTRARS`` list (used by tests). ``clock`` replaces the UTC wall clock the ``/v1``
    provenance uses for staleness and ingest lag (tests control it).
    """
    app = FastAPI(
        title="TruthTrail API",
        version="0.1.0",
        description=APP_DESCRIPTION,
        lifespan=lifespan,
    )
    register_problem_handlers(app)
    register_db_error_handlers(app)
    boot = get_boot_settings()
    # Policy at construction (D-03): an invalid value stops here with a ConfigurationError that
    # names the variable, like BootSettings; the /v1 bounds and the stale threshold read it.
    app.state.policy = get_policy()
    app.state.clock = clock or utc_now
    app.state.engine = engine
    app.state.engine_owned = False
    registry = ReadinessRegistry()
    app.state.readiness = registry
    has_database = engine is not None or (boot.database_url is not None and not boot.demo_mode)
    register_default_checks(registry, (lambda: app.state.engine) if has_database else None)
    app.include_router(build_health_router())
    # Decorator-only limiting (D-23): no SlowAPIMiddleware, no default_limits.
    limiter = build_limiter()
    app.state.limiter = limiter
    app.state.analyze_cache = AnalyzeCache(timer=cache_timer or time.monotonic)
    app.state.v1_cache = V1Cache(timer=cache_timer or time.monotonic)
    app.state.upstream_budget = UpstreamBudget()
    app.include_router(build_analyze_router(limiter))
    app.include_router(build_v1_router(limiter, v1_registrars))
    # Ordering rule: the LAST middleware added is the OUTERMOST. The catch-all is added first
    # so it sits just inside CORSMiddleware; an unexpected error is then rendered as a 500
    # problem+json before the response passes back out through CORS and gains its headers.
    app.add_middleware(CatchAllMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=boot.cors_origins,
        allow_methods=["GET", "HEAD", "OPTIONS"],
        allow_credentials=False,
        # Retry-After (429/503) and X-Cache are not CORS-safelisted; without this a browser
        # frontend reads both as null.
        expose_headers=["Retry-After", "X-Cache"],
    )
    if boot.trust_proxy_headers:
        # Added LAST, so outermost: it rewrites the client address before anything else sees
        # it. Never set FORWARDED_ALLOW_IPS to "*" unless the container is reachable only
        # through the proxy: a client could then supply its own X-Forwarded-For. The server
        # must ALWAYS run with --no-proxy-headers (see truthtrail.core.boot): uvicorn's own
        # handling is on by default for loopback peers and would bypass TRUST_PROXY_HEADERS.
        trusted = [h.strip() for h in boot.forwarded_allow_ips.split(",") if h.strip()]
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=trusted)
    return app
