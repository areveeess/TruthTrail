"""GNews provider adapter: fetches the most recent matching headline (``max=1``) for a search query.

Every upstream outcome is classified into a typed ``UpstreamError`` (see
``core/errors.py``) so the API answers 502/503 instead of a fabricated 200. No raised
error, log record or message ever carries the credential, the provider host or a
URL.
"""

import logging
import random
import time
from dataclasses import dataclass
from datetime import UTC
from typing import Annotated, NoReturn

import requests
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    StringConstraints,
    ValidationError,
)

from truthtrail.core.config import ConfigurationError, is_header_safe_key
from truthtrail.core.errors import UpstreamError

logger = logging.getLogger(__name__)

GNEWS_URL = "https://gnews.io/api/v4/search"
DEFAULT_RETRY_AFTER = 30
MAX_RETRY_AFTER = 3600

# Bounded retry policy (D-12): at most MAX_ATTEMPTS requests in total, BACKOFFS[i] seconds
# (plus jitter) before attempt i + 2, and BUDGET seconds for the whole call. Only transient
# failures are retried: timeouts, connect errors that are not TLS errors, and RETRY_STATUSES.
# 4xx (including 429), 3xx and a 200 with a bad payload are never retried.
BACKOFFS = (0.3, 0.6)
MAX_ATTEMPTS = 3
BUDGET = 8.0
CONNECT_TIMEOUT = 3.05
READ_TIMEOUT = 10.0
RETRY_STATUSES = frozenset({500, 502, 503, 504})

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

    totalArticles: int | None = None
    articles: list[_Article] | None = None


def _monotonic() -> float:
    """Clock seam: tests replace this module global to control time."""
    return time.monotonic()


def _sleep(seconds: float) -> None:
    """Sleep seam: tests replace this module global so nothing sleeps for real."""
    time.sleep(seconds)


def _jitter(low: float, high: float) -> float:
    """Jitter seam: a random extra delay in [low, high] so clients do not retry in lockstep."""
    return random.uniform(low, high)  # noqa: S311 - backoff jitter, not security


@dataclass(frozen=True)
class _Failure:
    """One classified failed attempt: the arguments for ``_fail`` plus whether to retry."""

    status: int
    code: str
    detail: str
    retryable: bool = False
    retry_after: int | None = None
    upstream_status: int | None = None


def _fail(
    status: int,
    code: str,
    detail: str,
    *,
    retry_after: int | None = None,
    upstream_status: int | None = None,
) -> NoReturn:
    """Log the failure class and raise a key-free, URL-free UpstreamError.

    Only the code and the upstream status are logged; the cause is dropped with
    ``from None`` because transport error text can embed the request URL.
    """
    logger.warning("gnews request failed: code=%s upstream_status=%s", code, upstream_status)
    raise UpstreamError(status, code, detail, retry_after) from None


def _retry_after(resp: requests.Response) -> int:
    """Seconds to wait: a numeric Retry-After capped at 3600, otherwise 30."""
    value = resp.headers.get("Retry-After", "").strip()
    if value.isascii() and value.isdigit():
        return min(int(value), MAX_RETRY_AFTER)
    return DEFAULT_RETRY_AFTER


def _request_once(
    params: dict[str, str | int], api_key: str, timeout: tuple[float, float]
) -> requests.Response | _Failure:
    """Send one request; return the response, or the classified transport failure."""
    try:
        return requests.get(
            GNEWS_URL,
            params=params,
            headers={"X-Api-Key": api_key},
            timeout=timeout,
            # A redirect would re-send X-Api-Key to wherever it points (requests strips only
            # Authorization), so a 3xx is treated as a bad upstream answer instead (D-16).
            allow_redirects=False,
        )
    except requests.exceptions.Timeout:
        # Before ConnectionError: ConnectTimeout is both a Timeout and a ConnectionError.
        return _Failure(
            503,
            "upstream_timeout",
            "The news provider timed out.",
            retryable=True,
            retry_after=DEFAULT_RETRY_AFTER,
        )
    except requests.exceptions.ConnectionError as exc:
        # Includes SSLError and ProxyError: the provider could not be reached at all. A TLS
        # failure is not transient, so only the other connect errors are retried.
        return _Failure(
            503,
            "upstream_unreachable",
            "The news provider could not be reached.",
            retryable=not isinstance(exc, requests.exceptions.SSLError),
            retry_after=DEFAULT_RETRY_AFTER,
        )
    except requests.exceptions.RequestException:
        # Reached, but the answer was unusable (broken chunked/compressed body, too many
        # redirects, invalid URL, ...): a bad upstream answer, not an outage (D-07).
        return _Failure(
            502, "upstream_bad_response", "The news provider returned an unusable response."
        )


def _classify_status(resp: requests.Response) -> _Failure | None:
    """Map a non-200 status to its Phase 1 failure; ``None`` means the status is 200."""
    status = resp.status_code
    if status == 200:
        return None
    if status == 401:
        return _Failure(
            502,
            "upstream_unauthorized",
            "The news provider rejected our credentials.",
            upstream_status=status,
        )
    if status == 403:
        return _Failure(
            502,
            "upstream_forbidden",
            "The news provider refused the request (credentials, subscription or daily quota).",
            upstream_status=status,
        )
    if status == 429:
        return _Failure(
            503,
            "upstream_rate_limited",
            "The news provider is rate limiting requests.",
            retry_after=_retry_after(resp),
            upstream_status=status,
        )
    return _Failure(
        502,
        "upstream_bad_response",
        "The news provider returned an unexpected status.",
        retryable=status in RETRY_STATUSES,
        upstream_status=status,
    )


def fetch_news(query: str, api_key: str) -> list[dict[str, str]]:
    """Return ``[{"title", "source", "publishedAt"}]`` for the query.

    The credential travels only in the ``X-Api-Key`` request header, never in the
    URL, because ``requests`` error text embeds the full URL. Redirects are never
    followed, so the key cannot be forwarded to another host. A blank or
    header-unsafe key raises ConfigurationError; any upstream failure or malformed
    payload raises UpstreamError. ``publishedAt`` is returned as a UTC ``...Z`` string.
    """
    if not api_key or not api_key.strip():
        raise ConfigurationError("GNEWS_API_KEY is not configured.")
    if not is_header_safe_key(api_key):
        # Never sent: requests would fail locally and the failure would look like a provider outage.
        raise ConfigurationError("GNEWS_API_KEY is not a valid header value.")

    params: dict[str, str | int] = {"q": query, "lang": "en", "max": 1}
    # Known limitation: requests read timeouts apply per socket read, so a server that drips
    # bytes can exceed BUDGET. GNews bodies are tiny (max=1), so this is accepted (T-02-35).
    start = _monotonic()
    # Used only when the budget ran out before any attempt could start.
    failure = _Failure(503, "upstream_timeout", "The news provider timed out.", retry_after=30)
    resp: requests.Response | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        remaining = BUDGET - (_monotonic() - start)
        if remaining <= 0:
            break
        outcome = _request_once(
            params, api_key, (min(CONNECT_TIMEOUT, remaining), min(READ_TIMEOUT, remaining))
        )
        if isinstance(outcome, requests.Response):
            status_failure = _classify_status(outcome)
            if status_failure is None:
                resp = outcome
                break
            failure = status_failure
        else:
            failure = outcome
        if not failure.retryable or attempt == MAX_ATTEMPTS:
            break
        delay = BACKOFFS[attempt - 1] + _jitter(0.0, 0.1)
        if (_monotonic() - start) + delay >= BUDGET:
            break
        # Only the attempt number, code and upstream status: never the URL, key or error text.
        logger.info(
            "gnews retry: attempt=%s code=%s upstream_status=%s",
            attempt,
            failure.code,
            failure.upstream_status,
        )
        _sleep(delay)

    if resp is None:
        _fail(
            failure.status,
            failure.code,
            failure.detail,
            retry_after=failure.retry_after,
            upstream_status=failure.upstream_status,
        )

    status = resp.status_code

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
            "publishedAt": a.publishedAt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        for a in payload.articles
    ]
