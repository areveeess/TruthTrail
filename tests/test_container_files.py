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
    forbidden = re.compile(r"KEY|SECRET|TOKEN|PASSWORD|GNEWS|DEMO_MODE", re.IGNORECASE)
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


def test_project_has_no_readme_key_so_dockerignored_markdown_cannot_break_the_build() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert "readme" not in project
