"""In-process TTL cache for ``GET /analyze`` responses (D-11).

Repeated reads within the TTL are served from memory to protect the scarce provider quota.
The key is the trimmed, casefolded query plus the demo-mode flag. cachetools caches are not
thread safe and the sync handler runs in the threadpool, so every access (reads included,
because expiry mutates the cache) takes one lock. The cache stores the object it is given
and never copies or mutates it. ``get_or_compute`` adds single-flight: concurrent callers of
one missing key share a single computation, so a cold or just-expired popular entry costs one
provider call, not one per request. It has no FastAPI imports.
"""

import threading
import time
from collections.abc import Callable
from concurrent.futures import Future

from cachetools import TTLCache

from truthtrail.schemas.models import AnalyzeResponse

CacheKey = tuple[str, bool]


def _key(query: str, demo: bool) -> CacheKey:
    return (query.strip().casefold(), demo)


class AnalyzeCache:
    """Lock-guarded TTL and LRU cache of successful ``AnalyzeResponse`` objects."""

    def __init__(
        self,
        ttl: float = 600.0,
        maxsize: int = 256,
        timer: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl
        self._maxsize = maxsize
        self._cache: TTLCache[CacheKey, AnalyzeResponse] = TTLCache(
            maxsize=maxsize, ttl=ttl, timer=timer
        )
        self._lock = threading.Lock()
        # Computations in progress, by key; guarded by the same lock as the cache.
        self._inflight: dict[CacheKey, Future[AnalyzeResponse]] = {}

    @property
    def ttl(self) -> float:
        """Seconds an entry stays valid."""
        return self._ttl

    @property
    def maxsize(self) -> int:
        """Maximum number of entries before the least recently used one is evicted."""
        return self._maxsize

    def get(self, query: str, demo: bool) -> AnalyzeResponse | None:
        """Return the stored response for this query and mode, or None."""
        with self._lock:
            return self._cache.get(_key(query, demo))

    def put(self, query: str, demo: bool, value: AnalyzeResponse) -> None:
        """Store a successful response (the object itself, not a copy)."""
        with self._lock:
            self._cache[_key(query, demo)] = value

    def get_or_compute(
        self, query: str, demo: bool, compute: Callable[[], AnalyzeResponse]
    ) -> tuple[AnalyzeResponse, bool]:
        """Return ``(response, shared)`` for this query and mode, computing at most once at a time.

        ``shared`` is False only for the caller that ran ``compute`` (a miss that paid for the
        work); it is True for a stored entry and for a caller that waited on another caller's
        computation, since neither spent a second provider call. ``compute`` runs outside the
        lock (it blocks on the network). A success is stored; an exception is never stored and
        is re-raised to the computing caller and to every caller that was waiting on it, so a
        failing provider is asked once, not once per waiter.
        """
        key = _key(query, demo)
        with self._lock:
            stored = self._cache.get(key)
            if stored is not None:
                return stored, True
            flight = self._inflight.get(key)
            leader = flight is None
            if flight is None:
                flight = self._inflight[key] = Future()
        if not leader:
            return flight.result(), True
        try:
            value = compute()
        except BaseException as exc:
            with self._lock:
                del self._inflight[key]
            flight.set_exception(exc)
            raise
        with self._lock:
            self._cache[key] = value
            del self._inflight[key]
        flight.set_result(value)
        return value, False
