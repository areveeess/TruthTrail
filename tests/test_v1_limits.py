"""The /v1 mount point limits every route by construction, and proxy headers are not trusted by
default (D-06, D-10, D-23).

slowapi issue 281: its middleware and ``default_limits`` silently skip routes added through
``include_router``, so a route can look limited and not be. ``LimitedRouter`` applies the limit
at registration instead, and the probe routes below prove the 429 on a route that reaches the
app through ``include_router`` (the test that would have caught the fail-open defect). The proxy
cases show a spoofed X-Forwarded-For changes the rate-limit key only when TRUST_PROXY_HEADERS is
true and the peer is listed in FORWARDED_ALLOW_IPS. TestClient never passes through uvicorn's own
proxy layer; tests/test_proxy_headers_server.py covers that with a real server.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import Request

from truthtrail.api.limits import LimitedRouter
from truthtrail.core.config import Settings

PROBLEM = "application/problem+json"


def probe(router: LimitedRouter) -> None:
    """Registrar with one route, the way Phase 3 and 4 add theirs."""

    @router.get("/_probe")
    def probe_ok(request: Request) -> dict[str, bool]:
        return {"ok": True}


def probe_two(router: LimitedRouter) -> None:
    """Registrar with two routes, to show each route has its own bucket."""

    @router.get("/_first")
    def first_route(request: Request) -> dict[str, bool]:
        return {"ok": True}

    @router.get("/_second")
    def second_route(request: Request) -> dict[str, bool]:
        return {"ok": True}


def _statuses(client: Any, path: str, count: int, headers: list[dict[str, str]] | None = None):
    return [
        client.get(path, headers=(headers[i] if headers else None)).status_code
        for i in range(count)
    ]


def test_probe_route_is_limited_and_returns_problem_429(
    client_factory: Callable[..., Any],
) -> None:
    """The fail-closed proof: a route added through include_router still gets its 429."""
    client = client_factory(
        env={"RATE_LIMIT_V1": "2/minute"}, app_kwargs={"v1_registrars": [probe]}
    )

    statuses = _statuses(client, "/v1/_probe", 2)
    response = client.get("/v1/_probe")

    body = response.json()
    assert statuses == [200, 200]
    assert response.status_code == 429
    assert response.headers["content-type"].startswith(PROBLEM)
    assert body["code"] == "rate_limited"
    assert body["source_status"] == "rate_limited"
    assert int(response.headers["retry-after"]) >= 1


def test_each_route_has_its_own_bucket(client_factory: Callable[..., Any]) -> None:
    client = client_factory(
        env={"RATE_LIMIT_V1": "1/minute"}, app_kwargs={"v1_registrars": [probe_two]}
    )

    first = _statuses(client, "/v1/_first", 2)
    second = _statuses(client, "/v1/_second", 2)

    assert first == [200, 429]
    assert second == [200, 429]


def test_handler_without_request_parameter_cannot_be_registered(
    client_factory: Callable[..., Any],
) -> None:
    def bad(router: LimitedRouter) -> None:
        @router.get("/_bad")
        def no_request() -> dict[str, bool]:
            return {"ok": True}

    with pytest.raises(Exception, match="request"):
        client_factory(app_kwargs={"v1_registrars": [bad]})


def test_default_v1_limit_is_sixty_per_minute() -> None:
    settings = Settings(demo_mode=True)

    assert settings.rate_limit_v1 == "60/minute"
    assert settings.rate_limit_analyze == "10/minute"


def test_default_limit_applies_without_configuration(client_factory: Callable[..., Any]) -> None:
    client = client_factory(app_kwargs={"v1_registrars": [probe]})

    statuses = _statuses(client, "/v1/_probe", 61)

    assert statuses == [200] * 60 + [429]


def test_no_registrars_means_no_v1_path_in_openapi(client_factory: Callable[..., Any]) -> None:
    client = client_factory()

    paths = list(client.get("/openapi.json").json()["paths"])

    assert [p for p in paths if p.startswith("/v1")] == []
    assert client.get("/v1/_probe").status_code == 404


def test_spoofed_forwarded_for_is_ignored_when_flag_unset(
    client_factory: Callable[..., Any],
) -> None:
    client = client_factory(
        env={"RATE_LIMIT_V1": "2/minute"},
        app_kwargs={"v1_registrars": [probe]},
        client=("127.0.0.1", 1),
    )
    spoofed = [{"X-Forwarded-For": f"198.51.100.{n}"} for n in (1, 2, 3)]

    statuses = _statuses(client, "/v1/_probe", 3, spoofed)

    assert statuses == [200, 200, 429]


def test_forwarded_for_from_a_trusted_peer_is_the_key_when_flag_on(
    client_factory: Callable[..., Any],
) -> None:
    client = client_factory(
        env={
            "RATE_LIMIT_V1": "1/minute",
            "TRUST_PROXY_HEADERS": "true",
            "FORWARDED_ALLOW_IPS": "127.0.0.1",
        },
        app_kwargs={"v1_registrars": [probe]},
        client=("127.0.0.1", 1),
    )
    distinct = [{"X-Forwarded-For": f"198.51.100.{n}"} for n in (1, 2, 3)]

    statuses = _statuses(client, "/v1/_probe", 3, distinct)
    repeated = client.get("/v1/_probe", headers=distinct[0]).status_code

    assert statuses == [200, 200, 200]
    assert repeated == 429


def test_forwarded_for_from_an_untrusted_peer_is_ignored_when_flag_on(
    client_factory: Callable[..., Any],
) -> None:
    client = client_factory(
        env={
            "RATE_LIMIT_V1": "1/minute",
            "TRUST_PROXY_HEADERS": "true",
            "FORWARDED_ALLOW_IPS": "127.0.0.1",
        },
        app_kwargs={"v1_registrars": [probe]},
        client=("203.0.113.9", 1),
    )
    distinct = [{"X-Forwarded-For": f"198.51.100.{n}"} for n in (1, 2)]

    statuses = _statuses(client, "/v1/_probe", 2, distinct)

    assert statuses == [200, 429]


def test_invalid_trust_flag_stops_construction_naming_the_variable(
    client_factory: Callable[..., Any],
) -> None:
    from truthtrail.core.config import ConfigurationError

    with pytest.raises(ConfigurationError, match="TRUST_PROXY_HEADERS") as excinfo:
        client_factory(env={"TRUST_PROXY_HEADERS": "perhaps-xyz"})

    assert "perhaps-xyz" not in str(excinfo.value)
