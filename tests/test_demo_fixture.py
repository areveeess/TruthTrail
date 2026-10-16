"""Tests for the committed synthetic demo fixture and its generator."""

from pathlib import Path

from models import AnalyzeResponse, DemoResult

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_FILE = REPO_ROOT / "fixtures" / "demo_analyze.json"


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
