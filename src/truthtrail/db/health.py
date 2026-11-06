"""The fail-closed ``database`` readiness check (D-25, D-27, RESEARCH Pattern 9, threat T-03-18).

``database_ready(engine)`` is True only when the database answers ``SELECT 1`` and its
``alembic_version`` holds exactly one row equal to the packaged head revision. A wrong or extra
revision returns False; a refused connection, a missing table or a timeout raises, and the
readiness registry logs only the check name and the exception class name and reports the check as
failed. This function never catches and never formats an exception (the text of a connection
error carries the host or socket path).

The statement timeout is set transaction-locally through a bound parameter
(``set_config('statement_timeout', :ms, true)``), so it never outlives the probe on a pooled
connection; it sits inside the registry's own thread timeout (``CHECK_TIMEOUT``, 2 s). All SQL is
constant text.
"""

from sqlalchemy import text
from sqlalchemy.engine import Engine

from truthtrail.db import packaged_head

READINESS_STATEMENT_TIMEOUT_MS = 1500

_SET_TIMEOUT = text("SELECT set_config('statement_timeout', :ms, true)")
_SELECT_ONE = text("SELECT 1")
_SELECT_VERSIONS = text("SELECT version_num FROM alembic_version")


def database_ready(engine: Engine) -> bool:
    """True when the database answers and is migrated exactly to the packaged head."""
    head = packaged_head()
    with engine.connect() as connection:
        connection.execute(_SET_TIMEOUT, {"ms": str(READINESS_STATEMENT_TIMEOUT_MS)})
        connection.execute(_SELECT_ONE).scalar_one()
        versions = list(connection.execute(_SELECT_VERSIONS).scalars())
    return versions == [head]
