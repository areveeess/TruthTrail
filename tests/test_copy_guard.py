"""Tests for scripts/copy_guard.py (D-13): rules, allow marker, exclusions, OpenAPI walk, repo state."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GUARD_PATH = REPO_ROOT / "scripts" / "copy_guard.py"

GOOD_README = "# Demo\n\nThe output is a flag for human review.\n"


@pytest.fixture(scope="module")
def guard():
    spec = importlib.util.spec_from_file_location("copy_guard", GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("sample", "rule_id"),
    [
        ("TruthTrail detects the truth.", "truth-claim"),
        ("It detects the\ntruth of every post.", "truth-claim"),
        ("Our fake news detector is fast.", "fake-news-detector"),
        ("It identifies fake news early.", "detects-misinformation"),
        ("TruthTrail detects potentially misleading content and shows its spread.", "detects-misleading"),
        ("A misinformation detector for teams.", "misinformation-detector"),
        ("An AI-based system for reviewers.", "ai-claim"),
        ("The card shows a FAKE badge.", "fake-verdict-label"),
        ("A truth detection tool.", "truth-claim-rev"),
        ("Our truth detector is fast.", "truth-claim-rev"),
        ("The truth-detection engine runs nightly.", "truth-claim-rev"),
        ("A truth\nverification service.", "truth-claim-rev"),
        ("Meet the truth checker.", "truth-claim-rev"),
        ("A lie detector for news.", "lie-detector"),
        ("Lie-detecting software.", "lie-detector"),
        ("A fake news filter for editors.", "fake-news-filter"),
        ("Our fake-news spotter.", "fake-news-filter"),
        ("A misinformation classifier.", "misinformation-classifier"),
        ("Disinformation classification at scale.", "misinformation-classifier"),
        ("It finds fake news before you do.", "finds-fake-news"),
        ("It spots misinformation.", "finds-fake-news"),
        ("Each post is labelled true or false.", "verdict-wording"),
        ("Shows a real or fake verdict.", "verdict-wording"),
    ],
)
def test_rules_fire_on_banned_samples(guard, sample, rule_id):
    findings = guard.scan_text(sample, "sample.md")
    assert rule_id in {f.rule for f in findings}
    assert all(f.source == "sample.md" and f.line >= 1 for f in findings)
    assert {rule for rule, _ in guard.BANNED} >= {rule_id}


@pytest.mark.parametrize(
    "sample",
    [
        "fake news are common online",
        "FAKE_TEST_KEY",
        "AI-assisted triage",
        "a misinformation early-warning system",
        "Baseline Detection & Evaluation",
        "This is a flag for human review.",
        "Truth is not decided here; a reviewer decides.",
        "We never claim to detect anything about the truth value of a post.",
        "It flags posts for human review.",
        "The lie of the land is mapped by a detector pipeline.",
        "A fake news story can spread quickly.",
        "Whether a claim is true is for the reviewer to decide.",
        "Verified accounts are shown with a badge.",
    ],
)
def test_clean_samples_pass(guard, sample):
    assert guard.scan_text(sample, "sample.md") == []


def test_allow_marker_on_line_and_line_before(guard):
    banned = "It detects the truth."
    marker = "<!-- copy-guard: allow -->"
    assert guard.scan_text(f"{banned} {marker}", "a.md") == []
    assert guard.scan_text(f"{marker}\n{banned}", "a.md") == []
    # Two lines above is too far away.
    far = guard.scan_text(f"{marker}\nfiller\n{banned}", "a.md")
    assert [f.rule for f in far] == ["truth-claim"]
    assert far[0].line == 3


@pytest.mark.parametrize(
    "banned",
    [
        "A truth detection tool.",
        "Our lie detector.",
        "A fake news filter.",
        "A misinformation classifier.",
        "It finds fake news.",
        "True or false.",
    ],
)
def test_allow_marker_covers_the_new_rules(guard, banned):
    marker = "<!-- copy-guard: allow -->"
    assert guard.scan_text(f"{banned} {marker}", "a.md") == []
    assert guard.scan_text(f"{marker}\n{banned}", "a.md") == []
    far = guard.scan_text(f"{marker}\nfiller\n{banned}", "a.md")
    assert len(far) == 1 and far[0].line == 3
    assert guard.scan_text(banned, "a.md") != []


def test_readme_requires_flag_phrase(guard, tmp_path):
    (tmp_path / "README.md").write_text("# Demo\n\nNothing about review here.\n", encoding="utf-8")
    findings = guard.scan_repo(tmp_path, include_openapi=False)
    assert [f.rule for f in findings] == ["missing-required-phrase"]

    (tmp_path / "README.md").write_text(GOOD_README, encoding="utf-8")
    assert guard.scan_repo(tmp_path, include_openapi=False) == []

    wrapped = "# Demo\n\nEvery result is flagged\nfor human review.\n"
    (tmp_path / "README.md").write_text(wrapped, encoding="utf-8")
    assert guard.scan_repo(tmp_path, include_openapi=False) == []

    (tmp_path / "README.md").unlink()
    assert [f.rule for f in guard.scan_repo(tmp_path, include_openapi=False)] == ["missing-readme"]


def test_excluded_dirs_are_not_scanned(guard, tmp_path):
    (tmp_path / "README.md").write_text(GOOD_README, encoding="utf-8")
    for excluded in ("tests", ".planning"):
        (tmp_path / excluded).mkdir()
        (tmp_path / excluded / "notes.md").write_text("It detects the truth.\n", encoding="utf-8")
    assert guard.scan_repo(tmp_path, include_openapi=False) == []

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("Intro\n\nAn AI-powered tool.\n", encoding="utf-8")
    findings = guard.scan_repo(tmp_path, include_openapi=False)
    assert [(f.source, f.line, f.rule) for f in findings] == [("docs/guide.md", 3, "ai-claim")]


def test_openapi_strings_are_walked(guard):
    spec = {
        "info": {"title": "T", "description": "It detects the truth."},
        "components": {
            "schemas": {
                "Verdict": {"type": "string", "enum": ["OK", "FAKE"]},
                "Hidden": {
                    "$ref": "It detects the truth.",
                    "pattern": "It detects the truth.",
                    "format": "It detects the truth.",
                    "operationId": "It detects the truth.",
                },
            }
        },
    }
    findings = guard.scan_openapi(spec)
    assert {(f.source, f.rule) for f in findings} == {
        ("openapi:info.description", "truth-claim"),
        ("openapi:components.schemas.Verdict.enum[1]", "fake-verdict-label"),
    }
    # A property that happens to be named "type" must not hide its description.
    nested = {"properties": {"type": {"description": "An AI-based badge."}}}
    assert [f.rule for f in guard.scan_openapi(nested)] == ["ai-claim"]


def test_repository_copy_is_clean(guard):
    assert guard.scan_repo(REPO_ROOT) == []


def _run_guard(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(
        [sys.executable, str(GUARD_PATH), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=60,
    )


def test_cli_exit_codes(tmp_path):
    clean = _run_guard()
    assert clean.returncode == 0, clean.stdout + clean.stderr
    assert "copy-guard: clean" in clean.stdout

    (tmp_path / "README.md").write_text("It detects the truth.\n", encoding="utf-8")
    bad = _run_guard("--root", str(tmp_path), "--no-openapi")
    assert bad.returncode == 1
    assert "README.md:" in bad.stdout
    assert "truth-claim" in bad.stdout
