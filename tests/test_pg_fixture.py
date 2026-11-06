"""Real-PostgreSQL test infrastructure (D-28, RESEARCH Pattern 11, F-10).

Unit tests cover the provisioning order, the binary search and the cluster command lines with
fakes (no server). The ``requires_db`` tests run against the session's real server: the
throwaway cluster here, ``TEST_DATABASE_URL`` in CI.
"""

import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import conftest
import pytest
from pg_cluster import (
    REMEDIES,
    Cluster,
    Provisioned,
    ProvisioningError,
    find_pg_bin,
    provision_admin_url,
)

PW_MARKER = "Pw-Marker-q81Z"
EXTERNAL_URL = f"postgresql://tt:{PW_MARKER}@127.0.0.1:5432/postgres"


class FakeCluster(Cluster):
    """A cluster whose start() records the call instead of running initdb."""

    started: list["FakeCluster"] = []  # noqa: RUF012 - test-local registry

    def __init__(self, bindir: Path) -> None:
        super().__init__(bindir, root=Path("/fake/tt-pg-x"), port=5999, euid=1000, windows=False)

    def start(self) -> None:
        FakeCluster.started.append(self)


def _never_called(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError("must not be called")


# --- provisioning order ------------------------------------------------------------------
def test_reachable_test_database_url_wins() -> None:
    result = provision_admin_url(
        {"TEST_DATABASE_URL": EXTERNAL_URL},
        which=_never_called,
        cluster_factory=_never_called,
        probe=lambda url: True,
    )
    assert result == Provisioned(admin_url=EXTERNAL_URL, mode="external", cluster=None)


def test_require_db_with_unreachable_url_raises_and_never_builds_a_cluster() -> None:
    with pytest.raises(ProvisioningError) as info:
        provision_admin_url(
            {"TEST_DATABASE_URL": EXTERNAL_URL, "REQUIRE_DB": "1"},
            which=_never_called,
            cluster_factory=_never_called,
            probe=lambda url: False,
        )
    message = str(info.value)
    assert "REQUIRE_DB=1" in message
    assert "TEST_DATABASE_URL" in message
    assert PW_MARKER not in message
    assert "127.0.0.1" not in message


def test_unreachable_url_without_require_db_falls_back_to_a_cluster() -> None:
    FakeCluster.started.clear()
    result = provision_admin_url(
        {"TEST_DATABASE_URL": EXTERNAL_URL},
        which=lambda environ: Path("/fake/bin"),
        cluster_factory=FakeCluster,
        probe=lambda url: False,
    )
    assert result.mode == "throwaway"
    assert result.cluster is FakeCluster.started[0]
    assert result.admin_url == result.cluster.url()


def test_require_db_without_url_still_builds_a_cluster() -> None:
    FakeCluster.started.clear()
    result = provision_admin_url(
        {"REQUIRE_DB": "1"},
        which=lambda environ: Path("/fake/bin"),
        cluster_factory=FakeCluster,
        probe=_never_called,
    )
    assert result.mode == "throwaway"
    assert len(FakeCluster.started) == 1


def test_no_url_and_no_binaries_names_all_three_remedies() -> None:
    with pytest.raises(ProvisioningError) as info:
        provision_admin_url(
            {}, which=lambda environ: None, cluster_factory=_never_called, probe=_never_called
        )
    message = str(info.value)
    assert REMEDIES in message
    for remedy in ("TEST_DATABASE_URL", "TRUTHTRAIL_PG_BIN", 'pytest -m "not requires_db"'):
        assert remedy in message


def test_no_message_contains_a_password() -> None:
    environ = {"TEST_DATABASE_URL": EXTERNAL_URL}
    with pytest.raises(ProvisioningError) as info:
        provision_admin_url(
            environ, which=lambda e: None, cluster_factory=_never_called, probe=lambda u: False
        )
    assert PW_MARKER not in str(info.value)


# --- binary search -----------------------------------------------------------------------
def _fs(*files: str) -> Any:
    present = {Path(f) for f in files}
    return lambda path: Path(path) in present


def test_find_pg_bin_prefers_the_explicit_directory() -> None:
    found = find_pg_bin(
        {"TRUTHTRAIL_PG_BIN": "/opt/pg/bin"},
        which=lambda name: "/usr/bin/pg_ctl",
        glob=lambda pattern: ["/usr/lib/postgresql/16/bin"],
        is_file=_fs("/opt/pg/bin/initdb", "/opt/pg/bin/pg_ctl", "/usr/bin/initdb"),
        windows=False,
    )
    assert found == Path("/opt/pg/bin")


def test_find_pg_bin_rejects_an_incomplete_explicit_directory() -> None:
    with pytest.raises(ProvisioningError, match="TRUTHTRAIL_PG_BIN"):
        find_pg_bin(
            {"TRUTHTRAIL_PG_BIN": "/opt/pg/bin"},
            which=lambda name: None,
            glob=lambda pattern: [],
            is_file=_fs("/opt/pg/bin/pg_ctl"),
            windows=False,
        )


def test_find_pg_bin_uses_the_path_before_the_versioned_directories() -> None:
    found = find_pg_bin(
        {},
        which=lambda name: "/usr/local/pgsql/bin/pg_ctl" if name == "pg_ctl" else None,
        glob=lambda pattern: ["/usr/lib/postgresql/16/bin"],
        is_file=_fs(
            "/usr/local/pgsql/bin/initdb",
            "/usr/local/pgsql/bin/pg_ctl",
            "/usr/lib/postgresql/16/bin/initdb",
            "/usr/lib/postgresql/16/bin/pg_ctl",
        ),
        windows=False,
    )
    assert found == Path("/usr/local/pgsql/bin")


def test_find_pg_bin_skips_a_path_entry_without_initdb_and_picks_the_newest() -> None:
    patterns: list[str] = []

    def glob(pattern: str) -> list[str]:
        patterns.append(pattern)
        return [
            "/usr/lib/postgresql/9.6/bin",
            "/usr/lib/postgresql/16/bin",
            "/usr/lib/postgresql/10/bin",
        ]

    found = find_pg_bin(
        {},
        which=lambda name: "/usr/bin/pg_ctl",  # psql-only install: no initdb next to it
        glob=glob,
        is_file=_fs(
            "/usr/bin/pg_ctl",
            *(
                f"/usr/lib/postgresql/{v}/bin/{t}"
                for v in ("9.6", "16", "10")
                for t in ("initdb", "pg_ctl")
            ),
        ),
        windows=False,
    )
    assert found == Path("/usr/lib/postgresql/16/bin")
    assert patterns == ["/usr/lib/postgresql/*/bin"]


def test_find_pg_bin_searches_program_files_on_windows() -> None:
    root = "C:\\Program Files\\PostgreSQL"
    found = find_pg_bin(
        {},
        which=lambda name: None,
        glob=lambda pattern: (
            [f"{root}\\16\\bin", f"{root}\\17\\bin"] if "Program Files" in pattern else []
        ),
        # Path joins, as the code builds them, so the fake matches on every platform.
        is_file=_fs(
            *(
                str(Path(f"{root}\\{v}\\bin") / f"{t}.exe")
                for v in ("16", "17")
                for t in ("initdb", "pg_ctl")
            )
        ),
        windows=True,
    )
    assert found == Path(f"{root}\\17\\bin")


def test_find_pg_bin_returns_none_when_nothing_is_installed() -> None:
    assert (
        find_pg_bin(
            {}, which=lambda name: None, glob=lambda pattern: [], is_file=_fs(), windows=False
        )
        is None
    )


# --- cluster command lines (dry run, nothing is started) --------------------------------
def test_root_cluster_runs_every_command_as_the_postgres_user() -> None:
    cluster = Cluster(Path("/pg/bin"), root=Path("/tmp/tt-pg-a"), port=6001, euid=0, windows=False)
    prefix = ["runuser", "-u", "postgres", "--"]
    for command in (cluster.initdb_command(), cluster.start_command(), cluster.stop_command()):
        assert command[:4] == prefix
    initdb = cluster.initdb_command()
    assert initdb[4] == "/pg/bin/initdb"
    assert initdb[5:] == [
        "-D", "/tmp/tt-pg-a/data", "-A", "trust", "-U", "postgres",
        "-E", "UTF8", "--locale=C", "--no-sync",
    ]  # fmt: skip
    options = cluster.server_options()
    assert "-c listen_addresses=''" in options
    assert "-c unix_socket_directories=/tmp/tt-pg-a" in options
    assert "-c port=6001" in options
    for flag in ("fsync=off", "synchronous_commit=off", "full_page_writes=off"):
        assert f"-c {flag}" in options
    assert cluster.stop_command()[-4:] == ["-m", "immediate", "-w", "stop"]
    assert cluster.url() == "postgresql+psycopg://postgres@/postgres?host=/tmp/tt-pg-a&port=6001"
    assert cluster.run_as == "postgres"


def test_non_root_unix_cluster_runs_commands_directly() -> None:
    cluster = Cluster(
        Path("/pg/bin"), root=Path("/tmp/tt-pg-b"), port=6002, euid=1000, windows=False
    )
    assert cluster.initdb_command()[0] == "/pg/bin/initdb"
    assert cluster.start_command()[0] == "/pg/bin/pg_ctl"
    assert cluster.run_as != "postgres" or os.environ.get("USER") == "postgres"


def test_windows_cluster_listens_on_loopback_tcp() -> None:
    cluster = Cluster(
        Path("C:\\pg\\bin"), root=Path("C:\\tmp\\tt-pg-c"), port=6003, euid=0, windows=True
    )
    start = cluster.start_command()
    assert "runuser" not in start
    assert start[0].endswith("pg_ctl.exe")
    options = cluster.server_options()
    assert "-c listen_addresses=127.0.0.1" in options
    assert "unix_socket_directories" not in options
    assert "'" not in options
    assert cluster.url() == "postgresql+psycopg://postgres@127.0.0.1:6003/postgres"


def test_stop_removes_the_directory_even_when_pg_ctl_fails(tmp_path: Path) -> None:
    root = tmp_path / "tt-pg-d"
    (root / "data").mkdir(parents=True)
    (root / "data" / "postmaster.pid").write_text("123\n", encoding="utf-8")
    calls: list[Sequence[str]] = []

    def failing_run(args: Sequence[str], **kwargs: Any) -> Any:
        calls.append(args)
        raise subprocess.CalledProcessError(1, list(args))

    cluster = Cluster(
        Path("/pg/bin"), root=root, port=6004, euid=1000, windows=False, run=failing_run
    )
    cluster.stop()
    assert calls
    assert calls[0][-1] == "stop"
    assert not root.exists()


def test_failed_start_cleans_up_and_raises_a_provisioning_error(tmp_path: Path) -> None:
    root = tmp_path / "tt-pg-e"
    root.mkdir()

    def failing_run(args: Sequence[str], **kwargs: Any) -> Any:
        raise subprocess.CalledProcessError(1, list(args))

    cluster = Cluster(
        Path("/pg/bin"), root=root, port=6005, euid=1000, windows=False, run=failing_run
    )
    with pytest.raises(ProvisioningError, match="did not start"):
        cluster.start()
    assert not root.exists()


# --- conftest hooks: marker enforcement and the REQUIRE_DB_FLOOR check --------------------
class _Item:
    def __init__(self, nodeid: str, fixtures: tuple[str, ...], marked: bool) -> None:
        self.nodeid, self.fixturenames, self._marked = nodeid, fixtures, marked

    def get_closest_marker(self, name: str) -> object | None:
        return object() if self._marked and name == "requires_db" else None


def test_a_database_fixture_without_the_marker_is_a_usage_error() -> None:
    items = [
        _Item("t.py::ok", ("db_url",), True),
        _Item("t.py::plain", ("tmp_path",), False),
        _Item("t.py::bad", ("make_engine", "db_url"), False),
    ]
    with pytest.raises(pytest.UsageError, match=r"t\.py::bad"):
        conftest.pytest_collection_modifyitems(None, items)  # type: ignore[arg-type]
    conftest.pytest_collection_modifyitems(None, items[:2])  # type: ignore[arg-type]


class _Reporter:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def write_line(self, line: str, **markup: bool) -> None:
        self.lines.append(line)


class _Session:
    def __init__(self, reporter: _Reporter) -> None:
        self.exitstatus = pytest.ExitCode.OK
        manager = type("PM", (), {"get_plugin": staticmethod(lambda name: reporter)})()
        self.config = type("Config", (), {"pluginmanager": manager})()


@pytest.mark.parametrize(
    ("floor", "executed", "fails"),
    [("", 0, False), ("3", 3, False), ("3", 2, True), ("0", 0, False), ("three", 9, True)],
)
def test_require_db_floor(
    floor: str, executed: int, fails: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(conftest.SESSION_ENVIRON, "REQUIRE_DB_FLOOR", floor)
    monkeypatch.setattr(conftest, "_DB_TESTS_EXECUTED", [executed])
    reporter = _Reporter()
    session = _Session(reporter)
    conftest.pytest_sessionfinish(session, 0)  # type: ignore[arg-type]
    assert (session.exitstatus == pytest.ExitCode.TESTS_FAILED) is fails
    assert bool(reporter.lines) is fails
    assert all("REQUIRE_DB_FLOOR" in line for line in reporter.lines)


# --- against the real server ------------------------------------------------------------
@pytest.mark.requires_db
def test_database_is_utf8_and_named_for_tests(db_url: str, make_engine: Any) -> None:
    from sqlalchemy import text
    from sqlalchemy.engine import make_url

    assert make_url(db_url).database.startswith("truthtrail_test_")
    engine = make_engine(db_url)
    with engine.connect() as connection:
        assert connection.execute(text("SHOW server_encoding")).scalar_one() == "UTF8"
        assert (
            connection.execute(text("SELECT current_database()"))
            .scalar_one()
            .startswith("truthtrail_test_")
        )


@pytest.mark.requires_db
def test_make_engine_runs_a_query(db_url: str, make_engine: Any) -> None:
    from sqlalchemy import text

    engine = make_engine(db_url)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1


@pytest.mark.requires_db
def test_empty_databases_are_distinct_and_dropped(
    empty_database: Any, pg_admin_url: str, make_engine: Any
) -> None:
    from sqlalchemy import text
    from sqlalchemy.engine import make_url

    first, second = empty_database(), empty_database()
    names = [make_url(first).database, make_url(second).database]
    assert names[0] != names[1]
    assert all(name.startswith("truthtrail_test_") for name in names)
    admin = make_engine(pg_admin_url)
    query = text("SELECT count(*) FROM pg_database WHERE datname = ANY(:names)")
    with admin.connect() as connection:
        assert connection.execute(query, {"names": names}).scalar_one() == 2
    empty_database.close()  # the same call the fixture finalizer makes
    with admin.connect() as connection:
        assert connection.execute(query, {"names": names}).scalar_one() == 0


@pytest.mark.requires_db
def test_provisioned_cluster_is_non_root(pg_provisioning: Provisioned) -> None:
    if pg_provisioning.mode == "throwaway":
        cluster = pg_provisioning.cluster
        assert cluster is not None
        pid = cluster.postmaster_pid()
        assert pid is not None
        if sys.platform.startswith("linux"):
            status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
            uid_line = next(line for line in status.splitlines() if line.startswith("Uid:"))
            real, effective = (int(v) for v in uid_line.split()[1:3])
            assert real != 0
            assert effective != 0
        else:
            assert cluster.run_as not in {"root", ""}
    else:
        assert pg_provisioning.mode == "external"
        # CI's service container: no local cluster is started next to the external database.
        assert pg_provisioning.cluster is None
