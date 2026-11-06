"""Shared plumbing of the ``/v1`` routes: the read-only connection, provenance and data version.

``get_connection(request)`` yields a short-lived connection from ``app.state.engine`` with the
read-only execution option (the API role's statement timeout comes from the engine, D-19) and
closes it afterwards. An app without an engine (``DEMO_MODE``, D-27) raises the existing
``ConfigurationError``, which renders the 500 ``not_configured`` problem body: such a process
never answers a data route with data. Handlers open the connection INSIDE their body through
``read_connection`` (the same generator as a context manager), not as a FastAPI dependency:
dependencies are resolved before the rate-limit wrapper runs, so a dependency would check out a
pool connection even for a request the limiter then rejects (D-23, T-03-46).

``build_meta`` applies the D-24 status rule with the app clock (``app.state.clock``) and
``app.state.policy.ingest_stale_after_seconds``:

- no committed checkpoint: ``empty``, ``data_as_of`` null;
- ``now - data_as_of`` greater than the threshold: ``stale``;
- otherwise ``ok`` (an empty filtered result with data present is ``ok``).

``source_mode`` is ``replay`` when the latest ingest run was a replay, else ``live``.

``data_version`` is one constant query over the small checkpoint table and the cascade rollups.
Cache keys include it, so a cached payload never outlives an ingest batch, an enrich pass or a
dirty mark by more than its TTL. All SQL here is constant text with no parameters from a request.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.engine import Connection

from truthtrail.core.config import ConfigurationError
from truthtrail.schemas.v1 import SourceMode, SourceStatus, V1Meta

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
ONE_MICROSECOND = timedelta(microseconds=1)

_LATEST_CHECKPOINT = text(
    "SELECT cursor_time_us FROM ingest_checkpoints ORDER BY updated_at DESC, source LIMIT 1"
)
_LATEST_RUN_MODE = text("SELECT mode FROM ingest_runs ORDER BY started_at DESC, id DESC LIMIT 1")
_DATA_VERSION = text(
    "SELECT (SELECT max(updated_at) FROM ingest_checkpoints),"
    " (SELECT max(cursor_time_us) FROM ingest_checkpoints),"
    " (SELECT max(started_at) FROM ingest_runs),"
    " max(c.rolled_up_at), count(*), count(*) FILTER (WHERE c.enrich_dirty),"
    " count(*) FILTER (WHERE c.root_deleted_at IS NOT NULL)"
    " FROM cascades c"
)


def utc_now() -> datetime:
    """The default app clock: the UTC wall clock."""
    return datetime.now(UTC)


def datetime_from_us(value: int) -> datetime:
    """Integer microseconds since the epoch to an aware UTC datetime, exactly (no float)."""
    return EPOCH + timedelta(microseconds=value)


def us_from_datetime(value: datetime) -> int:
    """An aware datetime to integer microseconds since the epoch, exactly (no float)."""
    return (value.astimezone(UTC) - EPOCH) // ONE_MICROSECOND


def as_utc(value: datetime) -> datetime:
    """Normalise a database timestamp to UTC (the session is UTC already, RESEARCH F-15)."""
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)


def get_connection(request: Request) -> Iterator[Connection]:
    """Yield a read-only connection from the app's engine and close it afterwards."""
    engine = request.app.state.engine
    if engine is None:
        raise ConfigurationError("no database is configured for this process")
    with engine.connect() as connection:
        connection.execution_options(postgresql_readonly=True)
        yield connection


read_connection = contextmanager(get_connection)


def source_status_for(
    data_as_of: datetime | None, now: datetime, stale_after_seconds: int
) -> SourceStatus:
    """The D-24 status rule (see the module docstring)."""
    if data_as_of is None:
        return "empty"
    if now - data_as_of > timedelta(seconds=stale_after_seconds):
        return "stale"
    return "ok"


def build_meta(
    connection: Connection, request: Request, *, observed_since: datetime | None = None
) -> V1Meta:
    """Build the provenance block for this request (never cached: staleness depends on now)."""
    cursor_us = connection.execute(_LATEST_CHECKPOINT).scalar_one_or_none()
    mode = connection.execute(_LATEST_RUN_MODE).scalar_one_or_none()
    data_as_of = None if cursor_us is None else datetime_from_us(int(cursor_us))
    now: datetime = request.app.state.clock()
    status = source_status_for(data_as_of, now, request.app.state.policy.ingest_stale_after_seconds)
    source_mode: SourceMode = "replay" if mode == "replay" else "live"
    return V1Meta(
        synthetic=False,
        data_as_of=data_as_of,
        source_status=status,
        source_mode=source_mode,
        observed_since=None if observed_since is None else as_utc(observed_since),
    )


def data_version(connection: Connection) -> tuple[Any, ...]:
    """A small tuple that changes whenever stored data changes (see the module docstring)."""
    row = connection.execute(_DATA_VERSION).one()
    return tuple(row)
