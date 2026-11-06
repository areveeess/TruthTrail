"""``GET /v1/stats``: global counts from the cascade rollups and the run log (D-23, D-24, F-17).

Every number comes from one aggregate statement over ``cascades`` plus two small statements over
``ingest_runs`` (the checkpoint is read by the provenance block); the ``events`` table is never
scanned, so the cost is O(cascades) and cacheable. ``events_by_kind.root`` is the number of
non-deleted roots (``event_count`` minus the child counts, summed), so the four kinds add up to
``events_total``. ``ingest_lag_seconds`` is the app clock minus ``data_as_of`` (never negative),
computed per request and never cached. The counts describe an observed subset of public Bluesky
posts, to flag for human review; they are never a verdict.
"""

import math
from datetime import datetime
from typing import Any

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from truthtrail.api.limits import LimitedRouter
from truthtrail.api.problems import V1_PROBLEM_RESPONSES
from truthtrail.api.v1_cache import STATS_TTL_SECONDS, V1Cache
from truthtrail.api.v1_deps import as_utc, build_meta, data_version, read_connection
from truthtrail.db.models import Cascade, IngestRun
from truthtrail.schemas.v1 import CAPTION, EventKindTotals, LastRun, StatsResponse


def _sum(column: Any) -> Any:
    return func.coalesce(func.sum(column), 0)


_ROLLUP = select(
    func.count(),
    func.count().filter(Cascade.root_deleted_at.is_not(None)),
    _sum(Cascade.event_count),
    _sum(Cascade.reply_count),
    _sum(Cascade.quote_count),
    _sum(Cascade.repost_count),
    _sum(Cascade.orphan_count),
    _sum(Cascade.disconnected_count),
    _sum(Cascade.deleted_count),
    func.min(Cascade.first_event_at),
).select_from(Cascade)
_GAPS = select(_sum(IngestRun.gap_count))
_LAST_RUN = (
    select(IngestRun.status, IngestRun.mode, IngestRun.started_at, IngestRun.finished_at)
    .order_by(IngestRun.started_at.desc(), IngestRun.id.desc())
    .limit(1)
)


def _stats(connection: Connection) -> dict[str, Any]:
    (
        cascades,
        deleted_roots,
        events,
        replies,
        quotes,
        reposts,
        orphans,
        disconnected,
        deleted,
        earliest,
    ) = connection.execute(_ROLLUP).one()
    gaps = int(connection.execute(_GAPS).scalar_one())
    run = connection.execute(_LAST_RUN).one_or_none()
    last_run = None
    if run is not None:
        last_run = LastRun(
            status=run.status,
            mode=run.mode,
            started_at=as_utc(run.started_at),
            finished_at=None if run.finished_at is None else as_utc(run.finished_at),
        )
    return {
        "cascades_total": int(cascades),
        "cascades_with_deleted_root": int(deleted_roots),
        "events_by_kind": EventKindTotals(
            root=int(events) - int(replies) - int(quotes) - int(reposts),
            reply=int(replies),
            quote=int(quotes),
            repost=int(reposts),
        ),
        "events_total": int(events),
        "orphans_total": int(orphans),
        "disconnected_total": int(disconnected),
        "deleted_total": int(deleted),
        "observed_since": None if earliest is None else as_utc(earliest),
        "ingest_gaps_total": gaps,
        "last_run": last_run,
    }


def ingest_lag_seconds(now: datetime, data_as_of: datetime | None) -> int | None:
    """Whole seconds from ``data_as_of`` to ``now`` (never negative); None before any ingest."""
    if data_as_of is None:
        return None
    return max(0, math.floor((now - data_as_of).total_seconds()))


def register_stats(router: LimitedRouter) -> None:
    """Add ``GET /stats``."""

    @router.get(
        "/stats",
        response_model=StatsResponse,
        responses=V1_PROBLEM_RESPONSES,
        summary="Global counts of the stored cascades, to flag for human review",
        description=(
            CAPTION + " Totals per edge kind, orphan, disconnected and deleted totals, "
            "observed_since, ingest lag, recorded gaps and the last collector run, computed "
            "from the cascade rollups and the run log."
        ),
    )
    def get_stats(request: Request) -> StatsResponse:
        """Global counts."""
        with read_connection(request) as connection:
            key = ("stats", data_version(connection))
            cache: V1Cache = request.app.state.v1_cache
            payload = cache.get_or_compute(key, STATS_TTL_SECONDS, lambda: _stats(connection))
            meta = build_meta(connection, request, observed_since=payload["observed_since"])
        lag = ingest_lag_seconds(request.app.state.clock(), meta.data_as_of)
        return StatsResponse(**payload, ingest_lag_seconds=lag, meta=meta)
