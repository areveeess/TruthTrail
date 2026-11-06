"""All SQL in the package is parameterised, and no query depends on the session time zone
(D-19, D-31, RESEARCH F-15, threat T-03-16).

An AST walk over every ``src/truthtrail/**/*.py`` file fails on:

(a) an f-string, a percent-format expression or a ``.format()`` call used as an argument of
    ``text(...)`` (including an alias such as ``from sqlalchemy import text as sql_text``),
    ``.execute(...)`` or ``.exec_driver_sql(...)``: values travel as bound parameters only;
(b) ``date_trunc(`` or ``extract(`` inside a string constant passed to those calls, and any
    ``func.date_trunc`` / ``func.extract`` attribute or ``sqlalchemy.extract`` import: both
    depend on the session time zone; timeline buckets use ``date_bin`` with an explicit origin.

Negative controls feed the walker bad source text and expect findings, and a file-count floor
keeps the walk from going blind. Every later module is covered automatically.
"""

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = REPO_ROOT / "src" / "truthtrail"
MIN_FILES = 30
SQL_CALLS = {"text", "execute", "exec_driver_sql"}
ZONE_FUNCTIONS = {"date_trunc", "extract"}
ZONE_IN_SQL = re.compile(r"\b(date_trunc|extract)\s*\(", re.IGNORECASE)


def _text_aliases(tree: ast.AST) -> set[str]:
    """Local names bound to ``sqlalchemy.text`` (``from sqlalchemy import text as x``)."""
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("sqlalchemy"):
            for alias in node.names:
                if alias.name == "text":
                    aliases.add(alias.asname or alias.name)
    return aliases


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _is_dynamic_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.JoinedStr):
        return "f-string"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        return "percent-format"
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "format"
    ):
        return "format()"
    return None


def sql_findings(source: str) -> list[str]:
    """Return one ``rule: call at line N`` string per violation in ``source``."""
    tree = ast.parse(source)
    sql_names = SQL_CALLS | _text_aliases(tree)
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("sqlalchemy"):
            for alias in node.names:
                if alias.name in ZONE_FUNCTIONS:
                    findings.append(f"zone-dependent import {alias.name} at line {node.lineno}")
        if (
            isinstance(node, ast.Attribute)
            and node.attr in ZONE_FUNCTIONS
            and (
                (isinstance(node.value, ast.Name) and node.value.id == "func")
                or (isinstance(node.value, ast.Attribute) and node.value.attr == "func")
            )
        ):
            findings.append(f"func.{node.attr} at line {node.lineno}")
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name not in sql_names:
            continue
        for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
            kind = _is_dynamic_string(argument)
            if kind is not None:
                findings.append(f"{kind} in {name}() at line {node.lineno}")
            for inner in ast.walk(argument):
                if (
                    isinstance(inner, ast.Constant)
                    and isinstance(inner.value, str)
                    and ZONE_IN_SQL.search(inner.value)
                ):
                    findings.append(f"date_trunc/extract in {name}() at line {node.lineno}")
    return findings


def _package_files() -> list[Path]:
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def test_package_sql_is_parameterised_and_zone_independent() -> None:
    files = _package_files()
    assert len(files) >= MIN_FILES, f"walk went blind: {len(files)} files"
    offenders = {
        str(path.relative_to(REPO_ROOT)): hits
        for path in files
        if (hits := sql_findings(path.read_text(encoding="utf-8")))
    }
    assert offenders == {}


def test_the_walk_covers_the_database_layer_and_the_migrations() -> None:
    names = {path.relative_to(PACKAGE_ROOT).as_posix() for path in _package_files()}
    assert {
        "db/models.py",
        "db/engine.py",
        "db/migrations/env.py",
        "db/migrations/versions/0001_baseline.py",
    } <= names


def test_walker_flags_f_strings_in_text_and_execute() -> None:
    source = (
        "from sqlalchemy import text\n"
        "def q(conn, name):\n"
        "    conn.execute(text(f'SELECT * FROM t WHERE n = {name}'))\n"
        "    conn.execute(f'DELETE FROM t WHERE n = {name}')\n"
    )
    assert sorted(sql_findings(source)) == [
        "f-string in execute() at line 4",
        "f-string in text() at line 3",
    ]


def test_walker_flags_percent_and_format() -> None:
    source = (
        "import sqlalchemy as sa\n"
        "def q(conn, n):\n"
        "    conn.execute(sa.text('SELECT %s' % n))\n"
        "    conn.exec_driver_sql('SELECT {}'.format(n))\n"
        "    conn.execute(statement=sa.text('SELECT {}'.format(n)))\n"
    )
    assert sorted(sql_findings(source)) == [
        "format() in exec_driver_sql() at line 4",
        "format() in text() at line 5",
        "percent-format in text() at line 3",
    ]


def test_walker_follows_text_aliases() -> None:
    source = (
        "from sqlalchemy import text as sql_text\ndef q(n):\n    return sql_text(f'SELECT {n}')\n"
    )
    assert sql_findings(source) == ["f-string in sql_text() at line 3"]


def test_walker_flags_zone_dependent_functions() -> None:
    source = (
        "from sqlalchemy import func, extract, text\n"
        "import sqlalchemy as sa\n"
        "def q(conn):\n"
        "    conn.execute(text(\"SELECT date_trunc('day', observed_at) FROM events\"))\n"
        "    conn.execute(text('SELECT EXTRACT (epoch FROM observed_at) FROM events'))\n"
        "    return func.date_trunc('day', 1), sa.func.extract('epoch', 1)\n"
    )
    assert sorted(sql_findings(source)) == [
        "date_trunc/extract in execute() at line 4",
        "date_trunc/extract in execute() at line 5",
        "date_trunc/extract in text() at line 4",
        "date_trunc/extract in text() at line 5",
        "func.date_trunc at line 6",
        "func.extract at line 6",
        "zone-dependent import extract at line 1",
    ]


def test_walker_accepts_bound_parameters_and_date_bin() -> None:
    source = (
        "from sqlalchemy import text\n"
        "Q = text(\"SELECT date_bin('5 minutes', observed_at, :origin) FROM events\")\n"
        "def q(conn, uri):\n"
        "    conn.execute(text('SELECT id FROM events WHERE uri = :uri'), {'uri': uri})\n"
        "    conn.execute(Q, {'origin': 0})\n"
        "    label = f'not sql {uri}'\n"
        "    return label, 'extracted text'\n"
    )
    assert sql_findings(source) == []
