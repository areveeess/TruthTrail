"""Configuration tests: key only in the header, fail-fast startup, secrets never echoed."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from config import ConfigurationError, get_settings

# Low-entropy marker values: they must never appear in any error, repr or output.
DATABASE_URL_MARKER = "postgresql://user:not-a-real-password@localhost:5432/truthtrail"
APP_PASSWORD_MARKER = "not-a-real-app-password"


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
def test_demo_mode_parsing(monkeypatch: pytest.MonkeyPatch, fake_key: str, raw: str, expected: bool) -> None:
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
        "PYTHONPATH": str(repo_root),
        "PYTHONDONTWRITEBYTECODE": "1",
        "DATABASE_URL": DATABASE_URL_MARKER,
    }

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
