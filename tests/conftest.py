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

import base64
import ipaddress
import json
import os
import random
import secrets
import socket
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
import responses
from hypothesis import HealthCheck, settings

import truthtrail
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


# --- Recorded real-data fixture (D-04) and the pseudonymiser (D-17) ------------------------
# Located from the installed package, never from the working directory (Phase 2 D-22).
RECORDED_DIR = Path(truthtrail.__file__).resolve().parent / "data" / "recorded"
FIXTURE_DATE = "2026-10-19"
FIXTURE_MAIN = RECORDED_DIR / f"bluesky-{FIXTURE_DATE}.jsonl"
FIXTURE_SAMPLES = RECORDED_DIR / f"bluesky-{FIXTURE_DATE}.samples.jsonl"
FIXTURE_MANIFEST = RECORDED_DIR / f"bluesky-{FIXTURE_DATE}.manifest.json"
# Clearly fake test secret for the keyed pseudonymiser: 32 random bytes generated per session
# (never a literal), base64url text exactly as an operator would set PSEUDONYM_SECRET.
FAKE_PSEUDONYM_SECRET = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


def fixture_manifest() -> dict[str, Any]:
    """The parsed manifest. A contract key that is absent raises KeyError naming it, so a count
    is read by its exact key and never improvised."""
    data: dict[str, Any] = json.loads(FIXTURE_MANIFEST.read_text(encoding="utf-8"))
    return data


def recorded_lines() -> Iterator[str]:
    """Every line of the main replay file, in file order (UTF-8, LF)."""
    with FIXTURE_MAIN.open(encoding="utf-8", newline="\n") as handle:
        for line in handle:
            yield line.rstrip("\n")


def recorded_frames() -> Iterator[dict[str, Any]]:
    """Every frame of the main replay file, parsed, in file order."""
    for line in recorded_lines():
        yield json.loads(line)


def find_frame(predicate: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
    """The first real recorded frame matching ``predicate``; LookupError when none does."""
    for frame in recorded_frames():
        if predicate(frame):
            return frame
    raise LookupError("no recorded frame matches the predicate")


def sample_rows() -> list[dict[str, Any]]:
    """Rows of the samples file: ``{"dialect": "v1" | "v2", "frame": {...}}`` (own token
    universe: its tokens never join to the main file)."""
    text = FIXTURE_SAMPLES.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def fixture_selection_policy() -> dict[str, Any]:
    """The manifest's ``selection_policy`` block: exactly the policy the cutter used."""
    block: dict[str, Any] = fixture_manifest()["selection_policy"]
    return block


@pytest.fixture(scope="session")
def fixture_allowlist_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The manifest's allowlist domains in the ``domain  # category`` format of the allowlist
    file, so fixture-driven tests never read the editable seed_domains.txt."""
    path = tmp_path_factory.mktemp("fixture-allowlist") / "allowlist.txt"
    domains = fixture_selection_policy()["allowlist_domains"]
    body = "".join(f"{domain}  # manifest\n" for domain in domains)
    path.write_text("# allowlist recorded in the fixture manifest at cut time\n" + body, "utf-8")
    return path


@pytest.fixture(scope="session")
def fixture_policy_environment(fixture_allowlist_file: Path) -> dict[str, str]:
    """Policy environment for subprocess tests, built from the manifest block. The active-root
    and total caps are raised above the fixture's own size (the cutter applied no such cap), so
    neither a ratified rate nor a ratified cap can change what a fixture replay selects."""
    block = fixture_selection_policy()
    frames = sum(1 for _line in recorded_lines())
    return {
        "TRACK_SAMPLE_PER_10K": str(block["sample_per_10k"]),
        "TRACK_ALLOWLIST_FILE": str(fixture_allowlist_file),
        "TRACK_REQUIRE_LANG": str(block["require_lang"]),
        "TRACK_ROOT_TTL_HOURS": str(block["root_ttl_hours"]),
        "TRACK_MAX_EVENTS_PER_CASCADE": str(block["max_events_per_cascade"]),
        "TRACK_MAX_ACTIVE_ROOTS": str(frames * 10),
        "STORE_MAX_EVENTS_TOTAL": str(frames * 10),
    }


@pytest.fixture
def keyer() -> Any:
    """A Keyer under the session's fake secret."""
    from truthtrail.ingest.pseudonym import make_keyer, parse_secret

    return make_keyer(parse_secret(FAKE_PSEUDONYM_SECRET))


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


# --- Collector pipeline helpers (plan 03-05, D-14, D-15, SC3) ---------------------------------
# Explicit TEST policy values. The selection fields come from the manifest's selection_policy
# block (``fixture_selection_policy()``), so a fixture replay reproduces the cut-time yield; the
# allowlist is the manifest's domain list materialised by ``fixture_allowlist_file`` (never the
# editable seed_domains.txt). The caps are raised above the fixture's own size, and the
# retention values are arbitrary positive test numbers. Nothing here reads a Policy default.
TEST_RETENTION_TEXT_DAYS = 7
TEST_RETENTION_CASCADE_DAYS = 30
TEST_RETENTION_TOMBSTONE_DAYS = 3
TEST_REWIND_SECONDS = 30
# The per-cascade cap the overflow, idempotency and crash-resume tests share: small enough that
# the largest fixture cascades overflow (each test asserts that it really does).
TEST_SMALL_CASCADE_CAP = 4


def fixture_frame_count() -> int:
    return sum(1 for _line in recorded_lines())


def make_test_policy(allowlist_file: Path, **overrides: Any) -> Policy:
    """A Policy built from explicit test values only; ``overrides`` replace single fields."""
    block = fixture_selection_policy()
    frames = fixture_frame_count()
    values: dict[str, Any] = {
        "track_sample_per_10k": block["sample_per_10k"],
        "track_allowlist_file": allowlist_file,
        "track_require_lang": block["require_lang"],
        "track_root_ttl_hours": block["root_ttl_hours"],
        "track_max_events_per_cascade": block["max_events_per_cascade"],
        "track_max_active_roots": frames * 10,
        "store_max_events_total": frames * 10,
        "track_seed_claim_url_match": False,
        "retention_text_days": TEST_RETENTION_TEXT_DAYS,
        "retention_cascade_days": TEST_RETENTION_CASCADE_DAYS,
        "retention_tombstone_days": TEST_RETENTION_TOMBSTONE_DAYS,
        "ingest_rewind_seconds": TEST_REWIND_SECONDS,
    }
    values.update(overrides)
    return Policy(**values)


@pytest.fixture
def explicit_policy(fixture_allowlist_file: Path) -> Callable[..., Policy]:
    """Factory of explicit test policies (see ``make_test_policy``)."""

    def build(**overrides: Any) -> Policy:
        return make_test_policy(fixture_allowlist_file, **overrides)

    return build


class ListSource:
    """An ``EventSource`` test double over a list of ``SourceItem`` values (replay semantics:
    items whose cursor is before the resume cursor are skipped, control items pass)."""

    def __init__(self, items: list[Any], *, mode: str = "replay", host: str = "list") -> None:
        self._items = list(items)
        self._mode = mode
        self._host = host

    @property
    def mode(self) -> Any:
        return self._mode

    @property
    def dialect(self) -> Any:
        return "v2"

    @property
    def host(self) -> str:
        return self._host

    async def items(self, resume_cursor_us: int | None, drops: Any = None) -> Any:
        for item in self._items:
            cursor = item.cursor_us
            if resume_cursor_us is not None and cursor is not None and cursor < resume_cursor_us:
                continue
            yield item


def fixture_items(keyer: Any, resume_cursor_us: int | None = None) -> list[Any]:
    """Every item ReplaySource yields for the packaged fixture from ``resume_cursor_us``."""
    import asyncio

    from truthtrail.ingest.source import DEFAULT_MANIFEST, ReplaySource

    async def collect() -> list[Any]:
        source = ReplaySource(DEFAULT_MANIFEST, keyer)
        return [item async for item in source.items(resume_cursor_us)]

    return asyncio.run(collect())


class PipelineRun:
    """Outcome of ``run_pipeline``: outcome counts, flush results and the index used."""

    def __init__(
        self, outcomes: Any, results: list[Any], index: Any, decider: Any, per_item: list[Any]
    ) -> None:
        self.outcomes = outcomes
        self.results = results
        self.index = index
        self.decider = decider
        self.per_item = per_item  # (result, outcome) in processing order

    def keys_with(self, outcome: str) -> list[str]:
        return [r.uri_key for r, o in self.per_item if o == outcome and hasattr(r, "edge_kind")]

    @property
    def inserted(self) -> int:
        return sum(r.inserted for r in self.results)

    @property
    def duplicates(self) -> int:
        return sum(r.duplicates for r in self.results)

    @property
    def overflow_counted(self) -> int:
        return sum(r.overflow_counted for r in self.results)


def run_pipeline(
    engine: Any,
    policy: Policy,
    items: list[Any],
    *,
    since_us: int | None = None,
    batch_rows: int = 100,
    source: str = "test-replay",
    known_claim_urls: Any = frozenset(),
    stop_after: int | None = None,
) -> PipelineRun:
    """Items -> Decider -> writer, synchronously, the way the run loop does it: the index is
    loaded first (``since_us`` None loads every cascade), batches flush at ``batch_rows`` rows,
    the index commits and expires only after a flush. ``stop_after`` stops after that many
    items (an in-process stop; the final partial batch is flushed)."""
    from collections import Counter

    from truthtrail.ingest import selection
    from truthtrail.ingest.writer import Batch, Decider, TrackedIndex, flush

    index = TrackedIndex()
    with engine.connect() as connection:
        index.load(connection, since_us)
    decider = Decider(
        policy, index, selection.load_allowlist(policy.track_allowlist_file), known_claim_urls
    )
    outcomes: Counter[str] = Counter()
    results: list[Any] = []
    per_item: list[Any] = []
    batch = Batch()

    def commit() -> None:
        nonlocal batch
        result = flush(engine, batch, source=source, dialect="v2", host="recorded")
        index.commit(result, batch)
        outcomes.update(batch.counters)
        if batch.max_time_us is not None:
            index.expire(batch.max_time_us)
        results.append(result)
        batch = Batch()

    for number, item in enumerate(items, start=1):
        batch.note_cursor(item.cursor_us)
        outcome = decider.process(item.result, batch)
        outcomes[outcome] += 1
        per_item.append((item.result, outcome))
        if batch.rows >= batch_rows:
            commit()
        if stop_after is not None and number >= stop_after:
            break
    commit()
    return PipelineRun(outcomes, results, index, decider, per_item)


PROJECTION_QUERIES = {
    "events": (
        "SELECT e.uri, e.edge_kind, e.inferred, e.parent_uri, e.reply_root_uri, e.quoted_uri,"
        " e.via_uri, e.parent_state, c.root_uri, a.pseudonym, e.observed_at, e.occurred_at,"
        " e.text, cl.claim_key, e.lang, e.deleted_at"
        " FROM events e LEFT JOIN cascades c ON c.id = e.cascade_id"
        " LEFT JOIN accounts a ON a.id = e.account_id LEFT JOIN claims cl ON cl.id = e.claim_id"
        " ORDER BY e.uri"
    ),
    "cascades": (
        "SELECT c.root_uri, cl.claim_key, c.tracking_ends_at, c.first_event_at,"
        " c.last_event_at, c.overflow_count, c.overflow_through_us, c.root_deleted_at"
        " FROM cascades c LEFT JOIN claims cl ON cl.id = c.claim_id ORDER BY c.root_uri"
    ),
    "accounts": "SELECT pseudonym, first_observed_at FROM accounts ORDER BY pseudonym",
    "claims": (
        "SELECT claim_key, kind, text, text_hash, url_canonical, link_domain"
        " FROM claims ORDER BY claim_key"
    ),
    "ingest_checkpoints": (
        "SELECT source, dialect, host, cursor_time_us FROM ingest_checkpoints ORDER BY source"
    ),
}
COUNTED_TABLES = ("events", "cascades", "accounts", "claims", "ingest_checkpoints")


def canonical_projection(engine: Any) -> dict[str, list[tuple[Any, ...]]]:
    """Every table by natural key (no surrogate ids), independent of insertion order."""
    from sqlalchemy import text

    with engine.connect() as connection:
        return {
            name: [tuple(row) for row in connection.execute(text(query))]
            for name, query in PROJECTION_QUERIES.items()
        }


def row_counts(engine: Any) -> dict[str, int]:
    """Row count per collector table."""
    from sqlalchemy import text

    with engine.connect() as connection:
        return {
            name: int(connection.execute(text("SELECT count(*) FROM " + name)).scalar_one())
            for name in COUNTED_TABLES
        }


# --- Enrich helpers (plan 03-06, D-14, D-22, SC4) --------------------------------------------
# A constructed row: (uri, edge_kind, parent_uri, observed_at, account_pseudonym, deleted).
# Keys are short test strings that fit the keyed-column widths (uri 20, pseudonym 16).
ForestRow = tuple[str, str, "str | None", Any, "str | None", bool]
TOMBSTONE_DELAY_SECONDS = 60


def insert_forest(
    engine: Any,
    rows: list[Any],
    *,
    root_uri: str,
    order: list[int] | None = None,
    id_base: int = 1000,
    tracking_ends_at: Any = None,
) -> int:
    """Insert constructed rows by direct parameterised SQL into the cascade of ``root_uri``
    (created dirty when missing) in ``order`` (a permutation of row indexes, default as given),
    with explicit surrogate ids ``id_base + position``, so two permutations get different ids
    for the same uri. A deleted row is a minimal tombstone (D-16). Returns the cascade id."""
    from datetime import timedelta

    from sqlalchemy import text

    sequence = list(range(len(rows))) if order is None else list(order)
    first = min((r[3] for r in rows), default=None)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO cascades (root_uri, tracking_ends_at, first_event_at, last_event_at)"
                " VALUES (:root, :ends, :first, :first) ON CONFLICT (root_uri) DO NOTHING"
            ),
            {
                "root": root_uri,
                "ends": tracking_ends_at or (first + timedelta(hours=48)),
                "first": first,
            },
        )
        cascade_id = int(
            connection.execute(
                text("SELECT id FROM cascades WHERE root_uri = :root"), {"root": root_uri}
            ).scalar_one()
        )
        for position, index in enumerate(sequence):
            uri, kind, parent, observed, account, deleted = rows[index]
            account_id = None
            if account is not None and not deleted:
                account_id = connection.execute(
                    text(
                        "INSERT INTO accounts (pseudonym, first_observed_at) VALUES (:p, :t)"
                        " ON CONFLICT (pseudonym) DO UPDATE SET pseudonym = EXCLUDED.pseudonym"
                        " RETURNING id"
                    ),
                    {"p": account, "t": observed},
                ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO events (id, uri, edge_kind, inferred, parent_uri, parent_state,"
                    " cascade_id, account_id, observed_at, deleted_at)"
                    " VALUES (:id, :uri, :kind, :inferred, :parent, :state, :cascade, :account,"
                    " :observed, :deleted_at)"
                ),
                {
                    "id": id_base + position,
                    "uri": uri,
                    "kind": kind,
                    "inferred": kind == "repost",
                    "parent": None if kind == "root" else parent,
                    "state": "none" if kind == "root" else "orphan",
                    "cascade": cascade_id,
                    "account": account_id,
                    "observed": observed,
                    "deleted_at": (
                        observed + timedelta(seconds=TOMBSTONE_DELAY_SECONDS) if deleted else None
                    ),
                },
            )
    return cascade_id


def set_checkpoint(engine: Any, cursor_us: int, *, source: str = "test-replay") -> None:
    """Write (or move) an ingest checkpoint at stream time ``cursor_us``."""
    from sqlalchemy import text

    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO ingest_checkpoints (source, dialect, host, cursor_time_us)"
                " VALUES (:s, 'v2', 'test', :c) ON CONFLICT (source) DO UPDATE"
                " SET cursor_time_us = EXCLUDED.cursor_time_us, updated_at = now()"
            ),
            {"s": source, "c": cursor_us},
        )


ENRICH_COUNTERS = (
    "event_count",
    "reply_count",
    "quote_count",
    "repost_count",
    "unique_accounts",
    "max_depth",
    "orphan_count",
    "disconnected_count",
    "deleted_count",
    "order_violation_count",
    "events_1h",
)


def enrich_projection(engine: Any) -> dict[str, Any]:
    """What enrich derived, keyed by natural keys only (no surrogate ids): per event uri the
    parent state, the resolved parent's uri (a join, not the id) and the depth; per cascade
    root the counters, times, flag, rolled_up_at and rollup_version."""
    from sqlalchemy import text

    with engine.connect() as connection:
        events = {
            uri: (state, parent, depth, root)
            for uri, state, parent, depth, root in connection.execute(
                text(
                    "SELECT e.uri, e.parent_state, p.uri, e.depth, c.root_uri FROM events e"
                    " LEFT JOIN events p ON p.id = e.parent_event_id"
                    " LEFT JOIN cascades c ON c.id = e.cascade_id ORDER BY e.uri"
                )
            )
        }
        columns = ", ".join(ENRICH_COUNTERS)
        cascades = {
            row[0]: tuple(row[1:])
            for row in connection.execute(
                text(
                    "SELECT root_uri, "
                    + columns
                    + ", first_event_at, last_event_at, enrich_dirty, rolled_up_at,"
                    " rollup_version FROM cascades ORDER BY root_uri"
                )
            )
        }
    return {"events": events, "cascades": cascades}


def truncate_application_tables(engine: Any) -> None:
    """Empty every application table (used at the start of each database Hypothesis example)."""
    from sqlalchemy import text

    with engine.begin() as connection:
        connection.execute(
            text("TRUNCATE " + ", ".join(APPLICATION_TABLES) + " RESTART IDENTITY CASCADE")
        )
