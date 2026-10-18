"""A registry of named dependency checks for the readiness endpoint (D-07).

Phase 3 registers a ``database`` check and Phase 4 a ``model`` check. A check is a
synchronous callable returning ``True`` when its dependency is usable. The registry
fails closed: a check that returns anything other than ``True``, or that raises an
``Exception``, is reported as failed. Only the check name and the exception class
name are logged; the exception text can carry a connection string and is never read.

A check also fails closed when it blocks. Each check runs in its own daemon thread and the
caller waits at most ``CHECK_TIMEOUT`` seconds for it, so a hung dependency (a database host
that never answers) cannot pin the shared request threadpool. A check whose previous run is
still going is not started a second time: later callers wait only until that run's deadline,
and once it has passed they fail the check at once, so at most one thread per check is ever
stuck and repeated probes do not queue up behind it.

This module imports only the standard library so ``core`` stays dependency-light.
"""

import logging
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

Check = Callable[[], bool]

# Seconds a caller waits for one check. A healthy check answers in milliseconds.
CHECK_TIMEOUT = 2.0


class _Run:
    """One execution of a check in a daemon thread, with its outcome and deadline."""

    def __init__(self, name: str, check: Check, timeout: float) -> None:
        self.ok = False
        self.raised = False  # the check raised an Exception (already logged by the worker)
        self.fatal: BaseException | None = None  # KeyboardInterrupt, SystemExit: re-raised
        self.deadline = time.monotonic() + timeout
        self._name = name
        self._check = check
        self.thread = threading.Thread(target=self._work, name=f"readiness-{name}", daemon=True)

    def _work(self) -> None:
        try:
            self.ok = self._check() is True
        except Exception as exc:
            self.raised = True
            logger.error("readiness check failed: name=%s error=%s", self._name, type(exc).__name__)
        except BaseException as exc:
            self.fatal = exc


class ReadinessRegistry:
    """Named dependency checks, evaluated in registration order."""

    def __init__(self, timeout: float = CHECK_TIMEOUT) -> None:
        self._checks: dict[str, Check] = {}
        self._timeout = timeout
        self._runs: dict[str, _Run] = {}
        self._lock = threading.Lock()

    def register(self, name: str, check: Check) -> None:
        """Add a check; a blank or duplicate name raises ValueError and changes nothing."""
        if not name.strip():
            raise ValueError("readiness check name must not be blank")
        if name in self._checks:
            raise ValueError(f"readiness check already registered: {name}")
        self._checks[name] = check

    def run(self) -> dict[str, bool]:
        """Run every check; ``True`` only where the check returned exactly ``True`` in time."""
        results: dict[str, bool] = {}
        for name, check in self._checks.items():
            results[name] = self._run_one(name, check)
        return results

    def _run_one(self, name: str, check: Check) -> bool:
        with self._lock:
            run = self._runs.get(name)
            if run is None or not run.thread.is_alive():
                run = _Run(name, check, self._timeout)
                self._runs[name] = run
                run.thread.start()
        run.thread.join(max(0.0, run.deadline - time.monotonic()))
        if run.thread.is_alive():
            logger.error("readiness check failed: name=%s error=timeout", name)
            return False
        if run.fatal is not None:
            raise run.fatal
        if not run.ok and not run.raised:
            logger.warning("readiness check failed: name=%s", name)
        return run.ok
