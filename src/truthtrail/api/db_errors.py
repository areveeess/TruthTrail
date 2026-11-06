"""Database failures rendered with the frozen Phase 1 error contract (D-25, FND-02, T-03-45).

- ``sqlalchemy.exc.OperationalError`` whose driver error carries SQLSTATE 57014 (statement
  timeout, ``QueryCanceled``) or 55P03 (lock timeout, ``LockNotAvailable``) is a 503
  ``database_timeout``;
- any other ``OperationalError`` (refused connection, missing socket, a database that does not
  accept connections, a dropped session) and ``sqlalchemy.exc.TimeoutError`` (pool exhaustion,
  which is NOT a ``DBAPIError``, RESEARCH pitfall 15) are a 503 ``database_unavailable``.

Both carry ``Retry-After: 5``, ``upstream: "database"`` and ``source_status`` equal to the code.
Every other database error (an integrity or programming error: the database answered, so it is
our bug) is not handled here and reaches the catch-all middleware as the generic 500
``internal_error``. The text of a connection error carries the host or socket path, so the body
uses fixed wording and the log line carries only the exception class name.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from truthtrail.core.errors import problem_body, problem_response

logger = logging.getLogger(__name__)

RETRY_AFTER_SECONDS = 5
TIMEOUT_SQLSTATES = frozenset({"57014", "55P03"})
UNAVAILABLE = "database_unavailable"
TIMEOUT = "database_timeout"
DETAIL = {
    UNAVAILABLE: "The database is temporarily unavailable.",
    TIMEOUT: "The database did not answer in time.",
}


def _database_problem(code: str) -> JSONResponse:
    body = problem_body(503, DETAIL[code], code, source_status=code, upstream="database")
    return problem_response(503, body, {"Retry-After": str(RETRY_AFTER_SECONDS)})


def classify_operational_error(exc: OperationalError) -> str:
    """``database_timeout`` for a statement or lock timeout, else ``database_unavailable``."""
    sqlstate = getattr(exc.orig, "sqlstate", None)
    return TIMEOUT if sqlstate in TIMEOUT_SQLSTATES else UNAVAILABLE


async def _operational_error_handler(request: Request, exc: OperationalError) -> JSONResponse:
    code = classify_operational_error(exc)
    logger.error("%s: %s", code, type(exc).__name__)
    return _database_problem(code)


async def _pool_timeout_handler(request: Request, exc: PoolTimeoutError) -> JSONResponse:
    logger.error("%s: %s", UNAVAILABLE, type(exc).__name__)
    return _database_problem(UNAVAILABLE)


def register_db_error_handlers(app: FastAPI) -> None:
    """Install the two database handlers (Starlette selects a handler by exception MRO)."""
    app.exception_handler(OperationalError)(_operational_error_handler)
    app.exception_handler(PoolTimeoutError)(_pool_timeout_handler)
