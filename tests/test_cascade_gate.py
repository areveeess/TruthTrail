"""The cascade invariants gate the demo fixture (D-19, Phase 1 review item IN-02).

``validate_cascade`` is a hard gate when the fixture is loaded: a violating fixture fails
loudly (CascadeError from the loader, a generic 500 on a request, a startup failure when
``DEMO_MODE=true``). ``order_events`` is deliberately NOT applied to the served body: the
committed fixture lists events per platform chain, so sorting it would change the frozen
Phase 1 body.
"""

import ast
import importlib
import json
import logging
import sys
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from truthtrail.core.cascade import (
    CascadeError,
    cascade_events_from,
    order_events,
    validate_cascade,
)
from truthtrail.schemas.models import AnalyzeResponse, DemoResult

PROBLEM = "application/problem+json"
SRC = Path(__file__).resolve().parent.parent / "src" / "truthtrail"
FIXTURE_FILE = SRC / "data" / "demo_analyze.json"
CASCADE_FILE = SRC / "core" / "cascade.py"


def committed_results() -> list[DemoResult]:
    response = AnalyzeResponse.model_validate_json(FIXTURE_FILE.read_text(encoding="utf-8"))
    results = [r for r in response.results if isinstance(r, DemoResult)]
    assert results
    return results


@pytest.fixture
def corrupt_fixture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, app_module: str
) -> Iterator[Path]:
    """Point the loader at a copy whose first child is observed one hour before its parent."""
    data = json.loads(FIXTURE_FILE.read_text(encoding="utf-8"))
    events = data["results"][0]["events"]
    by_id = {e["event_id"]: e for e in events}
    child = next(e for e in events if e["parent_event_id"] in by_id)
    parent_time = datetime.fromisoformat(by_id[child["parent_event_id"]]["timestamp"])
    child["timestamp"] = (parent_time - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = tmp_path / "demo_analyze.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    module = importlib.import_module(app_module)
    monkeypatch.setattr(f"{app_module}.FIXTURE_PATH", path)
    module.load_demo_fixture.cache_clear()
    try:
        yield path
    finally:
        module.load_demo_fixture.cache_clear()


def test_every_committed_cascade_passes_validate_cascade() -> None:
    for result in committed_results():
        validate_cascade(cascade_events_from(result.events))


def test_served_demo_body_keeps_the_committed_event_order(
    client_factory: Callable[..., Any],
) -> None:
    committed = json.loads(FIXTURE_FILE.read_text(encoding="utf-8"))

    response = client_factory(demo_mode="true").get("/analyze", params={"query": "anything"})

    assert response.status_code == 200
    body = response.json()
    assert body == committed
    served_ids = [[e["event_id"] for e in r["events"]] for r in body["results"]]
    committed_ids = [[e["event_id"] for e in r["events"]] for r in committed["results"]]
    assert served_ids == committed_ids


def test_sorting_the_committed_fixture_would_change_at_least_one_cascade() -> None:
    """Why the gate validates and does not reorder: sorting would break the frozen body."""
    differing = 0
    for result in committed_results():
        committed_ids = [e.event_id for e in result.events]
        sorted_ids = [e.event_id for e in order_events(cascade_events_from(result.events))]
        assert sorted(sorted_ids) == sorted(committed_ids)
        differing += sorted_ids != committed_ids

    assert differing >= 1


def test_loader_raises_cascade_error_for_a_violating_fixture(corrupt_fixture: Path) -> None:
    module = importlib.import_module("truthtrail.api.analyze")

    with pytest.raises(CascadeError):
        module.load_demo_fixture()


def test_request_gets_the_generic_500_for_a_violating_fixture(
    corrupt_fixture: Path,
    client_factory: Callable[..., Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    committed_event_ids = [e.event_id for r in committed_results() for e in r.events]

    with caplog.at_level(logging.ERROR):
        response = client_factory(demo_mode="true").get("/analyze", params={"query": "anything"})

    body = response.json()
    assert response.status_code == 500
    assert response.headers["content-type"].startswith(PROBLEM)
    assert body["code"] == "internal_error"
    assert "results" not in body
    assert not any(event_id in response.text for event_id in committed_event_ids)
    assert "CascadeError" in caplog.text


def test_demo_mode_startup_fails_for_a_violating_fixture(
    corrupt_fixture: Path, client_factory: Callable[..., Any]
) -> None:
    client = client_factory(demo_mode="true")

    with pytest.raises(CascadeError), client:
        pass


def test_lifespan_loads_the_fixture_only_in_demo_mode(
    monkeypatch: pytest.MonkeyPatch,
    client_factory: Callable[..., Any],
    app_module: str,
) -> None:
    calls: list[str] = []
    real = importlib.import_module(app_module).load_demo_fixture

    def recording_loader() -> AnalyzeResponse:
        calls.append("load")
        return real()

    monkeypatch.setattr(f"{app_module}.load_demo_fixture", recording_loader)

    with client_factory(demo_mode="false"):
        pass
    assert calls == []

    with client_factory(demo_mode="true"):
        pass
    assert calls == ["load"]


def test_cascade_module_imports_only_the_standard_library() -> None:
    tree = ast.parse(CASCADE_FILE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative imports are not allowed in core/cascade.py"
            assert node.module is not None
            imported.add(node.module.split(".")[0])

    assert imported
    assert imported <= set(sys.stdlib_module_names)
