"""Per-entrypoint settings (D-27, D-17, D-07): DatabaseSettings and IngestSettings.

The database and collector commands validate only what they need, the API's ``Settings`` never
holds the pseudonym key, and no value is ever echoed in an error, ``repr`` or ``str``.
"""

import pytest

from truthtrail.core.config import (
    ConfigurationError,
    DatabaseSettings,
    IngestSettings,
    Settings,
    get_database_settings,
    get_ingest_settings,
)

MARKER_URL = "postgresql://marker_user:Marker-Pass-6f2Q@db.invalid:5432/markerdb"
PSEUDONYM_MARKER = "Marker-Pseudonym-Zx81"


def test_missing_database_url_names_only_that_variable() -> None:
    with pytest.raises(ConfigurationError) as info:
        get_database_settings()
    message = str(info.value)
    assert message == "Invalid configuration (DATABASE_URL: Field required)"
    assert info.value.__cause__ is None


def test_missing_pseudonym_secret_names_only_that_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", MARKER_URL)
    with pytest.raises(ConfigurationError) as info:
        get_ingest_settings()
    message = str(info.value)
    assert "PSEUDONYM_SECRET" in message
    assert "DATABASE_URL" not in message
    assert MARKER_URL not in message


def test_ingest_settings_require_the_database_url_too(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PSEUDONYM_SECRET", PSEUDONYM_MARKER)
    with pytest.raises(ConfigurationError) as info:
        get_ingest_settings()
    assert "DATABASE_URL" in str(info.value)
    assert PSEUDONYM_MARKER not in str(info.value)


def test_secrets_are_masked_and_never_echoed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", MARKER_URL)
    monkeypatch.setenv("PSEUDONYM_SECRET", PSEUDONYM_MARKER)
    settings = get_ingest_settings()
    assert settings.database_url.get_secret_value() == MARKER_URL
    assert settings.pseudonym_secret.get_secret_value() == PSEUDONYM_MARKER
    for rendering in (repr(settings), str(settings), repr(settings.database_url)):
        assert MARKER_URL not in rendering
        assert "Marker-Pass" not in rendering
        assert PSEUDONYM_MARKER not in rendering
    database = get_database_settings()
    assert isinstance(database, DatabaseSettings)
    assert "Marker-Pass" not in repr(database)


def test_settings_are_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", MARKER_URL)
    first = get_database_settings()
    monkeypatch.setenv("DATABASE_URL", MARKER_URL + "2")
    assert get_database_settings().database_url.get_secret_value() != (
        first.database_url.get_secret_value()
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ops@example.org", "ops@example.org"),
        ("  https://example.org/contact  ", "https://example.org/contact"),
        ("Operator Name <ops@example.org>", "Operator Name <ops@example.org>"),
        ("   ", None),
        ("x" * 200, "x" * 200),
    ],
)
def test_collector_contact_accepts_header_safe_text(
    raw: str, expected: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", MARKER_URL)
    monkeypatch.setenv("PSEUDONYM_SECRET", PSEUDONYM_MARKER)
    monkeypatch.setenv("COLLECTOR_CONTACT", raw)
    assert get_ingest_settings().collector_contact == expected


def test_unset_collector_contact_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", MARKER_URL)
    monkeypatch.setenv("PSEUDONYM_SECRET", PSEUDONYM_MARKER)
    assert get_ingest_settings().collector_contact is None


@pytest.mark.parametrize(
    "raw",
    [
        "markercontact\r\nX-Injected: 1",
        "markercontact\nsecond line",
        "markercontact\rsecond",
        "markercontact\ttab",
        "markercontact\x7fdel",
        "markercontact\x1bescape",
        "markercontact-café",
        "markercontact" + "y" * 200,
    ],
)
def test_collector_contact_rejects_unsafe_text_without_echo(
    raw: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", MARKER_URL)
    monkeypatch.setenv("PSEUDONYM_SECRET", PSEUDONYM_MARKER)
    monkeypatch.setenv("COLLECTOR_CONTACT", raw)
    with pytest.raises(ConfigurationError) as info:
        get_ingest_settings()
    message = str(info.value)
    assert message.startswith("Invalid configuration (COLLECTOR_CONTACT: ")
    assert "markercontact" not in message
    assert PSEUDONYM_MARKER not in message
    assert "Marker-Pass" not in message


def test_api_settings_hold_no_ingest_values() -> None:
    assert "pseudonym_secret" not in Settings.model_fields
    assert "collector_contact" not in Settings.model_fields
    assert not issubclass(Settings, DatabaseSettings)
    assert issubclass(IngestSettings, DatabaseSettings)
