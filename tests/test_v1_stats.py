"""``GET /v1/stats`` against a real PostgreSQL (D-23, D-24, RESEARCH F-17).

Every number is recomputed independently from the tables in the test; a statement listener proves
the request never reads the ``events`` table (the stats come from the cascade rollups and the run
log only); the lag follows the injected clock; the payload is cached within its TTL and recomputed
after a new checkpoint (a data-version change).
"""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from conftest import insert_forest, set_checkpoint
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from truthtrail.api.v1_deps import datetime_from_us, us_from_datetime
from truthtrail.api.v1_stats import ingest_lag_seconds

pytestmark = pytest.mark.requires_db

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def seeded(seeded_db_url: str) -> Iterator[Engine]:
    engine = create_engine(seeded_db_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


def scalar(engine: Engine, sql: str, **params: Any) -> Any:
    with engine.connect() as connection:
        return connection.execute(text(sql), params).scalar_one()


def data_as_of(engine: Engine) -> datetime:
    return datetime_from_us(
        int(scalar(engine, "SELECT max(cursor_time_us) FROM ingest_checkpoints"))
    )


def capture(engine: Engine) -> list[str]:
    statements: list[str] = []
    event.listen(engine, "before_cursor_execute", lambda c, cur, s, *a: statements.append(s))
    return statements


def test_every_number_matches_an_independent_recount(
    v1_client: Callable[..., Any], seeded_db_url: str, seeded: Engine
) -> None:
    now = data_as_of(seeded) + timedelta(seconds=90)
    body = v1_client(seeded_db_url, clock=lambda: now).get("/v1/stats").json()

    def live(kind: str) -> int:
        return int(
            scalar(
                seeded,
                "SELECT count(*) FROM events WHERE edge_kind = :k AND deleted_at IS NULL",
                k=kind,
            )
        )

    assert body["cascades_total"] == scalar(seeded, "SELECT count(*) FROM cascades")
    assert body["cascades_with_deleted_root"] == scalar(
        seeded, "SELECT count(*) FROM cascades WHERE root_deleted_at IS NOT NULL"
    )
    assert body["events_by_kind"] == {k: live(k) for k in ("root", "reply", "quote", "repost")}
    assert body["events_total"] == scalar(
        seeded, "SELECT count(*) FROM events WHERE deleted_at IS NULL"
    )
    assert body["events_total"] == sum(body["events_by_kind"].values())
    assert body["orphans_total"] == scalar(
        seeded,
        "SELECT count(*) FROM events WHERE parent_state = 'orphan' AND deleted_at IS NULL",
    )
    assert body["deleted_total"] == scalar(
        seeded, "SELECT count(*) FROM events WHERE deleted_at IS NOT NULL"
    )
    assert body["disconnected_total"] == scalar(
        seeded, "SELECT sum(disconnected_count) FROM cascades"
    )
    assert datetime.fromisoformat(body["observed_since"]) == scalar(
        seeded, "SELECT min(observed_at) FROM events WHERE deleted_at IS NULL"
    )
    assert body["ingest_lag_seconds"] == 90
    assert body["ingest_gaps_total"] == scalar(
        seeded, "SELECT coalesce(sum(gap_count), 0) FROM ingest_runs"
    )
    assert body["last_run"]["mode"] == "replay"
    assert body["last_run"]["status"] == "completed"
    assert body["meta"]["synthetic"] is False
    assert body["meta"]["source_mode"] == "replay"
    assert body["meta"]["source_status"] == "ok"
    assert body["meta"]["observed_since"] == body["observed_since"]


def test_an_empty_database_gives_zeros_and_nulls(
    v1_client: Callable[..., Any], clean_db: str
) -> None:
    body = v1_client(clean_db).get("/v1/stats").json()
    assert body == {
        "cascades_total": 0,
        "cascades_with_deleted_root": 0,
        "events_by_kind": {"root": 0, "reply": 0, "quote": 0, "repost": 0},
        "events_total": 0,
        "orphans_total": 0,
        "disconnected_total": 0,
        "deleted_total": 0,
        "observed_since": None,
        "ingest_lag_seconds": None,
        "ingest_gaps_total": 0,
        "last_run": None,
        "meta": {
            "synthetic": False,
            "data_as_of": None,
            "source_status": "empty",
            "source_mode": "live",
            "observed_since": None,
        },
    }


def test_the_lag_follows_the_injected_clock(
    v1_client: Callable[..., Any], make_engine: Callable[..., Engine], clean_db: str
) -> None:
    set_checkpoint(make_engine(clean_db), us_from_datetime(T0))
    env = {"INGEST_STALE_AFTER_SECONDS": "3600"}
    for offset, status in ((0, "ok"), (3600, "ok"), (3601, "stale"), (86_400 * 3, "stale")):
        client = v1_client(clean_db, env=env, clock=lambda o=offset: T0 + timedelta(seconds=o))
        body = client.get("/v1/stats").json()
        assert body["ingest_lag_seconds"] == offset
        assert body["meta"]["source_status"] == status


def test_ingest_lag_is_never_negative() -> None:
    assert ingest_lag_seconds(T0, None) is None
    assert ingest_lag_seconds(T0, T0 + timedelta(seconds=5)) == 0
    assert ingest_lag_seconds(T0 + timedelta(seconds=1.9), T0) == 1


def test_the_request_never_reads_the_events_table(
    v1_client: Callable[..., Any], seeded_db_url: str
) -> None:
    client = v1_client(seeded_db_url)
    statements = capture(client.app.state.engine)
    assert client.get("/v1/stats").status_code == 200
    assert statements
    for statement in statements:
        lowered = " ".join(statement.lower().split())
        assert "from events" not in lowered
        assert "join events" not in lowered
        assert "events." not in lowered.replace("cascades.events_1h", "")
    assert any("from cascades" in " ".join(s.lower().split()) for s in statements)


def test_last_run_and_gap_totals_match_constructed_runs(
    v1_client: Callable[..., Any], make_engine: Callable[..., Engine], clean_db: str
) -> None:
    engine = make_engine(clean_db)
    runs = [
        ("live", T0, T0 + timedelta(minutes=5), "completed", 2),
        ("live", T0 + timedelta(hours=1), None, "running", 0),
        ("replay", T0 - timedelta(days=1), T0 - timedelta(days=1), "failed", 3),
    ]
    with engine.begin() as connection:
        for mode, started, finished, status, gaps in runs:
            connection.execute(
                text(
                    "INSERT INTO ingest_runs (source, mode, started_at, finished_at, status,"
                    " gap_count) VALUES ('s', :m, :s, :f, :st, :g)"
                ),
                {"m": mode, "s": started, "f": finished, "st": status, "g": gaps},
            )
    body = v1_client(clean_db).get("/v1/stats").json()
    assert body["ingest_gaps_total"] == 5
    assert body["last_run"] == {
        "status": "running",
        "mode": "live",
        "started_at": (T0 + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        "finished_at": None,
    }


def test_the_payload_is_cached_and_recomputed_after_a_new_checkpoint(
    v1_client: Callable[..., Any], make_engine: Callable[..., Engine], clean_db: str
) -> None:
    engine = make_engine(clean_db)
    insert_forest(engine, [("st-R", "root", None, T0, "a1", False)], root_uri="st-R")
    set_checkpoint(engine, us_from_datetime(T0))
    client = v1_client(clean_db, clock=lambda: T0)
    statements = capture(client.app.state.engine)

    def rollup_reads() -> int:
        return sum(1 for s in statements if "FROM cascades" in s and "sum(" in s)

    first = client.get("/v1/stats").json()
    second = client.get("/v1/stats").json()
    assert first == second
    assert rollup_reads() == 1
    with engine.begin() as connection:  # a rollup change the version key does not see
        connection.execute(text("UPDATE cascades SET reply_count = 0, event_count = 7"))
    assert client.get("/v1/stats").json()["events_total"] == first["events_total"]
    assert rollup_reads() == 1
    set_checkpoint(engine, us_from_datetime(T0 + timedelta(seconds=1)))
    third = client.get("/v1/stats").json()
    assert rollup_reads() == 2
    assert third["events_total"] == 7
    assert third["meta"]["data_as_of"] != first["meta"]["data_as_of"]
