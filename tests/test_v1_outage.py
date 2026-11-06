"""Database outages on /v1, proved against a real PostgreSQL (D-25, SC5, FND-02, T-03-45).

The database is taken offline without stopping the server (RESEARCH Pattern 11): ``ALTER
DATABASE ... ALLOW_CONNECTIONS false`` plus ``pg_terminate_backend`` of its sessions, restored in
a ``finally`` block. A probe route then answers 503 problem+json ``database_unavailable`` with
``Retry-After``, ``/ready`` answers 503 naming only ``database``, and after restoring connections
the next request is a 200 again (pre-ping reconnect). An engine pointed at a closed port gives the
same 503; a 300 ms statement timeout against ``pg_sleep(2)`` gives 503 ``database_timeout``; pool
exhaustion gives 503 ``database_unavailable`` after about the pool timeout; a constraint violation
and a write on the read-only connection give the generic 500. No body or log line carries the
host, socket path, database name, port, user or the marker password, and no error carries data.
"""

import logging
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi import Request
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

from truthtrail.api.limits import LimitedRouter
from truthtrail.api.problems import V1_PROBLEM_RESPONSES
from truthtrail.api.v1_deps import read_connection
from truthtrail.db.engine import POOL_TIMEOUT_SECONDS

pytestmark = pytest.mark.requires_db

PROBLEM_JSON = "application/problem+json"
MARKER = "out4MarkerPw"
CLOSED_USER = "tt_outage_user"
CLOSED_DB = "tt_outage_db"
CLOSED_URL = f"postgresql+psycopg://{CLOSED_USER}:{MARKER}@127.0.0.1:1/{CLOSED_DB}"


def probes(router: LimitedRouter) -> None:
    """Probe routes: a trivial read, a slow read, a constraint violation and a write."""

    @router.get("/_select_one", responses=V1_PROBLEM_RESPONSES)
    def select_one(request: Request) -> dict[str, int]:
        with read_connection(request) as connection:
            return {"value": int(connection.execute(text("SELECT 1")).scalar_one())}

    @router.get("/_sleep", responses=V1_PROBLEM_RESPONSES)
    def sleep_two(request: Request) -> dict[str, int]:
        with read_connection(request) as connection:
            connection.execute(text("SELECT pg_sleep(2)"))
            return {"value": 1}

    @router.get("/_sleep_long", responses=V1_PROBLEM_RESPONSES)
    def sleep_long(request: Request) -> dict[str, int]:
        with read_connection(request) as connection:
            connection.execute(text("SELECT pg_sleep(4)"))
            return {"value": 1}

    @router.get("/_violate", responses=V1_PROBLEM_RESPONSES)
    def violate(request: Request) -> dict[str, int]:
        # A writable transaction on purpose: the CHECK on edge_kind rejects the row.
        with request.app.state.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO events (uri, edge_kind, inferred, parent_state, observed_at)"
                    " VALUES (:uri, :kind, false, 'none', now())"
                ),
                {"uri": "v" + MARKER, "kind": "bogus"},
            )
        return {"value": 1}

    @router.get("/_write", responses=V1_PROBLEM_RESPONSES)
    def write_read_only(request: Request) -> dict[str, int]:
        with read_connection(request) as connection:
            connection.execute(
                text("INSERT INTO news_queries (slug, query) VALUES (:s, :q)"),
                {"s": "s" + MARKER, "q": MARKER},
            )
        return {"value": 1}


@pytest.fixture
def isolated_url(empty_database: Any) -> str:
    """A migrated database of its own (it is taken offline), with a marker password in its URL
    (trust authentication ignores it, so it only proves the URL never leaks)."""
    from conftest import upgrade_to_head

    url: str = empty_database()
    upgrade_to_head(url)
    return make_url(url).set(password=MARKER).render_as_string(hide_password=False)


@pytest.fixture
def admin(pg_admin_url: str) -> Iterator[Engine]:
    engine = create_engine(pg_admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


def _set_connections(admin: Engine, name: str, *, allowed: bool) -> None:
    assert name.startswith("truthtrail_test_")
    statement = (
        f'ALTER DATABASE "{name}" ALLOW_CONNECTIONS true'
        if allowed
        else f'ALTER DATABASE "{name}" ALLOW_CONNECTIONS false'
    )
    with admin.connect() as connection:
        connection.execute(text(statement))
        if not allowed:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": name},
            )


def _forbidden_fragments(url: str) -> list[str]:
    parsed = make_url(url)
    fragments = [MARKER, str(parsed.database), "postgresql", "psycopg"]
    host = parsed.query.get("host") or parsed.host
    if isinstance(host, str) and host:
        fragments.append(host)
    if parsed.port is not None:
        fragments.append(f"port {parsed.port}")
        fragments.append(f":{parsed.port}")
    return fragments


def assert_database_problem(
    response: Any, code: str, caplog: pytest.LogCaptureFixture, forbidden: list[str]
) -> None:
    assert response.status_code == 503
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    retry = response.headers["retry-after"]
    assert retry.isdigit()
    assert int(retry) > 0
    body = response.json()
    assert body["type"] == "about:blank"
    assert body["title"] == "Service Unavailable"
    assert body["status"] == 503
    assert body["code"] == code
    assert body["upstream"] == "database"
    assert body["synthetic"] is False
    assert body["source_status"] == code
    assert body["data_as_of"] is None
    assert "value" not in body
    for fragment in forbidden:
        assert fragment not in response.text
        assert fragment not in caplog.text


def assert_not_ready_database(response: Any, forbidden: list[str]) -> None:
    body = response.json()
    assert response.status_code == 503
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    assert body["code"] == "not_ready"
    assert body["detail"] == "Not ready: database."
    for fragment in forbidden:
        assert fragment not in response.text


def test_an_offline_database_is_503_unavailable_and_recovers(
    client_factory: Callable[..., Any],
    make_engine: Callable[..., Engine],
    isolated_url: str,
    admin: Engine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    name = str(make_url(isolated_url).database)
    forbidden = _forbidden_fragments(isolated_url)
    client = client_factory(
        app_kwargs={"engine": make_engine(isolated_url), "v1_registrars": [probes]}
    )
    assert client.get("/v1/_select_one").json() == {"value": 1}  # a pooled connection exists
    assert client.get("/ready").status_code == 200
    _set_connections(admin, name, allowed=False)
    try:
        response = client.get("/v1/_select_one")
        assert_database_problem(response, "database_unavailable", caplog, forbidden)
        assert_not_ready_database(client.get("/ready"), forbidden)
        # Still down on a second request (the pool holds no stale success).
        again = client.get("/v1/_select_one")
        assert_database_problem(again, "database_unavailable", caplog, forbidden)
    finally:
        _set_connections(admin, name, allowed=True)
    assert client.get("/v1/_select_one").json() == {"value": 1}
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["checks"] == {"database": "ok"}
    assert any("database_unavailable: OperationalError" in r.getMessage() for r in caplog.records)


def test_a_closed_port_is_503_unavailable(
    client_factory: Callable[..., Any],
    make_engine: Callable[..., Engine],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    client = client_factory(
        app_kwargs={"engine": make_engine(CLOSED_URL), "v1_registrars": [probes]}
    )
    forbidden = [MARKER, CLOSED_USER, CLOSED_DB, "127.0.0.1", "postgresql", ":1/"]
    response = client.get("/v1/_select_one")
    assert_database_problem(response, "database_unavailable", caplog, forbidden)
    assert_not_ready_database(client.get("/ready"), forbidden)


def test_a_statement_timeout_is_503_database_timeout(
    client_factory: Callable[..., Any],
    make_engine: Callable[..., Engine],
    migrated_db_url: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    engine = make_engine(migrated_db_url, statement_timeout_ms=300)
    client = client_factory(app_kwargs={"engine": engine, "v1_registrars": [probes]})
    started = time.monotonic()
    response = client.get("/v1/_sleep")
    elapsed = time.monotonic() - started
    assert_database_problem(
        response, "database_timeout", caplog, _forbidden_fragments(migrated_db_url)
    )
    assert elapsed < 2.0  # cancelled at 300 ms, long before pg_sleep(2) would return
    assert client.get("/v1/_select_one").json() == {"value": 1}
    assert any("database_timeout: OperationalError" in r.getMessage() for r in caplog.records)


def test_pool_exhaustion_is_503_unavailable_after_the_pool_timeout(
    client_factory: Callable[..., Any],
    make_engine: Callable[..., Engine],
    migrated_db_url: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    engine = make_engine(migrated_db_url, pool_size=1, max_overflow=0)
    client = client_factory(app_kwargs={"engine": engine, "v1_registrars": [probes]})
    held = engine.connect()
    try:
        started = time.monotonic()
        response = client.get("/v1/_select_one")
        elapsed = time.monotonic() - started
    finally:
        held.close()
    assert_database_problem(
        response, "database_unavailable", caplog, _forbidden_fragments(migrated_db_url)
    )
    assert POOL_TIMEOUT_SECONDS - 0.5 <= elapsed < POOL_TIMEOUT_SECONDS + 2.0
    assert any("database_unavailable: TimeoutError" in r.getMessage() for r in caplog.records)
    assert client.get("/v1/_select_one").json() == {"value": 1}


def test_concurrent_requests_beyond_the_pool_get_503_not_500(
    client_factory: Callable[..., Any], make_engine: Callable[..., Engine], migrated_db_url: str
) -> None:
    engine = make_engine(migrated_db_url, pool_size=1, max_overflow=0)
    client = client_factory(app_kwargs={"engine": engine, "v1_registrars": [probes]})
    statuses: list[int] = []
    slow = threading.Thread(
        target=lambda: statuses.append(client.get("/v1/_sleep_long").status_code)
    )
    slow.start()
    time.sleep(0.3)  # the slow request now holds the only connection
    statuses.append(client.get("/v1/_select_one").status_code)
    slow.join(timeout=10)
    assert sorted(statuses) == [200, 503]


def test_a_constraint_violation_is_the_generic_500(
    client_factory: Callable[..., Any],
    make_engine: Callable[..., Engine],
    migrated_db_url: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    client = client_factory(
        app_kwargs={"engine": make_engine(migrated_db_url), "v1_registrars": [probes]}
    )
    response = client.get("/v1/_violate")
    assert response.status_code == 500
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    assert "retry-after" not in response.headers
    body = response.json()
    assert body["code"] == "internal_error"
    assert "upstream" not in body
    for fragment in [*_forbidden_fragments(migrated_db_url), "INSERT", "edge_kind", "bogus"]:
        assert fragment not in response.text
        assert fragment not in caplog.text
    assert "events" not in response.text
    assert any("unexpected error: IntegrityError" in r.getMessage() for r in caplog.records)


def test_the_read_connection_refuses_writes(
    client_factory: Callable[..., Any],
    make_engine: Callable[..., Engine],
    migrated_db_url: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    engine = make_engine(migrated_db_url)
    client = client_factory(app_kwargs={"engine": engine, "v1_registrars": [probes]})
    response = client.get("/v1/_write")
    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert MARKER not in response.text
    assert MARKER not in caplog.text
    with engine.connect() as connection:
        count = connection.execute(
            text("SELECT count(*) FROM news_queries WHERE slug = :s"), {"s": "s" + MARKER}
        ).scalar_one()
    assert count == 0


def test_the_real_data_routes_are_503_during_an_outage_and_recover(
    client_factory: Callable[..., Any],
    make_engine: Callable[..., Engine],
    isolated_url: str,
    admin: Engine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    name = str(make_url(isolated_url).database)
    forbidden = _forbidden_fragments(isolated_url)
    client = client_factory(app_kwargs={"engine": make_engine(isolated_url)})
    assert client.get("/v1/cascades").status_code == 200
    _set_connections(admin, name, allowed=False)
    try:
        for path in ("/v1/cascades", "/v1/cascades/1", "/v1/cascades/1/tree"):
            assert_database_problem(client.get(path), "database_unavailable", caplog, forbidden)
        assert_not_ready_database(client.get("/ready"), forbidden)
    finally:
        _set_connections(admin, name, allowed=True)
    body = client.get("/v1/cascades").json()
    assert body["items"] == []
    assert body["meta"]["source_status"] == "empty"
