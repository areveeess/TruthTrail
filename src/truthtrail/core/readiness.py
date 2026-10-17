"""A registry of named dependency checks for the readiness endpoint (D-07).

Phase 3 registers a ``database`` check and Phase 4 a ``model`` check. A check is a
synchronous callable returning ``True`` when its dependency is usable. The registry
fails closed: a check that returns anything other than ``True``, or that raises an
``Exception``, is reported as failed. Only the check name and the exception class
name are logged; the exception text can carry a connection string and is never read.

This module imports only the standard library so ``core`` stays dependency-light.
"""

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

Check = Callable[[], bool]


class ReadinessRegistry:
    """Named dependency checks, evaluated in registration order."""

    def __init__(self) -> None:
        self._checks: dict[str, Check] = {}

    def register(self, name: str, check: Check) -> None:
        """Add a check; a blank or duplicate name raises ValueError and changes nothing."""
        if not name.strip():
            raise ValueError("readiness check name must not be blank")
        if name in self._checks:
            raise ValueError(f"readiness check already registered: {name}")
        self._checks[name] = check

    def run(self) -> dict[str, bool]:
        """Run every check; ``True`` only where the check returned exactly ``True``."""
        results: dict[str, bool] = {}
        for name, check in self._checks.items():
            try:
                ok = check() is True
            except Exception as exc:
                logger.error("readiness check failed: name=%s error=%s", name, type(exc).__name__)
                results[name] = False
                continue
            if not ok:
                logger.warning("readiness check failed: name=%s", name)
            results[name] = ok
        return results
