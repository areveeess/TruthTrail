"""Drift guard (D-31): Policy fields, the example environment file, the credential test's name
set, the conftest scrub list and the README name the same variables."""

from pathlib import Path

import conftest
from test_no_hardcoded_credentials import EXPECTED_ENV_NAMES

from truthtrail.core.policy import Policy

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
EXAMPLE_ENV = ROOT / ".env.example"

PHASE_1_AND_2_NAMES = {
    "GNEWS_API_KEY",
    "DEMO_MODE",
    "BLUESKY_HANDLE",
    "BLUESKY_APP_PASSWORD",
    "DATABASE_URL",
    "CORS_ORIGINS",
    "RATE_LIMIT_ANALYZE",
    "RATE_LIMIT_V1",
    "TRUST_PROXY_HEADERS",
    "FORWARDED_ALLOW_IPS",
}
OPERATOR_NAMES = {"PSEUDONYM_SECRET", "COLLECTOR_CONTACT"}
TEST_ONLY_NAMES = {"TEST_DATABASE_URL", "TRUTHTRAIL_PG_BIN", "REQUIRE_DB", "REQUIRE_DB_FLOOR"}
POLICY_NAMES = {name.upper() for name in Policy.model_fields}


def _example_names() -> list[str]:
    names = []
    for line in EXAMPLE_ENV.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            names.append(stripped.split("=", 1)[0].strip())
    return names


def test_every_policy_name_is_in_the_example_file() -> None:
    assert POLICY_NAMES - set(_example_names()) == set()


def test_every_policy_and_operator_name_is_in_the_readme() -> None:
    text = README.read_text(encoding="utf-8")
    missing = sorted(name for name in POLICY_NAMES | OPERATOR_NAMES if f"`{name}`" not in text)
    assert missing == []


def test_example_file_is_exactly_the_documented_set() -> None:
    names = _example_names()
    assert len(names) == len(set(names)), "a name is listed twice"
    assert len(names) == len(Policy.model_fields) + len(OPERATOR_NAMES) + len(PHASE_1_AND_2_NAMES)
    assert set(names) == POLICY_NAMES | OPERATOR_NAMES | PHASE_1_AND_2_NAMES


def test_credential_test_name_set_matches_the_example_file() -> None:
    assert set(_example_names()) == EXPECTED_ENV_NAMES


def test_test_only_names_are_in_the_readme_and_not_in_the_example_file() -> None:
    text = README.read_text(encoding="utf-8")
    assert sorted(name for name in TEST_ONLY_NAMES if f"`{name}`" not in text) == []
    assert TEST_ONLY_NAMES & set(_example_names()) == set()


def test_conftest_scrubs_every_name() -> None:
    scrubbed = set(conftest.ENV_NAMES)
    assert set(_example_names()) | TEST_ONLY_NAMES <= scrubbed


def test_conftest_disables_the_env_file_for_every_settings_class() -> None:
    from truthtrail.core.boot import BootSettings
    from truthtrail.core.config import DatabaseSettings, IngestSettings, Settings

    expected = {Settings, BootSettings, Policy, DatabaseSettings, IngestSettings}
    assert expected <= set(conftest.SETTINGS_CLASSES)
    for settings_class in conftest.SETTINGS_CLASSES:
        assert settings_class.model_config.get("env_file") is None


def test_readme_documents_the_fast_loop() -> None:
    assert 'pytest -m "not requires_db"' in README.read_text(encoding="utf-8")
