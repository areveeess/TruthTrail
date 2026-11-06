"""Container-only confirmation of the LIVE collector path with REAL data (plan 03-05, D-10, D-11).

Not collected by pytest and never run in CI: this is the one bounded check that touches the real
public Jetstream. It provisions a throwaway PostgreSQL (``pg_cluster.provision_admin_url``),
creates a ``truthtrail_test_{random}`` database, migrates it with the packaged command, generates
a throwaway PSEUDONYM_SECRET in memory, and runs

    python -m truthtrail.ingest run --max-seconds 180 --max-events 100000

as a subprocess against the public stream, with TRACK_SAMPLE_PER_10K=10000 (so the check does
not depend on the ratified sampling rate) and the ratified allowlist and bounds otherwise. It
then checks: exit code 0, run status ok with stop reason max_seconds, well over 1000 frames, at
least one cascade and one root event stored, every stored identifier a keyed token of the
expected length, no stored text column holding ``did:`` or ``at://``, and no ``did:`` in the
collector's output. It prints counts only, and drops the database and stops the cluster in
``finally`` blocks, so nothing raw outlives the run or reaches the repository.

Exit codes: 0 every check passed, 1 a check failed, 3 the stream answered HTTP 401 or 403 (STOP
and report; never substitute data), 5 no database could be provisioned.

Run from the repository root: ``.venv/bin/python tests/live_smoke.py``.
"""

from __future__ import annotations

import base64
import os
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
MAX_SECONDS = 180
MAX_EVENTS = 100_000
MIN_FRAMES = 1000
PASS_THROUGH = (
    "PATH",
    "SYSTEMROOT",
    "HTTPS_PROXY",
    "https_proxy",
    "NO_PROXY",
    "no_proxy",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
)


def _say(text: str) -> None:
    print(f"live-smoke: {text}", flush=True)


def _environment(url: str, secret: str) -> dict[str, str]:
    env = {name: os.environ[name] for name in PASS_THROUGH if name in os.environ}
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "DATABASE_URL": url,
            "PSEUDONYM_SECRET": secret,
            "TRACK_SAMPLE_PER_10K": "10000",
        }
    )
    return env


def _checks(engine: Any, output: str) -> list[str]:
    from sqlalchemy import text

    failures: list[str] = []
    with engine.connect() as connection:
        run = connection.execute(
            text("SELECT status, counters, error_class FROM ingest_runs ORDER BY id DESC LIMIT 1")
        ).one()
        counts = {
            name: connection.execute(text(f"SELECT count(*) FROM {name}")).scalar_one()
            for name in ("events", "cascades", "accounts", "claims")
        }
        roots = connection.execute(
            text("SELECT count(*) FROM events WHERE edge_kind = 'root'")
        ).scalar_one()
        bad_keys = connection.execute(
            text(
                "SELECT count(*) FROM events WHERE length(uri) <> 20"
                " OR coalesce(length(parent_uri), 20) <> 20"
                " OR coalesce(length(reply_root_uri), 20) <> 20"
                " OR coalesce(length(quoted_uri), 20) <> 20"
                " OR coalesce(length(via_uri), 20) <> 20"
            )
        ).scalar_one()
        bad_accounts = connection.execute(
            text("SELECT count(*) FROM accounts WHERE length(pseudonym) <> 16")
        ).scalar_one()
        raw_ids = connection.execute(
            text(
                "SELECT count(*) FROM events WHERE coalesce(text, '') LIKE '%did:%'"
                " OR coalesce(text, '') LIKE '%at://%'"
            )
        ).scalar_one()
        raw_claims = connection.execute(
            text(
                "SELECT count(*) FROM claims WHERE coalesce(text, '') LIKE '%did:%'"
                " OR coalesce(url_canonical, '') LIKE '%at://%'"
            )
        ).scalar_one()
    status, counters, error_class = run
    frames = int(counters.get("frames", 0))
    _say(
        f"status={status} stop_max_seconds={counters.get('stop:max_seconds', 0)} frames={frames}"
        f" events={counts['events']} roots={roots} cascades={counts['cascades']}"
        f" accounts={counts['accounts']} claims={counts['claims']}"
        f" children={counts['events'] - roots} gaps={counters.get('gap:outdated_cursor', 0)}"
        f" error_class={error_class}"
    )
    if status != "ok":
        failures.append("run status is not ok")
    if counters.get("stop:max_seconds") != 1:
        failures.append("the run did not stop at max_seconds")
    if frames <= MIN_FRAMES:
        failures.append("too few frames")
    if counts["cascades"] < 1 or roots < 1:
        failures.append("no tracked cascade stored")
    if bad_keys or bad_accounts:
        failures.append("an identifier is not a keyed token of the expected length")
    if raw_ids or raw_claims:
        failures.append("a stored text column holds did: or at://")
    if "did:" in output:
        failures.append("the collector output contains did:")
    return failures


def main() -> int:
    sys.path.insert(0, str(HERE))
    from pg_cluster import ProvisioningError, provision_admin_url
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.pool import NullPool

    try:
        provisioned = provision_admin_url(os.environ)
    except ProvisioningError:
        _say("no PostgreSQL could be provisioned")
        return 5
    admin = create_engine(provisioned.admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    name = f"truthtrail_test_{secrets.token_hex(4)}"
    engine = None
    try:
        with admin.connect() as connection:
            connection.execute(
                text(f"CREATE DATABASE \"{name}\" ENCODING 'UTF8' TEMPLATE template0")
            )
        url = (
            make_url(provisioned.admin_url).set(database=name).render_as_string(hide_password=False)
        )
        secret = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
        env = _environment(url, secret)
        migrate = subprocess.run(
            [sys.executable, "-m", "truthtrail.db", "migrate"],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if migrate.returncode != 0:
            _say(f"migration failed with exit {migrate.returncode}")
            return 1
        _say(f"streaming the public Jetstream for {MAX_SECONDS} s (bounded)")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "truthtrail.ingest",
                "run",
                "--max-seconds",
                str(MAX_SECONDS),
                "--max-events",
                str(MAX_EVENTS),
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=MAX_SECONDS + 240,
        )
        engine = create_engine(url, poolclass=NullPool)
        with engine.connect() as connection:
            error_class = connection.execute(
                text("SELECT error_class FROM ingest_runs ORDER BY id DESC LIMIT 1")
            ).scalar_one_or_none()
        _say(f"collector exit code {result.returncode}")
        if error_class == "SourceForbidden":
            _say("the stream answered HTTP 401 or 403: STOP and report; no data is substituted")
            return 3
        failures = _checks(engine, result.stdout + result.stderr)
        if result.returncode != 0:
            failures.append("the collector did not exit 0")
        for failure in failures:
            _say(f"FAILED: {failure}")
        if not failures:
            _say("all checks passed")
        return 1 if failures else 0
    finally:
        if engine is not None:
            engine.dispose()
        try:
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        finally:
            admin.dispose()
            if provisioned.cluster is not None:
                provisioned.cluster.stop()


if __name__ == "__main__":
    raise SystemExit(main())
