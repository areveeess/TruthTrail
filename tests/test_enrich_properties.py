"""Order independence of the cascade resolver, proved with Hypothesis (SC4, D-22).

ROADMAP success criterion 4: shuffled arrival order of the same events yields identical state.
The properties run under the repository's profile (``--hypothesis-profile=ci``: 200
derandomized examples; the default ``dev`` profile is lighter) and compare a canonical
projection keyed by uri: per-uri state, resolved parent, depth and disconnected flag, the
rollup, the canonical order and the order violations.

The strategy matters more than the property (RESEARCH Pattern 7, pitfall 12). Its first version
drew parents from the whole id universe and added only identical duplicates; against it all
three mutants below SURVIVED 200 examples, because cycles, shared parents and value conflicts
almost never occurred. This version draws parents MOSTLY from inside the drawn set (so chains,
shared parents, cycles with tails and children of reposts are common), uses a few seconds of
timestamps with microsecond 0 or 1 (many ties), a tiny account alphabet, tombstones, and appends
both identical and CONFLICTING duplicate deliveries (same uri, different account or deleted
flag). Each mutant replaces ONE private function of ``truthtrail.enrich.resolve`` with an
arrival-dependent variant, and its test wraps the property in ``pytest.raises(AssertionError)``
so the guard cannot rot silently:

1. ``_choose_duplicate``: the first delivered duplicate wins;
2. ``_canonical_order``: ties broken without the uri, in arrival order (a stable sort on
   ``(observed_at, depth)`` over the input order);
3. ``_cycle_members``: walks start in arrival order and mark the whole path, so a tail that
   leads into a cycle becomes invalid only when a walk happens to start on it.

The mutation tests set their own settings (200 derandomized examples) so they do not depend on
the profile.
"""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from hypothesis import find, given, settings
from hypothesis import strategies as st

from truthtrail.core import cascade as core_cascade
from truthtrail.core.cascade import CascadeEvent, find_order_violations
from truthtrail.enrich import resolve as resolve_module
from truthtrail.enrich.resolve import PARENT_STATES, EventRow, ResolvedCascade, resolve_cascade

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
AS_OF = T0 + timedelta(seconds=3)
IDS = tuple(f"u{i:02d}" for i in range(12))
KINDS = ("root", "reply", "reply", "quote", "repost")
ACCOUNTS = (None, "a", "b", "c")
MUTANT_SETTINGS = settings(max_examples=200, derandomize=True, database=None, deadline=None)


@st.composite
def cascade_rows(draw: st.DrawFn) -> list[EventRow]:
    size = draw(st.integers(min_value=1, max_value=10))
    ids = list(draw(st.permutations(IDS)))[:size]
    # Mostly INSIDE the drawn set (cycles, chains, shared parents), sometimes outside (orphans).
    pool: list[str | None] = [*ids * 4, *IDS, None]
    rows: list[EventRow] = []
    for uri in ids:
        kind = draw(st.sampled_from(KINDS))
        parent = None if kind == "root" else draw(st.sampled_from(pool))
        observed = T0 + timedelta(
            seconds=draw(st.integers(min_value=0, max_value=6)),
            microseconds=draw(st.sampled_from([0, 1])),
        )
        deleted = draw(st.sampled_from([False, False, False, True]))
        account = None if deleted else draw(st.sampled_from(ACCOUNTS))
        rows.append(EventRow(uri, kind, parent, observed, account, deleted))
    rows += draw(st.lists(st.sampled_from(rows), max_size=3))  # identical redeliveries
    rows += draw(
        st.lists(
            st.builds(
                lambda r, account, deleted: replace(r, account=account, deleted=deleted),
                st.sampled_from(rows),
                st.sampled_from(ACCOUNTS),
                st.booleans(),
            ),
            max_size=2,
        )
    )  # CONFLICTING duplicates: same uri, different values
    return rows


def projection(result: ResolvedCascade) -> tuple[Any, ...]:
    """Everything the database and the API will show, keyed by uri."""
    nodes = {
        uri: (node.state, node.parent, node.depth, node.disconnected)
        for uri, node in sorted(result.nodes.items())
    }
    return (nodes, result.rollup, result.order, result.violations, result.invalid_count)


def check_order_independent(rows: list[EventRow], data: st.DataObject) -> None:
    shuffled = data.draw(st.permutations(rows))
    assert projection(resolve_cascade(rows, AS_OF)) == projection(resolve_cascade(shuffled, AS_OF))


@given(rows=cascade_rows(), data=st.data())
def test_shuffled_arrival_yields_identical_state(rows: list[EventRow], data: st.DataObject) -> None:
    check_order_independent(rows, data)


def _ancestors_terminate(nodes: Mapping[str, Any]) -> bool:
    for start in nodes:
        seen: set[str] = set()
        current: str | None = start
        while current is not None:
            if current in seen:
                return False
            seen.add(current)
            current = nodes[current].parent
    return True


@given(rows=cascade_rows())
def test_the_output_satisfies_the_cascade_invariants(rows: list[EventRow]) -> None:
    result = resolve_cascade(rows, AS_OF)
    nodes = result.nodes
    assert {n.state for n in nodes.values()} <= set(PARENT_STATES)
    assert _ancestors_terminate(nodes)  # the resolved parent graph has no cycle
    live = [n for n in nodes.values() if not n.deleted]
    assert result.rollup.orphan_count == sum(1 for n in live if n.state == "orphan")
    assert result.rollup.event_count == len(live)
    assert result.rollup.deleted_count == len(nodes) - len(live)
    for node in nodes.values():
        if node.edge_kind == "repost":
            assert node.depth is None
        if node.state == "none":
            assert node.depth == 0
            assert node.parent is None
            assert not node.disconnected
        if node.state in {"orphan", "invalid"}:
            assert node.parent is None
            assert node.depth is None
            assert node.disconnected
        if node.state == "resolved":
            assert node.parent in nodes
            assert nodes[node.parent].edge_kind != "repost"  # a repost is never a parent
            if node.edge_kind != "repost" and not node.disconnected:
                parent_depth = nodes[node.parent].depth
                assert parent_depth is not None
                assert node.depth == parent_depth + 1
        if node.edge_kind != "repost" and node.state != "none":
            assert node.disconnected == (node.depth is None)
    # Ordered by observed_at; a present parent precedes its child except counted violations.
    assert sorted(result.order) == sorted(nodes)
    times = [nodes[u].observed_at for u in result.order]
    assert times == sorted(times)
    position = {uri: i for i, uri in enumerate(result.order)}
    for node in nodes.values():
        if node.parent is not None and position[node.parent] > position[node.uri]:
            assert node.uri in result.violations
    events = [CascadeEvent(u, n.parent, n.observed_at) for u, n in nodes.items()]
    assert list(result.violations) == find_order_violations(events)
    assert result.rollup.order_violation_count == len(result.violations)


@given(rows=cascade_rows())
def test_feeding_the_output_rows_back_is_idempotent(rows: list[EventRow]) -> None:
    first = resolve_cascade(rows, AS_OF)
    again = resolve_cascade(list(first.rows), AS_OF)
    assert projection(again) == projection(first)
    assert again.rows == first.rows
    assert again.duplicate_count == 0
    assert first.duplicate_count == len(rows) - len(first.rows)


# --- The strategy reaches the hard cases (a weak strategy is pitfall 12) ---------------------
FIND_SETTINGS = settings(max_examples=500, derandomize=True, database=None, deadline=None)


def _has_cycle_with_tail(rows: list[EventRow]) -> bool:
    result = resolve_cascade(rows, AS_OF)
    invalid = {u for u, n in result.nodes.items() if n.state == "invalid"}
    return any(n.state == "resolved" and n.parent in invalid for n in result.nodes.values())


def _has_conflicting_duplicate(rows: list[EventRow]) -> bool:
    by_uri: dict[str, set[EventRow]] = {}
    for item in rows:
        by_uri.setdefault(item.uri, set()).add(item)
    return any(len(group) > 1 for group in by_uri.values())


def _has_tie_with_violation(rows: list[EventRow]) -> bool:
    result = resolve_cascade(rows, AS_OF)
    times = [n.observed_at for n in result.nodes.values()]
    return len(set(times)) < len(times) and bool(result.violations)


@pytest.mark.parametrize(
    "predicate", [_has_cycle_with_tail, _has_conflicting_duplicate, _has_tie_with_violation]
)
def test_the_strategy_produces_the_hard_cases(predicate: Any) -> None:
    assert predicate(find(cascade_rows(), predicate, settings=FIND_SETTINGS))


# --- Mutants: each must be caught -----------------------------------------------------------
def _first_duplicate_wins(group: Sequence[EventRow]) -> EventRow:
    return group[0]


def _tie_break_without_uri(events: Sequence[CascadeEvent]) -> list[str]:
    by_id = {e.event_id: e for e in events}

    def depth(event: CascadeEvent) -> int:
        count, parent = 0, event.parent_event_id
        while parent is not None and parent in by_id:
            count, parent = count + 1, by_id[parent].parent_event_id
        return count

    return [e.event_id for e in sorted(events, key=lambda e: (e.observed_at, depth(e)))]


def _cycle_tail_from_arrival(links: Mapping[str, str]) -> set[str]:
    marked: set[str] = set()
    finished: set[str] = set()
    for start in links:  # arrival order, not sorted
        path: list[str] = []
        current: str | None = start
        while current is not None and current not in finished:
            if current in path:
                marked.update(path)  # the whole walk, tail included
                break
            path.append(current)
            current = links.get(current)
        finished.update(path)
    return marked


def _run_property_against(monkeypatch: pytest.MonkeyPatch, name: str, mutant: Any) -> None:
    monkeypatch.setattr(resolve_module, name, mutant)

    @MUTANT_SETTINGS
    @given(rows=cascade_rows(), data=st.data())
    def property_under_mutation(rows: list[EventRow], data: st.DataObject) -> None:
        check_order_independent(rows, data)

    with pytest.raises(AssertionError):
        property_under_mutation()


def test_the_first_duplicate_wins_mutant_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    _run_property_against(monkeypatch, "_choose_duplicate", _first_duplicate_wins)


def test_the_tie_break_without_uri_mutant_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    _run_property_against(monkeypatch, "_canonical_order", _tie_break_without_uri)


def test_the_arrival_chosen_cycle_tail_mutant_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    _run_property_against(monkeypatch, "_cycle_members", _cycle_tail_from_arrival)


def test_the_unmutated_resolver_passes_the_same_settings() -> None:
    @MUTANT_SETTINGS
    @given(rows=cascade_rows(), data=st.data())
    def property_unmutated(rows: list[EventRow], data: st.DataObject) -> None:
        check_order_independent(rows, data)

    property_unmutated()


def test_the_resolver_never_calls_the_raising_validator(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("validate_cascade must not be used by enrich")

    monkeypatch.setattr(core_cascade, "validate_cascade", refuse)
    rows = [
        EventRow("r", "root", None, T0, "a", False),
        EventRow("x", "reply", "y", T0, "a", False),
        EventRow("y", "reply", "x", T0, "a", False),
    ]
    assert resolve_cascade(rows, AS_OF).invalid_count == 2
