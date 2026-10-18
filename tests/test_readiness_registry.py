"""Unit tests of the readiness registry rules (D-07), independent of HTTP.

Hygiene (T-02-16): the exception text of a raising check is a marker string; the
tests prove it never reaches the log, only the check name and exception class name.
"""

import logging
import threading
import time

import pytest

from truthtrail.core.readiness import ReadinessRegistry

MARKER = "SECRET-CONN-STRING-MARKER"


def test_empty_registry_runs_to_empty_dict() -> None:
    assert ReadinessRegistry().run() == {}


def test_passing_check_is_reported_true_in_registration_order() -> None:
    registry = ReadinessRegistry()
    registry.register("zeta", lambda: True)
    registry.register("alpha", lambda: True)

    result = registry.run()

    assert result == {"zeta": True, "alpha": True}
    assert list(result) == ["zeta", "alpha"]


@pytest.mark.parametrize("value", [False, None, 1, "ok", [], 0])
def test_non_true_result_is_reported_false(value: object) -> None:
    registry = ReadinessRegistry()
    registry.register("x", lambda: value)  # type: ignore[arg-type,return-value]

    assert registry.run() == {"x": False}


def test_raising_check_is_failed_and_does_not_propagate() -> None:
    registry = ReadinessRegistry()

    def boom() -> bool:
        raise RuntimeError(MARKER)

    registry.register("database", boom)
    registry.register("model", lambda: True)

    assert registry.run() == {"database": False, "model": True}


def test_raising_check_logs_class_name_only(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    registry = ReadinessRegistry()

    def boom() -> bool:
        raise RuntimeError(MARKER)

    registry.register("database", boom)
    registry.run()

    marker_in_logs = MARKER in caplog.text
    assert not marker_in_logs
    assert "RuntimeError" in caplog.text
    assert "database" in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


def test_falsy_check_logs_name_only(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    registry = ReadinessRegistry()
    registry.register("model", lambda: False)

    registry.run()

    assert "model" in caplog.text


@pytest.mark.parametrize("exc_type", [KeyboardInterrupt, SystemExit])
def test_base_exceptions_are_not_swallowed(exc_type: type[BaseException]) -> None:
    registry = ReadinessRegistry()

    def stop() -> bool:
        raise exc_type

    registry.register("x", stop)

    with pytest.raises(exc_type):
        registry.run()


@pytest.mark.parametrize("name", ["", " ", "   ", "\t\n"])
def test_blank_name_is_rejected(name: str) -> None:
    registry = ReadinessRegistry()

    with pytest.raises(ValueError, match="name"):
        registry.register(name, lambda: True)

    assert registry.run() == {}


def test_duplicate_name_is_rejected_and_first_check_is_kept() -> None:
    registry = ReadinessRegistry()
    registry.register("database", lambda: True)

    with pytest.raises(ValueError, match="already registered"):
        registry.register("database", lambda: False)

    assert registry.run() == {"database": True}


def test_check_state_is_re_evaluated_on_every_run() -> None:
    registry = ReadinessRegistry()
    state = {"up": False}
    registry.register("x", lambda: state["up"])

    first = registry.run()
    state["up"] = True
    second = registry.run()

    assert first == {"x": False}
    assert second == {"x": True}


def test_hung_check_fails_closed_within_the_timeout(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    release = threading.Event()
    registry = ReadinessRegistry(timeout=0.2)
    registry.register("database", lambda: release.wait(timeout=30) and True)
    registry.register("model", lambda: True)

    started = time.monotonic()
    try:
        result = registry.run()
        elapsed = time.monotonic() - started
    finally:
        release.set()

    assert result == {"database": False, "model": True}
    assert elapsed < 2.0
    assert "database" in caplog.text
    assert "timeout" in caplog.text


def test_a_still_running_check_is_not_started_twice_and_later_callers_fail_at_once() -> None:
    release = threading.Event()
    starts: list[int] = []

    def hung() -> bool:
        starts.append(1)
        release.wait(timeout=30)
        return True

    registry = ReadinessRegistry(timeout=0.2)
    registry.register("database", hung)
    try:
        registry.run()  # waits out the deadline once
        started = time.monotonic()
        later = [registry.run() for _ in range(20)]
        elapsed = time.monotonic() - started
    finally:
        release.set()

    assert all(r == {"database": False} for r in later)
    assert len(starts) == 1
    assert elapsed < 0.5


def test_check_recovers_once_the_hung_run_finishes() -> None:
    release = threading.Event()
    registry = ReadinessRegistry(timeout=0.1)
    registry.register("database", lambda: release.wait(timeout=30))
    first = registry.run()
    release.set()
    for thread in threading.enumerate():
        if thread.name == "readiness-database":
            thread.join(timeout=5)

    second = registry.run()

    assert first == {"database": False}
    assert second == {"database": True}


def test_concurrent_callers_share_one_run_of_a_slow_healthy_check() -> None:
    starts: list[int] = []

    def slow() -> bool:
        starts.append(1)
        time.sleep(0.2)
        return True

    registry = ReadinessRegistry(timeout=5.0)
    registry.register("database", slow)
    results: list[dict[str, bool]] = []
    threads = [threading.Thread(target=lambda: results.append(registry.run())) for _ in range(5)]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert results == [{"database": True}] * 5
    assert len(starts) == 1
