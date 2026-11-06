"""The database enforces the edge, orphan, tombstone and minimisation invariants (D-12, D-14,
D-16, D-18, D-20).

Every rejected row is inserted in its own transaction, which the failure rolls back, and every
rejection asserts the NAME of the constraint that fired, so a test cannot pass because some other
rule happened to reject the row. All statements are parameterised. The rows are minimal valid
shapes built by the helpers below; a test changes one field to break one rule.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.requires_db

T0 = datetime(2026, 11, 6, 9, 0, tzinfo=UTC)

EVENT_COLUMNS = (
    "uri",
    "edge_kind",
    "inferred",
    "parent_uri",
    "reply_root_uri",
    "parent_state",
    "parent_event_id",
    "cascade_id",
    "depth",
    "account_id",
    "observed_at",
    "occurred_at",
    "text",
    "text_purged_at",
    "claim_id",
    "lang",
    "deleted_at",
)
INSERT_EVENT = text(
    "INSERT INTO events ("
    + ", ".join(EVENT_COLUMNS)
    + ") VALUES ("
    + ", ".join(":" + name for name in EVENT_COLUMNS)
    + ") RETURNING id"
)


def key(n: int) -> str:
    """A 20-character stand-in for a keyed URI (the real keys come from plan 03-04)."""
    return f"k{n:019d}"


@pytest.fixture
def engine(clean_db: str) -> Iterator[Engine]:
    eng = create_engine(clean_db, poolclass=NullPool)
    try:
        yield eng
    finally:
        eng.dispose()


def insert_cascade(connection: Connection, root_uri: str) -> int:
    row = connection.execute(
        text(
            "INSERT INTO cascades (root_uri, tracking_ends_at, first_event_at, last_event_at) "
            "VALUES (:root_uri, :t, :t, :t) RETURNING id"
        ),
        {"root_uri": root_uri, "t": T0},
    )
    return int(row.scalar_one())


def insert_account(connection: Connection, pseudonym: str = "p" * 16) -> int:
    row = connection.execute(
        text("INSERT INTO accounts (pseudonym, first_observed_at) VALUES (:p, :t) RETURNING id"),
        {"p": pseudonym, "t": T0},
    )
    return int(row.scalar_one())


def insert_claim(
    connection: Connection, claim_key: str = "c" * 26, kind: str = "social_link"
) -> int:
    row = connection.execute(
        text(
            "INSERT INTO claims (kind, claim_key, text_hash, url_canonical) "
            "VALUES (:kind, :claim_key, :text_hash, :url) RETURNING id"
        ),
        {"kind": kind, "claim_key": claim_key, "text_hash": "h" * 26, "url": "https://ex.org/a"},
    )
    return int(row.scalar_one())


def event_row(kind: str, n: int, cascade_id: int | None, **overrides: Any) -> dict[str, Any]:
    """A valid row of ``kind`` (root, reply, quote, repost); overrides break one rule."""
    row: dict[str, Any] = dict.fromkeys(EVENT_COLUMNS)
    row.update(uri=key(n), edge_kind=kind, cascade_id=cascade_id, observed_at=T0)
    if kind == "root":
        row.update(inferred=False, parent_state="none", depth=0, lang="en", text="root text")
    elif kind == "repost":
        row.update(inferred=True, parent_uri=key(1), parent_state="resolved")
    else:
        row.update(inferred=False, parent_uri=key(1), parent_state="orphan", depth=1)
    row.update(overrides)
    return row


def insert_event(connection: Connection, row: dict[str, Any]) -> int:
    return int(connection.execute(INSERT_EVENT, row).scalar_one())


def setup_cascade(engine: Engine) -> int:
    with engine.begin() as connection:
        cascade_id = insert_cascade(connection, key(1))
        insert_event(connection, event_row("root", 1, cascade_id))
    return cascade_id


def assert_rejected(engine: Engine, constraint: str, statement: Any, params: Any) -> None:
    with pytest.raises(IntegrityError) as caught, engine.begin() as connection:
        connection.execute(statement, params)
    assert caught.value.orig is not None
    assert caught.value.orig.diag.constraint_name == constraint  # type: ignore[attr-defined]


def assert_event_rejected(engine: Engine, constraint: str, row: dict[str, Any]) -> None:
    assert_rejected(engine, constraint, INSERT_EVENT, row)


def count(engine: Engine, table: str) -> int:
    statements = {
        "events": "SELECT count(*) FROM events",
        "cascades": "SELECT count(*) FROM cascades",
        "news_fetches": "SELECT count(*) FROM news_fetches",
    }
    with engine.connect() as connection:
        return int(connection.execute(text(statements[table])).scalar_one())


# --- valid shapes ----------------------------------------------------------------------------
def test_valid_root_reply_quote_and_repost_are_accepted(engine: Engine) -> None:
    cascade_id = setup_cascade(engine)
    with engine.begin() as connection:
        insert_event(connection, event_row("reply", 2, cascade_id))
        insert_event(connection, event_row("quote", 3, cascade_id, parent_state="resolved"))
        insert_event(connection, event_row("repost", 4, cascade_id))
    assert count(engine, "events") == 4


def test_server_defaults_apply(engine: Engine) -> None:
    cascade_id = setup_cascade(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO events (uri, edge_kind, inferred, parent_uri, cascade_id, "
                "observed_at) VALUES (:uri, 'reply', false, :parent, :cid, :t)"
            ),
            {"uri": key(9), "parent": key(1), "cid": cascade_id, "t": T0},
        )
        state = connection.execute(
            text("SELECT parent_state FROM events WHERE uri = :uri"), {"uri": key(9)}
        ).scalar_one()
        cascade = (
            connection.execute(
                text(
                    "SELECT event_count, overflow_count, rollup_version, enrich_dirty, "
                    "overflow_through_us FROM cascades WHERE id = :cid"
                ),
                {"cid": cascade_id},
            )
            .mappings()
            .one()
        )
        run = (
            connection.execute(
                text(
                    "INSERT INTO ingest_runs (source, mode, started_at, status) "
                    "VALUES ('jetstream', 'live', :t, 'running') "
                    "RETURNING counters, resume_gap, gap_count"
                ),
                {"t": T0},
            )
            .mappings()
            .one()
        )
    assert state == "orphan"
    assert dict(cascade) == {
        "event_count": 0,
        "overflow_count": 0,
        "rollup_version": 0,
        "enrich_dirty": True,
        "overflow_through_us": None,
    }
    assert dict(run) == {"counters": {}, "resume_gap": False, "gap_count": 0}


# --- D-12 edge semantics -------------------------------------------------------------------
def test_a_root_with_a_parent_is_rejected(engine: Engine) -> None:
    cascade_id = setup_cascade(engine)
    row = event_row("root", 2, cascade_id, parent_uri=key(1))
    assert_event_rejected(engine, "ck_events_root_iff_no_parent", row)


def test_a_reply_without_a_parent_is_rejected(engine: Engine) -> None:
    cascade_id = setup_cascade(engine)
    row = event_row("reply", 2, cascade_id, parent_uri=None)
    assert_event_rejected(engine, "ck_events_root_iff_no_parent", row)


def test_inferred_on_a_non_repost_is_rejected(engine: Engine) -> None:
    cascade_id = setup_cascade(engine)
    row = event_row("reply", 2, cascade_id, inferred=True)
    assert_event_rejected(engine, "ck_events_inferred_iff_repost", row)


def test_a_repost_that_is_not_inferred_is_rejected(engine: Engine) -> None:
    cascade_id = setup_cascade(engine)
    row = event_row("repost", 2, cascade_id, inferred=False)
    assert_event_rejected(engine, "ck_events_inferred_iff_repost", row)


def test_a_repost_with_a_depth_is_rejected(engine: Engine) -> None:
    cascade_id = setup_cascade(engine)
    row = event_row("repost", 2, cascade_id, depth=1)
    assert_event_rejected(engine, "ck_events_repost_has_no_depth", row)


def test_an_unknown_edge_kind_is_rejected(engine: Engine) -> None:
    cascade_id = setup_cascade(engine)
    row = event_row("reply", 2, cascade_id, edge_kind="like")
    assert_event_rejected(engine, "ck_events_edge_kind", row)


# --- D-14 orphan states -----------------------------------------------------------------------
def test_parent_state_none_on_a_reply_is_rejected(engine: Engine) -> None:
    cascade_id = setup_cascade(engine)
    row = event_row("reply", 2, cascade_id, parent_state="none")
    assert_event_rejected(engine, "ck_events_none_iff_root", row)


def test_a_root_marked_orphan_is_rejected(engine: Engine) -> None:
    with engine.begin() as connection:
        cascade_id = insert_cascade(connection, key(1))
    row = event_row("root", 1, cascade_id, parent_state="orphan")
    assert_event_rejected(engine, "ck_events_none_iff_root", row)


def test_an_unknown_parent_state_is_rejected(engine: Engine) -> None:
    cascade_id = setup_cascade(engine)
    row = event_row("reply", 2, cascade_id, parent_state="pending")
    assert_event_rejected(engine, "ck_events_parent_state", row)


def test_a_self_parent_is_rejected(engine: Engine) -> None:
    cascade_id = setup_cascade(engine)
    with engine.begin() as connection:
        reply_id = insert_event(connection, event_row("reply", 2, cascade_id))
    assert_rejected(
        engine,
        "ck_events_no_self_parent",
        text("UPDATE events SET parent_event_id = id WHERE id = :id"),
        {"id": reply_id},
    )


# --- D-18 minimisation ------------------------------------------------------------------------
def test_text_on_a_reply_is_rejected(engine: Engine) -> None:
    cascade_id = setup_cascade(engine)
    row = event_row("reply", 2, cascade_id, text="reply text")
    assert_event_rejected(engine, "ck_events_text_only_on_root", row)


def test_a_purged_text_must_be_null(engine: Engine) -> None:
    with engine.begin() as connection:
        cascade_id = insert_cascade(connection, key(1))
    row = event_row("root", 1, cascade_id, text_purged_at=T0)
    assert_event_rejected(engine, "ck_events_purged_text_is_null", row)
    with engine.begin() as connection:
        insert_event(connection, event_row("root", 1, cascade_id, text=None, text_purged_at=T0))
    assert count(engine, "events") == 1


# --- D-16 tombstones ----------------------------------------------------------------------------
def test_a_tombstone_that_keeps_its_account_is_rejected(engine: Engine) -> None:
    with engine.begin() as connection:
        cascade_id = insert_cascade(connection, key(1))
        account_id = insert_account(connection)
    row = event_row(
        "root", 1, cascade_id, text=None, lang=None, account_id=account_id, deleted_at=T0
    )
    assert_event_rejected(engine, "ck_events_tombstone_is_minimal", row)


@pytest.mark.parametrize(
    "field",
    ["text", "lang", "occurred_at", "claim_id"],
)
def test_a_tombstone_that_keeps_content_is_rejected(engine: Engine, field: str) -> None:
    with engine.begin() as connection:
        cascade_id = insert_cascade(connection, key(1))
        claim_id = insert_claim(connection)
    values = {"text": "kept text", "lang": "en", "occurred_at": T0, "claim_id": claim_id}
    row = event_row("root", 1, cascade_id, text=None, lang=None, deleted_at=T0)
    row[field] = values[field]
    assert_event_rejected(engine, "ck_events_tombstone_is_minimal", row)


def test_a_clean_tombstone_is_accepted_and_keeps_the_skeleton(engine: Engine) -> None:
    cascade_id = setup_cascade(engine)
    with engine.begin() as connection:
        insert_event(connection, event_row("reply", 2, cascade_id, deleted_at=T0))
        insert_event(connection, event_row("repost", 3, cascade_id, deleted_at=T0))
        kept = (
            connection.execute(
                text(
                    "SELECT edge_kind, parent_uri, cascade_id, observed_at FROM events "
                    "WHERE uri = :uri"
                ),
                {"uri": key(2)},
            )
            .mappings()
            .one()
        )
    assert dict(kept) == {
        "edge_kind": "reply",
        "parent_uri": key(1),
        "cascade_id": cascade_id,
        "observed_at": T0,
    }


# --- keys, foreign keys and the other enumerations ------------------------------------------
def test_a_duplicate_uri_is_rejected(engine: Engine) -> None:
    cascade_id = setup_cascade(engine)
    row = event_row("reply", 1, cascade_id)
    assert_event_rejected(engine, "uq_events_uri", row)


def test_deleting_a_cascade_deletes_its_events(engine: Engine) -> None:
    cascade_id = setup_cascade(engine)
    with engine.begin() as connection:
        insert_event(connection, event_row("reply", 2, cascade_id))
        connection.execute(text("DELETE FROM cascades WHERE id = :id"), {"id": cascade_id})
    assert count(engine, "events") == 0
    assert count(engine, "cascades") == 0


def test_deleting_a_parent_event_sets_parent_event_id_to_null(engine: Engine) -> None:
    cascade_id = setup_cascade(engine)
    with engine.begin() as connection:
        parent_id = insert_event(connection, event_row("reply", 2, cascade_id))
        child = event_row("reply", 3, cascade_id, parent_uri=key(2), parent_event_id=parent_id)
        child["parent_state"] = "resolved"
        child_id = insert_event(connection, child)
        connection.execute(text("DELETE FROM events WHERE id = :id"), {"id": parent_id})
        remaining = connection.execute(
            text("SELECT parent_event_id FROM events WHERE id = :id"), {"id": child_id}
        ).scalar_one()
    assert remaining is None


def test_deleting_an_account_or_claim_unlinks_its_events(engine: Engine) -> None:
    cascade_id = setup_cascade(engine)
    with engine.begin() as connection:
        account_id = insert_account(connection)
        claim_id = insert_claim(connection)
        reply_id = insert_event(
            connection, event_row("reply", 2, cascade_id, account_id=account_id, claim_id=claim_id)
        )
        connection.execute(text("DELETE FROM accounts WHERE id = :id"), {"id": account_id})
        connection.execute(text("DELETE FROM claims WHERE id = :id"), {"id": claim_id})
        links = (
            connection.execute(
                text("SELECT account_id, claim_id FROM events WHERE id = :id"), {"id": reply_id}
            )
            .mappings()
            .one()
        )
    assert dict(links) == {"account_id": None, "claim_id": None}


def test_an_unknown_claim_kind_is_rejected(engine: Engine) -> None:
    assert_rejected(
        engine,
        "ck_claims_kind",
        text("INSERT INTO claims (kind, claim_key, text_hash) VALUES (:k, :ck, :h)"),
        {"k": "rumour", "ck": "c" * 26, "h": "h" * 26},
    )


def test_claim_key_is_unique(engine: Engine) -> None:
    with engine.begin() as connection:
        insert_claim(connection, "d" * 26)
    assert_rejected(
        engine,
        "uq_claims_claim_key",
        text("INSERT INTO claims (kind, claim_key, text_hash) VALUES (:k, :ck, :h)"),
        {"k": "news_headline", "ck": "d" * 26, "h": "x" * 26},
    )


def test_account_pseudonym_is_unique(engine: Engine) -> None:
    with engine.begin() as connection:
        insert_account(connection, "q" * 16)
    assert_rejected(
        engine,
        "uq_accounts_pseudonym",
        text("INSERT INTO accounts (pseudonym, first_observed_at) VALUES (:p, :t)"),
        {"p": "q" * 16, "t": T0},
    )


def test_an_unknown_run_mode_is_rejected(engine: Engine) -> None:
    assert_rejected(
        engine,
        "ck_ingest_runs_mode",
        text("INSERT INTO ingest_runs (source, mode, started_at, status) VALUES (:s, :m, :t, :st)"),
        {"s": "jetstream", "m": "backfill", "t": T0, "st": "running"},
    )


def test_deleting_a_news_query_deletes_its_fetches_and_unlinks_its_claims(engine: Engine) -> None:
    with engine.begin() as connection:
        query_id = connection.execute(
            text("INSERT INTO news_queries (slug, query) VALUES (:s, :q) RETURNING id"),
            {"s": "wildfires", "q": "wildfires and floods"},
        ).scalar_one()
        connection.execute(
            text("INSERT INTO news_fetches (query_id, called_at) VALUES (:q, :t)"),
            {"q": query_id, "t": T0},
        )
        claim_id = connection.execute(
            text(
                "INSERT INTO claims (kind, claim_key, text_hash, query_id) "
                "VALUES ('news_headline', :ck, :h, :q) RETURNING id"
            ),
            {"ck": "n" * 26, "h": "h" * 26, "q": query_id},
        ).scalar_one()
        outcome = connection.execute(text("SELECT outcome FROM news_fetches")).scalar_one()
        connection.execute(text("DELETE FROM news_queries WHERE id = :id"), {"id": query_id})
        linked = connection.execute(
            text("SELECT query_id FROM claims WHERE id = :id"), {"id": claim_id}
        ).scalar_one()
    assert outcome == "pending"
    assert count(engine, "news_fetches") == 0
    assert linked is None
