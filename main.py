from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import Settings, get_settings
from gnews_fetcher import fetch_news
from risk_analyzer import analyze_risk
from spread_simulator import create_root_event, simulate_spread


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()  # fail fast: a missing key stops startup before any upstream call
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.get("/analyze")
def analyze(query: str, settings: Annotated[Settings, Depends(get_settings)]):
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
