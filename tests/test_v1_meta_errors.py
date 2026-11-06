"""The /v1 provenance block and the database error contract, without a database (D-24, D-25,
FND-02, threats T-03-45 and T-03-50).

``V1Meta`` is typed so it can never say ``synthetic: true``; the status rule is a pure function
of the latest checkpoint, the injected app clock and the stale threshold. Database exceptions are
built from fake driver errors and raised inside probe routes: a statement or lock timeout is a
503 ``database_timeout``, any other ``OperationalError`` and pool exhaustion are a 503
``database_unavailable``, each with ``Retry-After``; an integrity error is NOT handled and reaches
the catch-all as the generic 500. A marker planted in the SQL, the parameters and the driver
message never appears in a body or a log line. The database handlers shadow neither the rate-limit
nor the validation handler.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import Query, Request
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from truthtrail.api.db_errors import RETRY_AFTER_SECONDS, classify_operational_error
from truthtrail.api.limits import LimitedRouter
from truthtrail.api.problems import V1_PROBLEM_RESPONSES
from truthtrail.api.v1_deps import (
    build_meta,
    datetime_from_us,
    source_status_for,
    us_from_datetime,
)
from truthtrail.schemas.v1 import V1Meta

PROBLEM_JSON = "application/problem+json"
MARKER = "mkr7SecretPw"
HOST_MARKER = "db-host-mkr7.internal"
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
STALE_AFTER = 3600


class FakeDriverError(Exception):
    """A driver exception carrying a SQLSTATE and a message with infrastructure detail."""

    def __init__(self, sqlstate: str | None) -> None:
        super().__init__(f'connection to server at "{HOST_MARKER}" failed: password {MARKER}')
        self.sqlstate = sqlstate


def operational(sqlstate: str | None) -> OperationalError:
    return OperationalError(
        f"SELECT * FROM secret_{MARKER}", {"p": MARKER}, FakeDriverError(sqlstate)
    )


ERRORS: dict[str, Callable[[], BaseException]] = {
    "timeout": lambda: operational("57014"),
    "lock": lambda: operational("55P03"),
    "refused": lambda: operational("08006"),
    "no-sqlstate": lambda: operational(None),
    "pool": lambda: PoolTimeoutError(f"QueuePool limit reached {MARKER}"),
    "integrity": lambda: IntegrityError(
        f"INSERT INTO t VALUES ('{MARKER}')", {"p": MARKER}, FakeDriverError("23505")
    ),
    "programming": lambda: ProgrammingError(
        f"SELEC {MARKER}", {"p": MARKER}, FakeDriverError("42601")
    ),
}


def raising(router: LimitedRouter) -> None:
    @router.get("/_raise/{name}", responses=V1_PROBLEM_RESPONSES)
    def raise_named(request: Request, name: str) -> dict[str, bool]:
        raise ERRORS[name]()


def validated(router: LimitedRouter) -> None:
    @router.get("/_validated", responses=V1_PROBLEM_RESPONSES)
    def validated_route(request: Request, n: int = Query(ge=1)) -> dict[str, int]:
        return {"n": n}


def data_route(router: LimitedRouter) -> None:
    from truthtrail.api.v1_deps import read_connection

    @router.get("/_data", responses=V1_PROBLEM_RESPONSES)
    def data(request: Request) -> dict[str, int]:
        with read_connection(request) as connection:
            return {"value": int(connection.exec_driver_sql("SELECT 1").scalar_one())}


def _assert_clean(response: Any, caplog: pytest.LogCaptureFixture) -> None:
    for fragment in (MARKER, HOST_MARKER, "SELECT", "INSERT", "secret_"):
        assert fragment not in response.text
        assert fragment not in caplog.text


# --- V1Meta -----------------------------------------------------------------------------------
def test_meta_accepts_the_documented_shape() -> None:
    meta = V1Meta(
        synthetic=False, data_as_of=NOW, source_status="ok", source_mode="live", observed_since=NOW
    )
    assert meta.model_dump()["synthetic"] is False


@pytest.mark.parametrize("synthetic", [True, 1, "true"])
def test_meta_rejects_synthetic_true(synthetic: Any) -> None:
    with pytest.raises(ValidationError):
        V1Meta(synthetic=synthetic, data_as_of=None, source_status="empty", source_mode="live")


@pytest.mark.parametrize("status", ["fixture", "error", "upstream_error", "OK"])
def test_meta_rejects_other_source_statuses(status: str) -> None:
    with pytest.raises(ValidationError):
        V1Meta(synthetic=False, data_as_of=None, source_status=status, source_mode="live")


def test_meta_rejects_other_modes_naive_times_and_extra_members() -> None:
    with pytest.raises(ValidationError):
        V1Meta(synthetic=False, data_as_of=None, source_status="ok", source_mode="demo")
    with pytest.raises(ValidationError):
        V1Meta(
            synthetic=False,
            data_as_of=datetime(2026, 1, 1),  # the naive value is the point
            source_status="ok",
            source_mode="live",
        )
    with pytest.raises(ValidationError):
        V1Meta.model_validate(
            {
                "synthetic": False,
                "data_as_of": None,
                "source_status": "ok",
                "source_mode": "live",
                "risk": "High",
            }
        )


def test_meta_requires_synthetic_and_defaults_observed_since_to_null() -> None:
    with pytest.raises(ValidationError):
        V1Meta.model_validate({"data_as_of": None, "source_status": "ok", "source_mode": "live"})
    meta = V1Meta(synthetic=False, data_as_of=None, source_status="empty", source_mode="live")
    assert meta.observed_since is None


# --- Status rule --------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("data_as_of", "expected"),
    [
        (None, "empty"),
        (NOW, "ok"),
        (NOW - timedelta(seconds=STALE_AFTER), "ok"),
        (NOW - timedelta(seconds=STALE_AFTER, microseconds=1), "stale"),
        (NOW - timedelta(days=30), "stale"),
        (NOW + timedelta(seconds=5), "ok"),
    ],
)
def test_the_status_rule(data_as_of: datetime | None, expected: str) -> None:
    assert source_status_for(data_as_of, NOW, STALE_AFTER) == expected


def test_microseconds_round_trip_exactly() -> None:
    for us in (0, 1, 1_762_000_000_123_457, 4_102_444_799_999_999):
        assert us_from_datetime(datetime_from_us(us)) == us
    assert datetime_from_us(1).microsecond == 1


class FakeResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class FakeConnection:
    """Answers the two provenance queries in order: latest checkpoint, latest run mode."""

    def __init__(self, cursor_us: int | None, mode: str | None) -> None:
        self._answers = [cursor_us, mode]

    def execute(self, statement: Any) -> FakeResult:
        return FakeResult(self._answers.pop(0))


class FakeRequest:
    def __init__(self, now: datetime, stale_after: int) -> None:
        from types import SimpleNamespace

        state = SimpleNamespace(
            clock=lambda: now, policy=SimpleNamespace(ingest_stale_after_seconds=stale_after)
        )
        self.app = SimpleNamespace(state=state)


@pytest.mark.parametrize(
    ("cursor_offset", "mode", "status", "source_mode"),
    [
        (None, None, "empty", "live"),
        (None, "replay", "empty", "replay"),
        (timedelta(seconds=10), "live", "ok", "live"),
        (timedelta(seconds=STALE_AFTER), "replay", "ok", "replay"),
        (timedelta(seconds=STALE_AFTER + 1), "live", "stale", "live"),
        (timedelta(seconds=STALE_AFTER + 1), "replay", "stale", "replay"),
    ],
)
def test_build_meta_applies_the_rule_with_the_injected_clock(
    cursor_offset: timedelta | None, mode: str | None, status: str, source_mode: str
) -> None:
    cursor = None if cursor_offset is None else us_from_datetime(NOW - cursor_offset)
    meta = build_meta(
        FakeConnection(cursor, mode),  # type: ignore[arg-type]
        FakeRequest(NOW, STALE_AFTER),  # type: ignore[arg-type]
        observed_since=NOW - timedelta(days=1),
    )
    assert meta.synthetic is False
    assert meta.source_status == status
    assert meta.source_mode == source_mode
    assert meta.data_as_of == (None if cursor is None else datetime_from_us(cursor))
    assert meta.observed_since == NOW - timedelta(days=1)


# --- Error classification and bodies ------------------------------------------------------------
@pytest.mark.parametrize(
    ("sqlstate", "code"),
    [
        ("57014", "database_timeout"),
        ("55P03", "database_timeout"),
        ("08006", "database_unavailable"),
        ("57P01", "database_unavailable"),
        (None, "database_unavailable"),
    ],
)
def test_operational_errors_are_classified_by_sqlstate(sqlstate: str | None, code: str) -> None:
    assert classify_operational_error(operational(sqlstate)) == code


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("timeout", "database_timeout"),
        ("lock", "database_timeout"),
        ("refused", "database_unavailable"),
        ("no-sqlstate", "database_unavailable"),
        ("pool", "database_unavailable"),
    ],
)
def test_database_errors_render_503_problem_json(
    client_factory: Callable[..., Any],
    caplog: pytest.LogCaptureFixture,
    name: str,
    code: str,
) -> None:
    caplog.set_level(logging.DEBUG)
    client = client_factory(app_kwargs={"v1_registrars": [raising]})
    response = client.get(f"/v1/_raise/{name}")
    assert response.status_code == 503
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    assert response.headers["retry-after"] == str(RETRY_AFTER_SECONDS)
    assert int(response.headers["retry-after"]) > 0
    body = response.json()
    assert body == {
        "type": "about:blank",
        "title": "Service Unavailable",
        "status": 503,
        "detail": body["detail"],
        "code": code,
        "upstream": "database",
        "synthetic": False,
        "source_status": code,
        "data_as_of": None,
    }
    assert body["detail"] in {
        "The database is temporarily unavailable.",
        "The database did not answer in time.",
    }
    _assert_clean(response, caplog)
    assert any(code in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("name", ["integrity", "programming"])
def test_other_database_errors_are_the_generic_500(
    client_factory: Callable[..., Any], caplog: pytest.LogCaptureFixture, name: str
) -> None:
    caplog.set_level(logging.DEBUG)
    client = client_factory(app_kwargs={"v1_registrars": [raising]})
    response = client.get(f"/v1/_raise/{name}")
    assert response.status_code == 500
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    assert "retry-after" not in response.headers
    body = response.json()
    assert body["code"] == "internal_error"
    assert body["source_status"] == "error"
    assert body["synthetic"] is False
    assert body["data_as_of"] is None
    assert "upstream" not in body
    _assert_clean(response, caplog)


def test_an_app_without_an_engine_answers_not_configured(
    client_factory: Callable[..., Any], caplog: pytest.LogCaptureFixture
) -> None:
    client = client_factory(app_kwargs={"v1_registrars": [data_route]})
    response = client.get("/v1/_data")
    assert response.status_code == 500
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    body = response.json()
    assert body["code"] == "not_configured"
    assert body["source_status"] == "not_configured"
    assert body["data_as_of"] is None
    assert "value" not in body


def test_demo_mode_answers_not_configured_too(client_factory: Callable[..., Any]) -> None:
    client = client_factory(
        gnews_api_key=None, demo_mode="true", app_kwargs={"v1_registrars": [data_route]}
    )
    response = client.get("/v1/_data")
    assert response.status_code == 500
    assert response.json()["code"] == "not_configured"


# --- Registration order -------------------------------------------------------------------------
def test_db_handlers_do_not_shadow_the_validation_or_rate_limit_handlers(
    client_factory: Callable[..., Any],
) -> None:
    client = client_factory(
        env={"RATE_LIMIT_V1": "2/minute"}, app_kwargs={"v1_registrars": [validated]}
    )
    invalid = client.get("/v1/_validated", params={"n": "0"})
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "invalid_request"
    assert invalid.json()["errors"][0]["loc"] == ["query", "n"]
    assert [client.get("/v1/_validated", params={"n": "1"}).status_code for _ in range(2)] == [
        200,
        200,
    ]
    limited = client.get("/v1/_validated", params={"n": "1"})
    assert limited.status_code == 429
    assert limited.json()["code"] == "rate_limited"
    assert limited.headers["content-type"].startswith(PROBLEM_JSON)


def test_the_v1_declaration_has_no_502_and_declares_retry_after() -> None:
    assert set(V1_PROBLEM_RESPONSES) == {422, 429, 500, 503}
    for code in (429, 503):
        assert V1_PROBLEM_RESPONSES[code]["headers"]["Retry-After"]["schema"] == {"type": "integer"}
    assert "database" in V1_PROBLEM_RESPONSES[503]["description"]


def test_create_app_rejects_an_invalid_policy_naming_the_variable(
    client_factory: Callable[..., Any],
) -> None:
    from truthtrail.core.config import ConfigurationError

    with pytest.raises(ConfigurationError, match="MAX_TREE_NODES") as excinfo:
        client_factory(env={"MAX_TREE_NODES": "zero-xyz"})
    assert "zero-xyz" not in str(excinfo.value)


def test_create_app_stores_policy_clock_and_cache(client_factory: Callable[..., Any]) -> None:
    client = client_factory(
        env={"INGEST_STALE_AFTER_SECONDS": "77"}, app_kwargs={"clock": lambda: NOW}
    )
    state = client.app.state
    assert state.policy.ingest_stale_after_seconds == 77
    assert state.clock() == NOW
    assert state.v1_cache is not client_factory().app.state.v1_cache
