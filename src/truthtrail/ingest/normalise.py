"""Classified Jetstream frames to keyed ``NormalizedEvent`` values (D-12, D-17, D-18).

This is the personal-data boundary of the collector: after ``normalise`` no raw DID, rkey, handle
or ``at://`` URI exists in any result. Every record URI, edge target, reply root, quote target,
repost ``via`` and account is keyed by the ``Keyer`` (D-15: the stored ``uri`` and ``parent_uri``
values are the keyed forms of the ``at://`` URIs). Only a root candidate carries what selection
and the claim row need: its canonical link URLs and hosts (parsed, never fetched or resolved,
D-13), the publisher's link-card title, the 0..9999 sampling bucket computed from the raw URI
before it is discarded, and the post text, which is excluded from ``repr``. Reply, quote and
repost items never carry text.

Edges follow D-12 through ``selection.derive_edge`` (the function that measured the spike's
yield): reply wins over quote and keeps the quote target as the secondary ``quoted_key``; a quote
targets ``embed.record.uri`` or ``embed.record.record.uri``; a repost's parent is its subject
(inferred, no depth) and its optional ``via`` is a secondary key; edge targets count only when
their collection is ``app.bsky.feed.post`` (F-08); unknown embed types mean no quote and no card.

``observed_at`` is the stream time (UTC, microseconds) and never the wall clock (D-08).
``occurred_at`` is the author-asserted ``createdAt``, kept only when it parses, is timezone-aware
and lies between 1970-01-01 and the STREAM time plus 366 days (so a replay is identical);
otherwise it is None and ``occurred_at_invalid`` lets the caller count it. Updates are ignored
(F-18). No function here logs anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

from truthtrail.ingest import selection
from truthtrail.ingest.dialect import (
    POST_COLLECTION,
    REPOST_COLLECTION,
    AccountFrame,
    BadFrame,
    CommitFrame,
    ErrorFrame,
    IgnoredFrame,
    InfoFrame,
    ParsedFrame,
    SyncFrame,
    datetime_from_us,
)
from truthtrail.ingest.pseudonym import Keyer

EdgeKind = Literal["root-candidate", "reply", "quote", "repost"]
EventKind = Literal["post", "repost"]
AccountActionKind = Literal["account_deleted", "account_takedown", "sync"]

# Stable drop reasons (the caller counts them by name).
UPDATE_IGNORED = "update_ignored"
ACCOUNT_STATUS_IGNORED = "account_status_ignored"
IDENTITY_IGNORED = "identity_ignored"
UNWANTED_COLLECTION = "unwanted_collection"
BAD_EDGE = "bad_edge"
BAD_FRAME_PREFIX = "bad_frame:"

# Deletion statuses are an allow-list; every other status (deactivated, suspended,
# desynchronized, throttled, unknown) is ignored and counted (D-16, F-18).
_ACCOUNT_ACTIONS: dict[str, AccountActionKind] = {
    "deleted": "account_deleted",
    "takendown": "account_takedown",
}

OCCURRED_AT_FLOOR = datetime(1970, 1, 1, tzinfo=UTC)
OCCURRED_AT_MAX_AHEAD = timedelta(days=366)

_EMBED_EXTERNAL = "app.bsky.embed.external"
_EMBED_RECORD_WITH_MEDIA = "app.bsky.embed.recordWithMedia"


@dataclass(frozen=True, slots=True)
class LinkCandidate:
    """A canonical link of a root candidate and where it came from (card or facet)."""

    source: str
    url: str
    host: str


@dataclass(frozen=True, slots=True)
class NormalizedEvent:
    """One create of a post or repost, keyed; text exists only on a root candidate."""

    kind: EventKind
    edge_kind: EdgeKind
    uri_key: str
    account_key: str
    observed_at: datetime
    time_us: int
    seq: int | None = None
    parent_key: str | None = None
    reply_root_key: str | None = None
    quoted_key: str | None = None
    via_key: str | None = None
    occurred_at: datetime | None = None
    occurred_at_invalid: bool = False
    langs: tuple[str, ...] = ()
    labels: frozenset[str] = frozenset()
    links: tuple[LinkCandidate, ...] = ()
    card_title: str | None = None
    sample_bucket: int | None = None
    text: str | None = field(default=None, repr=False)

    def seed_candidate(self) -> selection.SeedCandidate:
        """The selection view of this event (OD-3); a non-root is never top level."""
        return selection.SeedCandidate(
            top_level=self.edge_kind == "root-candidate",
            canonical_urls=tuple(link.url for link in self.links),
            langs=self.langs,
            labels=self.labels,
            sample_bucket=self.sample_bucket if self.sample_bucket is not None else 0,
        )


@dataclass(frozen=True, slots=True)
class DeleteEvent:
    """A delete commit of a post or repost, keyed by the URI it removes (D-16)."""

    uri_key: str
    collection: str
    time_us: int


@dataclass(frozen=True, slots=True)
class AccountAction:
    """An account-wide removal: account deleted, taken down, or a sync divergence (D-16)."""

    action: AccountActionKind
    account_key: str
    time_us: int


@dataclass(frozen=True, slots=True)
class Dropped:
    """A frame that yields nothing to store; ``reason`` is a stable counter name."""

    reason: str


Normalized = NormalizedEvent | DeleteEvent | AccountAction | Dropped | InfoFrame | ErrorFrame


def _record_uri(did: str, collection: str, rkey: str) -> str:
    return f"at://{did}/{collection}/{rkey}"


def _key_target(keyer: Keyer, uri: str | None) -> str | None:
    return None if uri is None else keyer.uri_key(uri)


def _key_via(keyer: Keyer, via: str | None) -> str | None:
    """Key a repost ``via`` only when it is a well-formed at:// URI (a secondary relation)."""
    if via is None or selection.parse_at_uri(via) is None:
        return None
    return keyer.uri_key(via)


def occurred_at_from(created_at: object, observed_at: datetime) -> datetime | None:
    """``createdAt`` as an aware UTC datetime when valid, else None; never raises (D-08)."""
    if not isinstance(created_at, str):
        return None
    try:
        parsed = datetime.fromisoformat(created_at)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    try:
        value = parsed.astimezone(UTC)
    except (OverflowError, ValueError):  # an offset that moves the instant before year 1
        return None
    if value < OCCURRED_AT_FLOOR or value > observed_at + OCCURRED_AT_MAX_AHEAD:
        return None
    return value


def _card_title(record: dict[str, object]) -> str | None:
    """The publisher's link-card title (external embed, or the media of recordWithMedia)."""
    embed = record.get("embed")
    if not isinstance(embed, dict):
        return None
    card: object = None
    if embed.get("$type") == _EMBED_EXTERNAL:
        card = embed.get("external")
    elif embed.get("$type") == _EMBED_RECORD_WITH_MEDIA:
        media = embed.get("media")
        if isinstance(media, dict) and media.get("$type") == _EMBED_EXTERNAL:
            card = media.get("external")
    title = card.get("title") if isinstance(card, dict) else None
    return title if isinstance(title, str) and title.strip() else None


def _links(record: dict[str, object]) -> tuple[LinkCandidate, ...]:
    found: list[LinkCandidate] = []
    for source, raw in selection.link_urls(record):
        canonical = selection.canonicalise_url(raw)
        if canonical is not None:
            found.append(LinkCandidate(source, canonical, selection.url_host(canonical)))
    return tuple(found)


_EDGE_KINDS: dict[str, EdgeKind] = {
    "root": "root-candidate",
    "reply": "reply",
    "quote": "quote",
    "repost": "repost",
}


def _create(frame: CommitFrame, keyer: Keyer) -> NormalizedEvent | Dropped:
    record = frame.record if frame.record is not None else {}
    edge = selection.derive_edge(frame.collection, record)
    edge_kind = None if edge is None else _EDGE_KINDS.get(edge.kind)
    if edge is None or edge_kind is None:
        return Dropped(BAD_EDGE)
    raw_uri = _record_uri(frame.did, frame.collection, frame.rkey)
    observed_at = datetime_from_us(frame.time_us)
    occurred_at = occurred_at_from(record.get("createdAt"), observed_at)
    root = edge_kind == "root-candidate"
    text = record.get("text") if root else None
    return NormalizedEvent(
        kind="repost" if edge_kind == "repost" else "post",
        edge_kind=edge_kind,
        uri_key=keyer.uri_key(raw_uri),
        account_key=keyer.account_key(frame.did),
        observed_at=observed_at,
        time_us=frame.time_us,
        seq=frame.seq,
        parent_key=_key_target(keyer, edge.parent),
        reply_root_key=_key_target(keyer, edge.reply_root),
        quoted_key=_key_target(keyer, edge.quoted),
        via_key=_key_via(keyer, edge.via),
        occurred_at=occurred_at,
        occurred_at_invalid=occurred_at is None,
        # Only a root candidate carries what selection and the claim row need (D-18).
        langs=tuple(selection.record_langs(record)) if root else (),
        labels=frozenset(selection.record_labels(record)) if root else frozenset(),
        links=_links(record) if root else (),
        card_title=_card_title(record) if root else None,
        sample_bucket=selection.sample_bucket(raw_uri) if root else None,
        text=text if isinstance(text, str) else None,
    )


def normalise(parsed: ParsedFrame, keyer: Keyer) -> Normalized:
    """Turn one ``classify_frame`` result into a keyed result; never raises for a frame.

    ``InfoFrame`` and ``ErrorFrame`` control results pass through untouched for the caller.
    """
    if isinstance(parsed, InfoFrame | ErrorFrame):
        return parsed
    if isinstance(parsed, BadFrame):
        return Dropped(BAD_FRAME_PREFIX + parsed.reason)
    if isinstance(parsed, IgnoredFrame):
        return Dropped(IDENTITY_IGNORED)
    if isinstance(parsed, AccountFrame):
        action = _ACCOUNT_ACTIONS.get(parsed.status or "")
        if action is None:
            return Dropped(ACCOUNT_STATUS_IGNORED)
        return AccountAction(action, keyer.account_key(parsed.did), parsed.time_us)
    if isinstance(parsed, SyncFrame):
        return AccountAction("sync", keyer.account_key(parsed.did), parsed.time_us)
    if parsed.collection not in (POST_COLLECTION, REPOST_COLLECTION):
        return Dropped(UNWANTED_COLLECTION)
    if parsed.operation == "update":
        return Dropped(UPDATE_IGNORED)
    if parsed.operation == "delete":
        uri_key = keyer.uri_key(_record_uri(parsed.did, parsed.collection, parsed.rkey))
        return DeleteEvent(uri_key, parsed.collection, parsed.time_us)
    return _create(parsed, keyer)
