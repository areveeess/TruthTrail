"""Database access layer (D-19, D-31): URL normalisation, the engine factory and, from plan 03-03,
the models, migrations and repositories.

Engines are built per app (lifespan) or per command by ``truthtrail.db.engine.create_db_engine``
and disposed by their owner; no module holds an engine.
"""
