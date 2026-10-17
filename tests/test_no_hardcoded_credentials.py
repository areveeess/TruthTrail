"""Repo hygiene: no credential literals in git-visible files, names-only example env, gitignore.

Failure messages list ``path:line`` only, never the matched text, so a failing run
cannot print a secret. ``tests/`` is skipped because it holds deliberate fake markers.
"""

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

CREDENTIAL_RX = re.compile(
    r"""(?i)(api[_-]?key|passw(or)?d|secret|token)\s*[:=]\s*["'][A-Za-z0-9_\-./+]{16,}["']"""
)
SCANNED_SUFFIXES = {".py", ".md", ".json", ".yml", ".yaml", ".toml", ".txt", ".ini", ".cfg", ".sh"}
EXPECTED_ENV_NAMES = {
    "GNEWS_API_KEY",
    "DEMO_MODE",
    "BLUESKY_HANDLE",
    "BLUESKY_APP_PASSWORD",
    "DATABASE_URL",
    "CORS_ORIGINS",
}


def _git_visible_paths() -> list[str]:
    """Tracked plus untracked-but-not-ignored paths, relative to the repo root."""
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    ).stdout
    return [p for p in out.decode("utf-8", errors="replace").split("\0") if p]


def _scannable(path: str) -> bool:
    if path.startswith("tests/") or path == "package-lock.json":
        return False
    if not (REPO_ROOT / path).is_file():
        return False
    name = Path(path).name
    return Path(path).suffix in SCANNED_SUFFIXES or name.startswith(".env")


def test_no_credential_literals_in_repo() -> None:
    scanned: list[str] = []
    hits: list[str] = []
    for path in _git_visible_paths():
        if not _scannable(path):
            continue
        scanned.append(path)
        text = (REPO_ROOT / path).read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            if CREDENTIAL_RX.search(line):
                hits.append(f"{path}:{number}")

    assert hits == []
    # The scan scope must not silently shrink: planning docs and project rules are covered.
    assert any(p.startswith(".planning/") for p in scanned)
    assert ".claude/CLAUDE.md" in scanned


def test_backstop_regex_fires_on_a_synthetic_sample() -> None:
    long_value = "API_KEY = " + '"' + "x" * 20 + '"'
    short_value = "API_KEY = " + '"' + "x" * 5 + '"'

    assert CREDENTIAL_RX.search(long_value) is not None
    assert CREDENTIAL_RX.search(short_value) is None


def test_env_example_lists_names_only() -> None:
    lines = (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    entries = [ln for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]

    malformed = [ln for ln in entries if not re.fullmatch(r"[A-Z][A-Z0-9_]*=", ln)]
    assert malformed == []
    assert {ln[:-1] for ln in entries} == EXPECTED_ENV_NAMES


@pytest.mark.parametrize(
    ("path", "ignored"),
    [
        (".env", True),
        (".env.local", True),
        (".env.example", False),
        ("data/sample.json", True),
        ("__pycache__/x.cpython-313.pyc", True),
        (".venv/bin/python", True),
        ("src/truthtrail/data/demo_analyze.json", False),
        ("scripts/copy_guard.py", False),
        ("tests/test_settings.py", False),
        ("src/truthtrail/schemas/models.py", False),
    ],
)
def test_gitignore_semantics(path: str, ignored: bool) -> None:
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", path],
        cwd=REPO_ROOT,
        capture_output=True,
    )

    assert result.returncode in (0, 1), "git check-ignore failed"
    assert (result.returncode == 0) is ignored
