"""Database access layer (D-19, D-31): URL normalisation, the engine factory, the declarative
models (``truthtrail.db.models``), the packaged Alembic migrations and, from later plans, the
repositories.

Engines are built per app (lifespan) or per command by ``truthtrail.db.engine.create_db_engine``
and disposed by their owner; no module holds an engine.

``migration_config()`` builds an Alembic ``Config`` that points at the packaged migrations
without any ini file (the image has none) and never carries a database URL (RESEARCH F-14);
``packaged_head()`` is the single head revision the readiness check compares with the
database's ``alembic_version``.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def migration_config(connection: Connection | None = None) -> Config:
    """An Alembic config for the packaged migrations, optionally bound to ``connection``.

    The connection travels in ``config.attributes`` (read by ``env.py``); the URL never goes
    through ``set_main_option``, whose interpolation error would print it.
    """
    cfg = Config()
    # configparser interpolation: a literal percent sign in the path must be doubled.
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR).replace("%", "%%"))
    if connection is not None:
        cfg.attributes["connection"] = connection
    return cfg


def packaged_head() -> str:
    """The single head revision of the packaged migrations; raises unless exactly one exists."""
    heads = ScriptDirectory.from_config(migration_config()).get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"expected exactly one migration head, found {len(heads)}")
    return heads[0]
