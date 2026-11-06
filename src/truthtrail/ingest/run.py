"""The bounded collector run (D-09, D-10, D-11, D-21, D-30; RESEARCH Pattern 2).

``run_ingest`` is one batch job: asyncio at the socket edge, a synchronous database behind
``asyncio.to_thread`` (each flush is one transaction; the reader waits for it, which is the
natural back-pressure). It stops at the first of the time bound (a monotonic clock, never stream
time), the frames bound, the stored-rows bound, the STORE_MAX_EVENTS_TOTAL cap and, checked at
start and every ``refresh_every`` batches, DB_STOP_PERCENT of DB_BUDGET_BYTES. Reaching a
capacity bound is status ``capacity_reached``: promotion stops and is reported, nothing is ever
evicted. The checkpoint moves only inside the transaction that wrote the rows it covers.

One advisory lock per command makes runs single-flight (a second run returns ``locked``). The
``ingest_runs`` row is written at start (``running``) and finalised in a ``finally`` block with
the status, the counters (a JSON object of counts by name; the stop reason is the counter
``stop:<reason>``), the last stream time, the merged gap span and, on failure, the error CLASS
name only. No POSIX signal handler is installed: a KeyboardInterrupt or a cancellation ends the
run as ``interrupted`` after the final flush. The summary is ONE INFO log line of counts.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import Counter
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from truthtrail.core.policy import Policy
from truthtrail.db.locks import INGEST_LOCK_KEY, release_advisory_lock, try_advisory_lock
from truthtrail.db.models import IngestCheckpoint, IngestRun
from truthtrail.ingest import selection
from truthtrail.ingest.dialect import resume_cursor
from truthtrail.ingest.source import (
    DropCounter,
    EventSource,
    GapNotice,
    SourceError,
    SourceItem,
)
from truthtrail.ingest.writer import (
    Batch,
    Decider,
    FlushResult,
    TrackedIndex,
    db_size_bytes,
    flush,
    load_known_claim_urls,
)

logger = logging.getLogger(__name__)

STATUS_RUNNING = "running"
STATUS_OK = "ok"
STATUS_CAPACITY = "capacity_reached"
STATUS_INTERRUPTED = "interrupted"
STATUS_SOURCE_FAILED = "source_failed"
STATUS_DB_FAILED = "db_failed"
STATUS_LOCKED = "locked"

EXIT_OK = 0
EXIT_CONFIG = 3
EXIT_SOURCE = 4
EXIT_DATABASE = 5
EXIT_LOCKED = 6
EXIT_CODES: dict[str, int] = {
    STATUS_OK: EXIT_OK,
    STATUS_CAPACITY: EXIT_OK,
    STATUS_INTERRUPTED: EXIT_OK,
    STATUS_SOURCE_FAILED: EXIT_SOURCE,
    STATUS_DB_FAILED: EXIT_DATABASE,
    STATUS_LOCKED: EXIT_LOCKED,
}

STOP_MAX_SECONDS = "max_seconds"
STOP_MAX_EVENTS = "max_events"
STOP_MAX_STORED = "max_stored"
STOP_TOTAL_EVENTS = "store_max_events_total"
STOP_DB_BUDGET = "db_budget"
STOP_SOURCE_END = "source_end"
STOP_INTERRUPTED = "interrupted"
STOP_SOURCE_FAILED = "source_failed"
STOP_DB_FAILED = "db_failed"

LIVE_SOURCE_NAME = "bluesky"
REPLAY_SOURCE_NAME = "bluesky-replay"
REFRESH_EVERY_BATCHES = 50
_US_PER_HOUR = 3_600_000_000


@dataclass(frozen=True, slots=True)
class RunBounds:
    """The bounds of one run (D-10); ``from_policy`` takes every default from the Policy."""

    max_seconds: float
    max_events: int
    max_stored: int
    batch_rows: int
    batch_seconds: float
    batch_delay_seconds: float = 0.0
    refresh_every: int = REFRESH_EVERY_BATCHES

    @classmethod
    def from_policy(cls, policy: Policy, **overrides: Any) -> RunBounds:
        values: dict[str, Any] = {
            "max_seconds": float(policy.ingest_max_seconds),
            "max_events": policy.ingest_max_events,
            "max_stored": policy.ingest_max_stored,
            "batch_rows": policy.ingest_batch_rows,
            "batch_seconds": float(policy.ingest_batch_seconds),
        }
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**values)


@dataclass(frozen=True, slots=True)
class RunSummary:
    """The outcome of one run: counts and class names only (D-18)."""

    status: str
    stop_reason: str
    counters: Mapping[str, int]
    last_time_us: int | None = None
    gap_count: int = 0
    error_class: str | None = None
    run_id: int | None = None

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.status]

    def line(self) -> str:
        """The one-line summary: status, stop reason and counts, nothing else."""
        counts = " ".join(f"{name}={value}" for name, value in sorted(self.counters.items()))
        return f"ingest status={self.status} stop={self.stop_reason} {counts}".rstrip()


@dataclass(slots=True)
class _Gaps:
    """Every gap of the run merged into one conservative span (D-09)."""

    from_us: int | None = None
    to_us: int | None = None
    count: int = 0
    open: bool = False

    def add(self, from_us: int | None, to_us: int | None) -> None:
        self.count += 1
        if from_us is not None:
            self.from_us = from_us if self.from_us is None else min(self.from_us, from_us)
        if to_us is None:
            self.open = True
        else:
            self.close(to_us)

    def close(self, at_us: int) -> None:
        self.to_us = at_us if self.to_us is None else max(self.to_us, at_us)
        self.open = False


@dataclass(slots=True)
class _State:
    counters: Counter[str] = field(default_factory=Counter)
    gaps: _Gaps = field(default_factory=_Gaps)
    frames: int = 0
    stored: int = 0
    batches: int = 0
    last_time_us: int | None = None
    committed_us: int | None = None


def _read_checkpoint(connection: Connection, source_name: str) -> int | None:
    value = connection.execute(
        select(IngestCheckpoint.cursor_time_us).where(IngestCheckpoint.source == source_name)
    ).scalar_one_or_none()
    connection.commit()
    return value


def _over_budget(connection: Connection, policy: Policy) -> bool:
    limit = policy.db_budget_bytes * policy.db_stop_percent // 100
    over = db_size_bytes(connection) >= limit
    connection.commit()
    return over


async def run_ingest(
    engine: Engine,
    source: EventSource,
    policy: Policy,
    *,
    bounds: RunBounds,
    source_name: str,
    monotonic: Callable[[], float] = time.monotonic,
    wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], Any] = asyncio.sleep,
    claim_url_loader: Callable[[Connection], frozenset[str]] = load_known_claim_urls,
) -> RunSummary:
    """Run the collector once within ``bounds``; returns the summary (never raises for a source
    or database failure, a KeyboardInterrupt or a cancellation)."""
    state = _State()
    try:
        lock = engine.connect()
    except SQLAlchemyError as exc:
        return _failed_early(state, exc)
    try:
        try:
            if not try_advisory_lock(lock, INGEST_LOCK_KEY):
                return RunSummary(STATUS_LOCKED, STATUS_LOCKED, {})
        except SQLAlchemyError as exc:
            return _failed_early(state, exc)
        try:
            return await _locked_run(
                engine,
                lock,
                source,
                policy,
                bounds,
                source_name,
                state,
                monotonic=monotonic,
                wall_clock=wall_clock,
                sleep=sleep,
                claim_url_loader=claim_url_loader,
            )
        finally:
            # the lock also dies with the connection, closed below
            with contextlib.suppress(SQLAlchemyError):
                release_advisory_lock(lock, INGEST_LOCK_KEY)
    finally:
        lock.close()


def _failed_early(state: _State, exc: BaseException) -> RunSummary:
    summary = RunSummary(
        STATUS_DB_FAILED, STOP_DB_FAILED, dict(state.counters), error_class=type(exc).__name__
    )
    logger.info("%s", summary.line())
    return summary


async def _locked_run(
    engine: Engine,
    lock: Connection,
    source: EventSource,
    policy: Policy,
    bounds: RunBounds,
    source_name: str,
    state: _State,
    *,
    monotonic: Callable[[], float],
    wall_clock: Callable[[], datetime],
    sleep: Callable[[float], Any],
    claim_url_loader: Callable[[Connection], frozenset[str]],
) -> RunSummary:
    started = monotonic()
    live = source.mode == "live"
    rewind = policy.ingest_rewind_seconds
    try:
        checkpoint = _read_checkpoint(lock, source_name)
    except SQLAlchemyError as exc:
        return _failed_early(state, exc)
    now_us = int(wall_clock().timestamp() * 1_000_000)
    resume: int | None = None
    resume_gap = False
    if checkpoint is not None:
        too_old = now_us - checkpoint > policy.ingest_max_resume_age_hours * _US_PER_HOUR
        if live and too_old:
            resume_gap = True
            state.gaps.add(checkpoint, None)  # closed by the first event at the tip
        else:
            resume = resume_cursor(checkpoint, rewind)
    since: int | None
    if resume is not None:
        since = resume_cursor(resume, rewind)
    else:
        since = resume_cursor(now_us, rewind) if live else None

    index = TrackedIndex()
    try:
        index.load(lock, since)
        lock.commit()
        # OD-3 option B: the claims table is queried only when the flag is true.
        known = claim_url_loader(lock) if policy.track_seed_claim_url_match else frozenset()
        lock.commit()
        run_id = _start_run_row(lock, source, source_name, wall_clock(), resume, resume_gap)
        over = _over_budget(lock, policy)
    except SQLAlchemyError as exc:
        return _failed_early(state, exc)
    decider = Decider(policy, index, selection.load_allowlist(policy.track_allowlist_file), known)
    status, stop = STATUS_OK, STOP_SOURCE_END
    error_class: str | None = None
    batch = Batch()
    batch_started = monotonic()
    drops = DropCounter()
    stream: AsyncIterator[SourceItem] = source.items(resume, drops)

    async def commit_batch(current: Batch) -> FlushResult:
        result = await asyncio.to_thread(
            flush, engine, current, source=source_name, dialect=source.dialect, host=source.host
        )
        index.commit(result, current)
        if current.max_time_us is not None:
            index.expire(current.max_time_us)
            state.committed_us = max(state.committed_us or 0, current.max_time_us)
        _count_flush(state, current, result)
        return result

    try:
        if over:
            status, stop = STATUS_CAPACITY, STOP_DB_BUDGET
        else:
            while True:
                remaining = bounds.max_seconds - (monotonic() - started)
                if remaining <= 0:
                    stop = STOP_MAX_SECONDS
                    break
                try:
                    item = await asyncio.wait_for(anext(stream), timeout=remaining)
                except StopAsyncIteration:
                    stop = STOP_SOURCE_END
                    break
                except TimeoutError:
                    stop = STOP_MAX_SECONDS
                    break
                state.frames += 1
                _handle_item(item, decider, batch, state)
                due = monotonic() - batch_started >= bounds.batch_seconds
                advanced = batch.max_time_us is not None and (
                    state.committed_us is None or batch.max_time_us > state.committed_us
                )
                if batch.rows >= bounds.batch_rows or (due and (batch.rows or advanced)):
                    await commit_batch(batch)
                    batch = Batch()
                    batch_started = monotonic()
                    state.batches += 1
                    if bounds.batch_delay_seconds > 0:
                        await sleep(bounds.batch_delay_seconds)
                    if state.batches % bounds.refresh_every == 0:
                        if await asyncio.to_thread(_check_budget, engine, policy):
                            status, stop = STATUS_CAPACITY, STOP_DB_BUDGET
                            break
                        if policy.track_seed_claim_url_match:
                            decider.set_known_claim_urls(
                                await asyncio.to_thread(_load_claims, engine, claim_url_loader)
                            )
                if state.frames + drops.total() >= bounds.max_events:
                    stop = STOP_MAX_EVENTS
                    break
                if state.stored + batch_pending(batch) >= bounds.max_stored:
                    stop = STOP_MAX_STORED  # the final flush below writes at most the bound
                    break
                if index.total_events >= policy.store_max_events_total:
                    status, stop = STATUS_CAPACITY, STOP_TOTAL_EVENTS
                    break
        if batch.rows or batch.max_time_us is not None:
            await commit_batch(batch)
            batch = Batch()
    except SourceError as exc:
        status, stop, error_class = STATUS_SOURCE_FAILED, STOP_SOURCE_FAILED, type(exc).__name__
        error_class = await _final_flush(commit_batch, batch, error_class, state)
        if error_class != type(exc).__name__:
            status, stop = STATUS_DB_FAILED, STOP_DB_FAILED
    except SQLAlchemyError as exc:
        status, stop, error_class = STATUS_DB_FAILED, STOP_DB_FAILED, type(exc).__name__
    except (KeyboardInterrupt, asyncio.CancelledError):
        # The top-level task: finish the run cleanly instead of propagating (D-30, no handler).
        status, stop = STATUS_INTERRUPTED, STOP_INTERRUPTED
        result = await _final_flush(commit_batch, batch, None, state)
        if result is not None:
            status, stop, error_class = STATUS_DB_FAILED, STOP_DB_FAILED, result
    finally:
        aclose = getattr(stream, "aclose", None)
        if aclose is not None:
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await aclose()
    for reason, count in drops.as_dict().items():
        state.counters["drop:" + reason] += count
    state.counters["frames"] = state.frames + drops.total()
    state.counters["stop:" + stop] = 1
    summary = RunSummary(
        status,
        stop,
        dict(state.counters),
        state.last_time_us,
        state.gaps.count,
        error_class,
        run_id,
    )
    try:
        await asyncio.to_thread(_finish_run_row, engine, run_id, summary, state.gaps, wall_clock())
    except SQLAlchemyError as exc:
        if summary.status != STATUS_DB_FAILED:
            summary = RunSummary(
                STATUS_DB_FAILED,
                STOP_DB_FAILED,
                summary.counters,
                summary.last_time_us,
                summary.gap_count,
                type(exc).__name__,
                run_id,
            )
    logger.info("%s", summary.line())
    return summary


def batch_pending(batch: Batch) -> int:
    """Rows of the open batch that would be stored (events only)."""
    return len(batch.events)


async def _final_flush(
    commit_batch: Callable[[Batch], Any], batch: Batch, error_class: str | None, state: _State
) -> str | None:
    """Flush what was read before the failure; returns the database error class if it fails."""
    if not batch.rows and batch.max_time_us is None:
        return error_class
    try:
        await commit_batch(batch)
    except SQLAlchemyError as exc:
        return type(exc).__name__
    return error_class


def _handle_item(item: SourceItem, decider: Decider, batch: Batch, state: _State) -> None:
    result = item.result
    if isinstance(result, GapNotice):
        state.gaps.add(result.from_us, result.to_us)
        state.counters["gap:" + result.reason] += 1
        return
    if item.cursor_us is not None:
        if state.gaps.open:
            state.gaps.close(item.cursor_us)
        if state.last_time_us is None or item.cursor_us > state.last_time_us:
            state.last_time_us = item.cursor_us
    batch.note_cursor(item.cursor_us)
    state.counters["item:" + type(result).__name__] += 1
    state.counters[decider.process(result, batch)] += 1


def _count_flush(state: _State, batch: Batch, result: FlushResult) -> None:
    state.counters.update(batch.counters)
    state.stored += result.inserted
    for kind, count in result.inserted_by_kind.items():
        state.counters["stored_" + kind] += count
    for cause, count in result.tombstoned_by_cause.items():
        state.counters["tombstoned_" + cause] += count
    for name, value in (
        ("duplicate_on_insert", result.duplicates),
        ("delete_unmatched", result.deletes_unmatched),
        ("account_action_unmatched", result.account_actions_unmatched),
        ("root_deleted", result.roots_deleted),
        ("overflow_counted", result.overflow_counted),
    ):
        if value:
            state.counters[name] += value
    state.counters["batches"] += 1


def _check_budget(engine: Engine, policy: Policy) -> bool:
    with engine.connect() as connection:
        return _over_budget(connection, policy)


def _load_claims(engine: Engine, loader: Callable[[Connection], frozenset[str]]) -> frozenset[str]:
    with engine.connect() as connection:
        return loader(connection)


def _start_run_row(
    connection: Connection,
    source: EventSource,
    source_name: str,
    started_at: datetime,
    resume: int | None,
    resume_gap: bool,
) -> int:
    run_id = connection.execute(
        insert(IngestRun)
        .values(
            source=source_name,
            dialect=source.dialect,
            host=source.host,
            mode=source.mode,
            started_at=started_at,
            status=STATUS_RUNNING,
            resume_from_time_us=resume,
            resume_gap=resume_gap,
        )
        .returning(IngestRun.id)
    ).scalar_one()
    connection.commit()
    return int(run_id)


def _finish_run_row(
    engine: Engine, run_id: int, summary: RunSummary, gaps: _Gaps, finished_at: datetime
) -> None:
    with engine.begin() as connection:
        connection.execute(
            update(IngestRun)
            .where(IngestRun.id == run_id)
            .values(
                finished_at=finished_at,
                status=summary.status,
                counters=dict(summary.counters),
                last_time_us=summary.last_time_us,
                gap_from_us=gaps.from_us,
                gap_to_us=gaps.to_us,
                gap_count=gaps.count,
                error_class=summary.error_class,
            )
        )
