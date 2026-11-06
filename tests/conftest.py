"""Shared test fixtures: network and socket guards, env scrub, app client, payload builders and
the real-PostgreSQL fixtures.

Every test runs inside an autouse ``responses`` mock, so an unmocked outbound
``requests`` call raises ``requests.exceptions.ConnectionError`` instead of
reaching the live provider, and inside an autouse socket guard that allows only loopback
addresses and unix sockets. The app and the fetcher module are imported lazily
inside ``client_factory`` so collection never imports them and a future package
move touches this one file.

Database tests (D-28) carry ``@pytest.mark.requires_db`` and use ``db_url``, ``empty_database``
or ``make_engine``. The session provisions ``TEST_DATABASE_URL`` or a throwaway cluster
(``tests/pg_cluster.py``) on first use only, so ``pytest -m "not requires_db"`` never starts one.
No provisioning means one session-level exit naming the remedies, never a silent skip.
``REQUIRE_DB_FLOOR`` fails a run in which fewer database tests executed than the floor.
"""

import ipaddress
import os
import random
import secrets
import socket
from collections.abc import Callable, Iterator, Mapping
from typing import Any

import pytest
import responses
from hypothesis import HealthCheck, settings

from truthtrail.core.boot import BootSettings
from truthtrail.core.config import DatabaseSettings, IngestSettings, Settings, get_settings
from truthtrail.core.policy import Policy

# Hypothesis profiles (D-15): "ci" is deterministic and database-free; "dev" is lighter.
# Select with --hypothesis-profile=ci or the HYPOTHESIS_PROFILE environment variable.
settings.register_profile(
    "ci",
    max_examples=200,
    derandomize=True,
    database=None,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.register_profile("dev", max_examples=50, deadline=None)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))

# Names the module that owns the route-level callables load_demo_fixture,
# FIXTURE_PATH and analyze_risk, for string patch targets (the create_app split
# moved them out of truthtrail.main into the analyze router module).
APP_MODULE = "truthtrail.api.analyze"
FAKE_KEY = "FAKE_TEST_KEY"
GNEWS_URL = "https://gnews.io/api/v4/search"
ENV_NAMES = (
    "GNEWS_API_KEY",
    "DEMO_MODE",
    "BLUESKY_HANDLE",
    "BLUESKY_APP_PASSWORD",
    "DATABASE_URL",
    "CORS_ORIGINS",
    "RATE_LIMIT_ANALYZE",
    "RATE_LIMIT_V1",
    "TRUST_PROXY_HEADERS",
    "FORWARDED_ALLOW_IPS",
    # Phase 3 operator values (D-07, D-17)
    "PSEUDONYM_SECRET",
    "COLLECTOR_CONTACT",
    # Test-only database variables: read once per session before the scrub (see pg_cluster)
    "TEST_DATABASE_URL",
    "TRUTHTRAIL_PG_BIN",
    "REQUIRE_DB",
    "REQUIRE_DB_FLOOR",
    # Every policy parameter, derived from the model so the list cannot drift (D-03, D-31)
    *(name.upper() for name in Policy.model_fields),
)
# Every settings class: a developer's local .env must never leak into a test.
SETTINGS_CLASSES = (Settings, BootSettings, Policy, DatabaseSettings, IngestSettings)
# The environment as the session started, before any per-test scrub: the only place the
# test-only database variables are read (provisioning and the REQUIRE_DB_FLOOR check).
SESSION_ENVIRON = dict(os.environ)
# Fixtures that need a real PostgreSQL; a test that uses one must carry the requires_db marker.
DB_FIXTURES = frozenset(
    {"pg_provisioning", "pg_admin_url", "db_url", "empty_database", "migrated_db_url", "clean_db"}
)


@pytest.fixture(autouse=True)
def network_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[responses.RequestsMock]:
    """Block every unregistered outbound request and scrub secret-bearing env vars.

    A developer's local .env is disabled and the cached settings are cleared
    before and after each test, so no real value can leak in or persist.
    """
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    for settings_class in SETTINGS_CLASSES:
        monkeypatch.setitem(settings_class.model_config, "env_file", None)
    get_settings.cache_clear()
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rs:
        yield rs
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the adapter's retry backoff a no-op so no test ever sleeps for real (D-12)."""
    from truthtrail.services import gnews

    monkeypatch.setattr(gnews, "_sleep", lambda seconds: None)


@pytest.fixture
def mock_gnews(network_guard: responses.RequestsMock) -> responses.RequestsMock:
    """Return the active mock so tests can register GNews responses on it."""
    return network_guard


@pytest.fixture
def client_factory(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Any]:
    """Return a callable that builds a TestClient around the real app.

    Settings are driven through the environment. Using the returned client as a
    context manager (``with client_factory(...):``) runs the app lifespan.
    """

    def make(
        *,
        gnews_api_key: str | None = FAKE_KEY,
        demo_mode: str | None = None,
        raise_server_exceptions: bool = False,
        env: Mapping[str, str] | None = None,
        client: tuple[str, int] | None = None,
        app_kwargs: Mapping[str, Any] | None = None,
    ) -> Any:
        """Set the environment, then build a new app with ``create_app()`` per call.

        ``env`` sets extra environment variables, ``client`` is the (host, port) the
        TestClient reports as the peer address and ``app_kwargs`` is forwarded to
        ``create_app``, so later plans never edit this fixture for a new setting.
        """
        from fastapi.testclient import TestClient

        from truthtrail.api.app import create_app

        if gnews_api_key is not None:
            monkeypatch.setenv("GNEWS_API_KEY", gnews_api_key)
        if demo_mode is not None:
            monkeypatch.setenv("DEMO_MODE", demo_mode)
        for name, value in (env or {}).items():
            monkeypatch.setenv(name, value)
        get_settings.cache_clear()
        app = create_app(**(app_kwargs or {}))
        if client is None:
            return TestClient(app, raise_server_exceptions=raise_server_exceptions)
        return TestClient(app, raise_server_exceptions=raise_server_exceptions, client=client)

    return make


@pytest.fixture
def client(client_factory: Callable[..., Any]) -> Any:
    """TestClient that returns 500 responses instead of raising server errors."""
    return client_factory()


@pytest.fixture
def app_module() -> str:
    """Module name that string patch targets must use (see ``APP_MODULE``)."""
    return APP_MODULE


@pytest.fixture
def subprocess_env() -> dict[str, str]:
    """Return a new minimal environment dict for subprocess-based tests.

    SYSTEMROOT is passed through when present: without it asyncio cannot
    initialise Winsock on Windows (WinError 10106).
    """
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if "SYSTEMROOT" in os.environ:
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return env


@pytest.fixture
def fake_key() -> str:
    return FAKE_KEY


@pytest.fixture
def gnews_url() -> str:
    return GNEWS_URL


@pytest.fixture
def gnews_article() -> Callable[..., dict[str, Any]]:
    """Builder for one GNews-shaped article."""

    def article(
        title: str | None = "Local bakery wins award",
        source: str = "Example Wire",
        published_at: str = "2026-10-11T09:30:00Z",
    ) -> dict[str, Any]:
        return {
            "title": title,
            "description": None,
            "url": "https://example.org/article",
            "image": None,
            "publishedAt": published_at,
            "source": {"name": source, "url": "https://example.org"},
        }

    return article


@pytest.fixture
def gnews_payload() -> Callable[..., dict[str, Any]]:
    """Builder for a GNews search response body."""

    def payload(*articles: dict[str, Any]) -> dict[str, Any]:
        return {"totalArticles": len(articles), "articles": list(articles)}

    return payload


@pytest.fixture
def seeded_random() -> Iterator[Callable[[int], None]]:
    """Yield a seeding function and restore the global random state afterwards."""
    state = random.getstate()

    def seed(n: int) -> None:
        random.seed(n)

    yield seed
    random.setstate(state)


# --- Socket guard (D-28, T-03-12) ---------------------------------------------------------
SOCKET_GUARD_MESSAGE = (
    "socket guard: tests may connect only to loopback addresses and unix sockets; "
    "a connection to a non-loopback host was blocked"
)
LOOKUP_GUARD_MESSAGE = (
    "socket guard: tests may resolve only localhost and loopback addresses; "
    "a name lookup of a non-loopback host was blocked"
)


def is_loopback_host(host: object) -> bool:
    """True for ``localhost``, 127.0.0.0/8, ``::1`` and IPv4-mapped loopback addresses."""
    if isinstance(host, bytes):
        host = host.decode("ascii", errors="replace")
    if not isinstance(host, str):
        return False
    if host.lower() in {"localhost", "localhost."}:
        return True
    try:
        address = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_loopback


def is_allowed_address(family: int, address: object) -> bool:
    """Loopback (inet) or any unix-socket path; everything else is blocked."""
    if getattr(socket, "AF_UNIX", None) == family or isinstance(address, str | bytes):
        return True
    if isinstance(address, tuple) and address:
        return is_loopback_host(address[0])
    return False


@pytest.fixture(autouse=True)
def socket_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block non-loopback connects and name lookups made from the test process.

    The check runs before the real call, so no packet leaves. libpq (psycopg) and subprocess
    servers do not use Python sockets and are unaffected; unix sockets always pass.
    """
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo
    real_create_connection = socket.create_connection

    def connect(self: socket.socket, address: Any) -> None:
        if not is_allowed_address(self.family, address):
            raise RuntimeError(SOCKET_GUARD_MESSAGE)
        real_connect(self, address)

    def connect_ex(self: socket.socket, address: Any) -> int:
        if not is_allowed_address(self.family, address):
            raise RuntimeError(SOCKET_GUARD_MESSAGE)
        return real_connect_ex(self, address)

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if host is not None and not is_loopback_host(host):
            raise RuntimeError(LOOKUP_GUARD_MESSAGE)
        return real_getaddrinfo(host, *args, **kwargs)

    def create_connection(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
        if not (isinstance(address, tuple) and address and is_loopback_host(address[0])):
            raise RuntimeError(SOCKET_GUARD_MESSAGE)
        return real_create_connection(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(socket, "create_connection", create_connection)


# --- Real PostgreSQL (D-28, RESEARCH Pattern 11, F-09, F-10) --------------------------------
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """A test that uses a database fixture must carry the requires_db marker."""
    unmarked = [
        item.nodeid
        for item in items
        if DB_FIXTURES & set(getattr(item, "fixturenames", ()))
        and item.get_closest_marker("requires_db") is None
    ]
    if unmarked:
        raise pytest.UsageError(
            "tests using a database fixture must be marked requires_db: " + ", ".join(unmarked)
        )


@pytest.fixture(scope="session")
def pg_provisioning() -> Iterator[Any]:
    """TEST_DATABASE_URL or a throwaway cluster for the whole session (one error if neither)."""
    from pg_cluster import ProvisioningError, provision_admin_url

    try:
        provisioned = provision_admin_url(SESSION_ENVIRON)
    except ProvisioningError as exc:
        pytest.exit(f"requires_db: {exc}", returncode=3)
    try:
        yield provisioned
    finally:
        if provisioned.cluster is not None:
            provisioned.cluster.stop()


@pytest.fixture(scope="session")
def pg_admin_url(pg_provisioning: Any) -> str:
    """Admin URL of the session's server (tests never run DDL in the database it names)."""
    url: str = pg_provisioning.admin_url
    return url


def _admin_engine(admin_url: str) -> Any:
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    return create_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)


def _create_test_database(admin: Any, admin_url: str) -> tuple[str, str]:
    """CREATE a UTF-8 ``truthtrail_test_{random}`` database; return (name, URL)."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.pool import NullPool

    name = f"truthtrail_test_{secrets.token_hex(4)}"
    with admin.connect() as connection:
        connection.execute(text(f"CREATE DATABASE \"{name}\" ENCODING 'UTF8' TEMPLATE template0"))
    url = make_url(admin_url).set(database=name).render_as_string(hide_password=False)
    probe = create_engine(url, poolclass=NullPool)
    try:
        with probe.connect() as connection:
            encoding = connection.execute(text("SHOW server_encoding")).scalar_one()
    finally:
        probe.dispose()
    assert encoding == "UTF8", "test database is not UTF-8 (RESEARCH F-10)"
    return name, url


def _drop_test_database(admin: Any, name: str) -> None:
    from sqlalchemy import text

    assert name.startswith("truthtrail_test_")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest.fixture(scope="session")
def db_url(pg_admin_url: str) -> Iterator[str]:
    """URL of a fresh ``truthtrail_test_{random}`` database, dropped at the end of the session."""
    admin = _admin_engine(pg_admin_url)
    name = None
    try:
        name, url = _create_test_database(admin, pg_admin_url)
        yield url
    finally:
        if name is not None:
            _drop_test_database(admin, name)
        admin.dispose()


class EmptyDatabases:
    """Factory of extra empty test databases; ``close()`` drops every one it created."""

    def __init__(self, admin_url: str) -> None:
        self._admin_url = admin_url
        self._admin = _admin_engine(admin_url)
        self.names: list[str] = []

    def __call__(self) -> str:
        name, url = _create_test_database(self._admin, self._admin_url)
        self.names.append(name)
        return url

    def close(self) -> None:
        try:
            while self.names:
                _drop_test_database(self._admin, self.names.pop())
        finally:
            self._admin.dispose()


@pytest.fixture
def empty_database(pg_admin_url: str) -> Iterator[EmptyDatabases]:
    """Call it to get the URL of a new empty database (migration tests need a fresh one)."""
    factory = EmptyDatabases(pg_admin_url)
    try:
        yield factory
    finally:
        factory.close()


def upgrade_to_head(url: str) -> None:
    """Apply the packaged migrations to ``url`` through one shared connection (Pattern 8)."""
    from alembic import command
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    from truthtrail.db import migration_config

    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.begin() as connection:
            command.upgrade(migration_config(connection), "head")
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def migrated_db_url(pg_admin_url: str) -> Iterator[str]:
    """URL of a ``truthtrail_test_{random}`` database at the packaged head, shared by the
    session and dropped at its end. Tests that write rows use ``clean_db`` as well."""
    admin = _admin_engine(pg_admin_url)
    name = None
    try:
        name, url = _create_test_database(admin, pg_admin_url)
        upgrade_to_head(url)
        yield url
    finally:
        if name is not None:
            _drop_test_database(admin, name)
        admin.dispose()


# Every application table of the baseline revision (D-20); TRUNCATE order does not matter
# with CASCADE, the list is fixed so a new table is added here deliberately.
APPLICATION_TABLES = (
    "news_queries",
    "accounts",
    "claims",
    "cascades",
    "events",
    "ingest_checkpoints",
    "ingest_runs",
    "news_fetches",
)


@pytest.fixture
def clean_db(migrated_db_url: str) -> str:
    """The migrated database with every application table emptied and identities reset."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    engine = create_engine(migrated_db_url, poolclass=NullPool)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("TRUNCATE " + ", ".join(APPLICATION_TABLES) + " RESTART IDENTITY CASCADE")
            )
    finally:
        engine.dispose()
    return migrated_db_url


@pytest.fixture
def make_engine(request: pytest.FixtureRequest) -> Callable[..., Any]:
    """Build an engine with ``create_db_engine`` and register ``dispose`` as a finalizer.

    ``filterwarnings = error`` turns a garbage-collected engine with open pooled connections
    into a failing test (RESEARCH F-09), so every engine a test builds goes through this
    factory. Keyword arguments (``role``, ``pool_size``, ``max_overflow``,
    ``statement_timeout_ms``) are passed through.
    """
    from truthtrail.db.engine import create_db_engine

    def make(url: str, **kwargs: Any) -> Any:
        engine = create_db_engine(url, **kwargs)
        request.addfinalizer(engine.dispose)
        return engine

    return make


# --- REQUIRE_DB_FLOOR (D-28): absence of database tests can never read as green ------------
_DB_TESTS_EXECUTED = [0]


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    executed = report.passed or report.failed
    if report.when == "call" and "requires_db" in report.keywords and executed:
        _DB_TESTS_EXECUTED[0] += 1


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    raw = SESSION_ENVIRON.get("REQUIRE_DB_FLOOR", "").strip()
    if not raw:
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    executed = _DB_TESTS_EXECUTED[0]
    if not raw.isdigit():
        message = "REQUIRE_DB_FLOOR must be a non-negative integer"
    elif executed < int(raw):
        message = (
            f"REQUIRE_DB_FLOOR: {executed} database tests executed, fewer than the floor {raw}"
        )
    else:
        return
    if reporter is not None:
        reporter.write_line(message, red=True, bold=True)
    if session.exitstatus == pytest.ExitCode.OK:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
