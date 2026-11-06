"""Deletes are honoured by one rule, the tombstone (D-16, SC3, T-03-29, T-03-30).

Delete, account and sync frames are CONSTRUCTED from the real recorded shapes (the real frame's
keys, with the did, collection and rkey replaced by those of a stored fixture record; names start
with ``constructed_``) and go through the production dialect, normaliser, Decider and writer.
"""

import json
from copy import deepcopy
from dataclasses import replace
from typing import Any

import pytest
from conftest import fixture_items, recorded_frames, row_counts, run_pipeline
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from truthtrail.ingest.dialect import classify_frame
from truthtrail.ingest.normalise import (
    ACCOUNT_STATUS_IGNORED,
    Dropped,
    NormalizedEvent,
    normalise,
)
from truthtrail.ingest.source import SourceItem
from truthtrail.ingest.writer import DUPLICATE

pytestmark = pytest.mark.requires_db

KEPT = ("uri", "edge_kind", "parent_uri", "reply_root_uri", "cascade_id", "observed_at")
REMOVED = ("account_id", "occurred_at", "text", "claim_id", "lang")


@pytest.fixture
def engine(clean_db: str, make_engine: Any) -> Any:
    return make_engine(clean_db, role="collector")


@pytest.fixture
def items(keyer: Any) -> list[SourceItem]:
    return fixture_items(keyer)


@pytest.fixture
def stored(engine: Any, explicit_policy: Any, items: list[SourceItem]) -> Any:
    """The fixture replayed once (the deletes and account events it carries included)."""
    return run_pipeline(engine, explicit_policy(), items)


def _creates(keyer: Any) -> dict[str, dict[str, Any]]:
    """Real create frames by the uri key the normaliser gives them."""
    found: dict[str, dict[str, Any]] = {}
    for frame in recorded_frames():
        p = frame["payload"]
        if p.get("operation") == "create":
            found[keyer.uri_key(f"at://{p['did']}/{p['collection']}/{p['rkey']}")] = frame
    return found


def _real(predicate: Any) -> dict[str, Any]:
    return next(f for f in recorded_frames() if predicate(f["payload"]))


def constructed_delete(create: dict[str, Any]) -> dict[str, Any]:
    frame = deepcopy(_real(lambda p: p.get("operation") == "delete"))
    for name in ("did", "collection", "rkey"):
        frame["payload"][name] = create["payload"][name]
    frame["payload"]["witnessedAt"] = create["payload"]["witnessedAt"]
    frame["payload"]["time"] = create["payload"]["time"]
    return frame


def constructed_account(create: dict[str, Any], status: str | None) -> dict[str, Any]:
    frame = deepcopy(_real(lambda p: "account" in p))
    did = create["payload"]["did"]
    frame["payload"]["did"] = did
    frame["payload"]["account"]["did"] = did
    frame["payload"]["account"]["status"] = status
    frame["payload"]["witnessedAt"] = create["payload"]["witnessedAt"]
    frame["payload"]["time"] = create["payload"]["time"]
    return frame


def constructed_sync(create: dict[str, Any]) -> dict[str, Any]:
    frame = deepcopy(_real(lambda p: "sync" in p))
    frame["payload"]["did"] = create["payload"]["did"]
    frame["payload"]["sync"]["did"] = create["payload"]["did"]
    frame["payload"]["witnessedAt"] = create["payload"]["witnessedAt"]
    frame["payload"]["time"] = create["payload"]["time"]
    return frame


def _item(frame: dict[str, Any], keyer: Any) -> SourceItem:
    result = normalise(classify_frame(json.dumps(frame), "v2"), keyer)
    assert not isinstance(result, Dropped), result
    return SourceItem(result, getattr(result, "time_us", None))


def _row(engine: Any, uri: str) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(text("SELECT * FROM events WHERE uri = :u"), {"u": uri}).one()
    return dict(row._mapping)


def _cascade(engine: Any, root_uri: str) -> dict[str, Any]:
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT * FROM cascades WHERE root_uri = :u"), {"u": root_uri}
        ).one()
    return dict(row._mapping)


def _scalar(engine: Any, sql: str, **params: Any) -> Any:
    with engine.connect() as connection:
        return connection.execute(text(sql), params).scalar_one()


def _live(run: Any, kind: str, engine: Any) -> NormalizedEvent:
    """A stored, not yet tombstoned event of ``kind`` from the replay."""
    for result, outcome in run.per_item:
        if outcome == "accepted_" + kind and _row(engine, result.uri_key)["deleted_at"] is None:
            return result
    raise LookupError(kind)


def _delete(engine: Any, policy: Any, frames: list[dict[str, Any]], keyer: Any) -> Any:
    return run_pipeline(engine, policy, [_item(f, keyer) for f in frames])


# --- the fixture's own deletes --------------------------------------------------------------------
def test_the_fixture_deletes_tombstone_the_matching_stored_rows(stored: Any, engine: Any) -> None:
    from conftest import fixture_manifest

    deletes = fixture_manifest()["coverage"]["deletes"]
    tombstoned = sum(r.tombstoned_by_cause.get("delete", 0) for r in stored.results)
    assert tombstoned == deletes["post"] + deletes["repost"]
    assert _scalar(engine, "SELECT count(*) FROM events WHERE deleted_at IS NOT NULL") >= tombstoned


# --- key deletes ---------------------------------------------------------------------------------
def test_a_delete_turns_a_stored_reply_into_a_minimal_tombstone(
    stored: Any, engine: Any, explicit_policy: Any, keyer: Any
) -> None:
    reply = _live(stored, "reply", engine)
    before = _row(engine, reply.uri_key)
    run = _delete(
        engine, explicit_policy(), [constructed_delete(_creates(keyer)[reply.uri_key])], keyer
    )
    after = _row(engine, reply.uri_key)
    assert run.results[-1].tombstoned_by_cause == {"delete": 1}
    assert after["deleted_at"] is not None
    for name in KEPT:
        assert after[name] == before[name], name
    for name in REMOVED:
        assert after[name] is None, name


def test_the_cascade_skeleton_stays_connected_after_a_delete(
    stored: Any, engine: Any, explicit_policy: Any, keyer: Any
) -> None:
    parent = _scalar(
        engine,
        "SELECT p.uri FROM events p WHERE p.deleted_at IS NULL AND p.edge_kind <> 'root'"
        " AND EXISTS (SELECT 1 FROM events c WHERE c.parent_uri = p.uri) LIMIT 1",
    )
    children = _scalar(engine, "SELECT count(*) FROM events WHERE parent_uri = :u", u=parent)
    _delete(engine, explicit_policy(), [constructed_delete(_creates(keyer)[parent])], keyer)
    assert _row(engine, parent)["deleted_at"] is not None
    assert (
        _scalar(engine, "SELECT count(*) FROM events WHERE parent_uri = :u", u=parent) == children
    )


def test_a_deleted_repost_is_marked_and_its_cascade_is_dirty(
    stored: Any, engine: Any, explicit_policy: Any, keyer: Any
) -> None:
    repost = _live(stored, "repost", engine)
    with engine.begin() as connection:
        connection.execute(text("UPDATE cascades SET enrich_dirty = false"))
    _delete(engine, explicit_policy(), [constructed_delete(_creates(keyer)[repost.uri_key])], keyer)
    row = _row(engine, repost.uri_key)
    assert row["deleted_at"] is not None
    assert row["edge_kind"] == "repost"
    dirty = _scalar(engine, "SELECT enrich_dirty FROM cascades WHERE id = :i", i=row["cascade_id"])
    assert dirty is True
    assert _scalar(engine, "SELECT count(*) FROM cascades WHERE enrich_dirty") == 1


def test_deleting_a_root_sets_root_deleted_at_and_unlinks_its_claim(
    stored: Any, engine: Any, explicit_policy: Any, keyer: Any
) -> None:
    root = _live(stored, "root", engine)
    claim_id = _cascade(engine, root.uri_key)["claim_id"]
    assert claim_id is not None
    run = _delete(
        engine, explicit_policy(), [constructed_delete(_creates(keyer)[root.uri_key])], keyer
    )
    cascade = _cascade(engine, root.uri_key)
    assert run.results[-1].roots_deleted == 1
    assert cascade["root_deleted_at"] is not None
    assert cascade["claim_id"] is None
    assert cascade["enrich_dirty"] is True
    assert _scalar(engine, "SELECT count(*) FROM claims WHERE id = :i", i=claim_id) == 1


def test_the_claim_stays_while_another_cascade_still_links_it(
    engine: Any, explicit_policy: Any, items: list[SourceItem], keyer: Any
) -> None:
    full = run_pipeline(engine, explicit_policy(), items)
    roots = [r for r, o in full.per_item if o == "accepted_root"]
    first, second = roots[0], roots[1]
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE accounts, claims, cascades, events CASCADE"))
    constructed_same_url = replace(second, links=first.links)
    run_pipeline(
        engine,
        explicit_policy(),
        [SourceItem(first, first.time_us), SourceItem(constructed_same_url, second.time_us)],
    )
    assert row_counts(engine)["claims"] == 1
    _delete(engine, explicit_policy(), [constructed_delete(_creates(keyer)[first.uri_key])], keyer)
    assert _cascade(engine, first.uri_key)["claim_id"] is None
    assert _cascade(engine, second.uri_key)["claim_id"] is not None
    assert row_counts(engine)["claims"] == 1


def test_deleting_a_non_root_leaves_the_cascade_claim_untouched(
    stored: Any, engine: Any, explicit_policy: Any, keyer: Any
) -> None:
    reply = _live(stored, "reply", engine)
    cascade_id = _row(engine, reply.uri_key)["cascade_id"]
    claim = _scalar(engine, "SELECT claim_id FROM cascades WHERE id = :i", i=cascade_id)
    _delete(engine, explicit_policy(), [constructed_delete(_creates(keyer)[reply.uri_key])], keyer)
    assert _scalar(engine, "SELECT claim_id FROM cascades WHERE id = :i", i=cascade_id) == claim
    assert (
        _scalar(engine, "SELECT root_deleted_at FROM cascades WHERE id = :i", i=cascade_id) is None
    )


def test_replaying_the_root_create_after_its_delete_never_relinks(
    stored: Any, engine: Any, explicit_policy: Any, keyer: Any
) -> None:
    root = _live(stored, "root", engine)
    creates = _creates(keyer)
    _delete(engine, explicit_policy(), [constructed_delete(creates[root.uri_key])], keyer)
    deleted_at = _cascade(engine, root.uri_key)["root_deleted_at"]
    fresh = run_pipeline(engine, explicit_policy(), [_item(creates[root.uri_key], keyer)])
    cascade = _cascade(engine, root.uri_key)
    assert fresh.inserted == 0
    assert cascade["root_deleted_at"] == deleted_at
    assert cascade["claim_id"] is None
    assert _row(engine, root.uri_key)["deleted_at"] is not None


def test_a_second_identical_delete_touches_nothing(
    stored: Any, engine: Any, explicit_policy: Any, keyer: Any
) -> None:
    reply = _live(stored, "reply", engine)
    frame = constructed_delete(_creates(keyer)[reply.uri_key])
    _delete(engine, explicit_policy(), [frame], keyer)
    first = _row(engine, reply.uri_key)
    again = _delete(engine, explicit_policy(), [frame], keyer)
    assert again.results[-1].tombstoned == 0
    assert again.results[-1].deletes_unmatched == 1
    assert _row(engine, reply.uri_key) == first


def test_replaying_the_original_create_never_resurrects_content(
    stored: Any, engine: Any, explicit_policy: Any, keyer: Any
) -> None:
    reply = _live(stored, "reply", engine)
    creates = _creates(keyer)
    _delete(engine, explicit_policy(), [constructed_delete(creates[reply.uri_key])], keyer)
    tombstone = _row(engine, reply.uri_key)
    again = run_pipeline(engine, explicit_policy(), [_item(creates[reply.uri_key], keyer)])
    assert again.outcomes == {DUPLICATE: 1}
    assert _row(engine, reply.uri_key) == tombstone
    # a later run whose index no longer holds the cascade (its window closed)
    with engine.begin() as connection:
        connection.execute(text("UPDATE cascades SET tracking_ends_at = '2000-01-01T00:00Z'"))
    create = _item(creates[reply.uri_key], keyer)
    later = run_pipeline(engine, explicit_policy(), [create], since_us=create.cursor_us)
    assert later.inserted == 0
    assert _row(engine, reply.uri_key) == tombstone


def test_a_create_and_its_delete_in_one_batch_end_as_a_tombstone(
    engine: Any, explicit_policy: Any, items: list[SourceItem], keyer: Any
) -> None:
    full = run_pipeline(engine, explicit_policy(), items)
    root = next(r for r, o in full.per_item if o == "accepted_root")
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE accounts, claims, cascades, events CASCADE"))
    creates = _creates(keyer)
    batch_items = [
        _item(creates[root.uri_key], keyer),
        _item(constructed_delete(creates[root.uri_key]), keyer),
    ]
    run = run_pipeline(engine, explicit_policy(), batch_items, batch_rows=10)
    assert len(run.results) == 1
    row = _row(engine, root.uri_key)
    assert row["deleted_at"] is not None
    assert row["text"] is None
    assert row["account_id"] is None
    assert _cascade(engine, root.uri_key)["root_deleted_at"] is not None


def test_a_delete_for_an_untracked_record_is_a_counted_no_op(
    stored: Any, engine: Any, explicit_policy: Any, keyer: Any
) -> None:
    untracked = stored.keys_with("untracked")[0]
    counts = row_counts(engine)
    run = _delete(
        engine, explicit_policy(), [constructed_delete(_creates(keyer)[untracked])], keyer
    )
    assert run.outcomes == {"delete": 1}
    assert run.results[-1].deletes_unmatched == 1
    assert run.results[-1].tombstoned == 0
    assert row_counts(engine)["events"] == counts["events"]


def test_a_delete_in_a_cascade_whose_window_ended_still_works(
    stored: Any, engine: Any, explicit_policy: Any, keyer: Any
) -> None:
    reply = _live(stored, "reply", engine)
    with engine.begin() as connection:
        connection.execute(text("UPDATE cascades SET tracking_ends_at = '2000-01-01T00:00Z'"))
    frame = constructed_delete(_creates(keyer)[reply.uri_key])
    item = _item(frame, keyer)
    run = run_pipeline(engine, explicit_policy(), [item], since_us=item.cursor_us)
    assert len(run.index) == 0  # no open cascade was loaded
    assert run.results[-1].tombstoned == 1
    assert _row(engine, reply.uri_key)["deleted_at"] is not None


# --- account-wide paths
def _account_with_rows(engine: Any) -> tuple[int, int]:
    """(account id, number of live rows) of the account with the most live rows."""
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT account_id, count(*) n, count(DISTINCT cascade_id) c FROM events"
                " WHERE deleted_at IS NULL GROUP BY account_id ORDER BY c DESC, n DESC,"
                " account_id LIMIT 1"
            )
        ).one()
    return row[0], row[1]


def _create_of_account(engine: Any, keyer: Any, account_id: int) -> dict[str, Any]:
    with engine.connect() as connection:
        uri = connection.execute(
            text("SELECT min(uri) FROM events WHERE account_id = :a"), {"a": account_id}
        ).scalar_one()
    return _creates(keyer)[uri]


def _latest(create: dict[str, Any]) -> dict[str, Any]:
    """The constructed action carries the time of the account's newest fixture create."""
    frame = deepcopy(create)
    latest = max(
        (
            f["payload"]["witnessedAt"]
            for f in recorded_frames()
            if f["payload"].get("did") == create["payload"]["did"]
        ),
    )
    frame["payload"]["witnessedAt"] = latest
    frame["payload"]["time"] = latest
    return frame


@pytest.mark.parametrize(
    ("status", "cause"), [("deleted", "account_deleted"), ("takendown", "account_takedown")]
)
def test_an_account_removal_tombstones_every_row_of_the_account(
    stored: Any, engine: Any, explicit_policy: Any, keyer: Any, status: str, cause: str
) -> None:
    account_id, live = _account_with_rows(engine)
    with engine.connect() as connection:
        roots = (
            connection.execute(
                text(
                    "SELECT c.root_uri FROM events e JOIN cascades c ON c.id = e.cascade_id"
                    " WHERE e.account_id = :a AND e.edge_kind = 'root'"
                ),
                {"a": account_id},
            )
            .scalars()
            .all()
        )
        cascades = connection.execute(
            text("SELECT count(DISTINCT cascade_id) FROM events WHERE account_id = :a"),
            {"a": account_id},
        ).scalar_one()
    create = _latest(_create_of_account(engine, keyer, account_id))
    run = _delete(engine, explicit_policy(), [constructed_account(create, status)], keyer)
    assert run.results[-1].tombstoned_by_cause == {cause: live}
    assert cascades >= 1
    assert _scalar(engine, "SELECT count(*) FROM events WHERE account_id = :a", a=account_id) == 0
    for root_uri in roots:
        assert _cascade(engine, root_uri)["claim_id"] is None
        assert _cascade(engine, root_uri)["root_deleted_at"] is not None


def test_an_account_removal_unlinks_the_claim_of_every_root_of_the_account(
    engine: Any, explicit_policy: Any, items: list[SourceItem], keyer: Any
) -> None:
    full = run_pipeline(engine, explicit_policy(), items)
    roots = [r for r, o in full.per_item if o == "accepted_root"][:2]
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE accounts, claims, cascades, events CASCADE"))
    # two real roots, the second constructed to share the first one's account
    constructed_same_author = replace(roots[1], account_key=roots[0].account_key)
    run_pipeline(
        engine,
        explicit_policy(),
        [
            SourceItem(roots[0], roots[0].time_us),
            SourceItem(constructed_same_author, roots[1].time_us),
        ],
    )
    create = _latest(_creates(keyer)[roots[0].uri_key])
    action = _item(constructed_account(create, "deleted"), keyer)
    action = SourceItem(
        replace(action.result, time_us=max(r.time_us for r in roots)), action.cursor_us
    )
    _delete_items = run_pipeline(engine, explicit_policy(), [action])
    assert _delete_items.results[-1].roots_deleted == 2
    for root in roots:
        assert _cascade(engine, root.uri_key)["claim_id"] is None


@pytest.mark.parametrize(
    "status", ["deactivated", "suspended", "desynchronized", "throttled", "constructed-future"]
)
def test_other_account_statuses_are_ignored_and_counted(
    stored: Any, engine: Any, keyer: Any, status: str
) -> None:
    account_id, _live_rows = _account_with_rows(engine)
    frame = constructed_account(_create_of_account(engine, keyer, account_id), status)
    result = normalise(classify_frame(json.dumps(frame), "v2"), keyer)
    assert result == Dropped(ACCOUNT_STATUS_IGNORED)


def test_a_sync_event_tombstones_the_accounts_rows(
    stored: Any, engine: Any, explicit_policy: Any, keyer: Any
) -> None:
    account_id, live = _account_with_rows(engine)
    create = _latest(_create_of_account(engine, keyer, account_id))
    run = _delete(engine, explicit_policy(), [constructed_sync(create)], keyer)
    assert run.results[-1].tombstoned_by_cause == {"sync": live}


def test_an_account_event_for_an_unknown_pseudonym_is_a_counted_no_op(
    stored: Any, engine: Any, explicit_policy: Any, keyer: Any
) -> None:
    create = next(iter(_creates(keyer).values()))
    frame = constructed_account(create, "deleted")
    frame["payload"]["did"] = frame["payload"]["account"]["did"] = "did:plc:constructedunknown"
    counts = row_counts(engine)
    run = _delete(engine, explicit_policy(), [frame], keyer)
    assert run.results[-1].account_actions_unmatched == 1
    assert run.results[-1].tombstoned == 0
    assert row_counts(engine) == counts


def test_a_tombstone_cannot_hold_content(stored: Any, engine: Any) -> None:
    uri = _scalar(engine, "SELECT uri FROM events WHERE deleted_at IS NOT NULL LIMIT 1")
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text("UPDATE events SET lang = 'en' WHERE uri = :u"), {"u": uri})
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text("UPDATE events SET occurred_at = observed_at WHERE uri = :u"), {"u": uri}
        )
