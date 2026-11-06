"""The pure cascade resolver (D-08, D-12, D-14, D-16, D-22; RESEARCH Pattern 7).

``resolve_cascade(rows, as_of)`` turns the stored rows of one cascade into parent states,
resolved parents, depths, a disconnected flag, the canonical order, the order violations and the
rollup counters (``rollup.py``). It reads no clock, no database and no randomness, and it never
raises on data.

Determinism contract: the result is a function of the SET of rows keyed by ``uri``. It does not
depend on arrival order, on surrogate ids (they are not an input) or on the wall clock
(``events_1h`` is computed as of the explicit ``as_of``). Every place where arrival order could
leak is a private module-level function, called through this module, so the mutation tests can
replace exactly one of them and prove the property test catches the leak:

- ``_choose_duplicate``: rows with the same ``uri`` collapse to the SMALLEST row by a total key
  (conflicting duplicates are resolved by value, never by arrival);
- ``_canonical_order``: ``core.cascade.order_events`` over values whose ``event_id`` is the uri
  key, so ties break on the uri whatever order the values arrive in;
- ``_cycle_members``: every member of a parent cycle, whichever node a walk starts from, and
  never the tail that leads into the cycle.

Rules (parents are never invented):

- a ``root`` row has state ``none`` and depth 0 (its ``parent_uri`` is ignored);
- a non-root whose ``parent_uri`` matches no row is ``orphan``: it keeps its cascade and is
  never re-parented to the root;
- a self-parent, every member of a cycle, a child whose parent row is a repost (a repost is
  never a parent) and a row of an unknown edge kind are ``invalid``: quarantined and counted,
  never fatal, with no resolved parent;
- every other non-root is ``resolved`` with the parent's uri;
- connectedness and depth come from a walk from the root rows over resolved reply and quote
  edges; a resolved row whose ancestors end at an orphan or an invalid row is ``resolved`` but
  ``disconnected`` with depth ``None``;
- a repost has no depth and hangs off its subject as an inferred fan-out leaf: connected when
  its subject is connected, orphan when the subject is missing;
- order violations (a child observed before its present parent) are counted with
  ``core.cascade.find_order_violations`` over the same values the order uses; they are never
  raised and never repaired by editing a timestamp (D-08).

Tombstones (``deleted``) stay in the structure: they keep their state, parent and depth, so the
skeleton stays connected, and only the counters leave them out (D-16, see ``rollup.py``).

A naive ``observed_at`` (the database never produces one) is read as UTC so the function cannot
raise on it; every timestamp in the result is UTC.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from truthtrail.core.cascade import CascadeEvent, find_order_violations, order_events
from truthtrail.enrich.rollup import Rollup, compute_rollup

EDGE_KINDS = frozenset({"root", "reply", "quote", "repost"})
PARENT_STATES = ("none", "resolved", "orphan", "invalid")
# Edges along which depth is measured (D-12): reposts are a fan-out, never a chain.
CHAIN_KINDS = frozenset({"reply", "quote"})


@dataclass(frozen=True)
class EventRow:
    """One stored row as the resolver sees it: the keyed uri, the edge facts, the stream time,
    the keyed account (``None`` for a tombstone) and the tombstone flag."""

    uri: str
    edge_kind: str
    parent_uri: str | None
    observed_at: datetime
    account: str | None
    deleted: bool


@dataclass(frozen=True)
class ResolvedNode:
    """The derived state of one row: ``state`` in none/resolved/orphan/invalid, the resolved
    parent uri, depth (``None`` for reposts, orphans, invalid and disconnected rows) and
    whether the row is disconnected from every root."""

    uri: str
    edge_kind: str
    state: str
    parent: str | None
    depth: int | None
    disconnected: bool
    observed_at: datetime
    account: str | None
    deleted: bool


@dataclass(frozen=True)
class ResolvedCascade:
    """The resolver's result. ``nodes`` is keyed by uri in sorted order; ``rows`` are the
    collapsed input rows (one per uri, sorted), so feeding them back yields the same result."""

    nodes: Mapping[str, ResolvedNode]
    order: tuple[str, ...]
    violations: tuple[str, ...]
    rollup: Rollup
    invalid_count: int
    duplicate_count: int
    rows: tuple[EventRow, ...]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _row_key(row: EventRow) -> tuple[object, ...]:
    """A total order on rows (``None`` sorts before every string, False before True)."""
    return (
        row.uri,
        row.edge_kind,
        row.parent_uri is not None,
        row.parent_uri or "",
        row.observed_at,
        row.account is not None,
        row.account or "",
        row.deleted,
    )


def _choose_duplicate(group: Sequence[EventRow]) -> EventRow:
    """The row kept for one uri: the smallest by ``_row_key`` (independent of arrival)."""
    return min(group, key=_row_key)


def _canonical_order(events: Sequence[CascadeEvent]) -> list[str]:
    """Uris in ``order_events`` order: ``(observed_at, known ancestors, uri)``.

    ``events`` arrive in input order; the key is total, so the result does not depend on it.
    """
    return [event.event_id for event in order_events(events)]


def _cycle_members(links: Mapping[str, str]) -> set[str]:
    """Every uri on a parent cycle of ``links`` (child uri -> parent uri), self-loops included.

    The walks start from the uris in sorted order and only the cycle itself is marked, never
    the tail that leads into it, so the result is the same whichever node a walk starts from.
    """
    on_cycle: set[str] = set()
    finished: set[str] = set()
    for start in sorted(links):
        path: list[str] = []
        position: dict[str, int] = {}
        current: str | None = start
        while current is not None and current not in finished:
            if current in position:
                on_cycle.update(path[position[current] :])
                break
            position[current] = len(path)
            path.append(current)
            current = links.get(current)
        finished.update(path)
    return on_cycle


def _collapse(rows: Iterable[EventRow]) -> tuple[dict[str, EventRow], int]:
    """One row per uri (in first-arrival order of the uris) and the number of extra rows."""
    groups: dict[str, list[EventRow]] = {}
    total = 0
    for row in rows:
        total += 1
        normalised = replace(row, observed_at=_utc(row.observed_at))
        groups.setdefault(normalised.uri, []).append(normalised)
    chosen = {uri: _choose_duplicate(group) for uri, group in groups.items()}
    return chosen, total - len(chosen)


def _initial_states(by_uri: Mapping[str, EventRow]) -> tuple[dict[str, str], dict[str, str]]:
    """Per-uri state before cycle detection and the attachable links (child -> parent)."""
    states: dict[str, str] = {}
    links: dict[str, str] = {}
    for uri, row in by_uri.items():
        if row.edge_kind == "root":
            states[uri] = "none"
            continue
        parent_uri = row.parent_uri
        if row.edge_kind not in EDGE_KINDS or parent_uri == uri:
            states[uri] = "invalid"
            continue
        parent = by_uri.get(parent_uri) if parent_uri is not None else None
        if parent is None or parent_uri is None:
            states[uri] = "orphan"
        elif parent.edge_kind == "repost":
            states[uri] = "invalid"
        else:
            states[uri] = "resolved"
            links[uri] = parent_uri
    return states, links


def _connected_depths(
    by_uri: Mapping[str, EventRow], states: Mapping[str, str], links: Mapping[str, str]
) -> tuple[set[str], dict[str, int]]:
    """Connected uris and the depth of every connected non-repost row (walk from the roots)."""
    children: dict[str, list[str]] = {}
    for child in sorted(links):
        if states[child] == "resolved":
            children.setdefault(links[child], []).append(child)
    connected: set[str] = set()
    depths: dict[str, int] = {}
    frontier = sorted(uri for uri, state in states.items() if state == "none")
    for uri in frontier:
        connected.add(uri)
        depths[uri] = 0
    while frontier:
        following: list[str] = []
        for parent in frontier:
            for child in children.get(parent, ()):
                if child in connected:
                    continue
                connected.add(child)
                if by_uri[child].edge_kind in CHAIN_KINDS:
                    depths[child] = depths[parent] + 1
                    following.append(child)
        frontier = following
    return connected, depths


def resolve_cascade(rows: Iterable[EventRow], as_of: datetime) -> ResolvedCascade:
    """Resolve one cascade's rows (see the module docstring for every rule)."""
    by_uri, duplicates = _collapse(rows)
    states, links = _initial_states(by_uri)
    for uri in _cycle_members(links):
        states[uri] = "invalid"
        del links[uri]
    connected, depths = _connected_depths(by_uri, states, links)

    nodes: dict[str, ResolvedNode] = {}
    for uri in sorted(by_uri):
        row = by_uri[uri]
        state = states[uri]
        nodes[uri] = ResolvedNode(
            uri=uri,
            edge_kind=row.edge_kind,
            state=state,
            parent=links.get(uri) if state == "resolved" else None,
            depth=depths.get(uri),
            disconnected=state != "none" and uri not in connected,
            observed_at=row.observed_at,
            account=row.account,
            deleted=row.deleted,
        )

    # Input order on purpose: the canonical order must not depend on it (see _canonical_order).
    events = [CascadeEvent(uri, nodes[uri].parent, by_uri[uri].observed_at) for uri in by_uri]
    order = tuple(_canonical_order(events))
    violations = tuple(find_order_violations(events))
    rollup = compute_rollup(
        nodes.values(), order_violation_count=len(violations), as_of=_utc(as_of)
    )
    return ResolvedCascade(
        nodes=nodes,
        order=order,
        violations=violations,
        rollup=rollup,
        invalid_count=sum(1 for n in nodes.values() if n.state == "invalid" and not n.deleted),
        duplicate_count=duplicates,
        rows=tuple(by_uri[uri] for uri in sorted(by_uri)),
    )
