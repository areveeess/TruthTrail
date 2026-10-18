"""A process-wide cap on provider calls bounds quota use whoever asks (review WR-05).

The per-IP limit and the cache do not bound distinct queries: one client could spend the
provider's daily quota with unique queries. ``UpstreamBudget`` counts provider calls across all
clients and answers 503 with ``Retry-After`` before contacting the provider once it is spent.
Cache hits and demo mode cost nothing.
"""

from collections.abc import Callable
from typing import Any

import pytest

from truthtrail.api.limits import UPSTREAM_BUDGET, UpstreamBudget
from truthtrail.core.errors import UpstreamError

PROBLEM = "application/problem+json"


@pytest.fixture
def upstream(mock_gnews, gnews_url, gnews_payload, gnews_article) -> None:
    mock_gnews.get(gnews_url, json=gnews_payload(gnews_article()))


def _client(client_factory: Callable[..., Any], limit: str, **kwargs: Any) -> Any:
    client = client_factory(env={"RATE_LIMIT_ANALYZE": "100/minute"}, **kwargs)
    client.app.state.upstream_budget = UpstreamBudget(limit)
    return client


def test_default_budget_matches_the_free_plan_quota() -> None:
    assert UPSTREAM_BUDGET == "100/day"


def test_spend_raises_503_with_retry_after_when_the_budget_is_gone() -> None:
    budget = UpstreamBudget("2/hour")
    budget.spend()
    budget.spend()

    with pytest.raises(UpstreamError) as excinfo:
        budget.spend()

    exc = excinfo.value
    assert exc.status == 503
    assert exc.code == "upstream_budget_exhausted"
    assert exc.retry_after is not None
    assert 1 <= exc.retry_after <= 3600


def test_distinct_queries_from_one_client_stop_at_the_budget(
    client_factory, mock_gnews, upstream
) -> None:
    client = _client(client_factory, "3/hour")

    statuses = [
        client.get("/analyze", params={"query": f"unique topic {n}"}).status_code for n in range(6)
    ]
    last = client.get("/analyze", params={"query": "unique topic 99"})

    assert statuses == [200, 200, 200, 503, 503, 503]
    assert len(mock_gnews.calls) == 3
    body = last.json()
    assert last.headers["content-type"].startswith(PROBLEM)
    assert body["code"] == "upstream_budget_exhausted"
    assert body["source_status"] == "upstream_error"
    assert body["synthetic"] is False
    assert int(last.headers["retry-after"]) >= 1
    assert "x-cache" not in last.headers


def test_budget_is_shared_across_client_addresses(client_factory, mock_gnews, upstream) -> None:
    from fastapi.testclient import TestClient

    first = _client(client_factory, "2/hour", client=("198.51.100.1", 1))
    second = TestClient(first.app, client=("198.51.100.2", 1))
    third = TestClient(first.app, client=("198.51.100.3", 1))

    statuses = [
        c.get("/analyze", params={"query": f"topic {n}"}).status_code
        for n, c in enumerate((first, second, third))
    ]

    # Each address is far below its own per-IP limit, yet the shared budget is spent.
    assert statuses == [200, 200, 503]
    assert len(mock_gnews.calls) == 2


def test_cache_hits_are_served_after_the_budget_is_spent(
    client_factory, mock_gnews, upstream
) -> None:
    client = _client(client_factory, "1/hour")

    first = client.get("/analyze", params={"query": "bakery"})
    repeat = client.get("/analyze", params={"query": "bakery"})
    other = client.get("/analyze", params={"query": "something else"})

    assert first.status_code == 200
    assert repeat.status_code == 200
    assert repeat.headers["x-cache"] == "hit"
    assert other.status_code == 503
    assert len(mock_gnews.calls) == 1


def test_a_failed_fetch_still_spends_a_unit(client_factory, mock_gnews, gnews_url) -> None:
    mock_gnews.get(gnews_url, status=401, json={"errors": ["x"]})
    client = _client(client_factory, "1/hour")

    failed = client.get("/analyze", params={"query": "a"})
    refused = client.get("/analyze", params={"query": "b"})

    assert failed.status_code == 502
    assert refused.status_code == 503
    assert len(mock_gnews.calls) == 1


def test_demo_mode_never_spends_the_budget(client_factory, mock_gnews) -> None:
    client = _client(client_factory, "1/hour", gnews_api_key=None, demo_mode="true")

    with client:
        statuses = [client.get("/analyze", params={"query": f"q{n}"}).status_code for n in range(4)]

    assert statuses == [200, 200, 200, 200]
    assert len(mock_gnews.calls) == 0


def test_each_app_owns_its_budget(client_factory) -> None:
    one = client_factory()
    two = client_factory()

    assert one.app.state.upstream_budget is not two.app.state.upstream_budget
