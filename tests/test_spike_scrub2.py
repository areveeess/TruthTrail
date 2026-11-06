"""Unit tests for the scrub-2 host-aware URL rule and adult-label drop (plan 03-01 fix round).

Every input here is constructed data with obviously fake names (``alice.example`` and the
reserved ``.test`` / ``.example`` hosts); nothing is recorded data.
"""

import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from spike_lib import scrub  # noqa: E402

from truthtrail.ingest import selection as sel  # noqa: E402

ALLOW = ("example-news.test", "ft.com", "wire.test")
TYPE = "network.bsky.jetstream.subscribeEvents#"


def post_frame(
    rkey: str, urls: list[str], labels: list[str] | None = None, did: str = "did:plc:aaaa"
) -> dict:
    record: dict = {
        "$type": sel.POST_COLLECTION,
        "createdAt": "2026-01-01T00:00:00Z",
        "langs": ["en"],
        "facets": [
            {"features": [{"$type": sel.FACET_LINK, "uri": u}], "index": {}} for u in urls[1:]
        ],
    }
    if urls:
        record["embed"] = {"$type": sel.EMBED_EXTERNAL, "external": {"uri": urls[0]}}
    if labels:
        record["labels"] = {
            "$type": "com.atproto.label.defs#selfLabels",
            "values": [{"val": v} for v in labels],
        }
    return {
        "$type": "message",
        "payload": {
            "$type": TYPE + "commit",
            "collection": sel.POST_COLLECTION,
            "did": did,
            "operation": "create",
            "record": record,
            "rkey": rkey,
            "time": "2026-01-01T00:00:00Z",
        },
    }


def delete_frame(rkey: str, did: str = "did:plc:aaaa") -> dict:
    return {
        "$type": "message",
        "payload": {
            "$type": TYPE + "commit",
            "collection": sel.POST_COLLECTION,
            "did": did,
            "operation": "delete",
            "rkey": rkey,
            "time": "2026-01-01T00:00:01Z",
        },
    }


def test_a_constructed_bluesky_permalink_becomes_a_placeholder():
    state = scrub.Rescrub(allowlist=ALLOW)
    out = state.url("https://bsky.app/profile/alice.example/post/constructedrkey")
    assert out == "https://nonlisted-1.invalid/"
    assert "alice" not in out


def test_a_constructed_substack_at_url_and_personal_hosts_become_placeholders():
    state = scrub.Rescrub(allowlist=ALLOW)
    for url in (
        "https://substack.com/@alice.example/note/constructed",
        "https://alice-example.substack.com/p/constructed",
        "https://alice-example.bsky.social/",
        "https://jetstream.us-east.bsky.network/xrpc/x",
        "https://note.com/alice_example/n/constructed",
        "https://t.me/alice_example",
        "https://x.com/alice_example/status/1",
        "https://www.instagram.com/alice_example/",
        "https://alice-example.bandcamp.com/album/constructed",
        "https://alice-example.blogspot.com/2026/01/constructed.html",
        "https://linktr.ee/alice_example",
        "https://alice.example/about",
    ):
        out = state.url(url)
        assert out.startswith("https://nonlisted-"), url
        assert out.endswith(".invalid/"), url
        assert "alice" not in out


def test_always_replaced_hosts_win_over_the_allowlist():
    state = scrub.Rescrub(allowlist=(*ALLOW, "bsky.app", "substack.com"))
    assert state.url("https://bsky.app/profile/alice.example").endswith(".invalid/")
    assert state.url("https://substack.com/@alice.example").endswith(".invalid/")


def test_placeholders_are_numbered_per_distinct_url_in_first_seen_order():
    state = scrub.Rescrub(allowlist=ALLOW)
    a = state.url("https://alice.example/one")
    b = state.url("https://alice.example/two")
    again = state.url("https://alice.example/one")
    assert (a, b, again) == (
        "https://nonlisted-1.invalid/",
        "https://nonlisted-2.invalid/",
        "https://nonlisted-1.invalid/",
    )


def test_shorteners_keep_the_host_only():
    state = scrub.Rescrub(allowlist=ALLOW)
    assert state.url("https://bit.ly/constructed123") == "https://bit.ly/"
    assert sel.is_shortener("bit.ly")


def test_allowlisted_publisher_paths_stay_but_opaque_ids_are_counters():
    state = scrub.Rescrub(allowlist=ALLOW)
    plain = state.url("https://www.example-news.test/world/2026/jan/01/story-slug")
    assert plain == "https://www.example-news.test/world/2026/jan/01/story-slug"
    ident = str(uuid.UUID(int=12345))
    first = state.url(f"https://example-news.test/a/{ident}/story")
    assert first == "https://example-news.test/a/id0001/story"
    hexrun = "ab" * 12  # 24 hex characters, built at run time
    assert state.url(f"https://wire.test/x-{hexrun}") == "https://wire.test/x-id0002"
    assert state.url(f"https://example-news.test/b/{ident}") == "https://example-news.test/b/id0001"


def test_gift_and_redeem_links_lose_their_path_and_gift_hosts_their_gift_label():
    state = scrub.Rescrub(allowlist=ALLOW)
    assert state.url("https://giftarticle.ft.com/giftarticle/actions/redeem/abc") == (
        "https://ft.com/"
    )
    assert state.url("https://example-news.test/redeem/constructed-token") == (
        "https://example-news.test/"
    )


def test_rescrub_drops_adult_labelled_frames_and_their_deletes():
    frames = [
        post_frame("r1", ["https://example-news.test/story"]),
        post_frame("r2", ["https://alice.example/x"], labels=["porn"]),
        post_frame("r3", [], labels=["nudity"]),
        delete_frame("r2"),
        post_frame("r4", ["https://wire.test/y"], labels=["sexual"]),
    ]
    out, state = scrub.rescrub(frames, ALLOW)
    assert [f["payload"]["rkey"] for f in out] == ["r1"]
    assert state.frames_dropped_adult == 4
    assert not any(scrub.is_adult_labelled(f) for f in out)


def test_rescrub_is_idempotent_and_selection_invariant():
    frames = [
        post_frame("r1", ["https://example-news.test/story", "https://bit.ly/q"]),
        post_frame("r2", ["https://bsky.app/profile/alice.example/post/z"]),
        post_frame("r3", ["https://bit.ly/z"]),
        post_frame("r4", ["https://alice.example/x", "https://wire.test/a/b"]),
    ]
    once, _ = scrub.rescrub(frames, ALLOW)
    twice, _ = scrub.rescrub(once, ALLOW)
    assert once == twice
    for before, after in zip(frames, once, strict=True):
        b = sel.seed_decision(before["payload"]["record"], "at://x", ALLOW)
        a = sel.seed_decision(after["payload"]["record"], "at://x", ALLOW)
        assert (a.eligible, a.reason, a.domain) == (b.eligible, b.reason, b.domain)


def test_coverage_counts_adult_labels_whatever_gate_refused_the_post():
    frames = [
        post_frame("r1", [], labels=["porn"]),  # refused for no_link first
        post_frame("r2", ["https://alice.example/x"], labels=["sexual"]),  # not_allowlisted
        post_frame("r3", ["https://wire.test/x"], labels=["nudity"]),  # adult_label itself
    ]
    cov = scrub.compute_coverage(frames, ALLOW)
    assert cov["negative_controls"]["adult_labelled"] == 3
    assert cov["negative_controls"]["total"] == 3
    assert cov["negative_controls"]["near_miss_non_allowlisted"] == 1
