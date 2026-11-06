"""DATABASE_URL normalisation (D-19, T-03-09): pure, no database.

A distinctive marker password must never appear in an exception message, a ``repr`` or ``str``
of a URL or engine, or the log.
"""

import ast
import logging
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy.engine import URL

from truthtrail.core.config import ConfigurationError
from truthtrail.db.engine import create_db_engine
from truthtrail.db.url import SCHEME_ERROR, describe_database_url, normalise_database_url

ROOT = Path(__file__).resolve().parent.parent
PW_MARK = "Pw-Mark-7Qz4"
EXPECTED_ERROR = (
    "DATABASE_URL must use the postgresql://, postgres:// or postgresql+psycopg:// scheme"
)


@pytest.mark.parametrize(
    "raw",
    [
        "postgresql://tt@db.example.org:5432/truthtrail",
        "postgres://tt@db.example.org:5432/truthtrail",
        "postgresql+psycopg://tt@db.example.org:5432/truthtrail",
        "POSTGRESQL://tt@db.example.org:5432/truthtrail",
        "Postgres://tt@db.example.org:5432/truthtrail",
        "  postgresql://tt@db.example.org:5432/truthtrail  ",
    ],
)
def test_accepted_schemes_map_to_the_psycopg_dialect(raw: str) -> None:
    url = normalise_database_url(raw)
    assert url.drivername == "postgresql+psycopg"
    assert url.host == "db.example.org"
    assert url.port == 5432
    assert url.database == "truthtrail"
    assert url.username == "tt"


def test_unix_socket_query_is_kept() -> None:
    url = normalise_database_url("postgresql://postgres@/postgres?host=/tmp/tt-pg-x&port=5999")
    assert url.drivername == "postgresql+psycopg"
    assert url.query == {"host": "/tmp/tt-pg-x", "port": "5999"}


def test_encoded_password_survives() -> None:
    url = normalise_database_url("postgresql://tt:p%40ss%25w0rd@db.example.org/truthtrail")
    assert url.password == "p@ss%w0rd"


def test_secretstr_and_url_inputs_are_accepted() -> None:
    raw = "postgres://tt@db.example.org/truthtrail"
    assert normalise_database_url(SecretStr(raw)).drivername == "postgresql+psycopg"
    parsed = URL.create("postgresql", username="tt", host="db.example.org", database="d")
    assert normalise_database_url(parsed).drivername == "postgresql+psycopg"


@pytest.mark.parametrize(
    "raw",
    [
        f"mysql://tt:{PW_MARK}@db.example.org/truthtrail",
        f"sqlite:///tmp/{PW_MARK}.db",
        f"postgresql+asyncpg://tt:{PW_MARK}@db.example.org/truthtrail",
        f"http://tt:{PW_MARK}@db.example.org/",
        "",
        "   ",
        f"not a url {PW_MARK}",
        f"{PW_MARK}",
    ],
)
def test_other_values_are_rejected_with_fixed_text(raw: str) -> None:
    with pytest.raises(ConfigurationError) as info:
        normalise_database_url(raw)
    assert str(info.value) == EXPECTED_ERROR == SCHEME_ERROR
    assert PW_MARK not in repr(info.value)
    # No chained exception that could carry the value (SQLAlchemy's parse error repeats it).
    assert info.value.__cause__ is None
    assert info.value.__context__ is None or info.value.__suppress_context__ is True


def test_marker_password_never_appears_in_renderings(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    raw = f"postgres://tt:{PW_MARK}@db.example.org:5432/truthtrail"
    url = normalise_database_url(raw)
    assert url.password == PW_MARK
    for rendering in (str(url), repr(url), describe_database_url(url)):
        assert PW_MARK not in rendering
    engine = create_db_engine(raw)  # building an engine does not connect
    try:
        assert PW_MARK not in repr(engine)
        assert PW_MARK not in str(engine.url)
    finally:
        engine.dispose()
    with pytest.raises(ConfigurationError) as info:
        normalise_database_url(f"mysql://tt:{PW_MARK}@db.example.org/truthtrail")
    assert PW_MARK not in str(info.value)
    assert PW_MARK not in caplog.text


@pytest.mark.parametrize("bad", [0, -5, True, 2.5])
def test_statement_timeout_override_must_be_a_positive_integer(bad: object) -> None:
    with pytest.raises(ValueError, match="statement_timeout_ms"):
        create_db_engine(
            "postgresql://tt@db.example.org/truthtrail",
            statement_timeout_ms=bad,  # type: ignore[arg-type]
        )


def test_unknown_role_is_rejected() -> None:
    with pytest.raises(ValueError, match="role"):
        create_db_engine("postgresql://tt@db.example.org/truthtrail", role="admin")  # type: ignore[arg-type]


def test_engine_factory_rejects_a_bad_scheme_before_building() -> None:
    with pytest.raises(ConfigurationError):
        create_db_engine(f"mysql://tt:{PW_MARK}@db.example.org/truthtrail")


def test_no_module_level_engine_and_one_factory() -> None:
    """``create_engine`` is called only inside ``create_db_engine``; nothing builds an engine at
    import time anywhere in the package."""
    package = ROOT / "src" / "truthtrail"
    offenders = []
    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                # Raw engine construction only inside the factory. Calling the factory itself
                # from a function (a lifespan, a command) is the intended use; calling it at
                # module level is caught by the loop below.
                if name in {"create_engine", "engine_from_config"}:
                    relative = path.relative_to(package).as_posix()
                    if relative != "db/engine.py":
                        offenders.append(f"{relative}:{node.lineno}")
        for statement in tree.body:  # module level
            if isinstance(statement, ast.Assign | ast.AnnAssign) and isinstance(
                statement.value, ast.Call
            ):
                func = statement.value.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                assert "engine" not in name.lower(), path
    assert offenders == []
