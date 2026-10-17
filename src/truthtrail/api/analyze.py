"""The ``GET /analyze`` route, built per app by ``build_analyze_router()``.

The handler is defined inside the builder so later plans can decorate it with a per-app
limiter that must exist when the function is defined (no module-level mutable state).
"""

from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import StringConstraints
from slowapi import Limiter

from truthtrail.api.cache import AnalyzeCache
from truthtrail.api.problems import PROBLEM_RESPONSES
from truthtrail.core.cascade import cascade_events_from, validate_cascade
from truthtrail.core.config import Settings, get_settings
from truthtrail.schemas.models import AnalyzeResponse, DemoResult, LiveResult, Meta
from truthtrail.services.gnews import fetch_news
from truthtrail.services.keyword_baseline import analyze_risk

# 200 characters matches the provider's limit for q; the pattern rejects C0 and C1 control
# characters and the Unicode line/paragraph separators U+2028/U+2029 (also blocks log
# injection). Whitespace is trimmed before the checks, so only embedded ones are seen.
SearchQuery = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=200,
        pattern=r"^[^\x00-\x1f\x7f-\x9f\u2028\u2029]+$",
    ),
]

# Never a CWD-relative path: the fixture is found from this file wherever the app starts.
FIXTURE_PATH = Path(__file__).resolve().parents[1] / "data" / "demo_analyze.json"


@lru_cache(maxsize=1)
def load_demo_fixture() -> AnalyzeResponse:
    """Load and validate the committed synthetic demo fixture.

    Refuses (RuntimeError, rendered as a generic 500) any fixture whose meta is not
    labelled synthetic, so unlabelled demo data is never served. Every result's events must
    also satisfy the cascade invariants (``CascadeError`` otherwise, also a generic 500; in
    demo mode the lifespan loads the fixture, so startup fails). The events are validated,
    never reordered: the served body stays equal to the committed fixture (D-19).
    """
    fixture = AnalyzeResponse.model_validate_json(FIXTURE_PATH.read_text(encoding="utf-8"))
    if fixture.meta.synthetic is not True or fixture.meta.source_status != "fixture":
        raise RuntimeError("demo fixture is not labelled synthetic")
    for result in fixture.results:
        if isinstance(result, DemoResult):
            validate_cascade(cascade_events_from(result.events))
    return fixture


def build_analyze_router(limiter: Limiter) -> APIRouter:
    """Return a new router carrying ``GET /analyze`` (one per app), limited per client IP."""
    router = APIRouter()

    @router.get(
        "/analyze",
        response_model=AnalyzeResponse,
        responses=PROBLEM_RESPONSES,
        summary=(
            "Keyword-baseline risk flag for the most recent matching headline "
            "(flag for human review)"
        ),
    )
    @limiter.limit(lambda: get_settings().rate_limit_analyze)
    def analyze(
        request: Request,
        response: Response,
        query: Annotated[
            SearchQuery,
            Query(
                description=(
                    "Search keywords, 1-200 characters after trimming; "
                    "control and line-separator characters are rejected."
                )
            ),
        ],
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> AnalyzeResponse:
        # The limiter wrapper has already counted this request, so a cache hit still consumes
        # quota (limit before cache). The header is deliberately not documented in OpenAPI.
        cache: AnalyzeCache = request.app.state.analyze_cache
        cached = cache.get(query, settings.demo_mode)
        if cached is not None:
            response.headers["X-Cache"] = "hit"
            return cached
        # Miss: compute outside the cache lock (the fetch blocks on the network), store only a
        # success (an exception propagates before the put), then report the miss.
        result = _compute(query, settings)
        cache.put(query, settings.demo_mode, result)
        response.headers["X-Cache"] = "miss"
        return result

    return router


def _compute(query: str, settings: Settings) -> AnalyzeResponse:
    """Build the response for a cache miss: the demo fixture or a live provider fetch."""
    if settings.demo_mode:
        # The fixture is the only demo source and is reachable only through this branch.
        # The validated query is ignored in demo mode: the fixture never changes.
        return load_demo_fixture()
    api_key = (
        settings.gnews_api_key.get_secret_value() if settings.gnews_api_key is not None else ""
    )
    articles = fetch_news(query, api_key)
    # Server receive time: when this service obtained the provider response.
    data_as_of = datetime.now(UTC).replace(microsecond=0)

    results = [
        LiveResult(
            headline=article["title"],
            source=article["source"],
            published_at=article["publishedAt"],
            risk=analyze_risk(article["title"]),
            risk_method="keyword_baseline",
        )
        for article in articles
    ]
    meta = Meta(
        synthetic=False,
        data_as_of=data_as_of,
        source_status="ok" if results else "empty",
    )
    return AnalyzeResponse(results=results, meta=meta)
