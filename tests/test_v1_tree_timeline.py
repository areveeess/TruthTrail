"""``GET /v1/cascades/{id}/tree`` and ``/timeline`` (D-12, D-14, D-23, RESEARCH F-15, F-16,
threats T-03-46 and T-03-48).

Constructed forests are inserted by direct parameterised SQL (``insert_forest``) and enriched
with an explicit ``as_of``; the fixture cascades come from the shared seeded database. Tree
invariants: edges join shown nodes, nodes arrive in canonical order, reposts are inferred
fan-out leaves, tombstones carry no account, orphan subtrees are detached roots, the cap keeps a
prefix that is closed under ancestors unless an order violation exists (then
``links_may_be_missing``), and the kinds filter detaches subtrees. Timeline invariants: the
buckets sum to the non-deleted counts, the series is dense, the width follows the ladder, the
bucket count never exceeds the bound, and the session time zone changes nothing.
"""

import itertools
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from conftest import insert_forest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from truthtrail.api.v1_cascades import BUCKET_LADDER_SECONDS, choose_bucket_seconds

pytestmark = pytest.mark.requires_db

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
S = timedelta(seconds=1)


@pytest.fixture(scope="module")
def seeded(seeded_db_url: str) -> Iterator[Engine]:
    engine = create_engine(seeded_db_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


def rows(engine: Engine, sql: str, **params: Any) -> list[Any]:
    with engine.connect() as connection:
        return list(connection.execute(text(sql), params))


def build(
    engine: Engine, forest: list[Any], root: str, *, enrich: bool = True, id_base: int = 1000
) -> int:
    from truthtrail.enrich.apply import enrich_dirty

    cascade_id = insert_forest(engine, forest, root_uri=root, id_base=id_base)
    if enrich:
        latest = max(r[3] for r in forest)
        result = enrich_dirty(engine, as_of=latest + S)
        assert result.errors == {}
    return cascade_id


def tree(client: Any, cascade_id: int, **params: Any) -> dict[str, Any]:
    response = client.get(f"/v1/cascades/{cascade_id}/tree", params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def assert_tree_invariants(body: dict[str, Any]) -> None:
    nodes = {n["event_id"]: n for n in body["nodes"]}
    assert len(nodes) == len(body["nodes"]) == body["shown"]
    assert body["truncated"] == (body["shown"] < body["total"])
    children = set()
    for edge in body["edges"]:
        assert edge["parent_id"] in nodes
        assert edge["child_id"] in nodes
        assert edge["edge_kind"] == nodes[edge["child_id"]]["edge_kind"]
        assert edge["inferred"] == (edge["edge_kind"] == "repost")
        assert nodes[edge["parent_id"]]["edge_kind"] != "repost"  # a repost is never a parent
        assert edge["child_id"] not in children  # one parent per node
        children.add(edge["child_id"])
    roots = {r["event_id"]: r for r in body["roots"]}
    # Every shown node is either a child of a shown node or a root, never both.
    assert set(nodes) == children | set(roots)
    assert children.isdisjoint(roots)
    for event_id, root in roots.items():
        assert root["detached"] == (nodes[event_id]["edge_kind"] != "root")
    order = [n["event_id"] for n in body["nodes"]]
    times = [datetime.fromisoformat(n["observed_at"]) for n in body["nodes"]]
    assert times == sorted(times)
    position = {event_id: index for index, event_id in enumerate(order)}
    for node in body["nodes"]:
        assert node["account"] is None or len(node["account"]) <= 8
        if node["deleted"]:
            assert node["account"] is None
        if node["edge_kind"] == "repost":
            assert node["inferred"] is True
            assert node["depth"] is None
    if not body["links_may_be_missing"]:
        for edge in body["edges"]:
            if times[position[edge["parent_id"]]] <= times[position[edge["child_id"]]]:
                assert position[edge["parent_id"]] < position[edge["child_id"]]


# --- the fixture cascades -----------------------------------------------------------------------
def test_every_fixture_tree_holds_the_invariants(
    v1_client: Callable[..., Any], seeded_db_url: str, seeded: Engine
) -> None:
    client = v1_client(seeded_db_url)
    reposts = 0
    for (cascade_id,) in rows(seeded, "SELECT id FROM cascades ORDER BY id"):
        body = tree(client, cascade_id)
        assert_tree_invariants(body)
        assert body["total"] == body["shown"]
        assert body["truncated"] is False
        assert body["links_may_be_missing"] is False
        assert body["enrich_pending"] is False
        stored = {
            r.id: r
            for r in rows(
                seeded,
                "SELECT e.id, e.parent_event_id, e.parent_state, e.depth, e.deleted_at,"
                " a.pseudonym FROM events e LEFT JOIN accounts a ON a.id = e.account_id"
                " WHERE e.cascade_id = :c",
                c=cascade_id,
            )
        }
        assert {n["event_id"] for n in body["nodes"]} == set(stored)
        edges = {(e["parent_id"], e["child_id"]) for e in body["edges"]}
        for node in body["nodes"]:
            row = stored[node["event_id"]]
            assert node["parent_state"] == row.parent_state
            assert node["depth"] == row.depth
            assert node["deleted"] == (row.deleted_at is not None)
            if row.pseudonym is not None and row.deleted_at is None:
                assert node["account"] == row.pseudonym[:8]
            if row.parent_state == "resolved":
                assert (row.parent_event_id, row.id) in edges
            if node["edge_kind"] == "repost":
                reposts += 1
    assert reposts > 0


def test_the_fixture_orphan_is_a_detached_root(
    v1_client: Callable[..., Any], seeded_db_url: str, seeded: Engine
) -> None:
    orphan = rows(seeded, "SELECT id, cascade_id FROM events WHERE parent_state = 'orphan'")
    assert orphan
    client = v1_client(seeded_db_url)
    for event_id, cascade_id in orphan:
        roots = {r["event_id"]: r["detached"] for r in tree(client, cascade_id)["roots"]}
        assert roots[event_id] is True
        assert False in roots.values()  # the real root is listed too


# --- constructed forests ------------------------------------------------------------------------
def forest_with_everything() -> list[Any]:
    """root R; reply A (R); quote Q (A); reposts P1, P2 of R; tombstone reply D (R); child of the
    tombstone C (D); orphan O (missing parent); child of the orphan O2 (O)."""
    return [
        ("f-R", "root", None, T0, "acct-r-longer-1", False),
        ("f-A", "reply", "f-R", T0 + 1 * S, "acct-a-longer-1", False),
        ("f-Q", "quote", "f-A", T0 + 2 * S, "acct-q-longer-1", False),
        ("f-P1", "repost", "f-R", T0 + 3 * S, "acct-p1-longer1", False),
        ("f-P2", "repost", "f-R", T0 + 4 * S, "acct-p2-longer1", False),
        ("f-D", "reply", "f-R", T0 + 5 * S, "acct-d-longer-1", True),
        ("f-C", "reply", "f-D", T0 + 6 * S, "acct-c-longer-1", False),
        ("f-O", "reply", "f-ghost", T0 + 7 * S, "acct-o-longer-1", False),
        ("f-O2", "reply", "f-O", T0 + 8 * S, "acct-o2-longer1", False),
    ]


def ids_by_uri(engine: Engine, cascade_id: int) -> dict[str, int]:
    return dict(rows(engine, "SELECT uri, id FROM events WHERE cascade_id = :c", c=cascade_id))


def test_a_constructed_forest_has_every_node_kind(
    v1_client: Callable[..., Any], make_engine: Callable[..., Engine], clean_db: str
) -> None:
    engine = make_engine(clean_db)
    cascade_id = build(engine, forest_with_everything(), "f-R")
    ids = ids_by_uri(engine, cascade_id)
    body = tree(v1_client(clean_db), cascade_id)
    assert_tree_invariants(body)
    nodes = {n["event_id"]: n for n in body["nodes"]}
    edges = {(e["parent_id"], e["child_id"]) for e in body["edges"]}
    assert [n["event_id"] for n in body["nodes"]] == [
        ids[u] for u in ("f-R", "f-A", "f-Q", "f-P1", "f-P2", "f-D", "f-C", "f-O", "f-O2")
    ]
    assert body["roots"] == [
        {"event_id": ids["f-R"], "detached": False},
        {"event_id": ids["f-O"], "detached": True},
    ]
    for uri in ("f-P1", "f-P2"):
        node = nodes[ids[uri]]
        assert (node["edge_kind"], node["inferred"], node["depth"]) == ("repost", True, None)
        assert (ids["f-R"], ids[uri]) in edges
    tombstone = nodes[ids["f-D"]]
    assert tombstone["deleted"] is True
    assert tombstone["account"] is None
    assert (ids["f-D"], ids["f-C"]) in edges  # the skeleton stays connected
    assert nodes[ids["f-O"]]["parent_state"] == "orphan"
    assert (ids["f-O"], ids["f-O2"]) in edges
    assert nodes[ids["f-Q"]]["depth"] == 2
    assert nodes[ids["f-A"]]["account"] == "acct-a-l"
    assert all(n["account"] is None or len(n["account"]) == 8 for n in body["nodes"])
    assert body["meta"]["observed_since"] is not None
    assert datetime.fromisoformat(body["meta"]["observed_since"]) == T0


def test_the_cap_keeps_a_prefix_closed_under_ancestors(
    v1_client: Callable[..., Any], make_engine: Callable[..., Engine], clean_db: str
) -> None:
    engine = make_engine(clean_db)
    cascade_id = build(engine, forest_with_everything(), "f-R")
    for cap in (1, 2, 3, 5, 8):
        body = tree(v1_client(clean_db, env={"MAX_TREE_NODES": str(cap)}), cascade_id)
        assert_tree_invariants(body)
        assert body["shown"] == cap
        assert body["total"] == 9
        assert body["truncated"] is True
        assert body["links_may_be_missing"] is False
        nodes = {n["event_id"]: n for n in body["nodes"]}
        children = {e["child_id"] for e in body["edges"]}
        for node in body["nodes"]:
            if node["parent_state"] == "resolved":
                assert node["event_id"] in children  # its parent is shown
        assert len(nodes) == cap


def test_an_order_violation_in_a_capped_tree_sets_links_may_be_missing(
    v1_client: Callable[..., Any], make_engine: Callable[..., Engine], clean_db: str
) -> None:
    engine = make_engine(clean_db)
    forest = [
        ("v-R", "root", None, T0, "a1", False),
        ("v-A", "reply", "v-R", T0 + 5 * S, "a2", False),
        ("v-B", "reply", "v-A", T0 + 2 * S, "a3", False),  # observed before its parent
    ]
    cascade_id = build(engine, forest, "v-R")
    assert rows(engine, "SELECT order_violation_count FROM cascades")[0][0] == 1
    capped = tree(v1_client(clean_db, env={"MAX_TREE_NODES": "2"}), cascade_id)
    assert capped["truncated"] is True
    assert capped["links_may_be_missing"] is True
    full = tree(v1_client(clean_db, env={"MAX_TREE_NODES": "100"}), cascade_id)
    assert full["truncated"] is False
    assert full["links_may_be_missing"] is False
    assert len(full["edges"]) == 2


def test_the_kinds_filter_leaves_reposts_out_and_detaches_subtrees(
    v1_client: Callable[..., Any], make_engine: Callable[..., Engine], clean_db: str
) -> None:
    engine = make_engine(clean_db)
    cascade_id = build(engine, forest_with_everything(), "f-R")
    ids = ids_by_uri(engine, cascade_id)
    client = v1_client(clean_db)
    everything = tree(client, cascade_id)
    no_reposts = tree(client, cascade_id, kinds=["reply", "quote"])
    assert_tree_invariants(no_reposts)
    assert no_reposts["total"] == everything["total"] - 2
    assert all(n["edge_kind"] != "repost" for n in no_reposts["nodes"])
    assert no_reposts["roots"] == everything["roots"]  # dropping reposts is closure-safe
    quotes_only = tree(client, cascade_id, kinds=["quote"])
    assert_tree_invariants(quotes_only)
    assert [n["event_id"] for n in quotes_only["nodes"]] == [ids["f-R"], ids["f-Q"]]
    assert quotes_only["edges"] == []
    assert quotes_only["roots"] == [
        {"event_id": ids["f-R"], "detached": False},
        {"event_id": ids["f-Q"], "detached": True},
    ]
    bad = client.get(f"/v1/cascades/{cascade_id}/tree", params={"kinds": "root"})
    assert bad.status_code == 422
    assert bad.json()["errors"][0]["loc"][:2] == ["query", "kinds"]


def test_before_enrich_every_child_is_detached_and_pending(
    v1_client: Callable[..., Any], make_engine: Callable[..., Engine], clean_db: str
) -> None:
    engine = make_engine(clean_db)
    cascade_id = build(engine, forest_with_everything()[:3], "f-R", enrich=False)
    body = tree(v1_client(clean_db), cascade_id)
    assert body["enrich_pending"] is True
    assert body["edges"] == []
    assert [r["detached"] for r in body["roots"]] == [False, True, True]


def test_a_parent_cycle_written_another_way_is_never_an_error(
    v1_client: Callable[..., Any], make_engine: Callable[..., Engine], clean_db: str
) -> None:
    engine = make_engine(clean_db)
    forest = [
        ("c-R", "root", None, T0, "a1", False),
        ("c-A", "reply", "c-B", T0 + S, "a2", False),
        ("c-B", "reply", "c-A", T0 + 2 * S, "a3", False),
    ]
    cascade_id = build(engine, forest, "c-R", enrich=False)
    ids = ids_by_uri(engine, cascade_id)
    with engine.begin() as connection:
        for child, parent in (("c-A", "c-B"), ("c-B", "c-A")):
            connection.execute(
                text(
                    "UPDATE events SET parent_state = 'resolved', parent_event_id = :p"
                    " WHERE id = :c"
                ),
                {"p": ids[parent], "c": ids[child]},
            )
    body = tree(v1_client(clean_db), cascade_id)
    assert body["shown"] == 3
    assert body["edges"] == []
    assert [r["detached"] for r in body["roots"]] == [False, True, True]


# --- timeline -----------------------------------------------------------------------------------
def timeline(client: Any, cascade_id: int) -> dict[str, Any]:
    response = client.get(f"/v1/cascades/{cascade_id}/timeline")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def assert_dense(body: dict[str, Any]) -> None:
    width = timedelta(seconds=body["bucket_seconds"])
    starts = [datetime.fromisoformat(b["start"]) for b in body["buckets"]]
    assert starts[0] == datetime.fromisoformat(body["origin"])
    assert all(b - a == width for a, b in itertools.pairwise(starts))


def test_every_fixture_timeline_sums_to_the_stored_counts(
    v1_client: Callable[..., Any], seeded_db_url: str, seeded: Engine
) -> None:
    client = v1_client(seeded_db_url, env={"MAX_TIMELINE_BUCKETS": "500"})
    for (cascade_id,) in rows(seeded, "SELECT id FROM cascades ORDER BY id"):
        body = timeline(client, cascade_id)
        counts = dict(
            rows(
                seeded,
                "SELECT edge_kind, count(*) FROM events WHERE cascade_id = :c"
                " AND deleted_at IS NULL GROUP BY edge_kind",
                c=cascade_id,
            )
        )
        if not counts:
            assert body["buckets"] == []
            continue
        for kind in ("root", "reply", "quote", "repost"):
            assert sum(b[kind] for b in body["buckets"]) == counts.get(kind, 0), kind
        assert 1 <= len(body["buckets"]) <= 500
        assert_dense(body)
        first, last = rows(
            seeded,
            "SELECT min(observed_at), max(observed_at) FROM events WHERE cascade_id = :c"
            " AND deleted_at IS NULL",
            c=cascade_id,
        )[0]
        assert datetime.fromisoformat(body["origin"]) == first
        end = datetime.fromisoformat(body["buckets"][-1]["start"])
        assert end <= last < end + timedelta(seconds=body["bucket_seconds"])
        assert (
            sum(
                sum(b[k] for k in ("root", "reply", "quote", "repost")) for b in body["buckets"][:1]
            )
            > 0
        )


@pytest.mark.parametrize(
    ("span", "expected"),
    [
        (timedelta(seconds=30), 60),
        (timedelta(minutes=10), 60),
        (timedelta(hours=3), 60),
        (timedelta(days=3), 900),
        (timedelta(days=730), -(-int(timedelta(days=730).total_seconds()) // 499)),
    ],
    ids=["30s", "10min", "3h", "3d", "2y"],
)
def test_the_bucket_width_follows_the_ladder(
    v1_client: Callable[..., Any],
    make_engine: Callable[..., Engine],
    clean_db: str,
    span: timedelta,
    expected: int,
) -> None:
    engine = make_engine(clean_db)
    forest = [
        ("w-R", "root", None, T0, "a1", False),
        ("w-A", "reply", "w-R", T0 + span / 2, "a2", False),
        ("w-B", "reply", "w-R", T0 + span, "a3", False),
        ("w-D", "reply", "w-R", T0 + span + timedelta(days=900), "a4", True),  # not counted
    ]
    cascade_id = build(engine, forest, "w-R")
    body = timeline(v1_client(clean_db, env={"MAX_TIMELINE_BUCKETS": "500"}), cascade_id)
    assert body["bucket_seconds"] == expected
    assert len(body["buckets"]) <= 500
    assert_dense(body)
    assert sum(b["reply"] for b in body["buckets"]) == 2
    assert sum(b["root"] for b in body["buckets"]) == 1
    assert body["buckets"][0]["root"] == 1
    assert body["buckets"][-1]["reply"] >= 1


@pytest.mark.parametrize("limit", [1, 2, 5, 7])
def test_the_bucket_count_never_exceeds_the_bound(
    v1_client: Callable[..., Any], make_engine: Callable[..., Engine], clean_db: str, limit: int
) -> None:
    engine = make_engine(clean_db)
    forest = [("n-R", "root", None, T0, "a1", False)] + [
        (f"n-{i}", "reply", "n-R", T0 + timedelta(hours=i * 7, seconds=i), f"a{i}", False)
        for i in range(1, 12)
    ]
    cascade_id = build(engine, forest, "n-R")
    body = timeline(v1_client(clean_db, env={"MAX_TIMELINE_BUCKETS": str(limit)}), cascade_id)
    assert 1 <= len(body["buckets"]) <= limit
    assert sum(b["reply"] for b in body["buckets"]) == 11
    assert_dense(body)


def test_a_single_event_is_one_bucket_and_an_all_deleted_cascade_none(
    v1_client: Callable[..., Any], make_engine: Callable[..., Engine], clean_db: str
) -> None:
    engine = make_engine(clean_db)
    one = build(engine, [("s-R", "root", None, T0, "a1", False)], "s-R")
    body = timeline(v1_client(clean_db), one)
    assert len(body["buckets"]) == 1
    assert body["buckets"][0] == {
        "start": body["origin"],
        "root": 1,
        "reply": 0,
        "quote": 0,
        "repost": 0,
    }
    gone = build(engine, [("z-R", "root", None, T0, None, True)], "z-R", id_base=2000)
    empty = timeline(v1_client(clean_db), gone)
    assert empty["buckets"] == []
    assert empty["origin"] is None


def test_the_session_time_zone_changes_nothing(
    v1_client: Callable[..., Any],
    make_engine: Callable[..., Engine],
    clean_db: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = make_engine(clean_db)
    forest = [("tz-R", "root", None, T0 + timedelta(minutes=17), "a1", False)] + [
        (f"tz-{i}", "reply", "tz-R", T0 + timedelta(hours=5 * i, minutes=17), f"b{i}", False)
        for i in range(1, 30)
    ]
    cascade_id = build(engine, forest, "tz-R")
    utc = timeline(v1_client(clean_db), cascade_id)
    utc_tree = tree(v1_client(clean_db), cascade_id)
    monkeypatch.setenv("PGTZ", "Asia/Kolkata")
    shifted_client = v1_client(clean_db)
    with shifted_client.app.state.engine.connect() as connection:
        # the engine's connect hook pins UTC whatever PGTZ says (F-15)
        assert connection.execute(text("SHOW TimeZone")).scalar_one() == "UTC"
    assert timeline(shifted_client, cascade_id) == utc
    assert tree(shifted_client, cascade_id) == utc_tree
    assert utc["bucket_seconds"] == 3600  # a span of about six days
    assert all(
        datetime.fromisoformat(b["start"]).utcoffset() == timedelta(0) for b in utc["buckets"]
    )


def test_choose_bucket_seconds_unit() -> None:
    us = 1_000_000
    assert choose_bucket_seconds(0, 500) == BUCKET_LADDER_SECONDS[0]
    assert choose_bucket_seconds(499 * 60 * us, 500) == 60
    assert choose_bucket_seconds(500 * 60 * us, 500) == 300
    assert choose_bucket_seconds(10 * us, 1) == 60
    assert choose_bucket_seconds(100_000 * us, 1) == 100_001
    assert choose_bucket_seconds(100_000 * us, 2) == 86_400
    assert choose_bucket_seconds(200_000 * us, 2) == 200_000
    for span in (1, 59 * us, 10**15, 63_072_000 * us):
        for limit in (1, 2, 3, 500):
            size = choose_bucket_seconds(span, limit)
            assert span // (size * us) + 1 <= limit
    with pytest.raises(ValueError, match="non-negative"):
        choose_bucket_seconds(-1, 5)
    with pytest.raises(ValueError, match="positive"):
        choose_bucket_seconds(1, 0)
