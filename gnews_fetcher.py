"""GNews provider adapter: fetches headlines for a search query."""

import logging
from typing import NoReturn, Optional

import requests

from config import ConfigurationError
from problems import UpstreamError

logger = logging.getLogger(__name__)

GNEWS_URL = "https://gnews.io/api/v4/search"
TIMEOUT = (3.05, 10)  # (connect, read) seconds
DEFAULT_RETRY_AFTER = 30
MAX_RETRY_AFTER = 3600


def _fail(
    status: int,
    code: str,
    detail: str,
    *,
    retry_after: Optional[int] = None,
    upstream_status: Optional[int] = None,
) -> NoReturn:
    """Log the failure class and raise a key-free, URL-free UpstreamError.

    Only the code and the upstream status are logged; the cause is dropped with
    ``from None`` because transport error text can embed the request URL.
    """
    logger.warning(
        "gnews request failed: code=%s upstream_status=%s", code, upstream_status
    )
    raise UpstreamError(status, code, detail, retry_after) from None


def fetch_news(query: str, api_key: str) -> list[dict]:
    """Return ``[{"title", "source", "publishedAt"}]`` for the query.

    The credential travels only in the ``X-Api-Key`` request header, never in the
    URL, because ``requests`` error text embeds the full URL. A blank key raises
    ConfigurationError; an upstream failure raises UpstreamError.
    """
    if not api_key or not api_key.strip():
        raise ConfigurationError("GNEWS_API_KEY is not configured.")

    params = {"q": query, "lang": "en", "max": 1}
    resp = requests.get(
        GNEWS_URL, params=params, headers={"X-Api-Key": api_key}, timeout=TIMEOUT
    )
    if resp.status_code == 401:
        _fail(
            502,
            "upstream_unauthorized",
            "The news provider rejected our credentials.",
            upstream_status=401,
        )
    data = resp.json()

    articles = []
    for a in data.get("articles", []):
        articles.append({
            "title": a["title"],
            "source": a["source"]["name"],
            "publishedAt": a["publishedAt"]
        })
    return articles
