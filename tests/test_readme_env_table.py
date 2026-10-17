"""Documentation must not drift from configuration: the README names every variable.

The example environment file is the list of supported variables; each one has to appear in the
README, together with the commands a new developer needs.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
EXAMPLE_ENV = ROOT / ".env.example"

REQUIRED_STRINGS = (
    "flag for human review",
    "uv sync",
    "winget",
    "uvicorn main:app",
    "--no-proxy-headers",
    "/health",
    "/ready",
    "/v1",
)


def _env_names() -> list[str]:
    names = []
    for line in EXAMPLE_ENV.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        names.append(stripped.split("=", 1)[0].strip())
    return names


def test_example_environment_file_lists_ten_names() -> None:
    assert len(_env_names()) == 10


def test_every_environment_name_appears_in_the_readme() -> None:
    text = README.read_text(encoding="utf-8")
    missing = [name for name in _env_names() if name not in text]
    assert not missing, f"README does not mention: {missing}"


def test_readme_contains_the_required_commands_and_endpoints() -> None:
    text = README.read_text(encoding="utf-8")
    missing = [needle for needle in REQUIRED_STRINGS if needle not in text]
    assert not missing, f"README is missing: {missing}"
