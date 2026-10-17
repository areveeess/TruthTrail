"""Self-tests for the autouse network guard and env scrub, plus the tracer call."""

import os

import pytest
import requests
from conftest import ENV_NAMES


def test_unmocked_request_is_blocked() -> None:
    with pytest.raises(requests.exceptions.ConnectionError):
        requests.get("https://example.org", timeout=1)


def test_env_is_scrubbed() -> None:
    leaked = [name for name in ENV_NAMES if name in os.environ]
    assert leaked == []


def test_mocked_gnews_reaches_real_handler(
    client, mock_gnews, gnews_url, gnews_payload, gnews_article, fake_key
) -> None:
    mock_gnews.get(gnews_url, json=gnews_payload(gnews_article()))

    response = client.get("/analyze", params={"query": "bakery"})

    assert response.status_code == 200
    assert len(mock_gnews.calls) == 1
    call = mock_gnews.calls[0]
    carries_fake = fake_key in call.request.url or call.request.headers.get("X-Api-Key") == fake_key
    assert carries_fake, "outbound request must carry only the fake test key"
