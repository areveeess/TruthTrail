"""Layer import rules of the package, enforced statically and in a fresh interpreter (D-31).

The walker resolves absolute and relative imports (and literal ``import_module`` calls) of every
file under ``src/truthtrail`` to dotted module names; the rules are data, so plans 03-06 to 03-08
and 03-12 add rows (enrich purity, jobs, api forbidden imports) without touching the walker. Each
rule has a negative control that feeds the walker bad source text, and a file-count floor keeps
the walk from going blind. A fresh interpreter proves that importing the application loads no
ingest module and no websockets: the API process never holds the pseudonymiser (T-03-28).
"""

import ast
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
PACKAGE_ROOT = SRC_ROOT / "truthtrail"
MIN_FILES = 35


@dataclass(frozen=True)
class Rule:
    """Modules matching ``within`` (a package prefix or exact module) must import none of
    ``forbidden`` (each a module or a package prefix)."""

    name: str
    within: tuple[str, ...]
    forbidden: tuple[str, ...]


PURE_INGEST = (
    "truthtrail.ingest.pseudonym",
    "truthtrail.ingest.selection",
    "truthtrail.ingest.dialect",
    "truthtrail.ingest.normalise",
)

FORBIDDEN: tuple[Rule, ...] = (
    Rule(
        "core imports no higher layer",
        ("truthtrail.core",),
        (
            "truthtrail.api",
            "truthtrail.services",
            "truthtrail.schemas",
            "truthtrail.db",
            "truthtrail.ingest",
            "truthtrail.enrich",
            "truthtrail.jobs",
        ),
    ),
    Rule(
        "ingest never imports api, jobs or enrich",
        ("truthtrail.ingest",),
        ("truthtrail.api", "truthtrail.jobs", "truthtrail.enrich"),
    ),
    Rule(
        "api never imports ingest (the API process never holds the pseudonymiser)",
        ("truthtrail.api",),
        ("truthtrail.ingest",),
    ),
    Rule(
        "pure ingest modules import nothing from db",
        PURE_INGEST,
        ("truthtrail.db",),
    ),
)


def module_name(path: Path) -> str:
    """Dotted module name of a file under ``src`` (a package ``__init__`` is the package)."""
    parts = list(path.relative_to(SRC_ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _is_package(path: Path | None) -> bool:
    return path is not None and path.name == "__init__.py"


def imported_modules(source: str, module: str, *, is_package: bool = False) -> set[str]:
    """Every module ``source`` imports, resolved to dotted names.

    ``from X import name`` adds both ``X`` and ``X.name`` (the name may be a submodule), and a
    relative import is resolved against ``module``'s package.
    """
    package = module if is_package else module.rpartition(".")[0]
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".") if package else []
                keep = len(parts) - (node.level - 1)
                if keep < 0:
                    continue
                base = ".".join(parts[:keep])
                target = ".".join(p for p in (base, node.module or "") if p)
            else:
                target = node.module or ""
            if target:
                found.add(target)
            found.update(f"{target}.{alias.name}" if target else alias.name for alias in node.names)
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name in {"import_module", "__import__"} and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    found.add(first.value)
    return found


def _matches(name: str, prefixes: Iterable[str]) -> bool:
    return any(name == p or name.startswith(p + ".") for p in prefixes)


def violations(source: str, module: str, *, is_package: bool = False) -> list[str]:
    """``rule: imported module`` for every rule the source text of ``module`` breaks."""
    imported = imported_modules(source, module, is_package=is_package)
    hits: list[str] = []
    for rule in FORBIDDEN:
        if not _matches(module, rule.within):
            continue
        hits.extend(
            f"{rule.name}: {name}" for name in sorted(imported) if _matches(name, rule.forbidden)
        )
    return hits


def package_files() -> list[Path]:
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def test_the_package_follows_every_layer_rule() -> None:
    files = package_files()
    assert len(files) >= MIN_FILES
    offenders = {
        module_name(path): hits
        for path in files
        if (
            hits := violations(
                path.read_text(encoding="utf-8"), module_name(path), is_package=_is_package(path)
            )
        )
    }
    assert offenders == {}


def test_every_rule_governs_at_least_one_existing_module() -> None:
    modules = [module_name(path) for path in package_files()]
    for rule in FORBIDDEN:
        assert any(_matches(m, rule.within) for m in modules), rule.name


@pytest.mark.parametrize(
    ("module", "source", "forbidden"),
    [
        ("truthtrail.core.cascade", "from truthtrail.api import app\n", "truthtrail.api"),
        ("truthtrail.core.policy", "import truthtrail.db.engine\n", "truthtrail.db.engine"),
        ("truthtrail.core.config", "from ..ingest import pseudonym\n", "truthtrail.ingest"),
        (
            "truthtrail.core.boot",
            "from truthtrail.schemas.models import Meta\n",
            "truthtrail.schemas.models",
        ),
        (
            "truthtrail.core.errors",
            "import importlib\nimportlib.import_module('truthtrail.jobs')\n",
            "truthtrail.jobs",
        ),
        ("truthtrail.core.readiness", "from truthtrail import services\n", "truthtrail.services"),
        (
            "truthtrail.core.cascade",
            "from truthtrail.enrich.resolve import x\n",
            "truthtrail.enrich.resolve",
        ),
        (
            "truthtrail.ingest.source",
            "from truthtrail.api.app import create_app\n",
            "truthtrail.api.app",
        ),
        ("truthtrail.ingest.normalise", "from ..jobs import news\n", "truthtrail.jobs"),
        ("truthtrail.ingest.writer", "import truthtrail.enrich\n", "truthtrail.enrich"),
        (
            "truthtrail.api.v1",
            "from truthtrail.ingest.pseudonym import make_keyer\n",
            "truthtrail.ingest.pseudonym",
        ),
        ("truthtrail.api.app", "from ..ingest import source\n", "truthtrail.ingest"),
        ("truthtrail.ingest.dialect", "from truthtrail.db import models\n", "truthtrail.db"),
        (
            "truthtrail.ingest.selection",
            "from ..db.engine import create_db_engine\n",
            "truthtrail.db.engine",
        ),
        ("truthtrail.ingest.pseudonym", "import truthtrail.db\n", "truthtrail.db"),
    ],
)
def test_the_walker_flags_each_rule(module: str, source: str, forbidden: str) -> None:
    hits = violations(source, module)
    assert any(hit.endswith(": " + forbidden) for hit in hits), hits


def test_the_walker_resolves_relative_imports_and_packages() -> None:
    assert "truthtrail.ingest.dialect" in imported_modules(
        "from .dialect import classify_frame\n", "truthtrail.ingest.normalise"
    )
    assert "truthtrail.ingest.dialect" in imported_modules(
        "from .dialect import x\n", "truthtrail.ingest", is_package=True
    )
    assert "truthtrail.core" in imported_modules("from .. import core\n", "truthtrail.api.app")
    assert imported_modules("from ....... import x\n", "truthtrail.api.app") == set()


def test_allowed_imports_are_not_flagged() -> None:
    assert (
        violations(
            "from truthtrail.core.config import ConfigurationError\n", "truthtrail.ingest.pseudonym"
        )
        == []
    )
    assert violations("from truthtrail.db import models\n", "truthtrail.ingest.writer") == []
    assert violations("from truthtrail.api import app\n", "truthtrail.services.gnews") == []
    assert violations("import truthtrail.ingestion_notes\n", "truthtrail.api.v1") == []
    assert violations("from truthtrail.core import cascade\n", "truthtrail.api.app") == []


def test_importing_the_app_loads_no_ingest_module_and_no_websockets(
    tmp_path: Path, subprocess_env: dict[str, str]
) -> None:
    code = (
        "import sys\n"
        "import truthtrail.main\n"
        "from truthtrail.api.app import create_app\n"
        "create_app()\n"
        "roots = ('truthtrail.ingest', 'websockets')\n"
        "loaded = sorted(n for n in sys.modules if n in roots or n.startswith(roots[0] + '.') "
        "or n.startswith(roots[1] + '.'))\n"
        "print(len(loaded))\n"
        "sys.exit(1 if loaded else 0)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={**subprocess_env, "PYTHONPATH": str(SRC_ROOT)},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "0"


def test_the_fresh_interpreter_check_is_not_blind(
    tmp_path: Path, subprocess_env: dict[str, str]
) -> None:
    code = (
        "import sys\n"
        "import truthtrail.ingest.dialect\n"
        "print(sum(1 for n in sys.modules if n.startswith('truthtrail.ingest')))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={**subprocess_env, "PYTHONPATH": str(SRC_ROOT)},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert int(result.stdout.strip()) >= 2
