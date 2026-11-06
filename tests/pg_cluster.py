"""Throwaway PostgreSQL for the database tests (D-28, D-30; RESEARCH Pattern 11, F-10).

Imported by ``tests/conftest.py`` as ``pg_cluster`` (pytest puts ``tests/`` on ``sys.path``).

Provisioning order (``provision_admin_url``):

1. ``TEST_DATABASE_URL`` when it answers a one-second connect (CI service container, a
   developer's server). With ``REQUIRE_DB=1`` an unreachable URL is an error and there is NO
   fallback to a local cluster.
2. Otherwise a throwaway local cluster built from ``initdb`` and ``pg_ctl`` found through
   ``TRUTHTRAIL_PG_BIN``, the ``PATH``, ``/usr/lib/postgresql/*/bin`` (newest first) or
   ``C:\\Program Files\\PostgreSQL\\*\\bin``.
3. Otherwise ``ProvisioningError`` naming the remedies.

Cluster recipe: ``initdb -E UTF8 --locale=C`` (without it this container creates a SQL_ASCII
database and psycopg 3 returns bytes, F-10); PostgreSQL refuses to run as root, so when the
effective uid is 0 every command runs as the ``postgres`` system user through
``runuser -u postgres --`` inside a ``tempfile.mkdtemp`` directory chowned to that user with
mode 755 (pytest's ``tmp_path`` sits under a 0700 directory the user cannot enter). On Unix the
server listens only on a unix socket in that directory; on Windows only on 127.0.0.1. Durability
is switched off (fsync, synchronous_commit, full_page_writes) because the data is disposable.

Every command is a fixed argument list (no shell) with a timeout. No message here contains a
connection URL.
"""

from __future__ import annotations

import getpass
import glob as globmodule
import os
import re
import shutil
import socket
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

COMMAND_TIMEOUT_SECONDS = 120
PROBE_TIMEOUT_SECONDS = 1
POSTGRES_USER = "postgres"
UNIX_BIN_GLOB = "/usr/lib/postgresql/*/bin"
WINDOWS_BIN_GLOB = "C:\\Program Files\\PostgreSQL\\*\\bin"
REMEDIES = (
    "set TEST_DATABASE_URL to a reachable PostgreSQL server, or set TRUTHTRAIL_PG_BIN to a "
    'directory holding initdb and pg_ctl, or run the fast loop pytest -m "not requires_db"'
)


class ProvisioningError(RuntimeError):
    """No PostgreSQL could be provided for the database tests."""


def _is_windows() -> bool:
    return os.name == "nt"


def _executable(name: str, *, windows: bool) -> str:
    return f"{name}.exe" if windows else name


def _version_key(bindir: str) -> tuple[int, ...]:
    """Sort key from the version directory above ``bin`` (``.../16/bin`` -> (16,)).

    Splits on both separators so a Windows path sorts the same on any test platform.
    """
    parts = [part for part in re.split(r"[\\/]", bindir) if part]
    version = parts[-2] if len(parts) >= 2 else ""
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return (-1,)


def find_pg_bin(
    environ: Mapping[str, str],
    *,
    which: Callable[[str], str | None] = shutil.which,
    glob: Callable[[str], list[str]] = globmodule.glob,
    is_file: Callable[[Path], bool] = Path.is_file,
    windows: bool | None = None,
) -> Path | None:
    """Return the directory that holds both ``initdb`` and ``pg_ctl``, or None.

    Order: ``TRUTHTRAIL_PG_BIN`` (an error when set but incomplete), the directory of
    ``pg_ctl`` on the PATH, ``/usr/lib/postgresql/*/bin`` newest first, then the Windows
    ``Program Files`` installs newest first. The seams exist for the unit tests.
    """
    windows = _is_windows() if windows is None else windows

    def complete(directory: Path) -> bool:
        return all(
            is_file(directory / _executable(tool, windows=windows)) for tool in ("initdb", "pg_ctl")
        )

    explicit = environ.get("TRUTHTRAIL_PG_BIN", "").strip()
    if explicit:
        directory = Path(explicit)
        if not complete(directory):
            raise ProvisioningError(
                "TRUTHTRAIL_PG_BIN is set but that directory does not hold both initdb and pg_ctl"
            )
        return directory
    on_path = which(_executable("pg_ctl", windows=windows))
    if on_path and complete(Path(on_path).parent):
        return Path(on_path).parent
    pattern = WINDOWS_BIN_GLOB if windows else UNIX_BIN_GLOB
    for candidate in sorted(glob(pattern), key=_version_key, reverse=True):
        if complete(Path(candidate)):
            return Path(candidate)
    return None


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


class _Runner(Protocol):
    def __call__(self, args: Sequence[str], **kwargs: Any) -> Any: ...


class Cluster:
    """One throwaway cluster. ``start()`` builds and starts it, ``stop()`` always cleans up."""

    def __init__(
        self,
        bindir: Path,
        *,
        root: Path | None = None,
        port: int | None = None,
        euid: int | None = None,
        windows: bool | None = None,
        run: _Runner = subprocess.run,
    ) -> None:
        self.bindir = bindir
        self.windows = _is_windows() if windows is None else windows
        if euid is None:
            euid = -1 if self.windows else os.geteuid()
        self.as_postgres = not self.windows and euid == 0
        self.root = root
        self.port = port
        self._run = run
        # The account the server runs as (read back by test_provisioned_cluster_is_non_root).
        self.run_as = POSTGRES_USER if self.as_postgres else getpass.getuser()

    # --- command construction (pure, covered by dry-run unit tests) ----------------------
    def _tool(self, name: str) -> str:
        return str(self.bindir / _executable(name, windows=self.windows))

    def _prefix(self) -> list[str]:
        return ["runuser", "-u", POSTGRES_USER, "--"] if self.as_postgres else []

    def _require_layout(self) -> tuple[Path, int]:
        if self.root is None or self.port is None:
            raise ProvisioningError("cluster directory and port are not chosen yet")
        return self.root, self.port

    def initdb_command(self) -> list[str]:
        root, _port = self._require_layout()
        return [
            *self._prefix(),
            self._tool("initdb"),
            "-D",
            str(root / "data"),
            "-A",
            "trust",
            "-U",
            POSTGRES_USER,
            "-E",
            "UTF8",
            "--locale=C",
            "--no-sync",
        ]

    def server_options(self) -> str:
        root, port = self._require_layout()
        durability = "-c fsync=off -c synchronous_commit=off -c full_page_writes=off"
        if self.windows:
            # TCP on loopback only; no quotes (cmd.exe would pass them through literally).
            return f"-c listen_addresses=127.0.0.1 {durability} -c port={port}"
        # pg_ctl hands the options to /bin/sh, which turns '' into an empty value: no TCP.
        return (
            f"-c listen_addresses='' -c unix_socket_directories={root} {durability} -c port={port}"
        )

    def start_command(self) -> list[str]:
        root, _port = self._require_layout()
        return [
            *self._prefix(),
            self._tool("pg_ctl"),
            "-D",
            str(root / "data"),
            "-w",
            "-l",
            str(root / "log"),
            "-o",
            self.server_options(),
            "start",
        ]

    def stop_command(self) -> list[str]:
        root, _port = self._require_layout()
        return [
            *self._prefix(),
            self._tool("pg_ctl"),
            "-D",
            str(root / "data"),
            "-m",
            "immediate",
            "-w",
            "stop",
        ]

    def url(self) -> str:
        root, port = self._require_layout()
        if self.windows:
            return f"postgresql+psycopg://{POSTGRES_USER}@127.0.0.1:{port}/postgres"
        return f"postgresql+psycopg://{POSTGRES_USER}@/postgres?host={root}&port={port}"

    # --- lifecycle -----------------------------------------------------------------------
    def _execute(self, args: list[str]) -> None:
        self._run(
            args,
            check=True,
            capture_output=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
        )

    def _log_tail(self) -> str:
        if self.root is None:
            return ""
        try:
            lines = (self.root / "log").read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return ""
        return "\n".join(lines[-15:])

    def start(self) -> None:
        """Create the directory, run initdb and start the server; clean up on failure."""
        if self.root is None:
            self.root = Path(tempfile.mkdtemp(prefix="tt-pg-"))
        if self.port is None:
            self.port = _free_loopback_port()
        if self.as_postgres:
            import pwd  # Unix only

            account = pwd.getpwnam(POSTGRES_USER)
            os.chown(self.root, account.pw_uid, account.pw_gid)
            os.chmod(self.root, 0o755)  # the postgres user must traverse it
        try:
            self._execute(self.initdb_command())
            self._execute(self.start_command())
        except (OSError, subprocess.SubprocessError) as exc:
            tail = self._log_tail()
            self.stop()
            detail = f"; server log tail:\n{tail}" if tail else ""
            raise ProvisioningError(
                f"the throwaway PostgreSQL cluster did not start ({type(exc).__name__}){detail}"
            ) from None

    def postmaster_pid(self) -> int | None:
        """Process id from ``postmaster.pid`` while the server runs, else None."""
        if self.root is None:
            return None
        try:
            first = (self.root / "data" / "postmaster.pid").read_text(encoding="utf-8")
        except OSError:
            return None
        head = first.splitlines()[0].strip() if first else ""
        return int(head) if head.isdigit() else None

    def stop(self) -> None:
        """Stop the server (immediate mode) and remove the directory, even if stop fails."""
        if self.root is None:
            return
        try:
            if (self.root / "data" / "postmaster.pid").exists():
                self._execute(self.stop_command())
        except (OSError, subprocess.SubprocessError):
            pass  # removal below still runs; a dead server leaves nothing to stop
        finally:
            shutil.rmtree(self.root, ignore_errors=True)


@dataclass(frozen=True)
class Provisioned:
    """Where the database tests run: an admin URL, the mode and the local cluster if any."""

    admin_url: str
    mode: str  # "external" (TEST_DATABASE_URL) or "throwaway" (local cluster)
    cluster: Cluster | None


def _reachable(url: str) -> bool:
    """One short connect attempt; any failure is False (the reason is never echoed)."""
    import psycopg
    from sqlalchemy.engine import make_url

    try:
        conninfo = make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)
        with psycopg.connect(conninfo, connect_timeout=PROBE_TIMEOUT_SECONDS):
            return True
    except Exception:  # every failure means "not usable"
        return False


def provision_admin_url(
    environ: Mapping[str, str],
    *,
    which: Callable[[Mapping[str, str]], Path | None] = find_pg_bin,
    cluster_factory: Callable[[Path], Cluster] = Cluster,
    probe: Callable[[str], bool] = _reachable,
) -> Provisioned:
    """Pick the database for this session (see the module docstring for the order)."""
    url = environ.get("TEST_DATABASE_URL", "").strip()
    require = environ.get("REQUIRE_DB", "").strip() == "1"
    if url:
        if probe(url):
            return Provisioned(admin_url=url, mode="external", cluster=None)
        if require:
            raise ProvisioningError(
                "TEST_DATABASE_URL is set but the server did not answer, and REQUIRE_DB=1 "
                "forbids falling back to a local cluster"
            )
    bindir = which(environ)
    if bindir is None:
        raise ProvisioningError(f"no PostgreSQL is available for the database tests: {REMEDIES}")
    cluster = cluster_factory(bindir)
    cluster.start()
    return Provisioned(admin_url=cluster.url(), mode="throwaway", cluster=cluster)
