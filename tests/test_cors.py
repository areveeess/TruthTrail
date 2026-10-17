"""CORS accepts only configured origins, and error responses stay readable (D-09, IN-02).

Unset ``CORS_ORIGINS`` means no cross-origin access. The catch-all sits just inside
``CORSMiddleware`` so a 500, 404 or 422 for an allowed origin still carries the
Access-Control-Allow-Origin and Vary headers a browser frontend needs to read it.
"""

import logging
from collections.abc import Callable
from typing import Any

import pytest

from truthtrail.core.config import ConfigurationError

ALLOWED = "http://localhost:5173"
OTHER = "https://evil.example"
PROBLEM = "application/problem+json"


def _mock_ok(mock_gnews: Any, gnews_url: str, gnews_payload: Any, gnews_article: Any) -> None:
    mock_gnews.get(gnews_url, json=gnews_payload(gnews_article()))


def test_allowed_origin_gets_acao_and_vary(
    client_factory: Callable[..., Any], mock_gnews, gnews_url, gnews_payload, gnews_article
) -> None:
    _mock_ok(mock_gnews, gnews_url, gnews_payload, gnews_article)
    client = client_factory(env={"CORS_ORIGINS": ALLOWED})

    response = client.get("/analyze", params={"query": "x"}, headers={"Origin": ALLOWED})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert "origin" in response.headers["vary"].lower()
    assert "access-control-allow-credentials" not in response.headers


def test_unlisted_origin_gets_no_acao(
    client_factory: Callable[..., Any], mock_gnews, gnews_url, gnews_payload, gnews_article
) -> None:
    _mock_ok(mock_gnews, gnews_url, gnews_payload, gnews_article)
    client = client_factory(env={"CORS_ORIGINS": ALLOWED})

    response = client.get("/analyze", params={"query": "x"}, headers={"Origin": OTHER})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("env", [{}, {"CORS_ORIGINS": ""}, {"CORS_ORIGINS": " , "}])
def test_unset_or_empty_means_no_cross_origin_access(
    env: dict[str, str],
    client_factory: Callable[..., Any],
    mock_gnews,
    gnews_url,
    gnews_payload,
    gnews_article,
) -> None:
    _mock_ok(mock_gnews, gnews_url, gnews_payload, gnews_article)
    client = client_factory(env=env)

    for origin in (ALLOWED, OTHER, "null"):
        response = client.get("/analyze", params={"query": "x"}, headers={"Origin": origin})
        assert response.status_code == 200
        assert "access-control-allow-origin" not in response.headers


def test_comma_list_with_spaces_allows_each_entry(
    client_factory: Callable[..., Any], mock_gnews, gnews_url, gnews_payload, gnews_article
) -> None:
    _mock_ok(mock_gnews, gnews_url, gnews_payload, gnews_article)
    second = "https://app.example.org:8443"
    client = client_factory(env={"CORS_ORIGINS": f" {ALLOWED} ,{second}, "})

    for origin in (ALLOWED, second):
        response = client.get("/analyze", params={"query": "x"}, headers={"Origin": origin})
        assert response.headers["access-control-allow-origin"] == origin
    denied = client.get("/analyze", params={"query": "x"}, headers={"Origin": OTHER})
    assert "access-control-allow-origin" not in denied.headers


def test_preflight_for_allowed_origin_names_get_only(client_factory: Callable[..., Any]) -> None:
    client = client_factory(env={"CORS_ORIGINS": ALLOWED})

    response = client.options(
        "/analyze",
        headers={"Origin": ALLOWED, "Access-Control-Request-Method": "GET"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED
    methods = {m.strip() for m in response.headers["access-control-allow-methods"].split(",")}
    assert "GET" in methods
    assert "POST" not in methods
    assert "access-control-allow-credentials" not in response.headers


def test_preflight_for_post_is_rejected(client_factory: Callable[..., Any]) -> None:
    client = client_factory(env={"CORS_ORIGINS": ALLOWED})

    response = client.options(
        "/analyze",
        headers={"Origin": ALLOWED, "Access-Control-Request-Method": "POST"},
    )

    # Known limitation: CORSMiddleware answers a disallowed preflight as plain text, not
    # problem+json. For a listed origin it still echoes ACAO on this 400 (Starlette 1.8.0),
    # but the allowed-methods header omits POST, so a browser refuses the real request.
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("text/plain")
    methods = {m.strip() for m in response.headers["access-control-allow-methods"].split(",")}
    assert "POST" not in methods


def test_preflight_for_unlisted_origin_is_rejected(client_factory: Callable[..., Any]) -> None:
    client = client_factory(env={"CORS_ORIGINS": ALLOWED})

    response = client.options(
        "/analyze",
        headers={"Origin": OTHER, "Access-Control-Request-Method": "GET"},
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_404_for_allowed_origin_carries_acao(client_factory: Callable[..., Any]) -> None:
    client = client_factory(env={"CORS_ORIGINS": ALLOWED})

    response = client.get("/no-such-route", headers={"Origin": ALLOWED})

    assert response.status_code == 404
    assert response.headers["content-type"].startswith(PROBLEM)
    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert "origin" in response.headers["vary"].lower()


def test_422_for_allowed_origin_carries_acao(client_factory: Callable[..., Any]) -> None:
    client = client_factory(env={"CORS_ORIGINS": ALLOWED})

    response = client.get("/analyze", headers={"Origin": ALLOWED})  # query is required

    assert response.status_code == 422
    assert response.headers["content-type"].startswith(PROBLEM)
    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert "origin" in response.headers["vary"].lower()


def test_500_for_allowed_origin_is_problem_json_with_cors_headers(
    client_factory: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    mock_gnews,
    gnews_url,
    gnews_payload,
    gnews_article,
    app_module,
) -> None:
    _mock_ok(mock_gnews, gnews_url, gnews_payload, gnews_article)

    def boom(text: str) -> str:
        raise RuntimeError("internal-detail-marker")

    monkeypatch.setattr(f"{app_module}.analyze_risk", boom)
    client = client_factory(env={"CORS_ORIGINS": ALLOWED}, raise_server_exceptions=False)

    with caplog.at_level(logging.DEBUG):
        response = client.get("/analyze", params={"query": "x"}, headers={"Origin": ALLOWED})

    body = response.json()
    assert response.status_code == 500
    assert response.headers["content-type"].startswith(PROBLEM)
    assert body["code"] == "internal_error"
    assert body["detail"] == "Unexpected error."
    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert "origin" in response.headers["vary"].lower()
    # Only the class name is logged; the exception message never reaches body or log.
    assert "RuntimeError" in caplog.text
    assert "internal-detail-marker" not in response.text
    assert "internal-detail-marker" not in caplog.text


def test_500_for_unlisted_origin_carries_no_acao(
    client_factory: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    mock_gnews,
    gnews_url,
    gnews_payload,
    gnews_article,
    app_module,
) -> None:
    _mock_ok(mock_gnews, gnews_url, gnews_payload, gnews_article)
    monkeypatch.setattr(f"{app_module}.analyze_risk", lambda text: 1 / 0)
    client = client_factory(env={"CORS_ORIGINS": ALLOWED}, raise_server_exceptions=False)

    response = client.get("/analyze", params={"query": "x"}, headers={"Origin": OTHER})

    assert response.status_code == 500
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize(
    "bad",
    [
        "*",
        "http://localhost:5173/",
        "localhost:5173",
        "ftp://files.example.org",
        "https://app.example.org/path",
        "https://user@app.example.org",
        "https://*.example.org",
        "https://app.example.org?x=1",
        "http://localhost:notaport",
    ],
)
def test_invalid_origin_fails_construction_without_echoing_the_value(
    bad: str, client_factory: Callable[..., Any]
) -> None:
    with pytest.raises(ConfigurationError) as info:
        client_factory(env={"CORS_ORIGINS": f"{ALLOWED},{bad}"})

    message = str(info.value)
    assert "CORS_ORIGINS" in message
    assert bad not in message
    assert info.value.__cause__ is None
    assert info.value.__suppress_context__ is True
