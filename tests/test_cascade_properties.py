"""Property and unit tests for the cascade invariants (D-03, D-19, ROADMAP criterion 3).

For arbitrary generated cascades (forests built incrementally, timestamp ties included,
then shuffled), ``order_events`` must return a permutation sorted by ``observed_at`` in
which every present parent precedes its child, even on timestamp ties, and
``validate_cascade`` must accept valid cascades and reject a child observed before its
parent. The remaining behaviour lines are plain unit tests.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from truthtrail.core.cascade import (
    CascadeError,
    CascadeEvent,
    cascade_events_from,
    order_events,
    validate_cascade,
)
from truthtrail.schemas.models import Event

BASE = datetime(2026, 10, 11, 9, 30, tzinfo=UTC)

# 0 occurs often (timestamp ties), small values create near-ties and large values spread events.
DELTAS = st.one_of(
    st.just(0),
    st.integers(min_value=0, max_value=5),
    st.integers(min_value=0, max_value=10**9),
)


@st.composite
def cascades(draw: st.DrawFn, min_size: int = 0, max_size: int = 25) -> list[CascadeEvent]:
    """Build a forest incrementally: each event has no parent or picks an EARLIER event.

    Event ids are a drawn permutation, unrelated to creation order, so an id tie-break can
    never accidentally put a parent first.
    """
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    ids = draw(st.permutations(range(size)))
    events: list[CascadeEvent] = []
    for index in range(size):
        delta = timedelta(microseconds=draw(DELTAS))
        parent: CascadeEvent | None = None
        if events and draw(st.booleans()):
            parent = draw(st.sampled_from(events))
        observed_at = (parent.observed_at if parent else BASE) + delta
        events.append(
            CascadeEvent(
                event_id=f"id{ids[index]:04d}",
                parent_event_id=parent.event_id if parent else None,
                observed_at=observed_at,
            )
        )
    return events


@st.composite
def cascade_and_shuffle(draw: st.DrawFn) -> tuple[list[CascadeEvent], list[CascadeEvent]]:
    """Return a generated cascade together with a shuffled arrival order of the same events."""
    original = draw(cascades())
    return original, draw(st.permutations(original))


@given(cascades())
def test_order_is_sorted_permutation_with_parents_first(events: list[CascadeEvent]) -> None:
    """Property 1: a permutation, sorted by observed_at, every present parent before its child."""
    ordered = order_events(events)

    assert sorted(e.event_id for e in ordered) == sorted(e.event_id for e in events)
    assert all(a.observed_at <= b.observed_at for a, b in pairwise(ordered))
    position = {e.event_id: i for i, e in enumerate(ordered)}
    for event in ordered:
        if event.parent_event_id in position:
            assert position[event.parent_event_id] < position[event.event_id]


@given(cascade_and_shuffle())
def test_order_is_idempotent_and_independent_of_arrival_order(
    pair: tuple[list[CascadeEvent], list[CascadeEvent]],
) -> None:
    """Property 2: ordering twice changes nothing and arrival order never matters."""
    original, shuffled = pair

    assert order_events(shuffled) == order_events(original)
    assert order_events(order_events(original)) == order_events(original)


@given(cascades())
def test_generated_cascades_are_valid(events: list[CascadeEvent]) -> None:
    """Property 3: every generated cascade passes validation (also in shuffled order)."""
    validate_cascade(events)
    validate_cascade(order_events(events))
    validate_cascade(reversed(events))


@given(cascades(min_size=3), st.data())
def test_child_earlier_than_parent_is_rejected(
    events: list[CascadeEvent], data: st.DataObject
) -> None:
    """Property 4: moving a child one microsecond before its parent makes the cascade invalid."""
    by_id = {e.event_id: e for e in events}
    children = [e for e in events if e.parent_event_id is not None]
    assume(children)
    child = data.draw(st.sampled_from(children))
    assert child.parent_event_id is not None
    parent = by_id[child.parent_event_id]
    broken = replace(child, observed_at=parent.observed_at - timedelta(microseconds=1))
    mutated = [broken if e.event_id == child.event_id else e for e in events]

    with pytest.raises(CascadeError):
        validate_cascade(mutated)


def make(event_id: str, parent: str | None, offset_us: int = 0) -> CascadeEvent:
    return CascadeEvent(event_id, parent, BASE + timedelta(microseconds=offset_us))


def test_empty_input_gives_empty_list() -> None:
    assert order_events([]) == []
    validate_cascade([])


def test_order_events_does_not_mutate_its_input() -> None:
    events = [make("b", "a", 0), make("a", None, 0), make("c", "b", 5)]
    snapshot = list(events)

    ordered = order_events(events)

    assert events == snapshot
    assert ordered is not events
    assert [e.event_id for e in ordered] == ["a", "b", "c"]


def test_order_events_accepts_any_iterable() -> None:
    ordered = order_events(iter([make("b", "a", 1), make("a", None, 0)]))

    assert [e.event_id for e in ordered] == ["a", "b"]


def test_equal_timestamps_put_parent_before_child_even_when_child_id_sorts_first() -> None:
    events = [make("a-child", "z-parent", 0), make("z-parent", None, 0)]

    assert [e.event_id for e in order_events(events)] == ["z-parent", "a-child"]


def test_valid_cascade_with_equal_parent_and_child_timestamps() -> None:
    validate_cascade([make("a", None, 0), make("b", "a", 0)])


def test_orphan_with_absent_parent_is_tolerated() -> None:
    orphan = make("b", "missing", 7)
    events = [orphan, make("a", None, 3)]

    validate_cascade(events)
    assert [e.event_id for e in order_events(events)] == ["a", "b"]


def test_child_one_microsecond_before_parent_is_rejected() -> None:
    with pytest.raises(CascadeError):
        validate_cascade([make("a", None, 10), make("b", "a", 9)])


def test_duplicate_ids_are_rejected() -> None:
    events = [make("a", None, 0), make("a", None, 1)]

    with pytest.raises(CascadeError, match="duplicate"):
        validate_cascade(events)
    with pytest.raises(CascadeError):
        order_events(events)


def test_naive_observed_at_is_rejected() -> None:
    naive = CascadeEvent("a", None, datetime(2026, 10, 11, 9, 30))
    events = [naive, make("b", None, 0)]

    with pytest.raises(CascadeError, match="naive"):
        validate_cascade(events)
    with pytest.raises(CascadeError):
        order_events(events)


def test_self_parent_is_rejected() -> None:
    with pytest.raises(CascadeError):
        validate_cascade([make("a", "a", 0)])


def test_two_event_cycle_is_rejected_and_never_loops() -> None:
    events = [make("a", "b", 0), make("b", "a", 0)]

    with pytest.raises(CascadeError, match="cycle"):
        validate_cascade(events)
    with pytest.raises(CascadeError, match="cycle"):
        order_events(events)


def test_error_messages_carry_event_ids_only() -> None:
    with pytest.raises(CascadeError) as caught:
        validate_cascade([make("a", None, 10), make("b", "a", 9)])

    message = str(caught.value)
    assert "b" in message
    assert "2026" not in message


def test_adapter_parses_z_and_numeric_offsets_to_the_same_instant() -> None:
    zulu, plus_zero, shifted = cascade_events_from(
        [
            Event(
                event_id=name,
                platform="twitter",
                content_id="c",
                parent_event_id=None,
                user_id="u",
                timestamp=stamp,
                user_influence=1,
            )
            for name, stamp in (
                ("z", "2026-10-11T09:30:00Z"),
                ("p", "2026-10-11T09:30:00+00:00"),
                ("s", "2026-10-11T15:00:00+05:30"),
            )
        ]
    )

    assert zulu.observed_at == plus_zero.observed_at == shifted.observed_at
    assert shifted.observed_at == datetime(2026, 10, 11, 9, 30, tzinfo=UTC)
    assert shifted.observed_at.utcoffset() == timedelta(0)


def test_adapter_preserves_input_order_and_links() -> None:
    def event(name: str, parent: str | None, stamp: str) -> Event:
        return Event(
            event_id=name,
            platform="reddit",
            content_id="c",
            parent_event_id=parent,
            user_id="u",
            timestamp=stamp,
            user_influence=1,
        )

    converted = cascade_events_from(
        [event("b", "a", "2026-10-11T10:00:00Z"), event("a", None, "2026-10-11T09:00:00Z")]
    )

    assert [(e.event_id, e.parent_event_id) for e in converted] == [("b", "a"), ("a", None)]


@pytest.mark.parametrize("stamp", ["2026-10-11T09:30:00", "not a timestamp", "", "2026-13-45"])
def test_adapter_rejects_naive_or_unparseable_timestamps(stamp: str) -> None:
    bad = Event(
        event_id="e1",
        platform="twitter",
        content_id="c",
        parent_event_id=None,
        user_id="u",
        timestamp=stamp,
        user_influence=1,
    )

    with pytest.raises(CascadeError) as caught:
        cascade_events_from([bad])

    assert "e1" in str(caught.value)
    assert stamp not in str(caught.value) or stamp == ""
