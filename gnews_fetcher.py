"""GNews provider adapter: fetches headlines for a search query.

Every upstream outcome is classified into a typed ``UpstreamError`` (see
``problems.py``) so the API answers 502/503 instead of a fabricated 200. No raised
error, log record or message ever carries the credential, the provider host or a
URL.
"""

import logging
from datetime import timezone
from typing import Annotated, NoReturn, Optional

import requests
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    StringConstraints,
    ValidationError,
)

from config import ConfigurationError
from problems import UpstreamError

logger = logging.getLogger(__name__)

GNEWS_URL = "https://gnews.io/api/v4/search"
TIMEOUT = (3.05, 10)  # (connect, read) seconds
DEFAULT_RETRY_AFTER = 30
MAX_RETRY_AFTER = 3600

_NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class _Source(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: _NonEmptyStr


class _Article(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: _NonEmptyStr
    source: _Source
    publishedAt: AwareDatetime


class _Payload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    totalArticles: Optional[int] = None
    articles: Optional[list[_Article]] = None


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


def _retry_after(resp: requests.Response) -> int:
    """Seconds to wait: a numeric Retry-After capped at 3600, otherwise 30."""
    value = resp.headers.get("Retry-After", "").strip()
    if value.isascii() and value.isdigit():
        return min(int(value), MAX_RETRY_AFTER)
    return DEFAULT_RETRY_AFTER


def fetch_news(query: str, api_key: str) -> list[dict]:
    """Return ``[{"title", "source", "publishedAt"}]`` for the query.

    The credential travels only in the ``X-Api-Key`` request header, never in the
    URL, because ``requests`` error text embeds the full URL. Redirects are never
    followed, so the key cannot be forwarded to another host. A blank key raises
    ConfigurationError; any upstream failure or malformed payload raises
    UpstreamError. ``publishedAt`` is returned as a UTC ``...Z`` string.
    """
    if not api_key or not api_key.strip():
        raise ConfigurationError("GNEWS_API_KEY is not configured.")

    try:
        resp = requests.get(
            GNEWS_URL,
            params={"q": query, "lang": "en", "max": 1},
            headers={"X-Api-Key": api_key},
            timeout=TIMEOUT,
            # A redirect would re-send X-Api-Key to wherever it points (requests strips only
            # Authorization), so a 3xx is treated as a bad upstream answer instead (D-16).
            allow_redirects=False,
        )
    except requests.exceptions.Timeout:
        # Before RequestException: ConnectTimeout is both a Timeout and a ConnectionError.
        _fail(
            503,
            "upstream_timeout",
            "The news provider timed out.",
            retry_after=DEFAULT_RETRY_AFTER,
        )
    except requests.exceptions.RequestException:
        _fail(
            503,
            "upstream_unreachable",
            "The news provider could not be reached.",
            retry_after=DEFAULT_RETRY_AFTER,
        )

    status = resp.status_code
    if status == 401:
        _fail(
            502,
            "upstream_unauthorized",
            "The news provider rejected our credentials.",
            upstream_status=status,
        )
    if status == 403:
        _fail(
            502,
            "upstream_forbidden",
            "The news provider refused the request (credentials, subscription or daily quota).",
            upstream_status=status,
        )
    if status == 429:
        _fail(
            503,
            "upstream_rate_limited",
            "The news provider is rate limiting requests.",
            retry_after=_retry_after(resp),
            upstream_status=status,
        )
    if status != 200:
        _fail(
            502,
            "upstream_bad_response",
            "The news provider returned an unexpected status.",
            upstream_status=status,
        )

    # Outside the transport try: a JSON decode error is itself a RequestException.
    try:
        raw = resp.json()
    except ValueError:
        _fail(
            502,
            "upstream_bad_response",
            "The news provider returned an unreadable response.",
            upstream_status=status,
        )

    try:
        payload = _Payload.model_validate(raw)
    except ValidationError:
        _fail(
            502,
            "upstream_bad_response",
            "The news provider returned malformed article data.",
            upstream_status=status,
        )

    if payload.articles is None:
        if payload.totalArticles == 0:
            return []
        _fail(
            502,
            "upstream_bad_response",
            "The news provider returned malformed article data.",
            upstream_status=status,
        )

    return [
        {
            "title": a.title,
            "source": a.source.name,
            "publishedAt": a.publishedAt.astimezone(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
        }
        for a in payload.articles
    ]
