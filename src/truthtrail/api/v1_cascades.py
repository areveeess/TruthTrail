"""``/v1/cascades``: the list, the detail, the tree and the timeline (D-12, D-14, D-23, D-24).

Every handler is a sync ``def`` on the ``LimitedRouter`` (rate limited by construction), opens a
short-lived read-only connection inside its body (``read_connection``, after the limiter), builds
Core statements with bound parameters only, caches the payload WITHOUT the provenance block under
a key that includes the data version, and builds the meta fresh. Nothing here is a verdict: the
cascades are an observed subset of public Bluesky posts to flag for human review.

List (keyset pagination). The cursor is the base64url form (no padding) of the JSON array
``[sort, value, id]``: ``sort`` is ``recent`` or ``velocity``, ``value`` the integer
microseconds of ``last_event_at`` (recent) or ``events_1h`` (velocity), ``id`` the cascade id.
It is decoded and type-checked by an ``AfterValidator`` (a malformed cursor is the existing 422
problem+json with ``loc ["query", "cursor"]`` and never echoes the value); a cursor of another
sort is a 422 too. The timestamp bound is rebuilt exactly from integer microseconds, and the
predicate compares the row tuple ``(key, id)`` with it, descending on both, fetching one extra
row to know whether a next page exists. The ``claim_id`` filter follows the ratified merge policy
(D-03, OD-2): under ``none`` a request carrying it is a 422; the parameter stays declared either
way so the generated client never depends on a runtime setting.

Deleted roots (D-16): a cascade whose root was deleted is hidden unless ``include_deleted_roots``
is true, always carries ``claim`` null (even if a row was written another way) and never matches
the ``claim_id`` filter.

Tree (D-12, D-14, RESEARCH F-16): the cascade's events in ``core.cascade.order_events`` order
(``observed_at``, then depth, ties by the keyed uri) with resolved parents only. The optional
``kinds`` filter keeps the root; dropping a kind detaches the subtrees below it. The list is
capped at ``MAX_TREE_NODES``; a prefix of the canonical order is closed under ancestors unless
some event was observed before its parent, so ``links_may_be_missing`` is set when a truncated
tree has such a violation. Edges join two shown nodes only; ``roots`` lists the root and every
shown node without a shown parent (``detached`` true). Reposts are inferred fan-out leaves of
their subject, and nothing says who saw a post from whom. A node shows at most 8 characters of
its account pseudonym, and none for a tombstone.

Timeline (D-23, RESEARCH F-15): the bucket size is the smallest of 60 s, 5 min, 15 min, 1 h, 6 h
and 1 day that gives at most ``MAX_TIMELINE_BUCKETS`` buckets over the span of the non-deleted
events, else the span divided by (maximum minus one), rounded up. Buckets come from
``date_bin(:stride, observed_at, :origin)`` with the origin the earliest non-deleted event (the
session time zone cannot change them; ``date_trunc`` and ``extract`` are never used) and are
filled densely in Python. Tombstones are not counted.

Unknown cascade ids are the generic router 404 (problem+json, ``http_error``), deliberately not
declared in OpenAPI, exactly like an unknown path.
"""

import base64
import binascii
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import HTTPException, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import AfterValidator
from sqlalchemy import DateTime, Select, and_, bindparam, func, select, tuple_
from sqlalchemy.engine import Connection, Row

from truthtrail.api.limits import LimitedRouter
from truthtrail.api.problems import V1_PROBLEM_RESPONSES
from truthtrail.api.v1_cache import (
    DETAIL_TTL_SECONDS,
    LIST_TTL_SECONDS,
    TIMELINE_TTL_SECONDS,
    TREE_TTL_SECONDS,
    V1Cache,
)
from truthtrail.api.v1_deps import (
    as_utc,
    build_meta,
    data_version,
    datetime_from_us,
    read_connection,
    us_from_datetime,
)
from truthtrail.core.cascade import CascadeError, CascadeEvent, find_order_violations, order_events
from truthtrail.core.policy import get_policy
from truthtrail.db.models import Account, Cascade, Claim, Event, IngestRun
from truthtrail.schemas.v1 import (
    ACCOUNT_PREFIX_LENGTH,
    CAPTION,
    CascadeDetail,
    CascadePage,
    CascadeResponse,
    CascadeSort,
    CascadeSummary,
    ChildKind,
    ClaimSummary,
    EdgeKindCounts,
    TimelineBucket,
    TimelineResponse,
    TreeEdge,
    TreeNode,
    TreeResponse,
    TreeRoot,
)

MAX_ID = 2**63 - 1
MAX_COUNT = 2**31 - 1
# 9999-12-31T23:59:59.999999Z, the largest instant a datetime can hold.
MAX_CURSOR_US = 253_402_300_799_999_999
MAX_CURSOR_LENGTH = 200
_CURSOR_ALPHABET = re.compile(r"[A-Za-z0-9_-]+")
SORTS = ("recent", "velocity")
BUCKET_LADDER_SECONDS = (60, 300, 900, 3600, 21_600, 86_400)
_US = 1_000_000

_ROOT = Event.__table__.alias("root_event")


# --- Cursor ------------------------------------------------------------------------------------
def encode_cursor(sort: str, value: int, cascade_id: int) -> str:
    """The opaque cursor of the position ``(value, cascade_id)`` under ``sort``."""
    raw = json.dumps([sort, value, cascade_id], separators=(",", ":")).encode("ascii")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def decode_cursor(raw: str) -> tuple[str, int, int]:
    """Decode and type-check a cursor; ``ValueError`` (fixed text, no echo) when malformed."""
    if not raw or len(raw) > MAX_CURSOR_LENGTH or not _CURSOR_ALPHABET.fullmatch(raw):
        raise ValueError("malformed cursor")
    try:
        decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        value = json.loads(decoded.decode("utf-8"))
    except (binascii.Error, ValueError):
        raise ValueError("malformed cursor") from None
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("malformed cursor")
    sort, key, cascade_id = value
    if sort not in SORTS or not _is_int(key) or not _is_int(cascade_id):
        raise ValueError("malformed cursor")
    limit = MAX_CURSOR_US if sort == "recent" else MAX_COUNT
    if not 0 <= key <= limit or not 1 <= cascade_id <= MAX_ID:
        raise ValueError("malformed cursor")
    return str(sort), int(key), int(cascade_id)


def _check_cursor(raw: str | None) -> str | None:
    if raw is not None:
        decode_cursor(raw)
    return raw


def _invalid(field: str, message: str) -> RequestValidationError:
    """The existing 422 problem+json for one query parameter (the value is never echoed)."""
    return RequestValidationError(
        [{"loc": ("query", field), "msg": message, "type": "value_error"}]
    )


# --- Shared row mapping ------------------------------------------------------------------------
def _summary_select() -> Select[*tuple[Any, ...]]:
    return (
        select(
            Cascade.id,
            Cascade.first_event_at,
            Cascade.last_event_at,
            Cascade.tracking_ends_at,
            Cascade.event_count,
            Cascade.reply_count,
            Cascade.quote_count,
            Cascade.repost_count,
            Cascade.unique_accounts,
            Cascade.max_depth,
            Cascade.events_1h,
            Cascade.orphan_count,
            Cascade.disconnected_count,
            Cascade.overflow_count,
            Cascade.deleted_count,
            Cascade.order_violation_count,
            Cascade.root_deleted_at,
            Cascade.enrich_dirty,
            Cascade.rolled_up_at,
            Claim.id.label("claim_pk"),
            Claim.kind.label("claim_kind"),
            Claim.text.label("claim_title"),
            Claim.url_canonical,
            Claim.link_domain,
            Claim.source_name,
            Claim.published_at,
            _ROOT.c.observed_at.label("root_observed_at"),
            _ROOT.c.text.label("root_text"),
            _ROOT.c.text_purged_at.label("root_text_purged_at"),
            _ROOT.c.deleted_at.label("root_row_deleted_at"),
        )
        .select_from(Cascade)
        .outerjoin(Claim, Claim.id == Cascade.claim_id)
        .outerjoin(_ROOT, and_(_ROOT.c.uri == Cascade.root_uri, _ROOT.c.cascade_id == Cascade.id))
    )


def _observed_since(row: Row[Any]) -> datetime:
    return as_utc(row.root_observed_at if row.root_observed_at is not None else row.first_event_at)


def _summary_fields(row: Row[Any]) -> dict[str, Any]:
    root_deleted = row.root_deleted_at is not None or row.root_row_deleted_at is not None
    claim = None
    if row.claim_pk is not None and not root_deleted:
        claim = ClaimSummary(
            claim_id=row.claim_pk,
            kind=row.claim_kind,
            title=row.claim_title,
            url_canonical=row.url_canonical,
            link_domain=row.link_domain,
            source_name=row.source_name,
            published_at=None if row.published_at is None else as_utc(row.published_at),
        )
    return {
        "cascade_id": row.id,
        "observed_since": _observed_since(row),
        "last_event_at": as_utc(row.last_event_at),
        "tracking_ends_at": as_utc(row.tracking_ends_at),
        "event_count": row.event_count,
        "reply_count": row.reply_count,
        "quote_count": row.quote_count,
        "repost_count": row.repost_count,
        "unique_accounts": row.unique_accounts,
        "max_depth": row.max_depth,
        "events_1h": row.events_1h,
        "orphan_count": row.orphan_count,
        "disconnected_count": row.disconnected_count,
        "overflow_count": row.overflow_count,
        "deleted_count": row.deleted_count,
        "order_violation_count": row.order_violation_count,
        "root_deleted": root_deleted,
        "claim": claim,
        "root_text": None if root_deleted else row.root_text,
        "text_purged": row.root_text_purged_at is not None,
        "enrich_pending": bool(row.enrich_dirty),
        "rolled_up_at": None if row.rolled_up_at is None else as_utc(row.rolled_up_at),
    }


def _cache(request: Request) -> V1Cache:
    cache: V1Cache = request.app.state.v1_cache
    return cache


def _cascade_or_404(connection: Connection, cascade_id: int) -> Row[Any]:
    row = connection.execute(_summary_select().where(Cascade.id == cascade_id)).one_or_none()
    if row is None:
        raise HTTPException(status_code=404)
    return row


# --- List --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class _ListQuery:
    sort: str
    limit: int
    position: tuple[int, int] | None
    claim_id: int | None
    min_events: int | None
    has_orphans: bool | None
    include_deleted_roots: bool


def _page(connection: Connection, q: _ListQuery) -> tuple[list[CascadeSummary], str | None]:
    key = Cascade.last_event_at if q.sort == "recent" else Cascade.events_1h
    statement = _summary_select()
    if not q.include_deleted_roots:
        statement = statement.where(Cascade.root_deleted_at.is_(None))
    if q.claim_id is not None:
        statement = statement.where(
            Cascade.claim_id == q.claim_id, Cascade.root_deleted_at.is_(None)
        )
    if q.min_events is not None:
        statement = statement.where(Cascade.event_count >= q.min_events)
    if q.has_orphans is True:
        statement = statement.where(Cascade.orphan_count > 0)
    elif q.has_orphans is False:
        statement = statement.where(Cascade.orphan_count == 0)
    if q.position is not None:
        value, cascade_id = q.position
        bound: datetime | int = datetime_from_us(value) if q.sort == "recent" else value
        statement = statement.where(tuple_(key, Cascade.id) < tuple_(bound, cascade_id))
    statement = statement.order_by(key.desc(), Cascade.id.desc()).limit(q.limit + 1)
    rows = connection.execute(statement).all()
    items = [CascadeSummary(**_summary_fields(row)) for row in rows[: q.limit]]
    next_cursor = None
    if len(rows) > q.limit:
        last = rows[q.limit - 1]
        value = us_from_datetime(last.last_event_at) if q.sort == "recent" else last.events_1h
        next_cursor = encode_cursor(q.sort, int(value), int(last.id))
    return items, next_cursor


# --- Detail ------------------------------------------------------------------------------------
_INVALID_COUNT = select(func.count()).where(
    Event.cascade_id == bindparam("cascade_id"),
    Event.parent_state == "invalid",
    Event.deleted_at.is_(None),
)
_GAP_SPANS = select(IngestRun.gap_from_us, IngestRun.gap_to_us).where(
    IngestRun.gap_from_us.is_not(None), IngestRun.gap_to_us.is_not(None)
)


def count_overlapping_gaps(spans: Sequence[tuple[int, int]], start_us: int, end_us: int) -> int:
    """Gap spans (inclusive, integer microseconds) that overlap ``[start_us, end_us]``."""
    return sum(1 for low, high in spans if low <= end_us and high >= start_us)


def _detail(connection: Connection, cascade_id: int) -> CascadeDetail:
    row = _cascade_or_404(connection, cascade_id)
    fields = _summary_fields(row)
    invalid = int(connection.execute(_INVALID_COUNT, {"cascade_id": cascade_id}).scalar_one())
    spans = [
        (int(a), int(b))
        for a, b in connection.execute(_GAP_SPANS)
        if a is not None and b is not None
    ]
    # The tracked life: from the first stored event to the later of the last event and the end
    # of tracking (a gap after the last event can hide events that were never seen).
    start = us_from_datetime(row.first_event_at)
    end = us_from_datetime(max(row.last_event_at, row.tracking_ends_at))
    counts = EdgeKindCounts(
        root=row.event_count - row.reply_count - row.quote_count - row.repost_count,
        reply=row.reply_count,
        quote=row.quote_count,
        repost=row.repost_count,
        deleted=row.deleted_count,
    )
    return CascadeDetail(
        **fields,
        counts_by_kind=counts,
        invalid_count=invalid,
        ingest_gaps=count_overlapping_gaps(spans, start, end),
    )


# --- Tree --------------------------------------------------------------------------------------
_TREE_EVENTS = (
    select(
        Event.id,
        Event.uri,
        Event.edge_kind,
        Event.inferred,
        Event.parent_event_id,
        Event.parent_state,
        Event.observed_at,
        Event.depth,
        Event.deleted_at,
        Account.pseudonym,
    )
    .select_from(Event)
    .outerjoin(Account, Account.id == Event.account_id)
    .where(Event.cascade_id == bindparam("cascade_id"))
)


def canonical_tree_order(rows: Sequence[Any]) -> tuple[list[Any], dict[int, int], int]:
    """Rows in canonical order, each row's shown parent id, and the order-violation count.

    Only a ``resolved`` parent inside the cascade is a parent. ``order_events`` raises on a
    parent cycle, which enrich never writes; should one exist anyway, the rows are ordered by
    ``(observed_at, uri)`` with no links at all (every node detached), never an error.
    """
    by_id = {row.id: row for row in rows}
    parents = {
        row.id: row.parent_event_id
        for row in rows
        if row.parent_state == "resolved" and row.parent_event_id in by_id
    }
    by_uri = {row.uri: row for row in rows}
    events = [
        CascadeEvent(
            row.uri,
            by_id[parents[row.id]].uri if row.id in parents else None,
            as_utc(row.observed_at),
        )
        for row in rows
    ]
    try:
        ordered = [by_uri[e.event_id] for e in order_events(events)]
        violations = len(find_order_violations(events))
    except CascadeError:
        ordered = sorted(rows, key=lambda r: (as_utc(r.observed_at), r.uri))
        return ordered, {}, 1
    return ordered, parents, violations


def _tree(
    connection: Connection, cascade_id: int, kinds: frozenset[str] | None, cap: int
) -> dict[str, Any]:
    cascade = _cascade_or_404(connection, cascade_id)
    rows = connection.execute(_TREE_EVENTS, {"cascade_id": cascade_id}).all()
    ordered, parents, violations = canonical_tree_order(rows)
    if kinds is not None:
        ordered = [r for r in ordered if r.edge_kind == "root" or r.edge_kind in kinds]
    total = len(ordered)
    shown = ordered[:cap]
    shown_ids = {row.id for row in shown}
    nodes: list[TreeNode] = []
    edges: list[TreeEdge] = []
    roots: list[TreeRoot] = []
    for row in shown:
        deleted = row.deleted_at is not None
        account = None if deleted or row.pseudonym is None else row.pseudonym
        nodes.append(
            TreeNode(
                event_id=row.id,
                account=None if account is None else account[:ACCOUNT_PREFIX_LENGTH],
                edge_kind=row.edge_kind,
                inferred=row.inferred,
                parent_state=row.parent_state,
                observed_at=as_utc(row.observed_at),
                depth=row.depth,
                deleted=deleted,
            )
        )
        parent = parents.get(row.id)
        if parent is not None and parent in shown_ids:
            edges.append(
                TreeEdge(
                    parent_id=parent,
                    child_id=row.id,
                    edge_kind=row.edge_kind,
                    inferred=row.inferred,
                )
            )
        else:
            roots.append(TreeRoot(event_id=row.id, detached=row.edge_kind != "root"))
    truncated = len(shown) < total
    return {
        "cascade_id": cascade_id,
        "nodes": nodes,
        "edges": edges,
        "roots": roots,
        "shown": len(shown),
        "total": total,
        "truncated": truncated,
        "links_may_be_missing": truncated and violations > 0,
        "enrich_pending": bool(cascade.enrich_dirty),
        "observed_since": _observed_since(cascade),
    }


# --- Timeline ----------------------------------------------------------------------------------
_SPAN = select(func.min(Event.observed_at), func.max(Event.observed_at)).where(
    Event.cascade_id == bindparam("cascade_id"), Event.deleted_at.is_(None)
)
_BUCKET = func.date_bin(
    bindparam("stride"), Event.observed_at, bindparam("origin"), type_=DateTime(timezone=True)
).label("bucket")
_BUCKET_COUNTS = (
    select(_BUCKET, Event.edge_kind, func.count().label("n"))
    .where(Event.cascade_id == bindparam("cascade_id"), Event.deleted_at.is_(None))
    .group_by(_BUCKET, Event.edge_kind)
)


def choose_bucket_seconds(span_us: int, max_buckets: int) -> int:
    """The bucket width for a span of ``span_us`` microseconds (see the module docstring)."""
    if span_us < 0 or max_buckets < 1:
        raise ValueError("span must be non-negative and max_buckets positive")
    for size in BUCKET_LADDER_SECONDS:
        if span_us // (size * _US) + 1 <= max_buckets:
            return size
    if max_buckets == 1:
        return span_us // _US + 1
    return max(1, -(-span_us // ((max_buckets - 1) * _US)))


def _timeline(connection: Connection, cascade_id: int, max_buckets: int) -> dict[str, Any]:
    cascade = _cascade_or_404(connection, cascade_id)
    first, last = connection.execute(_SPAN, {"cascade_id": cascade_id}).one()
    payload: dict[str, Any] = {
        "cascade_id": cascade_id,
        "observed_since": _observed_since(cascade),
    }
    if first is None:
        return {
            **payload,
            "bucket_seconds": BUCKET_LADDER_SECONDS[0],
            "origin": None,
            "buckets": [],
        }
    origin = as_utc(first)
    span_us = us_from_datetime(last) - us_from_datetime(origin)
    size = choose_bucket_seconds(span_us, max_buckets)
    width = size * _US
    count = span_us // width + 1
    series: list[dict[str, int]] = [
        {"root": 0, "reply": 0, "quote": 0, "repost": 0} for _ in range(count)
    ]
    rows = connection.execute(
        _BUCKET_COUNTS,
        {"cascade_id": cascade_id, "stride": timedelta(seconds=size), "origin": origin},
    )
    origin_us = us_from_datetime(origin)
    for bucket, kind, n in rows:
        series[(us_from_datetime(bucket) - origin_us) // width][kind] += int(n)
    buckets = [
        TimelineBucket(start=origin + timedelta(seconds=size * index), **counts)
        for index, counts in enumerate(series)
    ]
    return {**payload, "bucket_seconds": size, "origin": origin, "buckets": buckets}


# --- Registrar ---------------------------------------------------------------------------------
CursorParam = Annotated[
    str | None,
    Query(
        max_length=MAX_CURSOR_LENGTH,
        description="Opaque next_cursor of the previous page; omit for the first page.",
    ),
    AfterValidator(_check_cursor),
]
CascadeIdParam = Annotated[int, Path(ge=1, le=MAX_ID, description="Id of the cascade.")]


def register_cascades(router: LimitedRouter) -> None:
    """Add the four cascade routes; the bounds come from the policy (D-03, D-23)."""
    policy = get_policy()

    @router.get(
        "/cascades",
        response_model=CascadePage,
        responses=V1_PROBLEM_RESPONSES,
        summary="List tracked cascades to flag for human review",
        description=(
            CAPTION + " Keyset-paginated tracked cascades with their completeness counts "
            "(orphans, disconnected, overflow, deleted, order violations). The list is a "
            "reading order for a human reviewer, not a verdict on any post."
        ),
    )
    def list_cascades(
        request: Request,
        cursor: CursorParam = None,
        limit: Annotated[
            int,
            Query(ge=1, le=policy.page_size_max, description="Page size."),
        ] = policy.page_size_default,
        sort: Annotated[
            CascadeSort,
            Query(description="recent: newest last_event_at first; velocity: most events_1h."),
        ] = "recent",
        claim_id: Annotated[
            int | None,
            Query(
                ge=1,
                le=MAX_ID,
                description=(
                    "Only cascades linking this claim (claim-level grouping). Rejected with "
                    "422 when the deployment's CASCADE_MERGE_POLICY is none."
                ),
            ),
        ] = None,
        min_events: Annotated[
            int | None,
            Query(ge=0, le=MAX_COUNT, description="Only cascades with at least this many events."),
        ] = None,
        has_orphans: Annotated[
            bool | None,
            Query(description="true: only cascades with orphans; false: only without."),
        ] = None,
        include_deleted_roots: Annotated[
            bool,
            Query(description="Include cascades whose root post was deleted (hidden by default)."),
        ] = False,
    ) -> CascadePage:
        """List tracked cascades in keyset order."""
        if claim_id is not None and request.app.state.policy.cascade_merge_policy == "none":
            raise _invalid(
                "claim_id", "claim_id is not available when CASCADE_MERGE_POLICY is none"
            )
        position = None
        if cursor is not None:
            cursor_sort, value, cascade_id = decode_cursor(cursor)
            if cursor_sort != sort:
                raise _invalid("cursor", "cursor was issued for another sort order")
            position = (value, cascade_id)
        query = _ListQuery(
            sort, limit, position, claim_id, min_events, has_orphans, include_deleted_roots
        )
        with read_connection(request) as connection:
            key = ("list", data_version(connection), query)
            items, next_cursor = _cache(request).get_or_compute(
                key, LIST_TTL_SECONDS, lambda: _page(connection, query)
            )
            meta = build_meta(connection, request)
        return CascadePage(items=items, next_cursor=next_cursor, limit=limit, sort=sort, meta=meta)

    @router.get(
        "/cascades/{cascade_id}",
        response_model=CascadeResponse,
        responses=V1_PROBLEM_RESPONSES,
        summary="One cascade with its completeness counts, to flag for human review",
        description=(
            CAPTION + " Summary of one cascade with observed_since, orphan, disconnected, "
            "overflow, order-violation, deleted and invalid counts, counts per edge kind and "
            "the ingest gaps overlapping its life. An unknown id is the generic 404."
        ),
    )
    def get_cascade(request: Request, cascade_id: CascadeIdParam) -> CascadeResponse:
        """One cascade."""
        with read_connection(request) as connection:
            key = ("detail", data_version(connection), cascade_id)
            detail = _cache(request).get_or_compute(
                key, DETAIL_TTL_SECONDS, lambda: _detail(connection, cascade_id)
            )
            meta = build_meta(connection, request, observed_since=detail.observed_since)
        return CascadeResponse(cascade=detail, meta=meta)

    @router.get(
        "/cascades/{cascade_id}/tree",
        response_model=TreeResponse,
        responses=V1_PROBLEM_RESPONSES,
        summary="The cascade tree in canonical order, capped, to flag for human review",
        description=(
            CAPTION + " Nodes, edges and roots in canonical order, capped at "
            f"{policy.max_tree_nodes} nodes (shown, total and truncated say 'showing N of M'). "
            "Orphan subtrees are detached roots; reposts are inferred fan-out leaves and say "
            "nothing about who saw a post from whom."
        ),
    )
    def get_cascade_tree(
        request: Request,
        cascade_id: CascadeIdParam,
        kinds: Annotated[
            list[ChildKind] | None,
            Query(
                description=(
                    "Edge kinds to include (repeatable); the root is always kept. Leaving a "
                    "kind out detaches the subtrees below it."
                )
            ),
        ] = None,
    ) -> TreeResponse:
        """One cascade tree."""
        selected = None if kinds is None else frozenset(kinds)
        cap = request.app.state.policy.max_tree_nodes
        with read_connection(request) as connection:
            key = ("tree", data_version(connection), cascade_id, selected, cap)
            payload = _cache(request).get_or_compute(
                key, TREE_TTL_SECONDS, lambda: _tree(connection, cascade_id, selected, cap)
            )
            fields = dict(payload)
            observed_since = fields.pop("observed_since")
            meta = build_meta(connection, request, observed_since=observed_since)
        return TreeResponse(**fields, meta=meta)

    @router.get(
        "/cascades/{cascade_id}/timeline",
        response_model=TimelineResponse,
        responses=V1_PROBLEM_RESPONSES,
        summary="Bucketed event counts of one cascade, to flag for human review",
        description=(
            CAPTION + " Dense counts per edge kind; the bucket width grows with the cascade's "
            f"span so that at most {policy.max_timeline_buckets} buckets are returned. Deleted "
            "events are not counted."
        ),
    )
    def get_cascade_timeline(request: Request, cascade_id: CascadeIdParam) -> TimelineResponse:
        """One cascade timeline."""
        max_buckets = request.app.state.policy.max_timeline_buckets
        with read_connection(request) as connection:
            key = ("timeline", data_version(connection), cascade_id, max_buckets)
            payload = _cache(request).get_or_compute(
                key,
                TIMELINE_TTL_SECONDS,
                lambda: _timeline(connection, cascade_id, max_buckets),
            )
            fields = dict(payload)
            observed_since = fields.pop("observed_since")
            meta = build_meta(connection, request, observed_since=observed_since)
        return TimelineResponse(**fields, meta=meta)
