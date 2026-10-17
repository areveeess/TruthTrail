"""In-process TTL cache for ``GET /analyze`` responses (D-11).

Repeated reads within the TTL are served from memory to protect the scarce provider quota.
The key is the trimmed, casefolded query plus the demo-mode flag. cachetools caches are not
thread safe and the sync handler runs in the threadpool, so every access (reads included,
because expiry mutates the cache) takes one lock. The cache stores the object it is given
and never copies or mutates it. It has no FastAPI imports.
"""

import threading
import time
from collections.abc import Callable

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
