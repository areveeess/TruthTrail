"""Cascade invariants as pure, standard-library-only functions (D-03, D-19).

A cascade is a set of events linked by ``parent_event_id``. Two invariants hold for any
cascade that is shown as analysis:

* events are ordered by ``observed_at``, and on equal timestamps a parent precedes its
  child (``order_events``);
* a child is never observed earlier than its parent (``validate_cascade``).

A parent that is not in the set is tolerated: an orphan is an explicit state and a missing
parent is never invented. Duplicate ids, naive datetimes, self-parents and parent cycles are
rejected with ``CascadeError``.

D-19: the committed demo fixture lists events per platform chain, not by timestamp. The
served demo body is therefore validated here but never reordered, so it stays equal to the
committed fixture. Real data (Phase 3) is served through ``order_events``.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


class CascadeError(ValueError):
    """A cascade violates an invariant. Messages name event ids only, never event content."""


@dataclass(frozen=True)
class CascadeEvent:
    """The ordering view of one event: identity, optional parent and a timezone-aware instant."""

    event_id: str
    parent_event_id: str | None
    observed_at: datetime


class HasTimestamp(Protocol):
    """Structural view of an event whose time is an ISO-8601 string (``schemas.Event``)."""

    @property
    def event_id(self) -> str: ...

    @property
    def parent_event_id(self) -> str | None: ...

    @property
    def timestamp(self) -> str: ...


def cascade_events_from(events: Iterable[HasTimestamp]) -> list[CascadeEvent]:
    """Convert objects with an ISO ``timestamp`` into ``CascadeEvent`` views, in input order.

    Offsets are normalised to UTC. A naive or unparseable timestamp raises ``CascadeError``.
    """
    converted: list[CascadeEvent] = []
    for event in events:
        try:
            parsed = datetime.fromisoformat(event.timestamp)
        except ValueError:
            raise CascadeError(f"unparseable timestamp on event {event.event_id}") from None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise CascadeError(f"naive timestamp on event {event.event_id}")
        converted.append(
            CascadeEvent(event.event_id, event.parent_event_id, parsed.astimezone(UTC))
        )
    return converted


def _index(events: Iterable[CascadeEvent]) -> dict[str, CascadeEvent]:
    """Map ids to events, rejecting duplicate ids and naive datetimes."""
    by_id: dict[str, CascadeEvent] = {}
    for event in events:
        if event.event_id in by_id:
            raise CascadeError(f"duplicate event id {event.event_id}")
        if event.observed_at.tzinfo is None or event.observed_at.utcoffset() is None:
            raise CascadeError(f"naive observed_at on event {event.event_id}")
        by_id[event.event_id] = event
    return by_id


def _depths(by_id: dict[str, CascadeEvent]) -> dict[str, int]:
    """Number of known ancestors per event; a missing parent ends the chain.

    An explicit path set detects a self-parent or any cycle instead of looping forever.
    """
    depths: dict[str, int] = {}
    for start in by_id:
        if start in depths:
            continue
        path: list[str] = []
        on_path: set[str] = set()
        current = start
        base = -1
        while True:
            if current in depths:
                base = depths[current]
                break
            if current in on_path:
                raise CascadeError(f"parent cycle through event {current}")
            on_path.add(current)
            path.append(current)
            parent = by_id[current].parent_event_id
            if parent is None or parent not in by_id:
                break
            current = parent
        depth = base
        for event_id in reversed(path):
            depth += 1
            depths[event_id] = depth
    return depths


def order_events(events: Iterable[CascadeEvent]) -> list[CascadeEvent]:
    """Return a new list ordered by ``(observed_at, depth, event_id)``; the input is untouched.

    ``depth`` is the number of known ancestors, so on equal timestamps a parent precedes its
    child. The key is total for unique ids, so the result does not depend on arrival order.
    Raises ``CascadeError`` for duplicate ids, naive datetimes, self-parents and cycles.
    """
    by_id = _index(events)
    depths = _depths(by_id)
    return sorted(by_id.values(), key=lambda e: (e.observed_at, depths[e.event_id], e.event_id))


def validate_cascade(events: Iterable[CascadeEvent]) -> None:
    """Raise ``CascadeError`` unless the cascade satisfies every invariant.

    Rejects duplicate ids, naive ``observed_at``, a self-parent or parent cycle, and a present
    parent observed later than its child. Equal timestamps are valid; orphans are tolerated.
    """
    by_id = _index(events)
    _depths(by_id)
    for event in by_id.values():
        parent = by_id.get(event.parent_event_id) if event.parent_event_id is not None else None
        if parent is not None and parent.observed_at > event.observed_at:
            raise CascadeError(f"event {event.event_id} is observed before its parent")
