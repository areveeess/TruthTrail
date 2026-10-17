"""HTTP-level behaviour of the /analyze TTL cache (D-11, D-20, D-23, ROADMAP criterion 5).

Repeated reads within the TTL cost no upstream quota: the second identical request is a
``X-Cache: hit`` and the provider is called once. Only successes are stored (the honest empty
result included, errors never), a hit replays the originally stored ``meta.data_as_of`` so
staleness stays visible, and the rate limit applies before the cache. Expiry uses an injected
fake clock (``create_app(cache_timer=...)``), so no test sleeps. The header is intentionally
not documented in OpenAPI.
"""

import json
from collections.abc import Callable
from typing import Any

import pytest
import requests
import responses

from truthtrail.api.analyze import FIXTURE_PATH

TTL = 600


class FakeClock:
    """Injectable cache timer: time only moves when the test advances it."""

    def __init__(self) -> None:
        self.now = 5000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def make_client(client_factory: Callable[..., Any], clock: FakeClock) -> Callable[..., Any]:
    """Build a client whose app cache runs on the fake clock."""

    def make(**kwargs: Any) -> Any:
        return client_factory(app_kwargs={"cache_timer": clock}, **kwargs)

    return make


@pytest.fixture
def upstream(mock_gnews, gnews_url, gnews_payload, gnews_article) -> None:
    mock_gnews.get(gnews_url, json=gnews_payload(gnews_article()))


def _get(client: Any, query: str = "bakery") -> Any:
    return client.get("/analyze", params={"query": query})


def test_second_identical_read_is_a_hit_with_one_upstream_call(
    make_client, mock_gnews, upstream
) -> None:
    client = make_client()

    first = _get(client)
    second = _get(client)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.headers["x-cache"] == "miss"
    assert second.headers["x-cache"] == "hit"
    assert len(mock_gnews.calls) == 1
    assert first.json() == second.json()


def test_hit_replays_the_original_data_as_of(make_client, mock_gnews, clock, upstream) -> None:
    """A hit keeps the stored provenance, so staleness stays visible to the reviewer.

    The module's ``datetime`` is deliberately not patched. ``data_as_of`` has one-second
    resolution, so the single upstream call is the assertion that rules out a recomputation,
    while the equal timestamps show the stored value was replayed.
    """
    client = make_client()

    first = _get(client)
    clock.advance(TTL - 1)
    second = _get(client)

    assert first.headers["x-cache"] == "miss"
    assert second.headers["x-cache"] == "hit"
    assert first.json()["meta"]["data_as_of"] == second.json()["meta"]["data_as_of"]
    assert first.json() == second.json()
    assert len(mock_gnews.calls) == 1


def test_entry_is_a_hit_at_599_seconds_and_a_miss_at_601(
    make_client, mock_gnews, clock, upstream
) -> None:
    client = make_client()

    _get(client)
    clock.advance(599)
    inside = _get(client)
    calls_inside = len(mock_gnews.calls)
    clock.advance(2)  # 601 s after the first (and only) store
    outside = _get(client)

    assert inside.headers["x-cache"] == "hit"
    assert calls_inside == 1
    assert outside.headers["x-cache"] == "miss"
    assert len(mock_gnews.calls) == 2


@pytest.mark.parametrize(
    ("failure", "expected_status", "failed_attempts"),
    [
        pytest.param({"json": {"errors": ["x"]}, "status": 401}, 502, 1, id="401"),
        # D-12: a transient failure is retried up to 3 attempts before it is reported.
        pytest.param({"json": {"errors": ["x"]}, "status": 503}, 502, 3, id="503"),
        pytest.param({"body": requests.exceptions.ConnectTimeout()}, 503, 3, id="timeout"),
    ],
)
def test_errors_are_never_cached(
    make_client,
    mock_gnews,
    gnews_url,
    gnews_payload,
    gnews_article,
    failure: dict[str, Any],
    expected_status: int,
    failed_attempts: int,
) -> None:
    client = make_client()
    mock_gnews.get(gnews_url, **failure)

    failed = _get(client)
    mock_gnews.replace(responses.GET, gnews_url, json=gnews_payload(gnews_article()))
    recovered = _get(client)

    assert failed.status_code == expected_status
    assert "x-cache" not in failed.headers
    assert recovered.status_code == 200
    assert recovered.headers["x-cache"] == "miss"
    assert recovered.json()["results"]
    assert len(mock_gnews.calls) == failed_attempts + 1


def test_honest_empty_result_is_cached(make_client, mock_gnews, gnews_url) -> None:
    mock_gnews.get(gnews_url, json={"totalArticles": 0, "articles": []})
    client = make_client()

    first = _get(client, "nothing-here")
    second = _get(client, "nothing-here")

    assert first.json()["meta"]["source_status"] == "empty"
    assert first.headers["x-cache"] == "miss"
    assert second.headers["x-cache"] == "hit"
    assert second.json() == first.json()
    assert len(mock_gnews.calls) == 1


def test_trimmed_and_casefolded_queries_share_an_entry(make_client, mock_gnews, upstream) -> None:
    client = make_client()

    first = _get(client, " Vaccine ")
    second = _get(client, "vaccine")
    third = _get(client, "VACCINE")

    assert first.headers["x-cache"] == "miss"
    assert second.headers["x-cache"] == "hit"
    assert third.headers["x-cache"] == "hit"
    assert len(mock_gnews.calls) == 1


def test_different_queries_are_separate_entries(make_client, mock_gnews, upstream) -> None:
    client = make_client()

    first = _get(client, "vaccine")
    second = _get(client, "election")
    again = _get(client, "vaccine")

    assert first.headers["x-cache"] == "miss"
    assert second.headers["x-cache"] == "miss"
    assert again.headers["x-cache"] == "hit"
    assert len(mock_gnews.calls) == 2


def test_demo_mode_second_identical_request_is_a_hit_equal_to_the_fixture(
    make_client, mock_gnews
) -> None:
    client = make_client(gnews_api_key=None, demo_mode="true")

    with client:
        first = _get(client, "anything")
        second = _get(client, "anything")

    committed = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert first.headers["x-cache"] == "miss"
    assert second.headers["x-cache"] == "hit"
    assert first.json() == committed
    assert second.json() == committed
    assert second.json()["meta"]["synthetic"] is True
    assert len(mock_gnews.calls) == 0


def test_invalid_request_carries_no_cache_header_and_does_not_touch_the_cache(
    make_client, mock_gnews, upstream
) -> None:
    client = make_client()

    invalid = _get(client, "")
    valid = _get(client)

    assert invalid.status_code == 422
    assert "x-cache" not in invalid.headers
    assert client.app.state.analyze_cache.get("", False) is None
    assert valid.headers["x-cache"] == "miss"
    assert len(mock_gnews.calls) == 1


def test_rate_limit_applies_before_the_cache(make_client, mock_gnews, upstream) -> None:
    """The third identical request would be a hit, but the limit answers it first."""
    client = make_client(env={"RATE_LIMIT_ANALYZE": "2/minute"})

    first = _get(client)
    second = _get(client)
    third = _get(client)

    assert first.headers["x-cache"] == "miss"
    assert second.headers["x-cache"] == "hit"
    assert third.status_code == 429
    assert "x-cache" not in third.headers
    assert len(mock_gnews.calls) == 1


def test_each_app_owns_its_cache(client_factory, mock_gnews, upstream) -> None:
    one = client_factory()
    two = client_factory()

    _get(one)
    other = _get(two)

    assert one.app.state.analyze_cache is not two.app.state.analyze_cache
    assert other.headers["x-cache"] == "miss"
    assert len(mock_gnews.calls) == 2


def test_openapi_does_not_document_the_cache_header(client) -> None:
    spec_text = json.dumps(client.get("/openapi.json").json()).lower()

    assert "x-cache" not in spec_text
