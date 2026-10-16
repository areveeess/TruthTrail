"""Input validation and the one problem+json shape for 422, 404/405, 500.

Hygiene (T-01-02, T-01-19): no raw request URL, params dict or header dict appears
in an assert expression or message; booleans and single values are computed first.
"""

from http import HTTPStatus

import pytest

PROBLEM = "application/problem+json"
INVALID_QUERIES = [
    pytest.param(None, id="missing"),
    pytest.param("", id="empty"),
    pytest.param("   ", id="whitespace-only"),
    pytest.param("a" * 201, id="201-chars"),
    pytest.param("a\x00b", id="nul"),
    pytest.param("a\nb", id="newline"),
    pytest.param("a\tb", id="tab"),
    pytest.param("a\x7fb", id="del"),
    pytest.param("a\x80b", id="c1-first"),
    pytest.param("a\x85b", id="c1-nel"),
    pytest.param("a\x9fb", id="c1-last"),
    pytest.param("a\u2028b", id="line-separator"),
    pytest.param("a\u2029b", id="paragraph-separator"),
]


def _assert_provenance(body: dict, source_status: str) -> None:
    assert body["type"] == "about:blank"
    assert body["synthetic"] is False
    assert body["source_status"] == source_status
    assert body["data_as_of"] is None


@pytest.mark.parametrize("query", INVALID_QUERIES)
def test_invalid_query_is_422_problem(
    client, mock_gnews, gnews_url, gnews_article, gnews_payload, query
) -> None:
    mock_gnews.get(gnews_url, json=gnews_payload(gnews_article()))
    params = {} if query is None else {"query": query}

    response = client.get("/analyze", params=params)

    body = response.json()
    content_type = response.headers["content-type"]
    upstream_calls = len(mock_gnews.calls)
    error_key_sets = [set(item) for item in body["errors"]]
    assert response.status_code == 422
    assert content_type.startswith(PROBLEM)
    assert body["status"] == 422
    assert body["title"] == HTTPStatus(422).phrase
    assert body["code"] == "invalid_request"
    _assert_provenance(body, "invalid_request")
    assert len(body["errors"]) >= 1
    assert all(keys == {"loc", "msg", "type"} for keys in error_key_sets)
    assert upstream_calls == 0


def test_oversize_query_is_not_echoed(client, mock_gnews) -> None:
    response = client.get("/analyze", params={"query": "a" * 5000})

    body_size = len(response.content)
    echoed = "a" * 10 in response.text
    assert response.status_code == 422
    assert body_size < 1000
    assert not echoed
    assert len(mock_gnews.calls) == 0


@pytest.mark.parametrize(
    ("query", "expected_q"),
    [
        pytest.param("a" * 200, "a" * 200, id="200-ascii"),
        pytest.param("é" * 200, "é" * 200, id="200-unicode"),
        pytest.param(" climate ", "climate", id="trimmed"),
        pytest.param("caf\u00e9\u00a0bar", "caf\u00e9\u00a0bar", id="latin1-letters-and-nbsp"),
        pytest.param("a\u2013b \u201cq\u201d", "a\u2013b \u201cq\u201d", id="typographic-punctuation"),
    ],
)
def test_query_boundaries_accepted(
    client, mock_gnews, gnews_url, gnews_article, gnews_payload, query, expected_q
) -> None:
    mock_gnews.get(gnews_url, json=gnews_payload(gnews_article()))

    response = client.get("/analyze", params={"query": query})

    forwarded_q = mock_gnews.calls[0].request.params.get("q")
    q_matches = forwarded_q == expected_q
    assert response.status_code == 200
    assert q_matches


def test_unknown_path_is_problem_json(client) -> None:
    response = client.get("/nope")

    body = response.json()
    assert response.status_code == 404
    assert response.headers["content-type"].startswith(PROBLEM)
    assert body["status"] == 404
    assert body["title"] == "Not Found"
    assert body["code"] == "http_error"
    _assert_provenance(body, "error")


def test_wrong_method_keeps_allow_header(client) -> None:
    response = client.post("/analyze")

    body = response.json()
    allow = response.headers.get("allow", "")
    assert response.status_code == 405
    assert response.headers["content-type"].startswith(PROBLEM)
    assert "GET" in allow
    assert body["status"] == 405
    assert body["code"] == "http_error"
    _assert_provenance(body, "error")


def test_missing_configuration_is_not_configured(client_factory, mock_gnews) -> None:
    # Not used as a context manager, so the lifespan fail-fast check is bypassed.
    client = client_factory(gnews_api_key=None)

    response = client.get("/analyze", params={"query": "x"})

    body = response.json()
    assert response.status_code == 500
    assert response.headers["content-type"].startswith(PROBLEM)
    assert body["status"] == 500
    assert body["code"] == "not_configured"
    _assert_provenance(body, "not_configured")
    assert len(mock_gnews.calls) == 0


def test_unexpected_error_is_generic_500(
    client, monkeypatch, mock_gnews, gnews_url, gnews_article, gnews_payload
) -> None:
    mock_gnews.get(gnews_url, json=gnews_payload(gnews_article()))

    def boom(text: str) -> str:
        raise RuntimeError("internal-detail-marker")

    monkeypatch.setattr("main.analyze_risk", boom)

    response = client.get("/analyze", params={"query": "x"})

    body = response.json()
    marker_leaked = "internal-detail-marker" in response.text
    assert response.status_code == 500
    assert response.headers["content-type"].startswith(PROBLEM)
    assert body["status"] == 500
    assert body["code"] == "internal_error"
    assert body["detail"] == "Unexpected error."
    _assert_provenance(body, "error")
    assert not marker_leaked
