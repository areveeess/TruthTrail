"""Characterization of spread_simulator (synthetic propagation events).

Assertions are structural: uuid4 ignores random.seed, so event_id values are
never compared. Known timestamp defects are strict xfails asserting the
desired behaviour.
"""

import uuid
from datetime import datetime

import pytest

import models
from spread_simulator import create_root_event, simulate_spread
from users import USERS

ARTICLE = {
    "title": "Example headline",
    "source": "Example Wire",
    "publishedAt": "2026-10-11T09:30:00Z",
}


def _run(risk: str = "High") -> list[dict]:
    return simulate_spread(create_root_event(ARTICLE), risk)


def _children(events: list[dict], platform: str) -> list[dict]:
    return [e for e in events if e["platform"] == platform]


def test_root_event_shape() -> None:
    root = create_root_event(ARTICLE)

    assert set(root) == set(models.Event.model_fields)
    assert root["platform"] == "news"
    assert root["parent_event_id"] is None
    assert root["content_id"] == "Example headline"
    assert root["user_id"] == "Example Wire"
    assert root["timestamp"] == "2026-10-11T09:30:00Z"
    assert root["user_influence"] == 90
    uuid.UUID(root["event_id"])


@pytest.mark.parametrize(("risk", "count"), [("High", 19), ("Medium", 10), ("Low", 10)])
def test_event_counts(risk: str, count: int) -> None:
    assert len(_run(risk)) == count


def test_chain_linkage() -> None:
    events = _run("High")
    root = events[0]

    assert root["platform"] == "news"
    assert len({e["event_id"] for e in events}) == len(events)
    for platform in USERS:
        chain = _children(events, platform)
        assert len(chain) == 6
        assert chain[0]["parent_event_id"] == root["event_id"]
        for previous, current in zip(chain, chain[1:]):
            assert current["parent_event_id"] == previous["event_id"]
        assert all(e["content_id"] == root["content_id"] for e in chain)


def test_users_from_pool() -> None:
    events = _run("High")

    for platform, pool in USERS.items():
        influence_by_id = {u["id"]: u["influence"] for u in pool}
        for event in _children(events, platform):
            assert event["user_id"] in influence_by_id
            assert event["user_influence"] == influence_by_id[event["user_id"]]


def test_child_offsets_within_window() -> None:
    events = _run("High")
    root_time = datetime.fromisoformat(events[0]["timestamp"].replace("Z", ""))

    for event in events[1:]:
        offset = datetime.fromisoformat(event["timestamp"]) - root_time
        assert 5 * 60 <= offset.total_seconds() <= 60 * 60


def test_non_id_fields_deterministic_under_seed(seeded_random) -> None:
    def snapshot() -> list[tuple]:
        return [
            (e["platform"], e["user_id"], e["timestamp"], e["user_influence"], e["content_id"])
            for e in _run("High")
        ]

    seeded_random(7)
    first = snapshot()
    seeded_random(7)
    second = snapshot()

    assert first == second


def test_events_validate_as_event_model() -> None:
    for event in _run("High"):
        models.Event(**event)


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="children are offset from the root, not from their parent; about 41% of links precede their parent",
)
def test_child_never_before_parent(seeded_random) -> None:
    def parsed(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", ""))

    for seed in range(20):
        seeded_random(seed)
        events = _run("High")
        by_id = {e["event_id"]: e for e in events}
        for event in events[1:]:
            parent = by_id[event["parent_event_id"]]
            assert parsed(event["timestamp"]) >= parsed(parent["timestamp"])


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="root keeps the upstream Z form, children are naive isoformat strings",
)
def test_timestamps_share_one_utc_format() -> None:
    assert all(e["timestamp"].endswith("Z") for e in _run("High"))
