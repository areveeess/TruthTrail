"""Contract tests for the response envelope and the RFC 9457 problem model."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from truthtrail.schemas.models import AnalyzeResponse, DemoResult, Event, LiveResult, Meta, Problem

RESULT = {
    "headline": "Example Town council statement (synthetic demo)",
    "source": "Example News (synthetic demo)",
    "published_at": "2026-10-03T08:15:00Z",
    "risk": "Low",
    "risk_method": "keyword_baseline",
}
META = {"synthetic": False, "data_as_of": "2026-10-11T10:02:11Z", "source_status": "ok"}
EVENT = {
    "event_id": "e1",
    "platform": "news",
    "content_id": "c1",
    "parent_event_id": None,
    "user_id": "u1",
    "timestamp": "2026-10-03T08:15:00Z",
    "user_influence": 90,
}


def test_event_model_unchanged() -> None:
    assert set(Event.model_fields) == {
        "event_id",
        "platform",
        "content_id",
        "parent_event_id",
        "user_id",
        "timestamp",
        "user_influence",
    }
    assert Event.model_fields["parent_event_id"].is_required()
    with pytest.raises(ValidationError):
        Event(**{k: v for k, v in EVENT.items() if k != "parent_event_id"})
    assert Event(**EVENT).parent_event_id is None


def test_live_result_rejects_events() -> None:
    with pytest.raises(ValidationError):
        LiveResult.model_validate({**RESULT, "events": []})


def test_dict_without_events_validates_as_live_result() -> None:
    response = AnalyzeResponse.model_validate({"results": [RESULT], "meta": META})
    assert isinstance(response.results[0], LiveResult)


def test_live_result_serializes_without_events_key() -> None:
    response = AnalyzeResponse.model_validate({"results": [RESULT], "meta": META})
    dumped = response.model_dump(mode="json")
    assert "events" not in dumped["results"][0]


def test_demo_result_requires_events() -> None:
    with pytest.raises(ValidationError):
        DemoResult.model_validate(RESULT)
    assert DemoResult.model_validate({**RESULT, "events": [EVENT]}).events[0].event_id == "e1"


def test_meta_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        Meta.model_validate({**META, "data_as_of": "2026-10-11T10:02:11"})


def test_meta_serializes_utc_as_z() -> None:
    meta = Meta(
        synthetic=False,
        data_as_of=datetime(2026, 10, 11, 10, 2, 11, tzinfo=UTC),
        source_status="ok",
    )
    assert meta.model_dump(mode="json")["data_as_of"] == "2026-10-11T10:02:11Z"


def test_risk_and_method_are_closed_sets() -> None:
    with pytest.raises(ValidationError):
        LiveResult.model_validate({**RESULT, "risk": "Critical"})
    with pytest.raises(ValidationError):
        LiveResult.model_validate({**RESULT, "risk_method": "ml_model"})


def test_problem_model_shape() -> None:
    body = {
        "type": "about:blank",
        "title": "Bad Gateway",
        "status": 502,
        "detail": "The news provider rejected our credentials.",
        "code": "upstream_unauthorized",
        "upstream": "gnews",
        "synthetic": False,
        "source_status": "upstream_error",
        "data_as_of": None,
    }
    problem = Problem.model_validate(body)
    assert problem.status == 502
    assert problem.errors is None
    with pytest.raises(ValidationError):
        Problem.model_validate({**body, "foo": "bar"})
    with pytest.raises(ValidationError):
        Problem.model_validate({**body, "data_as_of": "2026-10-11T10:02:11Z"})


def test_problem_synthetic_is_literal_false() -> None:
    required = {
        "title": "Bad Gateway",
        "status": 502,
        "detail": "The news provider rejected our credentials.",
        "code": "upstream_unauthorized",
        "source_status": "upstream_error",
    }
    assert Problem.model_validate(required).synthetic is False
    with pytest.raises(ValidationError):
        Problem.model_validate({**required, "synthetic": True})
