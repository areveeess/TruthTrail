"""Tests for the committed synthetic demo fixture and its generator."""

import json
import re
from datetime import datetime
from pathlib import Path

from models import AnalyzeResponse, DemoResult

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_FILE = REPO_ROOT / "fixtures" / "demo_analyze.json"
UTC_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def load_fixture() -> AnalyzeResponse:
    """Validate the committed fixture file through the response envelope."""
    return AnalyzeResponse.model_validate_json(FIXTURE_FILE.read_text(encoding="utf-8"))


def test_fixture_validates_and_is_labelled_synthetic() -> None:
    response = load_fixture()
    assert response.meta.synthetic is True
    assert response.meta.source_status == "fixture"
    assert response.results
    for result in response.results:
        assert isinstance(result, DemoResult)
        assert len(result.events) >= 1
        assert result.risk_method == "keyword_baseline"


def test_fixture_covers_each_risk_label() -> None:
    response = load_fixture()
    assert sorted(r.risk for r in response.results) == ["High", "Low", "Medium"]


def test_fixture_risk_matches_keyword_baseline() -> None:
    from risk_analyzer import analyze_risk

    for result in load_fixture().results:
        assert result.risk == analyze_risk(result.headline)


def test_fixture_is_visibly_synthetic() -> None:
    for result in load_fixture().results:
        assert "synthetic" in result.headline.lower()
        assert "synthetic" in result.source.lower()


def test_fixture_data_as_of_is_constant() -> None:
    raw = json.loads(FIXTURE_FILE.read_text(encoding="utf-8"))
    assert raw["meta"]["data_as_of"] == "2026-10-11T12:00:00Z"


def test_fixture_event_counts() -> None:
    expected = {"High": 19, "Medium": 10, "Low": 10}
    for result in load_fixture().results:
        assert len(result.events) == expected[result.risk]


def test_fixture_linkage() -> None:
    all_ids: list[str] = []
    for result in load_fixture().results:
        root = result.events[0]
        assert root.platform == "news"
        assert root.parent_event_id is None
        seen: set[str] = set()
        for event in result.events:
            if event is not root:
                assert event.parent_event_id in seen
            seen.add(event.event_id)
        all_ids.extend(event.event_id for event in result.events)
    assert len(all_ids) == len(set(all_ids))


def test_fixture_child_never_before_parent() -> None:
    for result in load_fixture().results:
        times = {e.event_id: datetime.fromisoformat(e.timestamp) for e in result.events}
        for event in result.events[1:]:
            assert times[event.event_id] >= times[event.parent_event_id]


def test_fixture_timestamps_are_utc_z() -> None:
    for result in load_fixture().results:
        for event in result.events:
            assert UTC_Z.match(event.timestamp)
