"""Alembic environment of the packaged migrations: see ``truthtrail.db.migration_env``.

Online only; the URL comes from a supplied connection or the DATABASE_URL environment variable,
never from the ini file or ``set_main_option`` (RESEARCH F-14).
"""

from truthtrail.db.migration_env import run_migrations

run_migrations()
