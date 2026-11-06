"""The enrich write-back on a real PostgreSQL (D-14, D-22, SC4; RESEARCH Pattern 7, threat T-03-43).

Proves at the database layer what ``test_enrich_properties.py`` proves for the pure resolver:
two permutations of the same rows, inserted with different surrogate ids, end in the same
projection keyed by uri, and a second enrich changes nothing. Also: the recorded fixture is
enriched to counters that match an independent recount from the raw rows; an orphan flips to
resolved when its parent is stored later and no parent is ever invented; order violations are
counted and left as stored; a stored cycle is quarantined without stopping the run; tombstones
keep the skeleton but leave the counters; a cascade locked by another transaction is skipped and
stays dirty; a dirty mark issued by the collector during an enrich transaction is never lost
(with a negative control showing the filtered UPDATE that would lose it); the advisory lock
refuses a concurrent run; with no checkpoint nothing is enriched; and the collector-owned
overflow columns are never written.
"""

import logging
import threading
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from conftest import (
    ENRICH_COUNTERS,
    TEST_SMALL_CASCADE_CAP,
    enrich_projection,
    fixture_items,
    insert_forest,
    run_pipeline,
    set_checkpoint,
    truncate_application_tables,
)
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text, update
from sqlalchemy.exc import OperationalError

from truthtrail.db.locks import ENRICH_LOCK_KEY, release_advisory_lock, try_advisory_lock
from truthtrail.db.models import PARENT_STATES, Cascade
from truthtrail.enrich import apply
from truthtrail.enrich.apply import EnrichResult, datetime_from_us, enrich_dirty
from truthtrail.enrich.rollup import ROLLUP_VERSION
from truthtrail.ingest.writer import mark_cascades_dirty, us_of

pytestmark = pytest.mark.requires_db

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
AS_OF = T0 + timedelta(minutes=30)
ROOT = "root-uri-000"


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def scalar(engine: Any, sql: str, **params: Any) -> Any:
    with engine.connect() as connection:
        return connection.execute(text(sql), params).scalar_one()


def cascade_row(engine: Any, root: str = ROOT) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT * FROM cascades WHERE root_uri = :r"), {"r": root}
        ).mappings()
        return dict(row.one())


def event_states(engine: Any) -> dict[str, tuple[str, str | None, int | None]]:
    return {u: (s, p, d) for u, (s, p, d, _r) in enrich_projection(engine)["events"].items()}


@pytest.fixture
def engine(clean_db: str, make_engine: Any) -> Any:
    return make_engine(clean_db, role="jobs")


# --- The recorded fixture: clean, consistent, and equal to an independent recount -----------
def _recount(engine: Any, as_of: datetime) -> dict[int, dict[str, Any]]:
    """Counters per cascade recomputed in the test from raw rows, without the resolver."""
    with engine.connect() as connection:
        raw = connection.execute(
            text(
                "SELECT cascade_id, uri, edge_kind, parent_uri, account_id, deleted_at,"
                " observed_at FROM events"
            )
        ).all()
    by_cascade: dict[int, dict[str, Any]] = defaultdict(dict)
    for cascade_id, uri, kind, parent, account, deleted_at, observed in raw:
        by_cascade[cascade_id][uri] = (kind, parent, account, deleted_at is not None, observed)
    expected: dict[int, dict[str, Any]] = {}
    for cascade_id, rows in by_cascade.items():

        def depth(uri: str, rows: dict[str, Any] = rows) -> int | None:
            hops = 0
            while True:
                kind, parent, *_ = rows[uri]
                if kind == "root":
                    return hops
                if parent not in rows or rows[parent][0] == "repost" or hops > len(rows):
                    return None
                uri, hops = parent, hops + 1

        live = {u: r for u, r in rows.items() if not r[3]}
        states = {}
        for uri, (kind, parent, *_rest) in rows.items():
            if kind == "root":
                states[uri] = "none"
            elif parent not in rows:
                states[uri] = "orphan"
            elif rows[parent][0] == "repost":
                states[uri] = "invalid"
            else:
                states[uri] = "resolved"
        depths = {u: depth(u) for u, r in rows.items() if r[0] != "repost"}
        connected = {u for u, d in depths.items() if d is not None}
        for uri, (kind, parent, *_rest) in rows.items():
            if kind == "repost" and states[uri] == "resolved" and parent in connected:
                connected.add(uri)
        times = [r[4] for r in (live or rows).values()]
        expected[cascade_id] = {
            "event_count": len(live),
            "reply_count": sum(1 for r in live.values() if r[0] == "reply"),
            "quote_count": sum(1 for r in live.values() if r[0] == "quote"),
            "repost_count": sum(1 for r in live.values() if r[0] == "repost"),
            "unique_accounts": len({r[2] for r in live.values() if r[2] is not None}),
            "max_depth": max((d for d in depths.values() if d is not None), default=0),
            "orphan_count": sum(1 for u in live if states[u] == "orphan"),
            "disconnected_count": sum(
                1 for u in live if states[u] != "none" and u not in connected
            ),
            "deleted_count": len(rows) - len(live),
            "order_violation_count": sum(
                1
                for u, r in rows.items()
                if r[0] != "root" and r[1] in rows and rows[r[1]][4] > r[4]
            ),
            "events_1h": sum(
                1 for r in live.values() if as_of - timedelta(hours=1) < r[4] <= as_of
            ),
            "first_event_at": min(times),
            "last_event_at": max(times),
            "states": states,
        }
    return expected


def test_the_fixture_enriches_clean_and_matches_an_independent_recount(
    engine: Any, explicit_policy: Any, keyer: Any
) -> None:
    run_pipeline(engine, explicit_policy(), fixture_items(keyer))
    data_as_of = datetime_from_us(
        scalar(engine, "SELECT max(cursor_time_us) FROM ingest_checkpoints")
    )
    assert scalar(engine, "SELECT count(*) FROM cascades WHERE enrich_dirty") > 0
    result = enrich_dirty(engine)
    assert result.as_of == data_as_of  # the default is the checkpoint's stream time
    assert result.errors == {}
    assert result.enriched == result.selected == scalar(engine, "SELECT count(*) FROM cascades")
    expected = _recount(engine, data_as_of)
    with engine.connect() as connection:
        cascades = connection.execute(text("SELECT * FROM cascades")).mappings().all()
        events = (
            connection.execute(
                text(
                    "SELECT e.uri, e.cascade_id, e.edge_kind, e.parent_state, e.depth,"
                    " p.cascade_id AS parent_cascade, p.depth AS parent_depth, p.uri AS parent_uri"
                    " FROM events e LEFT JOIN events p ON p.id = e.parent_event_id"
                )
            )
            .mappings()
            .all()
        )
    for cascade in cascades:
        assert cascade["enrich_dirty"] is False
        assert cascade["rolled_up_at"] == data_as_of
        assert cascade["rollup_version"] == ROLLUP_VERSION
        recount = expected[cascade["id"]]
        for name in (*ENRICH_COUNTERS, "first_event_at", "last_event_at"):
            assert cascade[name] == recount[name], name
    for event in events:
        assert event["parent_state"] in PARENT_STATES
        assert event["parent_state"] == expected[event["cascade_id"]]["states"][event["uri"]]
        if event["parent_state"] == "resolved":
            assert event["parent_cascade"] == event["cascade_id"]  # never across cascades
            if event["edge_kind"] != "repost" and event["depth"] is not None:
                assert event["depth"] == event["parent_depth"] + 1
        else:
            assert event["parent_uri"] is None  # no parent invented for orphans and roots
    # The recording holds real orphans (a reply whose parent was never stored): each is an
    # explicit orphan, counted, and kept in its cascade.
    real_orphans = sum(rec["orphan_count"] for rec in expected.values())
    assert real_orphans >= 1
    assert sum(c["orphan_count"] for c in cascades) == result.orphans == real_orphans


def test_a_second_enrich_selects_nothing_and_a_forced_pass_writes_nothing(
    engine: Any, explicit_policy: Any, keyer: Any
) -> None:
    run_pipeline(engine, explicit_policy(), fixture_items(keyer))
    enrich_dirty(engine)
    before = enrich_projection(engine)
    again = enrich_dirty(engine)
    assert again.selected == 0
    forced = enrich_dirty(engine, force=True)
    assert forced.selected == forced.enriched > 0
    assert forced.rows_updated == 0
    assert forced.cascades_updated == 0
    assert enrich_projection(engine) == before


# --- Permutations with different surrogate ids (the database layer of SC4) ------------------
CHILD_IDS = tuple(f"u{i:02d}" for i in range(9))
OUTSIDE = ("gone-1", "gone-2")
PSEUDONYMS = (None, "acct-a", "acct-b", "acct-c")


@st.composite
def stored_forests(draw: st.DrawFn) -> list[tuple[Any, ...]]:
    size = draw(st.integers(min_value=0, max_value=len(CHILD_IDS)))
    ids = list(draw(st.permutations(CHILD_IDS)))[:size]
    pool = [ROOT, ROOT, *ids * 3, *OUTSIDE]
    rows: list[tuple[Any, ...]] = [(ROOT, "root", None, T0, "acct-a", draw(st.booleans()))]
    for uri in ids:
        kind = draw(st.sampled_from(("reply", "reply", "quote", "repost")))
        observed = T0 + timedelta(
            seconds=draw(st.integers(min_value=-2, max_value=4)),
            microseconds=draw(st.sampled_from([0, 1])),
        )
        deleted = draw(st.sampled_from([False, False, True]))
        rows.append(
            (
                uri,
                kind,
                draw(st.sampled_from(pool)),
                observed,
                draw(st.sampled_from(PSEUDONYMS)),
                deleted,
            )
        )
    return rows


@settings(
    max_examples=25,
    deadline=None,
    derandomize=True,
    database=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(rows=stored_forests(), data=st.data())
def test_permutations_with_different_ids_yield_an_identical_projection(
    engine: Any, rows: list[tuple[Any, ...]], data: st.DataObject
) -> None:
    order_a = data.draw(st.permutations(range(len(rows))))
    order_b = data.draw(st.permutations(range(len(rows))))
    projections = []
    for order, base in ((order_a, 1000), (order_b, 7000)):
        truncate_application_tables(engine)
        insert_forest(engine, rows, root_uri=ROOT, order=list(order), id_base=base)
        first = enrich_dirty(engine, as_of=AS_OF)
        assert first.enriched == 1
        projections.append(enrich_projection(engine))
        assert enrich_dirty(engine, as_of=AS_OF).selected == 0
        forced = enrich_dirty(engine, as_of=AS_OF, force=True)
        assert (forced.rows_updated, forced.cascades_updated) == (0, 0)
        assert enrich_projection(engine) == projections[-1]
    assert projections[0] == projections[1]


# --- Orphans, violations, cycles and tombstones ---------------------------------------------
def test_an_orphan_flips_to_resolved_when_its_parent_is_stored_later(engine: Any) -> None:
    insert_forest(
        engine,
        [
            (ROOT, "root", None, at(0), "acct-a", False),
            ("child", "reply", "middle", at(20), "acct-b", False),
        ],
        root_uri=ROOT,
    )
    enrich_dirty(engine, as_of=AS_OF)
    assert event_states(engine)["child"] == ("orphan", None, None)
    before = cascade_row(engine)
    assert (before["orphan_count"], before["max_depth"], before["event_count"]) == (1, 0, 2)
    cascade_id = insert_forest(
        engine, [("middle", "reply", ROOT, at(10), "acct-c", False)], root_uri=ROOT, id_base=5000
    )
    with engine.begin() as connection:  # the way the writer marks a touched cascade
        mark_cascades_dirty(connection, {cascade_id})
    enrich_dirty(engine, as_of=AS_OF)
    assert event_states(engine)["child"] == ("resolved", "middle", 2)
    assert event_states(engine)["middle"] == ("resolved", ROOT, 1)
    after = cascade_row(engine)
    assert (after["orphan_count"], after["disconnected_count"]) == (0, 0)
    assert (after["max_depth"], after["event_count"], after["unique_accounts"]) == (2, 3, 3)


def test_a_child_before_its_parent_is_counted_and_left_as_stored(engine: Any) -> None:
    insert_forest(
        engine,
        [
            (ROOT, "root", None, at(10), "acct-a", False),
            ("early", "reply", ROOT, at(5), "acct-b", False),
        ],
        root_uri=ROOT,
    )
    enrich_dirty(engine, as_of=AS_OF)
    assert cascade_row(engine)["order_violation_count"] == 1
    assert event_states(engine)["early"] == ("resolved", ROOT, 1)
    assert scalar(engine, "SELECT observed_at FROM events WHERE uri = 'early'") == at(5)
    assert cascade_row(engine)["first_event_at"] == at(5)


def test_a_stored_cycle_is_quarantined_and_does_not_stop_the_run(engine: Any) -> None:
    insert_forest(
        engine,
        [
            (ROOT, "root", None, at(0), "acct-a", False),
            ("x", "reply", "y", at(1), "acct-b", False),
            ("y", "reply", "x", at(2), "acct-b", False),
            ("tail", "reply", "x", at(3), "acct-c", False),
            ("self", "quote", "self", at(4), "acct-c", False),
        ],
        root_uri=ROOT,
    )
    insert_forest(
        engine,
        [
            ("other", "root", None, at(0), "acct-a", False),
            ("ok", "reply", "other", at(1), None, False),
        ],
        root_uri="other",
        id_base=3000,
    )
    result = enrich_dirty(engine, as_of=AS_OF)
    assert (result.enriched, result.invalid, result.errors) == (2, 3, {})
    states = event_states(engine)
    assert {u for u, s in states.items() if s[0] == "invalid"} == {"x", "y", "self"}
    assert states["tail"] == ("resolved", "x", None)
    assert states["ok"] == ("resolved", "other", 1)
    assert cascade_row(engine)["disconnected_count"] == 4
    assert scalar(engine, "SELECT count(*) FROM events WHERE parent_event_id = id") == 0


def test_tombstones_keep_the_structure_and_leave_the_counters(engine: Any) -> None:
    insert_forest(
        engine,
        [
            (ROOT, "root", None, at(0), "acct-a", False),
            ("mid", "reply", ROOT, at(1), "acct-b", True),
            ("leaf", "reply", "mid", at(2), "acct-c", False),
            ("share", "repost", ROOT, at(3), "acct-d", True),
        ],
        root_uri=ROOT,
    )
    enrich_dirty(engine, as_of=AS_OF)
    states = event_states(engine)
    assert states["mid"] == ("resolved", ROOT, 1)
    assert states["leaf"] == ("resolved", "mid", 2)  # the child of a tombstone stays resolved
    row = cascade_row(engine)
    assert (row["event_count"], row["reply_count"], row["repost_count"]) == (2, 1, 0)
    assert (row["deleted_count"], row["max_depth"], row["unique_accounts"]) == (2, 2, 2)
    assert (row["orphan_count"], row["disconnected_count"]) == (0, 0)


# --- Locks: row lock, lost-flag race, advisory lock -----------------------------------------
def _small_cascade(engine: Any) -> int:
    return insert_forest(
        engine,
        [
            (ROOT, "root", None, at(0), "acct-a", False),
            ("a", "reply", ROOT, at(1), "acct-b", False),
        ],
        root_uri=ROOT,
    )


def test_a_cascade_locked_by_another_transaction_is_skipped_and_stays_dirty(
    engine: Any, clean_db: str, make_engine: Any
) -> None:
    cascade_id = _small_cascade(engine)
    other = make_engine(clean_db, role="collector")
    with other.connect() as holder:
        holder.begin()
        holder.execute(text("SELECT id FROM cascades WHERE id = :i FOR UPDATE"), {"i": cascade_id})
        result = enrich_dirty(engine, as_of=AS_OF)
        assert (result.selected, result.skipped_locked, result.enriched) == (1, 1, 0)
        assert cascade_row(engine)["enrich_dirty"] is True
        holder.rollback()
    result = enrich_dirty(engine, as_of=AS_OF)
    assert (result.enriched, result.skipped_locked) == (1, 0)
    assert cascade_row(engine)["enrich_dirty"] is False


def _wait_for_lock_waiter(engine: Any, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        waiting = scalar(
            engine,
            "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
            " AND wait_event_type = 'Lock'",
        )
        if waiting:
            return True
        time.sleep(0.02)
    return False


def _race(
    engine: Any, collector: Any, monkeypatch: pytest.MonkeyPatch, mark: Any, *, expect_wait: bool
) -> bool:
    """Run enrich; while its cascade transaction is open, a collector thread marks the cascade
    dirty with ``mark``. Returns whether the thread's UPDATE had to wait for enrich's lock."""
    cascade_id = _small_cascade(engine)
    real = apply.resolve_cascade
    errors: list[BaseException] = []
    waited: list[bool] = []

    def collector_mark() -> None:
        try:
            with collector.begin() as connection:
                mark(connection, cascade_id)
        except BaseException as exc:  # surfaced in the main thread
            errors.append(exc)

    worker = threading.Thread(target=collector_mark)

    def resolve_then_let_the_collector_in(rows: Any, as_of: datetime) -> Any:
        worker.start()
        if expect_wait:
            waited.append(_wait_for_lock_waiter(engine))
        else:
            worker.join(timeout=10)
            waited.append(False)
        return real(rows, as_of)

    monkeypatch.setattr(apply, "resolve_cascade", resolve_then_let_the_collector_in)
    result = enrich_dirty(engine, as_of=AS_OF)
    worker.join(timeout=10)
    assert not worker.is_alive()
    assert errors == []
    assert result.enriched == 1
    return waited[0]


def test_a_dirty_mark_during_an_enrich_transaction_is_never_lost(
    engine: Any, clean_db: str, make_engine: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    collector = make_engine(clean_db, role="collector")
    waited = _race(
        engine,
        collector,
        monkeypatch,
        lambda connection, ident: mark_cascades_dirty(connection, {ident}),
        expect_wait=True,
    )
    assert waited  # the writer's UPDATE waited for the enrich row lock ...
    assert cascade_row(engine)["enrich_dirty"] is True  # ... and the flag survived


def test_the_filtered_dirty_mark_would_have_lost_the_flag(
    engine: Any, clean_db: str, make_engine: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control: the writer's former ``WHERE enrich_dirty IS FALSE`` UPDATE reads the
    flag from its snapshot (still true), matches nothing, does not wait, and enrich then
    clears the flag: the collector's mark is lost. This is why mark_cascades_dirty is
    unconditional."""
    collector = make_engine(clean_db, role="collector")

    def filtered(connection: Any, ident: int) -> None:
        connection.execute(
            update(Cascade)
            .where(Cascade.id == ident, Cascade.enrich_dirty.is_(False))
            .values(enrich_dirty=True)
        )

    _race(engine, collector, monkeypatch, filtered, expect_wait=False)
    assert cascade_row(engine)["enrich_dirty"] is False


def test_an_event_row_held_by_an_open_collector_batch_is_contention_not_failure(
    engine: Any, clean_db: str, make_engine: Any
) -> None:
    insert_forest(
        engine,
        [
            (ROOT, "root", None, at(0), "acct-a", False),
            ("a", "reply", ROOT, at(1), "acct-b", False),
        ],
        root_uri=ROOT,
    )
    other = make_engine(clean_db, role="collector")
    with other.connect() as holder:
        holder.begin()
        holder.execute(text("SELECT id FROM events WHERE uri = 'a' FOR UPDATE"))
        result = enrich_dirty(engine, as_of=AS_OF)
        assert result.enriched == 0
        assert result.errors == {"LockNotAvailable": 1}
        assert cascade_row(engine)["enrich_dirty"] is True
        holder.rollback()
    assert enrich_dirty(engine, as_of=AS_OF).enriched == 1


def test_a_concurrent_enrich_run_is_refused_by_the_advisory_lock(
    engine: Any, clean_db: str, make_engine: Any
) -> None:
    _small_cascade(engine)
    other = make_engine(clean_db, role="jobs")
    with other.connect() as holder:
        assert try_advisory_lock(holder, ENRICH_LOCK_KEY)
        result = enrich_dirty(engine, as_of=AS_OF)
        assert result == EnrichResult(locked=True)
        assert result.line() == "enrich status=locked"
        release_advisory_lock(holder, ENRICH_LOCK_KEY)
    assert cascade_row(engine)["enrich_dirty"] is True
    assert enrich_dirty(engine, as_of=AS_OF).enriched == 1


# --- as_of, work selection and collector-owned columns --------------------------------------
def test_with_no_checkpoint_nothing_is_enriched(engine: Any) -> None:
    _small_cascade(engine)
    result = enrich_dirty(engine)
    assert (result.as_of, result.selected, result.enriched) == (None, 0, 0)
    assert cascade_row(engine)["enrich_dirty"] is True


def test_the_default_as_of_is_the_stream_time_and_changes_only_velocity(engine: Any) -> None:
    insert_forest(
        engine,
        [
            (ROOT, "root", None, at(0), "acct-a", False),
            ("a", "reply", ROOT, at(60), "acct-b", False),
            ("b", "reply", ROOT, at(4000), "acct-c", False),
        ],
        root_uri=ROOT,
    )
    set_checkpoint(engine, us_of(at(4000)))
    defaulted = enrich_dirty(engine)
    assert defaulted.as_of == at(4000)
    first = cascade_row(engine)
    assert (first["events_1h"], first["rolled_up_at"]) == (1, at(4000))  # (400 s, 4000 s]
    explicit = enrich_dirty(engine, as_of=at(100), force=True)
    assert (explicit.as_of, explicit.rows_updated, explicit.cascades_updated) == (at(100), 0, 1)
    second = cascade_row(engine)
    assert (second["events_1h"], second["rolled_up_at"]) == (2, at(100))  # (-3500 s, 100 s]
    changed = {k for k in first if first[k] != second[k]}
    assert changed == {"events_1h", "rolled_up_at"}


def test_a_stale_rollup_version_selects_a_clean_cascade(engine: Any) -> None:
    _small_cascade(engine)
    enrich_dirty(engine, as_of=AS_OF)
    with engine.begin() as connection:
        connection.execute(text("UPDATE cascades SET rollup_version = 0"))
    result = enrich_dirty(engine, as_of=AS_OF)
    assert (result.selected, result.cascades_updated) == (1, 1)
    assert cascade_row(engine)["rollup_version"] == ROLLUP_VERSION


def test_max_cascades_bounds_one_run_in_id_order(engine: Any) -> None:
    for index in range(3):
        insert_forest(
            engine,
            [(f"root-{index}", "root", None, at(index), "acct-a", False)],
            root_uri=f"root-{index}",
            id_base=1000 * (index + 1),
        )
    first = enrich_dirty(engine, as_of=AS_OF, max_cascades=2)
    assert first.selected == 2
    dirty = scalar(
        engine, "SELECT array_agg(root_uri ORDER BY id) FROM cascades WHERE enrich_dirty"
    )
    assert dirty == ["root-2"]
    assert enrich_dirty(engine, as_of=AS_OF, max_cascades=2).selected == 1
    with pytest.raises(ValueError, match="max_cascades"):
        enrich_dirty(engine, max_cascades=0)
    with pytest.raises(ValueError, match="aware"):
        enrich_dirty(engine, as_of=datetime(2026, 11, 1, 12, 0))


def test_an_unexpected_exception_is_counted_and_leaves_that_cascade_dirty(
    engine: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    for index in range(2):
        insert_forest(
            engine,
            [(f"root-{index}", "root", None, at(index), "acct-a", False)],
            root_uri=f"root-{index}",
            id_base=1000 * (index + 1),
        )
    real = apply.resolve_cascade
    calls = Counter[str]()

    def flaky(rows: Any, as_of: datetime) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise KeyError("boom")
        return real(rows, as_of)

    monkeypatch.setattr(apply, "resolve_cascade", flaky)
    result = enrich_dirty(engine, as_of=AS_OF)
    assert (result.selected, result.enriched, result.errors) == (2, 1, {"KeyError": 1})
    assert scalar(engine, "SELECT count(*) FROM cascades WHERE enrich_dirty") == 1


def test_a_database_failure_propagates(engine: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    _small_cascade(engine)

    def broken(*_args: object) -> None:
        raise OperationalError("SELECT 1", {}, RuntimeError("connection lost"))

    monkeypatch.setattr(apply, "_enrich_one", broken)
    with pytest.raises(OperationalError):
        enrich_dirty(engine, as_of=AS_OF)
    with engine.connect() as probe:  # the advisory lock was released on the way out
        assert try_advisory_lock(probe, ENRICH_LOCK_KEY)
        release_advisory_lock(probe, ENRICH_LOCK_KEY)


def test_enrich_never_writes_the_collector_owned_columns(
    engine: Any, explicit_policy: Any, keyer: Any
) -> None:
    owned = "overflow_count, overflow_through_us, root_deleted_at, claim_id, tracking_ends_at"
    run_pipeline(
        engine,
        explicit_policy(track_max_events_per_cascade=TEST_SMALL_CASCADE_CAP),
        fixture_items(keyer),
    )

    def snapshot() -> list[tuple[Any, ...]]:
        with engine.connect() as connection:
            rows = connection.execute(
                text("SELECT root_uri, " + owned + " FROM cascades ORDER BY root_uri")
            )
            return [tuple(r) for r in rows]

    before = snapshot()
    assert any(row[1] > 0 for row in before)  # some cascade really overflowed
    enrich_dirty(engine)
    assert snapshot() == before
    enrich_dirty(engine, force=True)
    assert snapshot() == before


def test_the_log_line_holds_counts_only(
    engine: Any, explicit_policy: Any, keyer: Any, caplog: pytest.LogCaptureFixture
) -> None:
    run_pipeline(engine, explicit_policy(), fixture_items(keyer))
    with engine.connect() as connection:
        keys = [u for (u,) in connection.execute(text("SELECT uri FROM events"))]
        keys += [p for (p,) in connection.execute(text("SELECT pseudonym FROM accounts"))]
    with caplog.at_level(logging.INFO, logger="truthtrail.enrich.apply"):
        result = enrich_dirty(engine)
    lines = [r.getMessage() for r in caplog.records if r.name == "truthtrail.enrich.apply"]
    assert lines == [result.line()]
    assert not any(key in lines[0] for key in keys)
    assert "did:" not in lines[0]
    assert "at://" not in lines[0]
