"""Static contract for .github/workflows/ci.yml (D-17, D-26).

The workflow cannot run in this container, so its structure is machine-checked instead: job
names (a branch-protection rule may require them), SHA-pinned actions, read-only permissions,
timeouts, the untouched gitleaks job and the uv based installs.
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
# Plan 02-12 extends this one constant when it adds jobs.
EXPECTED_JOBS = {"copy-guard", "gitleaks", "tests"}
FLOOR = "a5dd8257e920923677c60e70611a6f36d87747b2"
USES_LINE = re.compile(r"^\s*-?\s*uses:\s*(\S+)(.*)$")
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
VERSION_COMMENT = re.compile(r"^\s*# v\d")


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _doc() -> dict:
    return yaml.safe_load(_text())


def _jobs() -> dict:
    return _doc()["jobs"]


def _steps(job: str) -> list[dict]:
    return _jobs()[job]["steps"]


def _step_text(job: str) -> str:
    return yaml.safe_dump(_steps(job))


def test_job_names_are_unchanged() -> None:
    assert set(_jobs()) == EXPECTED_JOBS


def test_push_and_pull_request_trigger() -> None:
    doc = _doc()
    triggers = doc.get("on", doc.get(True))  # PyYAML parses the key `on` as True
    assert {"push", "pull_request"} <= set(triggers)


def test_permissions_are_read_only() -> None:
    assert _doc()["permissions"] == {"contents": "read"}


def test_every_action_is_sha_pinned_with_a_version_comment() -> None:
    found = 0
    for line in _text().splitlines():
        match = USES_LINE.match(line)
        if not match:
            continue
        found += 1
        assert PINNED.match(match.group(1)), f"not SHA-pinned: {line.strip()}"
        assert VERSION_COMMENT.match(match.group(2)), f"no version comment: {line.strip()}"
    assert found >= 4


def test_every_job_has_an_integer_timeout() -> None:
    for name, job in _jobs().items():
        assert isinstance(job.get("timeout-minutes"), int), name


def test_checkouts_do_not_persist_credentials() -> None:
    checkouts = 0
    for name in _jobs():
        for step in _steps(name):
            if str(step.get("uses", "")).startswith("actions/checkout@"):
                checkouts += 1
                assert step["with"]["persist-credentials"] is False, name
    assert checkouts >= 3


def test_no_secrets_are_referenced() -> None:
    assert "secrets." not in _text()


def test_gitleaks_job_is_intact() -> None:
    job = _jobs()["gitleaks"]
    assert job["env"]["RANGE_FLOOR"] == FLOOR
    checkout = next(s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout@"))
    assert checkout["with"]["fetch-depth"] == 0
    assert any("selftest" in str(s.get("name", "")).lower() for s in job["steps"])
    assert any("scripts/gitleaks_scan.sh" in str(s.get("run", "")) for s in job["steps"])


def test_python_jobs_install_with_locked_uv() -> None:
    for name in ("copy-guard", "tests"):
        steps = _steps(name)
        setup = [s for s in steps if str(s.get("uses", "")).startswith("astral-sh/setup-uv@")]
        assert len(setup) == 1, name
        assert setup[0]["with"]["version"] == "0.13.1", name
        assert any("uv sync --locked" in str(s.get("run", "")) for s in steps), name
        text = _step_text(name)
        assert "pip install" not in text, name
        assert "requirements" not in text, name
