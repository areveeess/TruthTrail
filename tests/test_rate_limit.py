"""Per-client-IP rate limiting on /analyze answers 429 problem+json (D-10, ROADMAP criterion 5).

The limit protects the scarce GNews quota. The 429 uses the same RFC 9457 shape as every other
error, carries a Retry-After computed from the limiter window, never echoes the client address
and is declared in OpenAPI. slowapi is used through decorators only (D-23); an AST guard keeps
its middleware and ``default_limits`` out of the package because both are silently inactive for
routes added through ``include_router`` (research Pitfall 2).

Hygiene: no raw request URL, params dict or header dict appears in an assert expression.
"""

import ast
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from truthtrail.core.config import ConfigurationError

PROBLEM = "application/problem+json"
ALLOWED = "http://localhost:5173"
PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "src" / "truthtrail"
MIN_PACKAGE_FILES = 8


@pytest.fixture
def upstream(mock_gnews, gnews_url, gnews_payload, gnews_article) -> None:
    """Every GNews call answers the same fixed 200 payload."""
    mock_gnews.get(gnews_url, json=gnews_payload(gnews_article()))


def _get(client: Any, query: str = "x") -> Any:
    return client.get("/analyze", params={"query": query})


def test_eleventh_default_request_is_429_problem(
    client_factory: Callable[..., Any], upstream
) -> None:
    """ROADMAP criterion 5: over the limit receives 429 with the problem+json shape."""
    client = client_factory()

    statuses = [_get(client).status_code for _ in range(10)]
    response = _get(client)

    body = response.json()
    content_type = response.headers["content-type"]
    retry_after = response.headers["retry-after"]
    key_in_body = "FAKE_TEST_KEY" in response.text
    peer_in_body = "testclient" in response.text
    assert statuses == [200] * 10
    assert response.status_code == 429
    assert content_type.startswith(PROBLEM)
    assert body["type"] == "about:blank"
    assert body["title"] == "Too Many Requests"
    assert body["status"] == 429
    assert body["code"] == "rate_limited"
    assert body["synthetic"] is False
    assert body["source_status"] == "rate_limited"
    assert body["data_as_of"] is None
    assert re.fullmatch(r"[0-9]+", retry_after) is not None
    assert 1 <= int(retry_after) <= 60
    assert "results" not in body
    assert not key_in_body
    assert not peer_in_body


def test_ok_responses_carry_no_rate_limit_headers(
    client_factory: Callable[..., Any], upstream
) -> None:
    client = client_factory()

    response = _get(client)

    names = {name.lower() for name in response.headers}
    assert response.status_code == 200
    assert "retry-after" not in names
    assert not {name for name in names if name.startswith("x-ratelimit")}


def test_limit_is_configurable_from_the_environment(
    client_factory: Callable[..., Any], upstream
) -> None:
    client = client_factory(env={"RATE_LIMIT_ANALYZE": "2/minute"})

    statuses = [_get(client).status_code for _ in range(3)]

    assert statuses == [200, 200, 429]


def test_limit_also_applies_in_demo_mode(client_factory: Callable[..., Any]) -> None:
    client = client_factory(
        gnews_api_key=None, demo_mode="true", env={"RATE_LIMIT_ANALYZE": "2/minute"}
    )

    statuses = [_get(client).status_code for _ in range(3)]

    assert statuses == [200, 200, 429]


def test_invalid_requests_do_not_consume_quota(
    client_factory: Callable[..., Any], upstream
) -> None:
    client = client_factory()

    invalid = [client.get("/analyze", params={"query": ""}).status_code for _ in range(15)]
    valid = [_get(client).status_code for _ in range(10)]

    assert invalid == [422] * 15
    assert valid == [200] * 10


def test_another_peer_is_not_limited_when_the_first_is_exhausted(
    client_factory: Callable[..., Any], upstream
) -> None:
    first = client_factory(env={"RATE_LIMIT_ANALYZE": "1/minute"})
    second = TestClient(first.app, client=("198.51.100.7", 5000))

    first_statuses = [_get(first).status_code for _ in range(2)]
    second_statuses = [_get(second).status_code for _ in range(2)]

    assert first_statuses == [200, 429]
    assert second_statuses == [200, 429]


def test_two_apps_have_independent_counters(client_factory: Callable[..., Any], upstream) -> None:
    one = client_factory(env={"RATE_LIMIT_ANALYZE": "1/minute"})
    exhausted = [_get(one).status_code for _ in range(2)]
    two = client_factory(env={"RATE_LIMIT_ANALYZE": "1/minute"})

    fresh = _get(two).status_code

    assert exhausted == [200, 429]
    assert fresh == 200
    assert one.app.state.limiter is not two.app.state.limiter


def test_health_and_ready_are_never_limited(client_factory: Callable[..., Any]) -> None:
    client = client_factory(env={"RATE_LIMIT_ANALYZE": "1/minute"})

    health = {client.get("/health").status_code for _ in range(50)}
    ready = {client.get("/ready").status_code for _ in range(50)}

    assert health == {200}
    assert ready == {200}


def test_429_for_an_allowed_origin_carries_cors_headers(
    client_factory: Callable[..., Any], upstream
) -> None:
    client = client_factory(env={"RATE_LIMIT_ANALYZE": "1/minute", "CORS_ORIGINS": ALLOWED})
    headers = {"Origin": ALLOWED}

    first = client.get("/analyze", params={"query": "x"}, headers=headers)
    limited = client.get("/analyze", params={"query": "x"}, headers=headers)

    assert first.status_code == 200
    assert limited.status_code == 429
    assert limited.headers["access-control-allow-origin"] == ALLOWED
    assert limited.headers["content-type"].startswith(PROBLEM)


@pytest.mark.parametrize("name", ["RATE_LIMIT_ANALYZE", "RATE_LIMIT_V1"])
def test_invalid_rate_limit_stops_startup_naming_the_variable(
    name: str, client_factory: Callable[..., Any]
) -> None:
    client = client_factory(env={name: "not-a-limit-xyz"})

    with pytest.raises(ConfigurationError) as excinfo, client:
        pass

    message = str(excinfo.value)
    assert name in message
    assert "not-a-limit-xyz" not in message


def test_openapi_declares_the_429_on_analyze(client_factory: Callable[..., Any]) -> None:
    client = client_factory()

    document = client.get("/openapi.json").json()

    response = document["paths"]["/analyze"]["get"]["responses"]["429"]
    header = response["headers"]["Retry-After"]
    assert list(response["content"]) == [PROBLEM]
    assert response["content"][PROBLEM]["schema"] == {"$ref": "#/components/schemas/Problem"}
    assert header["schema"] == {"type": "integer"}
    assert "429" not in document["paths"]["/health"]["get"]["responses"]
    assert "429" not in document["paths"]["/ready"]["get"]["responses"]


def _slowapi_hazards(source: str) -> list[str]:
    """Names of the silently inactive slowapi features that ``source`` uses."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.startswith("slowapi.middleware")]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith("slowapi.middleware"):
                found.append(module)
            elif module == "slowapi":
                found += [a.name for a in node.names if a.name == "SlowAPIMiddleware"]
        elif isinstance(node, ast.Call):
            found += [kw.arg for kw in node.keywords if kw.arg == "default_limits"]
    return found


def test_hazard_scanner_is_not_blind() -> None:
    assert _slowapi_hazards("from slowapi.middleware import SlowAPIMiddleware") != []
    assert _slowapi_hazards("from slowapi import SlowAPIMiddleware") != []
    assert _slowapi_hazards("Limiter(key_func=f, default_limits=['1/minute'])") != []
    assert _slowapi_hazards("from slowapi import Limiter\nLimiter(key_func=f)") == []


def test_package_never_uses_slowapi_middleware_or_default_limits() -> None:
    """Research Pitfall 2 / D-23: both skip routes added through include_router."""
    files = sorted(PACKAGE_ROOT.rglob("*.py"))

    hazards = {
        str(path.relative_to(PACKAGE_ROOT)): _slowapi_hazards(path.read_text(encoding="utf-8"))
        for path in files
    }

    assert len(files) >= MIN_PACKAGE_FILES
    assert {name: found for name, found in hazards.items() if found} == {}
