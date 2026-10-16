"""GNews provider adapter: fetches headlines for a search query."""

import requests

from config import ConfigurationError

GNEWS_URL = "https://gnews.io/api/v4/search"


def fetch_news(query: str, api_key: str) -> list[dict]:
    """Return ``[{"title", "source", "publishedAt"}]`` for the query.

    The credential travels only in the ``X-Api-Key`` request header, never in the
    URL, because ``requests`` error text embeds the full URL. A blank key raises
    ConfigurationError.
    """
    if not api_key or not api_key.strip():
        raise ConfigurationError("GNEWS_API_KEY is not configured.")

    params = {"q": query, "lang": "en", "max": 1}
    r = requests.get(GNEWS_URL, params=params, headers={"X-Api-Key": api_key})
    data = r.json()

    articles = []
    for a in data.get("articles", []):
        articles.append({
            "title": a["title"],
            "source": a["source"]["name"],
            "publishedAt": a["publishedAt"]
        })
    return articles
