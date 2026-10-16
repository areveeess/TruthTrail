"""Upstream failures become honest problem+json answers, never a fabricated 200.

Hygiene (T-01-02, T-01-18): no raw request URL, params dict or header dict appears
in an assert expression or message; booleans and single values are computed first.
"""

import logging

import pytest

import gnews_fetcher
from problems import UpstreamError


def test_gnews_401_returns_502_not_200(
    client, mock_gnews, gnews_url, fake_key, caplog
) -> None:
    """D-07 / ROADMAP success criterion 2: a GNews 401 is a 502, never a 200."""
    caplog.set_level(logging.DEBUG)
    mock_gnews.get(
        gnews_url, json={"errors": ["Invalid credentials (simulated)"]}, status=401
    )

    response = client.get("/analyze", params={"query": "x"})

    body = response.json()
    content_type = response.headers["content-type"]
    key_in_body = fake_key in response.text
    host_in_body = "gnews.io" in response.text
    key_in_logs = fake_key in caplog.text
    assert response.status_code == 502
    assert content_type.startswith("application/problem+json")
    assert body["type"] == "about:blank"
    assert body["title"] == "Bad Gateway"
    assert body["status"] == 502
    assert body["code"] == "upstream_unauthorized"
    assert body["upstream"] == "gnews"
    assert body["synthetic"] is False
    assert body["source_status"] == "upstream_error"
    assert body["data_as_of"] is None
    assert "results" not in body
    assert not key_in_body
    assert not host_in_body
    assert not key_in_logs


def test_adapter_error_carries_no_key_or_url(mock_gnews, gnews_url, fake_key) -> None:
    mock_gnews.get(gnews_url, json={"errors": ["simulated"]}, status=401)

    with pytest.raises(UpstreamError) as excinfo:
        gnews_fetcher.fetch_news("x", fake_key)

    exc = excinfo.value
    text = f"{exc!s} {exc!r}"
    key_leaked = fake_key in text
    host_leaked = "gnews.io" in text
    assert exc.status == 502
    assert exc.__cause__ is None
    assert exc.__suppress_context__ is True
    assert not key_leaked
    assert not host_leaked
