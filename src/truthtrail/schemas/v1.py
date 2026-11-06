"""Typed models of the ``/v1`` read API (D-23, D-24): the contract the Phase 5 client is built from.

Every model forbids extra members and every field carries a description, so the OpenAPI document
is the complete contract. Every success body carries a ``V1Meta`` (a NEW model: the Phase 1
``Meta`` has a required non-null ``data_as_of`` and a ``fixture`` status, neither of which fits
stored data). Nothing here is a verdict: no model has a ``risk`` or ``claim_scores`` member, the
counts are an observed subset, and the cascades are something to flag for human review.
"""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

CAPTION = "Observed subset of public Bluesky posts, as of the stated time."

SourceStatus = Literal["ok", "empty", "stale"]
SourceMode = Literal["live", "replay"]
EdgeKind = Literal["root", "reply", "quote", "repost"]
ChildKind = Literal["reply", "quote", "repost"]
ParentState = Literal["none", "resolved", "orphan", "invalid"]
ClaimKind = Literal["social_link", "news_headline"]
CascadeSort = Literal["recent", "velocity"]

ACCOUNT_PREFIX_LENGTH = 8


class _V1Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class V1Meta(_V1Model):
    __doc__ = (
        "Provenance of a /v1 response. " + CAPTION + " Stored observations are never synthetic; "
        "the data is something to flag for human review, not a verdict."
    )

    synthetic: Literal[False] = Field(
        description="Always false: /v1 serves only observed, stored data, never demo data."
    )
    data_as_of: AwareDatetime | None = Field(
        description=(
            "Stream time of the latest committed ingest checkpoint (UTC). Null only when "
            "nothing was ever ingested."
        )
    )
    source_status: SourceStatus = Field(
        description=(
            "empty: nothing was ever ingested. stale: data_as_of is older than the configured "
            "staleness threshold (for example the collector stopped or Bluesky was "
            "unreachable). ok: otherwise, including an empty filtered result."
        )
    )
    source_mode: SourceMode = Field(
        description=(
            "replay when the latest ingest run replayed a recorded file, live when it read the "
            "public stream (or when no run is recorded)."
        )
    )
    observed_since: AwareDatetime | None = Field(
        default=None,
        description=(
            "Earliest observation the response covers (a cascade's root observation, or the "
            "earliest cascade for global statistics). Nothing before it was observed; null "
            "where it is not meaningful."
        ),
    )


class ClaimSummary(_V1Model):
    """The article a root post links to (publisher text only, never post text)."""

    claim_id: int = Field(description="Stable id of the claim (use it with the claim_id filter).")
    kind: ClaimKind = Field(
        description="social_link: the article a root post links to. news_headline: a headline."
    )
    title: str | None = Field(
        description="Title published with the link card or headline, as plain text, if any."
    )
    url_canonical: str | None = Field(description="Canonical article URL, if any.")
    link_domain: str | None = Field(description="Host of the canonical URL, if any.")
    source_name: str | None = Field(description="Publisher name, if known.")
    published_at: AwareDatetime | None = Field(description="Publication time, if known.")


class CascadeSummary(_V1Model):
    __doc__ = (
        "One tracked cascade with its completeness counts. " + CAPTION + " Counts are lower "
        "bounds of what happened on Bluesky; use them to flag for human review."
    )

    cascade_id: int = Field(description="Stable id of the cascade.")
    observed_since: AwareDatetime = Field(
        description=(
            "When the root post was observed: the cascade exists only from this moment "
            "(the earliest stored event when the root row itself was purged)."
        )
    )
    last_event_at: AwareDatetime = Field(description="Latest observed event (stream time).")
    tracking_ends_at: AwareDatetime = Field(
        description="When the collector stops attaching new events to this cascade."
    )
    event_count: int = Field(description="Stored events that are not deleted, the root included.")
    reply_count: int = Field(description="Stored replies that are not deleted.")
    quote_count: int = Field(description="Stored quote posts that are not deleted.")
    repost_count: int = Field(
        description="Stored reposts that are not deleted (an inferred fan-out, not a chain)."
    )
    unique_accounts: int = Field(description="Distinct pseudonymous accounts among the events.")
    max_depth: int = Field(description="Longest reply or quote chain connected to the root.")
    events_1h: int = Field(
        description="Events observed in the hour before rolled_up_at (the velocity sort key)."
    )
    orphan_count: int = Field(
        description="Events whose parent post was never stored (never re-parented to the root)."
    )
    disconnected_count: int = Field(
        description="Events not connected to the root through stored links (orphans and below)."
    )
    overflow_count: int = Field(
        description=(
            "A lower bound: at least this many events were not stored because the cascade "
            "reached its stored-event cap. Redelivery cannot inflate it; events delivered out "
            "of stream-time order may be missed, so it is never an exact count."
        )
    )
    deleted_count: int = Field(
        description="Events deleted by their authors (kept as content-free tombstones)."
    )
    order_violation_count: int = Field(
        description="Events observed before their own parent (counted, never repaired)."
    )
    root_deleted: bool = Field(
        description="True when the root post was deleted; such cascades are hidden by default."
    )
    claim: ClaimSummary | None = Field(
        description="The linked article, if any; always null when the root post was deleted."
    )
    root_text: str | None = Field(
        description=(
            "Text of the root post as plain text; null once the retention window purged it, "
            "or when the root was deleted."
        )
    )
    text_purged: bool = Field(description="True when the root text was removed by retention.")
    enrich_pending: bool = Field(
        description=(
            "True when events arrived after the last rollup: counts, depths and links may "
            "lag until the next enrich run."
        )
    )
    rolled_up_at: AwareDatetime | None = Field(
        description="Stream time the counts were computed as of; null before the first rollup."
    )


class EdgeKindCounts(_V1Model):
    """Stored events per edge kind; the four kinds plus deleted add up to every stored event."""

    root: int = Field(description="Root posts that are not deleted.")
    reply: int = Field(description="Replies that are not deleted.")
    quote: int = Field(description="Quote posts that are not deleted.")
    repost: int = Field(description="Reposts that are not deleted.")
    deleted: int = Field(description="Tombstones of every kind.")


class CascadeDetail(CascadeSummary):
    __doc__ = (
        "One cascade with its counts per edge kind, quarantined events and ingest gaps. " + CAPTION
    )

    counts_by_kind: EdgeKindCounts = Field(description="Stored events per edge kind.")
    invalid_count: int = Field(
        description="Events quarantined as invalid (a self-parent, a cycle or a repost parent)."
    )
    ingest_gaps: int = Field(
        description=(
            "Recorded ingest gaps that overlap the cascade's observed life: events in a gap "
            "were never seen."
        )
    )


class CascadePage(_V1Model):
    __doc__ = "One page of cascades in keyset order. " + CAPTION

    items: list[CascadeSummary] = Field(description="Cascades of this page, in the sort order.")
    next_cursor: str | None = Field(
        description="Opaque cursor of the next page; null on the last page."
    )
    limit: int = Field(description="Page size used for this page.")
    sort: CascadeSort = Field(
        description="recent: newest last_event_at first. velocity: most events_1h first."
    )
    meta: V1Meta


class CascadeResponse(_V1Model):
    __doc__ = "One cascade and its provenance. " + CAPTION

    cascade: CascadeDetail = Field(description="The cascade.")
    meta: V1Meta


class TreeNode(_V1Model):
    """One stored event of a cascade tree (no post text, no full identifier)."""

    event_id: int = Field(description="Stable id of the event within this API.")
    account: str | None = Field(
        max_length=ACCOUNT_PREFIX_LENGTH,
        description=(
            "First 8 characters of the account pseudonym (a keyed hash, not a handle); null "
            "for a deleted event."
        ),
    )
    edge_kind: EdgeKind = Field(description="root, reply, quote or repost.")
    inferred: bool = Field(
        description=(
            "True for reposts: the link to the subject is inferred fan-out and says nothing "
            "about who saw the post from whom."
        )
    )
    parent_state: ParentState = Field(
        description=(
            "none (root), resolved (parent stored), orphan (parent never stored) or invalid "
            "(quarantined)."
        )
    )
    observed_at: AwareDatetime = Field(description="When the event was observed (stream time).")
    depth: int | None = Field(
        description="Distance from the root along replies and quotes; null for reposts and "
        "events not connected to the root."
    )
    deleted: bool = Field(description="True for a tombstone (the author deleted the post).")


class TreeEdge(_V1Model):
    """A link between two shown nodes, from the parent to the child."""

    parent_id: int = Field(description="event_id of the parent node.")
    child_id: int = Field(description="event_id of the child node.")
    edge_kind: ChildKind = Field(description="Edge kind of the child: reply, quote or repost.")
    inferred: bool = Field(description="True for repost fan-out edges.")


class TreeRoot(_V1Model):
    """A node drawn as the top of a subtree."""

    event_id: int = Field(description="event_id of the node.")
    detached: bool = Field(
        description=(
            "False for the cascade's root post; true for a subtree whose parent is not shown "
            "(never stored, quarantined, filtered out or beyond the cap)."
        )
    )


class TreeResponse(_V1Model):
    __doc__ = (
        "A cascade tree in canonical order (observed_at, then depth), capped. " + CAPTION + " "
        "Use it to flag for human review; missing links are shown as detached subtrees."
    )

    cascade_id: int = Field(description="Id of the cascade.")
    nodes: list[TreeNode] = Field(description="Shown nodes in canonical order.")
    edges: list[TreeEdge] = Field(description="Links whose two ends are both shown.")
    roots: list[TreeRoot] = Field(
        description="The root post and every shown node whose parent is not shown."
    )
    shown: int = Field(description="Number of nodes returned.")
    total: int = Field(description="Number of nodes after the kinds filter, before the cap.")
    truncated: bool = Field(description="True when shown is less than total (showing N of M).")
    links_may_be_missing: bool = Field(
        description=(
            "True when the tree is truncated and some event was observed before its parent, so "
            "a shown node's parent may lie beyond the cap."
        )
    )
    enrich_pending: bool = Field(
        description=(
            "True while new events wait for enrich: their links are unresolved and they appear "
            "as detached subtrees."
        )
    )
    meta: V1Meta


class TimelineBucket(_V1Model):
    """Events observed in one bucket, per edge kind (deleted events are not counted)."""

    start: AwareDatetime = Field(description="Start of the bucket (inclusive), UTC.")
    root: int = Field(description="Root posts observed in the bucket.")
    reply: int = Field(description="Replies observed in the bucket.")
    quote: int = Field(description="Quote posts observed in the bucket.")
    repost: int = Field(description="Reposts observed in the bucket.")


class TimelineResponse(_V1Model):
    __doc__ = "Dense bucketed event counts of one cascade. " + CAPTION

    cascade_id: int = Field(description="Id of the cascade.")
    bucket_seconds: int = Field(description="Width of every bucket in seconds.")
    origin: AwareDatetime | None = Field(
        description="Start of the first bucket (the earliest stored event); null when empty."
    )
    buckets: list[TimelineBucket] = Field(
        description="Consecutive buckets from the first to the last event, zeros included."
    )
    meta: V1Meta


class LastRun(_V1Model):
    """The most recent collector run."""

    status: str = Field(description="Outcome of the run, for example completed or failed.")
    mode: SourceMode = Field(description="live or replay.")
    started_at: AwareDatetime = Field(description="When the run started (wall clock).")
    finished_at: AwareDatetime | None = Field(description="When it finished; null if running.")


class EventKindTotals(_V1Model):
    """Stored events per edge kind over every cascade (deleted events are not counted)."""

    root: int = Field(description="Root posts that are not deleted.")
    reply: int = Field(description="Replies that are not deleted.")
    quote: int = Field(description="Quote posts that are not deleted.")
    repost: int = Field(description="Reposts that are not deleted.")


class StatsResponse(_V1Model):
    __doc__ = (
        "Global counts computed from the cascade rollups and the run log. " + CAPTION + " "
        "The totals describe what was stored, to help flag for human review."
    )

    cascades_total: int = Field(description="Stored cascades.")
    cascades_with_deleted_root: int = Field(description="Cascades whose root post was deleted.")
    events_by_kind: EventKindTotals = Field(description="Stored events per edge kind.")
    events_total: int = Field(description="Stored events that are not deleted.")
    orphans_total: int = Field(description="Sum of orphan_count over every cascade.")
    disconnected_total: int = Field(description="Sum of disconnected_count over every cascade.")
    deleted_total: int = Field(description="Sum of deleted_count over every cascade.")
    observed_since: AwareDatetime | None = Field(
        description="Earliest stored observation (null when nothing is stored)."
    )
    ingest_lag_seconds: int | None = Field(
        description="Seconds between now and data_as_of; null when nothing was ever ingested."
    )
    ingest_gaps_total: int = Field(description="Gaps recorded by every collector run.")
    last_run: LastRun | None = Field(description="The most recent collector run, if any.")
    meta: V1Meta
