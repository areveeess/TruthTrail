"""Unit tests of the AnalyzeCache mechanics (D-11), independent of HTTP.

The cache is a lock-guarded TTL and LRU map keyed by the trimmed, casefolded query plus the
demo flag. Expiry is tested with an injected fake clock, so no test sleeps.
"""

import threading
from datetime import UTC, datetime

import pytest

from truthtrail.api.cache import AnalyzeCache
from truthtrail.schemas.models import AnalyzeResponse, Meta

TTL = 600.0


class FakeClock:
    """Injectable timer: time only moves when the test says so."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _response(tag: int = 0) -> AnalyzeResponse:
    """A minimal empty live response; ``tag`` varies the timestamp so objects differ."""
    meta = Meta(
        synthetic=False,
        data_as_of=datetime(2026, 10, 17, 12, 0, tag % 60, tzinfo=UTC),
        source_status="empty",
    )
    return AnalyzeResponse(results=[], meta=meta)


def test_defaults_are_ttl_600_and_256_entries() -> None:
    cache = AnalyzeCache()

    assert cache.ttl == 600.0
    assert cache.maxsize == 256


def test_get_on_an_empty_cache_returns_none() -> None:
    assert AnalyzeCache().get("vaccine", False) is None


def test_put_then_get_returns_the_very_same_object() -> None:
    cache = AnalyzeCache()
    stored = _response()

    cache.put("vaccine", False, stored)

    assert cache.get("vaccine", False) is stored


@pytest.mark.parametrize("lookup", ["  vaccine ", "VACCINE", "Vaccine", "\tvaccine\n"])
def test_key_is_trimmed_and_casefolded(lookup: str) -> None:
    cache = AnalyzeCache()
    stored = _response()
    cache.put("Vaccine", False, stored)

    assert cache.get(lookup, False) is stored


def test_casefold_semantics_apply() -> None:
    cache = AnalyzeCache()
    stored = _response()
    cache.put("STRASSE", False, stored)

    assert cache.get("strasse", False) is stored
    assert cache.get("straße", False) is stored


def test_different_demo_flag_is_a_different_entry() -> None:
    cache = AnalyzeCache()
    live = _response(1)
    demo = _response(2)

    cache.put("vaccine", False, live)

    assert cache.get("vaccine", True) is None
    cache.put("vaccine", True, demo)
    assert cache.get("vaccine", False) is live
    assert cache.get("vaccine", True) is demo


def test_different_queries_are_different_entries() -> None:
    cache = AnalyzeCache()
    cache.put("vaccine", False, _response())

    assert cache.get("election", False) is None


def test_entry_expires_after_the_ttl_with_a_fake_clock() -> None:
    clock = FakeClock()
    cache = AnalyzeCache(ttl=TTL, timer=clock)
    stored = _response()
    cache.put("vaccine", False, stored)

    clock.advance(599)
    present = cache.get("vaccine", False)
    clock.advance(2)
    absent = cache.get("vaccine", False)

    assert present is stored
    assert absent is None


def test_bound_evicts_the_least_recently_used_entry() -> None:
    cache = AnalyzeCache(maxsize=2)
    first, second, third = _response(1), _response(2), _response(3)
    cache.put("a", False, first)
    cache.put("b", False, second)

    refreshed = cache.get("a", False)  # a read refreshes recency, so b is now the oldest
    cache.put("c", False, third)

    assert refreshed is first
    assert cache.get("b", False) is None
    assert cache.get("a", False) is first
    assert cache.get("c", False) is third


def test_get_and_put_both_take_the_lock() -> None:
    """Every access is synchronised, reads included, because expiry mutates the cache."""

    class SpyLock:
        def __init__(self) -> None:
            self.entered = 0

        def __enter__(self) -> None:
            self.entered += 1

        def __exit__(self, *exc: object) -> None:
            return None

    cache = AnalyzeCache()
    spy = SpyLock()
    cache._lock = spy  # type: ignore[assignment]

    cache.put("a", False, _response())
    after_put = spy.entered
    cache.get("a", False)

    assert after_put == 1
    assert spy.entered == 2


def test_concurrent_mixed_access_raises_nothing() -> None:
    """Smoke test: 8 threads x 500 mixed get/put on a tiny cache with a moving clock."""
    clock = FakeClock()
    cache = AnalyzeCache(ttl=5.0, maxsize=4, timer=clock)
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def worker(seed: int) -> None:
        try:
            barrier.wait()
            for i in range(500):
                key = f"q{(seed + i) % 7}"
                if i % 3 == 0:
                    cache.put(key, i % 2 == 0, _response(i))
                else:
                    cache.get(key, i % 2 == 0)
                if i % 50 == 0:
                    clock.advance(1)
        except BaseException as exc:  # collected and asserted below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
