"""``find_order_violations``: the non-raising order-violation counter beside ``validate_cascade``.

D-08: on real stream data a child observed before its parent is a counted data-quality metric,
never a database constraint and never "fixed" by editing a timestamp. The raising
``validate_cascade`` stays the fixture gate; this function returns the violating ids instead.
Cycles and self-parents are quarantined by the caller (enrich), so they never raise here and are
not reported as order violations. The input contract (duplicate ids, naive datetimes) still raises.
"""

import random
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st
from test_cascade_properties import cascades

from truthtrail.core.cascade import (
    CascadeError,
    CascadeEvent,
    find_order_violations,
    validate_cascade,
)

BASE = datetime(2026, 10, 19, 7, 42, tzinfo=UTC)


def ev(event_id: str, parent: str | None, seconds: float) -> CascadeEvent:
    return CascadeEvent(event_id, parent, BASE + timedelta(seconds=seconds))


def test_a_valid_cascade_has_no_violation() -> None:
    events = [ev("root", None, 0), ev("a", "root", 1), ev("b", "a", 2), ev("c", "root", 3)]
    assert find_order_violations(events) == []


def test_one_child_observed_before_its_parent_is_reported_not_raised() -> None:
    events = [ev("root", None, 10), ev("a", "root", 5), ev("b", "a", 20)]
    assert find_order_violations(events) == ["a"]
    with pytest.raises(CascadeError):
        validate_cascade(events)


def test_equal_timestamps_are_not_a_violation() -> None:
    events = [ev("root", None, 0), ev("a", "root", 0), ev("b", "a", 0)]
    assert find_order_violations(events) == []


def test_orphans_are_ignored() -> None:
    events = [ev("a", "missing", 0), ev("b", "a", 1)]
    assert find_order_violations(events) == []


def test_several_violations_come_back_sorted() -> None:
    events = [ev("root", None, 100), ev("z", "root", 1), ev("m", "root", 2), ev("a", "root", 3)]
    assert find_order_violations(events) == ["a", "m", "z"]


def test_a_self_parent_does_not_raise_and_is_not_reported() -> None:
    events = [ev("self", "self", 0), ev("root", None, 0)]
    assert find_order_violations(events) == []
    with pytest.raises(CascadeError):
        validate_cascade(events)


def test_a_cycle_does_not_raise_and_is_not_reported() -> None:
    # a -> b -> c -> a, with times that would be violations if the cycle were walked.
    events = [ev("a", "c", 5), ev("b", "a", 1), ev("c", "b", 9), ev("d", "c", 3)]
    # d hangs below the cycle but is not on it: its present parent c is observed later.
    assert find_order_violations(events) == ["d"]
    with pytest.raises(CascadeError):
        validate_cascade(events)


def test_duplicate_ids_still_raise() -> None:
    with pytest.raises(CascadeError, match="duplicate event id a"):
        find_order_violations([ev("a", None, 0), ev("a", None, 1)])


def test_naive_datetimes_still_raise() -> None:
    naive = CascadeEvent("a", None, datetime(2026, 1, 1))
    with pytest.raises(CascadeError, match="naive observed_at on event a"):
        find_order_violations([naive])


def test_the_input_is_not_modified_and_a_generator_is_accepted() -> None:
    events = [ev("root", None, 10), ev("a", "root", 5)]
    snapshot = list(events)
    assert find_order_violations(e for e in events) == ["a"]
    assert events == snapshot


# ----------------------------------------------------------------------------- properties


@given(cascades(), st.randoms(use_true_random=False))
def test_result_is_independent_of_input_order(
    events: list[CascadeEvent], rnd: random.Random
) -> None:
    shuffled = list(events)
    rnd.shuffle(shuffled)
    assert find_order_violations(shuffled) == find_order_violations(events)


@given(cascades())
def test_a_generated_valid_cascade_has_no_violation(events: list[CascadeEvent]) -> None:
    # The generator builds parents before children with non-negative deltas: always valid.
    validate_cascade(events)
    assert find_order_violations(events) == []


@given(cascades(min_size=2), st.data())
def test_empty_exactly_when_validate_cascade_accepts(
    events: list[CascadeEvent], data: st.DataObject
) -> None:
    # Move one event's time freely; the cascade stays acyclic, so validate_cascade decides.
    index = data.draw(st.integers(min_value=0, max_value=len(events) - 1))
    shift = data.draw(st.integers(min_value=-(10**9), max_value=10**9))
    moved = list(events)
    target = moved[index]
    moved[index] = CascadeEvent(
        target.event_id, target.parent_event_id, target.observed_at + timedelta(microseconds=shift)
    )
    found = find_order_violations(moved)
    try:
        validate_cascade(moved)
    except CascadeError:
        accepted = False
    else:
        accepted = True
    assert (found == []) is accepted
    assert found == sorted(found)


@given(
    st.lists(st.integers(min_value=0, max_value=6), min_size=1, max_size=12),
    st.lists(st.integers(min_value=0, max_value=10**6), min_size=12, max_size=12),
)
def test_never_raises_for_arbitrary_parent_links(parents: list[int], deltas: list[int]) -> None:
    # Every event may point at any id (itself included), so cycles and self-parents occur.
    events = [
        CascadeEvent(f"e{i}", f"e{p}", BASE + timedelta(microseconds=deltas[i]))
        for i, p in enumerate(parents)
    ]
    found = find_order_violations(events)
    assert found == sorted(found)
    assert set(found) <= {e.event_id for e in events}
