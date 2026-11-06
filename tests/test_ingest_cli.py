"""The collector CLI (D-10, D-11, D-16, D-17, D-30): arguments and Policy defaults, configuration
errors that name the variable and never the value, a packaged replay in a subprocess, the bounds,
and the stdin-only erase command that prints counts only (T-03-38).
"""

import io
import subprocess
import sys
from typing import Any

import pytest
from conftest import FAKE_PSEUDONYM_SECRET, fixture_manifest, recorded_frames, row_counts
from sqlalchemy import text

from truthtrail.ingest.__main__ import bounds_from_args, build_parser, main
from truthtrail.ingest.erase import is_did

MARKER_VALUE = "constructed-marker-value-9f2c"


@pytest.fixture
def cli_env(monkeypatch: pytest.MonkeyPatch, fixture_policy_environment: dict[str, str]) -> Any:
    """Set the policy environment of the fixture; returns a setter for the two secrets."""
    for name, value in fixture_policy_environment.items():
        monkeypatch.setenv(name, value)

    def configure(database_url: str | None, secret: str | None = FAKE_PSEUDONYM_SECRET) -> None:
        if database_url is not None:
            monkeypatch.setenv("DATABASE_URL", database_url)
        if secret is not None:
            monkeypatch.setenv("PSEUDONYM_SECRET", secret)

    return configure


def _scalar(url: str, make_engine: Any, sql: str, **params: Any) -> Any:
    engine = make_engine(url)
    with engine.connect() as connection:
        return connection.execute(text(sql), params).scalar_one()


# --- arguments ------------------------------------------------------------------------------------
def test_run_bounds_default_to_the_policy(explicit_policy: Any) -> None:
    policy = explicit_policy(ingest_max_seconds=21, ingest_max_events=22, ingest_max_stored=23)
    args = build_parser().parse_args(["run"])
    made = bounds_from_args(args, policy)
    assert (made.max_seconds, made.max_events, made.max_stored) == (21, 22, 23)
    assert made.batch_rows == policy.ingest_batch_rows
    assert made.batch_delay_seconds == 0
    args = build_parser().parse_args(["run", "--max-events", "5", "--batch-rows", "7"])
    made = bounds_from_args(args, policy)
    assert (made.max_events, made.batch_rows, made.max_seconds) == (5, 7, 21)


def test_a_did_passed_as_an_argument_is_refused_and_never_echoed(capsys: Any) -> None:
    did = "did:plc:" + "a" * 24
    with pytest.raises(SystemExit) as stop:
        main(["erase", did])
    assert stop.value.code == 2
    captured = capsys.readouterr()
    assert did not in captured.out + captured.err


def test_an_unknown_subcommand_is_a_usage_error(capsys: Any) -> None:
    with pytest.raises(SystemExit) as stop:
        main(["collect-everything"])
    assert stop.value.code == 2
    assert "collect-everything" not in capsys.readouterr().err


# --- configuration errors ------------------------------------------------------------------------
@pytest.mark.parametrize("missing", ["DATABASE_URL", "PSEUDONYM_SECRET"])
def test_a_missing_variable_exits_3_and_names_it(
    cli_env: Any, capsys: Any, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    cli_env("postgresql+psycopg://user:" + MARKER_VALUE + "@127.0.0.1:1/db")
    monkeypatch.delenv(missing)
    assert main(["run", "--replay", "packaged"]) == 3
    captured = capsys.readouterr()
    assert missing in captured.err
    assert MARKER_VALUE not in captured.out + captured.err
    assert FAKE_PSEUDONYM_SECRET not in captured.out + captured.err


@pytest.mark.parametrize(
    "secret",
    ["c2hvcnQ", "not base64 !!" + MARKER_VALUE, "ab" * 8],
    ids=["too-short", "wrong-encoding", "short-hex"],
)
def test_an_invalid_secret_exits_3_without_its_value(
    cli_env: Any, capsys: Any, secret: str
) -> None:
    cli_env("postgresql+psycopg://127.0.0.1:1/db", secret=secret)
    assert main(["run", "--replay", "packaged"]) == 3
    captured = capsys.readouterr()
    assert "PSEUDONYM_SECRET" in captured.err
    assert secret not in captured.out + captured.err


def test_a_non_positive_bound_is_a_configuration_error(cli_env: Any, capsys: Any) -> None:
    cli_env("postgresql+psycopg://127.0.0.1:1/db")
    assert main(["run", "--replay", "packaged", "--max-events", "0"]) == 3


def test_a_refused_replay_file_is_a_configuration_error(
    cli_env: Any, capsys: Any, tmp_path: Any
) -> None:
    cli_env("postgresql+psycopg://127.0.0.1:1/db")
    fake = tmp_path / "x.manifest.json"
    fake.write_text('{"source_mode": "synthetic"}', "utf-8")
    assert main(["run", "--replay", str(fake)]) == 3
    assert "replay refused" in capsys.readouterr().err


# --- runs -----------------------------------------------------------------------------------------
@pytest.mark.requires_db
def test_a_packaged_replay_in_a_subprocess_stores_the_tracked_roots(
    clean_db: str,
    make_engine: Any,
    subprocess_env: dict[str, str],
    fixture_policy_environment: dict[str, str],
) -> None:
    env = {
        **subprocess_env,
        **fixture_policy_environment,
        "DATABASE_URL": clean_db,
        "PSEUDONYM_SECRET": FAKE_PSEUDONYM_SECRET,
    }
    result = subprocess.run(
        [sys.executable, "-m", "truthtrail.ingest", "run", "--replay", "packaged"],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("ingest status=ok stop=source_end ")
    for marker in ("did:", "at://", "http", FAKE_PSEUDONYM_SECRET):
        assert marker not in result.stdout + result.stderr
    engine = make_engine(clean_db)
    counts = row_counts(engine)
    assert counts["cascades"] == fixture_manifest()["coverage"]["tracked_roots"]
    assert counts["events"] > counts["cascades"]
    with engine.connect() as connection:
        sources = connection.execute(text("SELECT source FROM ingest_checkpoints")).scalars().all()
    assert sources == ["bluesky-replay"]


@pytest.mark.requires_db
@pytest.mark.parametrize(
    ("flag", "stop"), [("--max-stored", "max_stored"), ("--max-events", "max_events")]
)
def test_the_bounds_stop_the_run_with_exit_0(
    clean_db: str, make_engine: Any, cli_env: Any, capsys: Any, flag: str, stop: str
) -> None:
    cli_env(clean_db)
    assert main(["run", "--replay", "packaged", flag, "40", "--batch-rows", "10"]) == 0
    out = capsys.readouterr().out
    assert f"stop={stop}" in out
    events = row_counts(make_engine(clean_db))["events"]
    assert 0 < events <= 40


@pytest.mark.requires_db
def test_a_held_lock_exits_6(clean_db: str, make_engine: Any, cli_env: Any) -> None:
    from truthtrail.db.locks import INGEST_LOCK_KEY, release_advisory_lock, try_advisory_lock

    cli_env(clean_db)
    with make_engine(clean_db).connect() as holder:
        assert try_advisory_lock(holder, INGEST_LOCK_KEY)
        assert main(["run", "--replay", "packaged"]) == 6
        assert release_advisory_lock(holder, INGEST_LOCK_KEY)


# --- erase ----------------------------------------------------------------------------------------
def _replayed(clean_db: str, cli_env: Any, capsys: Any) -> None:
    cli_env(clean_db)
    assert main(["run", "--replay", "packaged"]) == 0
    capsys.readouterr()


def _did_with_rows(clean_db: str, make_engine: Any, keyer: Any) -> tuple[str, int]:
    with make_engine(clean_db).connect() as connection:
        live = dict(
            connection.execute(
                text(
                    "SELECT a.pseudonym, count(*) FROM events e JOIN accounts a ON a.id ="
                    " e.account_id GROUP BY a.pseudonym"
                )
            ).all()
        )
    for frame in recorded_frames():
        did = frame["payload"]["did"]
        if keyer.account_key(did) in live:
            return did, live[keyer.account_key(did)]
    raise LookupError("no stored account")


@pytest.mark.requires_db
def test_erase_tombstones_a_known_account_and_nothing_else(
    clean_db: str, make_engine: Any, cli_env: Any, capsys: Any, keyer: Any, monkeypatch: Any
) -> None:
    _replayed(clean_db, cli_env, capsys)
    did, rows = _did_with_rows(clean_db, make_engine, keyer)
    before = _scalar(
        clean_db, make_engine, "SELECT count(*) FROM events WHERE deleted_at IS NOT NULL"
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(did + "\n"))
    assert main(["erase"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip().startswith(
        f"erase lines=1 invalid=0 matched=1 unknown=0 tombstoned={rows}"
    )
    assert did not in captured.out + captured.err
    after = _scalar(
        clean_db, make_engine, "SELECT count(*) FROM events WHERE deleted_at IS NOT NULL"
    )
    assert after == before + rows
    pseudonym = keyer.account_key(did)
    left = _scalar(
        clean_db,
        make_engine,
        "SELECT count(*) FROM events e JOIN accounts a ON a.id = e.account_id"
        " WHERE a.pseudonym = :p",
        p=pseudonym,
    )
    assert left == 0


@pytest.mark.requires_db
def test_erase_of_an_unknown_did_tombstones_nothing(
    clean_db: str, make_engine: Any, cli_env: Any, capsys: Any, monkeypatch: Any
) -> None:
    _replayed(clean_db, cli_env, capsys)
    counts = row_counts(make_engine(clean_db))
    monkeypatch.setattr(sys, "stdin", io.StringIO("did:plc:" + "z" * 24 + "\n"))
    assert main(["erase"]) == 0
    assert "matched=0 unknown=1 tombstoned=0" in capsys.readouterr().out
    assert row_counts(make_engine(clean_db)) == counts


@pytest.mark.requires_db
def test_erase_rejects_an_invalid_line_without_echoing_it(
    clean_db: str, cli_env: Any, capsys: Any, monkeypatch: Any
) -> None:
    cli_env(clean_db)
    bad = "handle." + MARKER_VALUE + ".example"
    monkeypatch.setattr(sys, "stdin", io.StringIO(bad + "\n\n"))
    assert main(["erase"]) == 0
    captured = capsys.readouterr()
    assert "lines=1 invalid=1 matched=0" in captured.out
    assert MARKER_VALUE not in captured.out + captured.err


@pytest.mark.requires_db
def test_erase_under_a_held_lock_exits_6(
    clean_db: str, make_engine: Any, cli_env: Any, monkeypatch: Any
) -> None:
    from truthtrail.db.locks import INGEST_LOCK_KEY, release_advisory_lock, try_advisory_lock

    cli_env(clean_db)
    monkeypatch.setattr(sys, "stdin", io.StringIO("did:plc:" + "a" * 24 + "\n"))
    with make_engine(clean_db).connect() as holder:
        assert try_advisory_lock(holder, INGEST_LOCK_KEY)
        assert main(["erase"]) == 6
        assert release_advisory_lock(holder, INGEST_LOCK_KEY)


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ("did:plc:" + "a" * 24, True),
        ("did:plc:" + "a" * 23, False),
        ("did:plc:" + "A" * 24, False),
        ("did:web:example.org", True),
        ("did:web:example.org%3A8443:user:alice", True),
        ("did:key:z6Mk", False),
        ("alice.bsky.social", False),
        ("did:plc:" + "a" * 24 + "\nx", False),
    ],
)
def test_the_did_pattern(value: str, valid: bool) -> None:
    assert is_did(value) is valid
