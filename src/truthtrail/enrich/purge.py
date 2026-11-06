"""The retention purge (D-16, D-18, OD-1; RESEARCH "Privacy, Retention and Storage", Pattern 5).

``purge(engine, policy, as_of=..., max_seconds=...)`` enforces the ratified retention policy.
Every window comes from the ``Policy`` object (D-03), so changing a retention number is a policy
edit only; nothing here hard-codes an owner-decision value:

======================  =========================================================================
Policy field            Pass (in this order)
======================  =========================================================================
retention_text_days     ``text``: root text is set NULL and ``text_purged_at`` = ``as_of`` once
                        the root's ``observed_at`` is that many days old (0 purges any text at
                        once, the RT-1 case)
retention_tombstone...  ``tombstones``: tombstone rows of every edge kind, roots included, are
                        hard-deleted that many days after ``deleted_at``; the touched cascades
                        are marked dirty in the same transaction so the next enrich turns their
                        children into honest orphans (the parent row is gone; nothing is
                        re-parented). A deleted root's cascade keeps ``root_deleted_at`` and so
                        stays hidden from the feed until the cascade window removes it
retention_dormant_days  ``dormant``: only when positive, cascades with no non-root event are
                        removed that many days after ``first_event_at`` (0 disables the pass)
retention_cascade_days  ``cascades``: whole cascades are deleted that many days after
                        ``first_event_at``; their events go with them through the foreign key
(none)                  ``claims``: ``social_link`` claims that no cascade and no event
                        references (for example the claim a root delete unlinked)
retention_news_days     ``news_claims`` (``news_headline`` claims by ``created_at``) and
                        ``news_fetches`` (the quota ledger, by ``called_at``)
(none)                  ``accounts``: pseudonymous accounts without any event
retention_cascade_days  ``ingest_runs``: run rows (counts only) by ``started_at``
======================  =========================================================================

All cutoffs are computed from the explicit ``as_of`` minus integer days and bound as parameters;
no statement calls ``now()``, so a test fixes time. The CLI's default ``as_of`` is the wall
clock, not the stream time: retention is a privacy promise in real time and must keep running
when ingestion stops.

Every pass is idempotent and batched: one transaction per batch selects at most ``batch`` ids
(``ORDER BY id LIMIT ... FOR UPDATE SKIP LOCKED``, so a row a concurrent writer holds is left for
the next run) and changes exactly those; the loop ends when a batch comes back short or the
``max_seconds`` deadline (a monotonic clock) passes, in which case the result says
``complete=False`` and a rerun finishes the work. ``dry_run`` runs the same selections as counts
and changes nothing (each pass is counted against the current data, so the counts of the later
passes are lower bounds). The purge takes its own advisory lock; another purge gets ``locked``.
It logs one line of counts and never an identifier.

Scheduling note: the D-10 pipeline runs collect, enrich and purge one after another. Row locks
and SKIP LOCKED keep a concurrent run safe for events and cascades; the claims and accounts
passes test "unreferenced" against the statement's snapshot, so they are meant to run while no
collector batch is open (Phase 6 schedules them sequentially).
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.sql.elements import TextClause

from truthtrail.core.policy import Policy
from truthtrail.db.locks import PURGE_LOCK_KEY, release_advisory_lock, try_advisory_lock

logger = logging.getLogger(__name__)

DEFAULT_BATCH_ROWS = 1000
# A cascade can hold up to TRACK_MAX_EVENTS_PER_CASCADE events, all deleted with it.
DEFAULT_BATCH_CASCADES = 50
DEFAULT_MAX_SECONDS = 120.0

# Seam for tests (the deadline clock); never the wall clock.
_monotonic: Callable[[], float] = time.monotonic


@dataclass(frozen=True)
class _Pass:
    """One pass: the id selection (batched, ``FOR UPDATE SKIP LOCKED``) and its dry-run count
    are literal statements with bound parameters (``:cutoff``, ``:n``), never composed SQL."""

    name: str
    select_ids: TextClause
    count: TextClause
    days: Callable[[Policy], int] | None  # the retention window, None when the pass has none
    enabled: Callable[[Policy], bool]
    delete: TextClause | None = None  # the per-batch DELETE by id (None: text and tombstones)
    cascades: bool = False  # batches of cascades (fewer per batch, their events counted too)
    events_of_matching: TextClause | None = None  # dry run: events of the matching cascades


def _always(_policy: Policy) -> bool:
    return True


def _dormant_enabled(policy: Policy) -> bool:
    return policy.retention_dormant_days > 0


_DELETE_CASCADES = text("DELETE FROM cascades WHERE id = ANY(CAST(:ids AS bigint[]))")
_DELETE_CLAIMS = text("DELETE FROM claims WHERE id = ANY(CAST(:ids AS bigint[]))")

_PASSES = (
    _Pass(
        "text",
        text(
            "SELECT t.id FROM events t WHERE t.edge_kind = 'root' AND t.text IS NOT NULL"
            " AND t.observed_at <= :cutoff ORDER BY t.id LIMIT :n FOR UPDATE OF t SKIP LOCKED"
        ),
        text(
            "SELECT count(*) FROM events t WHERE t.edge_kind = 'root' AND t.text IS NOT NULL"
            " AND t.observed_at <= :cutoff"
        ),
        lambda p: p.retention_text_days,
        _always,
    ),
    _Pass(
        "tombstones",
        text(
            "SELECT t.id FROM events t WHERE t.deleted_at IS NOT NULL AND t.deleted_at <= :cutoff"
            " ORDER BY t.id LIMIT :n FOR UPDATE OF t SKIP LOCKED"
        ),
        text(
            "SELECT count(*) FROM events t WHERE t.deleted_at IS NOT NULL"
            " AND t.deleted_at <= :cutoff"
        ),
        lambda p: p.retention_tombstone_days,
        _always,
    ),
    _Pass(
        "dormant",
        text(
            "SELECT t.id FROM cascades t WHERE t.first_event_at <= :cutoff AND NOT EXISTS"
            " (SELECT 1 FROM events e WHERE e.cascade_id = t.id AND e.edge_kind <> 'root')"
            " ORDER BY t.id LIMIT :n FOR UPDATE OF t SKIP LOCKED"
        ),
        text(
            "SELECT count(*) FROM cascades t WHERE t.first_event_at <= :cutoff AND NOT EXISTS"
            " (SELECT 1 FROM events e WHERE e.cascade_id = t.id AND e.edge_kind <> 'root')"
        ),
        lambda p: p.retention_dormant_days,
        _dormant_enabled,
        delete=_DELETE_CASCADES,
        cascades=True,
        events_of_matching=text(
            "SELECT count(*) FROM events x WHERE x.cascade_id IN (SELECT t.id FROM cascades t"
            " WHERE t.first_event_at <= :cutoff AND NOT EXISTS (SELECT 1 FROM events e"
            " WHERE e.cascade_id = t.id AND e.edge_kind <> 'root'))"
        ),
    ),
    _Pass(
        "cascades",
        text(
            "SELECT t.id FROM cascades t WHERE t.first_event_at <= :cutoff"
            " ORDER BY t.id LIMIT :n FOR UPDATE OF t SKIP LOCKED"
        ),
        text("SELECT count(*) FROM cascades t WHERE t.first_event_at <= :cutoff"),
        lambda p: p.retention_cascade_days,
        _always,
        delete=_DELETE_CASCADES,
        cascades=True,
        events_of_matching=text(
            "SELECT count(*) FROM events x WHERE x.cascade_id IN"
            " (SELECT t.id FROM cascades t WHERE t.first_event_at <= :cutoff)"
        ),
    ),
    _Pass(
        "claims",
        text(
            "SELECT t.id FROM claims t WHERE t.kind = 'social_link'"
            " AND t.id NOT IN (SELECT claim_id FROM cascades WHERE claim_id IS NOT NULL)"
            " AND t.id NOT IN (SELECT claim_id FROM events WHERE claim_id IS NOT NULL)"
            " ORDER BY t.id LIMIT :n FOR UPDATE OF t SKIP LOCKED"
        ),
        text(
            "SELECT count(*) FROM claims t WHERE t.kind = 'social_link'"
            " AND t.id NOT IN (SELECT claim_id FROM cascades WHERE claim_id IS NOT NULL)"
            " AND t.id NOT IN (SELECT claim_id FROM events WHERE claim_id IS NOT NULL)"
        ),
        None,
        _always,
        delete=_DELETE_CLAIMS,
    ),
    _Pass(
        "news_claims",
        text(
            "SELECT t.id FROM claims t WHERE t.kind = 'news_headline' AND t.created_at <= :cutoff"
            " ORDER BY t.id LIMIT :n FOR UPDATE OF t SKIP LOCKED"
        ),
        text(
            "SELECT count(*) FROM claims t WHERE t.kind = 'news_headline'"
            " AND t.created_at <= :cutoff"
        ),
        lambda p: p.retention_news_days,
        _always,
        delete=_DELETE_CLAIMS,
    ),
    _Pass(
        "news_fetches",
        text(
            "SELECT t.id FROM news_fetches t WHERE t.called_at <= :cutoff"
            " ORDER BY t.id LIMIT :n FOR UPDATE OF t SKIP LOCKED"
        ),
        text("SELECT count(*) FROM news_fetches t WHERE t.called_at <= :cutoff"),
        lambda p: p.retention_news_days,
        _always,
        delete=text("DELETE FROM news_fetches WHERE id = ANY(CAST(:ids AS bigint[]))"),
    ),
    _Pass(
        "accounts",
        text(
            "SELECT t.id FROM accounts t"
            " WHERE t.id NOT IN (SELECT account_id FROM events WHERE account_id IS NOT NULL)"
            " ORDER BY t.id LIMIT :n FOR UPDATE OF t SKIP LOCKED"
        ),
        text(
            "SELECT count(*) FROM accounts t"
            " WHERE t.id NOT IN (SELECT account_id FROM events WHERE account_id IS NOT NULL)"
        ),
        None,
        _always,
        delete=text("DELETE FROM accounts WHERE id = ANY(CAST(:ids AS bigint[]))"),
    ),
    _Pass(
        "ingest_runs",
        text(
            "SELECT t.id FROM ingest_runs t WHERE t.started_at <= :cutoff"
            " ORDER BY t.id LIMIT :n FOR UPDATE OF t SKIP LOCKED"
        ),
        text("SELECT count(*) FROM ingest_runs t WHERE t.started_at <= :cutoff"),
        lambda p: p.retention_cascade_days,
        _always,
        delete=text("DELETE FROM ingest_runs WHERE id = ANY(CAST(:ids AS bigint[]))"),
    ),
)
PASS_NAMES = tuple(spec.name for spec in _PASSES)

_PURGE_TEXT = text(
    "UPDATE events SET text = NULL, text_purged_at = :at WHERE id = ANY(CAST(:ids AS bigint[]))"
)
_DELETE_EVENTS = text(
    "DELETE FROM events WHERE id = ANY(CAST(:ids AS bigint[])) RETURNING cascade_id"
)
_MARK_DIRTY = text("UPDATE cascades SET enrich_dirty = true WHERE id = ANY(CAST(:ids AS bigint[]))")
_EVENTS_OF = text("SELECT count(*) FROM events WHERE cascade_id = ANY(CAST(:ids AS bigint[]))")
_DIRTY_OF_MATCHING = text(
    "SELECT count(DISTINCT t.cascade_id) FROM events t WHERE t.deleted_at IS NOT NULL"
    " AND t.deleted_at <= :cutoff AND t.cascade_id IS NOT NULL"
)


@dataclass(frozen=True)
class PurgeResult:
    """Counts per pass (no identifiers). ``locked``: another purge holds the lock;
    ``complete``: every pass ran to the end before the deadline."""

    locked: bool = False
    dry_run: bool = False
    complete: bool = True
    as_of: datetime | None = None
    counts: dict[str, int] = field(default_factory=dict)

    def line(self) -> str:
        if self.locked:
            return "purge status=locked"
        status = "dry_run" if self.dry_run else ("ok" if self.complete else "partial")
        counts = " ".join(f"{name}={count}" for name, count in self.counts.items())
        return f"purge status={status} {counts}".rstrip()


def _empty_counts() -> dict[str, int]:
    counts = dict.fromkeys(PASS_NAMES, 0)
    counts["cascade_events"] = 0
    counts["cascades_marked_dirty"] = 0
    return counts


def _params(spec: _Pass, policy: Policy, as_of: datetime) -> dict[str, Any]:
    if spec.days is None:
        return {}
    return {"cutoff": as_of - timedelta(days=spec.days(policy))}


def _apply_batch(
    connection: Connection, spec: _Pass, ids: list[int], as_of: datetime, counts: dict[str, int]
) -> None:
    bound = {"ids": ids}
    if spec.name == "text":
        connection.execute(_PURGE_TEXT, {**bound, "at": as_of})
    elif spec.name == "tombstones":
        touched = {c for (c,) in connection.execute(_DELETE_EVENTS, bound) if c is not None}
        if touched:
            connection.execute(_MARK_DIRTY, {"ids": sorted(touched)})
        counts["cascades_marked_dirty"] += len(touched)
    elif spec.delete is not None:
        if spec.cascades:
            counts["cascade_events"] += int(connection.execute(_EVENTS_OF, bound).scalar_one())
        connection.execute(spec.delete, bound)
    counts[spec.name] += len(ids)


def _run_pass(
    engine: Engine,
    spec: _Pass,
    params: dict[str, Any],
    *,
    as_of: datetime,
    batch: int,
    deadline: float,
    counts: dict[str, int],
) -> bool:
    """Loop one pass in batches; False when the deadline stopped it before the end."""
    while True:
        if _monotonic() >= deadline:
            return False
        with engine.begin() as connection:
            found = connection.execute(spec.select_ids, {**params, "n": batch}).scalars()
            ids = [int(i) for i in found]
            if ids:
                _apply_batch(connection, spec, ids, as_of, counts)
        if len(ids) < batch:
            return True


def _count_pass(
    connection: Connection, spec: _Pass, params: dict[str, Any], counts: dict[str, int]
) -> None:
    counts[spec.name] = int(connection.execute(spec.count, params).scalar_one())
    if spec.events_of_matching is not None:
        events = connection.execute(spec.events_of_matching, params).scalar_one()
        counts["cascade_events"] += int(events)
    if spec.name == "tombstones":
        dirty = connection.execute(_DIRTY_OF_MATCHING, params).scalar_one()
        counts["cascades_marked_dirty"] = int(dirty)


def purge(
    engine: Engine,
    policy: Policy,
    *,
    as_of: datetime,
    max_seconds: float = DEFAULT_MAX_SECONDS,
    dry_run: bool = False,
    batch_rows: int = DEFAULT_BATCH_ROWS,
    batch_cascades: int = DEFAULT_BATCH_CASCADES,
) -> PurgeResult:
    """Run every retention pass once (see the module docstring); returns counts only."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    if max_seconds <= 0 or batch_rows <= 0 or batch_cascades <= 0:
        raise ValueError("max_seconds and the batch sizes must be positive")
    as_of = as_of.astimezone(UTC)
    with engine.connect() as lock_connection:
        if not try_advisory_lock(lock_connection, PURGE_LOCK_KEY):
            logger.info("purge status=locked")
            return PurgeResult(locked=True)
        try:
            result = _purge_locked(
                engine,
                lock_connection,
                policy,
                as_of,
                max_seconds,
                dry_run,
                batch_rows,
                batch_cascades,
            )
        finally:
            release_advisory_lock(lock_connection, PURGE_LOCK_KEY)
    logger.info(result.line())
    return result


def _purge_locked(
    engine: Engine,
    lock_connection: Connection,
    policy: Policy,
    as_of: datetime,
    max_seconds: float,
    dry_run: bool,
    batch_rows: int,
    batch_cascades: int,
) -> PurgeResult:
    counts = _empty_counts()
    active = [spec for spec in _PASSES if spec.enabled(policy)]
    if dry_run:
        for spec in active:
            _count_pass(lock_connection, spec, _params(spec, policy, as_of), counts)
        lock_connection.commit()
        return PurgeResult(dry_run=True, as_of=as_of, counts=counts)
    deadline = _monotonic() + max_seconds
    complete = True
    for spec in active:
        batch = batch_cascades if spec.cascades else batch_rows
        finished = _run_pass(
            engine,
            spec,
            _params(spec, policy, as_of),
            as_of=as_of,
            batch=batch,
            deadline=deadline,
            counts=counts,
        )
        if not finished:
            complete = False
            break
    return PurgeResult(complete=complete, as_of=as_of, counts=counts)
