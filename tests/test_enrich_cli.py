"""The ``python -m truthtrail.enrich`` commands (D-10, D-16, D-18, OD-1).

Subprocess runs of ``run`` and ``purge`` exit 0 and print one counts-only line; the database is
prepared by the shared in-process pipeline (the fixture selection policy and allowlist) or, in
one test, by the ingest CLI subprocess with ``fixture_policy_environment()``; both must hold
``coverage.tracked_roots`` cascades, so the two selections cannot diverge. Purge always gets
explicit RETENTION_* values, never the ratified defaults. Configuration errors exit 3 naming the
variable and never the value, a database failure exits 5, a held lock exits 6, and usage
errors exit 2 without echoing the argument. Output never carries an identifier.
"""

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from conftest import (
    FAKE_PSEUDONYM_SECRET,
    fixture_items,
    fixture_manifest,
    row_counts,
    run_pipeline,
)
from sqlalchemy import text
from sqlalchemy.engine import make_url

from truthtrail.db.locks import (
    ENRICH_LOCK_KEY,
    PURGE_LOCK_KEY,
    release_advisory_lock,
    try_advisory_lock,
)
from truthtrail.enrich.__main__ import EXIT_CONFIG, EXIT_DATABASE, EXIT_LOCKED, EXIT_USAGE, main

SRC = Path(__file__).resolve().parent.parent / "src"
MARKER_VALUE = "constructed-marker-value-7d1e"
# Explicit test windows (never the ratified defaults), relative to the fixture day 2026-10-19.
RETENTION_ENV = {
    "RETENTION_TEXT_DAYS": "1",
    "RETENTION_CASCADE_DAYS": "40",
    "RETENTION_TOMBSTONE_DAYS": "1",
    "RETENTION_NEWS_DAYS": "5",
    "RETENTION_DORMANT_DAYS": "0",
}
PURGE_AS_OF = "2026-10-22T00:00:00+00:00"
RUN_AS_OF = "2026-10-19T23:00:00+00:00"


def cli(
    args: list[str], env: dict[str, str], cwd: Path, timeout: int = 180
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "truthtrail.enrich", *args],
        env={**env, "PYTHONPATH": str(SRC)},
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def identifiers(engine: Any) -> set[str]:
    with engine.connect() as connection:
        found = {u for (u,) in connection.execute(text("SELECT uri FROM events"))}
        found |= {p for (p,) in connection.execute(text("SELECT pseudonym FROM accounts"))}
    return found


def assert_counts_only(result: subprocess.CompletedProcess[str], keys: set[str]) -> None:
    output = result.stdout + result.stderr
    for marker in ("did:", "at://", "http", FAKE_PSEUDONYM_SECRET, MARKER_VALUE):
        assert marker not in output
    assert not any(key in output for key in keys)


@pytest.fixture
def prepared(clean_db: str, make_engine: Any, explicit_policy: Any, keyer: Any) -> Any:
    """The fixture replayed in process with the fixture selection policy (plan 03-05)."""
    engine = make_engine(clean_db, role="jobs")
    run_pipeline(engine, explicit_policy(), fixture_items(keyer))
    assert row_counts(engine)["cascades"] == fixture_manifest()["coverage"]["tracked_roots"]
    return engine


def give_roots_text(engine: Any) -> int:
    """The recording carries no post text (scrubbed at the cut), so constructed text is put on
    the live roots to give the text window something to purge."""
    with engine.begin() as connection:
        return connection.execute(
            text(
                "UPDATE events SET text = 'constructed root text'"
                " WHERE edge_kind = 'root' AND deleted_at IS NULL"
            )
        ).rowcount


def scalar(engine: Any, sql: str) -> Any:
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar_one()


@pytest.mark.requires_db
def test_run_then_purge_in_subprocesses_exit_zero_with_one_counts_line(
    prepared: Any, clean_db: str, subprocess_env: dict[str, str], tmp_path: Path
) -> None:
    keys = identifiers(prepared)
    env = {**subprocess_env, "DATABASE_URL": clean_db, **RETENTION_ENV}
    assert give_roots_text(prepared) > 0
    assert scalar(prepared, "SELECT count(*) FROM cascades WHERE enrich_dirty") > 0
    enriched = cli(["run"], env, tmp_path)
    assert enriched.returncode == 0, enriched.stderr[-2000:]
    lines = enriched.stdout.strip().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("enrich status=ok ")
    assert scalar(prepared, "SELECT count(*) FROM cascades WHERE enrich_dirty") == 0
    assert_counts_only(enriched, keys)
    purged = cli(["purge", "--as-of", PURGE_AS_OF], env, tmp_path)
    assert purged.returncode == 0, purged.stderr[-2000:]
    lines = purged.stdout.strip().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("purge status=ok ")
    assert " text=" in lines[0]
    assert scalar(prepared, "SELECT count(*) FROM events WHERE text IS NOT NULL") == 0
    assert scalar(prepared, "SELECT count(*) FROM events WHERE deleted_at IS NOT NULL") == 0
    tracked = fixture_manifest()["coverage"]["tracked_roots"]
    assert scalar(prepared, "SELECT count(*) FROM cascades") == tracked  # inside the window
    assert_counts_only(purged, keys)
    again = cli(["run"], env, tmp_path)  # the purge marked tombstoned cascades dirty
    assert again.returncode == 0, again.stderr[-2000:]
    assert scalar(prepared, "SELECT count(*) FROM cascades WHERE enrich_dirty") == 0


@pytest.mark.requires_db
def test_run_honours_as_of_and_purge_dry_run_deletes_nothing(
    prepared: Any, clean_db: str, subprocess_env: dict[str, str], tmp_path: Path
) -> None:
    env = {**subprocess_env, "DATABASE_URL": clean_db, **RETENTION_ENV}
    enriched = cli(["run", "--as-of", RUN_AS_OF, "--max-cascades", "1000"], env, tmp_path)
    assert enriched.returncode == 0, enriched.stderr[-2000:]
    stamps = scalar(prepared, "SELECT array_agg(DISTINCT rolled_up_at) FROM cascades")
    assert [s.isoformat() for s in stamps] == [RUN_AS_OF]
    texts = give_roots_text(prepared)
    before = row_counts(prepared)
    assert texts > 0
    preview = cli(["purge", "--as-of", PURGE_AS_OF, "--dry-run"], env, tmp_path)
    assert preview.returncode == 0, preview.stderr[-2000:]
    assert preview.stdout.startswith("purge status=dry_run ")
    assert f" text={texts} " in preview.stdout
    assert row_counts(prepared) == before
    assert scalar(prepared, "SELECT count(*) FROM events WHERE text IS NOT NULL") == texts


@pytest.mark.requires_db
def test_an_ingest_subprocess_and_the_in_process_pipeline_select_the_same_cascades(
    clean_db: str,
    make_engine: Any,
    subprocess_env: dict[str, str],
    fixture_policy_environment: dict[str, str],
    tmp_path: Path,
) -> None:
    ingest_env = {
        **subprocess_env,
        **fixture_policy_environment,
        "DATABASE_URL": clean_db,
        "PSEUDONYM_SECRET": FAKE_PSEUDONYM_SECRET,
        "PYTHONPATH": str(SRC),
    }
    ingested = subprocess.run(
        [sys.executable, "-m", "truthtrail.ingest", "run", "--replay", "packaged"],
        env=ingest_env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert ingested.returncode == 0, ingested.stderr[-2000:]
    engine = make_engine(clean_db)
    assert row_counts(engine)["cascades"] == fixture_manifest()["coverage"]["tracked_roots"]
    # enrich never needs the pseudonym key: it is left out of the environment on purpose
    enriched = cli(["run"], {**subprocess_env, "DATABASE_URL": clean_db}, tmp_path)
    assert enriched.returncode == 0, enriched.stderr[-2000:]
    assert scalar(engine, "SELECT count(*) FROM cascades WHERE enrich_dirty") == 0
    assert scalar(engine, "SELECT count(*) FROM cascades WHERE rolled_up_at IS NULL") == 0


@pytest.mark.requires_db
def test_a_concurrent_purge_or_run_exits_6(
    prepared: Any,
    clean_db: str,
    make_engine: Any,
    subprocess_env: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = {**subprocess_env, "DATABASE_URL": clean_db, **RETENTION_ENV}
    assert give_roots_text(prepared) > 0
    holder_engine = make_engine(clean_db, role="jobs")
    with holder_engine.connect() as holder:
        assert try_advisory_lock(holder, PURGE_LOCK_KEY)
        refused = cli(["purge", "--as-of", PURGE_AS_OF], env, tmp_path)
        assert refused.returncode == EXIT_LOCKED, refused.stderr[-2000:]
        assert refused.stdout.strip() == "purge status=locked"
        release_advisory_lock(holder, PURGE_LOCK_KEY)
        assert try_advisory_lock(holder, ENRICH_LOCK_KEY)
        monkeypatch.setenv("DATABASE_URL", clean_db)
        assert main(["run"]) == EXIT_LOCKED
        release_advisory_lock(holder, ENRICH_LOCK_KEY)
    assert scalar(prepared, "SELECT count(*) FROM events WHERE text IS NOT NULL") > 0


def test_a_missing_database_url_exits_3_naming_the_variable(
    subprocess_env: dict[str, str], tmp_path: Path
) -> None:
    result = cli(["run"], {**subprocess_env}, tmp_path, timeout=60)
    assert result.returncode == EXIT_CONFIG
    assert "DATABASE_URL" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DATABASE_URL", "mysql://user:" + MARKER_VALUE + "@localhost/db"),
        ("RETENTION_TEXT_DAYS", "-" + MARKER_VALUE),
    ],
)
def test_an_invalid_value_exits_3_without_echoing_it(
    name: str, value: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user@localhost/db")
    monkeypatch.setenv(name, value)
    assert main(["purge", "--dry-run"]) == EXIT_CONFIG
    captured = capsys.readouterr()
    assert MARKER_VALUE not in captured.out + captured.err
    assert "configuration error" in captured.err
    if name.startswith("RETENTION"):
        assert name in captured.err


@pytest.mark.requires_db
def test_a_database_failure_exits_5_with_the_class_name_only(
    clean_db: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = make_url(clean_db).set(database="truthtrail_no_such_database")
    monkeypatch.setenv("DATABASE_URL", missing.render_as_string(hide_password=False))
    assert main(["run"]) == EXIT_DATABASE
    captured = capsys.readouterr()
    assert captured.err.strip() == "database error: OperationalError"
    assert "truthtrail_no_such_database" not in captured.out + captured.err


@pytest.mark.parametrize(
    "argv",
    [
        ["run", "--as-of", "2026-10-19T12:00:00"],  # no UTC offset
        ["run", "--as-of", MARKER_VALUE],
        ["run", "--max-cascades", "0"],
        ["purge", "--max-seconds", "-1"],
        ["purge", MARKER_VALUE],
        [MARKER_VALUE],
    ],
)
def test_usage_errors_exit_2_without_echoing_the_argument(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stop:
        main(argv)
    assert stop.value.code == EXIT_USAGE
    captured = capsys.readouterr()
    assert MARKER_VALUE not in captured.out + captured.err
