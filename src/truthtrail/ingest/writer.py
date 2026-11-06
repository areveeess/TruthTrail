"""The collector's only write path: tracked-set decisions, batch upserts, tombstones and the
checkpoint in ONE transaction (D-09, D-14, D-15, D-16, D-18, D-21; RESEARCH Pattern 4).

Three pieces:

* ``TrackedIndex``: the in-memory tracked set (D-14). It maps the key of every stored event of
  a cascade whose tracking window is open to that cascade's root key, and holds per cascade
  the tracking end, the stored event count and the overflow high-water mark. It is loaded from
  the database at run start, extended as events are accepted and pruned as windows close.
  Cascades are identified by their root key (``cascades.root_uri`` is unique), so a cascade
  created in the current batch needs no surrogate id until the flush.
* ``Decider``: applies the rules to one keyed result. A root candidate goes through
  ``selection.seed_decision_for`` with every value from the ``Policy`` (allowlist, language,
  sampling and OD-3 option B), then the active-root and total caps. A reply, quote or repost
  is stored only when its parent, subject or reply root is a stored event of an open cascade.
  The event's OWN key is tested first: a key that is already stored is a duplicate, never a
  refusal and never overflow (SC3). An event refused only because its cascade is full is not
  stored and is tallied through the per-cascade stream-time high-water mark
  (``cascades.overflow_through_us``), so redelivery by a replay, a rewind or a restart cannot
  inflate ``overflow_count``; the tally is therefore a lower bound (it can undercount events
  delivered out of stream-time order or sharing a microsecond with a counted one). Nothing is
  ever evicted.
* ``flush``: one transaction per batch, in this order: accounts and claims upserted by their
  unique keys, cascades inserted once per root, events inserted ``ON CONFLICT (uri) DO
  NOTHING RETURNING uri`` (inserted and duplicate counts come from RETURNING, never rowcount),
  overflow tallies applied, tombstones by key, account-wide
  tombstones (only rows observed at or before the account event's stream time, so a replay
  that meets the action again cannot remove content the account published after it), every
  touched cascade marked dirty (``mark_cascades_dirty``, unconditionally), then the checkpoint
  with ``GREATEST`` so it only moves forward. Inserts come
  before tombstones, so a create and its delete in one batch end as a tombstone; a replayed
  create can never overwrite a tombstone, and the cascade insert never relinks a claim.

Every statement is a Core statement or a ``text()`` constant with bound parameters. No
function here logs anything: the run loop owns the counters (D-18).
"""

from __future__ import annotations

import base64
import hashlib
from collections import Counter
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection, Engine

from truthtrail.core.policy import Policy
from truthtrail.db.models import Account, Cascade, Claim, Event, IngestCheckpoint
from truthtrail.ingest import selection
from truthtrail.ingest.dialect import ErrorFrame, InfoFrame, datetime_from_us
from truthtrail.ingest.normalise import AccountAction, DeleteEvent, NormalizedEvent

# Option B (OD-3): at most this many stored news headline URLs are held in memory.
KNOWN_CLAIM_URL_LIMIT = 20_000
# The application tables whose size counts against DB_BUDGET_BYTES (D-21).
SIZE_TABLES = (
    "news_queries",
    "accounts",
    "claims",
    "cascades",
    "events",
    "ingest_checkpoints",
    "ingest_runs",
    "news_fetches",
)

SOCIAL_LINK = "social_link"
NEWS_HEADLINE = "news_headline"
DIGEST_CHARS = 26

# Stable outcome names (counted by the run loop).
DUPLICATE = "duplicate"
UNTRACKED = "untracked"
TRACKING_ENDED = "tracking_ended"
CAP_ACTIVE_ROOTS = "cap_active_roots"
CAP_TOTAL_EVENTS = "cap_total_events"
OVERFLOW = "overflow"
OVERFLOW_UNCOUNTED = "overflow_uncounted"
CASCADE_CONFLICT = "cascade_conflict"
REPLY_WITHOUT_PARENT = "reply_without_parent"
SEED_CLAIM_URL_MATCH = "seed_claim_url_match"
ACCEPTED_PREFIX = "accepted_"
CONTROL = "control"
DELETE = "delete"
REFUSAL_REASONS = (UNTRACKED, TRACKING_ENDED, CAP_ACTIVE_ROOTS, CAP_TOTAL_EVENTS, OVERFLOW)

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_ONE_US = timedelta(microseconds=1)


def us_of(value: datetime) -> int:
    """Unix microseconds of an aware datetime (exact integer arithmetic)."""
    return (value - _EPOCH) // _ONE_US


def digest(*parts: str) -> str:
    """Lowercase base32 of SHA-256 over NUL-joined parts, truncated to 26 characters."""
    raw = hashlib.sha256("\0".join(parts).encode("utf-8")).digest()
    return base64.b32encode(raw).decode("ascii").lower().rstrip("=")[:DIGEST_CHARS]


def claim_key_for(kind: str, url_canonical: str) -> str:
    """The unique ``claims.claim_key`` of a claim identified by its kind and canonical URL."""
    return digest(kind, url_canonical)


# --- The tracked set (D-14) --------------------------------------------------------------------
@dataclass(slots=True)
class CascadeState:
    """What the Decider needs to know about one open cascade."""

    tracking_ends_us: int
    event_count: int
    overflow_through_us: int | None = None
    keys: list[str] = field(default_factory=list)


class TrackedIndex:
    """Stored events of open cascades, keyed; bounded by the caps and pruned as windows close."""

    def __init__(self) -> None:
        self._events: dict[str, str] = {}
        self._cascades: dict[str, CascadeState] = {}
        self.committed_total = 0
        self.pending_total = 0

    # -- loading and queries --
    def load(self, connection: Connection, since_us: int | None) -> None:
        """Load cascades whose tracking ends after ``since_us`` (all when None) and their keys,
        plus the total stored event count for the STORE_MAX_EVENTS_TOTAL cap."""
        self._events.clear()
        self._cascades.clear()
        self.pending_total = 0
        cascade_query = select(
            Cascade.id, Cascade.root_uri, Cascade.tracking_ends_at, Cascade.overflow_through_us
        )
        if since_us is not None:
            cascade_query = cascade_query.where(
                Cascade.tracking_ends_at > datetime_from_us(since_us)
            )
        roots_by_id: dict[int, str] = {}
        for cascade_id, root_uri, ends_at, overflow_us in connection.execute(cascade_query):
            roots_by_id[cascade_id] = root_uri
            self._cascades[root_uri] = CascadeState(us_of(ends_at), 0, overflow_us)
        if roots_by_id:
            keys = connection.execute(
                select(Event.uri, Event.cascade_id).where(Event.cascade_id.in_(list(roots_by_id)))
            )
            for uri, owner in keys:
                if owner is None:  # pragma: no cover - selected by cascade_id
                    continue
                root = roots_by_id[owner]
                state = self._cascades[root]
                self._events[uri] = root
                state.keys.append(uri)
                state.event_count += 1
        self.committed_total = stored_event_count(connection)

    def lookup(self, key: str | None) -> str | None:
        """The root key of the open cascade that stores ``key``, else None."""
        return None if key is None else self._events.get(key)

    def cascade(self, root_key: str) -> CascadeState | None:
        return self._cascades.get(root_key)

    @property
    def active_roots(self) -> int:
        return len(self._cascades)

    @property
    def total_events(self) -> int:
        return self.committed_total + self.pending_total

    def __len__(self) -> int:
        return len(self._events)

    # -- mutation --
    def add_root(self, root_key: str, tracking_ends_us: int) -> None:
        self._cascades[root_key] = CascadeState(tracking_ends_us, 1, None, [root_key])
        self._events[root_key] = root_key
        self.pending_total += 1

    def add_child(self, key: str, root_key: str) -> None:
        state = self._cascades[root_key]
        state.event_count += 1
        state.keys.append(key)
        self._events[key] = root_key
        self.pending_total += 1

    def commit(self, result: FlushResult, batch: Batch) -> None:
        """Apply a COMMITTED flush: totals, overflow marks and cascades that already existed."""
        self.committed_total += result.inserted
        self.pending_total = 0
        for root_key, (_count, through_us) in batch.overflow.items():
            state = self._cascades.get(root_key)
            if state is not None and (
                state.overflow_through_us is None or state.overflow_through_us < through_us
            ):
                state.overflow_through_us = through_us
        for root_key, ends_us in result.tracking_ends_us.items():
            state = self._cascades.get(root_key)
            if state is not None:
                state.tracking_ends_us = ends_us

    def expire(self, stream_now_us: int) -> int:
        """Prune cascades whose window closed at or before ``stream_now_us``; returns how many.

        Call it only after a committed flush, never with pending rows in a batch.
        """
        closed = [r for r, s in self._cascades.items() if s.tracking_ends_us <= stream_now_us]
        for root_key in closed:
            for key in self._cascades.pop(root_key).keys:
                self._events.pop(key, None)
        return len(closed)


# --- The batch ---------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class PendingEvent:
    """One accepted event waiting for its flush; ids are resolved inside the transaction."""

    uri: str
    edge_kind: str
    root_key: str
    account_key: str
    observed_at: datetime
    occurred_at: datetime | None
    parent_uri: str | None = None
    reply_root_uri: str | None = None
    quoted_uri: str | None = None
    via_uri: str | None = None
    text: str | None = field(default=None, repr=False)
    lang: str | None = None
    claim_key: str | None = None


@dataclass(frozen=True, slots=True)
class PendingClaim:
    """A social_link claim of a new root: the canonical URL, its host and the card title."""

    claim_key: str
    url_canonical: str
    link_domain: str
    title: str | None


@dataclass(frozen=True, slots=True)
class PendingCascade:
    root_key: str
    observed_at: datetime
    tracking_ends_at: datetime
    claim_key: str | None


@dataclass(slots=True)
class Batch:
    """Everything one transaction writes, plus the batch's counters (never logged here)."""

    events: list[PendingEvent] = field(default_factory=list)
    claims: dict[str, PendingClaim] = field(default_factory=dict)
    cascades: dict[str, PendingCascade] = field(default_factory=dict)
    accounts: dict[str, datetime] = field(default_factory=dict)
    # Tombstones by key: the earliest delete time per key wins (deterministic deleted_at).
    tombstones: dict[str, datetime] = field(default_factory=dict)
    # Account-wide tombstones: pseudonym -> (cause, time); the first action per account wins.
    account_tombstones: dict[str, tuple[str, datetime]] = field(default_factory=dict)
    # Per-cascade overflow increments: root key -> (count, highest counted stream time).
    overflow: dict[str, tuple[int, int]] = field(default_factory=dict)
    max_time_us: int | None = None
    counters: Counter[str] = field(default_factory=Counter)

    @property
    def rows(self) -> int:
        """Rows this batch writes or changes (the INGEST_BATCH_ROWS threshold)."""
        return len(self.events) + len(self.tombstones) + len(self.account_tombstones)

    def note_cursor(self, cursor_us: int | None) -> None:
        if cursor_us is not None and (self.max_time_us is None or cursor_us > self.max_time_us):
            self.max_time_us = cursor_us

    def overflow_mark(self, root_key: str) -> int | None:
        pending = self.overflow.get(root_key)
        return None if pending is None else pending[1]

    def add_overflow(self, root_key: str, time_us: int) -> None:
        count, _mark = self.overflow.get(root_key, (0, time_us))
        self.overflow[root_key] = (count + 1, time_us)

    def add_event(self, pending: PendingEvent) -> None:
        self.events.append(pending)
        first = self.accounts.get(pending.account_key)
        if first is None or pending.observed_at < first:
            self.accounts[pending.account_key] = pending.observed_at

    def add_delete(self, event: DeleteEvent) -> None:
        at = datetime_from_us(event.time_us)
        current = self.tombstones.get(event.uri_key)
        if current is None or at < current:
            self.tombstones[event.uri_key] = at

    def add_account_action(self, action: AccountAction) -> None:
        if action.account_key not in self.account_tombstones:
            self.account_tombstones[action.account_key] = (
                action.action,
                datetime_from_us(action.time_us),
            )


# --- Decisions (D-13, D-14, OD-3) ----------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Decision:
    """The outcome for one event: accepted into ``root_key`` (``new_root`` for a seed) or not."""

    accepted: bool
    reason: str
    root_key: str | None = None
    new_root: bool = False
    claim_url: str | None = None


class Decider:
    """Applies the tracked-set rules to keyed results; every number comes from the Policy."""

    def __init__(
        self,
        policy: Policy,
        index: TrackedIndex,
        allowlist: Collection[str],
        known_claim_urls: Collection[str] = frozenset(),
    ) -> None:
        self._policy = policy
        self._index = index
        self._allowlist = frozenset(allowlist)
        self._known_claim_urls = frozenset(known_claim_urls)
        self._ttl_us = policy.track_root_ttl_hours * 3_600_000_000

    @property
    def index(self) -> TrackedIndex:
        return self._index

    def set_known_claim_urls(self, urls: Collection[str]) -> None:
        """Option B: replace the stored news headline URLs (refreshed by the run loop)."""
        self._known_claim_urls = frozenset(urls)

    def process(self, result: object, batch: Batch) -> str:
        """Route one source result into ``batch``; returns the outcome name to count."""
        if isinstance(result, NormalizedEvent):
            decision = self.decide(result, batch)
            if not decision.accepted:
                return decision.reason
            self._accept(result, decision, batch)
            if decision.reason == "claim_url_match":
                return SEED_CLAIM_URL_MATCH
            return ACCEPTED_PREFIX + ("root" if decision.new_root else result.edge_kind)
        if isinstance(result, DeleteEvent):
            batch.add_delete(result)
            return DELETE
        if isinstance(result, AccountAction):
            batch.add_account_action(result)
            return result.action
        if isinstance(result, InfoFrame | ErrorFrame):
            return CONTROL
        raise TypeError("unsupported source result")

    def decide(self, event: NormalizedEvent, batch: Batch) -> Decision:
        """Decide one event; the duplicate test of its own key always comes first."""
        if self._index.lookup(event.uri_key) is not None:
            return Decision(False, DUPLICATE)
        if event.edge_kind == "root-candidate":
            return self._decide_root(event)
        return self._decide_child(event, batch)

    def _decide_root(self, event: NormalizedEvent) -> Decision:
        policy = self._policy
        seed = selection.seed_decision_for(
            event.seed_candidate(),
            self._allowlist,
            require_lang=policy.track_require_lang,
            sample_per_10k=policy.track_sample_per_10k,
            known_claim_urls=self._known_claim_urls,
            seed_claim_url_match=policy.track_seed_claim_url_match,
        )
        if not seed.eligible:
            return Decision(False, seed.reason)
        if self._index.active_roots >= policy.track_max_active_roots:
            return Decision(False, CAP_ACTIVE_ROOTS)
        if self._index.total_events >= policy.store_max_events_total:
            return Decision(False, CAP_TOTAL_EVENTS)
        return Decision(True, seed.reason, event.uri_key, True, seed.claim_url)

    def _target_root(self, event: NormalizedEvent) -> tuple[str | None, bool]:
        """The cascade a child belongs to and whether parent and reply root disagree."""
        parent_root = self._index.lookup(event.parent_key)
        if event.edge_kind != "reply":
            return parent_root, False
        reply_root = self._index.lookup(event.reply_root_key)
        if parent_root is not None:
            conflict = reply_root is not None and reply_root != parent_root
            return parent_root, conflict
        return reply_root, False

    def _decide_child(self, event: NormalizedEvent, batch: Batch) -> Decision:
        if event.parent_key is None:
            # A reply whose parent reference is unusable: no edge can be drawn, never invented.
            return Decision(False, REPLY_WITHOUT_PARENT)
        root_key, conflict = self._target_root(event)
        if root_key is None:
            return Decision(False, UNTRACKED)
        if conflict:
            batch.counters[CASCADE_CONFLICT] += 1
        state = self._index.cascade(root_key)
        if state is None:  # pragma: no cover - lookup and cascades are updated together
            return Decision(False, UNTRACKED)
        if event.time_us >= state.tracking_ends_us:
            return Decision(False, TRACKING_ENDED)
        if state.event_count >= self._policy.track_max_events_per_cascade:
            marks = (state.overflow_through_us, batch.overflow_mark(root_key))
            mark = max((m for m in marks if m is not None), default=-1)
            if event.time_us > mark:
                batch.add_overflow(root_key, event.time_us)
                return Decision(False, OVERFLOW)
            return Decision(False, OVERFLOW_UNCOUNTED)
        if self._index.total_events >= self._policy.store_max_events_total:
            return Decision(False, CAP_TOTAL_EVENTS)
        return Decision(True, "tracked", root_key)

    def _accept(self, event: NormalizedEvent, decision: Decision, batch: Batch) -> None:
        root_key = decision.root_key
        if root_key is None:  # pragma: no cover - an accepted decision always names its root
            raise ValueError("an accepted decision must name its cascade")
        if decision.new_root:
            self._accept_root(event, decision, batch)
            return
        self._index.add_child(event.uri_key, root_key)
        batch.add_event(
            PendingEvent(
                uri=event.uri_key,
                edge_kind=event.edge_kind,
                root_key=root_key,
                account_key=event.account_key,
                observed_at=event.observed_at,
                occurred_at=event.occurred_at,
                parent_uri=event.parent_key,
                reply_root_uri=event.reply_root_key,
                quoted_uri=event.quoted_key,
                via_uri=event.via_key,
            )
        )

    def _accept_root(self, event: NormalizedEvent, decision: Decision, batch: Batch) -> None:
        policy = self._policy
        claim: PendingClaim | None = None
        if decision.claim_url is not None:
            card_urls = {link.url for link in event.links if link.source == selection.LINK_CARD}
            claim = PendingClaim(
                claim_key=claim_key_for(SOCIAL_LINK, decision.claim_url),
                url_canonical=decision.claim_url,
                link_domain=selection.url_host(decision.claim_url),
                # The publisher's card title belongs to the card's own link only.
                title=event.card_title if decision.claim_url in card_urls else None,
            )
            batch.claims.setdefault(claim.claim_key, claim)
        ends_us = event.time_us + self._ttl_us
        self._index.add_root(event.uri_key, ends_us)
        batch.cascades[event.uri_key] = PendingCascade(
            event.uri_key,
            event.observed_at,
            datetime_from_us(ends_us),
            None if claim is None else claim.claim_key,
        )
        # OD-1: post text only under a positive text retention (RT-1, 0 days, writes none).
        keep_text = policy.retention_text_days > 0
        batch.add_event(
            PendingEvent(
                uri=event.uri_key,
                edge_kind="root",
                root_key=event.uri_key,
                account_key=event.account_key,
                observed_at=event.observed_at,
                occurred_at=event.occurred_at,
                quoted_uri=event.quoted_key,
                text=event.text if keep_text else None,
                lang=policy.track_require_lang,
                claim_key=None if claim is None else claim.claim_key,
            )
        )


# --- The flush (one transaction) ------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class FlushResult:
    """What one committed transaction did (counts only, no identifiers except root keys)."""

    inserted_by_kind: Mapping[str, int]
    duplicates: int
    tombstoned_by_cause: Mapping[str, int]
    deletes_unmatched: int
    account_actions_unmatched: int
    roots_deleted: int
    overflow_counted: int
    checkpoint_us: int | None
    tracking_ends_us: Mapping[str, int]

    @property
    def inserted(self) -> int:
        return sum(self.inserted_by_kind.values())

    @property
    def tombstoned(self) -> int:
        return sum(self.tombstoned_by_cause.values())


def event_row(
    pending: PendingEvent,
    cascade_id: int,
    account_id: int,
    claim_id: int | None,
) -> dict[str, Any]:
    """THE row builder: every events row dict has exactly these keys (SQLAlchemy takes the
    key set of an executemany from the first dict)."""
    root = pending.edge_kind == "root"
    return {
        "uri": pending.uri,
        "edge_kind": pending.edge_kind,
        "inferred": pending.edge_kind == "repost",
        "parent_uri": None if root else pending.parent_uri,
        "reply_root_uri": None if root else pending.reply_root_uri,
        "quoted_uri": pending.quoted_uri,
        "via_uri": pending.via_uri if pending.edge_kind == "repost" else None,
        "parent_state": "none" if root else "orphan",
        "cascade_id": cascade_id,
        "account_id": account_id,
        "observed_at": pending.observed_at,
        "occurred_at": pending.occurred_at,
        "text": pending.text if root else None,
        "claim_id": claim_id if root else None,
        "lang": pending.lang if root else None,
    }


_TOMBSTONE_BY_KEY = text(
    "UPDATE events SET deleted_at = d.at, account_id = NULL, occurred_at = NULL, text = NULL,"
    " claim_id = NULL, lang = NULL"
    " FROM unnest(CAST(:keys AS varchar[]), CAST(:times AS timestamptz[])) AS d(uri, at)"
    " WHERE events.uri = d.uri AND events.deleted_at IS NULL"
    " RETURNING events.cascade_id, events.edge_kind, events.deleted_at"
)
_TOMBSTONE_BY_ACCOUNT = text(
    "UPDATE events SET deleted_at = :at, account_id = NULL, occurred_at = NULL, text = NULL,"
    " claim_id = NULL, lang = NULL"
    " WHERE account_id = :account_id AND deleted_at IS NULL AND observed_at <= :at"
    " RETURNING cascade_id, edge_kind, deleted_at"
)
_ROOT_DELETED = text(
    "UPDATE cascades SET root_deleted_at = COALESCE(cascades.root_deleted_at, d.at),"
    " claim_id = NULL, enrich_dirty = true"
    " FROM unnest(CAST(:ids AS bigint[]), CAST(:times AS timestamptz[])) AS d(id, at)"
    " WHERE cascades.id = d.id"
)
_OVERFLOW = text(
    "UPDATE cascades SET overflow_count = overflow_count + :n, overflow_through_us = :t"
    " WHERE id = :id AND (overflow_through_us IS NULL OR overflow_through_us < :t)"
)


def _upsert_accounts(connection: Connection, batch: Batch) -> dict[str, int]:
    if not batch.accounts:
        return {}
    base = pg_insert(Account)
    stmt = base.on_conflict_do_update(
        index_elements=[Account.pseudonym],
        set_={
            "first_observed_at": func.least(
                Account.first_observed_at, base.excluded.first_observed_at
            )
        },
    ).returning(Account.pseudonym, Account.id)
    rows = [{"pseudonym": k, "first_observed_at": t} for k, t in sorted(batch.accounts.items())]
    return dict(connection.execute(stmt, rows).all())


def _upsert_claims(connection: Connection, batch: Batch) -> dict[str, int]:
    if not batch.claims:
        return {}
    base = pg_insert(Claim)
    stmt = base.on_conflict_do_update(
        index_elements=[Claim.claim_key],
        set_={"text": func.coalesce(Claim.text, base.excluded.text)},
    ).returning(Claim.claim_key, Claim.id)
    rows = [
        {
            "kind": SOCIAL_LINK,
            "claim_key": c.claim_key,
            "text": c.title,
            "text_hash": c.claim_key,
            "url_canonical": c.url_canonical,
            "link_domain": c.link_domain,
        }
        for _key, c in sorted(batch.claims.items())
    ]
    return dict(connection.execute(stmt, rows).all())


def _ensure_cascades(
    connection: Connection, batch: Batch, claim_ids: Mapping[str, int]
) -> dict[str, tuple[int, int]]:
    """Insert new cascades once per root (never relinking) and resolve every needed id."""
    if batch.cascades:
        rows = [
            {
                "root_uri": c.root_key,
                "claim_id": None if c.claim_key is None else claim_ids[c.claim_key],
                "tracking_ends_at": c.tracking_ends_at,
                "first_event_at": c.observed_at,
                "last_event_at": c.observed_at,
            }
            for _key, c in sorted(batch.cascades.items())
        ]
        connection.execute(
            pg_insert(Cascade).on_conflict_do_nothing(index_elements=[Cascade.root_uri]), rows
        )
    needed = {p.root_key for p in batch.events} | set(batch.overflow) | set(batch.cascades)
    if not needed:
        return {}
    found = connection.execute(
        select(Cascade.root_uri, Cascade.id, Cascade.tracking_ends_at).where(
            Cascade.root_uri.in_(sorted(needed))
        )
    )
    return {root: (ident, us_of(ends)) for root, ident, ends in found}


def _insert_events(
    connection: Connection,
    batch: Batch,
    cascades: Mapping[str, tuple[int, int]],
    accounts: Mapping[str, int],
    claims: Mapping[str, int],
) -> tuple[Counter[str], set[int]]:
    inserted: Counter[str] = Counter()
    touched: set[int] = set()
    if not batch.events:
        return inserted, touched
    rows = [
        event_row(
            p,
            cascades[p.root_key][0],
            accounts[p.account_key],
            None if p.claim_key is None else claims[p.claim_key],
        )
        for p in batch.events
    ]
    stmt = (
        pg_insert(Event)
        .on_conflict_do_nothing(index_elements=[Event.uri])
        .returning(Event.uri, Event.edge_kind, Event.cascade_id)
    )
    for _uri, edge_kind, cascade_id in connection.execute(stmt, rows):
        inserted[edge_kind] += 1
        if cascade_id is not None:
            touched.add(cascade_id)
    return inserted, touched


def _apply_overflow(
    connection: Connection, batch: Batch, cascades: Mapping[str, tuple[int, int]]
) -> int:
    params = [
        {"id": cascades[root][0], "n": count, "t": through}
        for root, (count, through) in sorted(batch.overflow.items())
        if root in cascades
    ]
    if params:
        connection.execute(_OVERFLOW, params)
    return sum(p["n"] for p in params)


def _tombstone(
    connection: Connection, batch: Batch
) -> tuple[Counter[str], int, int, list[tuple[int, datetime]], set[int]]:
    """Key tombstones, then account-wide ones; returns causes, unmatched counts, deleted roots
    and touched cascades."""
    causes: Counter[str] = Counter()
    roots: list[tuple[int, datetime]] = []
    touched: set[int] = set()
    deletes_unmatched = 0
    accounts_unmatched = 0
    if batch.tombstones:
        keys = sorted(batch.tombstones)
        rows = connection.execute(
            _TOMBSTONE_BY_KEY, {"keys": keys, "times": [batch.tombstones[k] for k in keys]}
        ).all()
        if rows:
            causes[DELETE] += len(rows)
        deletes_unmatched = len(keys) - len(rows)
        for cascade_id, edge_kind, deleted_at in rows:
            touched.add(cascade_id)
            if edge_kind == "root":
                roots.append((cascade_id, deleted_at))
    if batch.account_tombstones:
        pseudonyms = sorted(batch.account_tombstones)
        ids = dict(
            connection.execute(
                select(Account.pseudonym, Account.id).where(Account.pseudonym.in_(pseudonyms))
            ).all()
        )
        for pseudonym in pseudonyms:
            cause, at = batch.account_tombstones[pseudonym]
            account_id = ids.get(pseudonym)
            if account_id is None:
                accounts_unmatched += 1
                continue
            rows = connection.execute(
                _TOMBSTONE_BY_ACCOUNT, {"at": at, "account_id": account_id}
            ).all()
            if rows:
                causes[cause] += len(rows)
            for cascade_id, edge_kind, deleted_at in rows:
                touched.add(cascade_id)
                if edge_kind == "root":
                    roots.append((cascade_id, deleted_at))
    return causes, deletes_unmatched, accounts_unmatched, roots, touched


def _write_checkpoint(
    connection: Connection, cursor_us: int, *, source: str, dialect: str, host: str
) -> None:
    stmt = pg_insert(IngestCheckpoint).values(
        source=source, dialect=dialect, host=host, cursor_time_us=cursor_us, cursor_seq=None
    )
    connection.execute(
        stmt.on_conflict_do_update(
            index_elements=[IngestCheckpoint.source],
            set_={
                "cursor_time_us": func.greatest(
                    IngestCheckpoint.cursor_time_us, stmt.excluded.cursor_time_us
                ),
                "dialect": stmt.excluded.dialect,
                "host": stmt.excluded.host,
                "updated_at": func.now(),
            },
        )
    )


def mark_cascades_dirty(connection: Connection, cascade_ids: Collection[int]) -> None:
    """Set ``enrich_dirty`` on every touched cascade, UNCONDITIONALLY (T-03-43).

    The UPDATE has no ``enrich_dirty IS FALSE`` filter on purpose: under READ COMMITTED a
    filtered UPDATE would read the flag from its snapshot, find it still true while an enrich
    transaction holds the cascade row (enrich clears it at commit) and match nothing, so the
    flag would be lost. Unfiltered, the UPDATE waits for enrich's ``FOR UPDATE`` lock and sets
    the flag after enrich commits. Ids are sorted so concurrent writers lock in one order.
    """
    if cascade_ids:
        connection.execute(
            update(Cascade).where(Cascade.id.in_(sorted(cascade_ids))).values(enrich_dirty=True)
        )


def _flush_in(
    connection: Connection, batch: Batch, *, source: str, dialect: str, host: str
) -> FlushResult:
    accounts = _upsert_accounts(connection, batch)
    claims = _upsert_claims(connection, batch)
    cascades = _ensure_cascades(connection, batch, claims)
    inserted, touched = _insert_events(connection, batch, cascades, accounts, claims)
    overflow_counted = _apply_overflow(connection, batch, cascades)
    causes, deletes_unmatched, accounts_unmatched, roots, dead = _tombstone(connection, batch)
    touched |= dead
    if roots:
        connection.execute(
            _ROOT_DELETED, {"ids": [i for i, _at in roots], "times": [at for _i, at in roots]}
        )
    mark_cascades_dirty(connection, touched)
    if batch.max_time_us is not None:
        _write_checkpoint(connection, batch.max_time_us, source=source, dialect=dialect, host=host)
    return FlushResult(
        inserted_by_kind=dict(sorted(inserted.items())),
        duplicates=len(batch.events) - sum(inserted.values()),
        tombstoned_by_cause=dict(sorted(causes.items())),
        deletes_unmatched=deletes_unmatched,
        account_actions_unmatched=accounts_unmatched,
        roots_deleted=len(roots),
        overflow_counted=overflow_counted,
        checkpoint_us=batch.max_time_us,
        tracking_ends_us={root: ends for root, (_id, ends) in cascades.items()},
    )


def flush(
    target: Engine | Connection, batch: Batch, *, source: str, dialect: str, host: str
) -> FlushResult:
    """Write ``batch`` in ONE transaction (see the module docstring for the order).

    ``target`` is an engine or a connection without an open transaction. On any error the
    transaction rolls back: no row, tombstone, account, claim, tally or checkpoint persists.
    The batch itself is not modified, so the same batch can be flushed again.
    """
    if isinstance(target, Engine):
        with target.begin() as connection:
            return _flush_in(connection, batch, source=source, dialect=dialect, host=host)
    with target.begin():
        return _flush_in(target, batch, source=source, dialect=dialect, host=host)


# --- Capacity and option B helpers -------------------------------------------------------------
_SIZE = text(
    "SELECT COALESCE(SUM(pg_total_relation_size(to_regclass(n))), 0)"
    " FROM unnest(CAST(:names AS text[])) AS n"
)


def db_size_bytes(connection: Connection) -> int:
    """Total on-disk size (tables, indexes, TOAST) of the application tables (D-21)."""
    return int(connection.execute(_SIZE, {"names": list(SIZE_TABLES)}).scalar_one())


def stored_event_count(connection: Connection) -> int:
    """Every stored event, tombstones included (the STORE_MAX_EVENTS_TOTAL cap)."""
    return int(connection.execute(select(func.count()).select_from(Event)).scalar_one())


def load_known_claim_urls(
    connection: Connection, limit: int = KNOWN_CLAIM_URL_LIMIT
) -> frozenset[str]:
    """Option B (OD-3): canonical URLs of stored news headline claims, newest first, bounded."""
    query = (
        select(Claim.url_canonical)
        .where(Claim.kind == NEWS_HEADLINE, Claim.url_canonical.is_not(None))
        .order_by(Claim.created_at.desc(), Claim.id.desc())
        .limit(limit)
    )
    return frozenset(url for (url,) in connection.execute(query) if url is not None)


def outcome_counts(outcomes: Iterable[str]) -> dict[str, int]:
    """Counter of outcome names, sorted by name (used by tests and the run summary)."""
    return dict(sorted(Counter(outcomes).items()))


def known_claim_urls_for(
    connection: Connection, policy: Policy, limit: int = KNOWN_CLAIM_URL_LIMIT
) -> frozenset[str]:
    """Option B gate (OD-3): the claims table is queried only when the policy flag is true."""
    if not policy.track_seed_claim_url_match:
        return frozenset()
    return load_known_claim_urls(connection, limit)
