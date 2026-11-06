"""Per-cascade transactional enrich write-back (D-14, D-22, D-24; RESEARCH Pattern 7, F-17).

``enrich_dirty(engine)`` selects work with SQL, resolves each cascade with the pure
``resolve_cascade`` and writes the result back, ONE transaction per cascade, so a reader always
sees a consistent cascade:

1. The enrich advisory lock is taken on a dedicated connection; when another run holds it the
   result says ``locked`` (the CLI exits 6) and nothing is read or written.
2. ``as_of`` is the explicit value, else the stream time of the most recently updated ingest
   checkpoint (``data_as_of``, D-24), so ``events_1h`` is consistent with what the API calls
   current; with no checkpoint nothing has been ingested and there is nothing to enrich.
3. Work is every cascade with ``enrich_dirty`` set or a ``rollup_version`` other than
   ``ROLLUP_VERSION``, ordered by id, at most ``max_cascades``; ``force`` selects every cascade.
4. Per cascade: ``SELECT ... FOR UPDATE SKIP LOCKED`` on the cascade row. A locked row (for
   example by an open collector batch, whose event inserts hold a key-share lock on it) is
   skipped and stays dirty. While enrich holds the lock, the collector's dirty-marking UPDATE
   waits for it and then sets the flag again, so a flag can never be lost (T-03-43).
5. The cascade's events (at most TRACK_MAX_EVENTS_PER_CASCADE by construction) are loaded,
   resolved, and only the events whose ``parent_event_id``, ``parent_state`` or ``depth``
   changed are updated (one executemany with bound parameters); the cascade row is updated only
   when a counter, the flag, ``rolled_up_at`` (= ``as_of``) or the version differs. A second
   pass over unchanged data therefore writes nothing.

Enrich never writes the collector-owned columns (``overflow_count``, ``overflow_through_us``,
``root_deleted_at``, ``claim_id``, ``tracking_ends_at``) and never invents a parent: an orphan
keeps ``parent_event_id`` NULL until its parent is stored.

An unexpected exception while resolving one cascade is counted by class name, rolls that
cascade back (it stays dirty) and does not stop the run; so is a lock conflict on an event row
(the changed rows are locked ``NOWAIT`` before the update, so a row held by an open collector
batch fails at once instead of deadlocking; SQLSTATE 55P03, or 40P01 for a deadlock). Any
other database error propagates (the CLI exits 5). The run logs ONE line of counts and never
an identifier.
"""

import logging
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import bindparam, or_, select, update
from sqlalchemy.engine import Connection, Engine, RowMapping
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from truthtrail.db.locks import ENRICH_LOCK_KEY, release_advisory_lock, try_advisory_lock
from truthtrail.db.models import Account, Cascade, Event, IngestCheckpoint
from truthtrail.enrich.resolve import EventRow, ResolvedCascade, resolve_cascade
from truthtrail.enrich.rollup import ROLLUP_VERSION

logger = logging.getLogger(__name__)

DEFAULT_MAX_CASCADES = 1000
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
# Lock conflicts on an event row are contention, not a broken database: the cascade stays
# dirty and the next run picks it up.
_CONTENTION_SQLSTATES = frozenset({"40P01", "55P03"})


def datetime_from_us(value: int) -> datetime:
    """The aware UTC datetime of Unix microseconds (exact integer arithmetic)."""
    return _EPOCH + timedelta(microseconds=value)


@dataclass(frozen=True)
class EnrichResult:
    """Counts of one enrich run (no identifiers). ``locked`` means another run held the lock."""

    locked: bool = False
    as_of: datetime | None = None
    selected: int = 0
    enriched: int = 0
    skipped_locked: int = 0
    cascades_updated: int = 0
    rows_updated: int = 0
    orphans: int = 0
    disconnected: int = 0
    invalid: int = 0
    order_violations: int = 0
    errors: Mapping[str, int] = field(default_factory=dict)

    def line(self) -> str:
        """One line of counts for the CLI and the log."""
        if self.locked:
            return "enrich status=locked"
        errors = ",".join(f"{name}:{count}" for name, count in sorted(self.errors.items()))
        return (
            f"enrich status=ok selected={self.selected} enriched={self.enriched}"
            f" skipped_locked={self.skipped_locked} cascades_updated={self.cascades_updated}"
            f" rows_updated={self.rows_updated} orphans={self.orphans}"
            f" disconnected={self.disconnected} invalid={self.invalid}"
            f" order_violations={self.order_violations} errors={errors or 'none'}"
        )


@dataclass
class _Tally:
    enriched: int = 0
    skipped_locked: int = 0
    cascades_updated: int = 0
    rows_updated: int = 0
    orphans: int = 0
    disconnected: int = 0
    invalid: int = 0
    order_violations: int = 0
    errors: Counter[str] = field(default_factory=Counter)


@dataclass(frozen=True)
class _Outcome:
    resolved: ResolvedCascade
    rows_updated: int
    cascade_updated: bool


def default_as_of(connection: Connection) -> datetime | None:
    """``data_as_of``: the stream time of the most recently updated checkpoint, or None."""
    cursor = connection.execute(
        select(IngestCheckpoint.cursor_time_us)
        .order_by(IngestCheckpoint.updated_at.desc(), IngestCheckpoint.source)
        .limit(1)
    ).scalar_one_or_none()
    return None if cursor is None else datetime_from_us(int(cursor))


def select_work(connection: Connection, *, max_cascades: int, force: bool) -> list[int]:
    """Ids of the cascades to enrich, ordered by id, at most ``max_cascades``."""
    query = select(Cascade.id).order_by(Cascade.id).limit(max_cascades)
    if not force:
        query = query.where(
            or_(Cascade.enrich_dirty.is_(True), Cascade.rollup_version != ROLLUP_VERSION)
        )
    return [int(ident) for ident in connection.execute(query).scalars()]


_LOCK_CASCADE = (
    select(
        Cascade.id,
        Cascade.enrich_dirty,
        Cascade.rolled_up_at,
        Cascade.rollup_version,
        Cascade.first_event_at,
        Cascade.last_event_at,
        Cascade.event_count,
        Cascade.reply_count,
        Cascade.quote_count,
        Cascade.repost_count,
        Cascade.unique_accounts,
        Cascade.max_depth,
        Cascade.orphan_count,
        Cascade.disconnected_count,
        Cascade.deleted_count,
        Cascade.order_violation_count,
        Cascade.events_1h,
    )
    .where(Cascade.id == bindparam("cascade_id"))
    .with_for_update(skip_locked=True)
)

_LOAD_EVENTS = (
    select(
        Event.id,
        Event.uri,
        Event.edge_kind,
        Event.parent_uri,
        Event.observed_at,
        Account.pseudonym,
        Event.deleted_at,
        Event.parent_event_id,
        Event.parent_state,
        Event.depth,
    )
    .outerjoin(Account, Account.id == Event.account_id)
    .where(Event.cascade_id == bindparam("cascade_id"))
    .order_by(Event.uri)
)

_UPDATE_EVENT = (
    update(Event)
    .where(Event.id == bindparam("b_id"))
    .values(
        parent_event_id=bindparam("b_parent"),
        parent_state=bindparam("b_state"),
        depth=bindparam("b_depth"),
    )
)


def _cascade_values(
    resolved: ResolvedCascade, as_of: datetime, current: RowMapping
) -> dict[str, Any]:
    values: dict[str, Any] = dict(resolved.rollup.counters())
    rollup = resolved.rollup
    # An empty cascade (every event purged) keeps its NOT NULL times.
    values["first_event_at"] = rollup.first_event_at or current["first_event_at"]
    values["last_event_at"] = rollup.last_event_at or current["last_event_at"]
    values["enrich_dirty"] = False
    values["rolled_up_at"] = as_of
    values["rollup_version"] = ROLLUP_VERSION
    return values


def _enrich_one(connection: Connection, cascade_id: int, as_of: datetime) -> _Outcome | None:
    """Resolve and write one cascade inside the caller's transaction; None when locked."""
    locked = connection.execute(_LOCK_CASCADE, {"cascade_id": cascade_id}).mappings().first()
    if locked is None:
        return None
    loaded = connection.execute(_LOAD_EVENTS, {"cascade_id": cascade_id}).all()
    rows = [
        EventRow(uri, kind, parent_uri, observed_at, pseudonym, deleted_at is not None)
        for _id, uri, kind, parent_uri, observed_at, pseudonym, deleted_at, *_ in loaded
    ]
    resolved = resolve_cascade(rows, as_of)
    id_by_uri = {uri: int(ident) for ident, uri, *_ in loaded}
    changes = _changed_events(loaded, resolved, id_by_uri)
    if changes:
        # NOWAIT: an event row locked by an open collector batch (a tombstone) fails at once
        # with 55P03 instead of waiting, so enrich can never deadlock with the collector, whose
        # dirty-marking UPDATE may already be waiting for this transaction's cascade lock.
        connection.execute(
            select(Event.id)
            .where(Event.id.in_(sorted(c["b_id"] for c in changes)))
            .with_for_update(nowait=True)
        ).all()
        connection.execute(_UPDATE_EVENT, changes)
    values = _cascade_values(resolved, as_of, locked)
    cascade_changed = any(locked[name] != value for name, value in values.items())
    if cascade_changed:
        connection.execute(update(Cascade).where(Cascade.id == cascade_id).values(**values))
    return _Outcome(resolved, len(changes), cascade_changed)


def _changed_events(
    loaded: Sequence[Any], resolved: ResolvedCascade, id_by_uri: Mapping[str, int]
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for ident, uri, *_rest, parent_event_id, parent_state, depth in loaded:
        node = resolved.nodes[uri]
        new_parent = None if node.parent is None else id_by_uri[node.parent]
        if (parent_event_id, parent_state, depth) != (new_parent, node.state, node.depth):
            changes.append(
                {
                    "b_id": ident,
                    "b_parent": new_parent,
                    "b_state": node.state,
                    "b_depth": node.depth,
                }
            )
    return changes


def _is_contention(exc: DBAPIError) -> bool:
    return getattr(exc.orig, "sqlstate", None) in _CONTENTION_SQLSTATES


def _process(engine: Engine, cascade_id: int, as_of: datetime, tally: _Tally) -> None:
    try:
        with engine.begin() as connection:
            outcome = _enrich_one(connection, cascade_id, as_of)
    except DBAPIError as exc:
        if not _is_contention(exc):
            raise
        tally.errors[type(exc.orig).__name__] += 1
        return
    except SQLAlchemyError:
        raise
    except Exception as exc:  # one malformed cascade never stops the run; it stays dirty
        tally.errors[type(exc).__name__] += 1
        return
    if outcome is None:
        tally.skipped_locked += 1
        return
    rollup = outcome.resolved.rollup
    tally.enriched += 1
    tally.rows_updated += outcome.rows_updated
    tally.cascades_updated += int(outcome.cascade_updated)
    tally.orphans += rollup.orphan_count
    tally.disconnected += rollup.disconnected_count
    tally.invalid += outcome.resolved.invalid_count
    tally.order_violations += rollup.order_violation_count


def enrich_dirty(
    engine: Engine,
    *,
    as_of: datetime | None = None,
    max_cascades: int = DEFAULT_MAX_CASCADES,
    force: bool = False,
) -> EnrichResult:
    """Enrich the dirty cascades (see the module docstring); returns counts only."""
    if max_cascades <= 0:
        raise ValueError("max_cascades must be positive")
    if as_of is not None and (as_of.tzinfo is None or as_of.utcoffset() is None):
        raise ValueError("as_of must be timezone-aware")
    with engine.connect() as lock_connection:
        if not try_advisory_lock(lock_connection, ENRICH_LOCK_KEY):
            logger.info("enrich status=locked")
            return EnrichResult(locked=True)
        try:
            result = _run(engine, lock_connection, as_of, max_cascades, force)
        finally:
            release_advisory_lock(lock_connection, ENRICH_LOCK_KEY)
    logger.info(result.line())
    return result


def _run(
    engine: Engine,
    lock_connection: Connection,
    as_of: datetime | None,
    max_cascades: int,
    force: bool,
) -> EnrichResult:
    effective = default_as_of(lock_connection) if as_of is None else as_of
    if effective is None:
        lock_connection.commit()
        return EnrichResult()
    effective = effective.astimezone(UTC)
    work = select_work(lock_connection, max_cascades=max_cascades, force=force)
    lock_connection.commit()
    tally = _Tally()
    for cascade_id in work:
        _process(engine, cascade_id, effective, tally)
    return EnrichResult(
        as_of=effective,
        selected=len(work),
        enriched=tally.enriched,
        skipped_locked=tally.skipped_locked,
        cascades_updated=tally.cascades_updated,
        rows_updated=tally.rows_updated,
        orphans=tally.orphans,
        disconnected=tally.disconnected,
        invalid=tally.invalid,
        order_violations=tally.order_violations,
        errors=dict(sorted(tally.errors.items())),
    )
