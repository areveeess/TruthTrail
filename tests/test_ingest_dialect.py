"""The Jetstream dialect module (D-05, D-06; RESEARCH Pattern 1, F-02, F-03, F-04, F-18).

Contract inputs are REAL recorded frames picked by predicate from the fixture (main file and the
samples file, whose v1 rows are real v1 frames). A shape the recording lacks is built from the
nearest real shape and named ``constructed_*``; the test says which path it took. Every connect
URL is built, never opened: the socket guard is active for the whole module.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import pytest
from conftest import fixture_manifest, recorded_frames, recorded_lines, sample_rows
from hypothesis import given
from hypothesis import strategies as st

from truthtrail.ingest import dialect
from truthtrail.ingest.dialect import (
    AccountFrame,
    BadFrame,
    CommitFrame,
    ErrorFrame,
    IgnoredFrame,
    InfoFrame,
    SyncFrame,
    build_connect_url,
    classify_frame,
    datetime_from_us,
    parse_stream_time,
    resume_cursor,
    subprotocols,
)

CURSOR_FIELDS = {"cursor", "cursor_us", "time_us", "seq"}


def payload(frame: dict[str, Any]) -> dict[str, Any]:
    return frame.get("payload", {})


def suffix(frame: dict[str, Any]) -> str:
    return str(payload(frame).get("$type", "")).rsplit("#", 1)[-1]


def commit(frame: dict[str, Any], collection: str, operation: str) -> bool:
    p = payload(frame)
    return suffix(frame) == "commit" and (p.get("collection"), p.get("operation")) == (
        collection,
        operation,
    )


def first(predicate: Any) -> dict[str, Any]:
    return next(f for f in recorded_frames() if predicate(f))


def text_of(frame: dict[str, Any]) -> str:
    return json.dumps(frame, separators=(",", ":"))


# ----------------------------------------------------------------------------- connect URL


def test_v2_url_without_cursor_has_exactly_the_documented_parameters() -> None:
    url = build_connect_url("jetstream.us-east.bsky.network", "v2")
    parts = urlsplit(url)
    assert (parts.scheme, parts.hostname, parts.path) == (
        "wss",
        "jetstream.us-east.bsky.network",
        "/xrpc/network.bsky.jetstream.subscribeEvents",
    )
    assert parse_qsl(parts.query) == [
        ("kinds", "commit"),
        ("kinds", "account"),
        ("kinds", "sync"),
        ("collections", "app.bsky.feed.post"),
        ("collections", "app.bsky.feed.repost"),
        ("maxMessageSizeBytes", "1048576"),
    ]


def test_v2_url_with_cursor_appends_the_microsecond_cursor() -> None:
    url = build_connect_url("jetstream.us-west.bsky.network", "v2", cursor_us=1792395721798854)
    assert url.endswith("&maxMessageSizeBytes=1048576&cursor=1792395721798854")
    assert "*" not in url
    assert "like" not in url


def test_v1_url_uses_the_legacy_parameter_names() -> None:
    url = build_connect_url("jetstream2.us-east.bsky.network", "v1", cursor_us=5)
    parts = urlsplit(url)
    assert parts.path == "/subscribe"
    assert parse_qsl(parts.query) == [
        ("wantedCollections", "app.bsky.feed.post"),
        ("wantedCollections", "app.bsky.feed.repost"),
        ("maxMessageSizeBytes", "1048576"),
        ("cursor", "5"),
    ]
    assert "kinds" not in parts.query


def test_cursor_zero_is_kept_and_the_ws_scheme_is_allowed_for_loopback_tests() -> None:
    assert build_connect_url("localhost", "v2", cursor_us=0, scheme="ws").startswith(
        "ws://localhost/xrpc/"
    )
    assert build_connect_url("localhost", "v2", cursor_us=0).endswith("&cursor=0")


@pytest.mark.parametrize(
    "host",
    [
        "wss://jetstream.us-east.bsky.network",
        "jetstream.us-east.bsky.network/xrpc",
        "jetstream.us-east.bsky.network:443",
        "user@jetstream.us-east.bsky.network",
        "user:pw@jetstream.us-east.bsky.network",
        "jetstream .us-east.bsky.network",
        " jetstream.us-east.bsky.network",
        "jetstream.us-east.bsky.network\n",
        "",
        "-bad.example",
        "a..b",
        "host?x=1",
    ],
)
def test_host_must_be_a_bare_hostname(host: str) -> None:
    with pytest.raises(ValueError, match="bare hostname") as info:
        build_connect_url(host, "v2")
    assert host.strip() == "" or host.strip() not in str(info.value)


def test_bad_scheme_cursor_and_dialect_are_rejected() -> None:
    with pytest.raises(ValueError, match="scheme"):
        build_connect_url("localhost", "v2", scheme="https")
    with pytest.raises(ValueError, match="cursor"):
        build_connect_url("localhost", "v2", cursor_us=-1)
    with pytest.raises(ValueError, match="cursor"):
        build_connect_url("localhost", "v2", cursor_us=True)
    with pytest.raises(ValueError, match="dialect"):
        build_connect_url("localhost", "v3")  # type: ignore[arg-type]


def test_subprotocols_per_dialect() -> None:
    assert subprotocols("v2") == ("xrpc.v1.json",)
    assert subprotocols("v1") == ()
    with pytest.raises(ValueError, match="dialect"):
        subprotocols("v3")  # type: ignore[arg-type]


def test_collections_and_kinds_are_explicit_constants() -> None:
    assert dialect.COLLECTIONS == ("app.bsky.feed.post", "app.bsky.feed.repost")
    assert dialect.KINDS == ("commit", "account", "sync")
    assert dialect.SERVER_MAX_MESSAGE_BYTES < dialect.MAX_FRAME_BYTES == 2 * 1024 * 1024


# ----------------------------------------------------------------------------- real v2 frames


def _assert_no_cursor(result: object) -> None:
    fields = set(getattr(result, "__slots__", ()))
    assert fields.isdisjoint(CURSOR_FIELDS), fields


@pytest.mark.parametrize(
    ("collection", "operation"),
    [
        ("app.bsky.feed.post", "create"),
        ("app.bsky.feed.repost", "create"),
        ("app.bsky.feed.post", "delete"),
        ("app.bsky.feed.repost", "delete"),
    ],
)
def test_real_commit_frames(collection: str, operation: str) -> None:
    frame = first(lambda f: commit(f, collection, operation))
    p = payload(frame)
    result = classify_frame(text_of(frame), "v2")
    assert isinstance(result, CommitFrame)
    assert (result.did, result.collection, result.rkey, result.operation) == (
        p["did"],
        collection,
        p["rkey"],
        operation,
    )
    assert result.seq == p["seq"]
    assert result.time_us == parse_stream_time(p["witnessedAt"])
    if operation == "create":
        assert result.record == p["record"]
    else:
        assert result.record is None
    assert "cid" not in p  # the scrubber drops cid; the dialect never requires it


def test_every_account_status_in_the_manifest_has_a_real_frame() -> None:
    statuses = fixture_manifest()["coverage"]["account_events_by_status"]
    assert statuses
    for status, count in statuses.items():
        assert count > 0
        frame = first(
            lambda f, s=status: suffix(f) == "account" and payload(f)["account"].get("status") == s
        )
        result = classify_frame(text_of(frame), "v2")
        assert isinstance(result, AccountFrame)
        assert result.status == status
        assert result.did == payload(frame)["did"]
        assert result.active == payload(frame)["account"]["active"]
        assert result.time_us == parse_stream_time(payload(frame)["witnessedAt"])


def test_real_sync_frame() -> None:
    assert fixture_manifest()["coverage"]["sync_events"] > 0
    frame = first(lambda f: suffix(f) == "sync")
    result = classify_frame(text_of(frame), "v2")
    assert result == SyncFrame(
        payload(frame)["did"], parse_stream_time(payload(frame)["witnessedAt"])
    )


def test_every_recorded_line_classifies_to_a_stream_result() -> None:
    kinds = {type(classify_frame(line, "v2")) for line in recorded_lines()}
    assert kinds <= {CommitFrame, AccountFrame, SyncFrame}
    assert kinds == {CommitFrame, AccountFrame, SyncFrame}


def test_raw_bytes_classify_like_text() -> None:
    line = next(recorded_lines())
    assert classify_frame(line.encode("utf-8"), "v2") == classify_frame(line, "v2")


# ----------------------------------------------------------------------------- samples file


def test_real_info_frames_from_the_samples_file_carry_no_cursor() -> None:
    infos = [
        r["frame"] for r in sample_rows() if r["dialect"] == "v2" and suffix(r["frame"]) == "info"
    ]
    assert {payload(f)["name"] for f in infos} == {"OutdatedCursor", "FutureCursor"}
    for frame in infos:
        result = classify_frame(text_of(frame), "v2")
        assert result == InfoFrame(payload(frame)["name"])
        _assert_no_cursor(result)


def test_error_frame_is_terminal_and_carries_no_cursor() -> None:
    """The recording holds no error frame, so this one is constructed from the documented
    ConsumerTooSlow shape (RESEARCH Frame shapes); the test asserts that path explicitly."""
    recorded = [r for r in sample_rows() if r["frame"].get("$type") == "error"]
    assert recorded == [], "a real error frame exists now: use it instead of the constructed one"
    constructed_error_frame = {"$type": "error", "error": "ConsumerTooSlow", "message": "slow"}
    result = classify_frame(json.dumps(constructed_error_frame), "v2")
    assert result == ErrorFrame("ConsumerTooSlow")
    _assert_no_cursor(result)
    assert classify_frame('{"$type":"error","error":5}', "v2") == BadFrame("bad_shape")


def test_real_v2_sample_frames() -> None:
    rows = [r for r in sample_rows() if r["dialect"] == "v2" and suffix(r["frame"]) == "commit"]
    assert rows
    for row in rows:
        assert isinstance(classify_frame(text_of(row["frame"]), "v2"), CommitFrame)


def test_real_v1_frames_classify_under_dialect_v1() -> None:
    rows = [r["frame"] for r in sample_rows() if r["dialect"] == "v1"]
    assert rows
    for frame in rows:
        result = classify_frame(text_of(frame), "v1")
        assert isinstance(result, CommitFrame)
        assert result.time_us == frame["time_us"]
        assert result.seq is None  # v1's cursor is per instance; only time_us is portable
        assert (result.did, result.rkey) == (frame["did"], frame["commit"]["rkey"])
        assert result.collection == frame["commit"]["collection"]
        # The same frame is not a v2 envelope.
        assert classify_frame(text_of(frame), "v2") == BadFrame("unknown_type")


def test_constructed_v1_account_identity_and_sync_frames() -> None:
    """The recording holds only v1 commits; the other v1 kinds are constructed from the real v1
    commit shape (top-level did, time_us, kind)."""
    base = next(r["frame"] for r in sample_rows() if r["dialect"] == "v1")
    shell = {"did": base["did"], "time_us": base["time_us"]}
    constructed_account = {
        **shell,
        "kind": "account",
        "account": {"active": False, "status": "deleted"},
    }
    constructed_identity = {**shell, "kind": "identity", "identity": {}}
    constructed_sync = {**shell, "kind": "sync"}
    assert classify_frame(json.dumps(constructed_account), "v1") == AccountFrame(
        base["did"], "deleted", False, base["time_us"]
    )
    assert classify_frame(json.dumps(constructed_identity), "v1") == IgnoredFrame("identity")
    assert classify_frame(json.dumps(constructed_sync), "v1") == SyncFrame(
        base["did"], base["time_us"]
    )
    for bad in (
        {**shell, "kind": 3},
        {**shell, "kind": "commit"},
        {**shell, "kind": "sync", "time_us": -1},
        {**shell, "kind": "sync", "time_us": "1"},
        {**shell, "kind": "labels"},
    ):
        assert isinstance(classify_frame(json.dumps(bad), "v1"), BadFrame)


def test_identity_and_time_fallback_on_constructed_v2_frames() -> None:
    real = first(lambda f: suffix(f) == "sync")
    p = payload(real)
    constructed_identity = {
        "$type": "message",
        "payload": {**p, "$type": "network.bsky.jetstream.subscribeEvents#identity"},
    }
    assert classify_frame(json.dumps(constructed_identity), "v2") == IgnoredFrame("identity")
    # witnessedAt absent: time is used (F-03 fallback).
    later = (datetime.fromisoformat(p["time"]) + timedelta(seconds=1)).isoformat()
    constructed_time_only = {"$type": "message", "payload": {**p, "time": later}}
    del constructed_time_only["payload"]["witnessedAt"]
    assert classify_frame(json.dumps(constructed_time_only), "v2") == SyncFrame(
        p["did"], parse_stream_time(later)
    )
    # witnessedAt wins over time when both are present.
    constructed_both = {"$type": "message", "payload": {**p, "time": later}}
    assert classify_frame(json.dumps(constructed_both), "v2") == SyncFrame(
        p["did"], parse_stream_time(p["witnessedAt"])
    )


# ----------------------------------------------------------------------------- bad frames


def _real_commit() -> dict[str, Any]:
    return first(lambda f: commit(f, "app.bsky.feed.post", "create"))


def _mutated(**changes: Any) -> str:
    frame = _real_commit()
    body = dict(payload(frame))
    for name, value in changes.items():
        if value is None:
            body.pop(name, None)
        else:
            body[name] = value
    return json.dumps({"$type": "message", "payload": body})


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("not json at all", "not_json"),
        ("", "not_json"),
        ("[1, 2, 3]", "not_object"),
        ('"a string"', "not_object"),
        ("null", "not_object"),
        ('{"$type":"message"}', "bad_shape"),
        ('{"$type":"message","payload":[]}', "bad_shape"),
        ('{"$type":"other"}', "unknown_type"),
        ('{"no_type":1}', "unknown_type"),
        (
            '{"$type":"message","payload":{"$type":"network.bsky.jetstream.subscribeEvents#label"}}',
            "unknown_type",
        ),
        ('{"$type":"message","payload":{"$type":"com.example#commit"}}', "unknown_type"),
        (
            '{"$type":"message","payload":{"$type":"network.bsky.jetstream.subscribeEvents#info"}}',
            "bad_shape",
        ),
        ("[" * 100_000 + "]" * 100_000, "not_json"),
    ],
    ids=[
        "text",
        "empty",
        "array",
        "string",
        "null",
        "no-payload",
        "payload-not-object",
        "outer-type",
        "no-type",
        "unknown-kind",
        "foreign-prefix",
        "info-without-name",
        "deep-nesting",
    ],
)
def test_bad_frames_return_a_reason_and_never_raise(text: str, reason: str) -> None:
    assert classify_frame(text, "v2") == BadFrame(reason)


@pytest.mark.parametrize(
    "changes",
    [
        {"did": None},
        {"did": "not-a-did"},
        {"did": 7},
        {"time": None, "witnessedAt": None},
        {"witnessedAt": "yesterday"},
        {"witnessedAt": "2026-10-19T07:42:01"},
        {"witnessedAt": 1792395721798854},
        {"rkey": None},
        {"rkey": "bad rkey"},
        {"collection": None},
        {"collection": "posts"},
        {"operation": "upsert"},
        {"record": None},
        {"record": "text"},
    ],
    ids=[
        "no-did",
        "bad-did",
        "did-number",
        "no-time",
        "unparseable-time",
        "naive-time",
        "numeric-time",
        "no-rkey",
        "bad-rkey",
        "no-collection",
        "bad-collection",
        "bad-operation",
        "create-without-record",
        "record-not-object",
    ],
)
def test_commit_shape_is_strict_on_the_fields_it_uses(changes: dict[str, Any]) -> None:
    assert classify_frame(_mutated(**changes), "v2") == BadFrame("bad_shape")


def test_constructed_account_and_sync_shape_errors() -> None:
    account = payload(first(lambda f: suffix(f) == "account"))
    sync = payload(first(lambda f: suffix(f) == "sync"))
    for body in (
        {**account, "account": "x"},
        {**account, "account": {**account["account"], "status": 3}},
        {**account, "account": {**account["account"], "active": "no"}},
        {**account, "did": None},
        {**sync, "did": "x"},
        {**sync, "witnessedAt": "bad"},
    ):
        assert classify_frame(json.dumps({"$type": "message", "payload": body}), "v2") == BadFrame(
            "bad_shape"
        )


def test_a_delete_with_a_record_object_is_accepted_and_a_cid_is_never_required() -> None:
    frame = first(lambda f: commit(f, "app.bsky.feed.post", "delete"))
    assert "cid" not in payload(frame)
    result = classify_frame(text_of(frame), "v2")
    assert isinstance(result, CommitFrame)


def test_oversize_by_one_byte_is_too_large() -> None:
    line = next(recorded_lines())
    size = len(line.encode("utf-8"))
    assert isinstance(classify_frame(line, "v2", max_bytes=size), CommitFrame | AccountFrame)
    assert classify_frame(line, "v2", max_bytes=size - 1) == BadFrame("too_large")
    padded = '{"pad":"' + "x" * (dialect.MAX_FRAME_BYTES) + '"}'
    assert classify_frame(padded, "v2") == BadFrame("too_large")


def test_non_text_input_is_not_json() -> None:
    assert classify_frame(None, "v2") == BadFrame("not_json")  # type: ignore[arg-type]
    assert classify_frame(b"\xff\xfe", "v2") == BadFrame("not_json")


def test_unknown_dialect_is_a_configuration_error() -> None:
    with pytest.raises(ValueError, match="dialect"):
        classify_frame("{}", "v3")  # type: ignore[arg-type]


JSON_VALUES = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text(max_size=20),
    lambda children: (
        st.lists(children, max_size=4)
        | st.dictionaries(
            st.sampled_from(
                [
                    "$type",
                    "payload",
                    "did",
                    "kind",
                    "time",
                    "time_us",
                    "witnessedAt",
                    "operation",
                    "collection",
                    "rkey",
                    "record",
                    "account",
                    "status",
                    "error",
                    "name",
                    "x",
                ]
            ),
            children,
            max_size=6,
        )
    ),
    max_leaves=20,
)


@given(JSON_VALUES, st.sampled_from(["v2", "v1"]))
def test_arbitrary_json_values_never_raise(value: object, which: str) -> None:
    result = classify_frame(json.dumps(value), which)  # type: ignore[arg-type]
    assert isinstance(
        result,
        CommitFrame | AccountFrame | SyncFrame | InfoFrame | ErrorFrame | IgnoredFrame | BadFrame,
    )


@given(st.text(), st.sampled_from(["v2", "v1"]))
def test_arbitrary_text_never_raises(text: str, which: str) -> None:
    classify_frame(text, which)  # type: ignore[arg-type]


@given(st.binary(max_size=200))
def test_arbitrary_bytes_never_raise(data: bytes) -> None:
    classify_frame(data, "v2")


# ----------------------------------------------------------------------------- time and cursor


@given(st.integers(min_value=0, max_value=4_102_444_800_000_000))
def test_microsecond_conversion_is_exact(us: int) -> None:
    moment = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=us)
    text = moment.isoformat().replace("+00:00", "Z")
    assert parse_stream_time(text) == us
    assert datetime_from_us(us) == moment
    assert datetime_from_us(us).tzinfo is UTC
    assert parse_stream_time(datetime_from_us(us).isoformat()) == us


def test_parse_stream_time_handles_offsets_and_rejects_naive() -> None:
    assert parse_stream_time("1970-01-01T01:00:00+01:00") == 0
    assert parse_stream_time("2026-10-19T07:42:01.798854Z") == 1792395721798854
    with pytest.raises(ValueError, match="time zone"):
        parse_stream_time("2026-10-19T07:42:01")
    for bad in ("nonsense", ""):
        with pytest.raises(ValueError, match="Invalid isoformat"):
            parse_stream_time(bad)
    with pytest.raises(ValueError, match="must be a string"):
        parse_stream_time(5)  # type: ignore[arg-type]


def test_resume_cursor_rewinds_and_floors_at_zero() -> None:
    assert resume_cursor(1792395721798854, 30) == 1792395721798854 - 30_000_000
    assert resume_cursor(29_999_999, 30) == 0
    assert resume_cursor(0, 30) == 0


def test_hostname_rule_accepts_real_hosts() -> None:
    for host in ("jetstream.us-east.bsky.network", "localhost", "127.0.0.1", "a" * 63 + ".example"):
        assert build_connect_url(host, "v1").startswith(f"wss://{host}/subscribe?")
