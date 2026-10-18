"""Bounded retry loop for the GNews adapter (D-12, ROADMAP criterion 5, research Pattern 8).

The adapter retries transient failures (timeouts, connect errors that are not TLS errors,
HTTP 500/502/503/504) at most three attempts in total, inside an 8 second budget, and maps
the last failure exactly as Phase 1 did. Nothing here sleeps: a ``FakeClock`` replaces the
module's ``_monotonic``, ``_sleep`` and ``_jitter`` seams.

Hygiene (T-01-02, T-01-18): no raw request URL, params dict or header dict appears in an
assert expression or message; booleans and single values are computed first.
"""

import itertools
import logging
import time

import pytest
import requests
import responses

from truthtrail.core.errors import UpstreamError
from truthtrail.services import gnews as gnews_fetcher


class FakeClock:
    """Deterministic monotonic clock whose sleep records the request and advances time."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []
        self.jitter_value = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def advance(self, delta: float) -> None:
        self.now += delta

    def jitter(self, low: float, high: float) -> float:
        return self.jitter_value


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    """Replace the adapter's time seams with a fake clock (overrides the autouse no-sleep)."""
    clock = FakeClock()
    monkeypatch.setattr(gnews_fetcher, "_monotonic", clock.monotonic)
    monkeypatch.setattr(gnews_fetcher, "_sleep", clock.sleep)
    monkeypatch.setattr(gnews_fetcher, "_jitter", clock.jitter)
    return clock


def _call_count(mock_gnews: responses.RequestsMock) -> int:
    return len(mock_gnews.calls)


def test_constants_match_the_policy() -> None:
    """D-12: three attempts, 0.3 s then 0.6 s backoff, 8 s budget, only transient statuses."""
    assert gnews_fetcher.BACKOFFS == (0.3, 0.6)
    assert gnews_fetcher.MAX_ATTEMPTS == 3
    assert gnews_fetcher.BUDGET == 8.0
    assert gnews_fetcher.CONNECT_TIMEOUT == 3.05
    assert gnews_fetcher.READ_TIMEOUT == 10.0
    retry_statuses = set(gnews_fetcher.RETRY_STATUSES)
    assert retry_statuses == {500, 502, 503, 504}


def test_real_jitter_stays_within_bounds() -> None:
    draws = [gnews_fetcher._jitter(0.0, 0.1) for _ in range(200)]
    in_bounds = all(0.0 <= d <= 0.1 for d in draws)
    assert in_bounds


def test_500_502_200_sequence_succeeds_after_two_backoffs(
    mock_gnews, gnews_url, gnews_article, gnews_payload, fake_key, fake_clock
) -> None:
    mock_gnews.get(gnews_url, status=500, json={"errors": ["simulated"]})
    mock_gnews.get(gnews_url, status=502, json={"errors": ["simulated"]})
    mock_gnews.get(gnews_url, json=gnews_payload(gnews_article()))

    result = gnews_fetcher.fetch_news("x", fake_key)

    titles = [item["title"] for item in result]
    assert titles == ["Local bakery wins award"]
    assert _call_count(mock_gnews) == 3
    assert fake_clock.sleeps == [0.3, 0.6]


def test_jitter_is_added_to_each_backoff(
    mock_gnews, gnews_url, gnews_article, gnews_payload, fake_key, fake_clock
) -> None:
    fake_clock.jitter_value = 0.05
    mock_gnews.get(gnews_url, status=503, json={})
    mock_gnews.get(gnews_url, status=503, json={})
    mock_gnews.get(gnews_url, json=gnews_payload(gnews_article()))

    gnews_fetcher.fetch_news("x", fake_key)

    rounded = [round(s, 6) for s in fake_clock.sleeps]
    assert rounded == [0.35, 0.65]


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_always_5xx_stops_at_three_calls_with_phase1_mapping(
    mock_gnews, gnews_url, fake_key, fake_clock, caplog, status: int
) -> None:
    caplog.set_level(logging.DEBUG)
    mock_gnews.get(gnews_url, status=status, json={"errors": ["simulated"]})

    with pytest.raises(UpstreamError) as excinfo:
        gnews_fetcher.fetch_news("x", fake_key)

    exc = excinfo.value
    adapter_messages = [r.getMessage() for r in caplog.records if r.name == gnews_fetcher.__name__]
    status_logged = any(f"upstream_status={status}" in m for m in adapter_messages)
    assert exc.status == 502
    assert exc.code == "upstream_bad_response"
    assert _call_count(mock_gnews) == 3
    assert fake_clock.sleeps == [0.3, 0.6]
    assert status_logged


@pytest.mark.parametrize(
    "exc_type", [requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout]
)
def test_always_timeout_stops_at_three_calls(
    mock_gnews, gnews_url, fake_key, fake_clock, exc_type
) -> None:
    mock_gnews.get(gnews_url, body=exc_type("simulated"))

    with pytest.raises(UpstreamError) as excinfo:
        gnews_fetcher.fetch_news("x", fake_key)

    exc = excinfo.value
    assert exc.status == 503
    assert exc.code == "upstream_timeout"
    assert exc.retry_after == 30
    assert _call_count(mock_gnews) == 3


@pytest.mark.parametrize(
    "exc_type", [requests.exceptions.ConnectionError, requests.exceptions.ProxyError]
)
def test_always_connection_error_stops_at_three_calls(
    mock_gnews, gnews_url, fake_key, fake_clock, exc_type
) -> None:
    mock_gnews.get(gnews_url, body=exc_type("simulated"))

    with pytest.raises(UpstreamError) as excinfo:
        gnews_fetcher.fetch_news("x", fake_key)

    exc = excinfo.value
    assert exc.status == 503
    assert exc.code == "upstream_unreachable"
    assert _call_count(mock_gnews) == 3


def test_ssl_error_is_not_retried(mock_gnews, gnews_url, fake_key, fake_clock) -> None:
    mock_gnews.get(gnews_url, body=requests.exceptions.SSLError("simulated"))

    with pytest.raises(UpstreamError) as excinfo:
        gnews_fetcher.fetch_news("x", fake_key)

    exc = excinfo.value
    assert exc.status == 503
    assert exc.code == "upstream_unreachable"
    assert _call_count(mock_gnews) == 1
    assert fake_clock.sleeps == []


@pytest.mark.parametrize(
    ("status", "expected_status", "expected_code"),
    [
        (400, 502, "upstream_bad_response"),
        (401, 502, "upstream_unauthorized"),
        (403, 502, "upstream_forbidden"),
        (404, 502, "upstream_bad_response"),
        (429, 503, "upstream_rate_limited"),
        (301, 502, "upstream_bad_response"),
        (302, 502, "upstream_bad_response"),
    ],
)
def test_non_retryable_statuses_are_called_once(
    mock_gnews, gnews_url, fake_key, fake_clock, status: int, expected_status: int, expected_code
) -> None:
    mock_gnews.get(
        gnews_url, status=status, headers={"Location": "https://elsewhere.example.org/"}, body=""
    )

    with pytest.raises(UpstreamError) as excinfo:
        gnews_fetcher.fetch_news("x", fake_key)

    exc = excinfo.value
    assert exc.status == expected_status
    assert exc.code == expected_code
    assert _call_count(mock_gnews) == 1
    assert fake_clock.sleeps == []


def test_429_keeps_the_provider_retry_after(mock_gnews, gnews_url, fake_key, fake_clock) -> None:
    mock_gnews.get(gnews_url, status=429, headers={"Retry-After": "7"}, json={})

    with pytest.raises(UpstreamError) as excinfo:
        gnews_fetcher.fetch_news("x", fake_key)

    assert excinfo.value.retry_after == 7
    assert _call_count(mock_gnews) == 1


@pytest.mark.parametrize("body", ["<html>not json</html>", '{"articles": [{"title": "a"}]}'])
def test_200_with_a_bad_payload_is_called_once(
    mock_gnews, gnews_url, fake_key, fake_clock, body: str
) -> None:
    mock_gnews.get(gnews_url, status=200, body=body)

    with pytest.raises(UpstreamError) as excinfo:
        gnews_fetcher.fetch_news("x", fake_key)

    assert excinfo.value.code == "upstream_bad_response"
    assert _call_count(mock_gnews) == 1
    assert fake_clock.sleeps == []


def test_first_attempt_connect_and_read_together_are_capped_by_the_budget(
    mock_gnews, gnews_url, gnews_article, gnews_payload, fake_key, fake_clock
) -> None:
    mock_gnews.get(gnews_url, json=gnews_payload(gnews_article()))

    gnews_fetcher.fetch_news("x", fake_key)

    connect, read = mock_gnews.calls[0].request.req_kwargs["timeout"]
    assert connect == 3.05
    assert read == pytest.approx(gnews_fetcher.BUDGET - 3.05)
    # urllib3 has no total timeout: a slow connect plus a slow read must still fit the budget.
    assert connect + read <= gnews_fetcher.BUDGET + 1e-9


def _burning_callback(
    mock_gnews: responses.RequestsMock,
    url: str,
    clock: FakeClock,
    seen: list[tuple[float, float]],
    burn: float | None,
) -> None:
    """Register a callback that spends fake time, records its timeout and raises ReadTimeout.

    ``burn`` caps the time one attempt spends; ``None`` means it spends connect plus read.
    """

    def callback(request):  # type: ignore[no-untyped-def]
        timeout = request.req_kwargs["timeout"]
        seen.append(timeout)
        # Worst case per attempt: the connect and the read both use their whole timeout.
        clock.advance(sum(timeout) if burn is None else min(sum(timeout), burn))
        raise requests.exceptions.ReadTimeout("simulated")

    mock_gnews.add_callback(responses.GET, url, callback=callback)


@pytest.mark.parametrize(("burn", "expected_calls"), [(None, 1), (4.0, 2)])
def test_slow_upstream_stops_at_the_budget(
    mock_gnews, gnews_url, fake_key, fake_clock, burn, expected_calls: int
) -> None:
    seen: list[tuple[float, float]] = []
    _burning_callback(mock_gnews, gnews_url, fake_clock, seen, burn)

    with pytest.raises(UpstreamError) as excinfo:
        gnews_fetcher.fetch_news("x", fake_key)

    exc = excinfo.value
    assert exc.status == 503
    assert exc.code == "upstream_timeout"
    assert len(seen) == expected_calls
    assert len(seen) < gnews_fetcher.MAX_ATTEMPTS
    assert fake_clock.now <= gnews_fetcher.BUDGET + 1e-9


def test_recorded_timeouts_shrink_and_total_time_stays_in_budget(
    mock_gnews, gnews_url, fake_key, fake_clock
) -> None:
    seen: list[tuple[float, float]] = []
    _burning_callback(mock_gnews, gnews_url, fake_clock, seen, 3.5)

    with pytest.raises(UpstreamError):
        gnews_fetcher.fetch_news("x", fake_key)

    reads = [read for _, read in seen]
    connects = [connect for connect, _ in seen]
    shrinking = all(a > b for a, b in itertools.pairwise(reads))
    positive = all(t > 0 for pair in seen for t in pair)
    connect_capped = all(c <= 3.05 for c in connects)
    read_capped = all(r <= 10.0 for r in reads)
    sums_within_budget = all(c + r <= gnews_fetcher.BUDGET + 1e-9 for c, r in seen)
    assert reads[0] == pytest.approx(gnews_fetcher.BUDGET - 3.05)
    assert sums_within_budget
    assert shrinking
    assert positive
    assert connect_capped
    assert read_capped
    assert fake_clock.now <= gnews_fetcher.BUDGET + 1e-9


def test_retry_is_skipped_when_the_delay_would_reach_the_budget(
    mock_gnews, gnews_url, fake_key, fake_clock
) -> None:
    seen: list[tuple[float, float]] = []
    _burning_callback(mock_gnews, gnews_url, fake_clock, seen, 7.8)

    with pytest.raises(UpstreamError) as excinfo:
        gnews_fetcher.fetch_news("x", fake_key)

    assert excinfo.value.code == "upstream_timeout"
    assert len(seen) == 1
    assert fake_clock.sleeps == []


def test_every_attempt_sends_the_same_key_and_never_follows_redirects(
    monkeypatch, mock_gnews, gnews_url, fake_key, fake_clock
) -> None:
    sent: list[dict] = []
    real_get = requests.get

    def spy(*args, **kwargs):
        sent.append({"redirects": kwargs.get("allow_redirects"), "headers": kwargs.get("headers")})
        return real_get(*args, **kwargs)

    monkeypatch.setattr(gnews_fetcher.requests, "get", spy)
    mock_gnews.get(gnews_url, status=503, json={})

    with pytest.raises(UpstreamError):
        gnews_fetcher.fetch_news("x", fake_key)

    keys = [item["headers"]["X-Api-Key"] for item in sent]
    redirects = [item["redirects"] for item in sent]
    keys_ok = keys == [fake_key] * 3
    redirects_ok = redirects == [False] * 3
    assert keys_ok
    assert redirects_ok


# --- end to end through GET /analyze (ROADMAP criterion 5) ---------------------------------


def test_analyze_failing_upstream_stops_after_three_calls(
    client, mock_gnews, gnews_url, fake_key, fake_clock
) -> None:
    mock_gnews.get(gnews_url, status=503, json={"errors": ["simulated"]})

    started = time.perf_counter()
    response = client.get("/analyze", params={"query": "x"})
    elapsed = time.perf_counter() - started

    body = response.json()
    content_type = response.headers["content-type"]
    key_in_body = fake_key in response.text
    host_in_body = "gnews.io" in response.text
    assert response.status_code == 502
    assert content_type.startswith("application/problem+json")
    assert body["code"] == "upstream_bad_response"
    assert _call_count(mock_gnews) == 3
    assert elapsed < 2.0
    assert not key_in_body
    assert not host_in_body


def test_analyze_timing_out_upstream_stops_after_three_calls(
    client, mock_gnews, gnews_url, fake_clock
) -> None:
    mock_gnews.get(gnews_url, body=requests.exceptions.ConnectTimeout("simulated"))

    started = time.perf_counter()
    response = client.get("/analyze", params={"query": "x"})
    elapsed = time.perf_counter() - started

    body = response.json()
    assert response.status_code == 503
    assert body["code"] == "upstream_timeout"
    assert response.headers.get("retry-after") == "30"
    assert _call_count(mock_gnews) == 3
    assert elapsed < 2.0


def test_analyze_slow_upstream_is_stopped_by_the_budget(
    client, mock_gnews, gnews_url, fake_clock
) -> None:
    seen: list[tuple[float, float]] = []
    _burning_callback(mock_gnews, gnews_url, fake_clock, seen, None)

    started = time.perf_counter()
    response = client.get("/analyze", params={"query": "x"})
    elapsed = time.perf_counter() - started

    body = response.json()
    assert response.status_code == 503
    assert body["code"] == "upstream_timeout"
    assert response.headers.get("retry-after") == "30"
    assert 0 < _call_count(mock_gnews) < gnews_fetcher.MAX_ATTEMPTS
    assert fake_clock.now <= gnews_fetcher.BUDGET + 1e-9
    assert elapsed < 2.0


def test_retry_logs_carry_the_attempt_number_and_no_key_or_url(
    mock_gnews, gnews_url, fake_key, fake_clock, caplog
) -> None:
    caplog.set_level(logging.DEBUG)
    leaky = requests.exceptions.ConnectTimeout(
        f"simulated https://gnews.io/api/v4/search?q=x&token={fake_key}"
    )
    mock_gnews.get(gnews_url, body=leaky)

    with pytest.raises(UpstreamError):
        gnews_fetcher.fetch_news("x", fake_key)

    records = [r for r in caplog.records if r.name == gnews_fetcher.__name__]
    messages = [r.getMessage() for r in records]
    key_in_logs = fake_key in caplog.text
    url_in_messages = any("http" in m or "gnews.io" in m for m in messages)
    attempt_logged = any(
        r.levelno == logging.INFO and "attempt=1" in r.getMessage() for r in records
    )
    second_logged = any(
        r.levelno == logging.INFO and "attempt=2" in r.getMessage() for r in records
    )
    has_warning = any(r.levelno == logging.WARNING for r in records)
    assert not key_in_logs
    assert not url_in_messages
    assert attempt_logged
    assert second_logged
    assert has_warning


def test_exhausted_retries_raise_from_none_without_key_or_url(
    mock_gnews, gnews_url, fake_key, fake_clock
) -> None:
    leaky = requests.exceptions.ConnectionError(
        f"simulated https://gnews.io/api/v4/search?q=x&token={fake_key}"
    )
    mock_gnews.get(gnews_url, body=leaky)

    with pytest.raises(UpstreamError) as excinfo:
        gnews_fetcher.fetch_news("x", fake_key)

    exc = excinfo.value
    text = f"{exc!s} {exc!r} {exc.detail}"
    key_leaked = fake_key in text
    host_leaked = "gnews.io" in text
    assert exc.__cause__ is None
    assert exc.__suppress_context__ is True
    assert not key_leaked
    assert not host_leaked


def test_a_redirect_is_never_followed_or_retried_through_the_endpoint(
    client, mock_gnews, gnews_url, gnews_article, gnews_payload, fake_clock
) -> None:
    target = "https://elsewhere.example.org/api"
    mock_gnews.get(gnews_url, status=302, headers={"Location": target}, body="")
    mock_gnews.get(target, json=gnews_payload(gnews_article()))

    response = client.get("/analyze", params={"query": "x"})

    urls_called = [call.request.url for call in mock_gnews.calls]
    redirect_followed = any(url.startswith(target) for url in urls_called)
    assert response.status_code == 502
    assert len(urls_called) == 1
    assert not redirect_followed
