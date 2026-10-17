"""Provenance envelope on /analyze: live results, empty results, demo fixture gating.

Hygiene (T-01-02): no raw request URL, params dict or header dict appears in an
assert expression or message.
"""

import importlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

PROBLEM = "application/problem+json"
FIXTURE_FILE = Path(__file__).resolve().parent.parent / "fixtures" / "demo_analyze.json"
DATA_AS_OF_FORMAT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _live_response(client, mock_gnews, gnews_url, gnews_payload, gnews_article):
    mock_gnews.get(
        gnews_url,
        json=gnews_payload(
            gnews_article(
                title="Mayor dies after long illness",
                source="Example Wire",
                published_at="2026-10-11T09:30:00Z",
            )
        ),
    )
    return client.get("/analyze", params={"query": "mayor"})


def test_live_result_contract(
    client, mock_gnews, gnews_url, gnews_payload, gnews_article
) -> None:
    response = _live_response(client, mock_gnews, gnews_url, gnews_payload, gnews_article)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"results", "meta"}
    assert body["results"] == [
        {
            "headline": "Mayor dies after long illness",
            "source": "Example Wire",
            "published_at": "2026-10-11T09:30:00Z",
            "risk": "High",
            "risk_method": "keyword_baseline",
        }
    ]
    meta = body["meta"]
    assert meta["synthetic"] is False
    assert meta["source_status"] == "ok"
    assert DATA_AS_OF_FORMAT.match(meta["data_as_of"])
    data_as_of = datetime.strptime(meta["data_as_of"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
    assert abs(datetime.now(timezone.utc) - data_as_of) < timedelta(seconds=60)
    assert "2025-01-01" not in response.text


def test_live_result_has_no_events_key(
    client, mock_gnews, gnews_url, gnews_payload, gnews_article
) -> None:
    response = _live_response(client, mock_gnews, gnews_url, gnews_payload, gnews_article)

    result = response.json()["results"][0]
    assert set(result) == {"headline", "source", "published_at", "risk", "risk_method"}


def test_empty_result_is_honest_200(client, mock_gnews, gnews_url) -> None:
    """D-04: an empty provider answer is an honest empty 200, never a fabricated article."""
    mock_gnews.get(gnews_url, json={"totalArticles": 0, "articles": []})

    response = client.get("/analyze", params={"query": "nothing-here"})

    body = response.json()
    assert response.status_code == 200
    assert body["results"] == []
    assert body["meta"]["synthetic"] is False
    assert body["meta"]["source_status"] == "empty"
    assert DATA_AS_OF_FORMAT.match(body["meta"]["data_as_of"])
    assert "2025-01-01" not in response.text
    assert "unknown" not in response.text


def test_demo_mode_serves_labelled_fixture(client_factory, mock_gnews) -> None:
    client = client_factory(gnews_api_key=None, demo_mode="true")

    with client:
        response = client.get("/analyze", params={"query": "anything"})

    body = response.json()
    committed = json.loads(FIXTURE_FILE.read_text(encoding="utf-8"))
    assert response.status_code == 200
    assert body == committed
    assert body["meta"]["synthetic"] is True
    assert body["meta"]["source_status"] == "fixture"
    assert body["meta"]["data_as_of"] == "2026-10-11T12:00:00Z"
    assert body["results"]
    assert all(result["events"] for result in body["results"])
    assert len(mock_gnews.calls) == 0


def test_demo_mode_still_validates_query(client_factory, mock_gnews) -> None:
    client = client_factory(gnews_api_key=None, demo_mode="true")

    with client:
        response = client.get("/analyze", params={"query": ""})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith(PROBLEM)
    assert len(mock_gnews.calls) == 0


def _upstream_ok(mock_gnews, gnews_url, gnews_payload, gnews_article):
    mock_gnews.get(gnews_url, json=gnews_payload(gnews_article()))


def _upstream_empty(mock_gnews, gnews_url, gnews_payload, gnews_article):
    mock_gnews.get(gnews_url, json={"totalArticles": 0, "articles": []})


def _upstream_401(mock_gnews, gnews_url, gnews_payload, gnews_article):
    mock_gnews.get(gnews_url, json={"errors": ["simulated provider error"]}, status=401)


def _upstream_timeout(mock_gnews, gnews_url, gnews_payload, gnews_article):
    mock_gnews.get(gnews_url, body=requests.exceptions.ConnectTimeout("simulated timeout"))


@pytest.mark.parametrize("demo_mode", [None, "false"], ids=["unset", "false"])
@pytest.mark.parametrize(
    "register",
    [
        pytest.param(_upstream_ok, id="one-article"),
        pytest.param(_upstream_empty, id="empty"),
        pytest.param(_upstream_401, id="401"),
        pytest.param(_upstream_timeout, id="timeout"),
    ],
)
def test_fixture_never_served_when_demo_mode_off(
    client_factory,
    monkeypatch,
    mock_gnews,
    gnews_url,
    gnews_payload,
    gnews_article,
    demo_mode,
    register,
    app_module,
) -> None:
    """T-01-24: with DEMO_MODE unset or false the fixture loader is never reached."""
    calls: list[str] = []

    def stub() -> None:
        calls.append("called")
        raise RuntimeError("fixture loader must not be reached")

    monkeypatch.setattr(f"{app_module}.load_demo_fixture", stub)
    register(mock_gnews, gnews_url, gnews_payload, gnews_article)
    client = client_factory(demo_mode=demo_mode)

    response = client.get("/analyze", params={"query": "anything"})

    body = response.json()
    synthetic = body["meta"]["synthetic"] if "meta" in body else body["synthetic"]
    assert calls == []
    assert synthetic is False


def test_demo_mode_refuses_unlabelled_fixture(
    client_factory, monkeypatch, tmp_path, app_module
) -> None:
    """T-01-27: a fixture that is not labelled synthetic is never served."""
    edited = json.loads(FIXTURE_FILE.read_text(encoding="utf-8"))
    edited["meta"]["synthetic"] = False
    path = tmp_path / "demo_analyze.json"
    path.write_text(json.dumps(edited), encoding="utf-8")
    main = importlib.import_module(app_module)
    monkeypatch.setattr(f"{app_module}.FIXTURE_PATH", path)
    main.load_demo_fixture.cache_clear()
    try:
        client = client_factory(gnews_api_key=None, demo_mode="true")
        response = client.get("/analyze", params={"query": "anything"})
    finally:
        main.load_demo_fixture.cache_clear()

    body = response.json()
    assert response.status_code == 500
    assert response.headers["content-type"].startswith(PROBLEM)
    assert body["code"] == "internal_error"
    assert "results" not in body


def _scenario_live_ok(ctx):
    _upstream_ok(*ctx["mock"])
    return ctx["client"]().get("/analyze", params={"query": "x"})


def _scenario_live_empty(ctx):
    _upstream_empty(*ctx["mock"])
    return ctx["client"]().get("/analyze", params={"query": "x"})


def _scenario_demo(ctx):
    return ctx["client"](gnews_api_key=None, demo_mode="true").get(
        "/analyze", params={"query": "x"}
    )


def _scenario_401(ctx):
    _upstream_401(*ctx["mock"])
    return ctx["client"]().get("/analyze", params={"query": "x"})


def _scenario_429(ctx):
    mock_gnews, gnews_url = ctx["mock"][0], ctx["mock"][1]
    mock_gnews.get(gnews_url, json={"errors": ["simulated"]}, status=429)
    return ctx["client"]().get("/analyze", params={"query": "x"})


def _scenario_timeout(ctx):
    _upstream_timeout(*ctx["mock"])
    return ctx["client"]().get("/analyze", params={"query": "x"})


def _scenario_invalid_query(ctx):
    return ctx["client"]().get("/analyze", params={"query": ""})


def _scenario_unknown_path(ctx):
    return ctx["client"]().get("/nope")


def _scenario_wrong_method(ctx):
    return ctx["client"]().post("/analyze")


def _scenario_missing_configuration(ctx):
    # Not used as a context manager, so the lifespan fail-fast check is bypassed.
    return ctx["client"](gnews_api_key=None).get("/analyze", params={"query": "x"})


@pytest.mark.parametrize(
    ("scenario", "success"),
    [
        pytest.param(_scenario_live_ok, True, id="live-ok"),
        pytest.param(_scenario_live_empty, True, id="live-empty"),
        pytest.param(_scenario_demo, True, id="demo"),
        pytest.param(_scenario_401, False, id="upstream-401"),
        pytest.param(_scenario_429, False, id="upstream-429"),
        pytest.param(_scenario_timeout, False, id="timeout"),
        pytest.param(_scenario_invalid_query, False, id="invalid-query"),
        pytest.param(_scenario_unknown_path, False, id="unknown-path"),
        pytest.param(_scenario_wrong_method, False, id="wrong-method"),
        pytest.param(_scenario_missing_configuration, False, id="missing-configuration"),
    ],
)
def test_every_response_carries_provenance(
    client_factory, mock_gnews, gnews_url, gnews_payload, gnews_article, scenario, success
) -> None:
    """FND-03: synthetic, data_as_of and source_status on every response, success or error."""
    ctx = {
        "client": client_factory,
        "mock": (mock_gnews, gnews_url, gnews_payload, gnews_article),
    }

    response = scenario(ctx)

    body = response.json()
    if success:
        assert response.status_code == 200
        meta = body["meta"]
        assert isinstance(meta["synthetic"], bool)
        assert isinstance(meta["source_status"], str)
        assert DATA_AS_OF_FORMAT.match(meta["data_as_of"])
    else:
        assert response.status_code >= 400
        assert isinstance(body["synthetic"], bool)
        assert isinstance(body["source_status"], str)
        assert "data_as_of" in body
        assert body["data_as_of"] is None
