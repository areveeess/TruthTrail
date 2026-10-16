"""Configuration tests: key only in the header, fail-fast startup, secrets never echoed."""

from typing import Any

import pytest

from config import ConfigurationError


def test_key_sent_only_in_header(
    client: Any, mock_gnews: Any, gnews_url: str, gnews_payload: Any, gnews_article: Any, fake_key: str
) -> None:
    mock_gnews.get(gnews_url, json=gnews_payload(gnews_article()))

    response = client.get("/analyze", params={"query": "x"})

    assert response.status_code == 200
    call = mock_gnews.calls[0]
    header_ok = call.request.headers.get("X-Api-Key") == fake_key
    params_ok = set(call.request.params) == {"q", "lang", "max"}
    assert header_ok, "the key must travel in the X-Api-Key header"
    assert params_ok, "the query string must carry exactly q, lang and max"


def test_missing_key_fails_fast_at_startup(client_factory: Any, mock_gnews: Any) -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        with client_factory(gnews_api_key=None):
            pass

    message = str(excinfo.value)
    assert "GNEWS_API_KEY" in message
    assert "DEMO_MODE" in message
    assert len(mock_gnews.calls) == 0
