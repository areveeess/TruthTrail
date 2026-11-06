"""Static contract for the Dockerfile and .dockerignore (D-18, D-26).

No Docker daemon exists in the dev container, so the image cannot be built here. These tests
parse the two files as text and enforce every security-relevant property of the image; the real
build and the running container are verified by the CI ``docker`` job and recorded as a
non-gating human follow-up (D-26). No network and no Docker CLI are used.
"""

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DIGEST = re.compile(r"@sha256:[0-9a-f]{64}(?=\s|$)")
EXPECTED_CMD = [
    "uvicorn",
    "truthtrail.main:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8000",
    "--no-proxy-headers",
]


def _logical_lines() -> list[str]:
    """Dockerfile instructions with backslash continuations joined and comments dropped."""
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    lines: list[str] = []
    buffer = ""
    for raw in text.split("\n"):
        stripped = raw.strip()
        if not buffer and (not stripped or stripped.startswith("#")):
            continue
        if stripped.endswith("\\"):
            buffer += stripped[:-1].rstrip() + " "
            continue
        lines.append((buffer + stripped).strip())
        buffer = ""
    assert not buffer, "Dockerfile ends inside a continuation"
    return lines


def _instructions(name: str) -> list[str]:
    return [line for line in _logical_lines() if line.split(None, 1)[0].upper() == name]


def _dockerignore() -> set[str]:
    text = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    return {
        line.strip()
        for line in text.split("\n")
        if line.strip() and not line.strip().startswith("#")
    }


def test_every_from_and_the_uv_image_are_pinned_by_tag_and_digest() -> None:
    froms = _instructions("FROM")
    assert len(froms) == 2
    for line in froms:
        assert re.search(r"\bpython:3\.13-slim@sha256:", line), line
        assert DIGEST.search(line), f"base image not digest-pinned: {line}"
    copy_uv = [line for line in _instructions("COPY") if "--from=ghcr.io/astral-sh/uv" in line]
    assert len(copy_uv) == 1
    assert "ghcr.io/astral-sh/uv:0.13.1@sha256:" in copy_uv[0]
    assert DIGEST.search(copy_uv[0]), "uv image not digest-pinned"


def test_two_stages_share_one_identical_base_reference() -> None:
    froms = _instructions("FROM")
    assert len(froms) == 2
    assert froms[0].upper().endswith(" AS BUILDER")
    final_base = froms[1].split()[1]
    builder_base = froms[0].split()[1]
    assert final_base == builder_base


def test_installs_use_uv_sync_without_dev_and_non_editable() -> None:
    syncs = [line for line in _instructions("RUN") if "uv sync" in line]
    assert len(syncs) == 2
    for line in syncs:
        assert "--no-dev" in line
        assert "--no-editable" in line
    assert sum("--frozen" in line for line in syncs) == 1
    assert sum("--locked" in line for line in syncs) == 1


def test_installs_never_pull_train_or_extra_groups() -> None:
    for line in _instructions("RUN"):
        if "uv sync" not in line:
            continue
        assert "train" not in line
        assert "--all-groups" not in line
        assert "--group" not in line
        assert "--extra" not in line


def test_only_the_runtime_inputs_are_copied() -> None:
    sources: list[str] = []
    for line in _instructions("COPY"):
        parts = line.split()[1:]
        flags = [p for p in parts if p.startswith("--")]
        args = [p for p in parts if not p.startswith("--")]
        if any(f.startswith("--from=ghcr.io/astral-sh/uv") for f in flags):
            continue
        if "--from=builder" in flags:
            assert args == ["/app/.venv", "/app/.venv"]
            sources.append("builder:/app/.venv")
            continue
        assert not flags, line
        sources.extend(args[:-1])
    assert sources == ["pyproject.toml", "uv.lock", "src", "builder:/app/.venv"]
    assert not _instructions("ADD")


def test_runs_as_exactly_one_non_root_user_with_uid_10001() -> None:
    users = _instructions("USER")
    assert len(users) == 1
    name = users[0].split()[1].split(":")[0]
    assert name not in {"root", "0"}
    assert re.search(r"useradd\b[^&]*--uid 10001\b", "\n".join(_instructions("RUN")))
    # USER comes after the venv copy and is in the final stage (after the second FROM).
    lines = _logical_lines()
    final_from = [i for i, line in enumerate(lines) if line.startswith("FROM ")][-1]
    assert lines.index(users[0]) > final_from


def test_healthcheck_probes_health_with_python_not_curl() -> None:
    checks = _instructions("HEALTHCHECK")
    assert len(checks) == 1
    check = checks[0]
    assert "/health" in check
    assert "/ready" not in check
    assert "curl" not in check
    assert "wget" not in check
    assert re.search(r'CMD \["python", "-c", ".*urllib\.request', check)


def test_cmd_is_the_exact_exec_form_with_the_proxy_header_flag() -> None:
    cmds = _instructions("CMD")
    # HEALTHCHECK lines carry their own CMD keyword but are a different instruction.
    assert len(cmds) == 1
    match = re.fullmatch(r"CMD (\[.*\])", cmds[0])
    assert match, cmds[0]
    parsed = json.loads(match.group(1))
    assert parsed == EXPECTED_CMD
    # D-10: uvicorn's own default proxy handling is disabled; only the in-app switch remains.
    assert parsed[-1] == "--no-proxy-headers"


def test_no_env_or_arg_carries_a_secret_or_demo_mode() -> None:
    # Phase 3 (D-29): the image must never bake in the database URL, the pseudonym key or the
    # collector's operator values either.
    forbidden = re.compile(
        r"KEY|SECRET|TOKEN|PASSWORD|GNEWS|DEMO_MODE|DATABASE_URL|PSEUDONYM|COLLECTOR", re.IGNORECASE
    )
    for line in (*_instructions("ENV"), *_instructions("ARG")):
        assert not forbidden.search(line), f"secret-like or DEMO_MODE setting: {line}"


def test_dockerfile_has_no_secret_looking_text_or_tabs() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "\t" not in text
    assert "\r" not in text
    assert not re.search(r"\b[0-9a-fA-F]{32}\b", text), "32-hex string in Dockerfile"


def test_dockerignore_excludes_the_sensitive_and_legacy_paths() -> None:
    entries = _dockerignore()
    required = {
        "legacy",
        "tests",
        "scripts",
        ".planning",
        ".claude",
        "*.md",
        ".git",
        ".venv",
        "**/__pycache__",
    }
    assert required <= entries, f"missing: {sorted(required - entries)}"
    assert any(entry.startswith(".env") for entry in entries), "no environment-file pattern"


def test_the_recorded_fixture_stays_out_of_the_image_while_no_runtime_code_reads_it() -> None:
    package = ROOT / "src" / "truthtrail"
    readers = [
        path.relative_to(ROOT).as_posix()
        for path in package.rglob("*.py")
        if "data/recorded" in path.read_text(encoding="utf-8")
        or '"recorded"' in path.read_text(encoding="utf-8")
    ]
    if not readers:
        assert "src/truthtrail/data/recorded" in _dockerignore()


def test_project_has_no_readme_key_so_dockerignored_markdown_cannot_break_the_build() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert "readme" not in project


# --- Phase 3: no ignore rule may hide the packaged runtime data (D-29) -----------------------
# Context-relative paths the image needs at runtime: readiness reads the migration head, the
# collector reads the allowlist, the news job reads the topics file.
RUNTIME_DATA = (
    "src/truthtrail/db/migrations/env.py",
    "src/truthtrail/db/migrations/versions/0001_baseline.py",
    "src/truthtrail/data/seed_domains.txt",
    "src/truthtrail/data/news_topics.toml",
)
# Files a later plan creates; the ignore rules are checked for them now, their existence then.
PENDING_RUNTIME_DATA = {"src/truthtrail/data/news_topics.toml": "plan 03-08"}
RECORDED_FIXTURE = "src/truthtrail/data/recorded/bluesky-2026-10-19.jsonl"


def _pattern_regex(pattern: str) -> re.Pattern[str]:
    """Docker's .dockerignore matching: anchored at the context root, ``*`` and ``?`` stay
    inside one path segment, ``**`` spans any number of segments."""
    segments = pattern.strip("/").split("/")
    regex = ""
    for index, segment in enumerate(segments):
        last = index == len(segments) - 1
        if segment == "**":
            # In the middle or at the start: zero or more whole segments; at the end: anything.
            regex += ".*" if last else "(?:.*/)?"
            continue
        for char in segment:
            if char == "*":
                regex += "[^/]*"
            elif char == "?":
                regex += "[^/]"
            else:
                regex += re.escape(char)
        if not last:
            regex += "/"
    return re.compile(regex + "$")


def hidden_by(entries: list[str], path: str) -> bool:
    """True when ``entries`` exclude ``path`` (a pattern matching a parent directory hides
    everything under it; a later ``!pattern`` re-includes; the last matching rule wins)."""
    segments = path.split("/")
    candidates = ["/".join(segments[: i + 1]) for i in range(len(segments))]
    hidden = False
    for entry in entries:
        negated = entry.startswith("!")
        regex = _pattern_regex(entry.removeprefix("!"))
        if any(regex.match(candidate) for candidate in candidates):
            hidden = not negated
    return hidden


def _ordered_entries() -> list[str]:
    text = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    return [
        line.strip()
        for line in text.split("\n")
        if line.strip() and not line.strip().startswith("#")
    ]


def test_no_ignore_rule_hides_the_packaged_migrations_or_runtime_data() -> None:
    entries = _ordered_entries()
    hidden = [path for path in RUNTIME_DATA if hidden_by(entries, path)]
    assert hidden == [], f"hidden from the image: {hidden}"
    for path in RUNTIME_DATA:
        exists = (ROOT / path).is_file()
        if path in PENDING_RUNTIME_DATA:
            assert not exists, (
                f"{path} now exists ({PENDING_RUNTIME_DATA[path]}): remove it from "
                "PENDING_RUNTIME_DATA so its existence is enforced"
            )
        else:
            assert exists, path


def test_the_ignore_matcher_is_not_blind() -> None:
    target = "src/truthtrail/db/migrations/env.py"
    for hiding in (
        "src",
        "src/truthtrail/db",
        "**/migrations",
        "**/*.py",
        "src/truthtrail/db/migrations/*.py",
        "src/*/db",
        "src/**",
        "src/**/env.py",
        "s?c",
    ):
        assert hidden_by([hiding], target), hiding
    for harmless in (
        "*.md",
        "scripts",
        "tests",
        "**/__pycache__",
        "migrations",
        "*.py",
        ".env*",
        "src/truthtrail/data/recorded",
        "src/**/versions",
        "s?",
    ):
        assert not hidden_by([harmless], target), harmless
    assert not hidden_by(["src", "!src/truthtrail/db/migrations"], target)
    assert hidden_by(["!src", "src/truthtrail"], target)


def test_the_recorded_fixture_ships_once_runtime_code_reads_it() -> None:
    """The mirror of the rule above: the fixture is hidden exactly while nothing reads it."""
    package = ROOT / "src" / "truthtrail"
    readers = [
        path
        for path in package.rglob("*.py")
        if "data/recorded" in path.read_text(encoding="utf-8")
        or '"recorded"' in path.read_text(encoding="utf-8")
    ]
    assert (ROOT / RECORDED_FIXTURE).is_file()
    assert hidden_by(_ordered_entries(), RECORDED_FIXTURE) is (not readers)
