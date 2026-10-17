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
EXPECTED_JOBS = {"copy-guard", "gitleaks", "tests", "lint", "typecheck", "audit", "docker"}
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
    assert checkouts == len(EXPECTED_JOBS)


def test_no_secrets_are_referenced() -> None:
    assert "secrets." not in _text()


def test_gitleaks_job_is_intact() -> None:
    job = _jobs()["gitleaks"]
    assert job["env"]["RANGE_FLOOR"] == FLOOR
    checkout = next(
        s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout@")
    )
    assert checkout["with"]["fetch-depth"] == 0
    assert any("selftest" in str(s.get("name", "")).lower() for s in job["steps"])
    assert any("scripts/gitleaks_scan.sh" in str(s.get("run", "")) for s in job["steps"])


def test_python_jobs_install_with_locked_uv() -> None:
    for name in ("copy-guard", "tests", "lint", "typecheck", "audit"):
        steps = _steps(name)
        setup = [s for s in steps if str(s.get("uses", "")).startswith("astral-sh/setup-uv@")]
        assert len(setup) == 1, name
        assert setup[0]["with"]["version"] == "0.13.1", name
        assert any("uv sync --locked" in str(s.get("run", "")) for s in steps), name
        text = _step_text(name)
        assert "pip install" not in text, name
        assert "requirements.txt" not in text, name


def _run_text(job: str) -> str:
    return "\n".join(str(s.get("run", "")) for s in _steps(job))


def test_lint_job_runs_ruff_and_the_lock_check() -> None:
    text = _run_text("lint")
    assert "ruff check" in text
    assert "ruff format --check" in text
    assert "uv lock --check" in text


def test_typecheck_job_runs_mypy() -> None:
    assert "mypy" in _run_text("typecheck")


def test_audit_job_audits_the_exported_lock_with_hashes() -> None:
    text = _run_text("audit")
    assert "uv export" in text
    assert "--locked" in text
    assert "pip-audit" in text
    assert "--require-hashes" in text


def test_tests_job_gates_coverage_with_the_ci_profile() -> None:
    text = _run_text("tests")
    assert "--cov" in text
    assert "--hypothesis-profile=ci" in text


def test_docker_job_builds_runs_and_probes_the_image() -> None:
    text = _run_text("docker")
    assert "docker build" in text
    assert "DEMO_MODE=true" in text
    for path in ("/health", "/ready", "/analyze"):
        assert path in text, path
    assert '"synthetic":true' in text
    assert "id -u" in text
    for module in ("spread_simulator", "users", "risk_analyzer", "pytest"):
        assert module in text, module


def test_docker_job_always_prints_logs_and_stops_the_container() -> None:
    cleanup = [s for s in _steps("docker") if str(s.get("if", "")).strip() == "always()"]
    assert len(cleanup) == 1
    assert "docker logs" in cleanup[0]["run"]
    assert "docker stop" in cleanup[0]["run"]
    # The cleanup step is the last one, so it never hides a failure of an earlier step.
    assert _steps("docker")[-1].get("if") == "always()"


def test_docker_job_needs_no_uv_and_no_secret_environment() -> None:
    text = _step_text("docker")
    assert "setup-uv" not in text
    assert "uv sync" not in text
    assert "GNEWS_API_KEY" not in text


def test_no_job_skips_failures() -> None:
    text = _text()
    assert "continue-on-error" not in text
    # A pip-audit exception is allowed only with a dated comment naming the advisory (T-02-41).
    if "--ignore-vuln" in _run_text("audit"):
        assert re.search(r"#.*\d{4}-\d{2}-\d{2}", text)
