"""The engine factory against a real PostgreSQL (D-19, D-25 groundwork, D-28).

Timeouts, the pool, the UTC session and the failure classes are observed on the server, not
mocked. Every engine comes from ``make_engine``, which disposes it (RESEARCH F-09). No test
prints or asserts a full URL.
"""

import time
from datetime import timedelta
from typing import Any

import psycopg
import pytest
from sqlalchemy import exc, text
from sqlalchemy.engine import make_url

from truthtrail.db.engine import (
    CONNECT_TIMEOUT_SECONDS,
    LOCK_TIMEOUT_MS,
    POOL_TIMEOUT_SECONDS,
    STATEMENT_TIMEOUT_MS,
)

pytestmark = pytest.mark.requires_db


def _show(engine: Any, setting: str) -> str:
    with engine.connect() as connection:
        value: str = connection.execute(text(f"SHOW {setting}")).scalar_one()
        return value


def _as_ms(value: str) -> int:
    """Convert PostgreSQL's rendering of a duration setting (``5s``, ``300ms``) to ms."""
    if value.endswith("ms"):
        return int(value[:-2])
    if value.endswith("s"):
        return int(value[:-1]) * 1000
    if value.endswith("min"):
        return int(value[:-3]) * 60_000
    return int(value)


@pytest.mark.parametrize("role", ["api", "collector", "jobs"])
def test_role_statement_timeout_and_lock_timeout(role: str, db_url: str, make_engine: Any) -> None:
    engine = make_engine(db_url, role=role)
    assert _as_ms(_show(engine, "statement_timeout")) == STATEMENT_TIMEOUT_MS[role]
    assert _as_ms(_show(engine, "lock_timeout")) == LOCK_TIMEOUT_MS


def test_api_and_batch_roles_differ(db_url: str, make_engine: Any) -> None:
    assert _show(make_engine(db_url, role="api"), "statement_timeout") == "5s"
    assert _show(make_engine(db_url, role="collector"), "statement_timeout") == "30s"
    assert _show(make_engine(db_url, role="jobs"), "statement_timeout") == "30s"
    assert _show(make_engine(db_url), "lock_timeout") == "2s"


def test_session_is_utc_even_when_pgtz_is_set(
    db_url: str, make_engine: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PGTZ", "Asia/Kolkata")
    # Negative control: without the factory's connect hook PGTZ wins (RESEARCH F-15).
    conninfo = make_url(db_url).set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(conninfo) as raw:
        zone = raw.execute("SHOW timezone").fetchone()
    assert zone == ("Asia/Kolkata",)

    engine = make_engine(db_url)
    assert _show(engine, "timezone") == "UTC"
    with engine.connect() as connection:
        stamp = connection.execute(
            text("SELECT TIMESTAMPTZ '2026-11-06 12:00:00+05:30'")
        ).scalar_one()
    assert stamp.utcoffset() == timedelta(0)
    assert stamp.hour == 6
    assert stamp.minute == 30


def test_url_options_are_kept_next_to_the_timeouts(db_url: str, make_engine: Any) -> None:
    url = make_url(db_url).update_query_dict({"options": "-c work_mem=8MB"})
    engine = make_engine(url.render_as_string(hide_password=False))
    assert _show(engine, "work_mem") == "8MB"
    assert _show(engine, "statement_timeout") == "5s"


def test_pool_settings(db_url: str, make_engine: Any) -> None:
    engine = make_engine(db_url)
    assert engine.pool.size() == 5
    assert engine.pool.timeout() == POOL_TIMEOUT_SECONDS
    # pool size 5 plus overflow 5: ten checkouts succeed, the eleventh waits the pool timeout.
    held = [engine.connect() for _ in range(10)]
    try:
        started = time.monotonic()
        with pytest.raises(exc.TimeoutError):
            engine.connect()
        assert POOL_TIMEOUT_SECONDS - 0.5 <= time.monotonic() - started < POOL_TIMEOUT_SECONDS + 3
    finally:
        for connection in held:
            connection.close()


def test_pre_ping_replaces_a_connection_the_server_closed(
    db_url: str, pg_admin_url: str, make_engine: Any
) -> None:
    engine = make_engine(db_url, pool_size=1, max_overflow=0)
    with engine.connect() as connection:
        first_pid = connection.execute(text("SELECT pg_backend_pid()")).scalar_one()
    admin = make_engine(pg_admin_url, pool_size=1, max_overflow=0)
    with admin.connect() as connection:
        connection.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": first_pid})
        connection.commit()
    with engine.connect() as connection:  # without pre-ping this checkout would fail
        second_pid = connection.execute(text("SELECT pg_backend_pid()")).scalar_one()
    assert second_pid != first_pid


def test_slow_query_is_cancelled_by_the_statement_timeout(db_url: str, make_engine: Any) -> None:
    engine = make_engine(db_url, statement_timeout_ms=300)
    started = time.monotonic()
    with engine.connect() as connection, pytest.raises(exc.OperationalError) as info:
        connection.execute(text("SELECT pg_sleep(5)"))
    assert isinstance(info.value.orig, psycopg.errors.QueryCanceled)
    assert time.monotonic() - started < 3


def test_pool_exhaustion_is_a_timeout_error_not_a_dbapi_error(
    db_url: str, make_engine: Any
) -> None:
    engine = make_engine(db_url, pool_size=1, max_overflow=0)
    with engine.connect():
        started = time.monotonic()
        with pytest.raises(exc.TimeoutError) as info:
            engine.connect()
        elapsed = time.monotonic() - started
    assert not isinstance(info.value, exc.DBAPIError)
    assert POOL_TIMEOUT_SECONDS - 0.5 <= elapsed < POOL_TIMEOUT_SECONDS + 3


def test_closed_port_fails_within_the_connect_timeout(make_engine: Any) -> None:
    engine = make_engine("postgresql://tt@127.0.0.1:1/truthtrail")
    started = time.monotonic()
    with pytest.raises(exc.OperationalError) as info:
        engine.connect()
    assert time.monotonic() - started < CONNECT_TIMEOUT_SECONDS + 1
    assert isinstance(info.value.orig, psycopg.OperationalError)
