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
    ``forbidden`` (each a module or a package prefix); modules listed in ``allowed`` (exact
    names) are the deliberate exceptions."""

    name: str
    within: tuple[str, ...]
    forbidden: tuple[str, ...]
    allowed: tuple[str, ...] = ()


PURE_INGEST = (
    "truthtrail.ingest.pseudonym",
    "truthtrail.ingest.selection",
    "truthtrail.ingest.dialect",
    "truthtrail.ingest.normalise",
)

# Plan 03-06 (D-22): the pure resolver and rollup import only the standard library and
# truthtrail.core (and each other); test_pure_enrich_modules_import_only_stdlib_and_core
# enforces the positive list, the rule below the layer table.
PURE_ENRICH = ("truthtrail.enrich.resolve", "truthtrail.enrich.rollup")
PURE_ENRICH_ALLOWED = ("truthtrail.core", *PURE_ENRICH)

# The ONE named exemption from the api news rule: the legacy /analyze router, retired in plan
# 03-11; plan 03-12 empties this tuple. test_the_api_news_exemption_cannot_grow pins it.
API_NEWS_EXEMPT = ("truthtrail.api.analyze",)

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
        "api never imports jobs, enrich or websockets (plan 03-07, D-31)",
        ("truthtrail.api",),
        ("truthtrail.jobs", "truthtrail.enrich", "websockets"),
    ),
    Rule(
        "api never reaches the news client (plan 03-07, D-26, D-31)",
        ("truthtrail.api",),
        ("truthtrail.services.gnews", "requests"),
        allowed=API_NEWS_EXEMPT,
    ),
    Rule(
        "pure ingest modules import nothing from db",
        PURE_INGEST,
        ("truthtrail.db",),
    ),
    Rule(
        "pure enrich modules import nothing from db, api, ingest, jobs, services or schemas",
        PURE_ENRICH,
        (
            "truthtrail.db",
            "truthtrail.api",
            "truthtrail.ingest",
            "truthtrail.jobs",
            "truthtrail.services",
            "truthtrail.schemas",
            "sqlalchemy",
            "psycopg",
        ),
    ),
    Rule(
        "enrich never imports api or ingest (plan 03-06)",
        ("truthtrail.enrich",),
        ("truthtrail.api", "truthtrail.ingest"),
    ),
    Rule(
        "only the live Jetstream source imports websockets (plan 03-05)",
        ("truthtrail",),
        ("websockets",),
        allowed=("truthtrail.ingest.source",),
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
        if not _matches(module, rule.within) or module in rule.allowed:
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
        ("truthtrail.ingest.run", "import websockets\n", "websockets"),
        (
            "truthtrail.ingest.writer",
            "from websockets.asyncio.client import connect\n",
            "websockets.asyncio.client",
        ),
        ("truthtrail.api.app", "from websockets import exceptions\n", "websockets"),
        ("truthtrail.enrich.resolve", "from truthtrail.db import models\n", "truthtrail.db"),
        ("truthtrail.enrich.rollup", "import sqlalchemy\n", "sqlalchemy"),
        (
            "truthtrail.enrich.resolve",
            "from ..ingest.pseudonym import make_keyer\n",
            "truthtrail.ingest.pseudonym",
        ),
        ("truthtrail.enrich.rollup", "from truthtrail import jobs\n", "truthtrail.jobs"),
        (
            "truthtrail.enrich.resolve",
            "import truthtrail.services.gnews\n",
            "truthtrail.services.gnews",
        ),
        (
            "truthtrail.enrich.rollup",
            "from truthtrail.schemas.models import Event\n",
            "truthtrail.schemas.models",
        ),
        ("truthtrail.enrich.apply", "from truthtrail.api import app\n", "truthtrail.api"),
        ("truthtrail.enrich.purge", "from ..ingest import writer\n", "truthtrail.ingest"),
        (
            "truthtrail.ingest.run",
            "from truthtrail.enrich.apply import x\n",
            "truthtrail.enrich.apply",
        ),
        ("truthtrail.api.v1_cascades", "from truthtrail.jobs import news\n", "truthtrail.jobs"),
        (
            "truthtrail.api.v1_stats",
            "from truthtrail.enrich.resolve import resolve_cascade\n",
            "truthtrail.enrich.resolve",
        ),
        ("truthtrail.api.v1_deps", "import websockets\n", "websockets"),
        (
            "truthtrail.api.v1_cascades",
            "from truthtrail.services.gnews import fetch_news\n",
            "truthtrail.services.gnews",
        ),
        ("truthtrail.api.app", "import requests\n", "requests"),
        ("truthtrail.api.db_errors", "from ..services import gnews\n", "truthtrail.services.gnews"),
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
    assert violations("import websockets\n", "truthtrail.ingest.source") == []
    assert violations("import websocketsx\n", "truthtrail.ingest.run") == []


def test_the_api_news_exemption_cannot_grow() -> None:
    """Only the legacy /analyze router may import the news client until plan 03-12."""
    exempt = {
        name for rule in FORBIDDEN for name in rule.allowed if _matches(name, ("truthtrail.api",))
    }
    assert exempt == {"truthtrail.api.analyze"}
    news_rule = next(rule for rule in FORBIDDEN if "news client" in rule.name)
    assert news_rule.allowed == API_NEWS_EXEMPT == ("truthtrail.api.analyze",)


def test_the_exemption_is_only_for_the_news_rule() -> None:
    # The exempt module is still bound by every other api rule.
    hits = violations("from truthtrail.enrich import apply\n", "truthtrail.api.analyze")
    assert any("enrich" in hit for hit in hits), hits
    assert (
        violations("from truthtrail.services.gnews import fetch_news\n", "truthtrail.api.analyze")
        == []
    )


def non_pure_enrich_imports(source: str, module: str) -> list[str]:
    """Imports of a pure enrich module outside the standard library and its allowed list."""
    offenders: list[str] = []
    for name in sorted(imported_modules(source, module)):
        top = name.partition(".")[0]
        if top == "truthtrail":
            if not _matches(name, PURE_ENRICH_ALLOWED):
                offenders.append(name)
        elif top not in sys.stdlib_module_names:
            offenders.append(name)
    return offenders


def test_pure_enrich_modules_import_only_stdlib_and_core() -> None:
    for module in PURE_ENRICH:
        path = PACKAGE_ROOT.joinpath(*module.split(".")[1:]).with_suffix(".py")
        assert path.is_file(), module
        assert non_pure_enrich_imports(path.read_text(encoding="utf-8"), module) == []


@pytest.mark.parametrize(
    "source",
    [
        "import sqlalchemy\n",
        "from hypothesis import given\n",
        "from truthtrail.enrich.apply import enrich_dirty\n",
        "from ..db.locks import ENRICH_LOCK_KEY\n",
        "import truthtrail.ingest\n",
    ],
)
def test_the_pure_enrich_check_is_not_blind(source: str) -> None:
    assert non_pure_enrich_imports(source, "truthtrail.enrich.resolve") != []


def test_the_pure_enrich_check_allows_stdlib_core_and_siblings() -> None:
    source = (
        "from collections.abc import Iterable\n"
        "from datetime import UTC\n"
        "from truthtrail.core.cascade import order_events\n"
        "from truthtrail.enrich.rollup import Rollup\n"
    )
    assert non_pure_enrich_imports(source, "truthtrail.enrich.resolve") == []


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
