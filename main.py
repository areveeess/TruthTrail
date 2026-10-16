from contextlib import asynccontextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import StringConstraints
from config import Settings, get_settings
from gnews_fetcher import fetch_news
from models import AnalyzeResponse, LiveResult, Meta
from problems import PROBLEM_RESPONSES, register_problem_handlers
from risk_analyzer import analyze_risk


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()  # fail fast: a missing key stops startup before any upstream call
    yield


# 200 characters matches the provider's limit for q; the pattern rejects control
# characters (also blocks log injection). Whitespace is trimmed before the checks.
SearchQuery = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200, pattern=r"^[^\x00-\x1f\x7f]+$")]

# Never a CWD-relative path: the fixture is found from this file wherever the app starts.
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "demo_analyze.json"


@lru_cache(maxsize=1)
def load_demo_fixture() -> AnalyzeResponse:
    """Load and validate the committed synthetic demo fixture.

    Refuses (RuntimeError, rendered as a generic 500) any fixture whose meta is not
    labelled synthetic, so unlabelled demo data is never served.
    """
    fixture = AnalyzeResponse.model_validate_json(FIXTURE_PATH.read_text(encoding="utf-8"))
    if fixture.meta.synthetic is not True or fixture.meta.source_status != "fixture":
        raise RuntimeError("demo fixture is not labelled synthetic")
    return fixture


APP_DESCRIPTION = (
    "Prototype under reconstruction. Ranks recent news headlines with a keyword baseline "
    "so a human reviewer can decide what to look at first. "
    "Every result is a flag for human review, not a verdict on whether a claim is true. "
    "Every response carries "
    "provenance (synthetic, data_as_of, source_status). Synthetic demo data is served "
    "only when DEMO_MODE=true and is labelled synthetic: true."
)

app = FastAPI(
    title="TruthTrail API",
    version="0.1.0",
    description=APP_DESCRIPTION,
    lifespan=lifespan,
)
register_problem_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.get(
    "/analyze",
    response_model=AnalyzeResponse,
    responses=PROBLEM_RESPONSES,
    summary="Keyword-baseline risk flags for recent headlines (flag for human review)",
)
def analyze(
    query: Annotated[
        SearchQuery,
        Query(
            description="Search keywords, 1-200 characters after trimming; control characters are rejected."
        ),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AnalyzeResponse:
    if settings.demo_mode:
        # The fixture is the only demo source and is reachable only through this branch.
        # The validated query is ignored in demo mode: the fixture never changes.
        return load_demo_fixture()
    api_key = settings.gnews_api_key.get_secret_value() if settings.gnews_api_key is not None else ""
    articles = fetch_news(query, api_key)
    # Server receive time: when this service obtained the provider response.
    data_as_of = datetime.now(timezone.utc).replace(microsecond=0)

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
