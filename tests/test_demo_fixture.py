"""Tests for the committed synthetic demo fixture and its generator."""

import importlib.util
import json
import os
import random
import re
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from types import ModuleType

import pytest

from truthtrail.schemas.models import AnalyzeResponse, DemoResult

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_FILE = REPO_ROOT / "src" / "truthtrail" / "data" / "demo_analyze.json"
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
    from truthtrail.services.keyword_baseline import analyze_risk

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


@pytest.fixture
def generator() -> ModuleType:
    """Load the generator script, skipping if the simulator is gone (Phase 2 deletes it)."""
    pytest.importorskip("spread_simulator")
    path = REPO_ROOT / "scripts" / "generate_demo_fixture.py"
    spec = importlib.util.spec_from_file_location("generate_demo_fixture", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _windows_system_env() -> dict[str, str]:
    """Pass through the variables a Windows child process needs; empty elsewhere."""
    return {k: os.environ[k] for k in ("SYSTEMROOT",) if k in os.environ}


def run_check(*extra: str) -> subprocess.CompletedProcess:
    """Run the generator CLI in check mode from the repository root."""
    return subprocess.run(
        [sys.executable, "scripts/generate_demo_fixture.py", "--check", *extra],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        # SYSTEMROOT is required on Windows: without it asyncio cannot initialise Winsock
        # (WinError 10106).
        env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "", **_windows_system_env()},
    )


def test_build_is_deterministic(generator: ModuleType) -> None:
    assert generator.build_fixture() == generator.build_fixture()


def test_build_restores_global_random_state(generator: ModuleType) -> None:
    random.seed(12345)
    before = random.getstate()
    generator.build_fixture()
    assert random.getstate() == before


def test_build_restores_uuid4(generator: ModuleType) -> None:
    original = uuid.uuid4
    generator.build_fixture()
    assert uuid.uuid4 is original


def test_committed_fixture_matches_generator(generator: ModuleType) -> None:
    completed = run_check()
    assert completed.returncode == 0


def test_check_detects_hand_edit(generator: ModuleType, tmp_path: Path) -> None:
    copy = tmp_path / "demo_analyze.json"
    text = FIXTURE_FILE.read_text(encoding="utf-8")
    assert '"synthetic": true' in text
    copy.write_text(text.replace('"synthetic": true', '"synthetic": false'), encoding="utf-8")
    completed = run_check("--path", str(copy))
    assert completed.returncode == 1
    assert "stale" in completed.stderr


def test_check_fails_on_missing_file(generator: ModuleType, tmp_path: Path) -> None:
    completed = run_check("--path", str(tmp_path / "missing.json"))
    assert completed.returncode == 1
