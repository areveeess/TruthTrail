"""Unit table for the pure cascade resolver and its rollup (D-08, D-12, D-14, D-16, D-22).

Each test names one rule: orphans stay orphans and are never re-parented to the root, children
of orphans are resolved but disconnected, reposts are a fan-out with no depth and are never a
parent, self-parents and cycles are quarantined as invalid whichever node arrives first,
duplicates collapse by value, tombstones keep the structure but leave the counters, ``events_1h``
uses a half-open window over an explicit ``as_of``, and order violations are counted, never
repaired. No database: the resolver is a pure function.
"""

from datetime import UTC, datetime, timedelta
from itertools import permutations

import pytest

from truthtrail.core.cascade import CascadeEvent, find_order_violations
from truthtrail.db.models import Cascade
from truthtrail.enrich import rollup as rollup_module
from truthtrail.enrich.resolve import EventRow, ResolvedCascade, resolve_cascade

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
AS_OF = T0 + timedelta(hours=2)


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def row(
    uri: str,
    kind: str,
    parent: str | None,
    seconds: float = 0,
    account: str | None = "acct-a",
    *,
    deleted: bool = False,
) -> EventRow:
    return EventRow(uri, kind, parent, at(seconds), None if deleted else account, deleted)


def resolve(rows: list[EventRow], as_of: datetime = AS_OF) -> ResolvedCascade:
    return resolve_cascade(rows, as_of)


def summary(result: ResolvedCascade) -> dict[str, tuple[str, str | None, int | None, bool]]:
    return {
        uri: (node.state, node.parent, node.depth, node.disconnected)
        for uri, node in result.nodes.items()
    }


def test_a_simple_tree_has_depths_zero_one_two() -> None:
    result = resolve([row("r", "root", None), row("a", "reply", "r", 1), row("b", "reply", "a", 2)])
    assert summary(result) == {
        "r": ("none", None, 0, False),
        "a": ("resolved", "r", 1, False),
        "b": ("resolved", "a", 2, False),
    }
    assert result.rollup.max_depth == 2
    assert result.rollup.event_count == 3
    assert result.rollup.reply_count == 2
    assert result.order == ("r", "a", "b")


def test_reply_and_quote_chains_both_carry_depth() -> None:
    result = resolve(
        [
            row("r", "root", None),
            row("q1", "quote", "r", 1),
            row("a", "reply", "q1", 2),
            row("q2", "quote", "a", 3),
        ]
    )
    assert [result.nodes[u].depth for u in ("r", "q1", "a", "q2")] == [0, 1, 2, 3]
    assert result.rollup.quote_count == 2
    assert result.rollup.reply_count == 1
    assert result.rollup.max_depth == 3


def test_a_reply_whose_parent_is_missing_is_an_orphan_and_never_reparented() -> None:
    result = resolve([row("r", "root", None), row("a", "reply", "missing", 1)])
    node = result.nodes["a"]
    assert node.state == "orphan"
    assert node.parent is None  # not the root: no parent is invented
    assert node.depth is None
    assert node.disconnected is True
    assert result.rollup.orphan_count == 1
    assert result.rollup.disconnected_count == 1
    assert result.rollup.event_count == 2  # the orphan keeps its cascade


def test_a_reply_to_an_orphan_is_resolved_but_disconnected() -> None:
    result = resolve(
        [row("r", "root", None), row("a", "reply", "missing", 1), row("b", "reply", "a", 2)]
    )
    assert summary(result)["b"] == ("resolved", "a", None, True)
    assert result.rollup.orphan_count == 1
    assert result.rollup.disconnected_count == 2
    assert result.rollup.max_depth == 0


def test_a_repost_of_the_root_is_a_connected_fan_out_without_depth() -> None:
    result = resolve([row("r", "root", None), row("p", "repost", "r", 1, "acct-b")])
    assert summary(result)["p"] == ("resolved", "r", None, False)
    assert result.rollup.repost_count == 1
    assert result.rollup.max_depth == 0
    assert result.rollup.unique_accounts == 2


def test_a_repost_of_a_missing_subject_is_an_orphan() -> None:
    result = resolve([row("r", "root", None), row("p", "repost", "missing", 1)])
    assert summary(result)["p"] == ("orphan", None, None, True)
    assert result.rollup.orphan_count == 1


def test_a_repost_of_an_orphan_is_disconnected() -> None:
    result = resolve(
        [row("r", "root", None), row("a", "reply", "missing", 1), row("p", "repost", "a", 2)]
    )
    assert summary(result)["p"] == ("resolved", "a", None, True)
    assert result.rollup.disconnected_count == 2


@pytest.mark.parametrize("kind", ["repost", "reply", "quote"])
def test_a_child_whose_parent_row_is_a_repost_is_invalid(kind: str) -> None:
    result = resolve([row("r", "root", None), row("p", "repost", "r", 1), row("c", kind, "p", 2)])
    assert summary(result)["c"] == ("invalid", None, None, True)
    assert result.nodes["p"].state == "resolved"  # the repost itself is fine
    assert result.invalid_count == 1
    assert result.rollup.disconnected_count == 1


def test_a_self_parent_is_invalid_and_not_fatal() -> None:
    result = resolve([row("r", "root", None), row("s", "reply", "s", 1)])
    assert summary(result)["s"] == ("invalid", None, None, True)
    assert result.invalid_count == 1
    assert "s" in result.order


@pytest.mark.parametrize("arrival", list(permutations(["r", "x", "y"])))
def test_every_member_of_a_two_node_cycle_is_invalid_whatever_arrives_first(
    arrival: tuple[str, ...],
) -> None:
    rows = {
        "r": row("r", "root", None),
        "x": row("x", "reply", "y", 1),
        "y": row("y", "reply", "x", 2),
    }
    result = resolve([rows[u] for u in arrival])
    assert result.nodes["x"].state == "invalid"
    assert result.nodes["y"].state == "invalid"
    assert result.invalid_count == 2


@pytest.mark.parametrize("arrival", list(permutations(["x", "y", "z", "t"])))
def test_a_three_node_cycle_marks_every_member_but_never_its_tail(
    arrival: tuple[str, ...],
) -> None:
    rows = {
        "x": row("x", "reply", "y", 1),
        "y": row("y", "quote", "z", 2),
        "z": row("z", "reply", "x", 3),
        "t": row("t", "reply", "x", 4),  # the tail: points into the cycle
    }
    result = resolve([row("r", "root", None)] + [rows[u] for u in arrival])
    assert {u for u, n in result.nodes.items() if n.state == "invalid"} == {"x", "y", "z"}
    assert summary(result)["t"] == ("resolved", "x", None, True)
    assert result.rollup.disconnected_count == 4


def test_duplicate_uris_collapse_to_the_smallest_row_whatever_the_arrival() -> None:
    first = row("a", "reply", "r", 1, "acct-b")
    second = row("a", "reply", "r", 1, "acct-a")
    third = row("a", "reply", "r", 1, deleted=True)  # account None sorts first
    base = [row("r", "root", None)]
    results = [resolve(base + list(order)) for order in permutations([first, second, third])]
    assert all(r.rows == results[0].rows for r in results)
    kept = results[0].nodes["a"]
    assert kept.account is None
    assert kept.deleted is True
    assert results[0].duplicate_count == 2
    assert results[0].rollup.deleted_count == 1


def test_a_tombstone_keeps_structure_and_leaves_the_counters() -> None:
    rows = [
        row("r", "root", None, 0, "acct-a"),
        row("a", "reply", "r", 10, deleted=True),
        row("b", "reply", "a", 20, "acct-b"),
        row("p", "repost", "r", 30, deleted=True),
        row("o", "reply", "missing", 40, deleted=True),
    ]
    result = resolve(rows, as_of=at(60))
    assert summary(result)["a"] == ("resolved", "r", 1, False)
    assert summary(result)["b"] == ("resolved", "a", 2, False)  # still connected
    assert result.rollup.max_depth == 2
    assert result.rollup.event_count == 2
    assert result.rollup.reply_count == 1
    assert result.rollup.repost_count == 0
    assert result.rollup.unique_accounts == 2
    assert result.rollup.events_1h == 2
    assert result.rollup.orphan_count == 0  # the deleted orphan is not counted
    assert result.rollup.disconnected_count == 0
    assert result.rollup.deleted_count == 3


def test_a_tombstone_counts_toward_max_depth() -> None:
    rows = [row("r", "root", None), row("a", "reply", "r", 1), row("b", "reply", "a", 2)]
    rows[2] = row("b", "reply", "a", 2, deleted=True)
    assert resolve(rows).rollup.max_depth == 2


def test_events_1h_uses_a_half_open_window() -> None:
    as_of = at(7200)
    rows = [
        row("r", "root", None, 0),
        row("old", "reply", "r", 3600),  # exactly one hour before as_of: excluded
        row("in", "reply", "r", 3600.000001),
        row("now", "reply", "r", 7200),  # exactly as_of: included
        row("late", "reply", "r", 7200.000001),  # after as_of: excluded
    ]
    assert resolve(rows, as_of).rollup.events_1h == 2


def test_an_order_violation_is_counted_listed_and_not_repaired() -> None:
    rows = [row("r", "root", None, 10), row("early", "reply", "r", 5)]
    result = resolve(rows)
    assert result.violations == ("early",)
    assert result.rollup.order_violation_count == 1
    node = result.nodes["early"]
    assert (node.state, node.parent, node.depth) == ("resolved", "r", 1)
    assert node.observed_at == at(5)  # the timestamp is never edited
    assert result.order == ("early", "r")


def test_order_violations_match_find_order_violations_on_the_same_events() -> None:
    rows = [
        row("r", "root", None, 10),
        row("a", "reply", "r", 5),
        row("b", "reply", "a", 4),
        row("c", "reply", "r", 11),
    ]
    result = resolve(rows)
    events = [CascadeEvent(u, n.parent, n.observed_at) for u, n in result.nodes.items()]
    assert list(result.violations) == find_order_violations(events) == ["a", "b"]


def test_only_the_root_means_max_depth_zero() -> None:
    result = resolve([row("r", "root", None)])
    assert result.rollup.max_depth == 0
    assert result.rollup.event_count == 1
    assert summary(result) == {"r": ("none", None, 0, False)}


def test_first_and_last_event_at_skip_tombstones_unless_all_are_deleted() -> None:
    rows = [
        row("r", "root", None, 1),
        row("a", "reply", "r", 0, deleted=True),
        row("b", "reply", "r", 5),
        row("c", "reply", "r", 9, deleted=True),
    ]
    result = resolve(rows)
    assert (result.rollup.first_event_at, result.rollup.last_event_at) == (at(1), at(5))
    everything_deleted = [
        row("r", "root", None, 1, deleted=True),
        row("a", "reply", "r", 3, deleted=True),
    ]
    gone = resolve(everything_deleted)
    assert (gone.rollup.first_event_at, gone.rollup.last_event_at) == (at(1), at(3))
    assert gone.rollup.event_count == 0


def test_canonical_order_breaks_ties_on_the_uri_and_puts_parents_first() -> None:
    rows = [
        row("r", "root", None, 0),
        row("m", "reply", "r", 1),
        row("b", "reply", "r", 1),
        row("k", "reply", "m", 1),
        row("a", "repost", "r", 1),
    ]
    for order in permutations(rows):
        assert resolve(list(order)).order == ("r", "a", "b", "m", "k")


def test_an_empty_row_list_resolves_to_nothing() -> None:
    result = resolve([])
    assert result.nodes == {}
    assert result.order == ()
    assert result.rollup.event_count == 0
    assert result.rollup.first_event_at is None
    assert result.rollup.last_event_at is None
    assert result.rollup.max_depth == 0


def test_a_cascade_without_a_root_row_is_all_orphan_or_disconnected() -> None:
    rows = [
        row("a", "reply", "gone", 1),
        row("b", "reply", "a", 2),
        row("p", "repost", "gone", 3),
    ]
    result = resolve(rows)
    assert {n.state for n in result.nodes.values()} == {"orphan", "resolved"}
    assert all(n.disconnected for n in result.nodes.values())
    assert result.rollup.orphan_count == 2
    assert result.rollup.disconnected_count == 3
    assert result.rollup.max_depth == 0


def test_two_as_of_values_differ_only_in_events_1h() -> None:
    rows = [row("r", "root", None, 0), row("a", "reply", "r", 30), row("b", "reply", "r", 4000)]
    early = resolve(rows, at(60))
    late = resolve(rows, at(5_000))
    assert early.rollup.events_1h == 2
    assert late.rollup.events_1h == 1
    assert summary(early) == summary(late)
    assert early.order == late.order
    early_counters = {k: v for k, v in early.rollup.counters().items() if k != "events_1h"}
    late_counters = {k: v for k, v in late.rollup.counters().items() if k != "events_1h"}
    assert early_counters == late_counters


def test_an_unknown_edge_kind_is_invalid_not_fatal() -> None:
    result = resolve([row("r", "root", None), row("x", "like", "r", 1)])
    assert result.nodes["x"].state == "invalid"
    assert result.invalid_count == 1


def test_a_non_root_without_a_parent_reference_is_an_orphan() -> None:
    result = resolve([row("r", "root", None), row("x", "reply", None, 1)])
    assert summary(result)["x"] == ("orphan", None, None, True)


def test_a_naive_timestamp_is_read_as_utc_without_raising() -> None:
    naive = EventRow("a", "reply", "r", datetime(2026, 11, 1, 12, 0, 1), "acct-a", False)
    result = resolve([row("r", "root", None), naive])
    assert result.nodes["a"].observed_at == at(1)
    assert result.nodes["a"].observed_at.tzinfo == UTC


def test_unique_accounts_ignore_missing_and_deleted_accounts() -> None:
    rows = [
        row("r", "root", None, 0, "acct-a"),
        row("a", "reply", "r", 1, "acct-a"),
        row("b", "reply", "r", 2, None),
        row("c", "repost", "r", 3, "acct-c", deleted=True),
        row("d", "quote", "r", 4, "acct-d"),
    ]
    assert resolve(rows).rollup.unique_accounts == 2


def test_disconnected_count_covers_descendants_of_orphans_and_invalid_rows() -> None:
    rows = [
        row("r", "root", None),
        row("o", "reply", "gone", 1),
        row("o1", "reply", "o", 2),
        row("o2", "repost", "o1", 3),
        row("s", "reply", "s", 4),
        row("s1", "reply", "s", 5),
        row("ok", "reply", "r", 6),
    ]
    result = resolve(rows)
    assert result.rollup.disconnected_count == 5
    assert result.rollup.orphan_count == 1
    assert summary(result)["s1"] == ("resolved", "s", None, True)
    assert summary(result)["ok"] == ("resolved", "r", 1, False)


def test_several_root_rows_are_each_a_root() -> None:
    result = resolve(
        [row("r1", "root", None), row("r2", "root", None, 1), row("a", "reply", "r2", 2)]
    )
    assert summary(result)["r2"] == ("none", None, 0, False)
    assert summary(result)["a"] == ("resolved", "r2", 1, False)


def test_feeding_the_collapsed_rows_back_changes_nothing() -> None:
    rows = [row("r", "root", None), row("a", "reply", "r", 1), row("a", "reply", "r", 1, "acct-z")]
    first = resolve(rows)
    again = resolve(list(first.rows))
    assert summary(again) == summary(first)
    assert again.rollup == first.rollup
    assert again.duplicate_count == 0


def test_the_counters_are_cascade_columns() -> None:
    columns = set(Cascade.__table__.columns.keys())
    counters = resolve([row("r", "root", None)]).rollup.counters()
    assert set(counters) <= columns
    assert {"first_event_at", "last_event_at"} <= columns
    assert rollup_module.ROLLUP_VERSION >= 1
