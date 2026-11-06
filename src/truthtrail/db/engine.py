"""The engine factory (D-19, D-25 groundwork; RESEARCH Pattern 9, F-09, F-15, pitfalls 14 and 15).

``create_db_engine`` builds a new SQLAlchemy engine on every call and this module holds no
engine or other state. Engines are built per app (in the lifespan) or per command, and the
owner disposes them; tests build theirs through the ``make_engine`` fixture, which registers
``dispose`` as a finalizer (``filterwarnings = error`` turns a leaked connection into a failure).

Timeouts (D-19) bound every way the database can hang a caller: a pool checkout waits at most
``POOL_TIMEOUT_SECONDS`` (then ``sqlalchemy.exc.TimeoutError``, which is NOT a DBAPIError), a
connect at most ``CONNECT_TIMEOUT_SECONDS``, a statement the role's timeout and a lock wait
``LOCK_TIMEOUT_MS`` (both then psycopg ``QueryCanceled`` inside ``OperationalError``).

Every new connection runs ``SET TIME ZONE 'UTC'`` and commits: ``PGTZ`` and the cluster default
(the OS zone on Windows) win over a ``-c timezone`` connect option, and psycopg returns
``timestamptz`` values in the session zone (F-15). No timestamp query may use ``date_trunc`` or
``extract``, which depend on the session zone; use ``date_bin`` with an explicit origin (plan
03-07 enforces it with an AST test).
"""

from typing import Any, Literal

from pydantic import SecretStr
from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL, Engine

from truthtrail.db.url import normalise_database_url

Role = Literal["api", "collector", "jobs"]

# D-19: bounded waits everywhere. A request handler fails fast; batch work gets longer
# statements but the same lock bound.
POOL_TIMEOUT_SECONDS = 2
CONNECT_TIMEOUT_SECONDS = 3
LOCK_TIMEOUT_MS = 2000
STATEMENT_TIMEOUT_MS: dict[str, int] = {"api": 5000, "collector": 30000, "jobs": 30000}


def _set_utc_session(dbapi_connection: Any, _connection_record: Any) -> None:
    """``connect`` event: pin the session time zone to UTC on every new DBAPI connection."""
    with dbapi_connection.cursor() as cursor:
        cursor.execute("SET TIME ZONE 'UTC'")
    dbapi_connection.commit()


def _timeout_options(statement_timeout_ms: int, url: URL) -> str:
    """The libpq ``options`` string: integers only, never SQL. Options already in the URL
    (for example a hosted pooler's endpoint option) are kept in front."""
    ours = f"-c statement_timeout={statement_timeout_ms} -c lock_timeout={LOCK_TIMEOUT_MS}"
    existing = url.query.get("options")
    if isinstance(existing, str) and existing.strip():
        return f"{existing.strip()} {ours}"
    return ours


def create_db_engine(
    url: str | SecretStr | URL,
    *,
    role: Role = "api",
    pool_size: int = 5,
    max_overflow: int = 5,
    statement_timeout_ms: int | None = None,
) -> Engine:
    """Build a new engine for ``url`` with the D-19 pool, timeouts and UTC session.

    ``statement_timeout_ms`` overrides the role's statement timeout; it exists for tests that
    provoke a timeout with a few hundred milliseconds (never 1 ms: a tiny value cancels
    SQLAlchemy's first-connect initialisation query, RESEARCH pitfall 14).
    """
    if role not in STATEMENT_TIMEOUT_MS:
        raise ValueError("role must be api, collector or jobs")
    timeout_ms = (
        STATEMENT_TIMEOUT_MS[role] if statement_timeout_ms is None else statement_timeout_ms
    )
    if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int) or timeout_ms <= 0:
        raise ValueError("statement_timeout_ms must be a positive integer")
    normalised = normalise_database_url(url)
    engine = create_engine(
        normalised,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=POOL_TIMEOUT_SECONDS,
        connect_args={
            "connect_timeout": CONNECT_TIMEOUT_SECONDS,
            "options": _timeout_options(timeout_ms, normalised),
        },
    )
    event.listen(engine, "connect", _set_utc_session)
    return engine
