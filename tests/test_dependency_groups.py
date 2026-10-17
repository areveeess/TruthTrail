"""Dependency policy and lock contract (D-14, D-22, D-24).

Pure ``tomllib`` checks of ``pyproject.toml`` and ``uv.lock``; no network and no uv invocation.
"""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EXPECTED_SERVING = {
    "fastapi": "0.143.0",
    "starlette": "1.8.0",
    "pydantic": "2.14.0",
    "pydantic-settings": "2.15.0",
    "uvicorn": "0.54.0",
    "requests": "2.34.2",
    "slowapi": "0.1.10",
    "limits": "5.8.0",
    "cachetools": "7.2.3",
}
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([0-9][A-Za-z0-9.!+_-]*)$")


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _lock() -> dict:
    return tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))


def _names(entries: list[str]) -> set[str]:
    out = set()
    for entry in entries:
        match = PIN.match(entry)
        assert match, f"not an exact pin: {entry!r}"
        out.add(match.group(1))
    return out


def test_python_version_is_pinned_to_3_13() -> None:
    assert _pyproject()["project"]["requires-python"] == ">=3.13,<3.14"
    assert (ROOT / ".python-version").read_text(encoding="utf-8").strip() == "3.13"


def test_project_has_no_readme_key() -> None:
    # The image build fails once markdown is dockerignored (D-22).
    assert "readme" not in _pyproject()["project"]


def test_serving_dependencies_are_exact_pins() -> None:
    deps = _pyproject()["project"]["dependencies"]
    pins = {}
    for entry in deps:
        match = PIN.match(entry)
        assert match, f"not an exact pin: {entry!r}"
        pins[match.group(1)] = match.group(2)
    assert pins == EXPECTED_SERVING


def test_groups_are_split_and_dev_is_the_default() -> None:
    doc = _pyproject()
    groups = doc["dependency-groups"]
    assert {"dev", "train"} <= set(groups)
    assert _names(groups["train"]) == {"scikit-learn", "numpy"}
    assert doc["tool"]["uv"]["default-groups"] == ["dev"]
    for entry in groups["dev"]:
        assert PIN.match(entry), f"not an exact pin: {entry!r}"


def test_uv_required_version_is_not_set() -> None:
    # The container's uv is older than the one that generated the lock (D-24).
    assert "required-version" not in _pyproject()["tool"]["uv"]


def test_lock_covers_every_group_and_keeps_train_out_of_runtime() -> None:
    lock = _lock()
    assert lock["requires-python"] == "==3.13.*"
    packages = {p["name"]: p for p in lock["package"]}
    required = ("scikit-learn", "numpy", "fastapi", "slowapi", "limits", "cachetools")
    for name in (*required, "hypothesis", "pytest-cov"):
        assert name in packages, f"{name} missing from uv.lock"
    root = packages["truthtrail"]
    train = {d["name"] for d in root["dev-dependencies"]["train"]}
    assert train == {"scikit-learn", "numpy"}
    runtime = {d["name"] for d in root["dependencies"]}
    assert not runtime & {"scikit-learn", "numpy"}


def test_retired_pip_manifests_are_gone() -> None:
    for name in ("requirements.txt", "requirements-dev.txt", "pytest.ini"):
        assert not (ROOT / name).exists(), f"{name} must be deleted (D-14, D-25)"


def test_pytest_configuration_lives_in_pyproject() -> None:
    table = _pyproject()["tool"]["pytest"]["ini_options"]
    assert table["xfail_strict"] is True
    assert "--cov" not in table["addopts"]
