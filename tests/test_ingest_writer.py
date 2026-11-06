"""The collector writer against a real PostgreSQL (D-09, D-14, D-15, D-16, D-18, D-21, OD-1,
OD-3, SC3).

Every test replays the packaged real recording through ReplaySource, the Decider and the writer
(``run_pipeline`` in conftest) under an explicit test policy, never a Policy default. Shapes the
fixture lacks are CONSTRUCTED from the nearest real item; their names start with
``constructed_``.
"""

from dataclasses import replace
from typing import Any

import pytest
from conftest import (
    TEST_SMALL_CASCADE_CAP,
    canonical_projection,
    fixture_items,
    fixture_manifest,
    row_counts,
    run_pipeline,
)
from sqlalchemy import event, text

from truthtrail.ingest import selection
from truthtrail.ingest.normalise import LinkCandidate, NormalizedEvent
from truthtrail.ingest.source import SourceItem
from truthtrail.ingest.writer import (
    CAP_ACTIVE_ROOTS,
    CAP_TOTAL_EVENTS,
    CASCADE_CONFLICT,
    DIGEST_CHARS,
    DUPLICATE,
    OVERFLOW,
    OVERFLOW_UNCOUNTED,
    REPLY_WITHOUT_PARENT,
    SEED_CLAIM_URL_MATCH,
    TRACKING_ENDED,
    UNTRACKED,
    Batch,
    Decider,
    PendingEvent,
    TrackedIndex,
    claim_key_for,
    db_size_bytes,
    digest,
    event_row,
    flush,
    known_claim_urls_for,
    load_known_claim_urls,
    stored_event_count,
)

pytestmark = pytest.mark.requires_db

SOURCE = "test-replay"


@pytest.fixture
def engine(clean_db: str, make_engine: Any) -> Any:
    return make_engine(clean_db, role="collector")


@pytest.fixture(scope="module")
def items() -> list[SourceItem]:
    from conftest import FAKE_PSEUDONYM_SECRET

    from truthtrail.ingest.pseudonym import make_keyer, parse_secret

    return fixture_items(make_keyer(parse_secret(FAKE_PSEUDONYM_SECRET)))


def _scalar(engine: Any, sql: str, **params: Any) -> Any:
    with engine.connect() as connection:
        return connection.execute(text(sql), params).scalar_one()


def _events(items: list[SourceItem]) -> list[NormalizedEvent]:
    return [i.result for i in items if isinstance(i.result, NormalizedEvent)]


def _item(result: NormalizedEvent) -> SourceItem:
    return SourceItem(result, result.time_us)


def _accepted_root(run: Any) -> NormalizedEvent:
    return next(r for r, o in run.per_item if o == "accepted_root")


# --- tracked roots only -----------------------------------------------------------------------
def test_replay_stores_exactly_the_roots_selection_accepts(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    run = run_pipeline(engine, explicit_policy(), items)
    tracked = fixture_manifest()["coverage"]["tracked_roots"]
    assert run.outcomes["accepted_root"] == tracked
    assert row_counts(engine)["cascades"] == tracked
    assert _scalar(engine, "SELECT count(*) FROM events WHERE edge_kind = 'root'") == tracked
    stored = set(run.keys_with("accepted_root"))
    with engine.connect() as connection:
        roots = {r for (r,) in connection.execute(text("SELECT root_uri FROM cascades"))}
    assert roots == stored


def test_children_by_kind_match_the_manifest(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    run = run_pipeline(engine, explicit_policy(), items)
    expected = fixture_manifest()["coverage"]["children_by_kind"]
    for kind, count in expected.items():
        assert run.outcomes["accepted_" + kind] == count
        assert _scalar(engine, "SELECT count(*) FROM events WHERE edge_kind = :k", k=kind) == count


def test_every_stored_child_hangs_off_a_stored_event(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    run_pipeline(engine, explicit_policy(), items)
    loose = _scalar(
        engine,
        "SELECT count(*) FROM events e WHERE e.edge_kind <> 'root' AND NOT EXISTS ("
        " SELECT 1 FROM events p WHERE p.uri IN (e.parent_uri, e.reply_root_uri)"
        " AND p.cascade_id = e.cascade_id)",
    )
    assert loose == 0
    assert _scalar(engine, "SELECT count(*) FROM events WHERE cascade_id IS NULL") == 0


def test_no_event_exists_for_an_untracked_child(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    run = run_pipeline(engine, explicit_policy(), items)
    refused = run.keys_with(UNTRACKED)
    assert refused, "the fixture has untracked children"
    found = _scalar(engine, "SELECT count(*) FROM events WHERE uri = ANY(:k)", k=refused)
    assert found == 0
    not_roots = run.keys_with("not_allowlisted") + run.keys_with("lang")
    assert _scalar(engine, "SELECT count(*) FROM events WHERE uri = ANY(:k)", k=not_roots) == 0


def test_refusal_reasons_are_counted_by_name(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    run = run_pipeline(engine, explicit_policy(), items)
    assert sum(run.outcomes.values()) == len(items)
    negatives = fixture_manifest()["coverage"]["negative_controls"]
    assert run.outcomes["not_allowlisted"] == negatives["near_miss_non_allowlisted"]
    assert run.outcomes["shortener"] == negatives["shortener"]
    assert run.outcomes["lang"] == negatives["non_english_allowlisted"]
    assert run.outcomes[UNTRACKED] > 0
    assert set(run.outcomes) <= {
        *selection.SEED_REASONS,
        UNTRACKED,
        "accepted_root",
        "accepted_reply",
        "accepted_quote",
        "accepted_repost",
        "delete",
        "account_deleted",
        "account_takedown",
        "sync",
        CASCADE_CONFLICT,
    }


# --- caps (D-21, OD-3): counted refusals, never eviction ------------------------------------------
def test_active_root_cap_refuses_new_roots_and_evicts_nothing(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    full = run_pipeline(engine, explicit_policy(), items)
    first_five = full.keys_with("accepted_root")[:5]
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE accounts, claims, cascades, events CASCADE"))
    run = run_pipeline(engine, explicit_policy(track_max_active_roots=5), items)
    assert run.outcomes["accepted_root"] == 5
    assert run.outcomes[CAP_ACTIVE_ROOTS] == full.outcomes["accepted_root"] - 5
    with engine.connect() as connection:
        roots = [r for (r,) in connection.execute(text("SELECT root_uri FROM cascades"))]
    assert sorted(roots) == sorted(first_five)


def test_total_event_cap_stops_storing_at_the_bound(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    run = run_pipeline(engine, explicit_policy(store_max_events_total=50), items, batch_rows=7)
    assert row_counts(engine)["events"] == 50
    assert run.outcomes[CAP_TOTAL_EVENTS] > 0
    with engine.connect() as connection:
        assert stored_event_count(connection) == 50


def test_per_cascade_cap_counts_overflow_and_stores_no_surplus(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    cap = TEST_SMALL_CASCADE_CAP
    run = run_pipeline(engine, explicit_policy(track_max_events_per_cascade=cap), items)
    biggest = _scalar(
        engine, "SELECT max(n) FROM (SELECT count(*) n FROM events GROUP BY cascade_id) s"
    )
    assert biggest == cap
    total = _scalar(engine, "SELECT sum(overflow_count) FROM cascades")
    assert total > 0
    # Independent recount: per cascade, the overflow refusals whose stream time is strictly
    # above every earlier counted one.
    refusals: dict[str, list[int]] = {}
    for result, outcome in run.per_item:
        if outcome in (OVERFLOW, OVERFLOW_UNCOUNTED):
            root = run.index.lookup(result.parent_key) or run.index.lookup(result.reply_root_key)
            refusals.setdefault(root, []).append(result.time_us)
    recount = 0
    for times in refusals.values():
        mark = -1
        for t in times:
            if t > mark:
                recount += 1
                mark = t
    assert recount == total == run.outcomes[OVERFLOW]
    marks = _scalar(engine, "SELECT count(*) FROM cascades WHERE overflow_count > 0")
    assert marks == len(refusals)


# --- order, windows, edges ---------------------------------------------------------------------
def test_a_child_before_its_root_is_refused_untracked(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    full = run_pipeline(engine, explicit_policy(), items)
    roots = {r.uri_key: r for r, o in full.per_item if o == "accepted_root"}
    child = next(r for r, o in full.per_item if o == "accepted_reply" and r.parent_key in roots)
    root = roots[child.parent_key]
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE accounts, claims, cascades, events CASCADE"))
    run = run_pipeline(engine, explicit_policy(), [_item(child), _item(root)])
    assert [o for _r, o in run.per_item] == [UNTRACKED, "accepted_root"]


def test_a_child_after_the_tracking_window_is_refused(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    policy = explicit_policy(track_root_ttl_hours=1)
    full = run_pipeline(engine, explicit_policy(), items)
    root = _accepted_root(full)
    child = next(r for r, o in full.per_item if o == "accepted_reply")
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE accounts, claims, cascades, events CASCADE"))
    late = replace(child, parent_key=root.uri_key, time_us=root.time_us + 3_600_000_000)
    inside = replace(
        child, uri_key="constructedinsidexxxx"[:20], parent_key=root.uri_key, time_us=root.time_us
    )
    run = run_pipeline(engine, policy, [_item(root), _item(late), _item(inside)])
    assert [o for _r, o in run.per_item] == ["accepted_root", TRACKING_ENDED, "accepted_reply"]


def test_root_text_is_written_only_under_a_positive_text_retention(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    full = run_pipeline(engine, explicit_policy(), items)
    real_root = _accepted_root(full)
    assert all(r.text is None for r in _events(items)), "the scrubbed fixture carries no text"
    constructed_root_text = replace(real_root, text="constructed root text marker")
    for days, expected in ((7, "constructed root text marker"), (0, None)):
        with engine.begin() as connection:
            connection.execute(text("TRUNCATE accounts, claims, cascades, events CASCADE"))
        run_pipeline(
            engine, explicit_policy(retention_text_days=days), [_item(constructed_root_text)]
        )
        stored = _scalar(engine, "SELECT text FROM events WHERE uri = :u", u=real_root.uri_key)
        assert stored == expected


def test_claim_rows_hold_the_canonical_url_and_its_host(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    run_pipeline(engine, explicit_policy(), items)
    with engine.connect() as connection:
        claims = connection.execute(
            text("SELECT kind, claim_key, text_hash, url_canonical, link_domain FROM claims")
        ).all()
        unlinked = connection.execute(
            text("SELECT count(*) FROM cascades WHERE claim_id IS NULL AND root_deleted_at IS NULL")
        ).scalar_one()
    assert claims
    assert unlinked == 0
    for kind, key, text_hash, url, host in claims:
        assert kind == "social_link"
        assert key == claim_key_for("social_link", url) == text_hash
        assert host == selection.url_host(url)
        assert selection.canonicalise_url(url) == url


def test_constructed_card_title_goes_to_the_claim_row(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    full = run_pipeline(engine, explicit_policy(), items)
    real_root = _accepted_root(full)
    assert all(r.card_title is None for r in _events(items)), "the fixture carries no titles"
    url = real_root.links[0].url
    constructed_card_title = replace(
        real_root,
        card_title="Constructed publisher title",
        links=(LinkCandidate(selection.LINK_CARD, url, selection.url_host(url)),),
    )
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE accounts, claims, cascades, events CASCADE"))
    run_pipeline(engine, explicit_policy(), [_item(constructed_card_title)])
    title = _scalar(engine, "SELECT text FROM claims WHERE url_canonical = :u", u=url)
    assert title == "Constructed publisher title"


def test_accounts_are_unique_by_pseudonym_and_only_for_stored_events(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    run_pipeline(engine, explicit_policy(), items)
    assert _scalar(engine, "SELECT count(*) - count(DISTINCT pseudonym) FROM accounts") == 0
    orphan_accounts = _scalar(
        engine,
        "SELECT count(*) FROM accounts a WHERE NOT EXISTS ("
        " SELECT 1 FROM events e WHERE e.account_id = a.id)",
    )
    tombstoned = _scalar(engine, "SELECT count(*) FROM events WHERE deleted_at IS NOT NULL")
    assert orphan_accounts <= tombstoned
    assert _scalar(engine, "SELECT max(length(pseudonym)) FROM accounts") == 16


def test_a_reply_with_an_unknown_parent_is_an_orphan_in_the_roots_cascade(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    run_pipeline(engine, explicit_policy(), items)
    with engine.connect() as connection:
        orphans = connection.execute(
            text(
                "SELECT e.parent_state, e.cascade_id, r.cascade_id FROM events e"
                " JOIN events r ON r.uri = e.reply_root_uri"
                " WHERE e.edge_kind = 'reply'"
                " AND NOT EXISTS (SELECT 1 FROM events p WHERE p.uri = e.parent_uri)"
            )
        ).all()
    assert len(orphans) == fixture_manifest()["coverage"]["orphan_replies"]
    for state, cascade, root_cascade in orphans:
        assert state == "orphan"
        assert cascade == root_cascade


def test_cascade_conflict_is_counted_and_the_parent_cascade_wins(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    full = run_pipeline(engine, explicit_policy(), items)
    roots = full.keys_with("accepted_root")[:2]
    first, second = (r for r, _o in full.per_item if getattr(r, "uri_key", None) in roots)
    reply = next(r for r, o in full.per_item if o == "accepted_reply")
    constructed_conflict = replace(
        reply,
        uri_key="constructedconflictx",
        parent_key=first.uri_key,
        reply_root_key=second.uri_key,
        time_us=max(first.time_us, second.time_us),
    )
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE accounts, claims, cascades, events CASCADE"))
    run = run_pipeline(
        engine, explicit_policy(), [_item(first), _item(second), _item(constructed_conflict)]
    )
    assert run.outcomes[CASCADE_CONFLICT] == 1
    owner = _scalar(
        engine,
        "SELECT c.root_uri FROM events e JOIN cascades c ON c.id = e.cascade_id WHERE e.uri = :u",
        u="constructedconflictx",
    )
    assert owner == first.uri_key


def test_a_reply_without_a_usable_parent_is_refused_not_invented(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    full = run_pipeline(engine, explicit_policy(), items)
    root = _accepted_root(full)
    reply = next(r for r, o in full.per_item if o == "accepted_reply")
    constructed_rootonly = replace(
        reply, uri_key="constructedrootonlyx", parent_key=None, reply_root_key=root.uri_key
    )
    run = run_pipeline(engine, explicit_policy(), [_item(constructed_rootonly)])
    assert run.outcomes[REPLY_WITHOUT_PARENT] == 1
    assert _scalar(engine, "SELECT count(*) FROM events WHERE uri = 'constructedrootonlyx'") == 0


def test_stored_rows_follow_the_edge_rules(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    run_pipeline(engine, explicit_policy(), items)
    checks = {
        "SELECT count(*) FROM events WHERE edge_kind = 'root' AND deleted_at IS NULL"
        " AND (parent_state <> 'none' OR inferred OR lang IS NULL OR claim_id IS NULL)": 0,
        "SELECT count(*) FROM events WHERE edge_kind = 'root' AND parent_state <> 'none'": 0,
        "SELECT count(*) FROM events WHERE edge_kind <> 'root' AND (parent_state <> 'orphan'"
        " OR text IS NOT NULL OR lang IS NOT NULL OR claim_id IS NOT NULL)": 0,
        "SELECT count(*) FROM events WHERE inferred <> (edge_kind = 'repost')": 0,
        "SELECT count(*) FROM events WHERE via_uri IS NOT NULL AND edge_kind <> 'repost'": 0,
        "SELECT count(*) FROM events WHERE depth IS NOT NULL OR parent_event_id IS NOT NULL": 0,
    }
    for sql, expected in checks.items():
        assert _scalar(engine, sql) == expected, sql


def test_event_row_dicts_have_one_key_set_for_every_kind() -> None:
    from datetime import UTC, datetime

    now = datetime(2026, 10, 19, tzinfo=UTC)
    shapes = {
        kind: event_row(PendingEvent("u" * 20, kind, "r" * 20, "a" * 16, now, None), 1, 2, 3)
        for kind in ("root", "reply", "quote", "repost")
    }
    keys = {frozenset(row) for row in shapes.values()}
    assert len(keys) == 1
    assert shapes["repost"]["inferred"] is True
    assert shapes["reply"]["inferred"] is False
    assert shapes["reply"]["claim_id"] is None
    assert shapes["root"]["claim_id"] == 3


def test_digests_are_lowercase_base32_of_fixed_length() -> None:
    value = digest("social_link", "https://example.org/a")
    assert len(value) == DIGEST_CHARS
    assert value == value.lower()
    assert set(value) <= set("abcdefghijklmnopqrstuvwxyz234567")
    assert claim_key_for("social_link", "https://example.org/a") == value
    assert claim_key_for("news_headline", "https://example.org/a") != value


# --- checkpoint and capacity helpers
def test_checkpoint_equals_the_maximum_stream_time(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    run_pipeline(engine, explicit_policy(), items)
    expected = max(i.cursor_us for i in items if i.cursor_us is not None)
    cursor = _scalar(
        engine, "SELECT cursor_time_us FROM ingest_checkpoints WHERE source = :s", s=SOURCE
    )
    assert cursor == expected


def test_checkpoint_never_moves_backwards(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    run_pipeline(engine, explicit_policy(), items)
    newest = _scalar(engine, "SELECT cursor_time_us FROM ingest_checkpoints")
    older = Batch()
    older.note_cursor(newest - 60_000_000)
    result = flush(engine, older, source=SOURCE, dialect="v2", host="recorded")
    assert result.checkpoint_us == newest - 60_000_000
    assert _scalar(engine, "SELECT cursor_time_us FROM ingest_checkpoints") == newest


def test_an_empty_batch_writes_no_checkpoint(engine: Any) -> None:
    result = flush(engine, Batch(), source=SOURCE, dialect="v2", host="recorded")
    assert result.inserted == 0
    assert result.checkpoint_us is None
    assert row_counts(engine)["ingest_checkpoints"] == 0


def test_capacity_helpers_return_plausible_values(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    with engine.connect() as connection:
        empty = db_size_bytes(connection)
    run_pipeline(engine, explicit_policy(), items)
    with engine.connect() as connection:
        size = db_size_bytes(connection)
        count = stored_event_count(connection)
    assert 0 < empty <= size < 100_000_000
    assert count == row_counts(engine)["events"]


# --- OD-3 option B -----------------------------------------------------------------------------
def _near_miss(run: Any) -> NormalizedEvent:
    """A real top-level English fixture root refused only because its host is not allowlisted."""
    negatives = fixture_manifest()["coverage"]["negative_controls"]
    assert negatives["near_miss_non_allowlisted"] > 0, "use the real near-miss negative"
    return next(
        r
        for r, o in run.per_item
        if o == "not_allowlisted" and "en" in r.langs and not r.labels and r.links
    )


def _insert_headline(engine: Any, url: str, kind: str = "news_headline") -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO claims (kind, claim_key, text, text_hash, url_canonical)"
                " VALUES (:kind, :key, :title, :key, :url)"
            ),
            {"kind": kind, "key": claim_key_for(kind, url), "title": "headline", "url": url},
        )


def _option_b_run(engine: Any, policy: Any, events: list[NormalizedEvent]) -> Any:
    with engine.connect() as connection:
        known = known_claim_urls_for(connection, policy)
    return run_pipeline(engine, policy, [_item(e) for e in events], known_claim_urls=known)


def test_option_b_seeds_a_non_allowlisted_root_whose_url_is_a_stored_headline(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    near = _near_miss(run_pipeline(engine, explicit_policy(), items))
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE accounts, claims, cascades, events CASCADE"))
    url = near.links[0].url
    _insert_headline(engine, url)
    on = _option_b_run(engine, explicit_policy(track_seed_claim_url_match=True), [near])
    assert on.outcomes[SEED_CLAIM_URL_MATCH] == 1
    assert _scalar(engine, "SELECT count(*) FROM cascades WHERE root_uri = :u", u=near.uri_key) == 1
    social = _scalar(engine, "SELECT url_canonical FROM claims WHERE kind = 'social_link'")
    assert social == url


def test_option_b_off_refuses_the_same_frame_as_not_allowlisted(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    near = _near_miss(run_pipeline(engine, explicit_policy(), items))
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE accounts, claims, cascades, events CASCADE"))
    _insert_headline(engine, near.links[0].url)
    off = _option_b_run(engine, explicit_policy(track_seed_claim_url_match=False), [near])
    assert off.outcomes["not_allowlisted"] == 1
    assert row_counts(engine)["cascades"] == 0


def test_option_b_refuses_when_the_stored_headline_url_differs(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    near = _near_miss(run_pipeline(engine, explicit_policy(), items))
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE accounts, claims, cascades, events CASCADE"))
    _insert_headline(engine, near.links[0].url + "-different")
    run = _option_b_run(engine, explicit_policy(track_seed_claim_url_match=True), [near])
    assert run.outcomes["not_allowlisted"] == 1
    assert row_counts(engine)["cascades"] == 0


def test_load_known_claim_urls_returns_news_headlines_only_and_honours_the_limit(
    engine: Any,
) -> None:
    _insert_headline(engine, "https://example.org/social", kind="social_link")
    for n in range(3):
        _insert_headline(engine, f"https://example.org/news-{n}")
    with engine.connect() as connection:
        everything = load_known_claim_urls(connection)
        limited = load_known_claim_urls(connection, limit=2)
    assert everything == {f"https://example.org/news-{n}" for n in range(3)}
    assert len(limited) == 2
    assert limited <= everything


def test_option_b_keeps_every_hygiene_rule(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    near = _near_miss(run_pipeline(engine, explicit_policy(), items))
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE accounts, claims, cascades, events CASCADE"))
    url = near.links[0].url
    shortener_url = "https://bit.ly/constructed"
    _insert_headline(engine, url)
    _insert_headline(engine, shortener_url)
    variants = {
        "lang": replace(near, uri_key="constructedgermanxxx", langs=("de",)),
        "adult_label": replace(near, uri_key="constructedadultxxxx", labels=frozenset({"porn"})),
        "shortener": replace(
            near,
            uri_key="constructedshortxxxx",
            links=(LinkCandidate(selection.LINK_CARD, shortener_url, "bit.ly"),),
        ),
        UNTRACKED: replace(
            near,
            uri_key="constructedreplyxxxx",
            edge_kind="reply",
            parent_key="unknownparentxxxxxxx",
        ),
    }
    run = _option_b_run(
        engine, explicit_policy(track_seed_claim_url_match=True), list(variants.values())
    )
    assert [o for _r, o in run.per_item] == list(variants)
    assert row_counts(engine)["cascades"] == 0


def test_option_b_off_never_queries_the_claims_table(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    statements: list[str] = []

    def record(_conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        _option_b_run(engine, explicit_policy(track_seed_claim_url_match=False), _events(items))
        off = [s for s in statements if "news_headline" in s or "FROM claims" in s]
        statements.clear()
        _option_b_run(engine, explicit_policy(track_seed_claim_url_match=True), _events(items)[:5])
        on = [s for s in statements if "FROM claims" in s]
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert off == []
    assert len(on) == 1


# --- overflow tally and duplicates (SC3)
def _overflow_columns(engine: Any) -> list[tuple[Any, ...]]:
    with engine.connect() as connection:
        return [
            tuple(r)
            for r in connection.execute(
                text(
                    "SELECT root_uri, overflow_count, overflow_through_us FROM cascades"
                    " ORDER BY root_uri"
                )
            )
        ]


def test_redelivery_never_inflates_the_overflow_tally(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    policy = explicit_policy(track_max_events_per_cascade=TEST_SMALL_CASCADE_CAP)
    run_pipeline(engine, policy, items)
    before = _overflow_columns(engine)
    assert sum(r[1] for r in before) > 0
    # a replay
    again = run_pipeline(engine, policy, items)
    assert again.overflow_counted == 0
    assert _overflow_columns(engine) == before
    # a 30 s rewind from the checkpoint
    cursor = _scalar(engine, "SELECT cursor_time_us FROM ingest_checkpoints")
    since = cursor - policy.ingest_rewind_seconds * 1_000_000
    rewound = [i for i in items if i.cursor_us is not None and i.cursor_us >= since]
    run_pipeline(engine, policy, rewound, since_us=since)
    assert _overflow_columns(engine) == before


def test_the_same_overflow_batch_flushed_twice_counts_once(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    policy = explicit_policy(track_max_events_per_cascade=TEST_SMALL_CASCADE_CAP)
    index = TrackedIndex()
    with engine.connect() as connection:
        index.load(connection, None)
    decider = Decider(policy, index, selection.load_allowlist(policy.track_allowlist_file))
    batch = Batch()
    for item in items:
        batch.note_cursor(item.cursor_us)
        decider.process(item.result, batch)
    assert batch.overflow
    first = flush(engine, batch, source=SOURCE, dialect="v2", host="recorded")
    after_first = _overflow_columns(engine)
    second = flush(engine, batch, source=SOURCE, dialect="v2", host="recorded")
    assert first.overflow_counted > 0
    assert second.inserted == 0
    assert _overflow_columns(engine) == after_first


def test_a_stored_event_redelivered_at_the_cap_is_a_duplicate_not_overflow(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    policy = explicit_policy(track_max_events_per_cascade=TEST_SMALL_CASCADE_CAP)
    run = run_pipeline(engine, policy, items)
    full_root = next(root for root, *_rest in _overflow_columns(engine) if _rest[0] > 0)
    stored_child = next(
        r
        for r, o in run.per_item
        if o.startswith("accepted_")
        and o != "accepted_root"
        and run.index.lookup(r.uri_key) == full_root
    )
    before = _overflow_columns(engine)
    again = run_pipeline(engine, policy, [_item(stored_child)])
    assert again.outcomes == {DUPLICATE: 1}
    assert _overflow_columns(engine) == before


def test_an_out_of_order_overflow_event_is_not_counted(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    policy = explicit_policy(track_max_events_per_cascade=TEST_SMALL_CASCADE_CAP)
    run = run_pipeline(engine, policy, items)
    root, count, mark = next(r for r in _overflow_columns(engine) if r[1] > 0)
    template = next(r for r, o in run.per_item if o == "accepted_repost")
    constructed_late_overflow = replace(
        template, uri_key="constructedlateoverx", parent_key=root, time_us=mark - 1
    )
    constructed_new_overflow = replace(
        template, uri_key="constructednewoverxx", parent_key=root, time_us=mark + 1
    )
    late = run_pipeline(engine, policy, [_item(constructed_late_overflow)])
    assert late.outcomes == {OVERFLOW_UNCOUNTED: 1}
    assert next(r for r in _overflow_columns(engine) if r[0] == root) == (root, count, mark)
    new = run_pipeline(engine, policy, [_item(constructed_new_overflow)])
    assert new.outcomes == {OVERFLOW: 1}
    assert next(r for r in _overflow_columns(engine) if r[0] == root) == (root, count + 1, mark + 1)


# --- atomicity: deterministic failure injection (D-09, T-03-37)
_TRIGGER_FUNCTION = (
    "CREATE OR REPLACE FUNCTION tt_test_fail() RETURNS trigger LANGUAGE plpgsql AS $$"
    " BEGIN IF TG_NARGS = 0 OR NEW.uri = TG_ARGV[0] THEN"
    " RAISE EXCEPTION 'injected test failure'; END IF; RETURN NEW; END $$"
)


def _failing_batch(engine: Any, policy: Any, items: list[SourceItem]) -> tuple[Batch, str]:
    """Commit the first half, then build (but do not flush) a batch over the second half plus a
    tombstone of an already stored row; the batch holds every kind of write."""
    half = len(items) // 2
    run_pipeline(engine, policy, items[:half])
    stored = _scalar(engine, "SELECT uri FROM events WHERE deleted_at IS NULL ORDER BY uri LIMIT 1")
    index = TrackedIndex()
    with engine.connect() as connection:
        index.load(connection, None)
    decider = Decider(policy, index, selection.load_allowlist(policy.track_allowlist_file))
    batch = Batch()
    for item in items[half:]:
        batch.note_cursor(item.cursor_us)
        decider.process(item.result, batch)
    batch.tombstones[stored] = batch.events[0].observed_at
    assert batch.cascades
    assert batch.claims
    assert batch.overflow
    assert batch.accounts
    assert {p.edge_kind for p in batch.events} >= {"root", "reply", "repost"}
    return batch, stored


@pytest.mark.parametrize("target", ["events_insert", "checkpoint_upsert"])
def test_a_failing_batch_persists_nothing_and_then_flushes_completely(
    engine: Any, explicit_policy: Any, items: list[SourceItem], target: str
) -> None:
    from sqlalchemy.exc import DBAPIError

    policy = explicit_policy(track_max_events_per_cascade=TEST_SMALL_CASCADE_CAP)
    batch, stored = _failing_batch(engine, policy, items)
    before = canonical_projection(engine)
    counts = row_counts(engine)
    victim = batch.events[-1].uri
    assert victim.isalnum()  # a keyed token, safe as a trigger argument
    if target == "events_insert":
        trigger = (
            "CREATE TRIGGER tt_test_fail BEFORE INSERT ON events FOR EACH ROW"
            f" EXECUTE FUNCTION tt_test_fail('{victim}')"
        )
        table = "events"
    else:
        trigger = (
            "CREATE TRIGGER tt_test_fail BEFORE INSERT OR UPDATE ON ingest_checkpoints"
            " FOR EACH ROW EXECUTE FUNCTION tt_test_fail()"
        )
        table = "ingest_checkpoints"
    with engine.begin() as connection:
        connection.execute(text(_TRIGGER_FUNCTION))
        connection.execute(text(trigger))
    try:
        with pytest.raises(DBAPIError):
            flush(engine, batch, source=SOURCE, dialect="v2", host="recorded")
        assert row_counts(engine) == counts
        assert canonical_projection(engine) == before
        assert _scalar(engine, "SELECT deleted_at FROM events WHERE uri = :u", u=stored) is None
    finally:
        with engine.begin() as connection:
            connection.execute(text(f"DROP TRIGGER IF EXISTS tt_test_fail ON {table}"))
            connection.execute(text("DROP FUNCTION IF EXISTS tt_test_fail()"))
    result = flush(engine, batch, source=SOURCE, dialect="v2", host="recorded")
    assert result.inserted > 0
    assert result.overflow_counted > 0
    assert row_counts(engine)["events"] == counts["events"] + result.inserted
    assert _scalar(engine, "SELECT deleted_at FROM events WHERE uri = :u", u=stored) is not None
    cursor = _scalar(engine, "SELECT cursor_time_us FROM ingest_checkpoints")
    assert cursor == batch.max_time_us


def test_control_a_non_atomic_writer_would_leave_partial_rows_visible(
    engine: Any, explicit_policy: Any, items: list[SourceItem]
) -> None:
    """The observation method can see partial writes: rows committed on their own, then a
    failing checkpoint, leave the rows behind (a writer built that way could not pass)."""
    from sqlalchemy.exc import DBAPIError

    policy = explicit_policy(track_max_events_per_cascade=TEST_SMALL_CASCADE_CAP)
    rows_only, _stored = _failing_batch(engine, policy, items)
    counts = row_counts(engine)
    cursor = rows_only.max_time_us
    rows_only.max_time_us = None  # this helper writes its rows without the checkpoint
    with engine.begin() as connection:
        connection.execute(text(_TRIGGER_FUNCTION))
        connection.execute(
            text(
                "CREATE TRIGGER tt_test_fail BEFORE INSERT OR UPDATE ON ingest_checkpoints"
                " FOR EACH ROW EXECUTE FUNCTION tt_test_fail()"
            )
        )
    try:
        flush(engine, rows_only, source=SOURCE, dialect="v2", host="recorded")  # commit 1
        failing = Batch()
        failing.note_cursor(cursor)
        with pytest.raises(DBAPIError):
            flush(engine, failing, source=SOURCE, dialect="v2", host="recorded")  # commit 2
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP TRIGGER IF EXISTS tt_test_fail ON ingest_checkpoints"))
            connection.execute(text("DROP FUNCTION IF EXISTS tt_test_fail()"))
    assert row_counts(engine)["events"] > counts["events"]


# --- advisory locks ------------------------------------------------------------------------------
def test_advisory_lock_is_single_flight_and_released(engine: Any) -> None:
    from truthtrail.db.locks import (
        INGEST_LOCK_KEY,
        LOCK_KEYS,
        release_advisory_lock,
        try_advisory_lock,
    )

    assert len(set(LOCK_KEYS.values())) == len(LOCK_KEYS) == 4
    with engine.connect() as first, engine.connect() as second:
        assert try_advisory_lock(first, INGEST_LOCK_KEY) is True
        assert try_advisory_lock(second, INGEST_LOCK_KEY) is False
        assert release_advisory_lock(first, INGEST_LOCK_KEY) is True
        assert try_advisory_lock(second, INGEST_LOCK_KEY) is True
        assert release_advisory_lock(second, INGEST_LOCK_KEY) is True
