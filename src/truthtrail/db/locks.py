"""Single-flight advisory locks, one constant key per command (RESEARCH Pattern 6, T-03-35).

A command takes its lock with ``try_advisory_lock`` on its OWN connection and keeps that
connection open for the whole run; the session-level lock dies with the connection, so a
killed process can never leave a stale lock behind. A second run of the same command gets
``False`` and exits with its documented "another run is active" status. Keys are bound
parameters, never SQL text.
"""

from sqlalchemy import text
from sqlalchemy.engine import Connection

# One key per command. Arbitrary but fixed 63-bit values, so another application sharing the
# database is unlikely to collide; the ingest key also guards the operator erase command.
INGEST_LOCK_KEY = 0x7472_7574_6801
ENRICH_LOCK_KEY = 0x7472_7574_6802
PURGE_LOCK_KEY = 0x7472_7574_6803
NEWS_LOCK_KEY = 0x7472_7574_6804

LOCK_KEYS: dict[str, int] = {
    "ingest": INGEST_LOCK_KEY,
    "enrich": ENRICH_LOCK_KEY,
    "purge": PURGE_LOCK_KEY,
    "news": NEWS_LOCK_KEY,
}


def try_advisory_lock(connection: Connection, key: int) -> bool:
    """Take the session-level advisory lock ``key`` without waiting; True when acquired.

    The statement runs in its own short transaction, which is committed so the connection is
    left idle (the lock is session-scoped and outlives the transaction).
    """
    acquired = connection.execute(
        text("SELECT pg_try_advisory_lock(:key)"), {"key": key}
    ).scalar_one()
    connection.commit()
    return bool(acquired)


def release_advisory_lock(connection: Connection, key: int) -> bool:
    """Release the advisory lock ``key`` held by this session; True when it was held."""
    released = connection.execute(
        text("SELECT pg_advisory_unlock(:key)"), {"key": key}
    ).scalar_one()
    connection.commit()
    return bool(released)
