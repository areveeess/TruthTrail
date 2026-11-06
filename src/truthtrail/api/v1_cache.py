"""Per-app, success-only TTL cache of ``/v1`` payloads (D-23, T-03-51).

Modelled on the Phase 2 ``AnalyzeCache``: cachetools caches with a bounded size and an injected
timer, one lock around every access (expiry mutates the cache and the sync handlers run in the
threadpool), and single flight, so concurrent callers of one missing key share one computation.
A computation that raises stores nothing; the error reaches the computing caller and every
waiter, and the next call computes again. Errors are never cached.

Keys always include the data version (``v1_deps.data_version``), so an entry never outlives a
data change by more than its TTL. Entries hold payloads WITHOUT the provenance block: the meta is
built fresh on every request because staleness depends on the current time.

Ordering rule: the rate limiter runs before the cache (it wraps the handler), so a cache hit
still counts against the client's limit. There are no FastAPI imports here.
"""

import threading
import time
from collections.abc import Callable, Hashable
from concurrent.futures import Future
from typing import Any, TypeVar, cast

from cachetools import TTLCache

T = TypeVar("T")

# Seconds an entry stays valid, per route.
LIST_TTL_SECONDS = 5.0
DETAIL_TTL_SECONDS = 10.0
TREE_TTL_SECONDS = 10.0
TIMELINE_TTL_SECONDS = 10.0
STATS_TTL_SECONDS = 10.0
DEFAULT_MAXSIZE = 512


class V1Cache:
    """Lock-guarded TTL and LRU caches (one per TTL) with single-flight computation."""

    def __init__(
        self, maxsize: int = DEFAULT_MAXSIZE, timer: Callable[[], float] = time.monotonic
    ) -> None:
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        self._maxsize = maxsize
        self._timer = timer
        self._caches: dict[float, TTLCache[Hashable, Any]] = {}
        self._lock = threading.Lock()
        self._inflight: dict[tuple[float, Hashable], Future[Any]] = {}

    @property
    def maxsize(self) -> int:
        """Entries per TTL before the least recently used one is evicted."""
        return self._maxsize

    def _cache(self, ttl_seconds: float) -> TTLCache[Hashable, Any]:
        cache = self._caches.get(ttl_seconds)
        if cache is None:
            cache = self._caches[ttl_seconds] = TTLCache(
                maxsize=self._maxsize, ttl=ttl_seconds, timer=self._timer
            )
        return cache

    def __len__(self) -> int:
        with self._lock:
            return sum(len(cache) for cache in self._caches.values())

    def get_or_compute(self, key: Hashable, ttl_seconds: float, compute: Callable[[], T]) -> T:
        """Return the stored value for ``key`` or compute, store and return it (successes only)."""
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        flight_key = (ttl_seconds, key)
        with self._lock:
            cache = self._cache(ttl_seconds)
            if key in cache:
                return cast(T, cache[key])
            flight = self._inflight.get(flight_key)
            leader = flight is None
            if flight is None:
                flight = self._inflight[flight_key] = Future()
        if not leader:
            return cast(T, flight.result())
        try:
            value = compute()
        except BaseException as exc:
            with self._lock:
                del self._inflight[flight_key]
            flight.set_exception(exc)
            raise
        with self._lock:
            self._cache(ttl_seconds)[key] = value
            del self._inflight[flight_key]
        flight.set_result(value)
        return value
