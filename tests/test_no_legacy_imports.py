"""The live package must never reach the legacy simulator or user pools (D-01).

ROADMAP criterion 1: ``spread_simulator`` and ``users`` live in ``legacy/`` and are
unreachable from any route or import. Three independent proofs: a static AST walk
over every package file (with a negative control so it is not blind), a fresh
interpreter that imports ``truthtrail.main`` and inspects ``sys.modules``, and a
serving-only ``PYTHONPATH`` on which the legacy modules cannot even be found.
"""

import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = REPO_ROOT / "src" / "truthtrail"
FORBIDDEN = {"legacy", "spread_simulator", "users", "risk_analyzer"}
MIN_FILES = 8


def forbidden_imports(source: str) -> list[str]:
    """Return the forbidden module names ``source`` imports, statically or by a literal name."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN:
                    found.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module and node.module.split(".")[0] in FORBIDDEN:
                found.append(node.module)
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name in {"import_module", "__import__"} and node.args:
                first = node.args[0]
                if (
                    isinstance(first, ast.Constant)
                    and isinstance(first.value, str)
                    and first.value.split(".")[0] in FORBIDDEN
                ):
                    found.append(first.value)
    return found


def test_package_never_imports_legacy_modules() -> None:
    files = sorted(PACKAGE_ROOT.rglob("*.py"))
    assert len(files) >= MIN_FILES

    offenders = {
        str(path.relative_to(REPO_ROOT)): hits
        for path in files
        if (hits := forbidden_imports(path.read_text(encoding="utf-8")))
    }
    assert offenders == {}


def test_walker_flags_forbidden_imports() -> None:
    source = (
        "import spread_simulator\n"
        "from users import USERS\n"
        "import importlib\n"
        "importlib.import_module('risk_analyzer')\n"
        "__import__('legacy.users')\n"
    )
    assert forbidden_imports(source) == [
        "spread_simulator",
        "users",
        "risk_analyzer",
        "legacy.users",
    ]
    assert forbidden_imports("from . import users\nimport json\n") == []


def _serving_env(subprocess_env: dict[str, str]) -> dict[str, str]:
    """Environment whose PYTHONPATH is the src directory only: never the repo root or legacy."""
    return {**subprocess_env, "PYTHONPATH": str(PACKAGE_ROOT.parent)}


def test_importing_the_app_loads_no_legacy_module(
    tmp_path: Path, subprocess_env: dict[str, str]
) -> None:
    code = (
        "import sys\n"
        "import truthtrail.main\n"
        f"loaded = sorted(n for n in {sorted(FORBIDDEN)!r} if n in sys.modules)\n"
        "sys.exit(1 if loaded else 0)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=_serving_env(subprocess_env),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


def test_legacy_modules_are_not_findable_on_the_serving_path(
    tmp_path: Path, subprocess_env: dict[str, str]
) -> None:
    code = (
        "import importlib.util, sys\n"
        f"found = [n for n in {sorted(FORBIDDEN)!r} if importlib.util.find_spec(n) is not None]\n"
        "sys.exit(1 if found else 0)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=_serving_env(subprocess_env),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
