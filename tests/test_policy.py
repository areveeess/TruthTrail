"""The Phase 3 policy object (D-03): defaults equal the owner-ratified spike, values validate.

No test here hard-codes an owner-decision (OD) number. The expected values come from the real
``03-SPIKE.md`` through the gate's own importable functions (``scripts/check_spike_ratified.py``),
and constructed documents reuse the real document's recommended parameters and measurements.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

import truthtrail
from truthtrail.core.config import ConfigurationError
from truthtrail.core.policy import Policy, get_policy

ROOT = Path(__file__).resolve().parent.parent
GATE_PATH = ROOT / "scripts" / "check_spike_ratified.py"
SPIKE = ROOT / ".planning" / "phases" / "03-real-propagation-data" / "03-SPIKE.md"
# The ratified document records the allowlist relative to the repository root; the policy
# default is package-relative (Phase 2 D-22). Compared separately below.
PATH_KEYS = {"TRACK_ALLOWLIST_FILE"}


def _load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_spike_ratified_for_policy", GATE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GATE = _load_gate()


def _ratified() -> dict[str, Any]:
    return GATE.compute_effective_parameters(GATE.load_document(SPIKE))


def _env_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _field(policy: Policy, key: str) -> Any:
    return getattr(policy, key.lower())


def test_real_spike_document_is_ratified() -> None:
    code, _messages, payload = GATE.evaluate(SPIKE)
    assert code == GATE.EXIT_OK
    assert payload is not None


def test_policy_has_the_thirty_four_register_names() -> None:
    assert len(Policy.model_fields) == 34


def test_every_effective_parameter_is_a_policy_field() -> None:
    missing = [key for key in _ratified()["effective"] if key.lower() not in Policy.model_fields]
    assert missing == []


def test_policy_defaults_equal_the_ratified_document() -> None:
    effective = _ratified()["effective"]
    policy = get_policy()
    mismatched = [
        key
        for key, value in effective.items()
        if key not in PATH_KEYS and _field(policy, key) != value
    ]
    assert mismatched == []


def test_allowlist_default_is_the_ratified_file_inside_the_package() -> None:
    ratified = Path(_ratified()["effective"]["TRACK_ALLOWLIST_FILE"])
    default = get_policy().track_allowlist_file
    package_data = Path(truthtrail.__file__).resolve().parent / "data"
    assert default.is_absolute()
    assert default.parent == package_data
    assert default.is_file()
    # Same file: the ratified repository-relative path ends in the same package-relative parts.
    assert ratified.parts[-3:] == default.parts[-3:]
    if package_data.is_relative_to(ROOT):  # source checkout (editable install)
        assert (ROOT / ratified).resolve() == default


def test_policy_defaults_follow_the_ratified_od_choices() -> None:
    computed = _ratified()
    policy = get_policy()
    defaults = {key: _field(policy, key) for key in GATE.OD_BOUND_KEYS}
    assert defaults == {key: computed["effective"][key] for key in GATE.OD_BOUND_KEYS}
    assert GATE.check_od_consistency(computed["resolved"], defaults) == []


OPTION_CASES = {
    "RT-1": {"od1": "RT-1", "od2": "M1", "od3": "A"},
    "RT-2": {"od1": "RT-2", "od2": "M1", "od3": "A"},
    "RT-3": {"od1": "RT-3", "od2": "M1", "od3": "A"},
    "M0": {"od1": "RT-2", "od2": "M0", "od3": "A"},
    "M1": {"od1": "RT-2", "od2": "M1", "od3": "A"},
    "A": {"od1": "RT-2", "od2": "M1", "od3": "A"},
    "B": {"od1": "RT-2", "od2": "M1", "od3": "B"},
}


def _constructed_document(path: Path, options: dict[str, str]) -> Path:
    """A ratified document for ``options`` with the real recommended parameters, no overrides."""
    import json

    real = GATE.load_document(SPIKE)
    lines = [
        "---",
        "phase: 3",
        "ratified: true",
        "ratified_by: owner",
        "ratified_on: 2026-11-06",
        "ratification_source: owner-edit",
        f"od1_retention: {options['od1']}",
        f"od2_merge: {options['od2']}",
        f"od3_tracking: {options['od3']}",
        "schema_via_uri: true",
        "dependencies_approved: true",
        "pseudonym_scheme: d17-hmac-v1",
        f"eligible_roots_per_day: {real['eligible_roots_per_day']}",
        f"bytes_per_root: {real['bytes_per_root']}",
        f"recommended_parameters: {json.dumps(real['recommended_parameters'])}",
        f"recommended_options: {json.dumps(real['recommended_options'])}",
        "ratified_parameters: {}",
        "---",
        "",
        "Constructed for tests/test_policy.py.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("option", list(OPTION_CASES))
def test_every_od_option_is_enactable(
    option: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = _constructed_document(tmp_path / "03-SPIKE.md", OPTION_CASES[option])
    code, _messages, payload = GATE.evaluate(document)
    assert code == GATE.EXIT_OK
    assert payload is not None
    effective = payload["effective_parameters"]
    resolved = {od: payload[f"resolved_{od}"] for od in ("od1", "od2", "od3")}

    for key in GATE.OD_BOUND_KEYS:
        monkeypatch.setenv(key, _env_value(effective[key]))
    policy = get_policy()

    values = {key: _field(policy, key) for key in GATE.OD_BOUND_KEYS}
    assert values == {key: effective[key] for key in GATE.OD_BOUND_KEYS}
    assert GATE.check_od_consistency(resolved, values) == []
    for key, implied in GATE.OD_IMPLICATIONS[option]["sets"].items():
        if isinstance(implied, str) and implied.startswith("="):
            assert _field(policy, key) == _field(policy, implied[1:])
        else:
            assert _field(policy, key) == implied


def test_rt1_text_days_zero_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETENTION_TEXT_DAYS", "0")
    assert get_policy().retention_text_days == 0


def test_rt3_text_days_equal_to_cascade_days_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    cascade = get_policy().retention_cascade_days
    monkeypatch.setenv("RETENTION_TEXT_DAYS", str(cascade))
    policy = get_policy()
    assert policy.retention_text_days == policy.retention_cascade_days


def test_text_days_above_cascade_days_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    cascade = get_policy().retention_cascade_days
    monkeypatch.setenv("RETENTION_TEXT_DAYS", str(cascade + 1))
    with pytest.raises(ConfigurationError) as info:
        get_policy()
    assert "RETENTION_TEXT_DAYS" in str(info.value)


def _override_for(name: str, default: object, tmp_path: Path) -> tuple[str, object]:
    """An environment string different from the default, and the value it must produce."""
    special: dict[str, tuple[str, object]] = {
        "cascade_merge_policy": (
            "none" if default != "none" else "claim_group",
            "none" if default != "none" else "claim_group",
        ),
        "ingest_dialect": ("v1" if default != "v1" else "v2", "v1" if default != "v1" else "v2"),
        "track_require_lang": ("de", "de"),
        "ingest_hosts": ("A.example.org, b.example.org", ["a.example.org", "b.example.org"]),
        "track_allowlist_file": (str(tmp_path / "domains.txt"), tmp_path / "domains.txt"),
    }
    if name in special:
        return special[name]
    if isinstance(default, bool):
        return _env_value(not default), not default
    assert isinstance(default, int), name
    return str(default + 1), default + 1


@pytest.mark.parametrize("name", sorted(Policy.model_fields))
def test_every_environment_name_overrides_its_field(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    default = getattr(get_policy(), name)
    raw, expected = _override_for(name, default, tmp_path)
    monkeypatch.setenv(name.upper(), raw)
    value = getattr(get_policy(), name)
    assert value == expected
    assert value != default


def test_environment_names_are_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    default = get_policy().max_tree_nodes
    monkeypatch.setenv("max_tree_nodes", str(default + 1))
    assert get_policy().max_tree_nodes == default + 1


def test_blank_value_means_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    default = get_policy().page_size_max
    monkeypatch.setenv("PAGE_SIZE_MAX", "")
    assert get_policy().page_size_max == default


INVALID = [
    # (variable, value, value is a distinctive marker that must never be echoed)
    ("TRACK_MAX_ACTIVE_ROOTS", "0", False),
    ("RETENTION_CASCADE_DAYS", "0", False),
    ("RETENTION_TEXT_DAYS", "-424242", True),
    ("RETENTION_DORMANT_DAYS", "-424242", True),
    ("INGEST_MAX_EVENTS", "markervalue", True),
    ("NEWS_DAILY_BUDGET", "4.25e1marker", True),
    ("RETENTION_TEXT_DAYS", "3001", True),  # above the cascade days, within its own range
    ("INGEST_MAX_RESUME_AGE_HOURS", "36", False),
    ("INGEST_MAX_RESUME_AGE_HOURS", "424242", True),
    ("TRACK_SAMPLE_PER_10K", "0", False),
    ("TRACK_SAMPLE_PER_10K", "10001", True),
    ("DB_STOP_PERCENT", "101", True),
    ("INGEST_REWIND_SECONDS", "29", False),
    ("PAGE_SIZE_DEFAULT", "5150", True),  # above PAGE_SIZE_MAX
    ("INGEST_HOSTS", "https://marker.example.org", True),
    ("INGEST_HOSTS", "marker.example.org/path", True),
    ("INGEST_HOSTS", "marker.example.org:443", True),
    ("INGEST_HOSTS", "user@marker.example.org", True),
    ("INGEST_HOSTS", " , ", False),
    ("CASCADE_MERGE_POLICY", "markermerge", True),
    ("INGEST_DIALECT", "v3marker", True),
    ("TRACK_SEED_CLAIM_URL_MATCH", "maybemarker", True),
    ("TRACK_REQUIRE_LANG", "Englishmarker", True),
]


@pytest.mark.parametrize(("name", "value", "is_marker"), INVALID)
def test_invalid_values_fail_naming_the_variable_never_the_value(
    name: str, value: str, is_marker: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigurationError) as info:
        get_policy()
    message = str(info.value)
    assert message.startswith(f"Invalid configuration ({name}: ")
    assert info.value.__cause__ is None
    assert info.value.__suppress_context__ is True
    if is_marker:
        assert value.strip() not in message
        assert value.strip() not in repr(info.value)


def test_get_policy_is_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    first = get_policy()
    monkeypatch.setenv("NEWS_MAX_TOPICS", str(first.news_max_topics + 1))
    assert get_policy().news_max_topics == first.news_max_topics + 1
