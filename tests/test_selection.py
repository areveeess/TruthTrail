"""Selection functions shipped in ``truthtrail.ingest.selection`` (D-12, D-13, OD-3 A and B).

The module moved from the spike with ``git mv`` (plan 03-04), so the functions that measured the
ratified yield are the functions that ship. The first block of tests moved here unchanged from
tests/test_spike_analysis.py apart from the import path; their inputs are constructed data (names
start with ``constructed_``). The additions test ``sample_bucket``, ``load_allowlist``, the
candidate-based decision, option B and the end-to-end yield over the real recorded fixture under
the policy recorded in its manifest (never the editable seed_domains.txt). No OD value is
hard-coded: every policy value is passed explicitly or read from the manifest.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from conftest import (
    fixture_manifest,
    fixture_selection_policy,
    recorded_lines,
)

from truthtrail.ingest import selection as sel
from truthtrail.ingest.dialect import classify_frame
from truthtrail.ingest.normalise import NormalizedEvent, normalise
from truthtrail.ingest.pseudonym import Keyer

POST = sel.POST_COLLECTION
REPOST = sel.REPOST_COLLECTION
T0 = datetime(2026, 1, 1, tzinfo=UTC)
ALLOW = frozenset({"example-news.test", "wire.test"})
PACKAGED_ALLOWLIST = Path(sel.__file__).resolve().parents[1] / "data" / "seed_domains.txt"


def ts(sec: float) -> str:
    return (T0 + timedelta(seconds=sec)).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def uri(did: str, rkey: str, coll: str = POST) -> str:
    return f"at://did:plc:{did}/{coll}/{rkey}"


def constructed_post(**kw):
    rec = {"$type": POST, "createdAt": ts(0), "text": "constructed words"}
    rec.update(kw)
    return rec


# ----------------------------------------------------------------------------- moved unchanged


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


# ----------------------------------------------------------------------------- sample bucket


def test_sample_bucket_is_deterministic_in_range_and_defines_sample_keep():
    uris = [uri("bucket", f"{i:013d}") for i in range(3000)]
    for u in uris:
        bucket = sel.sample_bucket(u)
        assert 0 <= bucket < 10000
        assert bucket == sel.sample_bucket(u)
        digest = hashlib.sha256(u.encode("utf-8")).digest()
        assert bucket == int.from_bytes(digest[:8], "big") % 10000
        for per_10k in (0, 1, 625, 5000, 9999, 10000):
            assert sel.sample_keep(u, per_10k) is (bucket < per_10k)


def test_seed_decision_uses_a_given_bucket_instead_of_the_raw_uri():
    record = constructed_post(
        embed={"$type": sel.EMBED_EXTERNAL, "external": {"uri": "https://wire.test/n"}},
        langs=["en"],
    )
    kept = sel.seed_decision(record, None, ALLOW, sample_per_10k=10, sample_bucket=9)
    out = sel.seed_decision(record, None, ALLOW, sample_per_10k=10, sample_bucket=10)
    assert (kept.reason, out.reason) == ("eligible", "sampled_out")
    raw = uri("a", "root")
    bucket = sel.sample_bucket(raw)
    assert sel.seed_decision(record, raw, ALLOW, sample_per_10k=bucket + 1) == sel.seed_decision(
        record, "ignored", ALLOW, sample_per_10k=bucket + 1, sample_bucket=bucket
    )
    with pytest.raises(ValueError, match="sample bucket"):
        sel.seed_decision(record, None, ALLOW)


# ----------------------------------------------------------------------------- allowlist file


def test_load_allowlist_reads_the_packaged_draft_file():
    domains = sel.load_allowlist(PACKAGED_ALLOWLIST)
    assert isinstance(domains, frozenset)
    assert 0 < len(domains) <= sel.ALLOWLIST_MAX_ENTRIES == 60
    assert all(d == d.lower() and not d.startswith("www.") and "#" not in d for d in domains)


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "allowlist.txt"
    path.write_text(body, encoding="utf-8")
    return path


def test_load_allowlist_ignores_comments_and_blank_lines(tmp_path):
    path = _write(tmp_path, "# header\n\nwire.test  # wire-service\n   \nnews.example  # x\n")
    assert sel.load_allowlist(path) == frozenset({"wire.test", "news.example"})
    assert sel.load_allowlist(str(path)) == frozenset({"wire.test", "news.example"})


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("Wire.test  # wire-service\n", "lowercase"),
        ("www.wire.test  # wire-service\n", "www"),
        ("wire.test/path  # x\n", "registrable"),
        ("localhost  # x\n", "registrable"),
        ("wire.test  # a\nwire.test  # b\n", "duplicate"),
        ("".join(f"d{i}.example  # x\n" for i in range(61)), "more than 60"),
    ],
    ids=["uppercase", "www", "path", "single-label", "duplicate", "61-entries"],
)
def test_load_allowlist_refuses_instead_of_normalising(tmp_path, body, message):
    with pytest.raises(ValueError, match=message):
        sel.load_allowlist(_write(tmp_path, body))


def test_sixty_entries_are_accepted(tmp_path):
    body = "".join(f"d{i}.example  # x\n" for i in range(60))
    assert len(sel.load_allowlist(_write(tmp_path, body))) == 60


def test_the_fixture_allowlist_file_holds_exactly_the_manifest_domains(fixture_allowlist_file):
    recorded = fixture_selection_policy()["allowlist_domains"]
    assert sel.load_allowlist(fixture_allowlist_file) == frozenset(recorded)
    assert fixture_allowlist_file.resolve() != PACKAGED_ALLOWLIST.resolve()
    assert "seed_domains" not in fixture_allowlist_file.name


def test_the_fixture_policy_environment_is_built_from_the_manifest(
    fixture_policy_environment, fixture_allowlist_file, monkeypatch
):
    from truthtrail.core.policy import get_policy

    block = fixture_selection_policy()
    env = fixture_policy_environment
    assert env["TRACK_SAMPLE_PER_10K"] == str(block["sample_per_10k"]) == "10000"
    assert env["TRACK_ALLOWLIST_FILE"] == str(fixture_allowlist_file)
    assert env["TRACK_REQUIRE_LANG"] == block["require_lang"]
    assert env["TRACK_ROOT_TTL_HOURS"] == str(block["root_ttl_hours"])
    assert env["TRACK_MAX_EVENTS_PER_CASCADE"] == str(block["max_events_per_cascade"])
    frames = sum(1 for _ in recorded_lines())
    assert int(env["TRACK_MAX_ACTIVE_ROOTS"]) > frames
    assert int(env["STORE_MAX_EVENTS_TOTAL"]) > frames
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    policy = get_policy()
    assert policy.track_sample_per_10k == block["sample_per_10k"]
    assert policy.track_allowlist_file == fixture_allowlist_file
    assert sel.load_allowlist(policy.track_allowlist_file) == frozenset(block["allowlist_domains"])


# ----------------------------------------------------------------------------- explicit policy


def _link_post(host: str, **kw):
    facet = {"features": [{"$type": sel.FACET_LINK, "uri": f"https://{host}/story"}]}
    return constructed_post(facets=[facet], **kw)


@pytest.fixture(scope="module")
def packaged() -> frozenset[str]:
    return sel.load_allowlist(PACKAGED_ALLOWLIST)


@pytest.fixture(scope="module")
def listed(packaged) -> str:
    return sorted(packaged)[0]


def test_every_seed_reason_under_explicit_values_and_the_packaged_allowlist(packaged, listed):
    raw = uri("a", "root")
    bucket = sel.sample_bucket(raw)
    explicit = {"require_lang": "en", "sample_per_10k": 10000}
    cases = {
        "eligible": _link_post(listed, langs=["en"]),
        "not_top_level": _link_post(
            listed, langs=["en"], reply={"parent": {"uri": uri("a", "p")}, "root": {"uri": raw}}
        ),
        "no_link": constructed_post(langs=["en"]),
        "shortener": _link_post("bit.ly", langs=["en"]),
        "not_allowlisted": _link_post("other.example", langs=["en"]),
        "lang": _link_post(listed, langs=["de"]),
        "adult_label": _link_post(listed, langs=["en"], labels={"values": [{"val": "sexual"}]}),
        "no_unauthenticated_label": _link_post(
            listed, langs=["en"], labels={"values": [{"val": "!no-unauthenticated"}]}
        ),
    }
    seen = set()
    for reason, record in cases.items():
        decision = sel.seed_decision(record, raw, packaged, **explicit)
        assert decision.reason == reason, reason
        assert decision.eligible is (reason == "eligible")
        seen.add(reason)
    sampled = sel.seed_decision(
        cases["eligible"], raw, packaged, require_lang="en", sample_per_10k=bucket
    )
    assert sampled.reason == "sampled_out"
    seen.add("sampled_out")
    claim = sel.seed_decision(
        _link_post("other.example", langs=["en"]),
        raw,
        packaged,
        **explicit,
        known_claim_urls={"https://other.example/story"},
        seed_claim_url_match=True,
    )
    assert claim.reason == "claim_url_match"
    seen.add("claim_url_match")
    assert seen == set(sel.SEED_REASONS)


def test_every_adult_label_refuses(packaged, listed):
    for label in sorted(sel.ADULT_LABELS):
        record = _link_post(listed, langs=["en"], labels={"values": [{"val": label}]})
        assert sel.seed_decision(record, uri("a", "r"), packaged).reason == "adult_label"


# ----------------------------------------------------------------------------- option B

CLAIM_URL = "https://other.example/story"


def _decide(record, *, flag: bool, known=frozenset({CLAIM_URL}), **kw):
    return sel.seed_decision(
        record,
        uri("a", "root"),
        ALLOW,
        require_lang="en",
        sample_per_10k=kw.pop("sample_per_10k", 10000),
        known_claim_urls=known,
        seed_claim_url_match=flag,
        **kw,
    )


def test_option_b_seeds_a_known_claim_url_only_when_the_flag_is_true():
    record = _link_post("other.example", langs=["en"])
    on = _decide(record, flag=True)
    assert on == sel.SeedDecision(True, "claim_url_match", "other.example", CLAIM_URL)
    assert _decide(record, flag=False).reason == "not_allowlisted"
    assert _decide(record, flag=True, known=frozenset({"https://other.example/else"})).reason == (
        "not_allowlisted"
    )
    assert _decide(record, flag=True, known=frozenset()).reason == "not_allowlisted"
    assert _decide(record, flag=True, known=None).reason == "not_allowlisted"


def test_option_b_keeps_every_other_rule():
    def at(host: str, **kw):
        return _link_post(host, **kw)

    shortener_url = "https://bit.ly/story"
    assert _decide(at("other.example", langs=["de"]), flag=True).reason == "lang"
    assert _decide(at("other.example"), flag=True).reason == "lang"
    adult = at("other.example", langs=["en"], labels={"values": [{"val": "porn"}]})
    assert _decide(adult, flag=True).reason == "adult_label"
    hidden = at("other.example", langs=["en"], labels={"values": [{"val": "!no-unauthenticated"}]})
    assert _decide(hidden, flag=True).reason == "no_unauthenticated_label"
    short = at("bit.ly", langs=["en"])
    assert _decide(short, flag=True, known=frozenset({shortener_url})).reason == "shortener"
    reply = at(
        "other.example",
        langs=["en"],
        reply={"parent": {"uri": uri("a", "p")}, "root": {"uri": uri("a", "r")}},
    )
    assert _decide(reply, flag=True).reason == "not_top_level"
    bucket = sel.sample_bucket(uri("a", "root"))
    record = at("other.example", langs=["en"])
    assert _decide(record, flag=True, sample_per_10k=bucket).reason == "sampled_out"


def test_an_allowlisted_link_wins_over_a_claim_match():
    record = constructed_post(
        facets=[
            {"features": [{"$type": sel.FACET_LINK, "uri": CLAIM_URL}]},
            {"features": [{"$type": sel.FACET_LINK, "uri": "https://wire.test/n"}]},
        ],
        langs=["en"],
    )
    decision = _decide(record, flag=True)
    assert decision == sel.SeedDecision(True, "eligible", "wire.test", "https://wire.test/n")


# ----------------------------------------------------------------------------- candidate view


def test_the_candidate_decision_equals_the_record_decision_on_constructed_records():
    records = [
        _link_post("wire.test", langs=["en"]),
        _link_post("other.example", langs=["en"]),
        _link_post("bit.ly", langs=["en"]),
        constructed_post(langs=["en"]),
        constructed_post(
            embed={"$type": sel.EMBED_EXTERNAL, "external": {"uri": "https://WWW.wire.test/a/"}},
            langs=["fr", "en"],
            labels={"values": [{"val": "nudity"}]},
        ),
        constructed_post(reply={"parent": {"uri": uri("a", "p")}}),
    ]
    for record in records:
        raw = uri("x", "root")
        candidate = sel.seed_candidate(record, raw)
        for kw in ({}, {"known_claim_urls": {CLAIM_URL}, "seed_claim_url_match": True}):
            assert sel.seed_decision_for(candidate, ALLOW, **kw) == sel.seed_decision(
                record, raw, ALLOW, **kw
            )


# ----------------------------------------------------------------------------- real fixture


def _fixture_roots(keyer: Keyer, sample_per_10k: int) -> set[str]:
    """URI keys of the roots that normaliser plus selection accept over the whole fixture,
    under the manifest's recorded policy with the given sampling rate."""
    policy = fixture_selection_policy()
    allowlist = frozenset(policy["allowlist_domains"])
    roots: set[str] = set()
    for line in recorded_lines():
        event = normalise(classify_frame(line, "v2"), keyer)
        if not isinstance(event, NormalizedEvent) or event.edge_kind != "root-candidate":
            continue
        decision = sel.seed_decision_for(
            event.seed_candidate(),
            allowlist,
            require_lang=policy["require_lang"],
            sample_per_10k=sample_per_10k,
        )
        if decision.eligible:
            roots.add(event.uri_key)
    return roots


def test_normaliser_plus_selection_reproduce_the_manifest_tracked_roots(keyer):
    """The yield the spike cut is the yield that ships: exactly ``coverage.tracked_roots``."""
    policy = fixture_selection_policy()
    roots = _fixture_roots(keyer, policy["sample_per_10k"])
    assert len(roots) == fixture_manifest()["coverage"]["tracked_roots"]


def test_record_and_candidate_decisions_agree_on_every_fixture_root_candidate(keyer):
    policy = fixture_selection_policy()
    allowlist = frozenset(policy["allowlist_domains"])
    compared = 0
    for line in recorded_lines():
        event = normalise(classify_frame(line, "v2"), keyer)
        if not isinstance(event, NormalizedEvent) or event.edge_kind != "root-candidate":
            continue
        payload = json.loads(line)["payload"]
        raw = f"at://{payload['did']}/{payload['collection']}/{payload['rkey']}"
        kw = {"require_lang": policy["require_lang"], "sample_per_10k": policy["sample_per_10k"]}
        expected = sel.seed_decision(payload["record"], raw, allowlist, **kw)
        assert sel.seed_decision_for(event.seed_candidate(), allowlist, **kw) == expected
        assert event.sample_bucket == sel.sample_bucket(raw)
        compared += 1
    assert compared > 0


def test_a_lower_sampling_rate_replays_a_deterministic_subset(keyer):
    """Replaying under a rate below 10,000 keeps a deterministic subset of the tracked roots.

    That subset is NOT the set the live collector would keep at the same rate: the bucket is a
    hash of the raw at-URI, and the fixture's URIs are scrubbed tokens, so a fixture bucket is
    not the live bucket of the original post. No test claims the two agree. The rate here is a
    test value, not the ratified one.
    """
    everything = _fixture_roots(keyer, fixture_selection_policy()["sample_per_10k"])
    half = _fixture_roots(keyer, 5000)
    assert half == _fixture_roots(keyer, 5000)
    assert half < everything
    assert half
