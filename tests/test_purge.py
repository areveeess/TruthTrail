"""The retention purge on a real PostgreSQL (D-16, D-18, OD-1; threats T-03-41, T-03-44).

Every test passes an explicit policy with small, arbitrary windows and an explicit ``as_of``;
none reads a Policy default, so no owner-decision value is hard-coded here (D-03). Each window
is tested at its boundary with rows one second on either side. Also: tombstones of every edge
kind are hard-deleted and their children become honest orphans after enrich; a deleted root's
cascade stays hidden; the dormant pass runs only when enabled; purge is idempotent, bounded by
its deadline (a rerun finishes), previewable with a dry run, and single-flight.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from conftest import (
    APPLICATION_TABLES,
    enrich_projection,
    insert_forest,
)
from sqlalchemy import text

from truthtrail.db.locks import PURGE_LOCK_KEY, release_advisory_lock, try_advisory_lock
from truthtrail.enrich import purge as purge_module
from truthtrail.enrich.apply import enrich_dirty
from truthtrail.enrich.purge import PASS_NAMES, PurgeResult, purge

pytestmark = pytest.mark.requires_db

AS_OF = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
TEXT_DAYS = 5
CASCADE_DAYS = 20
TOMBSTONE_DAYS = 2
NEWS_DAYS = 10
SECOND = timedelta(seconds=1)


def days_ago(days: float, plus: timedelta = timedelta(0)) -> datetime:
    return AS_OF - timedelta(days=days) + plus


@pytest.fixture
def engine(clean_db: str, make_engine: Any) -> Any:
    return make_engine(clean_db, role="jobs")


@pytest.fixture
def policy(explicit_policy: Any) -> Any:
    def build(**overrides: Any) -> Any:
        values = {
            "retention_text_days": TEXT_DAYS,
            "retention_cascade_days": CASCADE_DAYS,
            "retention_tombstone_days": TOMBSTONE_DAYS,
            "retention_news_days": NEWS_DAYS,
            "retention_dormant_days": 0,
        }
        values.update(overrides)
        return explicit_policy(**values)

    return build


def run(engine: Any, policy: Any, **kwargs: Any) -> PurgeResult:
    kwargs.setdefault("as_of", AS_OF)
    kwargs.setdefault("max_seconds", 60)
    result = purge(engine, policy, **kwargs)
    assert not result.locked
    return result


def execute(engine: Any, sql: str, **params: Any) -> None:
    with engine.begin() as connection:
        connection.execute(text(sql), params)


def scalar(engine: Any, sql: str, **params: Any) -> Any:
    with engine.connect() as connection:
        return connection.execute(text(sql), params).scalar_one()


def rows(engine: Any, sql: str, **params: Any) -> list[tuple[Any, ...]]:
    with engine.connect() as connection:
        return [tuple(r) for r in connection.execute(text(sql), params)]


def snapshot(engine: Any) -> dict[str, list[tuple[Any, ...]]]:
    """Every application table, every column, ordered by id (a full before/after image)."""
    with engine.connect() as connection:
        return {
            table: [
                tuple(r) for r in connection.execute(text("SELECT * FROM " + table + " ORDER BY 1"))
            ]
            for table in APPLICATION_TABLES
        }


def cascade(
    engine: Any, root: str, start: datetime, children: int = 0, *, base: int = 1000, **kw: Any
) -> int:
    """A cascade whose root is observed at ``start`` with ``children`` replies 1 s apart."""
    forest = [(root, "root", None, start, "acct-" + root[-4:], False)]
    forest += [
        (f"{root}-c{i}", "reply", root, start + (i + 1) * SECOND, f"acct-c{i}", False)
        for i in range(children)
    ]
    return insert_forest(engine, forest, root_uri=root, id_base=base, **kw)


def set_text(engine: Any, uri: str, value: str = "constructed root text") -> None:
    execute(engine, "UPDATE events SET text = :t WHERE uri = :u", t=value, u=uri)


def tombstone(engine: Any, uri: str, deleted_at: datetime) -> None:
    execute(
        engine,
        "UPDATE events SET deleted_at = :d, account_id = NULL, text = NULL, claim_id = NULL,"
        " lang = NULL, occurred_at = NULL WHERE uri = :u",
        d=deleted_at,
        u=uri,
    )


def add_claim(engine: Any, key: str, kind: str = "social_link", created: Any = None) -> int:
    with engine.begin() as connection:
        return int(
            connection.execute(
                text(
                    "INSERT INTO claims (kind, claim_key, text, text_hash, created_at)"
                    " VALUES (:k, :key, 'constructed publisher title', :key,"
                    " COALESCE(:c, now())) RETURNING id"
                ),
                {"k": kind, "key": key, "c": created},
            ).scalar_one()
        )


# --- Text window -----------------------------------------------------------------------------
def test_root_text_is_purged_after_the_text_window_and_kept_inside_it(
    engine: Any, policy: Any
) -> None:
    cascade(engine, "old-root", days_ago(TEXT_DAYS, -SECOND), base=1000)
    cascade(engine, "new-root", days_ago(TEXT_DAYS, SECOND), base=2000)
    set_text(engine, "old-root")
    set_text(engine, "new-root")
    result = run(engine, policy())
    assert result.counts["text"] == 1
    assert rows(engine, "SELECT uri, text IS NULL, text_purged_at FROM events ORDER BY uri") == [
        ("new-root", False, None),
        ("old-root", True, AS_OF),
    ]


def test_zero_text_days_purges_every_text_at_once(engine: Any, policy: Any) -> None:
    cascade(engine, "root-a", AS_OF, base=1000)
    cascade(engine, "root-b", days_ago(1), base=2000)
    set_text(engine, "root-a")
    set_text(engine, "root-b")
    assert run(engine, policy(retention_text_days=0)).counts["text"] == 2
    assert scalar(engine, "SELECT count(*) FROM events WHERE text IS NOT NULL") == 0


# --- Cascade window --------------------------------------------------------------------------
def test_whole_cascades_older_than_the_window_go_with_their_events(
    engine: Any, policy: Any
) -> None:
    cascade(engine, "old-root", days_ago(CASCADE_DAYS, -SECOND), children=3, base=1000)
    cascade(engine, "new-root", days_ago(CASCADE_DAYS, SECOND), children=2, base=2000)
    result = run(engine, policy())
    assert (result.counts["cascades"], result.counts["cascade_events"]) == (1, 4)
    assert rows(engine, "SELECT root_uri FROM cascades") == [("new-root",)]
    assert scalar(engine, "SELECT count(*) FROM events") == 3
    assert scalar(engine, "SELECT count(*) FROM events WHERE uri LIKE 'old-root%'") == 0


def test_ingest_runs_older_than_the_cascade_window_are_removed(engine: Any, policy: Any) -> None:
    for started in (days_ago(CASCADE_DAYS, -SECOND), days_ago(CASCADE_DAYS, SECOND)):
        execute(
            engine,
            "INSERT INTO ingest_runs (source, mode, started_at, status) VALUES"
            " ('test', 'replay', :s, 'ok')",
            s=started,
        )
    assert run(engine, policy()).counts["ingest_runs"] == 1
    assert rows(engine, "SELECT started_at FROM ingest_runs") == [(days_ago(CASCADE_DAYS, SECOND),)]


# --- Claims, news and accounts ---------------------------------------------------------------
def test_unreferenced_social_claims_go_and_referenced_ones_stay(engine: Any, policy: Any) -> None:
    linked = add_claim(engine, "claim-linked")
    add_claim(engine, "claim-orphaned")
    shared = add_claim(engine, "claim-shared")
    first = cascade(engine, "root-one", days_ago(1), base=1000)
    second = cascade(engine, "root-two", days_ago(1), base=2000)
    third = cascade(engine, "root-three", days_ago(1), base=3000)
    execute(engine, "UPDATE cascades SET claim_id = :c WHERE id = :i", c=linked, i=first)
    execute(
        engine,
        "UPDATE cascades SET claim_id = :c WHERE id IN (:a, :b)",
        c=shared,
        a=second,
        b=third,
    )
    execute(engine, "UPDATE events SET claim_id = :c WHERE uri = 'root-two'", c=shared)
    # root-two is deleted: the writer tombstones the root and unlinks the claim (plan 03-05);
    # root-three still links the same article, so the claim must stay.
    tombstone(engine, "root-two", days_ago(1))
    execute(
        engine,
        "UPDATE cascades SET claim_id = NULL, root_deleted_at = :d WHERE id = :i",
        d=days_ago(1),
        i=second,
    )
    assert run(engine, policy()).counts["claims"] == 1
    keys = {k for (k,) in rows(engine, "SELECT claim_key FROM claims")}
    assert keys == {"claim-linked", "claim-shared"}
    execute(
        engine,
        "UPDATE cascades SET claim_id = NULL, root_deleted_at = :d WHERE id = :i",
        d=days_ago(1),
        i=third,
    )
    assert run(engine, policy()).counts["claims"] == 1
    assert {k for (k,) in rows(engine, "SELECT claim_key FROM claims")} == {"claim-linked"}


def test_a_claim_referenced_only_by_an_event_is_kept(engine: Any, policy: Any) -> None:
    claim = add_claim(engine, "claim-event-only")
    cascade(engine, "root-one", days_ago(1))
    execute(engine, "UPDATE events SET claim_id = :c WHERE uri = 'root-one'", c=claim)
    assert run(engine, policy()).counts["claims"] == 0


def test_news_claims_and_fetches_older_than_the_news_window_go(engine: Any, policy: Any) -> None:
    add_claim(engine, "news-old", "news_headline", days_ago(NEWS_DAYS, -SECOND))
    add_claim(engine, "news-new", "news_headline", days_ago(NEWS_DAYS, SECOND))
    add_claim(engine, "social-old", "social_link", days_ago(NEWS_DAYS * 3))
    cascade(engine, "root-one", days_ago(1))
    execute(
        engine,
        "UPDATE cascades SET claim_id = (SELECT id FROM claims WHERE claim_key = 'social-old')",
    )
    with engine.begin() as connection:
        query = connection.execute(
            text(
                "INSERT INTO news_queries (slug, query) VALUES ('topic', 'constructed')"
                " RETURNING id"
            )
        ).scalar_one()
    for called in (days_ago(NEWS_DAYS, -SECOND), days_ago(NEWS_DAYS, SECOND)):
        execute(
            engine,
            "INSERT INTO news_fetches (query_id, called_at, outcome) VALUES (:q, :c, 'ok')",
            q=query,
            c=called,
        )
    result = run(engine, policy())
    assert (result.counts["news_claims"], result.counts["news_fetches"]) == (1, 1)
    assert {k for (k,) in rows(engine, "SELECT claim_key FROM claims")} == {
        "news-new",
        "social-old",
    }
    assert rows(engine, "SELECT called_at FROM news_fetches") == [(days_ago(NEWS_DAYS, SECOND),)]


def test_accounts_without_events_are_removed_and_others_kept(engine: Any, policy: Any) -> None:
    cascade(engine, "root-one", days_ago(1), children=1)
    execute(
        engine,
        "INSERT INTO accounts (pseudonym, first_observed_at) VALUES ('acct-lonely', :t)",
        t=days_ago(3),
    )
    tombstone(engine, "root-one-c0", days_ago(0.5))  # its account now has no event
    result = run(engine, policy())
    assert result.counts["accounts"] == 2
    assert rows(engine, "SELECT pseudonym FROM accounts") == [("acct--one",)]


# --- Tombstones -----------------------------------------------------------------------------
def test_tombstones_of_every_kind_are_deleted_after_the_window_and_children_become_orphans(
    engine: Any, policy: Any
) -> None:
    start = days_ago(5)
    insert_forest(
        engine,
        [
            ("root-one", "root", None, start, "acct-a", False),
            ("mid", "reply", "root-one", start + SECOND, "acct-b", False),
            ("leaf", "reply", "mid", start + 2 * SECOND, "acct-c", False),
            ("share", "repost", "root-one", start + 3 * SECOND, "acct-d", False),
            ("young", "quote", "root-one", start + 4 * SECOND, "acct-e", False),
        ],
        root_uri="root-one",
    )
    insert_forest(
        engine,
        [
            ("root-two", "root", None, start, "acct-f", False),
            ("kid", "reply", "root-two", start + SECOND, "acct-g", False),
        ],
        root_uri="root-two",
        id_base=5000,
    )
    tombstone(engine, "mid", days_ago(TOMBSTONE_DAYS, -SECOND))
    tombstone(engine, "share", days_ago(TOMBSTONE_DAYS, -SECOND))
    tombstone(engine, "young", days_ago(TOMBSTONE_DAYS, SECOND))  # inside the window: kept
    tombstone(engine, "root-two", days_ago(TOMBSTONE_DAYS, -SECOND))
    execute(
        engine,
        "UPDATE cascades SET root_deleted_at = :d WHERE root_uri = 'root-two'",
        d=days_ago(TOMBSTONE_DAYS, -SECOND),
    )
    enrich_dirty(engine, as_of=AS_OF)
    assert scalar(engine, "SELECT count(*) FROM cascades WHERE enrich_dirty") == 0
    result = run(engine, policy())
    assert (result.counts["tombstones"], result.counts["cascades_marked_dirty"]) == (3, 2)
    remaining = {u for (u,) in rows(engine, "SELECT uri FROM events")}
    assert remaining == {"root-one", "leaf", "young", "kid"}
    assert scalar(engine, "SELECT count(*) FROM cascades WHERE enrich_dirty") == 2
    enrich_dirty(engine, as_of=AS_OF)
    events = enrich_projection(engine)["events"]
    assert events["leaf"][:3] == ("orphan", None, None)  # an honest orphan, not re-parented
    assert events["kid"][:3] == ("orphan", None, None)
    assert events["young"][:3] == ("resolved", "root-one", 1)
    hidden = rows(engine, "SELECT root_deleted_at FROM cascades WHERE root_uri = 'root-two'")
    assert hidden == [(days_ago(TOMBSTONE_DAYS, -SECOND),)]  # the deleted root stays hidden


# --- Dormant cascades -----------------------------------------------------------------------
def test_the_dormant_pass_runs_only_when_positive_and_spares_cascades_with_children(
    engine: Any, policy: Any
) -> None:
    cascade(engine, "lonely-old", days_ago(4, -SECOND), base=1000)
    cascade(engine, "lonely-new", days_ago(4, SECOND), base=2000)
    cascade(engine, "busy-old", days_ago(4, -SECOND), children=1, base=3000)
    disabled = run(engine, policy())
    assert disabled.counts["dormant"] == 0
    assert scalar(engine, "SELECT count(*) FROM cascades") == 3
    enabled = run(engine, policy(retention_dormant_days=4))
    assert (enabled.counts["dormant"], enabled.counts["cascade_events"]) == (1, 1)
    assert {r for (r,) in rows(engine, "SELECT root_uri FROM cascades")} == {
        "lonely-new",
        "busy-old",
    }


# --- Properties of the job ------------------------------------------------------------------
def _everything(engine: Any) -> None:
    cascade(engine, "old-root", days_ago(CASCADE_DAYS + 1), children=2, base=1000)
    cascade(engine, "mid-root", days_ago(TEXT_DAYS + 1), children=2, base=2000)
    cascade(engine, "new-root", days_ago(1), children=1, base=3000)
    for uri in ("old-root", "mid-root", "new-root"):
        set_text(engine, uri)
    tombstone(engine, "mid-root-c0", days_ago(TOMBSTONE_DAYS + 1))
    add_claim(engine, "claim-orphaned")
    add_claim(engine, "news-old", "news_headline", days_ago(NEWS_DAYS + 1))


def test_a_second_purge_changes_nothing(engine: Any, policy: Any) -> None:
    _everything(engine)
    first = run(engine, policy())
    assert first.complete
    assert sum(first.counts[name] for name in PASS_NAMES) > 0
    after = snapshot(engine)
    second = run(engine, policy())
    assert all(count == 0 for count in second.counts.values())
    assert snapshot(engine) == after


def test_dry_run_counts_and_changes_nothing(engine: Any, policy: Any) -> None:
    _everything(engine)
    before = snapshot(engine)
    preview = run(engine, policy(), dry_run=True)
    assert preview.dry_run
    assert preview.line().startswith("purge status=dry_run ")
    assert snapshot(engine) == before
    real = run(engine, policy())
    for name in ("text", "tombstones", "cascades", "news_claims", "cascades_marked_dirty"):
        assert preview.counts[name] == real.counts[name], name
    assert preview.counts["cascade_events"] == real.counts["cascade_events"]


def test_a_tiny_deadline_stops_with_a_partial_result_and_a_rerun_finishes(
    engine: Any, policy: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    for index in range(3):
        cascade(engine, f"root-{index}", days_ago(TEXT_DAYS + 1), base=1000 * (index + 1))
        set_text(engine, f"root-{index}")
    ticks = iter(range(10_000))
    monkeypatch.setattr(purge_module, "_monotonic", lambda: float(next(ticks)))
    # deadline = start + 2 ticks: one text batch of one row runs, then the deadline passes
    partial = run(engine, policy(), max_seconds=2, batch_rows=1)
    assert not partial.complete
    assert partial.line().startswith("purge status=partial ")
    assert partial.counts["text"] == 1
    assert scalar(engine, "SELECT count(*) FROM events WHERE text IS NOT NULL") == 2
    monkeypatch.undo()
    finished = run(engine, policy(), batch_rows=1)
    assert finished.complete
    assert finished.counts["text"] == 2
    assert scalar(engine, "SELECT count(*) FROM events WHERE text IS NOT NULL") == 0


def test_small_batches_loop_until_every_row_is_done(engine: Any, policy: Any) -> None:
    for index in range(5):
        cascade(
            engine, f"old-{index}", days_ago(CASCADE_DAYS + 1), children=1, base=1000 * (index + 1)
        )
    result = run(engine, policy(), batch_rows=2, batch_cascades=2)
    assert result.complete
    assert (result.counts["cascades"], result.counts["cascade_events"]) == (5, 10)
    assert scalar(engine, "SELECT count(*) FROM cascades") == 0


def test_a_concurrent_purge_is_refused_by_the_advisory_lock(
    engine: Any, policy: Any, clean_db: str, make_engine: Any
) -> None:
    _everything(engine)
    before = snapshot(engine)
    other = make_engine(clean_db, role="jobs")
    with other.connect() as holder:
        assert try_advisory_lock(holder, PURGE_LOCK_KEY)
        refused = purge(engine, policy(), as_of=AS_OF, max_seconds=60)
        assert refused == PurgeResult(locked=True)
        assert refused.line() == "purge status=locked"
        release_advisory_lock(holder, PURGE_LOCK_KEY)
    assert snapshot(engine) == before


def test_the_windows_come_from_the_policy_object(engine: Any, policy: Any) -> None:
    cascade(engine, "root-a", days_ago(8))
    set_text(engine, "root-a")
    assert run(engine, policy(retention_text_days=9)).counts["text"] == 0
    assert run(engine, policy(retention_text_days=8)).counts["text"] == 1
    assert run(engine, policy(retention_cascade_days=9)).counts["cascades"] == 0
    assert run(engine, policy(retention_cascade_days=8)).counts["cascades"] == 1


def test_invalid_arguments_are_refused(engine: Any, policy: Any) -> None:
    with pytest.raises(ValueError, match="aware"):
        purge(engine, policy(), as_of=datetime(2026, 11, 6, 12, 0), max_seconds=1)
    with pytest.raises(ValueError, match="positive"):
        purge(engine, policy(), as_of=AS_OF, max_seconds=0)
    with pytest.raises(ValueError, match="positive"):
        purge(engine, policy(), as_of=AS_OF, batch_rows=0)


def test_the_log_line_holds_counts_only(
    engine: Any, policy: Any, caplog: pytest.LogCaptureFixture
) -> None:
    _everything(engine)
    keys = {u for (u,) in rows(engine, "SELECT uri FROM events")}
    keys |= {p for (p,) in rows(engine, "SELECT pseudonym FROM accounts")}
    with caplog.at_level(logging.INFO, logger="truthtrail.enrich.purge"):
        result = run(engine, policy())
    lines = [r.getMessage() for r in caplog.records if r.name == "truthtrail.enrich.purge"]
    assert lines == [result.line()]
    assert not any(key in lines[0] for key in keys)
    assert "constructed" not in lines[0]
