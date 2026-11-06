"""Pure rollup counters of one resolved cascade (D-14, D-16, D-22).

Definitions (the verifier and the ``/v1`` API read exactly these):

- ``event_count``, ``reply_count``, ``quote_count``, ``repost_count``: NON-deleted rows (all
  kinds for ``event_count``, the root included).
- ``unique_accounts``: distinct non-null accounts over non-deleted rows.
- ``orphan_count``: non-deleted rows whose state is ``orphan``.
- ``disconnected_count``: non-deleted non-root rows that are not connected to a root through
  resolved edges: orphans, all their descendants, invalid rows and the descendants of invalid
  rows.
- ``deleted_count``: tombstones.
- ``max_depth``: the largest depth of a connected non-repost row, tombstones INCLUDED, because a
  tombstone keeps the skeleton connected; 0 when only the root (or nothing) is connected.
- ``order_violation_count``: the order violations over all rows (tombstones included), computed
  by the resolver with ``core.cascade.find_order_violations``.
- ``events_1h``: non-deleted rows observed in the half-open window ``(as_of - 1 hour, as_of]``;
  ``as_of`` is explicit, never the wall clock.
- ``first_event_at`` / ``last_event_at``: the earliest and latest ``observed_at`` of non-deleted
  rows, or of all rows when every row is deleted; ``None`` only for an empty cascade.

Tombstones count toward structure (depth, connectedness, ``max_depth``) but not toward the
counters. The invalid count is not a cascade column (D-20): it travels in the resolver result
and the run's log line, and the tree endpoint shows ``parent_state`` per node.

Standard library only; no clock, no randomness, no I/O.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

# Bumped whenever a definition above changes, so enrich recomputes every cascade whose stored
# rollup_version differs (apply.py selects them as work).
ROLLUP_VERSION = 1

VELOCITY_WINDOW = timedelta(hours=1)


class RolledNode(Protocol):
    """The facts of one resolved row the counters need (``resolve.ResolvedNode``)."""

    @property
    def edge_kind(self) -> str: ...

    @property
    def state(self) -> str: ...

    @property
    def depth(self) -> int | None: ...

    @property
    def disconnected(self) -> bool: ...

    @property
    def observed_at(self) -> datetime: ...

    @property
    def account(self) -> str | None: ...

    @property
    def deleted(self) -> bool: ...


@dataclass(frozen=True)
class Rollup:
    """The stored counters of one cascade (see the module docstring for each definition)."""

    event_count: int
    reply_count: int
    quote_count: int
    repost_count: int
    unique_accounts: int
    max_depth: int
    orphan_count: int
    disconnected_count: int
    deleted_count: int
    order_violation_count: int
    events_1h: int
    first_event_at: datetime | None
    last_event_at: datetime | None

    def counters(self) -> dict[str, int]:
        """The integer counters by column name, sorted by name."""
        values = {
            "deleted_count": self.deleted_count,
            "disconnected_count": self.disconnected_count,
            "event_count": self.event_count,
            "events_1h": self.events_1h,
            "max_depth": self.max_depth,
            "orphan_count": self.orphan_count,
            "order_violation_count": self.order_violation_count,
            "quote_count": self.quote_count,
            "reply_count": self.reply_count,
            "repost_count": self.repost_count,
            "unique_accounts": self.unique_accounts,
        }
        return dict(sorted(values.items()))


def in_velocity_window(observed_at: datetime, as_of: datetime) -> bool:
    """True when ``observed_at`` lies in ``(as_of - 1 hour, as_of]``."""
    return as_of - VELOCITY_WINDOW < observed_at <= as_of


def compute_rollup(
    nodes: Iterable[RolledNode], *, order_violation_count: int, as_of: datetime
) -> Rollup:
    """The counters of a cascade's resolved nodes as of ``as_of`` (never the wall clock)."""
    all_nodes = list(nodes)
    live = [n for n in all_nodes if not n.deleted]
    depths = [n.depth for n in all_nodes if n.depth is not None and n.edge_kind != "repost"]
    span = live or all_nodes
    times = [n.observed_at for n in span]
    return Rollup(
        event_count=len(live),
        reply_count=sum(1 for n in live if n.edge_kind == "reply"),
        quote_count=sum(1 for n in live if n.edge_kind == "quote"),
        repost_count=sum(1 for n in live if n.edge_kind == "repost"),
        unique_accounts=len({n.account for n in live if n.account is not None}),
        max_depth=max(depths, default=0),
        orphan_count=sum(1 for n in live if n.state == "orphan"),
        disconnected_count=sum(1 for n in live if n.disconnected),
        deleted_count=len(all_nodes) - len(live),
        order_violation_count=order_violation_count,
        events_1h=sum(1 for n in live if in_velocity_window(n.observed_at, as_of)),
        first_event_at=min(times, default=None),
        last_event_at=max(times, default=None),
    )
