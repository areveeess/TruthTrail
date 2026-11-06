"""``GET /v1/cascades`` and ``GET /v1/cascades/{id}`` against a real PostgreSQL (D-14, D-16, D-23,
D-24, OD-2, threats T-03-46 to T-03-50).

Read-only tests share ``seeded_db_url`` (the packaged fixture replayed through the collector
pipeline and enriched as of its checkpoint, plus one recorded replay run). Tests that write use
``clean_db`` and build their rows by direct parameterised SQL or through the production writer
(the deleted-root case uses a constructed delete frame, D-16). Every expected value is recomputed
from the tables in the test; no OD value is hard-coded (policy values travel as explicit
environment overrides).
"""

import base64
import json
from collections.abc import Callable, Iterator
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from conftest import (
    fixture_items,
    insert_forest,
    make_test_policy,
    recorded_frames,
    run_pipeline,
    set_checkpoint,
)
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from truthtrail.api.v1_cascades import decode_cursor, encode_cursor
from truthtrail.api.v1_deps import datetime_from_us, us_from_datetime

pytestmark = pytest.mark.requires_db

PROBLEM_JSON = "application/problem+json"
T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


# --- helpers ------------------------------------------------------------------------------------
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


def scalar(engine: Engine, sql: str, **params: Any) -> Any:
    with engine.connect() as connection:
        return connection.execute(text(sql), params).scalar_one()


def data_as_of(engine: Engine) -> datetime:
    return datetime_from_us(
        int(scalar(engine, "SELECT max(cursor_time_us) FROM ingest_checkpoints"))
    )


@pytest.fixture
def seeded_client(v1_client: Callable[..., Any], seeded_db_url: str, seeded: Engine) -> Any:
    now = data_as_of(seeded) + timedelta(minutes=1)
    return v1_client(seeded_db_url, clock=lambda: now)


def walk(client: Any, **params: Any) -> list[dict[str, Any]]:
    """Every item of a full pagination walk; asserts the page invariants on the way."""
    items: list[dict[str, Any]] = []
    cursor = None
    for _ in range(10_000):
        query = {**params, **({"cursor": cursor} if cursor else {})}
        response = client.get("/v1/cascades", params=query)
        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["items"]) <= body["limit"]
        items.extend(body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            return items
    raise AssertionError("pagination did not terminate")


def keys_named(value: Any, names: set[str]) -> list[str]:
    """Every key in ``names`` anywhere in a JSON value (recursive)."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in names:
                found.append(key)
            found.extend(keys_named(child, names))
    elif isinstance(value, list):
        for child in value:
            found.extend(keys_named(child, names))
    return found


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def assert_invalid(response: Any, field: str, raw: str | None = None) -> None:
    assert response.status_code == 422, response.text
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    body = response.json()
    assert body["code"] == "invalid_request"
    assert body["synthetic"] is False
    assert body["data_as_of"] is None
    assert [issue["loc"] for issue in body["errors"]] == [["query", field]]
    if raw:
        assert raw not in response.text


# --- the list -----------------------------------------------------------------------------------
def test_the_list_matches_the_schema_and_every_field(seeded_client: Any, seeded: Engine) -> None:
    response = seeded_client.get("/v1/cascades", params={"limit": 5})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "next_cursor", "limit", "sort", "meta"}
    assert body["limit"] == 5
    assert body["sort"] == "recent"
    assert len(body["items"]) == 5
    assert body["next_cursor"] is not None
    expected = rows(
        seeded,
        "SELECT * FROM cascades WHERE root_deleted_at IS NULL"
        " ORDER BY last_event_at DESC, id DESC LIMIT 5",
    )
    for item, row in zip(body["items"], expected, strict=True):
        assert item["cascade_id"] == row.id
        for name in (
            "event_count",
            "reply_count",
            "quote_count",
            "repost_count",
            "unique_accounts",
            "max_depth",
            "events_1h",
            "orphan_count",
            "disconnected_count",
            "overflow_count",
            "deleted_count",
            "order_violation_count",
        ):
            assert item[name] == getattr(row, name), name
        assert datetime.fromisoformat(item["last_event_at"]) == row.last_event_at
        assert datetime.fromisoformat(item["tracking_ends_at"]) == row.tracking_ends_at
        assert datetime.fromisoformat(item["rolled_up_at"]) == row.rolled_up_at
        assert item["enrich_pending"] is False
        assert item["root_deleted"] is False
        assert item["text_purged"] is False
        root_observed = scalar(
            seeded, "SELECT observed_at FROM events WHERE uri = :u", u=row.root_uri
        )
        assert datetime.fromisoformat(item["observed_since"]) == root_observed
        if row.claim_id is not None:
            claim = rows(seeded, "SELECT * FROM claims WHERE id = :i", i=row.claim_id)[0]
            assert item["claim"]["claim_id"] == claim.id
            assert item["claim"]["kind"] == claim.kind
            assert item["claim"]["url_canonical"] == claim.url_canonical
            assert item["claim"]["link_domain"] == claim.link_domain
            assert item["claim"]["title"] == claim.text
    assert body["meta"]["synthetic"] is False
    assert body["meta"]["source_status"] == "ok"
    assert body["meta"]["source_mode"] == "replay"
    assert body["meta"]["observed_since"] is None
    assert datetime.fromisoformat(body["meta"]["data_as_of"]) == data_as_of(seeded)


@pytest.mark.parametrize("sort", ["recent", "velocity"])
@pytest.mark.parametrize("limit", [1, 7, 25, 100])
def test_a_full_walk_returns_every_cascade_once_in_order(
    seeded_client: Any, seeded: Engine, sort: str, limit: int
) -> None:
    key = "last_event_at" if sort == "recent" else "events_1h"
    expected = [
        r.id
        for r in rows(
            seeded,
            "SELECT id FROM cascades WHERE root_deleted_at IS NULL ORDER BY "
            + key
            + " DESC, id DESC",
        )
    ]
    items = walk(seeded_client, sort=sort, limit=limit)
    ids = [item["cascade_id"] for item in items]
    assert ids == expected
    assert len(set(ids)) == len(ids) > 100


def test_deleted_roots_are_hidden_by_default_and_included_on_request(
    seeded_client: Any, seeded: Engine
) -> None:
    deleted = {
        r.id for r in rows(seeded, "SELECT id FROM cascades WHERE root_deleted_at IS NOT NULL")
    }
    assert deleted  # the fixture carries a deleted root
    default = {i["cascade_id"] for i in walk(seeded_client, limit=100)}
    everything = walk(seeded_client, limit=100, include_deleted_roots="true")
    assert default.isdisjoint(deleted)
    assert {i["cascade_id"] for i in everything} == default | deleted
    assert len(everything) == scalar(seeded, "SELECT count(*) FROM cascades")
    for item in everything:
        if item["cascade_id"] in deleted:
            assert item["root_deleted"] is True
            assert item["claim"] is None
            assert item["root_text"] is None


def test_min_events_and_has_orphans_filter(seeded_client: Any, seeded: Engine) -> None:
    threshold = 10
    big = walk(seeded_client, limit=100, min_events=threshold)
    assert {i["cascade_id"] for i in big} == {
        r.id
        for r in rows(
            seeded,
            "SELECT id FROM cascades WHERE root_deleted_at IS NULL AND event_count >= :n",
            n=threshold,
        )
    }
    orphaned = walk(seeded_client, limit=100, has_orphans="true")
    clean = walk(seeded_client, limit=100, has_orphans="false")
    assert orphaned
    assert all(i["orphan_count"] > 0 for i in orphaned)
    assert all(i["orphan_count"] == 0 for i in clean)
    assert len(orphaned) + len(clean) == len(walk(seeded_client, limit=100))


def test_a_walk_stays_stable_while_newer_cascades_arrive(
    v1_client: Callable[..., Any], make_engine: Callable[..., Engine], clean_db: str
) -> None:
    engine = make_engine(clean_db)
    for n in range(30):
        insert_forest(
            engine,
            [(f"old{n:02d}", "root", None, T0 + timedelta(minutes=n), f"acct{n}", False)],
            root_uri=f"old{n:02d}",
            id_base=1000 + n * 10,
        )
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE cascades SET events_1h = id % 4, last_event_at = first_event_at")
        )
    client = v1_client(clean_db)
    for sort in ("recent", "velocity"):
        seen: list[int] = []
        cursor = None
        extra = 0
        while True:
            params: dict[str, Any] = {"limit": 7, "sort": sort}
            if cursor:
                params["cursor"] = cursor
            body = client.get("/v1/cascades", params=params).json()
            seen.extend(i["cascade_id"] for i in body["items"])
            cursor = body["next_cursor"]
            if cursor is None:
                break
            # A newer cascade arrives between pages; it sorts before the current position.
            uri = f"new{sort[0]}{extra:02d}"
            insert_forest(
                engine,
                [(uri, "root", None, T0 + timedelta(days=1, minutes=extra), "acctn", False)],
                root_uri=uri,
                id_base=5000 + extra * 10 + (0 if sort == "recent" else 500),
            )
            with engine.begin() as connection:
                connection.execute(
                    text("UPDATE cascades SET events_1h = 1000 WHERE root_uri = :u"), {"u": uri}
                )
            extra += 1
        old = {r.id for r in rows(engine, "SELECT id FROM cascades WHERE root_uri LIKE 'old%'")}
        assert len(seen) == len(set(seen))
        assert old <= set(seen)
        assert extra >= 4


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("!!!", id="not-base64-alphabet"),
        pytest.param("a", id="bad-base64-length"),
        pytest.param(b64(b"not json"), id="base64-not-json"),
        pytest.param(b64(b"\xff\xfe\xfd"), id="not-utf8"),
        pytest.param(b64(b'{"sort":"recent"}'), id="json-object"),
        pytest.param(b64(b'["recent",1]'), id="too-short"),
        pytest.param(b64(b'["recent",1,2,3]'), id="too-long"),
        pytest.param(b64(b'["recent","1",2]'), id="string-value"),
        pytest.param(b64(b'["recent",1.5,2]'), id="float-value"),
        pytest.param(b64(b'["recent",true,2]'), id="bool-value"),
        pytest.param(b64(b'["recent",1,-4]'), id="negative-id"),
        pytest.param(b64(b'["recent",1,0]'), id="zero-id"),
        pytest.param(b64(b'["recent",-1,2]'), id="negative-value"),
        pytest.param(b64(b'["recent",253402300800000000,2]'), id="beyond-datetime"),
        pytest.param(b64(b'["sideways",1,2]'), id="unknown-sort"),
        pytest.param(b64(b'["velocity",1,2]'), id="sort-mismatch"),
        pytest.param("A" * 300, id="too-long-string"),
    ],
)
def test_malformed_cursors_are_422_without_echo(seeded_client: Any, raw: str) -> None:
    response = seeded_client.get("/v1/cascades", params={"cursor": raw, "sort": "recent"})
    assert_invalid(response, "cursor", raw if len(raw) > 3 else None)


def test_a_cursor_round_trips_exactly() -> None:
    instant = datetime(2026, 10, 19, 13, 5, 7, 123457, tzinfo=UTC)
    cursor = encode_cursor("recent", us_from_datetime(instant), 42)
    assert "=" not in cursor
    sort, value, cascade_id = decode_cursor(cursor)
    assert (sort, cascade_id) == ("recent", 42)
    assert datetime_from_us(value) == instant
    assert json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))) == [
        "recent",
        value,
        42,
    ]


def test_limit_bounds_come_from_the_policy(
    v1_client: Callable[..., Any], seeded_db_url: str
) -> None:
    client = v1_client(seeded_db_url, env={"PAGE_SIZE_MAX": "50", "PAGE_SIZE_DEFAULT": "9"})
    assert_invalid(client.get("/v1/cascades", params={"limit": 0}), "limit")
    assert_invalid(client.get("/v1/cascades", params={"limit": 51}), "limit")
    assert_invalid(client.get("/v1/cascades", params={"limit": "x"}), "limit")
    assert client.get("/v1/cascades", params={"limit": 50}).json()["limit"] == 50
    assert client.get("/v1/cascades").json()["limit"] == 9


@pytest.mark.parametrize(
    ("name", "value"),
    [("min_events", "-1"), ("claim_id", "0"), ("has_orphans", "perhaps"), ("sort", "risk")],
)
def test_invalid_filters_are_422(seeded_client: Any, name: str, value: str) -> None:
    assert_invalid(seeded_client.get("/v1/cascades", params={name: value}), name)


def test_claim_grouping_filters_by_claim_under_claim_group(
    v1_client: Callable[..., Any], seeded_db_url: str, seeded: Engine
) -> None:
    client = v1_client(seeded_db_url, env={"CASCADE_MERGE_POLICY": "claim_group"})
    shared = rows(
        seeded,
        "SELECT claim_id, count(*) AS n FROM cascades WHERE claim_id IS NOT NULL"
        " AND root_deleted_at IS NULL GROUP BY claim_id HAVING count(*) > 1"
        " ORDER BY count(*) DESC, claim_id LIMIT 3",
    )
    assert shared  # cascades of the fixture share canonical article URLs (OD-2 M1)
    for claim_id, n in shared:
        items = walk(client, limit=100, claim_id=claim_id)
        assert len(items) == n
        assert {i["claim"]["claim_id"] for i in items} == {claim_id}


def test_the_claim_filter_is_422_under_merge_policy_none(
    v1_client: Callable[..., Any], seeded_db_url: str
) -> None:
    client = v1_client(seeded_db_url, env={"CASCADE_MERGE_POLICY": "none"})
    response = client.get("/v1/cascades", params={"claim_id": 987654})
    assert_invalid(response, "claim_id", "987654")
    assert "CASCADE_MERGE_POLICY" in response.json()["errors"][0]["msg"]
    assert client.get("/v1/cascades").status_code == 200


@pytest.mark.parametrize("policy", ["claim_group", "none"])
def test_the_claim_parameter_is_declared_under_every_policy(
    v1_client: Callable[..., Any], seeded_db_url: str, policy: str
) -> None:
    client = v1_client(seeded_db_url, env={"CASCADE_MERGE_POLICY": policy})
    operation = client.get("/openapi.json").json()["paths"]["/v1/cascades"]["get"]
    assert "claim_id" in {p["name"] for p in operation["parameters"]}


def test_an_empty_database_is_200_empty_with_null_data_as_of(
    v1_client: Callable[..., Any], clean_db: str
) -> None:
    body = v1_client(clean_db).get("/v1/cascades").json()
    assert body["items"] == []
    assert body["next_cursor"] is None
    assert body["meta"] == {
        "synthetic": False,
        "data_as_of": None,
        "source_status": "empty",
        "source_mode": "live",
        "observed_since": None,
    }


def test_staleness_follows_the_injected_clock_and_the_threshold(
    v1_client: Callable[..., Any], make_engine: Callable[..., Engine], clean_db: str
) -> None:
    engine = make_engine(clean_db)
    cursor = us_from_datetime(T0)
    set_checkpoint(engine, cursor)
    env = {"INGEST_STALE_AFTER_SECONDS": "600"}
    inside = v1_client(clean_db, env=env, clock=lambda: T0 + timedelta(seconds=600))
    outside = v1_client(clean_db, env=env, clock=lambda: T0 + timedelta(seconds=601))
    for client, status in ((inside, "ok"), (outside, "stale")):
        meta = client.get("/v1/cascades").json()["meta"]
        assert meta["source_status"] == status
        assert datetime.fromisoformat(meta["data_as_of"]) == T0


def test_source_mode_follows_the_latest_run(
    v1_client: Callable[..., Any], make_engine: Callable[..., Engine], clean_db: str
) -> None:
    engine = make_engine(clean_db)
    set_checkpoint(engine, us_from_datetime(T0))

    def add_run(mode: str, started: datetime) -> None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ingest_runs (source, mode, started_at, status)"
                    " VALUES ('s', :m, :t, 'completed')"
                ),
                {"m": mode, "t": started},
            )

    client = v1_client(clean_db, clock=lambda: T0)
    assert client.get("/v1/cascades").json()["meta"]["source_mode"] == "live"
    add_run("replay", T0)
    assert client.get("/v1/cascades").json()["meta"]["source_mode"] == "replay"
    add_run("live", T0 + timedelta(minutes=1))
    assert client.get("/v1/cascades").json()["meta"]["source_mode"] == "live"


def test_no_response_has_a_risk_member_and_meta_is_never_synthetic(
    seeded_client: Any, seeded: Engine
) -> None:
    some_id = scalar(seeded, "SELECT min(id) FROM cascades")
    paths = [
        "/v1/cascades",
        "/v1/cascades?include_deleted_roots=true&limit=100",
        f"/v1/cascades/{some_id}",
        f"/v1/cascades/{some_id}/tree",
        f"/v1/cascades/{some_id}/timeline",
    ]
    for path in paths:
        body = seeded_client.get(path).json()
        assert keys_named(body, {"risk", "risk_method", "claim_scores", "score"}) == [], path
        assert body["meta"]["synthetic"] is False


# --- deleted roots, through the writer's tombstone path (D-16) -----------------------------------
def _constructed_delete(create: dict[str, Any]) -> dict[str, Any]:
    real = next(f for f in recorded_frames() if f["payload"].get("operation") == "delete")
    frame = deepcopy(real)
    for name in ("did", "collection", "rkey", "witnessedAt", "time"):
        frame["payload"][name] = create["payload"][name]
    return frame


def _create_frames(keyer: Any) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for frame in recorded_frames():
        p = frame["payload"]
        if p.get("operation") == "create":
            found[keyer.uri_key(f"at://{p['did']}/{p['collection']}/{p['rkey']}")] = frame
    return found


def test_a_deleted_root_shows_no_claim_and_leaves_the_claim_filter(
    v1_client: Callable[..., Any],
    make_engine: Callable[..., Engine],
    clean_db: str,
    fixture_allowlist_file: Any,
    keyer: Any,
) -> None:
    import json as json_module

    from truthtrail.enrich.apply import enrich_dirty
    from truthtrail.ingest.dialect import classify_frame
    from truthtrail.ingest.normalise import normalise
    from truthtrail.ingest.source import SourceItem

    engine = make_engine(clean_db, role="collector")
    policy = make_test_policy(fixture_allowlist_file)
    run_pipeline(engine, policy, fixture_items(keyer))
    claim_id, first_root, other_root = rows(
        engine,
        "SELECT c.claim_id, min(c.root_uri), max(c.root_uri) FROM cascades c"
        " WHERE c.claim_id IS NOT NULL AND c.root_deleted_at IS NULL"
        " GROUP BY c.claim_id HAVING count(*) = 2 ORDER BY c.claim_id LIMIT 1",
    )[0]
    frame = _constructed_delete(_create_frames(keyer)[first_root])
    result = normalise(classify_frame(json_module.dumps(frame), "v2"), keyer)
    run_pipeline(engine, policy, [SourceItem(result, getattr(result, "time_us", None))])
    enrich_dirty(engine)
    deleted_id = scalar(engine, "SELECT id FROM cascades WHERE root_uri = :u", u=first_root)
    other_id = scalar(engine, "SELECT id FROM cascades WHERE root_uri = :u", u=other_root)
    assert scalar(engine, "SELECT claim_id FROM cascades WHERE id = :i", i=deleted_id) is None

    client = v1_client(clean_db, env={"CASCADE_MERGE_POLICY": "claim_group"})
    listed = {i["cascade_id"]: i for i in walk(client, limit=100, include_deleted_roots="true")}
    assert listed[deleted_id]["root_deleted"] is True
    assert listed[deleted_id]["claim"] is None
    assert deleted_id not in {i["cascade_id"] for i in walk(client, limit=100)}
    detail = client.get(f"/v1/cascades/{deleted_id}").json()["cascade"]
    assert detail["claim"] is None
    assert detail["root_deleted"] is True
    for include in ("false", "true"):
        matched = walk(client, limit=100, claim_id=claim_id, include_deleted_roots=include)
        assert [i["cascade_id"] for i in matched] == [other_id]

    # The API guard: a claim linked again by direct SQL is still not shown.
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE cascades SET claim_id = :c WHERE id = :i"),
            {"c": claim_id, "i": deleted_id},
        )
    fresh = v1_client(clean_db, env={"CASCADE_MERGE_POLICY": "claim_group"})
    assert fresh.get(f"/v1/cascades/{deleted_id}").json()["cascade"]["claim"] is None
    matched = walk(fresh, limit=100, claim_id=claim_id, include_deleted_roots="true")
    assert [i["cascade_id"] for i in matched] == [other_id]


# --- the detail ---------------------------------------------------------------------------------
def test_an_unknown_id_is_the_generic_404_with_provenance(seeded_client: Any) -> None:
    for path in (
        "/v1/cascades/999999999",
        "/v1/cascades/999999999/tree",
        "/v1/cascades/999999999/timeline",
    ):
        response = seeded_client.get(path)
        assert response.status_code == 404
        assert response.headers["content-type"].startswith(PROBLEM_JSON)
        body = response.json()
        assert body["code"] == "http_error"
        assert body["synthetic"] is False
        assert body["data_as_of"] is None
        assert body["source_status"] == "error"


@pytest.mark.parametrize("raw", ["0", "-3", "abc", str(2**63)])
def test_an_invalid_id_is_422(seeded_client: Any, raw: str) -> None:
    response = seeded_client.get(f"/v1/cascades/{raw}")
    assert response.status_code == 422
    assert response.json()["errors"][0]["loc"] == ["path", "cascade_id"]


def test_the_detail_carries_every_completeness_count(seeded_client: Any, seeded: Engine) -> None:
    for row in rows(seeded, "SELECT * FROM cascades ORDER BY id"):
        response = seeded_client.get(f"/v1/cascades/{row.id}")
        assert response.status_code == 200
        body = response.json()
        cascade = body["cascade"]
        root_observed = scalar(
            seeded,
            "SELECT observed_at FROM events WHERE uri = :u AND cascade_id = :c",
            u=row.root_uri,
            c=row.id,
        )
        assert datetime.fromisoformat(cascade["observed_since"]) == root_observed
        assert datetime.fromisoformat(body["meta"]["observed_since"]) == root_observed
        for name in (
            "orphan_count",
            "disconnected_count",
            "overflow_count",
            "order_violation_count",
            "deleted_count",
            "event_count",
        ):
            assert cascade[name] == getattr(row, name), name
        counts = cascade["counts_by_kind"]
        assert sum(counts.values()) == row.event_count + row.deleted_count
        by_kind = dict(
            rows(
                seeded,
                "SELECT edge_kind, count(*) FROM events WHERE cascade_id = :c"
                " AND deleted_at IS NULL GROUP BY edge_kind",
                c=row.id,
            )
        )
        for kind in ("root", "reply", "quote", "repost"):
            assert counts[kind] == by_kind.get(kind, 0), kind
        assert counts["deleted"] == scalar(
            seeded,
            "SELECT count(*) FROM events WHERE cascade_id = :c AND deleted_at IS NOT NULL",
            c=row.id,
        )
        assert cascade["invalid_count"] == scalar(
            seeded,
            "SELECT count(*) FROM events WHERE cascade_id = :c AND parent_state = 'invalid'"
            " AND deleted_at IS NULL",
            c=row.id,
        )
        assert cascade["ingest_gaps"] == 0
        assert cascade["enrich_pending"] is False


def test_the_overflow_description_says_it_is_a_lower_bound(seeded_client: Any) -> None:
    schemas = seeded_client.get("/openapi.json").json()["components"]["schemas"]
    description = schemas["CascadeSummary"]["properties"]["overflow_count"]["description"]
    assert "at least" in description
    assert "lower bound" in description


def test_ingest_gaps_overlapping_the_cascade_life_are_counted(
    v1_client: Callable[..., Any], make_engine: Callable[..., Engine], clean_db: str
) -> None:
    engine = make_engine(clean_db)
    cascade_id = insert_forest(
        engine,
        [
            ("g-root", "root", None, T0, "a1", False),
            ("g-reply", "reply", "g-root", T0 + timedelta(hours=1), "a2", False),
        ],
        root_uri="g-root",
        tracking_ends_at=T0 + timedelta(hours=2),
    )
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE cascades SET last_event_at = :t WHERE id = :i"),
            {"t": T0 + timedelta(hours=1), "i": cascade_id},
        )
    spans = [
        (T0 - timedelta(hours=3), T0 - timedelta(hours=2)),  # before: not counted
        (T0 - timedelta(minutes=5), T0 + timedelta(minutes=5)),  # overlaps the start
        (T0 + timedelta(minutes=30), T0 + timedelta(minutes=31)),  # inside
        (T0 + timedelta(hours=1, minutes=30), T0 + timedelta(hours=1, minutes=40)),  # tracked
        (T0 + timedelta(hours=3), T0 + timedelta(hours=4)),  # after tracking: not counted
    ]
    with engine.begin() as connection:
        for low, high in spans:
            connection.execute(
                text(
                    "INSERT INTO ingest_runs (source, mode, started_at, status, gap_from_us,"
                    " gap_to_us, gap_count) VALUES ('s', 'live', :t, 'completed', :a, :b, 1)"
                ),
                {"t": high, "a": us_from_datetime(low), "b": us_from_datetime(high)},
            )
        connection.execute(
            text(
                "INSERT INTO ingest_runs (source, mode, started_at, status)"
                " VALUES ('s', 'live', :t, 'completed')"
            ),
            {"t": T0},
        )
    body = v1_client(clean_db).get(f"/v1/cascades/{cascade_id}").json()
    assert body["cascade"]["ingest_gaps"] == 3


def test_enrich_pending_follows_the_dirty_mark(
    v1_client: Callable[..., Any], make_engine: Callable[..., Engine], clean_db: str
) -> None:
    from truthtrail.enrich.apply import enrich_dirty

    engine = make_engine(clean_db)
    rows_ = [("p-root", "root", None, T0, "a1", False)]
    cascade_id = insert_forest(engine, rows_, root_uri="p-root")
    enrich_dirty(engine, as_of=T0)
    client = v1_client(clean_db)
    assert client.get(f"/v1/cascades/{cascade_id}").json()["cascade"]["enrich_pending"] is False
    insert_forest(
        engine,
        [("p-reply", "reply", "p-root", T0 + timedelta(seconds=5), "a2", False)],
        root_uri="p-root",
        id_base=2000,
    )
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE cascades SET enrich_dirty = true WHERE id = :i"), {"i": cascade_id}
        )
    pending = client.get(f"/v1/cascades/{cascade_id}").json()["cascade"]
    assert pending["enrich_pending"] is True
    assert pending["event_count"] == 1  # the rollup lags until enrich runs
    enrich_dirty(engine, as_of=T0 + timedelta(seconds=10))
    done = client.get(f"/v1/cascades/{cascade_id}").json()["cascade"]
    assert done["enrich_pending"] is False
    assert done["event_count"] == 2
    assert done["reply_count"] == 1


def test_root_text_is_shown_until_purged(
    v1_client: Callable[..., Any],
    make_engine: Callable[..., Engine],
    clean_db: str,
    fixture_allowlist_file: Any,
) -> None:
    from truthtrail.enrich.apply import enrich_dirty
    from truthtrail.enrich.purge import purge

    engine = make_engine(clean_db)
    cascade_id = insert_forest(
        engine, [("t-root", "root", None, T0, "a1", False)], root_uri="t-root"
    )
    constructed = "Constructed root text for the purge test."
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE events SET text = :t WHERE uri = 't-root'"), {"t": constructed}
        )
    enrich_dirty(engine, as_of=T0)
    before = v1_client(clean_db).get(f"/v1/cascades/{cascade_id}").json()["cascade"]
    assert before["root_text"] == constructed
    assert before["text_purged"] is False
    policy = make_test_policy(fixture_allowlist_file)
    purge(engine, policy, as_of=T0 + timedelta(days=policy.retention_text_days, seconds=1))
    after = v1_client(clean_db).get(f"/v1/cascades/{cascade_id}").json()["cascade"]
    assert after["root_text"] is None
    assert after["text_purged"] is True


def test_cached_reads_do_not_requery_within_the_ttl(
    v1_client: Callable[..., Any], seeded_db_url: str, seeded: Engine
) -> None:
    from sqlalchemy import event

    class Timer:
        now = 0.0

        def __call__(self) -> float:
            return self.now

    timer = Timer()
    client = v1_client(seeded_db_url, cache_timer=timer)
    engine = client.app.state.engine
    statements: list[str] = []
    event.listen(engine, "before_cursor_execute", lambda c, cur, s, *a: statements.append(s))
    some_id = scalar(seeded, "SELECT min(id) FROM cascades")

    def payload_reads() -> int:
        return sum(1 for s in statements if "FROM cascades LEFT OUTER JOIN claims" in s)

    for path in ("/v1/cascades", f"/v1/cascades/{some_id}"):
        statements.clear()
        first = client.get(path).json()
        second = client.get(path).json()
        assert first == second
        assert payload_reads() == 1
        timer.now += 10.0
        client.get(path)
        assert payload_reads() == 2
