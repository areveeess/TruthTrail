"""Idempotent collector writes (D-15, SC3): replaying the same input twice, a 30 s rewind, an
in-process stop and resume and a batch flushed twice all leave identical row counts per table and
an identical canonical projection by natural key, overflow_count and overflow_through_us of a
capped cascade included.
"""

import json
from copy import deepcopy
from typing import Any

import pytest
from conftest import (
    TEST_SMALL_CASCADE_CAP,
    canonical_projection,
    find_frame,
    fixture_items,
    row_counts,
    run_pipeline,
)
from sqlalchemy import text

from truthtrail.ingest import selection
from truthtrail.ingest.dialect import classify_frame
from truthtrail.ingest.normalise import UPDATE_IGNORED, Dropped, normalise
from truthtrail.ingest.source import DropCounter
from truthtrail.ingest.writer import DUPLICATE, Batch, Decider, TrackedIndex, flush

pytestmark = pytest.mark.requires_db

# Row counts per table after ONE replay of the packaged fixture under the explicit test policy
# (``make_test_policy``: the manifest's selection_policy block, caps above the fixture size)
# with TRACK_MAX_EVENTS_PER_CASCADE = TEST_SMALL_CASCADE_CAP (4), the same override the
# crash-resume test passes to its CLI subprocesses. Derived from the first verified run:
# 149 cascades = coverage.tracked_roots; 118 claims = the distinct canonical URLs of those roots;
# 426 events = 149 roots + the children that fit under the cap of 4 per cascade (the uncapped
# replay stores 805 = 149 + 245 replies + 29 quotes + 382 reposts, coverage.children_by_kind);
# 317 accounts = the distinct authors of those 426 events; one checkpoint row. It changes only
# when the fixture or the rules change.
GOLDEN_CAPPED_ROW_COUNTS = {
    "events": 426,
    "cascades": 149,
    "accounts": 317,
    "claims": 118,
    "ingest_checkpoints": 1,
}
GOLDEN_UNCAPPED_ROW_COUNTS = {
    "events": 805,
    "cascades": 149,
    "accounts": 562,
    "claims": 118,
    "ingest_checkpoints": 1,
}


@pytest.fixture
def engine(clean_db: str, make_engine: Any) -> Any:
    return make_engine(clean_db, role="collector")


@pytest.fixture
def items(keyer: Any) -> list[Any]:
    return fixture_items(keyer)


def _truncate(engine: Any) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("TRUNCATE accounts, claims, cascades, events, ingest_checkpoints CASCADE")
        )


def _checkpoint(engine: Any) -> int:
    with engine.connect() as connection:
        value: int = connection.execute(
            text("SELECT cursor_time_us FROM ingest_checkpoints")
        ).scalar_one()
    return value


def _resume(engine: Any, policy: Any, keyer: Any) -> Any:
    """Resume the way the run loop does: checkpoint minus the rewind, index loaded from there."""
    since = _checkpoint(engine) - policy.ingest_rewind_seconds * 1_000_000
    return run_pipeline(engine, policy, fixture_items(keyer, since), since_us=since)


def test_replaying_twice_leaves_identical_counts_and_projection(
    engine: Any, explicit_policy: Any, items: list[Any]
) -> None:
    first = run_pipeline(engine, explicit_policy(), items)
    counts, projection = row_counts(engine), canonical_projection(engine)
    second = run_pipeline(engine, explicit_policy(), items)
    assert row_counts(engine) == counts
    assert canonical_projection(engine) == projection
    assert first.inserted == counts["events"]
    assert second.inserted == 0
    assert second.outcomes[DUPLICATE] == first.inserted


def test_a_rewound_replay_changes_nothing(
    engine: Any, explicit_policy: Any, items: list[Any], keyer: Any
) -> None:
    policy = explicit_policy()
    run_pipeline(engine, policy, items)
    counts, projection = row_counts(engine), canonical_projection(engine)
    again = _resume(engine, policy, keyer)
    assert again.inserted == 0
    assert again.outcomes[DUPLICATE] > 0
    assert row_counts(engine) == counts
    assert canonical_projection(engine) == projection


def test_stop_and_resume_equals_one_uninterrupted_run(
    engine: Any, explicit_policy: Any, items: list[Any], keyer: Any
) -> None:
    policy = explicit_policy()
    run_pipeline(engine, policy, items)
    expected = canonical_projection(engine)
    _truncate(engine)
    run_pipeline(engine, policy, items, stop_after=len(items) // 3)
    assert row_counts(engine)["events"] < GOLDEN_UNCAPPED_ROW_COUNTS["events"]
    _resume(engine, policy, keyer)
    assert canonical_projection(engine) == expected


def _capped(explicit_policy: Any) -> Any:
    return explicit_policy(track_max_events_per_cascade=TEST_SMALL_CASCADE_CAP)


def _overflowing(engine: Any) -> int:
    with engine.connect() as connection:
        total: int = connection.execute(
            text("SELECT coalesce(sum(overflow_count), 0) FROM cascades")
        ).scalar_one()
    return total


def test_capped_replay_twice_keeps_the_overflow_columns(
    engine: Any, explicit_policy: Any, items: list[Any]
) -> None:
    run_pipeline(engine, _capped(explicit_policy), items)
    assert _overflowing(engine) > 0
    projection = canonical_projection(engine)
    run_pipeline(engine, _capped(explicit_policy), items)
    assert canonical_projection(engine) == projection


def test_capped_rewound_replay_keeps_the_overflow_columns(
    engine: Any, explicit_policy: Any, items: list[Any], keyer: Any
) -> None:
    policy = _capped(explicit_policy)
    run_pipeline(engine, policy, items)
    projection = canonical_projection(engine)
    _resume(engine, policy, keyer)
    assert canonical_projection(engine) == projection


@pytest.mark.parametrize("fraction", [4, 2])
def test_capped_stop_and_resume_equals_one_uninterrupted_run(
    engine: Any, explicit_policy: Any, items: list[Any], keyer: Any, fraction: int
) -> None:
    policy = _capped(explicit_policy)
    run_pipeline(engine, policy, items)
    assert _overflowing(engine) > 0
    expected = canonical_projection(engine)
    _truncate(engine)
    run_pipeline(engine, policy, items, stop_after=len(items) // fraction)
    _resume(engine, policy, keyer)
    assert canonical_projection(engine) == expected


def test_an_update_frame_is_ignored_and_counted(
    engine: Any, explicit_policy: Any, items: list[Any], keyer: Any
) -> None:
    run_pipeline(engine, explicit_policy(), items)
    projection = canonical_projection(engine)
    create = find_frame(
        lambda f: (
            f["payload"].get("operation") == "create"
            and f["payload"].get("collection") == selection.POST_COLLECTION
        )
    )
    constructed_update = deepcopy(create)
    constructed_update["payload"]["operation"] = "update"
    constructed_update["payload"]["record"]["text"] = "constructed update text"
    result = normalise(classify_frame(json.dumps(constructed_update), "v2"), keyer)
    assert result == Dropped(UPDATE_IGNORED)
    drops = DropCounter()
    drops.add(result.reason)
    assert drops.as_dict() == {UPDATE_IGNORED: 1}
    run_pipeline(engine, explicit_policy(), [])
    assert canonical_projection(engine) == projection


def test_the_same_batch_flushed_twice_is_a_no_op(
    engine: Any, explicit_policy: Any, items: list[Any]
) -> None:
    policy = explicit_policy()
    index = TrackedIndex()
    with engine.connect() as connection:
        index.load(connection, None)
    decider = Decider(policy, index, selection.load_allowlist(policy.track_allowlist_file))
    batch = Batch()
    for item in items:
        batch.note_cursor(item.cursor_us)
        decider.process(item.result, batch)
    first = flush(engine, batch, source="test-replay", dialect="v2", host="recorded")
    projection = canonical_projection(engine)
    second = flush(engine, batch, source="test-replay", dialect="v2", host="recorded")
    assert first.inserted == GOLDEN_UNCAPPED_ROW_COUNTS["events"]
    assert second.inserted == 0
    assert second.duplicates == len(batch.events)
    assert second.tombstoned == 0
    assert canonical_projection(engine) == projection


def test_golden_row_counts_of_one_capped_replay(
    engine: Any, explicit_policy: Any, items: list[Any]
) -> None:
    run_pipeline(engine, _capped(explicit_policy), items)
    assert row_counts(engine) == GOLDEN_CAPPED_ROW_COUNTS


def test_golden_row_counts_of_one_uncapped_replay(
    engine: Any, explicit_policy: Any, items: list[Any]
) -> None:
    run_pipeline(engine, explicit_policy(), items)
    assert row_counts(engine) == GOLDEN_UNCAPPED_ROW_COUNTS
