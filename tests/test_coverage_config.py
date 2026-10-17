"""Shape of the coverage configuration in pyproject.toml (D-15).

The gate is the measured total minus 2 points and may only be ratcheted upward. It must not be
part of addopts, otherwise a partial test run (one file, one test) would trip it.
"""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _config() -> dict:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_coverage_measures_the_package_with_branches() -> None:
    run = _config()["tool"]["coverage"]["run"]
    assert run["source"] == ["truthtrail"]
    assert run["branch"] is True


def test_fail_under_is_an_integer_percentage() -> None:
    value = _config()["tool"]["coverage"]["report"]["fail_under"]
    assert isinstance(value, int)
    assert not isinstance(value, bool)
    assert 1 <= value <= 100


def test_addopts_does_not_enable_coverage() -> None:
    addopts = _config()["tool"]["pytest"]["ini_options"]["addopts"]
    assert "--cov" not in addopts


def test_legacy_directory_is_not_measured() -> None:
    source = _config()["tool"]["coverage"]["run"]["source"]
    assert all("legacy" not in entry for entry in source)
