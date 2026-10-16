"""Legacy pre-envelope characterization of GET /analyze.

Deliberately replaced by contract tests when the response envelope (D-01) lands
in plan 01-05. Any row whose defect a later plan fixes loses its xfail marker in
that plan's commit. Rows marked xfail assert the DESIRED behaviour.

Hygiene (T-01-02): no raw request URL, params dict or header dict appears in an
assert expression or message; booleans and single values are computed first.
"""

import pytest
import requests

DEFECT = pytest.mark.xfail(strict=True, raises=AssertionError)


def _register(mock_gnews, gnews_url, gnews_payload, gnews_article, **article_kwargs):
    mock_gnews.get(gnews_url, json=gnews_payload(gnews_article(**article_kwargs)))


def test_legacy_single_article_shape(
    client, mock_gnews, gnews_url, gnews_payload, gnews_article
) -> None:
    _register(
        mock_gnews,
        gnews_url,
        gnews_payload,
        gnews_article,
        title="Mayor dies after long illness",
        source="Example Wire",
        published_at="2026-10-11T09:30:00Z",
    )

    response = client.get("/analyze", params={"query": "mayor"})

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    item = body[0]
    assert set(item) == {"headline", "risk", "events"}
    assert item["headline"] == "Mayor dies after long illness"
    assert item["risk"] == "High"
    assert len(item["events"]) == 19
    root = item["events"][0]
    assert root["parent_event_id"] is None
    assert root["user_id"] == "Example Wire"
    assert root["timestamp"] == "2026-10-11T09:30:00Z"


def test_legacy_medium_article_has_10_events(
    client, mock_gnews, gnews_url, gnews_payload, gnews_article
) -> None:
    _register(
        mock_gnews, gnews_url, gnews_payload, gnews_article, title="Local bakery wins award"
    )

    response = client.get("/analyze", params={"query": "bakery"})

    assert response.status_code == 200
    item = response.json()[0]
    assert item["risk"] == "Medium"
    assert len(item["events"]) == 10


def test_legacy_forwards_query_params(
    client, mock_gnews, gnews_url, gnews_payload, gnews_article
) -> None:
    _register(mock_gnews, gnews_url, gnews_payload, gnews_article)

    client.get("/analyze", params={"query": "climate"})

    params = mock_gnews.calls[0].request.params
    q = params.get("q")
    lang = params.get("lang")
    max_articles = params.get("max")
    assert q == "climate"
    assert lang == "en"
    assert max_articles == "1"


@DEFECT
def test_empty_result_is_not_fabricated(client, mock_gnews, gnews_url) -> None:
    """D-04: an empty upstream result must not become a fabricated article."""
    mock_gnews.get(gnews_url, json={"totalArticles": 0, "articles": []})

    response = client.get("/analyze", params={"query": "nothing-here"})

    body = response.json()
    items = body if isinstance(body, list) else body.get("results", [])
    has_fabricated_date = "2025-01-01T10:00:00Z" in response.text
    has_unknown_user = any(
        event.get("user_id") == "unknown"
        for item in items
        for event in item.get("events", [])
    )
    assert not has_fabricated_date
    assert not has_unknown_user


@pytest.mark.parametrize(
    ("upstream_status", "expected"),
    [
        pytest.param(401, 502, id="401"),
        pytest.param(403, 502, id="403"),
        pytest.param(429, 503, id="429"),
    ],
)
def test_upstream_status_is_honest(
    client, mock_gnews, gnews_url, upstream_status: int, expected: int
) -> None:
    """D-07: an upstream error must not be answered with a fabricated 200."""
    mock_gnews.get(
        gnews_url, json={"errors": ["simulated provider error"]}, status=upstream_status
    )

    response = client.get("/analyze", params={"query": "anything"})

    assert response.status_code == expected


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        pytest.param("server_error", 502, id="http-500-html"),
        pytest.param("not_json", 502, id="200-not-json"),
        pytest.param("null_title", 502, id="null-title"),
        pytest.param("timeout", 503, id="connect-timeout"),
    ],
)
def test_malformed_or_failed_upstream_is_honest(
    client,
    mock_gnews,
    gnews_url,
    gnews_payload,
    gnews_article,
    scenario: str,
    expected: int,
) -> None:
    """An unhandled upstream failure must not surface as a plain 500."""
    if scenario == "server_error":
        mock_gnews.get(gnews_url, status=500, body="oops")
    elif scenario == "not_json":
        mock_gnews.get(gnews_url, status=200, body="<html>not json</html>")
    elif scenario == "null_title":
        mock_gnews.get(gnews_url, json=gnews_payload(gnews_article(title=None)))
    else:
        mock_gnews.get(gnews_url, body=requests.exceptions.ConnectTimeout("simulated timeout"))

    response = client.get("/analyze", params={"query": "anything"})

    assert response.status_code == expected


def test_empty_query_is_rejected(
    client, mock_gnews, gnews_url, gnews_payload, gnews_article
) -> None:
    """FND-04: an empty query must be rejected with 422, not forwarded upstream."""
    _register(mock_gnews, gnews_url, gnews_payload, gnews_article)

    response = client.get("/analyze", params={"query": ""})

    assert response.status_code == 422
