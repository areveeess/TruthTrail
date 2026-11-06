"""The normaliser: keyed identifiers, D-12 edges and the personal-data boundary (D-12, D-17, D-18).

Inputs are REAL recorded frames picked by predicate from the fixture. A shape the recording lacks
(its manifest ``coverage`` count is 0, or the shape has no coverage key and a scan of the fixture
finds none) is built from the nearest real frame and named ``constructed_{shape}``; each such test
first asserts that the fixture really lacks the shape, so the path taken is explicit and never a
silent skip. The scrubbed fixture carries no link-card title and no post text (D-04), so title and
text capture are tested on frames constructed from a real root frame (``constructed_card_title``,
``constructed_root_text``); those inserted values are never presented as recorded.

Expected keys are computed independently in the test from the raw frame with ``keyer.uri_key`` of
the referenced ``at://`` URI (D-15: stored ``uri`` and ``parent_uri`` values are those keyed forms).
"""

import ast
import copy
import dataclasses
import json
import re
import secrets
import socket
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from conftest import fixture_manifest, recorded_frames, recorded_lines
from hypothesis import given
from hypothesis import strategies as st

import truthtrail.ingest
from truthtrail.ingest import selection as sel
from truthtrail.ingest.dialect import (
    BadFrame,
    ErrorFrame,
    InfoFrame,
    classify_frame,
    datetime_from_us,
    parse_stream_time,
)
from truthtrail.ingest.normalise import (
    AccountAction,
    DeleteEvent,
    Dropped,
    LinkCandidate,
    NormalizedEvent,
    normalise,
    occurred_at_from,
)
from truthtrail.ingest.pseudonym import Keyer, make_keyer

POST = "app.bsky.feed.post"
REPOST = "app.bsky.feed.repost"
COMMIT_TYPE = "network.bsky.jetstream.subscribeEvents#commit"
RESULT_TYPES = (NormalizedEvent, DeleteEvent, AccountAction, Dropped, InfoFrame, ErrorFrame)
HANDLE_RX = re.compile(r"@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
INGEST_DIR = Path(truthtrail.ingest.__file__).resolve().parent
# Hypothesis cannot use the function-scoped keyer fixture; this one is keyed at runtime too.
FUZZ_KEYER = make_keyer(secrets.token_bytes(32))

# Golden histogram of result types over the whole fixture, derived from the first verified run
# and explained by the manifest's counts_by_kind: 605 post creates + 525 repost creates = 1130
# NormalizedEvent; 15 post deletes + 10 repost deletes = 25 DeleteEvent; of the 22 account events
# 5 deleted + 5 takendown become AccountAction and 5 active + 5 deactivated + 2 throttled are
# Dropped (12); the 3 sync events are AccountAction too (13 in total). No frame is a bad frame.
GOLDEN_TYPES = {"NormalizedEvent": 1130, "DeleteEvent": 25, "AccountAction": 13, "Dropped": 12}
GOLDEN_DETAIL = {
    "NormalizedEvent:root-candidate": 252,
    "NormalizedEvent:reply": 313,
    "NormalizedEvent:quote": 40,
    "NormalizedEvent:repost": 525,
    "DeleteEvent:app.bsky.feed.post": 15,
    "DeleteEvent:app.bsky.feed.repost": 10,
    "AccountAction:account_deleted": 5,
    "AccountAction:account_takedown": 5,
    "AccountAction:sync": 3,
    "Dropped:account_status_ignored": 12,
}


def payload(frame: dict[str, Any]) -> dict[str, Any]:
    return frame.get("payload", {})


def suffix(frame: dict[str, Any]) -> str:
    return str(payload(frame).get("$type", "")).rsplit("#", 1)[-1]


def is_create(frame: dict[str, Any], collection: str) -> bool:
    p = payload(frame)
    return (
        suffix(frame) == "commit"
        and p.get("collection") == collection
        and p.get("operation") == "create"
    )


def embed_of(frame: dict[str, Any]) -> dict[str, Any]:
    return payload(frame).get("record", {}).get("embed") or {}


def find(predicate: Any) -> dict[str, Any] | None:
    return next((f for f in recorded_frames() if predicate(f)), None)


def first(predicate: Any) -> dict[str, Any]:
    frame = find(predicate)
    assert frame is not None, "the fixture holds no frame of this shape"
    return frame


def run(frame: dict[str, Any], keyer: Keyer) -> Any:
    return normalise(classify_frame(json.dumps(frame), "v2"), keyer)


def raw_uri(frame: dict[str, Any]) -> str:
    p = payload(frame)
    return f"at://{p['did']}/{p['collection']}/{p['rkey']}"


def stream_us(frame: dict[str, Any]) -> int:
    return parse_stream_time(payload(frame)["witnessedAt"])


def is_root_with_link(frame: dict[str, Any]) -> bool:
    record = payload(frame).get("record", {})
    return (
        is_create(frame, POST)
        and "reply" not in record
        and embed_of(frame).get("$type") not in (sel.EMBED_RECORD, sel.EMBED_RECORD_WITH_MEDIA)
        and bool(sel.link_urls(record))
    )


def quote_target(frame: dict[str, Any]) -> str | None:
    embed = embed_of(frame)
    if embed.get("$type") == sel.EMBED_RECORD:
        return (embed.get("record") or {}).get("uri")
    if embed.get("$type") == sel.EMBED_RECORD_WITH_MEDIA:
        return ((embed.get("record") or {}).get("record") or {}).get("uri")
    return None


# ----------------------------------------------------------------------------- real shapes


def test_root_candidate_with_a_card_link(keyer: Keyer) -> None:
    frame = first(lambda f: is_root_with_link(f) and embed_of(f).get("$type") == sel.EMBED_EXTERNAL)
    event = run(frame, keyer)
    assert isinstance(event, NormalizedEvent)
    assert (event.kind, event.edge_kind) == ("post", "root-candidate")
    assert event.uri_key == keyer.uri_key(raw_uri(frame))
    assert event.account_key == keyer.account_key(payload(frame)["did"])
    assert event.parent_key is None
    assert event.reply_root_key is None
    assert event.links
    assert event.links[0].source == "card"
    for link in event.links:
        assert link.url == sel.canonicalise_url(link.url)
        assert "?" not in link.url
        assert "#" not in link.url
        assert link.host == sel.url_host(link.url)
    # The scrubber drops titles and text (D-04): nothing to capture on a real fixture frame.
    assert event.card_title is None
    assert event.text is None
    assert event.sample_bucket == sel.sample_bucket(raw_uri(frame))
    assert event.langs == tuple(payload(frame)["record"].get("langs", []))


def test_root_candidate_with_a_facet_link(keyer: Keyer) -> None:
    frame = first(lambda f: is_root_with_link(f) and "embed" not in payload(f)["record"])
    event = run(frame, keyer)
    assert isinstance(event, NormalizedEvent)
    assert event.edge_kind == "root-candidate"
    assert {link.source for link in event.links} == {"facet"}


def test_reply(keyer: Keyer) -> None:
    frame = first(
        lambda f: is_create(f, POST) and "reply" in payload(f)["record"] and not quote_target(f)
    )
    reply = payload(frame)["record"]["reply"]
    event = run(frame, keyer)
    assert isinstance(event, NormalizedEvent)
    assert (event.kind, event.edge_kind) == ("post", "reply")
    assert event.parent_key == keyer.uri_key(reply["parent"]["uri"])
    assert event.reply_root_key == keyer.uri_key(reply["root"]["uri"])
    assert event.quoted_key is None
    assert event.text is None
    assert event.links == ()
    assert event.card_title is None
    assert event.sample_bucket is None
    assert event.langs == ()


def test_quote_of_a_record(keyer: Keyer) -> None:
    frame = first(
        lambda f: (
            is_create(f, POST)
            and embed_of(f).get("$type") == sel.EMBED_RECORD
            and "reply" not in payload(f)["record"]
        )
    )
    event = run(frame, keyer)
    assert isinstance(event, NormalizedEvent)
    assert (event.kind, event.edge_kind) == ("post", "quote")
    assert event.parent_key == keyer.uri_key(quote_target(frame))
    assert event.quoted_key is None
    assert event.reply_root_key is None
    assert event.text is None
    assert event.links == ()


def test_quote_with_media(keyer: Keyer) -> None:
    frame = first(
        lambda f: (
            is_create(f, POST)
            and embed_of(f).get("$type") == sel.EMBED_RECORD_WITH_MEDIA
            and "reply" not in payload(f)["record"]
        )
    )
    event = run(frame, keyer)
    assert isinstance(event, NormalizedEvent)
    assert event.edge_kind == "quote"
    assert event.parent_key == keyer.uri_key(quote_target(frame))


def test_a_reply_that_also_quotes_is_a_reply_with_a_secondary_quoted_key(keyer: Keyer) -> None:
    frame = first(
        lambda f: is_create(f, POST) and "reply" in payload(f)["record"] and quote_target(f)
    )
    event = run(frame, keyer)
    assert isinstance(event, NormalizedEvent)
    assert event.edge_kind == "reply"
    assert event.parent_key == keyer.uri_key(payload(frame)["record"]["reply"]["parent"]["uri"])
    assert event.quoted_key == keyer.uri_key(quote_target(frame))


def test_repost(keyer: Keyer) -> None:
    frame = first(lambda f: is_create(f, REPOST) and "via" not in payload(f)["record"])
    event = run(frame, keyer)
    assert isinstance(event, NormalizedEvent)
    assert (event.kind, event.edge_kind) == ("repost", "repost")
    assert event.parent_key == keyer.uri_key(payload(frame)["record"]["subject"]["uri"])
    assert event.via_key is None
    assert event.reply_root_key is None
    assert event.quoted_key is None
    assert event.text is None
    assert event.links == ()


def test_repost_with_via(keyer: Keyer) -> None:
    frame = first(lambda f: is_create(f, REPOST) and "via" in payload(f)["record"])
    record = payload(frame)["record"]
    event = run(frame, keyer)
    assert isinstance(event, NormalizedEvent)
    assert event.edge_kind == "repost"
    assert event.parent_key == keyer.uri_key(record["subject"]["uri"])
    assert event.via_key == keyer.uri_key(record["via"]["uri"])


def test_an_unknown_embed_type_is_a_root_candidate_without_quote_or_card(keyer: Keyer) -> None:
    frame = first(
        lambda f: is_create(f, POST) and embed_of(f).get("$type") == "app.bsky.embed.gallery"
    )
    event = run(frame, keyer)
    assert isinstance(event, NormalizedEvent)
    assert event.edge_kind in ("root-candidate", "reply")
    assert event.edge_kind == ("reply" if "reply" in payload(frame)["record"] else "root-candidate")
    assert event.quoted_key is None
    assert all(link.source != "card" for link in event.links)


@pytest.mark.parametrize("collection", [POST, REPOST])
def test_delete(keyer: Keyer, collection: str) -> None:
    frame = first(
        lambda f: (
            suffix(f) == "commit"
            and payload(f)["collection"] == collection
            and payload(f)["operation"] == "delete"
        )
    )
    assert fixture_manifest()["coverage"]["deletes"]["post" if collection == POST else "repost"] > 0
    event = run(frame, keyer)
    assert event == DeleteEvent(keyer.uri_key(raw_uri(frame)), collection, stream_us(frame))


def test_account_statuses(keyer: Keyer) -> None:
    statuses = fixture_manifest()["coverage"]["account_events_by_status"]
    for status in statuses:
        frame = first(
            lambda f, s=status: suffix(f) == "account" and payload(f)["account"]["status"] == s
        )
        result = run(frame, keyer)
        did = payload(frame)["did"]
        if status == "deleted":
            assert result == AccountAction(
                "account_deleted", keyer.account_key(did), stream_us(frame)
            )
        elif status == "takendown":
            assert result == AccountAction(
                "account_takedown", keyer.account_key(did), stream_us(frame)
            )
        else:
            assert result == Dropped("account_status_ignored"), status
    assert {"deleted", "takendown"} <= set(statuses)


def test_constructed_account_statuses_the_fixture_lacks(keyer: Keyer) -> None:
    present = set(fixture_manifest()["coverage"]["account_events_by_status"])
    base = first(lambda f: suffix(f) == "account")
    for status in ("suspended", "desynchronized", "a-future-status", None):
        assert status not in present
        constructed_account = copy.deepcopy(base)
        if status is None:
            payload(constructed_account)["account"].pop("status", None)
        else:
            payload(constructed_account)["account"]["status"] = status
        assert run(constructed_account, keyer) == Dropped("account_status_ignored")


def test_sync(keyer: Keyer) -> None:
    assert fixture_manifest()["coverage"]["sync_events"] > 0
    frame = first(lambda f: suffix(f) == "sync")
    assert run(frame, keyer) == AccountAction(
        "sync", keyer.account_key(payload(frame)["did"]), stream_us(frame)
    )


# ----------------------------------------------------------------------------- constructed shapes


def test_constructed_update_is_ignored(keyer: Keyer) -> None:
    assert find(lambda f: payload(f).get("operation") == "update") is None
    constructed_update = copy.deepcopy(first(lambda f: is_create(f, POST)))
    payload(constructed_update)["operation"] = "update"
    assert run(constructed_update, keyer) == Dropped("update_ignored")


def test_constructed_quote_of_a_non_post_target_is_a_root_candidate(keyer: Keyer) -> None:
    """D-12 through derive_edge (F-08): a quote counts only when it targets a post, so a post that
    embeds a feed generator is a top-level root candidate (RESEARCH Code Examples), not an edge."""
    non_post = [f for f in recorded_frames() if (q := quote_target(f)) and f"/{POST}/" not in q]
    assert non_post == []
    constructed_quote_of_generator = copy.deepcopy(
        first(
            lambda f: (
                is_create(f, POST)
                and embed_of(f).get("$type") == sel.EMBED_RECORD
                and "reply" not in payload(f)["record"]
            )
        )
    )
    target = payload(constructed_quote_of_generator)["record"]["embed"]["record"]
    target["uri"] = target["uri"].replace(POST, "app.bsky.feed.generator")
    event = run(constructed_quote_of_generator, keyer)
    assert isinstance(event, NormalizedEvent)
    assert event.edge_kind == "root-candidate"
    assert event.parent_key is None
    assert event.quoted_key is None


def test_constructed_repost_of_a_non_post_target_is_a_bad_edge(keyer: Keyer) -> None:
    subjects = [
        payload(f)["record"]["subject"]["uri"] for f in recorded_frames() if is_create(f, REPOST)
    ]
    assert all(f"/{POST}/" in s for s in subjects)
    constructed_repost_of_document = copy.deepcopy(first(lambda f: is_create(f, REPOST)))
    subject = payload(constructed_repost_of_document)["record"]["subject"]
    subject["uri"] = subject["uri"].replace(POST, "site.standard.document")
    assert run(constructed_repost_of_document, keyer) == Dropped("bad_edge")


def test_constructed_reply_with_both_references_unusable_is_a_bad_edge(keyer: Keyer) -> None:
    constructed_reply_unusable = copy.deepcopy(
        first(lambda f: is_create(f, POST) and "reply" in payload(f)["record"])
    )
    reply = payload(constructed_reply_unusable)["record"]["reply"]
    reply["parent"]["uri"] = "not-a-uri"
    reply["root"]["uri"] = reply["root"]["uri"].replace(POST, "app.bsky.feed.generator")
    assert run(constructed_reply_unusable, keyer) == Dropped("bad_edge")


def test_constructed_reply_with_only_a_usable_root(keyer: Keyer) -> None:
    constructed_reply_root_only = copy.deepcopy(
        first(lambda f: is_create(f, POST) and "reply" in payload(f)["record"])
    )
    reply = payload(constructed_reply_root_only)["record"]["reply"]
    reply["parent"]["uri"] = "junk"
    event = run(constructed_reply_root_only, keyer)
    assert isinstance(event, NormalizedEvent)
    assert event.parent_key is None
    assert event.reply_root_key == keyer.uri_key(reply["root"]["uri"])


def test_constructed_did_web_subject_is_accepted(keyer: Keyer) -> None:
    constructed_did_web = copy.deepcopy(first(lambda f: is_create(f, REPOST)))
    web_uri = f"at://did:web:example.invalid/{POST}/2222222222222"
    payload(constructed_did_web)["record"]["subject"]["uri"] = web_uri
    event = run(constructed_did_web, keyer)
    assert isinstance(event, NormalizedEvent)
    assert event.parent_key == keyer.uri_key(web_uri)


def test_constructed_malformed_via_is_not_keyed(keyer: Keyer) -> None:
    constructed_bad_via = copy.deepcopy(
        first(lambda f: is_create(f, REPOST) and "via" in payload(f)["record"])
    )
    payload(constructed_bad_via)["record"]["via"]["uri"] = "junk"
    event = run(constructed_bad_via, keyer)
    assert isinstance(event, NormalizedEvent)
    assert event.via_key is None


def test_constructed_unwanted_collection(keyer: Keyer) -> None:
    constructed_like = copy.deepcopy(first(lambda f: is_create(f, REPOST)))
    payload(constructed_like)["collection"] = "app.bsky.feed.like"
    assert run(constructed_like, keyer) == Dropped("unwanted_collection")


def test_control_identity_and_bad_frames(keyer: Keyer) -> None:
    info = InfoFrame("OutdatedCursor")
    error = ErrorFrame("ConsumerTooSlow")
    assert normalise(info, keyer) is info
    assert normalise(error, keyer) is error
    base = first(lambda f: suffix(f) == "sync")
    constructed_identity = copy.deepcopy(base)
    payload(constructed_identity)["$type"] = payload(base)["$type"].replace("#sync", "#identity")
    assert run(constructed_identity, keyer) == Dropped("identity_ignored")
    assert normalise(classify_frame("not json", "v2"), keyer) == Dropped("bad_frame:not_json")
    assert normalise(BadFrame("too_large"), keyer) == Dropped("bad_frame:too_large")


def test_constructed_card_title_and_root_text_are_captured_only_for_a_root(keyer: Keyer) -> None:
    real_root = first(
        lambda f: is_root_with_link(f) and embed_of(f).get("$type") == sel.EMBED_EXTERNAL
    )
    constructed_card_title = copy.deepcopy(real_root)
    payload(constructed_card_title)["record"]["embed"]["external"]["title"] = "Publisher headline"
    event = run(constructed_card_title, keyer)
    assert isinstance(event, NormalizedEvent)
    assert event.card_title == "Publisher headline"

    constructed_root_text = copy.deepcopy(real_root)
    marker = "CONSTRUCTED-ROOT-TEXT-MARKER"
    payload(constructed_root_text)["record"]["text"] = marker
    event = run(constructed_root_text, keyer)
    assert isinstance(event, NormalizedEvent)
    assert event.text == marker
    assert marker not in repr(event)
    assert marker not in str(event)

    blank_title = copy.deepcopy(constructed_card_title)
    payload(blank_title)["record"]["embed"]["external"]["title"] = "   "
    assert run(blank_title, keyer).card_title is None

    for predicate in (
        lambda f: is_create(f, POST) and "reply" in payload(f)["record"],
        lambda f: (
            is_create(f, POST)
            and embed_of(f).get("$type") == sel.EMBED_RECORD
            and "reply" not in payload(f)["record"]
        ),
        lambda f: is_create(f, REPOST),
    ):
        constructed_child_text = copy.deepcopy(first(predicate))
        payload(constructed_child_text)["record"]["text"] = marker
        child = run(constructed_child_text, keyer)
        assert isinstance(child, NormalizedEvent)
        assert child.edge_kind != "root-candidate"
        assert child.text is None
        assert child.card_title is None


def test_constructed_record_with_media_card_title(keyer: Keyer) -> None:
    constructed_media_card = copy.deepcopy(first(is_root_with_link))
    record = payload(constructed_media_card)["record"]
    record["embed"] = {
        "$type": sel.EMBED_RECORD_WITH_MEDIA,
        "media": {
            "$type": sel.EMBED_EXTERNAL,
            "external": {"uri": "https://apnews.com/x", "title": "T"},
        },
        "record": {"record": {"uri": "not-a-post"}},
    }
    event = run(constructed_media_card, keyer)
    assert isinstance(event, NormalizedEvent)
    assert event.edge_kind == "root-candidate"
    assert event.card_title == "T"
    assert LinkCandidate("card", "https://apnews.com/x", "apnews.com") in event.links


# ----------------------------------------------------------------------------- time


def test_observed_at_is_the_stream_time_with_microseconds(keyer: Keyer) -> None:
    for frame in list(recorded_frames())[:200]:
        result = run(frame, keyer)
        if isinstance(result, NormalizedEvent):
            assert result.time_us == stream_us(frame)
            assert result.observed_at == datetime_from_us(stream_us(frame))
            assert result.observed_at.tzinfo is UTC
            assert result.observed_at.microsecond == stream_us(frame) % 1_000_000
            assert result.seq == payload(frame)["seq"]


OBSERVED = datetime(2026, 10, 19, 7, 42, 1, 798854, tzinfo=UTC)


@pytest.mark.parametrize(
    ("created_at", "valid"),
    [
        ("2026-10-19T07:42:01.000Z", True),
        ("2026-10-19T09:42:01+02:00", True),
        ("1970-01-01T00:00:00Z", True),
        ((OBSERVED + timedelta(days=366) - timedelta(seconds=1)).isoformat(), True),
        ((OBSERVED + timedelta(days=366)).isoformat(), True),
        ((OBSERVED + timedelta(days=366) + timedelta(seconds=1)).isoformat(), False),
        ("1969-12-31T23:59:59Z", False),
        ("0001-01-01T00:00:00+14:00", False),
        ("2026-10-19T07:42:01", False),
        ("2026-10-19", False),
        ("yesterday", False),
        ("", False),
        (1792395721, False),
        (None, False),
    ],
    ids=[
        "normal",
        "offset",
        "floor",
        "one-second-inside-upper",
        "at-upper",
        "one-second-beyond-upper",
        "before-1970",
        "offset-before-year-one",
        "naive",
        "date-only",
        "unparseable",
        "empty",
        "number",
        "missing",
    ],
)
def test_created_at_bounds(created_at: object, valid: bool) -> None:
    value = occurred_at_from(created_at, OBSERVED)
    assert (value is not None) is valid
    if value is not None:
        assert value.tzinfo is UTC


def test_occurred_at_flows_into_the_event_and_is_counted_when_invalid(keyer: Keyer) -> None:
    frame = first(lambda f: is_create(f, REPOST))
    good = run(frame, keyer)
    assert good.occurred_at == datetime.fromisoformat(payload(frame)["record"]["createdAt"])
    assert good.occurred_at_invalid is False
    constructed_bad_created_at = copy.deepcopy(frame)
    payload(constructed_bad_created_at)["record"]["createdAt"] = "1900-01-01T00:00:00Z"
    bad = run(constructed_bad_created_at, keyer)
    assert bad.occurred_at is None
    assert bad.occurred_at_invalid is True


# ----------------------------------------------------------------------------- whole fixture


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        out: list[str] = []
        for item in dataclasses.fields(value):
            out.extend(_strings(getattr(value, item.name)))
        return out
    if isinstance(value, tuple | list | frozenset | set):
        return [s for item in value for s in _strings(item)]
    return []


def test_no_result_holds_a_raw_identifier(keyer: Keyer) -> None:
    raw_dids: set[str] = set()
    raw_rkeys: set[str] = set()
    raw_uris: set[str] = set()
    results = []
    for frame in recorded_frames():
        p = payload(frame)
        if "did" in p:
            raw_dids.add(p["did"])
        if "rkey" in p:
            raw_rkeys.add(p["rkey"])
            raw_uris.add(raw_uri(frame))
        results.append(run(frame, keyer))
    assert raw_dids
    assert raw_rkeys
    for result in results:
        for text in [*_strings(result), repr(result)]:
            assert "did:" not in text
            assert "at://" not in text
            assert HANDLE_RX.search(text) is None
            assert not any(token in text for token in raw_rkeys)
            assert not any(token in text for token in raw_dids)


def test_the_whole_fixture_normalises_to_the_golden_histogram(keyer: Keyer) -> None:
    by_type: Counter[str] = Counter()
    detail: Counter[str] = Counter()
    for line in recorded_lines():
        result = normalise(classify_frame(line, "v2"), keyer)
        name = type(result).__name__
        by_type[name] += 1
        if isinstance(result, NormalizedEvent):
            detail[f"{name}:{result.edge_kind}"] += 1
        elif isinstance(result, DeleteEvent):
            detail[f"{name}:{result.collection}"] += 1
        elif isinstance(result, AccountAction):
            detail[f"{name}:{result.action}"] += 1
        elif isinstance(result, Dropped):
            detail[f"{name}:{result.reason}"] += 1
    assert dict(by_type) == GOLDEN_TYPES
    assert dict(detail) == GOLDEN_DETAIL
    counts = fixture_manifest()["counts_by_kind"]
    assert by_type["NormalizedEvent"] == counts["post_create"] + counts["repost_create"]
    assert by_type["DeleteEvent"] == counts["post_delete"] + counts["repost_delete"]
    assert by_type["AccountAction"] + by_type["Dropped"] == counts["account"] + counts["sync"]


@pytest.fixture(scope="module")
def commit_envelope() -> dict[str, Any]:
    return next(f for f in recorded_frames() if is_create(f, POST))


RECORD_VALUES = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(max_size=30),
    lambda children: (
        st.lists(children, max_size=3)
        | st.dictionaries(
            st.sampled_from(
                [
                    "$type",
                    "uri",
                    "reply",
                    "parent",
                    "root",
                    "embed",
                    "record",
                    "media",
                    "external",
                    "title",
                    "facets",
                    "features",
                    "langs",
                    "labels",
                    "values",
                    "val",
                    "subject",
                    "via",
                    "createdAt",
                    "text",
                    "x",
                ]
            ),
            children,
            max_size=5,
        )
    ),
    max_leaves=25,
)


@given(
    record=st.dictionaries(
        st.sampled_from(
            [
                "$type",
                "reply",
                "embed",
                "facets",
                "langs",
                "labels",
                "subject",
                "via",
                "createdAt",
                "text",
            ]
        ),
        RECORD_VALUES,
        max_size=8,
    ),
    collection=st.sampled_from([POST, REPOST]),
)
def test_arbitrary_records_inside_a_valid_commit_never_raise(
    record: dict[str, Any], collection: str, commit_envelope: dict[str, Any]
) -> None:
    frame = copy.deepcopy(commit_envelope)
    payload(frame)["record"] = record
    payload(frame)["collection"] = collection
    result = normalise(classify_frame(json.dumps(frame), "v2"), FUZZ_KEYER)
    assert isinstance(result, RESULT_TYPES)


def test_nothing_is_fetched_or_resolved_while_normalising_and_selecting(
    keyer: Keyer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Links are parsed, never fetched (D-13, T-03-24): no socket call happens at all."""
    calls: list[str] = []

    def refuse(name: str) -> Any:
        def call(*args: Any, **kwargs: Any) -> Any:
            calls.append(name)
            raise AssertionError(f"{name} called during normalisation")

        return call

    monkeypatch.setattr(socket.socket, "connect", refuse("connect"))
    monkeypatch.setattr(socket, "getaddrinfo", refuse("getaddrinfo"))
    monkeypatch.setattr(socket, "create_connection", refuse("create_connection"))
    allow = frozenset(fixture_manifest()["selection_policy"]["allowlist_domains"])
    for line in recorded_lines():
        result = normalise(classify_frame(line, "v2"), keyer)
        if isinstance(result, NormalizedEvent):
            sel.seed_decision_for(result.seed_candidate(), allow)
    assert calls == []


def test_the_pure_ingest_modules_import_no_network_client() -> None:
    forbidden = {
        "socket",
        "ssl",
        "http",
        "urllib.request",
        "requests",
        "httpx",
        "websockets",
        "logging",
    }
    for name in ("dialect.py", "normalise.py", "pseudonym.py", "selection.py"):
        tree = ast.parse((INGEST_DIR / name).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        hits = {m for m in imported if m in forbidden or m.split(".")[0] in forbidden - {"urllib"}}
        assert hits == set(), (name, hits)
