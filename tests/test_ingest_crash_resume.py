"""Kill-and-resume proof of the collector (SC3, D-09, D-28, D-30).

The CLI replays the packaged real recording in a subprocess against database A, throttled with
``--batch-rows 20 --batch-delay-seconds 0.05`` so it is mid-stream for a while. The test polls
A until a checkpoint row and at least one event exist, kills the process with ``Popen.kill()``
(never a POSIX signal; it works on Windows) and reruns the same command to completion. The same
command runs uninterrupted against database B. Both must end with identical row counts per table
and an identical canonical projection by natural key (overflow_count and overflow_through_us of
the capped cascades included), the checkpoint at the recording's last stream time and no event
missing or duplicated. The kill is repeated at a second, later point so a lucky moment cannot
pass. The per-cascade cap override makes at least one fixture cascade overflow (asserted on B),
so the capped path is really exercised; the uninterrupted counts equal the idempotency test's
golden dict, which is built from the same explicit policy.
"""

import subprocess
import sys
import time
from typing import Any

import pytest
from conftest import (
    FAKE_PSEUDONYM_SECRET,
    TEST_SMALL_CASCADE_CAP,
    canonical_projection,
    fixture_items,
    fixture_manifest,
    row_counts,
    upgrade_to_head,
)
from sqlalchemy import text
from test_ingest_idempotency import GOLDEN_CAPPED_ROW_COUNTS

pytestmark = pytest.mark.requires_db

COMMAND = [
    sys.executable,
    "-m",
    "truthtrail.ingest",
    "run",
    "--replay",
    "packaged",
    "--batch-rows",
    "20",
    "--batch-delay-seconds",
    "0.05",
]
POLL_SECONDS = 0.01
DEADLINE_SECONDS = 120


@pytest.fixture
def environment(subprocess_env: dict[str, str], fixture_policy_environment: dict[str, str]) -> Any:
    def build(url: str) -> dict[str, str]:
        return {
            **subprocess_env,
            **fixture_policy_environment,
            "TRACK_MAX_EVENTS_PER_CASCADE": str(TEST_SMALL_CASCADE_CAP),
            "DATABASE_URL": url,
            "PSEUDONYM_SECRET": FAKE_PSEUDONYM_SECRET,
        }

    return build


def _fresh(empty_database: Any, make_engine: Any) -> tuple[str, Any]:
    url = empty_database()
    upgrade_to_head(url)
    return url, make_engine(url)


def _run_to_completion(env: dict[str, str]) -> None:
    result = subprocess.run(
        COMMAND, env=env, capture_output=True, text=True, timeout=DEADLINE_SECONDS
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert "status=ok" in result.stdout


def _kill_when(env: dict[str, str], engine: Any, min_events: int) -> int:
    """Start the CLI, kill it once a checkpoint and ``min_events`` events exist; return the
    event count seen at the kill."""
    process = subprocess.Popen(
        COMMAND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    seen = 0
    try:
        deadline = time.monotonic() + DEADLINE_SECONDS
        while time.monotonic() < deadline and process.poll() is None:
            with engine.connect() as connection:
                checkpoints = connection.execute(
                    text("SELECT count(*) FROM ingest_checkpoints")
                ).scalar_one()
                seen = connection.execute(text("SELECT count(*) FROM events")).scalar_one()
            if checkpoints and seen >= min_events:
                break
            time.sleep(POLL_SECONDS)
        assert process.poll() is None, "the run finished before the kill point"
        process.kill()
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=30)
    return seen


def _last_stream_time(keyer: Any) -> int:
    return max(i.cursor_us for i in fixture_items(keyer) if i.cursor_us is not None)


def _assert_complete(engine: Any, keyer: Any) -> None:
    with engine.connect() as connection:
        cursor = connection.execute(
            text("SELECT cursor_time_us FROM ingest_checkpoints WHERE source = 'bluesky-replay'")
        ).scalar_one()
        dupes = connection.execute(
            text("SELECT count(*) - count(DISTINCT uri) FROM events")
        ).scalar_one()
    assert cursor == _last_stream_time(keyer)
    assert dupes == 0


@pytest.mark.parametrize("min_events", [1, 200], ids=["early-kill", "later-kill"])
def test_a_killed_run_resumes_to_the_same_result_as_an_uninterrupted_one(
    empty_database: Any, make_engine: Any, environment: Any, keyer: Any, min_events: int
) -> None:
    url_b, engine_b = _fresh(empty_database, make_engine)
    _run_to_completion(environment(url_b))
    expected_counts = row_counts(engine_b)
    expected = canonical_projection(engine_b)
    with engine_b.connect() as connection:
        overflow = connection.execute(text("SELECT sum(overflow_count) FROM cascades")).scalar_one()
    assert overflow > 0, "the cap override must make a fixture cascade overflow"
    assert expected_counts["cascades"] == fixture_manifest()["coverage"]["tracked_roots"]
    assert expected_counts == GOLDEN_CAPPED_ROW_COUNTS

    url_a, engine_a = _fresh(empty_database, make_engine)
    seen = _kill_when(environment(url_a), engine_a, min_events)
    assert seen >= min_events
    assert row_counts(engine_a)["events"] < expected_counts["events"], "killed mid-stream"
    with engine_a.connect() as connection:
        interrupted = connection.execute(
            text("SELECT count(*) FROM ingest_runs WHERE status = 'running'")
        ).scalar_one()
    assert interrupted == 1  # the killed process could not finalise its run row
    _run_to_completion(environment(url_a))

    assert row_counts(engine_a) == expected_counts
    assert canonical_projection(engine_a) == expected
    _assert_complete(engine_a, keyer)
    _assert_complete(engine_b, keyer)
