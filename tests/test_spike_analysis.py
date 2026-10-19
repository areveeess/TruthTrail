"""Tests for the pure spike libraries in scripts/spike_lib (plan 03-01, D-01 and D-04).

Every input built here is hand-made constructed data (names start with ``constructed_``); none of
it is presented as recorded. The expected numbers of the constructed log are computed by hand in
the comments of ``build_constructed_log``.
"""

import gzip
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from spike_lib import analysis, scrub  # noqa: E402
from spike_lib import selection as sel  # noqa: E402

POST = sel.POST_COLLECTION
REPOST = sel.REPOST_COLLECTION
TYPE = "network.bsky.jetstream.subscribeEvents#"
T0 = datetime(2026, 1, 1, tzinfo=UTC)
ALLOW = frozenset({"example-news.test", "wire.test"})
DID_RX = re.compile(r"^did:plc:[a-z2-7]{24}$")
TOKEN13_RX = re.compile(r"^[a-z2-7]{13}$")


def ts(sec: float) -> str:
    return (T0 + timedelta(seconds=sec)).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def uri(did: str, rkey: str, coll: str = POST) -> str:
    return f"at://did:plc:{did}/{coll}/{rkey}"


# ----------------------------------------------------------------------------- selection


def constructed_post(**kw):
    rec = {"$type": POST, "createdAt": ts(0), "text": "constructed words"}
    rec.update(kw)
    return rec


@pytest.mark.parametrize(
    ("collection", "record", "kind", "parent", "root", "quoted", "via"),
    [
        (POST, constructed_post(), "root", None, None, None, None),
        (
            POST,
            constructed_post(
                reply={"parent": {"uri": uri("a", "p")}, "root": {"uri": uri("a", "r")}}
            ),
            "reply",
            uri("a", "p"),
            uri("a", "r"),
            None,
            None,
        ),
        (
            POST,
            constructed_post(embed={"$type": sel.EMBED_RECORD, "record": {"uri": uri("b", "q")}}),
            "quote",
            uri("b", "q"),
            None,
            None,
            None,
        ),
        (
            POST,
            constructed_post(
                embed={
                    "$type": sel.EMBED_RECORD_WITH_MEDIA,
                    "media": {"$type": "app.bsky.embed.images"},
                    "record": {"$type": sel.EMBED_RECORD, "record": {"uri": uri("b", "q2")}},
                }
            ),
            "quote",
            uri("b", "q2"),
            None,
            None,
            None,
        ),
        (
            POST,
            constructed_post(
                reply={"parent": {"uri": uri("a", "p")}, "root": {"uri": uri("a", "r")}},
                embed={"$type": sel.EMBED_RECORD, "record": {"uri": uri("b", "q")}},
            ),
            "reply",
            uri("a", "p"),
            uri("a", "r"),
            uri("b", "q"),
            None,
        ),
        (REPOST, {"subject": {"uri": uri("c", "s")}}, "repost", uri("c", "s"), None, None, None),
        (
            REPOST,
            {"subject": {"uri": uri("c", "s")}, "via": {"uri": uri("d", "v", REPOST)}},
            "repost",
            uri("c", "s"),
            None,
            None,
            uri("d", "v", REPOST),
        ),
    ],
)
def test_derive_edge_table(collection, record, kind, parent, root, quoted, via):
    edge = sel.derive_edge(collection, record)
    assert edge == sel.Edge(kind, parent, root, quoted, via)


def test_derive_edge_drops_unusable_targets_and_tolerates_junk():
    generator = uri("e", "g", "app.bsky.feed.generator")
    assert sel.derive_edge(REPOST, {"subject": {"uri": generator}}) is None
    quote_of_generator = constructed_post(
        embed={"$type": sel.EMBED_RECORD, "record": {"uri": generator}}
    )
    assert sel.derive_edge(POST, quote_of_generator) == sel.Edge("root")
    web = "at://did:web:example.test/app.bsky.feed.post/abc"
    assert sel.derive_edge(REPOST, {"subject": {"uri": web}}).parent == web
    assert (
        sel.derive_edge(POST, constructed_post(embed={"$type": "x.unknown.embed"})).kind == "root"
    )
    assert sel.derive_edge(POST, constructed_post(reply={"parent": {"uri": "junk"}})) is None
    assert sel.derive_edge(POST, "not a record") is None
    assert sel.derive_edge("app.bsky.feed.like", {}) is None
    assert sel.parse_at_uri("at://handle.example/app.bsky.feed.post/x") is None


def test_link_urls_union_of_card_and_facet():
    record = constructed_post(
        embed={"$type": sel.EMBED_EXTERNAL, "external": {"uri": "https://a.test/x"}},
        facets=[
            {"features": [{"$type": "app.bsky.richtext.facet#mention", "did": "did:plc:x"}]},
            {"features": [{"$type": sel.FACET_LINK, "uri": "https://b.test/y"}]},
        ],
    )
    assert sel.link_urls(record) == [("card", "https://a.test/x"), ("facet", "https://b.test/y")]
    media = constructed_post(
        embed={
            "$type": sel.EMBED_RECORD_WITH_MEDIA,
            "media": {"$type": sel.EMBED_EXTERNAL, "external": {"uri": "https://c.test/z"}},
            "record": {"record": {"uri": uri("a", "q")}},
        }
    )
    assert sel.link_urls(media) == [("card", "https://c.test/z")]
    assert sel.link_urls("junk") == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "https://WWW.Example-News.test/a/?utm_source=x&id=1#frag",
            "https://example-news.test/a?id=1",
        ),
        ("http://example.test/", "http://example.test/"),
        ("https://example.test/p?fbclid=1&gclid=2&utm_medium=3", "https://example.test/p"),
        ("https://example.test:443/p", "https://example.test/p"),
        ("ftp://example.test/x", None),
        ("javascript:alert(1)", None),
        ("https://nytimes.com@evil.example/x", "https://evil.example/x"),
        ("https://", None),
    ],
)
def test_canonicalise_url(raw, expected):
    assert sel.canonicalise_url(raw) == expected


def test_userinfo_trick_resolves_to_the_evil_host():
    canonical = sel.canonicalise_url("https://nytimes.com@evil.example/x")
    assert sel.url_host(canonical) == "evil.example"
    assert not sel.host_allowed(sel.url_host(canonical), {"nytimes.com"})


@pytest.mark.parametrize(
    ("host", "allowed"),
    [
        ("nytimes.com", True),
        ("www.nytimes.com", True),
        ("news.bbc.co.uk", True),
        ("evilnytimes.com", False),
        ("nytimes.com.evil.example", False),
        ("bbc.co.uk.evil.example", False),
        ("", False),
    ],
)
def test_allowlist_spoof_table(host, allowed):
    assert sel.host_allowed(host, {"nytimes.com", "bbc.co.uk"}) is allowed


def test_shortener_detection():
    assert sel.is_shortener("bit.ly")
    assert sel.is_shortener("go.t.co") is True
    assert sel.is_shortener("nyti.ms")
    assert not sel.is_shortener("example-news.test")
    assert not sel.is_shortener("bit.ly.evil.example")


def test_sample_keep_is_deterministic_and_matches_its_rate():
    uris = [uri("sample", f"{i:013d}") for i in range(20000)]
    assert all(sel.sample_keep(u, 10000) for u in uris[:100])
    assert not any(sel.sample_keep(u, 0) for u in uris[:100])
    first = [sel.sample_keep(u, 2500) for u in uris]
    assert first == [sel.sample_keep(u, 2500) for u in uris]
    assert 0.23 < sum(first) / len(first) < 0.27
    assert sel.sample_keep(uris[0], sel.sample_bucket(uris[0]) + 1)
    assert not sel.sample_keep(uris[0], sel.sample_bucket(uris[0]))


@pytest.mark.parametrize(
    ("record", "reason"),
    [
        (constructed_post(reply={"parent": {"uri": uri("a", "p")}}), "not_top_level"),
        (constructed_post(langs=["en"]), "no_link"),
        (
            constructed_post(
                facets=[{"features": [{"$type": sel.FACET_LINK, "uri": "https://bit.ly/x"}]}],
                langs=["en"],
            ),
            "shortener",
        ),
        (
            constructed_post(
                facets=[{"features": [{"$type": sel.FACET_LINK, "uri": "https://other.test/x"}]}],
                langs=["en"],
            ),
            "not_allowlisted",
        ),
        (
            constructed_post(
                facets=[{"features": [{"$type": sel.FACET_LINK, "uri": "https://wire.test/x"}]}],
                langs=["de"],
            ),
            "lang",
        ),
        (
            constructed_post(
                facets=[{"features": [{"$type": sel.FACET_LINK, "uri": "https://wire.test/x"}]}]
            ),
            "lang",
        ),
        (
            constructed_post(
                facets=[{"features": [{"$type": sel.FACET_LINK, "uri": "https://wire.test/x"}]}],
                langs=["en"],
                labels={"values": [{"val": "porn"}]},
            ),
            "adult_label",
        ),
        (
            constructed_post(
                facets=[{"features": [{"$type": sel.FACET_LINK, "uri": "https://wire.test/x"}]}],
                langs=["en"],
                labels={"values": [{"val": "!no-unauthenticated"}]},
            ),
            "no_unauthenticated_label",
        ),
    ],
)
def test_seed_decision_reasons(record, reason):
    decision = sel.seed_decision(record, uri("a", "root"), ALLOW)
    assert decision.eligible is False
    assert decision.reason == reason


def test_seed_decision_eligible_and_sampled_out():
    record = constructed_post(
        embed={
            "$type": sel.EMBED_EXTERNAL,
            "external": {"uri": "https://www.wire.test/n?utm_source=a"},
        },
        langs=["en"],
    )
    decision = sel.seed_decision(record, uri("a", "root"), ALLOW)
    assert decision == sel.SeedDecision(True, "eligible", "wire.test", "https://wire.test/n")
    bucket = sel.sample_bucket(uri("a", "root"))
    out = sel.seed_decision(record, uri("a", "root"), ALLOW, sample_per_10k=bucket)
    assert out.reason == "sampled_out"
    assert sel.seed_decision(record, uri("a", "root"), ALLOW, require_lang="").eligible


# ----------------------------------------------------------------------------- scrubber


def test_counter_tokens_are_sequential_and_grammatical():
    assert scrub.counter_token(0, 13, "2") == "2" * 13
    assert scrub.counter_token(1, 13, "2") == "2" * 11 + "23"
    assert scrub.counter_token(32, 13, "2") == "2" * 11 + "32"
    maps = scrub.ScrubMaps()
    first = maps.did("did:plc:one")
    assert DID_RX.match(first)
    assert maps.did("did:plc:two") != first
    assert maps.did("did:plc:one") == first
    assert TOKEN13_RX.match(maps.rkey("anything"))
    assert TOKEN13_RX.match(maps.rev("rev"))
    assert maps.did_web == 0
    maps.did("did:web:example.test")
    assert maps.did_web == 1


def test_scrub_post_drops_text_cid_query_and_non_link_facets():
    original = {
        "$type": "message",
        "payload": {
            "$type": TYPE + "commit",
            "did": "did:plc:authorone",
            "seq": 7,
            "time": ts(3),
            "witnessedAt": ts(3),
            "operation": "create",
            "collection": POST,
            "rkey": "rkeyone",
            "rev": "revone",
            "cid": "bafycidmarker",
            "record": {
                "$type": POST,
                "createdAt": ts(2),
                "text": "MARKERTEXT body",
                "langs": ["en"],
                "tags": ["MARKERTAG"],
                "reply": {
                    "parent": {"uri": uri("authortwo", "parentkey"), "cid": "bafyparent"},
                    "root": {"uri": uri("authorone", "rootkey"), "cid": "bafyroot"},
                },
                "embed": {
                    "$type": sel.EMBED_EXTERNAL,
                    "external": {
                        "uri": "https://User:pw@Example.test/a/b?token=1#x",
                        "title": "MARKERTITLE",
                        "description": "MARKERDESC",
                        "thumb": {"ref": "t"},
                    },
                },
                "facets": [
                    {
                        "index": {"byteStart": 0, "byteEnd": 5},
                        "features": [
                            {"$type": "app.bsky.richtext.facet#mention", "did": "did:plc:mentioned"}
                        ],
                    },
                    {
                        "index": {"byteStart": 6, "byteEnd": 9},
                        "features": [
                            {"$type": sel.FACET_LINK, "uri": "https://example.test/c?q=1"}
                        ],
                    },
                ],
                "labels": {
                    "$type": "com.atproto.label.defs#selfLabels",
                    "values": [{"val": "porn"}, {"val": "Bad Value!"}],
                },
            },
        },
    }
    maps = scrub.ScrubMaps()
    out = scrub.scrub_frame(original, maps)
    text = scrub.dumps(out)
    for marker in (
        "MARKER",
        "authorone",
        "authortwo",
        "bafy",
        "token=1",
        "pw",
        "mentioned",
        "Bad Value",
    ):
        assert marker not in text
    payload = out["payload"]
    assert payload["did"] == maps.did("did:plc:authorone")
    assert (
        payload["record"]["reply"]["root"]["uri"]
        == f"at://{payload['did']}/{POST}/{maps.rkey('rootkey')}"
    )
    assert payload["record"]["embed"]["external"] == {"uri": "https://example.test/a/b"}
    assert payload["record"]["facets"][0]["features"][0]["uri"] == "https://example.test/c"
    assert payload["record"]["labels"]["values"] == [{"val": "porn"}]
    assert "cid" not in payload
    assert not re.search(r"\b[0-9a-fA-F]{32}\b", text)
    assert scrub.dumps(scrub.scrub_frame(original, scrub.ScrubMaps())) == text


def test_scrub_maps_did_web_to_plc_and_counts_it():
    frame = {
        "$type": "message",
        "payload": {
            "$type": TYPE + "commit",
            "did": "did:web:example.test",
            "seq": 1,
            "time": ts(1),
            "operation": "create",
            "collection": REPOST,
            "rkey": "k",
            "rev": "r",
            "record": {
                "$type": REPOST,
                "subject": {"uri": "at://did:web:other.test/app.bsky.feed.post/p", "cid": "c"},
                "createdAt": ts(0),
            },
        },
    }
    maps = scrub.ScrubMaps()
    out = scrub.scrub_frame(frame, maps)
    assert "did:web" not in scrub.dumps(out)
    assert maps.did_web == 2


def test_scrub_account_sync_info_and_unsafe_frames():
    maps = scrub.ScrubMaps()
    account = {
        "$type": "message",
        "payload": {
            "$type": TYPE + "account",
            "did": "did:plc:acct",
            "seq": 5,
            "time": ts(1),
            "account": {
                "active": False,
                "did": "did:plc:acct",
                "seq": 99,
                "status": "bizarre",
                "time": ts(1),
            },
        },
    }
    out = scrub.scrub_frame(account, maps)
    assert out["payload"]["account"]["status"] == "other"
    sync = {
        "$type": "message",
        "payload": {
            "$type": TYPE + "sync",
            "did": "did:plc:acct",
            "seq": 6,
            "time": ts(2),
            "sync": {
                "blocks": {"$bytes": "QUJD"},
                "did": "did:plc:acct",
                "rev": "r",
                "seq": 3,
                "time": ts(2),
            },
        },
    }
    assert scrub.scrub_frame(sync, maps)["payload"]["sync"]["blocks"] == "dropped"
    info = {
        "$type": "message",
        "payload": {
            "$type": TYPE + "info",
            "name": "OutdatedCursor",
            "message": "starting at seq 26111682562",
        },
    }
    assert scrub.scrub_frame(info, maps)["payload"]["name"] == "OutdatedCursor"
    leaky = {
        "$type": "message",
        "payload": {"$type": TYPE + "info", "name": "x", "message": "at://did:plc:x/y/z"},
    }
    assert "message" not in scrub.scrub_frame(leaky, maps)["payload"]
    identity = {
        "$type": "message",
        "payload": {"$type": TYPE + "identity", "did": "did:plc:i", "seq": 1, "time": ts(1)},
    }
    assert scrub.scrub_frame(identity, maps) is None
    like = {
        "$type": "message",
        "payload": {
            "$type": TYPE + "commit",
            "did": "did:plc:i",
            "collection": "app.bsky.feed.like",
            "operation": "create",
            "rkey": "k",
            "record": {},
        },
    }
    assert scrub.scrub_frame(like, maps) is None


def test_scrub_v1_frame_matches_the_v2_scrub_rules():
    frame = {
        "did": "did:plc:v1author",
        "time_us": 1700000000000000,
        "kind": "commit",
        "commit": {
            "rev": "r1",
            "operation": "create",
            "collection": POST,
            "rkey": "k1",
            "cid": "bafyv1",
            "record": constructed_post(text="MARKERV1"),
        },
    }
    out = scrub.scrub_v1_frame(frame, scrub.ScrubMaps())
    text = scrub.dumps(out)
    assert "MARKERV1" not in text
    assert "bafyv1" not in text
    assert "v1author" not in text
    assert out["time_us"] == 1700000000000000


# ----------------------------------------------------------------------------- constructed log


class LogBuilder:
    def __init__(self) -> None:
        self.frames: list[str] = []
        self.seq = 0

    def commit(self, sec, did, coll, rkey, record=None, op="create"):
        self.seq += 1
        payload = {
            "$type": TYPE + "commit",
            "did": f"did:plc:{did}",
            "seq": self.seq,
            "time": ts(sec),
            "witnessedAt": ts(sec),
            "operation": op,
            "collection": coll,
            "rkey": rkey,
            "rev": "rev" + rkey,
        }
        if record is not None:
            payload["record"] = record
            payload["cid"] = "bafycid" + rkey
        text = json.dumps({"$type": "message", "payload": payload})
        self.frames.append(text)
        return text

    def other(self, sec, kind, **fields):
        self.seq += 1
        payload = {"$type": TYPE + kind, "seq": self.seq, "time": ts(sec), "witnessedAt": ts(sec)}
        payload.update(fields)
        self.frames.append(json.dumps({"$type": "message", "payload": payload}))


def card(url):
    return {"$type": sel.EMBED_EXTERNAL, "external": {"uri": url, "title": "MARKERTITLE"}}


def facet(url):
    return [
        {
            "index": {"byteStart": 0, "byteEnd": 10},
            "features": [{"$type": sel.FACET_LINK, "uri": url}],
        }
    ]


def build_constructed_log(directory: Path, label: str = "wA", offset: float = 0.0) -> None:
    """Write one constructed raw log and its meta file.

    Hand-computed expectations (see test_constructed_log_measurements): 28 frames after one
    duplicate, a malformed line and a control line; stream span 27 s; three eligible roots R1, R2,
    R8 (R1 and R8 share one canonical URL); R1 holds 7 children (4 replies, 1 quote, 2 reposts),
    R2 one orphan reply, R8 none.
    """
    b = LogBuilder()
    t = lambda s: s + offset  # noqa: E731
    r1, r2, r8 = uri("author1", "root1"), uri("author2", "root2"), uri("author8", "root8")
    b.commit(
        t(0),
        "author1",
        POST,
        "root1",
        constructed_post(
            createdAt=ts(t(-1)),
            embed=card("https://www.example-news.test/a?utm_source=x&id=1"),
            langs=["en"],
            text="commentary words https://example-news.test/a",
        ),
    )
    b.commit(
        t(1),
        "author2",
        POST,
        "root2",
        constructed_post(
            createdAt=ts(t(0)),
            facets=facet("https://example-news.test/b"),
            langs=["en", "fr"],
            text="https://example-news.test/b",
        ),
    )
    b.commit(
        t(2),
        "author3",
        POST,
        "root3",
        constructed_post(createdAt=ts(t(1)), embed=card("https://other.test/x"), langs=["en"]),
    )
    b.commit(
        t(3),
        "author4",
        POST,
        "root4",
        constructed_post(createdAt=ts(t(2)), facets=facet("https://wire.test/n"), langs=["de"]),
    )
    b.commit(
        t(4),
        "author5",
        POST,
        "root5",
        constructed_post(createdAt=ts(t(3)), facets=facet("https://bit.ly/abc"), langs=["en"]),
    )
    b.commit(
        t(5), "author6", POST, "root6", constructed_post(createdAt=ts(t(5) - 7200), langs=["en"])
    )
    b.commit(
        t(6),
        "author7",
        POST,
        "root7",
        constructed_post(
            createdAt=ts(t(5)),
            embed=card("https://wire.test/adult"),
            facets=facet("https://wire.test/adult"),
            langs=["en"],
            labels={"values": [{"val": "porn"}]},
        ),
    )
    b.commit(
        t(7),
        "author8",
        POST,
        "root8",
        constructed_post(
            createdAt=ts(t(6)),
            embed=card("https://example-news.test/a?id=1&fbclid=zzz"),
            langs=["en"],
        ),
    )
    b.commit(
        t(10),
        "author9",
        POST,
        "re1",
        constructed_post(createdAt=ts(t(9)), reply={"parent": {"uri": r1}, "root": {"uri": r1}}),
    )
    b.commit(
        t(11),
        "author10",
        POST,
        "re2",
        constructed_post(
            createdAt=ts(t(10)),
            reply={"parent": {"uri": uri("author9", "re1")}, "root": {"uri": r1}},
        ),
    )
    b.commit(
        t(12),
        "author11",
        POST,
        "q1",
        constructed_post(
            createdAt=ts(t(11)),
            langs=["en"],
            embed={"$type": sel.EMBED_RECORD, "record": {"uri": r1}},
            facets=facet("https://example-news.test/q"),
        ),
    )
    b.commit(
        t(13),
        "author12",
        REPOST,
        "p1",
        {"$type": REPOST, "createdAt": ts(t(12)), "subject": {"uri": r1}},
    )
    dup = b.commit(
        t(14),
        "author13",
        REPOST,
        "p2",
        {
            "$type": REPOST,
            "createdAt": ts(t(13)),
            "subject": {"uri": r1},
            "via": {"uri": uri("author12", "p1", REPOST)},
        },
    )
    b.commit(
        t(15),
        "author14",
        POST,
        "re3",
        constructed_post(
            createdAt=ts(t(14)),
            reply={"parent": {"uri": uri("zzz", "unknownparent")}, "root": {"uri": r2}},
        ),
    )
    b.commit(
        t(16),
        "author15",
        REPOST,
        "p3",
        {"$type": REPOST, "createdAt": ts(t(15)), "subject": {"uri": uri("zzz", "untracked")}},
    )
    b.commit(
        t(17),
        "author16",
        POST,
        "re4",
        constructed_post(
            createdAt=ts(t(16)),
            facets=facet("https://wire.test/r"),
            reply={"parent": {"uri": uri("zzz", "other")}, "root": {"uri": uri("zzz", "other")}},
        ),
    )
    b.commit(
        t(18),
        "author17",
        POST,
        "rq",
        constructed_post(
            createdAt=ts(t(17)),
            reply={"parent": {"uri": uri("author10", "re2")}, "root": {"uri": r1}},
            embed={"$type": sel.EMBED_RECORD, "record": {"uri": r2}},
        ),
    )
    b.commit(
        t(19),
        "author18",
        POST,
        "gen",
        constructed_post(
            createdAt="garbage",
            embed={
                "$type": sel.EMBED_RECORD,
                "record": {"uri": uri("zzz", "feed", "app.bsky.feed.generator")},
            },
        ),
    )
    b.commit(
        t(19),
        "author19",
        POST,
        "re5",
        constructed_post(
            createdAt=ts(t(18)),
            reply={"parent": {"uri": uri("author9", "re1")}, "root": {"uri": r2}},
        ),
    )
    b.commit(t(20), "author9", POST, "re1", None, op="delete")
    b.commit(t(21), "author2", POST, "root2", None, op="delete")
    b.other(
        t(22),
        "account",
        did="did:plc:acct1",
        account={
            "active": False,
            "did": "did:plc:acct1",
            "seq": 1,
            "status": "deleted",
            "time": ts(t(22)),
        },
    )
    b.other(
        t(23),
        "account",
        did="did:plc:acct2",
        account={
            "active": False,
            "did": "did:plc:acct2",
            "seq": 2,
            "status": "takendown",
            "time": ts(t(23)),
        },
    )
    b.other(
        t(24),
        "account",
        did="did:plc:acct3",
        account={
            "active": False,
            "did": "did:plc:acct3",
            "seq": 3,
            "status": "weird",
            "time": ts(t(24)),
        },
    )
    b.other(
        t(25),
        "sync",
        did="did:plc:acct4",
        sync={
            "blocks": {"$bytes": "QUJD"},
            "did": "did:plc:acct4",
            "rev": "r",
            "seq": 4,
            "time": ts(t(25)),
        },
    )
    b.frames.append(
        json.dumps(
            {
                "$type": "message",
                "payload": {
                    "$type": TYPE + "info",
                    "name": "OutdatedCursor",
                    "message": "starting at seq 1",
                },
            }
        )
    )
    b.commit(t(27), "author20", "app.bsky.feed.like", "like1", {"$type": "app.bsky.feed.like"})
    b.commit(t(8), "author21", POST, "late", constructed_post(createdAt=ts(t(108)), langs=["en"]))
    b.frames.append(dup)  # exact duplicate delivery: removed by the (host, seq) dedup
    del r8
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{label}.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as handle:
        for index, frame in enumerate(b.frames):
            handle.write(json.dumps({"rx": 1_700_000_000_000 + index, "f": frame}) + "\n")
        handle.write("this line is not json\n")
        handle.write(json.dumps({"rx": 1, "ev": "connect", "detail": {}}) + "\n")
    meta = {
        "host": "constructed.example",
        "dialect": "v2",
        "bound_seconds": 100,
        "max_bytes": 10**6,
        "stop_reason": "seconds",
    }
    (directory / f"{label}.meta.json").write_text(json.dumps(meta), encoding="utf-8")


@pytest.fixture(scope="module")
def constructed(tmp_path_factory):
    directory = tmp_path_factory.mktemp("constructed_raw")
    build_constructed_log(directory)
    refs = analysis.discover_logs(directory)
    results, collector, stats = analysis.analyze_logs(refs, ALLOW, keep_rows=True)
    return directory, refs, results, collector, stats


def test_reader_counts_malformed_control_and_duplicate_lines(constructed):
    _directory, _refs, _results, _collector, stats = constructed
    assert stats["malformed_lines"] == 1
    assert stats["control_lines"] == 1
    assert stats["duplicate_frames"] == 1
    assert stats["unparseable_frames"] == 0


def test_constructed_log_s2_volume(constructed):
    s2 = constructed[2]["combined"]["s2"]
    assert s2["frames"] == 28
    assert s2["stream_seconds"] == 27.0
    assert s2["by_kind"]["commit/create/app.bsky.feed.post"]["count"] == 17
    assert s2["by_kind"]["commit/create/app.bsky.feed.repost"]["count"] == 3
    assert s2["by_kind"]["commit/delete/app.bsky.feed.post"]["count"] == 2
    assert s2["by_kind"]["account"]["count"] == 3
    shares = s2["post_create_shares"]
    assert shares["top_level"] == pytest.approx(10 / 17, abs=1e-4)
    assert shares["reply"] == pytest.approx(5 / 17, abs=1e-4)
    assert shares["quote"] == pytest.approx(1 / 17, abs=1e-4)
    assert shares["reply_quote"] == pytest.approx(1 / 17, abs=1e-4)
    assert s2["frame_bytes"]["max"] >= s2["frame_bytes"]["p50"]
    assert s2["per_second_events"]["max"] >= 2


def test_constructed_log_s4_time(constructed):
    s4 = constructed[2]["combined"]["s4"]
    assert s4["arrival_inversions"] == 1
    assert s4["largest_inversion_seconds"] == 19.0
    assert s4["created_future_gt_60s"] == 1
    assert s4["created_older_than_1h"] == 1
    assert s4["created_absurd_or_unparseable"] == 1
    assert s4["created_minus_stream_seconds"]["n"] == 16
    assert s4["parent_child_pairs_in_log"] == 7
    assert s4["child_before_parent"] == 0
    assert s4["seq_backwards"] == 0


def test_constructed_log_s5_yield(constructed):
    s5 = constructed[2]["combined"]["s5"]
    assert s5["eligible_roots"] == 3
    assert s5["eligible_per_hour"] == 400.0
    assert s5["decisions"] == {
        "adult_label": 1,
        "eligible": 3,
        "lang": 1,
        "no_link": 3,
        "not_allowlisted": 1,
        "shortener": 1,
    }
    assert s5["allowlisted_link_roots"] == 5
    assert s5["english_share"] == 0.8
    assert s5["adult_label_share"] == 0.2
    assert s5["commentary_share"] == 0.8
    assert s5["distinct_domains"] == 1
    assert s5["top_domains"][0] == {"domain": "example-news.test", "roots": 3, "authors": 3}
    assert s5["cascade_children"] == {
        "n": 3,
        "median": 1.0,
        "p90": 7.0,
        "p99": 7.0,
        "max": 7.0,
        "with_children": 2,
    }
    assert s5["reply_depth"] == {"1": 1, "2": 2, "3": 1, "orphan": 1}
    assert s5["orphan_rate"] == 0.2
    assert s5["top1pct_event_share"] == pytest.approx(8 / 11, abs=1e-4)
    assert s5["outcomes"]["observed"] == {
        "n": 3,
        "any": 0.6667,
        "reply": 0.6667,
        "quote": 0.3333,
        "repost": 0.3333,
    }
    assert s5["outcomes"]["15m"]["n"] == 0
    assert s5["outcomes"]["15m"]["any"] is None
    assert s5["sampling"]["10000"]["roots"] == 3
    assert s5["sampling"]["625"]["roots"] <= 3
    assert s5["option_c_distinct_subjects_per_bucket_mean"] == 6.0
    assert s5["option_c_thresholds"]["10"]["subjects_per_bucket_mean"] == 0.0


def test_constructed_log_s6_shapes(constructed):
    s6 = constructed[2]["combined"]["s6"]
    assert s6["reply_quote_posts"] == 1
    assert s6["top_level_link_sources"] == {
        "both": 1,
        "card_only": 3,
        "facet_only": 3,
        "neither": 3,
    }
    assert s6["top_level_with_shortener"] == 1
    assert s6["quote_targets_not_posts"] == 1
    assert s6["embed_types"]["record"] == 3
    assert s6["reposts"]["via"] == 1
    assert s6["reposts"]["via_seen"] == 1
    assert s6["reposts"]["via_same_subject"] == 1
    assert s6["reposts"]["root_subject"] == 2
    assert s6["reposts"]["untracked_subject"] == 1
    assert s6["repost_via_share"] == pytest.approx(1 / 3, abs=1e-4)


def test_constructed_log_s7_deletes_and_accounts(constructed):
    s7 = constructed[2]["combined"]["s7"]
    assert s7["deletes"] == {"post": 2}
    lat = s7["delete_latency_seconds_all_posts"]
    assert (lat["n"], lat["p50"], lat["max"]) == (2, 10.0, 20.0)
    assert s7["delete_latency_seconds_tracked_roots"]["p50"] == 20.0
    assert s7["delete_latency_seconds_tracked_children"]["p50"] == 10.0
    assert s7["account_events_by_status"] == {"deleted": 1, "other": 1, "takendown": 1}
    assert s7["unknown_status_values_distinct"] == 1
    assert s7["sync_events"] == 1
    assert s7["info_frames"] == {"OutdatedCursor": 1}
    assert s7["other_frames"] == 1


def test_constructed_log_s9_merge_frequency(constructed):
    s9 = constructed[2]["combined"]["s9"]
    assert s9["children_whose_parent_is_in_another_cascade"] == 1
    assert s9["roots"] == 3
    assert s9["distinct_canonical_urls"] == 2
    assert s9["roots_in_shared_url_groups"] == 2
    assert s9["largest_url_group"] == 2
    assert s9["quote_posts_seed_eligible"] == 1


def test_per_window_and_combined_agree_for_one_window(constructed):
    results = constructed[2]
    assert results["windows"]["wA"]["s5"] == results["combined"]["s5"]


def test_ensure_no_identifiers_raises_and_results_are_clean(constructed):
    for bad in ("did:plc:abc", "at://x/y/z", "someone@example.com", {"k": ["did:web:x"]}):
        with pytest.raises(ValueError, match="identifier"):
            analysis.ensure_no_identifiers(bad)
    analysis.ensure_no_identifiers({"domain": "example-news.test", "n": 3, "list": ["a", 1.5]})
    analysis.ensure_no_identifiers(constructed[2])
    markdown = analysis.summary_markdown(constructed[2]["combined"])
    analysis.ensure_no_identifiers(markdown)
    for marker in ("author1", "MARKER", "commentary words", "zzz"):
        assert marker not in markdown
        assert marker not in json.dumps(constructed[2])


def test_summary_markdown_has_one_heading_per_measurement_in_order(constructed):
    markdown = analysis.summary_markdown(constructed[2]["combined"])
    headings = re.findall(r"^### (S-\d+)", markdown, flags=re.MULTILINE)
    assert headings == ["S-2", "S-4", "S-5", "S-6", "S-7", "S-9"]


def test_window_spans_two_windows(tmp_path):
    build_constructed_log(tmp_path, "wA", 0.0)
    build_constructed_log(tmp_path, "wB", 7200.0)
    refs = analysis.discover_logs(tmp_path)
    spans = analysis.window_spans(refs)
    assert [s["label"] for s in spans] == ["wA", "wB"]
    for span in spans:
        assert span["stream_seconds"] == pytest.approx((span["last_us"] - span["first_us"]) / 1e6)
        assert span["stream_seconds"] == 27.0
        assert span["frames"] == 28
        assert span["dialect"] == "v2"
        assert re.fullmatch(r"[0-9a-f]{64}", span["raw_sha256"])
        assert span["bound_seconds"] == 100
        assert span["stop_reason"] == "seconds"
    assert spans[1]["first_us"] - spans[0]["first_us"] == 7200 * 1_000_000
    results, _collector, _stats = analysis.analyze_logs(refs, ALLOW)
    assert results["combined"]["s2"]["stream_seconds"] == 54.0
    assert results["combined"]["s5"]["eligible_roots"] == 6


def test_domains_only_filters_rare_authors(constructed):
    out = analysis.domains_only(constructed[1], ALLOW, min_authors=1)
    domains = {row["domain"]: row for row in out["top_domains"]}
    assert domains["example-news.test"]["authors"] == 3
    assert "bit.ly" in domains
    assert analysis.domains_only(constructed[1], ALLOW, min_authors=4)["top_domains"] == []


# ----------------------------------------------------------------------------- cutter


def _cut(constructed, out_dir, **kw):
    _directory, refs, _results, collector, _stats = constructed
    return scrub.cut(
        collector,
        allowlist=sorted(ALLOW),
        out_dir=out_dir,
        date="2026-01-01",
        windows=analysis.window_spans(refs),
        samples=[
            {
                "dialect": "v1",
                "f": json.dumps(
                    {
                        "did": "did:plc:v1",
                        "time_us": 1,
                        "kind": "account",
                        "account": {"active": True, "status": "active"},
                    }
                ),
            }
        ],
        tool_sha="0" * 40,
        **kw,
    )


def test_cutter_is_deterministic_and_manifest_has_the_data_contract(constructed, tmp_path):
    first = _cut(constructed, tmp_path / "one", min_children=2)
    second = _cut(constructed, tmp_path / "two", min_children=2)
    for name in (
        "bluesky-2026-01-01.jsonl",
        "bluesky-2026-01-01.samples.jsonl",
        "bluesky-2026-01-01.manifest.json",
    ):
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes()
    assert first == second
    assert first["source_mode"] == "recorded-real"
    assert first["selection_policy"]["sample_per_10k"] == 10000
    assert first["selection_policy"]["require_lang"] == "en"
    assert first["selection_policy"]["allowlist_domains"] == sorted(ALLOW)
    assert first["windows"][0]["label"] == "wA"
    assert (
        first["windows"][0]["stream_seconds"]
        == (first["windows"][0]["last_us"] - first["windows"][0]["first_us"]) / 1e6
    )
    assert first["counts_by_kind"] == {
        "post_create": 17,
        "repost_create": 3,
        "post_delete": 2,
        "repost_delete": 0,
        "account": 3,
        "sync": 1,
        "info": 0,
    }
    cov = first["coverage"]
    assert cov["tracked_roots"] == 3
    assert cov["children_by_kind"] == {"reply": 5, "quote": 1, "repost": 2}
    assert (
        cov["cascades_with_replies"],
        cov["cascades_with_quotes"],
        cov["cascades_with_reposts"],
    ) == (2, 1, 1)
    assert cov["cascades_with_depth2_replies"] == 1
    assert cov["orphan_replies"] == 1
    assert cov["deletes"] == {"post": 2, "repost": 0}
    assert cov["account_events_by_status"] == {"deleted": 1, "other": 1, "takendown": 1}
    assert cov["sync_events"] == 1
    assert cov["negative_controls"] == {
        "total": 9,
        "near_miss_non_allowlisted": 1,
        "non_english_allowlisted": 1,
        "adult_labelled": 1,
        "shortener": 1,
        "reply_with_link": 1,
    }
    assert first["trimmed"] is False
    assert first["frames_dropped_by_scrubber"] == 0


def test_cut_fixture_has_no_text_cid_queries_or_raw_identifiers(constructed, tmp_path):
    manifest = _cut(constructed, tmp_path, min_children=2)
    body = (tmp_path / "bluesky-2026-01-01.jsonl").read_text(encoding="utf-8")
    assert "\r" not in body
    assert body.endswith("\n")
    for marker in (
        "MARKER",
        "author",
        "commentary",
        "bafycid",
        "utm_",
        "fbclid",
        "?id=",
        "did:web",
    ):
        assert marker not in body
    keys: set[str] = set()

    def walk(value):
        if isinstance(value, dict):
            keys.update(value)
            for inner in value.values():
                walk(inner)
        elif isinstance(value, list):
            for inner in value:
                walk(inner)

    dids = set(re.findall(r"did:plc:[a-z0-9]+", body))
    assert dids
    assert all(DID_RX.match(d) for d in dids)
    for line in body.splitlines():
        walk(json.loads(line))
    assert not keys & {"cid", "text", "title", "description", "thumb", "alt"}
    assert not re.search(r"\b[0-9a-fA-F]{32}\b", body)
    assert sum(f["bytes"] for f in manifest["files"]) <= 1_500_000
    assert {f["name"] for f in manifest["files"]} == {
        "bluesky-2026-01-01.jsonl",
        "bluesky-2026-01-01.samples.jsonl",
    }
    samples = (tmp_path / "bluesky-2026-01-01.samples.jsonl").read_text(encoding="utf-8")
    assert '"dialect":"v1"' in samples
    assert "did:plc:v1" not in samples


def test_cutter_replays_children_after_their_roots(constructed, tmp_path):
    _cut(constructed, tmp_path, min_children=2)
    position: dict[str, int] = {}
    edges: list[tuple[int, str]] = []
    lines = (tmp_path / "bluesky-2026-01-01.jsonl").read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        payload = json.loads(line)["payload"]
        if not payload["$type"].endswith("#commit") or payload["operation"] != "create":
            continue
        position[f"at://{payload['did']}/{payload['collection']}/{payload['rkey']}"] = index
        edge = sel.derive_edge(payload["collection"], payload["record"])
        if edge is not None and edge.parent is not None:
            edges.append((index, edge.parent))
    linked = [(i, parent) for i, parent in edges if parent in position]
    assert len(linked) >= 7
    assert all(position[parent] < i for i, parent in linked)


def test_cutter_enforces_its_budget_and_trims_in_a_fixed_order(constructed, tmp_path):
    full = _cut(constructed, tmp_path / "full", min_children=99)
    total = sum(f["bytes"] for f in full["files"])
    budget = int(total * 0.75)
    small = _cut(constructed, tmp_path / "small", min_children=99, max_bytes=budget)
    assert small["trimmed"] is True
    assert sum(f["bytes"] for f in small["files"]) <= budget
    again = _cut(constructed, tmp_path / "again", min_children=99, max_bytes=budget)
    assert again == small
    assert (
        small["coverage"]["negative_controls"]["total"]
        < full["coverage"]["negative_controls"]["total"]
    )
    tiny = _cut(constructed, tmp_path / "tiny", min_children=99, max_bytes=2500)
    assert tiny["coverage"]["tracked_roots"] < full["coverage"]["tracked_roots"]
    assert tiny["coverage"]["negative_controls"]["total"] == 0


def test_cutter_coverage_keys_are_present_when_the_data_lacks_the_shape(tmp_path):
    raw = tmp_path / "raw"
    b = LogBuilder()
    b.commit(
        0,
        "solo",
        POST,
        "root1",
        constructed_post(embed=card("https://wire.test/only"), langs=["en"]),
    )
    raw.mkdir()
    with gzip.open(raw / "w1.jsonl.gz", "wt", encoding="utf-8") as handle:
        for index, frame in enumerate(b.frames):
            handle.write(json.dumps({"rx": index, "f": frame}) + "\n")
    (raw / "w1.meta.json").write_text(json.dumps({"host": "h", "dialect": "v2"}), encoding="utf-8")
    refs = analysis.discover_logs(raw)
    _results, collector, _stats = analysis.analyze_logs(refs, ALLOW, keep_rows=True)
    manifest = scrub.cut(
        collector,
        allowlist=sorted(ALLOW),
        out_dir=tmp_path / "out",
        date="2026-01-02",
        windows=analysis.window_spans(refs),
        tool_sha="1" * 40,
    )
    cov = manifest["coverage"]
    assert cov["tracked_roots"] == 1
    assert cov["children_by_kind"] == {"reply": 0, "quote": 0, "repost": 0}
    assert cov["deletes"] == {"post": 0, "repost": 0}
    assert cov["account_events_by_status"] == {}
    assert cov["sync_events"] == 0
    assert set(cov["negative_controls"]) == {
        "total",
        "near_miss_non_allowlisted",
        "non_english_allowlisted",
        "adult_labelled",
        "shortener",
        "reply_with_link",
    }
    assert Counter(manifest["counts_by_kind"].values()) == Counter({0: 6, 1: 1})


def test_iter_tracked_rows_yields_roots_children_and_deletes_in_stream_order(constructed):
    rows = list(analysis.iter_tracked_rows(constructed[3]))
    kinds = Counter(r.kind for r in rows)
    assert kinds == {"root": 3, "child": 8, "delete": 2}
    orders = [r.frame.order for r in rows]
    assert orders == sorted(orders)
    depths = [r.depth for r in rows if r.edge_kind == "reply" and not r.orphan]
    assert sorted(d for d in depths if d is not None) == [1, 2, 2, 3]
