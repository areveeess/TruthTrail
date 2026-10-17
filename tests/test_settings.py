"""Configuration tests: key only in the header, fail-fast startup, secrets never echoed."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from truthtrail.core.config import ConfigurationError, get_settings

# Low-entropy marker values: they must never appear in any error, repr or output.
DATABASE_URL_MARKER = "postgresql://user:not-a-real-password@localhost:5432/truthtrail"
APP_PASSWORD_MARKER = "not-a-real-app-password"


def test_key_sent_only_in_header(
    client: Any,
    mock_gnews: Any,
    gnews_url: str,
    gnews_payload: Any,
    gnews_article: Any,
    fake_key: str,
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
    with pytest.raises(ConfigurationError) as excinfo, client_factory(gnews_api_key=None):
        pass

    message = str(excinfo.value)
    assert "GNEWS_API_KEY" in message
    assert "DEMO_MODE" in message
    assert len(mock_gnews.calls) == 0


def test_demo_mode_starts_without_key(client_factory: Any, mock_gnews: Any) -> None:
    with client_factory(gnews_api_key=None, demo_mode="true"):
        pass

    assert len(mock_gnews.calls) == 0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("0", False),
        ("no", False),
    ],
)
def test_demo_mode_parsing(
    monkeypatch: pytest.MonkeyPatch, fake_key: str, raw: str, expected: bool
) -> None:
    monkeypatch.setenv("GNEWS_API_KEY", fake_key)
    monkeypatch.setenv("DEMO_MODE", raw)
    get_settings.cache_clear()

    assert get_settings().demo_mode is expected


def test_invalid_demo_mode_fails_startup(monkeypatch: pytest.MonkeyPatch, fake_key: str) -> None:
    monkeypatch.setenv("GNEWS_API_KEY", fake_key)
    monkeypatch.setenv("DEMO_MODE", "maybe")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError) as excinfo:
        get_settings()

    assert "demo_mode" in str(excinfo.value)


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_key_is_missing(monkeypatch: pytest.MonkeyPatch, blank: str) -> None:
    monkeypatch.setenv("GNEWS_API_KEY", blank)
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError) as excinfo:
        get_settings()

    assert "GNEWS_API_KEY" in str(excinfo.value)


def test_startup_error_never_echoes_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL_MARKER)
    monkeypatch.setenv("BLUESKY_APP_PASSWORD", APP_PASSWORD_MARKER)
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError) as excinfo:
        get_settings()

    message = str(excinfo.value)
    leaked = [m for m in (DATABASE_URL_MARKER, APP_PASSWORD_MARKER, "not-a-real") if m in message]
    assert leaked == []
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__ is True


def test_settings_repr_masks_secrets(monkeypatch: pytest.MonkeyPatch, fake_key: str) -> None:
    monkeypatch.setenv("GNEWS_API_KEY", fake_key)
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL_MARKER)
    monkeypatch.setenv("BLUESKY_APP_PASSWORD", APP_PASSWORD_MARKER)
    get_settings.cache_clear()

    text = repr(get_settings())

    leaked = [v for v in (fake_key, DATABASE_URL_MARKER, APP_PASSWORD_MARKER) if v in text]
    assert leaked == []
    assert "SecretStr('**********')" in text


def test_uvicorn_exits_on_missing_key(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": os.pathsep.join([str(repo_root), str(repo_root / "src")]),
        "PYTHONDONTWRITEBYTECODE": "1",
        "DATABASE_URL": DATABASE_URL_MARKER,
    }
    # SYSTEMROOT is required on Windows: without it asyncio cannot initialise Winsock
    # (WinError 10106).
    if "SYSTEMROOT" in os.environ:
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]

    result = subprocess.run(
        [sys.executable, "-m", "uvicorn", "main:app", "--port", "0"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 3
    assert "GNEWS_API_KEY" in output
    assert "Application startup failed" in output
    assert "not-a-real" not in output


# Surrounding whitespace (a pasted newline or space) is trimmed by Settings (owner decision,
# UAT test 3).
TRIMMABLE_KEYS = [
    pytest.param("FAKE_TEST_KEY\n", id="trailing-newline"),
    pytest.param("FAKE_TEST_KEY\r\n", id="trailing-crlf"),
    pytest.param(" FAKE_TEST_KEY", id="leading-space"),
    pytest.param("FAKE_TEST_KEY ", id="trailing-space"),
    pytest.param("\tFAKE_TEST_KEY\t", id="surrounding-tabs"),
]

# Whitespace inside the key, an embedded control character, and non-ASCII text
# (non-latin-1 and latin-1 alike) can never be a header value, even after trimming.
BAD_KEYS = [
    pytest.param("FAKE_TEST\nKEY", id="embedded-newline"),
    pytest.param("FAKE\tTEST", id="embedded-tab"),
    pytest.param("FAKE TEST", id="embedded-space"),
    pytest.param("FAKE_TEST_KEY✓", id="non-latin-1"),
    pytest.param("FAKE_TEST_KEYé", id="latin-1-non-ascii"),
]


@pytest.mark.parametrize("bad_key", BAD_KEYS)
def test_malformed_key_is_rejected_at_configuration_time(
    monkeypatch: pytest.MonkeyPatch, mock_gnews: Any, bad_key: str
) -> None:
    monkeypatch.setenv("GNEWS_API_KEY", bad_key)
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError) as excinfo:
        get_settings()

    message = str(excinfo.value)
    leaked = bad_key.strip() in message or bad_key in message
    assert "GNEWS_API_KEY" in message
    assert not leaked
    assert excinfo.value.__cause__ is None
    assert len(mock_gnews.calls) == 0


@pytest.mark.parametrize("bad_key", BAD_KEYS)
def test_malformed_key_fails_startup_without_calling_the_provider(
    client_factory: Any, mock_gnews: Any, bad_key: str
) -> None:
    with pytest.raises(ConfigurationError) as excinfo, client_factory(gnews_api_key=bad_key):
        pass

    leaked = "FAKE_TEST" in str(excinfo.value)
    assert not leaked
    assert len(mock_gnews.calls) == 0


@pytest.mark.parametrize("bad_key", BAD_KEYS)
def test_malformed_key_without_lifespan_is_500_not_configured(
    client_factory: Any, mock_gnews: Any, gnews_url: str, gnews_payload: Any, bad_key: str
) -> None:
    """With the lifespan bypassed, the request answers not_configured and skips the provider."""
    mock_gnews.get(gnews_url, json=gnews_payload())
    client = client_factory(gnews_api_key=bad_key)

    response = client.get("/analyze", params={"query": "x"})

    body = response.json()
    leaked = "FAKE_TEST" in response.text
    assert response.status_code == 500
    assert body["code"] == "not_configured"
    assert body["source_status"] == "not_configured"
    assert not leaked
    assert len(mock_gnews.calls) == 0


@pytest.mark.parametrize("bad_key", [*TRIMMABLE_KEYS, *BAD_KEYS])
def test_fetcher_never_sends_a_malformed_key(
    mock_gnews: Any, gnews_url: str, gnews_payload: Any, bad_key: str
) -> None:
    from truthtrail.services import gnews as gnews_fetcher

    mock_gnews.get(gnews_url, json=gnews_payload())

    with pytest.raises(ConfigurationError) as excinfo:
        gnews_fetcher.fetch_news("x", bad_key)

    leaked = "FAKE_TEST" in str(excinfo.value)
    assert not leaked
    assert len(mock_gnews.calls) == 0


@pytest.mark.parametrize("padded_key", TRIMMABLE_KEYS)
def test_surrounding_whitespace_is_trimmed(
    monkeypatch: pytest.MonkeyPatch, padded_key: str
) -> None:
    monkeypatch.setenv("GNEWS_API_KEY", padded_key)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.gnews_api_key is not None
    assert settings.gnews_api_key.get_secret_value() == "FAKE_TEST_KEY"


@pytest.mark.parametrize("padded_key", TRIMMABLE_KEYS)
def test_trimmed_key_reaches_the_provider_exactly(
    client_factory: Any, mock_gnews: Any, gnews_url: str, gnews_payload: Any, padded_key: str
) -> None:
    mock_gnews.get(gnews_url, json=gnews_payload())

    with client_factory(gnews_api_key=padded_key) as client:
        response = client.get("/analyze", params={"query": "x"})

    sent = mock_gnews.calls[0].request.headers["X-Api-Key"]
    assert response.status_code == 200
    assert sent == "FAKE_TEST_KEY"
