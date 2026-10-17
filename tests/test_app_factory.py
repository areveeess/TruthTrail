"""create_app() builds an independent app per call; strict settings load only at startup (D-23)."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI

from truthtrail.api.app import create_app
from truthtrail.core.config import ConfigurationError


def _route_paths(app: FastAPI) -> list[str]:
    """Paths the app serves; read from the OpenAPI document because FastAPI 0.143 keeps
    included routers as one nested route object whose path is empty."""
    app.openapi_schema = None  # routes may have changed since the document was built
    return list(app.openapi()["paths"])


def test_two_calls_return_independent_apps() -> None:
    first = create_app()
    second = create_app()
    assert first is not second
    assert first.state is not second.state
    assert first.router is not second.router
    assert first.routes is not second.routes
    assert "/analyze" in _route_paths(first)
    assert _route_paths(first) == _route_paths(second)


def test_state_and_routes_do_not_leak_between_apps() -> None:
    first = create_app()
    second = create_app()
    first.state.marker = "first"
    assert not hasattr(second.state, "marker")

    @first.get("/only-on-first")
    def only_on_first() -> dict[str, str]:
        return {}

    assert "/only-on-first" in _route_paths(first)
    assert "/only-on-first" not in _route_paths(second)


def test_module_entrypoint_exposes_an_app() -> None:
    import truthtrail.main

    assert isinstance(truthtrail.main.app, FastAPI)


def test_strict_settings_are_read_only_at_startup(client_factory: Callable[..., Any]) -> None:
    # No GNEWS_API_KEY and no DEMO_MODE: construction must still succeed ...
    client = client_factory(gnews_api_key=None)
    # ... and only entering the app (running the lifespan) reads the strict settings.
    with pytest.raises(ConfigurationError), client:
        pass
