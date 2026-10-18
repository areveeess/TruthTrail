"""Liveness and readiness endpoints (D-06, D-07, D-20; ENG-05, ROADMAP criterion 4).

Checks are injected with ``client.app.state.readiness.register(...)`` on the per-test
app. Hygiene (T-02-16): the exception text of a raising check is a secret-looking
marker that must appear in neither the response body nor the captured logs.
"""

import logging
from typing import Any

import pytest

PROBLEM_JSON = "application/problem+json"
SECRET = "postgres://user:SECRETPASSWORD@db.internal:5432/app"


def _register(client: Any, name: str, check: Any) -> None:
    client.app.state.readiness.register(name, check)


def test_health_is_200_ok(client: Any) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_is_200_with_a_failing_check_and_no_news_key(client_factory: Any) -> None:
    client = client_factory(gnews_api_key=None)
    _register(client, "database", lambda: False)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_with_no_checks_is_200(client: Any) -> None:
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {}}


def test_ready_with_passing_check_lists_it(client: Any) -> None:
    _register(client, "x", lambda: True)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"x": "ok"}}


def test_ready_with_injected_failing_check_is_503_problem(client: Any) -> None:
    """ROADMAP criterion 4: an injected failing check makes /ready return 503."""
    _register(client, "database", lambda: False)

    response = client.get("/ready")

    body = response.json()
    assert response.status_code == 503
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    assert body["type"] == "about:blank"
    assert body["title"] == "Service Unavailable"
    assert body["status"] == 503
    assert body["code"] == "not_ready"
    assert body["detail"] == "Not ready: database."
    assert body["synthetic"] is False
    assert body["source_status"] == "not_ready"
    assert body["data_as_of"] is None
    assert "meta" not in body
    assert "retry-after" not in response.headers


def test_ready_names_only_failed_checks_sorted(client: Any) -> None:
    _register(client, "model", lambda: False)
    _register(client, "cache", lambda: True)
    _register(client, "database", lambda: False)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "Not ready: database, model."


def test_raising_check_is_503_and_leaks_nothing(
    client: Any, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    def boom() -> bool:
        raise RuntimeError(SECRET)

    _register(client, "database", boom)

    response = client.get("/ready")

    in_body = "SECRETPASSWORD" in response.text
    in_logs = "SECRETPASSWORD" in caplog.text
    assert response.status_code == 503
    assert response.json()["detail"] == "Not ready: database."
    assert not in_body
    assert not in_logs
    assert "RuntimeError" in caplog.text


def test_check_returning_none_is_503(client: Any) -> None:
    _register(client, "database", lambda: None)  # type: ignore[arg-type,return-value]

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "Not ready: database."


def test_ready_recovers_when_the_dependency_comes_back(client: Any) -> None:
    state = {"up": False}
    _register(client, "database", lambda: state["up"])

    down = client.get("/ready")
    state["up"] = True
    up = client.get("/ready")

    assert down.status_code == 503
    assert up.status_code == 200
    assert up.json() == {"status": "ready", "checks": {"database": "ok"}}


def test_health_and_ready_need_no_query_and_no_auth(client: Any) -> None:
    for path in ("/health", "/ready"):
        response = client.get(path)
        assert response.status_code == 200


def test_readiness_registry_is_per_app(client_factory: Any) -> None:
    first = client_factory()
    second = client_factory()
    _register(first, "database", lambda: False)

    assert first.get("/ready").status_code == 503
    assert second.get("/ready").status_code == 200
    assert first.app.state.readiness is not second.app.state.readiness


def test_openapi_declares_health_and_ready(client: Any) -> None:
    spec = client.get("/openapi.json").json()

    health = spec["paths"]["/health"]["get"]
    ready = spec["paths"]["/ready"]["get"]
    assert health["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/Health"
    }
    assert ready["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/Ready"
    }
    unavailable = ready["responses"]["503"]
    assert set(unavailable["content"]) == {PROBLEM_JSON}
    assert unavailable["content"][PROBLEM_JSON]["schema"] == {
        "$ref": "#/components/schemas/Problem"
    }
    assert "headers" not in unavailable
    assert "503" not in health["responses"]


def test_openapi_health_and_ready_schemas_are_typed(client: Any) -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]

    assert schemas["Health"]["properties"]["status"]["const"] == "ok"
    assert schemas["Health"]["additionalProperties"] is False
    assert schemas["Ready"]["properties"]["status"]["const"] == "ready"
    assert set(schemas["Ready"]["properties"]) == {"status", "checks"}
    assert schemas["Ready"]["additionalProperties"] is False


def test_ready_with_a_hung_check_is_503_and_does_not_block_other_endpoints(client: Any) -> None:
    """A check that never answers fails closed; /health and a repeat /ready stay fast."""
    import threading
    import time

    from truthtrail.core.readiness import ReadinessRegistry

    release = threading.Event()
    client.app.state.readiness = ReadinessRegistry(timeout=0.2)
    _register(client, "database", lambda: release.wait(timeout=30))
    try:
        first = client.get("/ready")
        started = time.monotonic()
        second = client.get("/ready")
        health = client.get("/health")
        elapsed = time.monotonic() - started
    finally:
        release.set()

    assert first.status_code == 503
    assert first.json()["detail"] == "Not ready: database."
    assert second.status_code == 503
    assert health.status_code == 200
    assert elapsed < 0.5
