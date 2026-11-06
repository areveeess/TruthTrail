"""The bounded run loop against a real PostgreSQL (D-09, D-10, D-11, D-21, D-30, OD-3).

Sources are the real recording (ReplaySource) or ``ListSource`` doubles over its items; the
monotonic clock, the wall clock and the sleep are injected, and every bound is an explicit test
value.
"""

import asyncio
import logging
import signal
from datetime import timedelta
from typing import Any

import pytest
from conftest import (
    TEST_SMALL_CASCADE_CAP,
    ListSource,
    canonical_projection,
    fixture_items,
    row_counts,
)
from sqlalchemy import text

from truthtrail.db.locks import INGEST_LOCK_KEY, release_advisory_lock, try_advisory_lock
from truthtrail.ingest.dialect import datetime_from_us
from truthtrail.ingest.normalise import NormalizedEvent
from truthtrail.ingest.run import (
    REPLAY_SOURCE_NAME,
    RunBounds,
    RunSummary,
    run_ingest,
)
from truthtrail.ingest.source import (
    DEFAULT_MANIFEST,
    GapNotice,
    ReplaySource,
    SourceFailed,
    SourceItem,
)
from truthtrail.ingest.writer import claim_key_for, load_known_claim_urls

pytestmark = pytest.mark.requires_db

LIVE = "bluesky"


class Clock:
    """A fake monotonic clock that advances ``step`` seconds on every reading."""

    def __init__(self, step: float = 0.0) -> None:
        self.now = 0.0
        self.step = step

    def __call__(self) -> float:
        value = self.now
        self.now += self.step
        return value


class FailingSource(ListSource):
    """Yields ``after`` items, then raises ``error`` (a source failure or a Ctrl+C)."""

    def __init__(self, items: list[Any], after: int, error: BaseException, **kw: Any) -> None:
        super().__init__(items, **kw)
        self._after = after
        self._error = error

    async def items(self, resume_cursor_us: int | None, drops: Any = None) -> Any:
        count = 0
        async for item in super().items(resume_cursor_us, drops):
            if count == self._after:
                raise self._error
            yield item
            count += 1


@pytest.fixture
def engine(clean_db: str, make_engine: Any) -> Any:
    return make_engine(clean_db, role="collector")


@pytest.fixture
def items(keyer: Any) -> list[SourceItem]:
    return fixture_items(keyer)


def bounds(**overrides: Any) -> RunBounds:
    values: dict[str, Any] = {
        "max_seconds": 10_000.0,
        "max_events": 1_000_000,
        "max_stored": 1_000_000,
        "batch_rows": 50,
        "batch_seconds": 10_000.0,
    }
    values.update(overrides)
    return RunBounds(**values)


def run_loop(
    engine: Any,
    source: Any,
    policy: Any,
    *,
    source_name: str = REPLAY_SOURCE_NAME,
    clock: Clock | None = None,
    wall: Any = None,
    sleep: Any = None,
    loader: Any = load_known_claim_urls,
    **overrides: Any,
) -> RunSummary:
    async def no_sleep(_seconds: float) -> None:
        await asyncio.sleep(0)

    kwargs: dict[str, Any] = {
        "bounds": bounds(**overrides),
        "source_name": source_name,
        "monotonic": clock or Clock(),
        "sleep": sleep or no_sleep,
        "claim_url_loader": loader,
    }
    if wall is not None:
        kwargs["wall_clock"] = lambda: wall
    return asyncio.run(run_ingest(engine, source, policy, **kwargs))


def _scalar(engine: Any, sql: str, **params: Any) -> Any:
    with engine.connect() as connection:
        return connection.execute(text(sql), params).scalar_one()


def _run_row(engine: Any) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(text("SELECT * FROM ingest_runs ORDER BY id DESC LIMIT 1")).one()
    return dict(row._mapping)


def _max_cursor(items: list[SourceItem]) -> int:
    return max(i.cursor_us for i in items if i.cursor_us is not None)


# --- bounds --------------------------------------------------------------------------------------
def test_a_full_replay_ends_ok_at_the_source_end(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    summary = run_loop(engine, ListSource(items), explicit_policy())
    assert summary.status == "ok"
    assert summary.stop_reason == "source_end"
    assert summary.exit_code == 0
    assert row_counts(engine)["cascades"] == summary.counters["accepted_root"]
    row = _run_row(engine)
    assert row["status"] == "ok"
    assert row["mode"] == "replay"
    assert row["counters"]["stop:source_end"] == 1
    assert row["last_time_us"] == _max_cursor(items)
    assert row["error_class"] is None


def test_max_seconds_stops_on_the_monotonic_clock(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    summary = run_loop(
        engine, ListSource(items), explicit_policy(), clock=Clock(1.0), max_seconds=60
    )
    assert summary.stop_reason == "max_seconds"
    assert summary.exit_code == 0
    assert 0 < summary.counters["frames"] < len(items)


def test_max_events_stops_after_that_many_frames(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    summary = run_loop(engine, ListSource(items), explicit_policy(), max_events=100)
    assert summary.stop_reason == "max_events"
    assert summary.counters["frames"] == 100
    assert summary.exit_code == 0


def test_max_stored_stops_with_at_most_the_bound_written(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    summary = run_loop(engine, ListSource(items), explicit_policy(), max_stored=30, batch_rows=7)
    assert summary.stop_reason == "max_stored"
    assert row_counts(engine)["events"] <= 30
    assert row_counts(engine)["events"] >= 30 - 7
    assert summary.exit_code == 0


def test_the_total_event_cap_stops_promotion_as_capacity_reached(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    summary = run_loop(engine, ListSource(items), explicit_policy(store_max_events_total=40))
    assert summary.status == "capacity_reached"
    assert summary.stop_reason == "store_max_events_total"
    assert summary.exit_code == 0
    assert row_counts(engine)["events"] == 40
    assert _run_row(engine)["status"] == "capacity_reached"


def test_a_database_over_budget_at_start_stores_nothing(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    summary = run_loop(engine, ListSource(items), explicit_policy(db_budget_bytes=1))
    assert summary.status == "capacity_reached"
    assert summary.stop_reason == "db_budget"
    assert summary.exit_code == 0
    assert row_counts(engine)["events"] == 0


def test_the_budget_is_checked_every_refresh_cadence_of_batches(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    from truthtrail.ingest.writer import db_size_bytes

    with engine.connect() as connection:
        empty = db_size_bytes(connection)
    # room for the run row and the checkpoint (a few 8 KiB pages), not for the replay
    policy = explicit_policy(db_budget_bytes=empty + 48 * 1024, db_stop_percent=100)
    summary = run_loop(engine, ListSource(items), policy, batch_rows=20, refresh_every=2)
    assert summary.stop_reason == "db_budget"
    assert summary.counters["batches"] >= 2
    assert 0 < row_counts(engine)["events"] < 805
    assert row_counts(engine)["ingest_checkpoints"] == 1


def test_batches_flush_at_the_row_threshold(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    summary = run_loop(engine, ListSource(items), explicit_policy(), batch_rows=25)
    events = row_counts(engine)["events"]
    assert events // 25 <= summary.counters["batches"] <= events // 25 + 15


def test_batches_flush_at_the_time_threshold(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    summary = run_loop(
        engine,
        ListSource(items),
        explicit_policy(),
        clock=Clock(1.0),
        batch_rows=10**6,
        batch_seconds=100,
    )
    assert len(items) // 100 - 2 <= summary.counters["batches"] <= len(items) // 50 + 2


def test_a_checkpoint_only_transaction_is_written_when_nothing_is_stored(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    refused = [
        i for i in items if isinstance(i.result, NormalizedEvent) and i.result.edge_kind == "reply"
    ][:20]
    summary = run_loop(
        engine, ListSource(refused), explicit_policy(), clock=Clock(1.0), batch_seconds=1
    )
    assert row_counts(engine)["events"] == 0
    assert summary.counters["untracked"] == 20
    assert _scalar(engine, "SELECT cursor_time_us FROM ingest_checkpoints") == _max_cursor(refused)


def test_bounds_default_to_the_policy_values(explicit_policy: Any) -> None:
    policy = explicit_policy(
        ingest_max_seconds=11,
        ingest_max_events=12,
        ingest_max_stored=13,
        ingest_batch_rows=14,
        ingest_batch_seconds=15,
    )
    made = RunBounds.from_policy(policy, max_events=None, batch_delay_seconds=0.5)
    assert (made.max_seconds, made.max_events, made.max_stored) == (11, 12, 13)
    assert (made.batch_rows, made.batch_seconds, made.batch_delay_seconds) == (14, 15, 0.5)


# --- interruption and failures --------------------------------------------------------------------
def test_keyboard_interrupt_flushes_and_finalises_as_interrupted(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    source = FailingSource(items, 300, KeyboardInterrupt())
    summary = run_loop(engine, source, explicit_policy(), batch_rows=1000)
    assert summary.status == "interrupted"
    assert summary.exit_code == 0
    assert _scalar(engine, "SELECT cursor_time_us FROM ingest_checkpoints") == _max_cursor(
        items[:300]
    )
    assert _run_row(engine)["status"] == "interrupted"


def test_a_source_failure_keeps_what_was_read_and_records_the_class_name(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    source = FailingSource(items, 200, SourceFailed("reconnect_budget"))
    summary = run_loop(engine, source, explicit_policy())
    assert summary.status == "source_failed"
    assert summary.exit_code == 4
    assert summary.error_class == "SourceFailed"
    row = _run_row(engine)
    assert row["error_class"] == "SourceFailed"
    assert row["status"] == "source_failed"
    assert _scalar(engine, "SELECT cursor_time_us FROM ingest_checkpoints") == _max_cursor(
        items[:200]
    )


def test_a_database_failure_during_a_flush_is_db_failed_with_the_class_name_only(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE OR REPLACE FUNCTION tt_test_fail() RETURNS trigger LANGUAGE plpgsql AS $$"
                " BEGIN RAISE EXCEPTION 'injected test failure'; END $$"
            )
        )
        connection.execute(
            text(
                "CREATE TRIGGER tt_test_fail BEFORE INSERT ON events FOR EACH ROW"
                " EXECUTE FUNCTION tt_test_fail()"
            )
        )
    try:
        summary = run_loop(engine, ListSource(items), explicit_policy())
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP TRIGGER IF EXISTS tt_test_fail ON events"))
            connection.execute(text("DROP FUNCTION IF EXISTS tt_test_fail()"))
    assert summary.status == "db_failed"
    assert summary.exit_code == 5
    row = _run_row(engine)
    assert row["error_class"] == summary.error_class
    assert summary.error_class is not None
    assert summary.error_class.isidentifier()
    assert "injected" not in str(row)
    assert row_counts(engine)["events"] == 0


def test_an_unreachable_database_is_db_failed(
    make_engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    engine = make_engine(f"postgresql+psycopg://nobody@127.0.0.1:{port}/none", role="collector")
    summary = run_loop(engine, ListSource(items), explicit_policy())
    assert summary.status == "db_failed"
    assert summary.exit_code == 5
    assert summary.error_class == "OperationalError"


def test_a_second_concurrent_run_is_refused_by_the_advisory_lock(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    with engine.connect() as holder:
        assert try_advisory_lock(holder, INGEST_LOCK_KEY)
        locked = run_loop(engine, ListSource(items), explicit_policy())
        assert release_advisory_lock(holder, INGEST_LOCK_KEY)
    assert locked.status == "locked"
    assert locked.exit_code == 6
    assert row_counts(engine)["events"] == 0
    after = run_loop(engine, ListSource(items), explicit_policy())
    assert after.status == "ok"
    with engine.connect() as probe:
        assert try_advisory_lock(probe, INGEST_LOCK_KEY)
        assert release_advisory_lock(probe, INGEST_LOCK_KEY)


# --- resume, gaps, summary ------------------------------------------------------------------------
def _old_checkpoint(engine: Any, source_name: str, cursor: int) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO ingest_checkpoints (source, dialect, host, cursor_time_us)"
                " VALUES (:s, 'v2', 'loopback', :c)"
            ),
            {"s": source_name, "c": cursor},
        )


def test_an_old_live_checkpoint_starts_at_the_tip_and_records_a_resume_gap(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    policy = explicit_policy()
    wall = datetime_from_us(_max_cursor(items)) + timedelta(minutes=1)
    hours = policy.ingest_max_resume_age_hours + 1
    checkpoint = _max_cursor(items) + 60_000_000 - hours * 3_600_000_000
    _old_checkpoint(engine, LIVE, checkpoint)
    first = next(i.cursor_us for i in items if i.cursor_us is not None)
    summary = run_loop(engine, ListSource(items, mode="live"), policy, source_name=LIVE, wall=wall)
    row = _run_row(engine)
    assert row["resume_gap"] is True
    assert row["resume_from_time_us"] is None
    assert (row["gap_from_us"], row["gap_to_us"], row["gap_count"]) == (checkpoint, first, 1)
    assert summary.gap_count == 1


def test_replay_mode_never_records_a_resume_gap(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    policy = explicit_policy()
    wall = datetime_from_us(_max_cursor(items)) + timedelta(minutes=1)
    checkpoint = _max_cursor(items) - 3_600_000_000 * (policy.ingest_max_resume_age_hours + 1)
    _old_checkpoint(engine, REPLAY_SOURCE_NAME, checkpoint)
    run_loop(engine, ListSource(items), policy, wall=wall)
    row = _run_row(engine)
    assert row["resume_gap"] is False
    assert row["gap_count"] == 0
    assert row["resume_from_time_us"] == checkpoint - policy.ingest_rewind_seconds * 1_000_000


def test_a_mid_run_outdated_cursor_merges_into_the_gap_span(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    cursors = [i.cursor_us for i in items[:60] if i.cursor_us is not None]
    gap = SourceItem(GapNotice(cursors[-1], None, "outdated_cursor"), None)
    later = next(i.cursor_us for i in items[60:] if i.cursor_us is not None)
    summary = run_loop(engine, ListSource([*items[:60], gap, *items[60:]]), explicit_policy())
    row = _run_row(engine)
    assert (row["gap_from_us"], row["gap_to_us"], row["gap_count"]) == (cursors[-1], later, 1)
    assert summary.counters["gap:outdated_cursor"] == 1


def test_the_summary_is_one_info_line_of_counts_without_identifiers(
    engine: Any, explicit_policy: Any, items: list[SourceItem], caplog: Any
) -> None:
    with caplog.at_level(logging.DEBUG):
        summary = run_loop(engine, ListSource(items), explicit_policy())
    records = [r for r in caplog.records if r.name == "truthtrail.ingest.run"]
    assert len(records) == 1
    assert records[0].levelno == logging.INFO
    assert records[0].getMessage() == summary.line()
    with engine.connect() as connection:
        keys = [k for (k,) in connection.execute(text("SELECT uri FROM events"))]
        keys += [k for (k,) in connection.execute(text("SELECT pseudonym FROM accounts"))]
    assert keys
    assert not any(key in caplog.text for key in keys)


def test_resume_after_a_stop_equals_one_uninterrupted_run(
    engine: Any, explicit_policy: Any, keyer: Any
) -> None:
    policy = explicit_policy(track_max_events_per_cascade=TEST_SMALL_CASCADE_CAP)
    run_loop(engine, ReplaySource(DEFAULT_MANIFEST, keyer), policy, batch_rows=20)
    expected = canonical_projection(engine)
    assert _scalar(engine, "SELECT sum(overflow_count) FROM cascades") > 0
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE accounts, claims, cascades, events, ingest_checkpoints, ingest_runs"
                " CASCADE"
            )
        )
    stopped = run_loop(
        engine, ReplaySource(DEFAULT_MANIFEST, keyer), policy, batch_rows=20, max_events=500
    )
    assert stopped.stop_reason == "max_events"
    resumed = run_loop(engine, ReplaySource(DEFAULT_MANIFEST, keyer), policy, batch_rows=20)
    assert resumed.status == "ok"
    assert _run_row(engine)["resume_from_time_us"] is not None
    assert canonical_projection(engine) == expected


# --- option B in the loop -------------------------------------------------------------------------
def _near_and_fillers(
    items: list[SourceItem], allowlist: Any
) -> tuple[SourceItem, list[SourceItem]]:
    from truthtrail.ingest import selection

    refused = []
    for item in items:
        r = item.result
        if isinstance(r, NormalizedEvent) and r.edge_kind == "root-candidate" and r.links:
            decision = selection.seed_decision_for(r.seed_candidate(), allowlist)
            if decision.reason == "not_allowlisted" and "en" in r.langs and not r.labels:
                refused.append(item)
    return refused[-1], refused[:6]


def test_option_b_loader_runs_at_start_and_every_cadence_and_picks_up_new_headlines(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    from truthtrail.ingest import selection

    policy = explicit_policy(track_seed_claim_url_match=True)
    near, fillers = _near_and_fillers(items, selection.load_allowlist(policy.track_allowlist_file))
    url = near.result.links[0].url
    loaded: list[frozenset[str]] = []

    def loader(connection: Any) -> frozenset[str]:
        urls = load_known_claim_urls(connection)
        loaded.append(urls)
        return urls

    async def insert_headline_once(_seconds: float) -> None:
        if _scalar(engine, "SELECT count(*) FROM claims WHERE kind = 'news_headline'") == 0:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO claims (kind, claim_key, text, text_hash, url_canonical)"
                        " VALUES ('news_headline', :k, 'headline', :k, :u)"
                    ),
                    {"k": claim_key_for("news_headline", url), "u": url},
                )

    summary = run_loop(
        engine,
        ListSource([*fillers, near]),
        policy,
        clock=Clock(1.0),
        batch_seconds=1,
        batch_delay_seconds=0.001,
        refresh_every=2,
        sleep=insert_headline_once,
        loader=loader,
    )
    assert loaded[0] == frozenset()
    assert len(loaded) >= 2
    assert url in loaded[-1]
    assert summary.counters["seed_claim_url_match"] == 1
    assert row_counts(engine)["cascades"] == 1


def test_option_b_off_never_calls_the_loader(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    calls: list[int] = []

    def loader(_connection: Any) -> frozenset[str]:
        calls.append(1)
        return frozenset()

    run_loop(
        engine, ListSource(items), explicit_policy(), refresh_every=1, batch_rows=10, loader=loader
    )
    assert calls == []


def test_the_loop_runs_under_asyncio_run_and_installs_no_signal_handler(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    names = [s for s in (signal.SIGINT, signal.SIGTERM, getattr(signal, "SIGHUP", None)) if s]
    before = {s: signal.getsignal(s) for s in names}
    inside: dict[Any, Any] = {}

    class Probe(ListSource):
        async def items(self, resume_cursor_us: int | None, drops: Any = None) -> Any:
            loop = asyncio.get_running_loop()
            inside["loop_handlers"] = dict(getattr(loop, "_signal_handlers", {}))
            inside["term"] = signal.getsignal(signal.SIGTERM)
            async for item in super().items(resume_cursor_us, drops):
                yield item

    summary = run_loop(engine, Probe(items[:50]), explicit_policy())
    assert summary.status == "ok"
    assert inside["loop_handlers"] == {}
    assert inside["term"] == before[signal.SIGTERM]
    assert {s: signal.getsignal(s) for s in names} == before
