"""The /v1 payload cache: success-only, TTL-bounded, version-keyed, per app, size-bounded,
single-flight, and behind the rate limiter (D-23, D-31, threat T-03-51).

Expiry is driven by an injected timer (nothing sleeps). The database test counts statements with
a ``before_cursor_execute`` listener: a cached read still runs the cheap version query, never the
payload query, until the data version changes.
"""

import threading
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import Request
from sqlalchemy import event, text
from sqlalchemy.engine import Engine

from truthtrail.api.limits import LimitedRouter
from truthtrail.api.problems import V1_PROBLEM_RESPONSES
from truthtrail.api.v1_cache import (
    DETAIL_TTL_SECONDS,
    LIST_TTL_SECONDS,
    STATS_TTL_SECONDS,
    TIMELINE_TTL_SECONDS,
    TREE_TTL_SECONDS,
    V1Cache,
)
from truthtrail.api.v1_deps import data_version, read_connection


class FakeTimer:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Counter:
    def __init__(self, value: Any = "v") -> None:
        self.calls = 0
        self.value = value

    def __call__(self) -> Any:
        self.calls += 1
        return (self.value, self.calls)


def test_ttls_are_short_and_positive() -> None:
    assert LIST_TTL_SECONDS == 5.0
    for ttl in (DETAIL_TTL_SECONDS, TREE_TTL_SECONDS, TIMELINE_TTL_SECONDS, STATS_TTL_SECONDS):
        assert ttl == 10.0


def test_a_hit_inside_the_ttl_does_not_recompute() -> None:
    timer = FakeTimer()
    cache = V1Cache(timer=timer)
    compute = Counter()
    first = cache.get_or_compute(("k", 1), 5.0, compute)
    timer.now += 4.999
    second = cache.get_or_compute(("k", 1), 5.0, compute)
    assert first is second
    assert compute.calls == 1


def test_an_entry_expires_exactly_after_its_ttl() -> None:
    timer = FakeTimer()
    cache = V1Cache(timer=timer)
    compute = Counter()
    cache.get_or_compute("k", 5.0, compute)
    timer.now += 5.0
    cache.get_or_compute("k", 5.0, compute)
    assert compute.calls == 2


def test_different_ttls_do_not_share_entries() -> None:
    cache = V1Cache(timer=FakeTimer())
    compute = Counter()
    cache.get_or_compute("k", 5.0, compute)
    cache.get_or_compute("k", 10.0, compute)
    assert compute.calls == 2
    assert len(cache) == 2


def test_a_changed_data_version_is_a_miss() -> None:
    cache = V1Cache(timer=FakeTimer())
    compute = Counter()
    cache.get_or_compute(("list", ("version", 1)), 5.0, compute)
    cache.get_or_compute(("list", ("version", 2)), 5.0, compute)
    cache.get_or_compute(("list", ("version", 2)), 5.0, compute)
    assert compute.calls == 2


def test_a_failing_compute_stores_nothing_and_the_next_call_recomputes() -> None:
    cache = V1Cache(timer=FakeTimer())
    calls = []

    def failing() -> Any:
        calls.append(1)
        raise RuntimeError("database down")

    with pytest.raises(RuntimeError):
        cache.get_or_compute("k", 5.0, failing)
    with pytest.raises(RuntimeError):
        cache.get_or_compute("k", 5.0, failing)
    assert len(calls) == 2
    assert len(cache) == 0
    compute = Counter()
    cache.get_or_compute("k", 5.0, compute)
    assert compute.calls == 1


def test_concurrent_identical_calls_compute_once() -> None:
    cache = V1Cache(timer=FakeTimer())
    started = threading.Event()
    release = threading.Event()
    calls: list[int] = []

    def slow() -> str:
        calls.append(1)
        started.set()
        assert release.wait(5)
        return "payload"

    results: list[str] = []
    leader = threading.Thread(target=lambda: results.append(cache.get_or_compute("k", 5.0, slow)))
    leader.start()
    assert started.wait(5)
    waiters = [
        threading.Thread(target=lambda: results.append(cache.get_or_compute("k", 5.0, slow)))
        for _ in range(4)
    ]
    for waiter in waiters:
        waiter.start()
    release.set()
    for thread in [leader, *waiters]:
        thread.join(5)
    assert calls == [1]
    assert results == ["payload"] * 5


def test_waiters_share_a_failure_and_nothing_is_stored() -> None:
    cache = V1Cache(timer=FakeTimer())
    started = threading.Event()
    release = threading.Event()

    def failing() -> str:
        started.set()
        assert release.wait(5)
        raise ValueError("boom")

    outcomes: list[str] = []

    def call() -> None:
        try:
            cache.get_or_compute("k", 5.0, failing)
        except ValueError:
            outcomes.append("raised")

    leader = threading.Thread(target=call)
    leader.start()
    assert started.wait(5)
    waiter = threading.Thread(target=call)
    waiter.start()
    release.set()
    leader.join(5)
    waiter.join(5)
    assert outcomes == ["raised", "raised"]
    assert len(cache) == 0


def test_the_size_bound_evicts_the_least_recently_used_entry() -> None:
    cache = V1Cache(maxsize=2, timer=FakeTimer())
    compute = Counter()
    cache.get_or_compute("a", 5.0, compute)
    cache.get_or_compute("b", 5.0, compute)
    cache.get_or_compute("a", 5.0, compute)  # a is now the most recently used
    cache.get_or_compute("c", 5.0, compute)  # evicts b
    assert len(cache) == 2
    calls = compute.calls
    cache.get_or_compute("a", 5.0, compute)
    assert compute.calls == calls
    cache.get_or_compute("b", 5.0, compute)
    assert compute.calls == calls + 1


def test_invalid_arguments_are_rejected() -> None:
    with pytest.raises(ValueError, match="maxsize"):
        V1Cache(maxsize=0)
    with pytest.raises(ValueError, match="ttl"):
        V1Cache().get_or_compute("k", 0, Counter())


# --- In an app ------------------------------------------------------------------------------
COMPUTED: list[str] = []


def cached_probe(router: LimitedRouter) -> None:
    @router.get("/_cached", responses=V1_PROBLEM_RESPONSES)
    def cached(request: Request) -> dict[str, int]:
        def compute() -> int:
            COMPUTED.append("x")
            return len(COMPUTED)

        return {"value": request.app.state.v1_cache.get_or_compute(("probe",), 10.0, compute)}


def test_caches_are_per_app(client_factory: Callable[..., Any]) -> None:
    COMPUTED.clear()
    one = client_factory(app_kwargs={"v1_registrars": [cached_probe]})
    two = client_factory(app_kwargs={"v1_registrars": [cached_probe]})
    assert one.get("/v1/_cached").json() == {"value": 1}
    assert one.get("/v1/_cached").json() == {"value": 1}
    assert two.get("/v1/_cached").json() == {"value": 2}
    assert one.app.state.v1_cache is not two.app.state.v1_cache


def test_the_app_cache_uses_the_injected_timer(client_factory: Callable[..., Any]) -> None:
    COMPUTED.clear()
    timer = FakeTimer()
    client = client_factory(app_kwargs={"v1_registrars": [cached_probe], "cache_timer": timer})
    assert client.get("/v1/_cached").json() == {"value": 1}
    timer.now += 10.0
    assert client.get("/v1/_cached").json() == {"value": 2}


def test_a_cache_hit_still_counts_against_the_rate_limit(
    client_factory: Callable[..., Any],
) -> None:
    COMPUTED.clear()
    client = client_factory(
        env={"RATE_LIMIT_V1": "3/minute"}, app_kwargs={"v1_registrars": [cached_probe]}
    )
    statuses = [client.get("/v1/_cached").status_code for _ in range(4)]
    assert statuses == [200, 200, 200, 429]
    assert COMPUTED == ["x"]  # one computation, three answers, then the limit


def versioned_probe(router: LimitedRouter) -> None:
    @router.get("/_versioned", responses=V1_PROBLEM_RESPONSES)
    def versioned(request: Request) -> dict[str, int]:
        with read_connection(request) as connection:
            version = data_version(connection)

            def compute() -> int:
                return int(connection.execute(text("SELECT count(*) FROM cascades")).scalar_one())

            value = request.app.state.v1_cache.get_or_compute(("n", version), 10.0, compute)
        return {"value": value}


@pytest.mark.requires_db
def test_a_cached_read_skips_the_payload_query_until_the_version_changes(
    client_factory: Callable[..., Any], make_engine: Callable[..., Engine], clean_db: str
) -> None:
    from conftest import insert_forest, set_checkpoint

    engine = make_engine(clean_db)
    statements: list[str] = []
    event.listen(
        engine,
        "before_cursor_execute",
        lambda conn, cursor, statement, *rest: statements.append(statement),
    )
    client = client_factory(app_kwargs={"engine": engine, "v1_registrars": [versioned_probe]})

    def payload_queries() -> int:
        return sum(1 for s in statements if s == "SELECT count(*) FROM cascades")

    assert client.get("/v1/_versioned").json() == {"value": 0}
    assert client.get("/v1/_versioned").json() == {"value": 0}
    assert payload_queries() == 1
    from datetime import UTC, datetime

    insert_forest(
        engine,
        [("r1", "root", None, datetime(2026, 1, 1, tzinfo=UTC), "acct1", False)],
        root_uri="r1",
    )
    assert client.get("/v1/_versioned").json() == {"value": 1}
    assert payload_queries() == 2
    set_checkpoint(engine, 1_000_000)
    assert client.get("/v1/_versioned").json() == {"value": 1}
    assert payload_queries() == 3
