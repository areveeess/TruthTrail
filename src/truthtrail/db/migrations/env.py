"""Alembic environment for the packaged migrations (D-19, RESEARCH Pattern 8, F-14).

Online mode only. The connection comes from ``config.attributes["connection"]`` when a caller
supplies one (the pytest migration tests and ``python -m truthtrail.db``); otherwise an engine is
built from the ``DATABASE_URL`` environment variable by ``create_db_engine`` with the ``jobs``
role (connect, 30 s statement and 2 s lock timeouts, D-19, T-03-18) and disposed afterwards (the
``alembic`` command line, used by CI against the service container).

The database URL NEVER goes through ``Config.set_main_option`` or the ini file: a percent sign in
a URL-encoded password makes configparser interpolation raise a ``ValueError`` whose message
contains the whole URL (F-14). Nothing here prints or logs the URL.
"""

import os

from alembic import context
from sqlalchemy.engine import Connection

from truthtrail.core.config import ConfigurationError
from truthtrail.db.engine import create_db_engine
from truthtrail.db.models import Base

target_metadata = Base.metadata


def _configure_and_run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run against the supplied connection, or one built from ``DATABASE_URL``."""
    supplied = context.config.attributes.get("connection")
    if supplied is not None:
        _configure_and_run(supplied)
        return
    raw = os.environ.get("DATABASE_URL", "").strip()
    if not raw:
        raise ConfigurationError("DATABASE_URL is required to run migrations")
    engine = create_db_engine(raw, role="jobs", pool_size=1, max_overflow=0)
    try:
        with engine.connect() as connection:
            _configure_and_run(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise ConfigurationError("offline (--sql) migrations are not supported")
run_migrations_online()
