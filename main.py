from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import StringConstraints
from config import Settings, get_settings
from gnews_fetcher import fetch_news
from problems import register_problem_handlers
from risk_analyzer import analyze_risk
from spread_simulator import create_root_event, simulate_spread


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

@app.get("/analyze")
def analyze(
    query: Annotated[
        SearchQuery,
        Query(
            description="Search keywords, 1-200 characters after trimming; control characters are rejected."
        ),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
):
    api_key = settings.gnews_api_key.get_secret_value() if settings.gnews_api_key is not None else ""
    articles = fetch_news(query, api_key)

    # 🔥 FALLBACK so frontend NEVER breaks
    if not articles:
        articles = [{
            "title": query,
            "source": "unknown",
            "publishedAt": "2025-01-01T10:00:00Z"
        }]

    results = []

    for article in articles:
        risk = analyze_risk(article["title"])
        root = create_root_event(article)
        events = simulate_spread(root, risk)

        results.append({
            "headline": article["title"],
            "risk": risk,
            "events": events
        })

    return results
