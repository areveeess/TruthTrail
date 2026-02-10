from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from gnews_fetcher import fetch_news
from risk_analyzer import analyze_risk
from spread_simulator import create_root_event, simulate_spread

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.get("/analyze")
def analyze(query: str):
    articles = fetch_news(query)

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
