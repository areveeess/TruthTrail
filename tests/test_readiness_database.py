"""The ``database`` readiness check and the engine wiring (D-19, D-25, D-27, RESEARCH F-11,
threats T-03-18 and T-03-20).

``/ready`` is 200 only when the database answers and its ``alembic_version`` equals the packaged
head; it is 503 naming only ``database`` for a missing engine, a closed port, a missing table, a
wrong or extra revision and a refused connection, and it recovers. Plain apps and ``DEMO_MODE``
apps register no check and behave exactly as in Phase 2. The lifespan disposes only the engine it
built. Neither the body nor the logs ever carry a URL, host, user, database name or password.
"""

import logging
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

from truthtrail.api.app import register_default_checks
from truthtrail.core.boot import BootSettings
from truthtrail.core.config import ConfigurationError
from truthtrail.core.readiness import CHECK_TIMEOUT, ReadinessRegistry
from truthtrail.db import packaged_head
from truthtrail.db.health import database_ready

PROBLEM_JSON = "application/problem+json"
MARKER = "rdy9MarkerPw"
CLOSED_URL = f"postgresql+psycopg://tt_ready_user:{MARKER}@127.0.0.1:1/tt_ready_db"
FORBIDDEN_IN_OUTPUT = (MARKER, "tt_ready_user", "tt_ready_db", "127.0.0.1", "postgresql")


def assert_not_ready_database(response: Any) -> None:
    body = response.json()
    assert response.status_code == 503
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    assert body["code"] == "not_ready"
    assert body["detail"] == "Not ready: database."
    assert body["source_status"] == "not_ready"
    assert body["synthetic"] is False
    assert body["data_as_of"] is None
    for fragment in FORBIDDEN_IN_OUTPUT:
        assert fragment not in response.text


def disposal_recorder(engine: Engine) -> list[Engine]:
    disposed: list[Engine] = []
    event.listen(engine, "engine_disposed", disposed.append)
    return disposed


# --- apps without a database ----------------------------------------------------------------
def test_a_plain_app_registers_no_check(client_factory: Callable[..., Any]) -> None:
    client = client_factory()
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {}}
    assert client.app.state.engine is None
    assert client.app.state.engine_owned is False


def test_demo_mode_registers_no_check_even_with_a_database_url(
    client_factory: Callable[..., Any],
) -> None:
    client = client_factory(demo_mode="true", env={"DATABASE_URL": CLOSED_URL})
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {}}


def test_demo_mode_lifespan_builds_no_engine(client_factory: Callable[..., Any]) -> None:
    client = client_factory(demo_mode="true", env={"DATABASE_URL": CLOSED_URL})
    with client:
        assert client.app.state.engine is None
        assert client.get("/ready").status_code == 200


# --- fail closed without a usable database ----------------------------------------------------
def test_database_url_without_a_lifespan_fails_closed(client_factory: Callable[..., Any]) -> None:
    """TestClient(app) without ``with`` never builds the engine: the check must not pass."""
    client = client_factory(env={"DATABASE_URL": CLOSED_URL})
    assert client.app.state.engine is None
    assert_not_ready_database(client.get("/ready"))


def test_an_injected_engine_on_a_closed_port_is_not_ready_in_time(
    client_factory: Callable[..., Any], make_engine: Callable[..., Engine]
) -> None:
    engine = make_engine(CLOSED_URL)
    client = client_factory(app_kwargs={"engine": engine})
    started = time.monotonic()
    response = client.get("/ready")
    assert time.monotonic() - started < CHECK_TIMEOUT + 1.0
    assert_not_ready_database(response)
    assert "retry-after" not in response.headers


def test_the_log_names_the_check_and_class_only(
    client_factory: Callable[..., Any],
    make_engine: Callable[..., Engine],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    client = client_factory(app_kwargs={"engine": make_engine(CLOSED_URL)})
    client.get("/ready")
    assert "readiness check failed: name=database error=OperationalError" in caplog.text
    for fragment in FORBIDDEN_IN_OUTPUT:
        assert fragment not in caplog.text


def test_an_injected_engine_registers_the_check_even_in_demo_mode(
    client_factory: Callable[..., Any], make_engine: Callable[..., Engine]
) -> None:
    client = client_factory(demo_mode="true", app_kwargs={"engine": make_engine(CLOSED_URL)})
    assert client.app.state.engine_owned is False
    assert_not_ready_database(client.get("/ready"))


def test_register_default_checks_without_a_getter_registers_nothing() -> None:
    registry = ReadinessRegistry()
    register_default_checks(registry)
    assert registry.run() == {}
    with_getter = ReadinessRegistry()
    register_default_checks(with_getter, lambda: None)
    assert with_getter.run() == {"database": False}


def test_boot_settings_record_presence_only(monkeypatch: pytest.MonkeyPatch) -> None:
    assert BootSettings().demo_mode is False
    assert BootSettings().database_url is None
    monkeypatch.setenv("DATABASE_URL", "   ")
    assert BootSettings().database_url is None
    monkeypatch.setenv("DATABASE_URL", CLOSED_URL)
    boot = BootSettings()
    assert boot.database_url is not None
    assert MARKER not in repr(boot)
    for raw, expected in (("true", True), ("YES", True), ("1", True), ("0", False)):
        monkeypatch.setenv("DEMO_MODE", raw)
        assert BootSettings().demo_mode is expected
    # Unparseable counts as false at construction (the check is registered, fail closed);
    # the strict Settings in the lifespan still refuses to start on it.
    monkeypatch.setenv("DEMO_MODE", "maybe")
    assert BootSettings().demo_mode is False


def test_an_invalid_database_url_stops_startup_without_echoing_it(
    client_factory: Callable[..., Any],
) -> None:
    client = client_factory(env={"DATABASE_URL": f"mysql://u:{MARKER}@db.invalid/x"})
    with pytest.raises(ConfigurationError) as caught, client:
        pass
    assert "DATABASE_URL" in str(caught.value)
    assert MARKER not in str(caught.value)


def test_an_unreachable_database_does_not_stop_startup(
    client_factory: Callable[..., Any],
) -> None:
    client = client_factory(env={"DATABASE_URL": CLOSED_URL})
    with client:
        engine = client.app.state.engine
        assert engine is not None
        assert client.app.state.engine_owned is True
        disposed = disposal_recorder(engine)
        assert client.get("/health").status_code == 200
        assert_not_ready_database(client.get("/ready"))
    assert disposed == [engine]
    assert client.app.state.engine is None


# --- a real PostgreSQL ------------------------------------------------------------------------
@pytest.mark.requires_db
def test_ready_with_a_migrated_database_lists_database_ok(
    client_factory: Callable[..., Any], make_engine: Callable[..., Engine], migrated_db_url: str
) -> None:
    client = client_factory(app_kwargs={"engine": make_engine(migrated_db_url)})
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok"}}


@pytest.mark.requires_db
def test_a_database_without_alembic_version_is_not_ready(
    client_factory: Callable[..., Any],
    make_engine: Callable[..., Engine],
    empty_database: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = client_factory(app_kwargs={"engine": make_engine(empty_database())})
    assert_not_ready_database(client.get("/ready"))
    assert "error=ProgrammingError" in caplog.text


def _stamped(empty_database: Any, versions: list[str]) -> str:
    url: str = empty_database()
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("CREATE TABLE alembic_version (version_num varchar(32) PRIMARY KEY)")
            )
            for version in versions:
                connection.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES (:v)"), {"v": version}
                )
    finally:
        engine.dispose()
    return url


@pytest.mark.requires_db
def test_a_wrong_revision_is_not_ready(
    client_factory: Callable[..., Any], make_engine: Callable[..., Engine], empty_database: Any
) -> None:
    url = _stamped(empty_database, ["ffffffffffff"])
    client = client_factory(app_kwargs={"engine": make_engine(url)})
    assert_not_ready_database(client.get("/ready"))


@pytest.mark.requires_db
def test_an_extra_revision_row_is_not_ready(
    client_factory: Callable[..., Any], make_engine: Callable[..., Engine], empty_database: Any
) -> None:
    url = _stamped(empty_database, [packaged_head(), "ffffffffffff"])
    client = client_factory(app_kwargs={"engine": make_engine(url)})
    assert_not_ready_database(client.get("/ready"))


@pytest.fixture
def isolated_migrated_url(empty_database: Any) -> str:
    """A migrated database of its own, for tests that take it offline."""
    from conftest import upgrade_to_head

    url: str = empty_database()
    upgrade_to_head(url)
    return url


@pytest.fixture
def admin(pg_admin_url: str) -> Iterator[Engine]:
    engine = create_engine(pg_admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


def _set_connections(admin: Engine, name: str, *, allowed: bool) -> None:
    assert name.startswith("truthtrail_test_")
    with admin.connect() as connection:
        connection.execute(
            text(f'ALTER DATABASE "{name}" ALLOW_CONNECTIONS {"true" if allowed else "false"}')
        )
        if not allowed:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": name},
            )


@pytest.mark.requires_db
def test_a_refused_connection_is_not_ready_and_recovers(
    client_factory: Callable[..., Any],
    make_engine: Callable[..., Engine],
    isolated_migrated_url: str,
    admin: Engine,
) -> None:
    name = str(make_url(isolated_migrated_url).database)
    client = client_factory(app_kwargs={"engine": make_engine(isolated_migrated_url)})
    assert client.get("/ready").status_code == 200  # a pooled connection now exists
    _set_connections(admin, name, allowed=False)
    try:
        assert_not_ready_database(client.get("/ready"))
    finally:
        _set_connections(admin, name, allowed=True)
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["checks"] == {"database": "ok"}


@pytest.mark.requires_db
def test_the_lifespan_owns_and_disposes_the_engine_it_builds(
    client_factory: Callable[..., Any], migrated_db_url: str
) -> None:
    client = client_factory(env={"DATABASE_URL": migrated_db_url})
    assert client.app.state.engine is None
    with client:
        engine = client.app.state.engine
        assert engine is not None
        assert client.app.state.engine_owned is True
        disposed = disposal_recorder(engine)
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json()["checks"] == {"database": "ok"}
    assert disposed == [engine]
    assert client.app.state.engine is None
    assert client.app.state.engine_owned is False


@pytest.mark.requires_db
def test_the_lifespan_never_disposes_an_injected_engine(
    client_factory: Callable[..., Any], make_engine: Callable[..., Engine], migrated_db_url: str
) -> None:
    engine = make_engine(migrated_db_url)
    disposed = disposal_recorder(engine)
    client = client_factory(env={"DATABASE_URL": CLOSED_URL}, app_kwargs={"engine": engine})
    with client:
        assert client.app.state.engine is engine
        assert client.get("/ready").status_code == 200
    assert disposed == []
    assert client.app.state.engine is engine


@pytest.mark.requires_db
def test_the_probe_timeout_is_transaction_local(
    make_engine: Callable[..., Engine], migrated_db_url: str
) -> None:
    engine = make_engine(migrated_db_url, pool_size=1, max_overflow=0)
    assert database_ready(engine) is True
    with engine.connect() as connection:  # the same pooled connection
        assert connection.execute(text("SHOW statement_timeout")).scalar_one() == "5s"
