"""Copy guard: fail when overclaiming wording appears in user-facing copy (D-13).

TruthTrail flags content for human review; it never decides what is true. This
script scans the README, docs/, UI string directories and every string of the
FastAPI OpenAPI document for banned phrases (truth- or fake-news-detection
claims, AI-based/AI-powered wording, an all-caps verdict label) and requires the
README to contain the phrase "flag ... for human review".

A line carrying the marker ``copy-guard: allow`` (on the matching line, any line
of a wrapped match, or the line immediately before) may quote a banned phrase.
tests/ and .planning/ are never scanned, and this file lives in scripts/, which
is not scanned either, because it has to spell the patterns out.

Usage:
    python scripts/copy_guard.py [--root PATH] [--no-openapi]

Exit codes: 0 clean, 1 findings.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ALLOW_MARKER = "copy-guard: allow"

# (rule id, pattern). Patterns use \s+ between words so hard-wrapped Markdown cannot dodge them.
# fake-verdict-label is case-sensitive with word boundaries: it matches the badge,
# not the prose word, and not FAKE_TEST_KEY (underscore is a word character).
BANNED: list[tuple[str, re.Pattern[str]]] = [
    ("truth-claim", re.compile(r"\bdetect(s|ing|ion|or|ors)?\s+(of\s+)?(the\s+)?truth\b", re.I)),
    ("fake-news-detector", re.compile(r"\bfake[\s-]+news\s+(detect\w*|classif\w*|identif\w*)\b", re.I)),
    (
        "detects-misinformation",
        re.compile(
            r"\b(detect(s|ing)?|identif(y|ies|ying))\s+(and\s+\w+\s+)?"
            r"(fake\s+news|misinformation|disinformation|fake\s+content|false\s+(claims?|information))\b",
            re.I,
        ),
    ),
    (
        "detects-misleading",
        re.compile(
            r"\bdetect(s|ing)?\s+(potentially\s+|possibly\s+)?(misleading|false|fake|fraudulent)"
            r"\s+(content|claims?|posts?|news|information|stories)\b",
            re.I,
        ),
    ),
    ("misinformation-detector", re.compile(r"\b(mis|dis)information\s+detect(or|ors|ion)\b", re.I)),
    ("ai-claim", re.compile(r"\bAI[\s-]*(based|powered|driven|enabled)\b", re.I)),
    ("fake-verdict-label", re.compile(r"\bFAKE\b")),
]

REQUIRED_README = re.compile(r"\bflag(s|ged)?\b[\s\S]{0,60}?\bfor\s+human\s+review\b", re.I)

# UI directories that do not exist yet simply match nothing; Phase 5 adds its directory if it differs.
SCAN_GLOBS = (
    "README.md",
    "docs/**/*",
    "frontend/src/**/*",
    "web/src/**/*",
    "dashboard/src/**/*",
    "ui/**/*",
)
TEXT_SUFFIXES = frozenset(
    {".md", ".mdx", ".txt", ".rst", ".html", ".htm", ".json", ".js", ".jsx", ".ts", ".tsx",
     ".vue", ".svelte", ".yml", ".yaml"}
)
EXCLUDED_PREFIXES = ("tests/", ".planning/", "node_modules/", ".venv/")

# OpenAPI string leaves under these keys are identifiers or formats, not copy.
OPENAPI_SKIP_KEYS = frozenset({"$ref", "operationId", "pattern", "format", "type"})


class Finding(NamedTuple):
    """One banned-copy hit (or a missing required element)."""

    source: str
    line: int
    rule: str
    excerpt: str


def scan_text(text: str, source: str) -> list[Finding]:
    """Return a Finding for every banned phrase in ``text`` that is not allow-marked."""
    lines = text.splitlines()
    findings: list[Finding] = []
    for rule, pattern in BANNED:
        for match in pattern.finditer(text):
            start = text.count("\n", 0, match.start()) + 1
            end = text.count("\n", 0, max(match.end() - 1, match.start())) + 1
            # 1-based lines start-1 (the line before) through end, as 0-based slice.
            window = lines[max(start - 2, 0):end]
            if any(ALLOW_MARKER in line for line in window):
                continue
            excerpt = " ".join(match.group(0).split())[:80]
            findings.append(Finding(source, start, rule, excerpt))
    findings.sort(key=lambda f: (f.line, f.rule))
    return findings


def openapi_strings(spec: Any, path: str = "") -> Iterator[tuple[str, str]]:
    """Yield (dotted path, value) for every copy-bearing string leaf of an OpenAPI document."""
    if isinstance(spec, dict):
        for key, value in spec.items():
            child = f"{path}.{key}" if path else str(key)
            if isinstance(value, str):
                if key not in OPENAPI_SKIP_KEYS:
                    yield child, value
            else:
                yield from openapi_strings(value, child)
    elif isinstance(spec, list):
        for index, value in enumerate(spec):
            child = f"{path}[{index}]"
            if isinstance(value, str):
                yield child, value
            else:
                yield from openapi_strings(value, child)


def scan_openapi(spec: Any) -> list[Finding]:
    """Scan every OpenAPI string leaf; findings carry source ``openapi:<path>``."""
    findings: list[Finding] = []
    for path, value in openapi_strings(spec):
        findings.extend(scan_text(value, f"openapi:{path}"))
    return findings


def _candidate_files(root: Path) -> list[Path]:
    seen: dict[str, Path] = {}
    for glob in SCAN_GLOBS:
        for path in root.glob(glob):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            rel = path.relative_to(root).as_posix()
            if rel.startswith(EXCLUDED_PREFIXES):
                continue
            seen[rel] = path
    return [seen[rel] for rel in sorted(seen)]


def _scan(root: Path, include_openapi: bool) -> tuple[list[Finding], int, int]:
    findings: list[Finding] = []
    files = _candidate_files(root)
    for path in files:
        rel = path.relative_to(root).as_posix()
        findings.extend(scan_text(path.read_text(encoding="utf-8", errors="replace"), rel))

    readme = root / "README.md"
    if not readme.is_file():
        findings.append(Finding("README.md", 0, "missing-readme", "README.md is absent"))
    elif not REQUIRED_README.search(readme.read_text(encoding="utf-8", errors="replace")):
        findings.append(
            Finding("README.md", 1, "missing-required-phrase", 'README must say "flag ... for human review"')
        )

    strings = 0
    if include_openapi:
        import main as app_module  # lazy: needs the repo root on sys.path and builds the app

        spec = app_module.app.openapi()
        strings = sum(1 for _ in openapi_strings(spec))
        findings.extend(scan_openapi(spec))
    return findings, len(files), strings


def scan_repo(root: Path, include_openapi: bool = True) -> list[Finding]:
    """Scan README, docs, UI directories and (optionally) the live OpenAPI strings under ``root``."""
    return _scan(Path(root), include_openapi)[0]


def main(argv: list[str] | None = None) -> int:
    """Run the guard; print findings as ``source:line: rule: excerpt``. Returns the exit code."""
    parser = argparse.ArgumentParser(description="Fail on overclaiming copy in docs and API strings.")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repository root to scan")
    parser.add_argument("--no-openapi", action="store_true", help="skip the OpenAPI string walk")
    args = parser.parse_args(argv)

    findings, files, strings = _scan(args.root, include_openapi=not args.no_openapi)
    if findings:
        for f in findings:
            sys.stdout.write(f"{f.source}:{f.line}: {f.rule}: {f.excerpt}\n")
        sys.stdout.write(f"copy-guard: {len(findings)} finding(s)\n")
        return 1
    sys.stdout.write(f"copy-guard: clean ({files} files, {strings} OpenAPI strings)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
