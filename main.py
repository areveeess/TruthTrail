from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import StringConstraints
from config import Settings, get_settings
from gnews_fetcher import fetch_news
from models import AnalyzeResponse, LiveResult, Meta
from problems import register_problem_handlers
from risk_analyzer import analyze_risk


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()  # fail fast: a missing key stops startup before any upstream call
    yield


# 200 characters matches the provider's limit for q; the pattern rejects control
# characters (also blocks log injection). Whitespace is trimmed before the checks.
SearchQuery = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200, pattern=r"^[^\x00-\x1f\x7f]+$")]

app = FastAPI(lifespan=lifespan)
register_problem_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.get("/analyze", response_model=AnalyzeResponse)
def analyze(
    query: Annotated[
        SearchQuery,
        Query(
            description="Search keywords, 1-200 characters after trimming; control characters are rejected."
        ),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AnalyzeResponse:
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
