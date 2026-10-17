"""Shared test fixtures: network guard, env scrub, app client and payload builders.

Every test runs inside an autouse ``responses`` mock, so an unmocked outbound
``requests`` call raises ``requests.exceptions.ConnectionError`` instead of
reaching the live provider. The app and the fetcher module are imported lazily
inside ``client_factory`` so collection never imports them and a future package
move touches this one file.
"""

import os
import random
from collections.abc import Callable, Iterator
from typing import Any, Optional

import pytest
import responses

from truthtrail.core.config import Settings, get_settings

# Names the module that owns the route-level callables load_demo_fixture,
# FIXTURE_PATH and analyze_risk, for string patch targets. Plan 02-02 (package
# move) and plan 02-05 (create_app refactor) each change this single line.
APP_MODULE = "truthtrail.main"
FAKE_KEY = "FAKE_TEST_KEY"
GNEWS_URL = "https://gnews.io/api/v4/search"
ENV_NAMES = (
    "GNEWS_API_KEY",
    "DEMO_MODE",
    "BLUESKY_HANDLE",
    "BLUESKY_APP_PASSWORD",
    "DATABASE_URL",
)


@pytest.fixture(autouse=True)
def network_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[responses.RequestsMock]:
    """Block every unregistered outbound request and scrub secret-bearing env vars.

    A developer's local .env is disabled and the cached settings are cleared
    before and after each test, so no real value can leak in or persist.
    """
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    get_settings.cache_clear()
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rs:
        yield rs
    get_settings.cache_clear()


@pytest.fixture
def mock_gnews(network_guard: responses.RequestsMock) -> responses.RequestsMock:
    """Return the active mock so tests can register GNews responses on it."""
    return network_guard


@pytest.fixture
def client_factory(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Any]:
    """Return a callable that builds a TestClient around the real app.

    Settings are driven through the environment. Using the returned client as a
    context manager (``with client_factory(...):``) runs the app lifespan.
    """

    def make(
        *,
        gnews_api_key: Optional[str] = FAKE_KEY,
        demo_mode: Optional[str] = None,
        raise_server_exceptions: bool = False,
    ) -> Any:
        import truthtrail.main as main
        from fastapi.testclient import TestClient

        if gnews_api_key is not None:
            monkeypatch.setenv("GNEWS_API_KEY", gnews_api_key)
        if demo_mode is not None:
            monkeypatch.setenv("DEMO_MODE", demo_mode)
        get_settings.cache_clear()
        return TestClient(main.app, raise_server_exceptions=raise_server_exceptions)

    return make


@pytest.fixture
def client(client_factory: Callable[..., Any]) -> Any:
    """TestClient that returns 500 responses instead of raising server errors."""
    return client_factory()


@pytest.fixture
def app_module() -> str:
    """Module name that string patch targets must use (see ``APP_MODULE``)."""
    return APP_MODULE


@pytest.fixture
def subprocess_env() -> dict[str, str]:
    """Return a new minimal environment dict for subprocess-based tests.

    SYSTEMROOT is passed through when present: without it asyncio cannot
    initialise Winsock on Windows (WinError 10106).
    """
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if "SYSTEMROOT" in os.environ:
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return env


@pytest.fixture
def fake_key() -> str:
    return FAKE_KEY


@pytest.fixture
def gnews_url() -> str:
    return GNEWS_URL


@pytest.fixture
def gnews_article() -> Callable[..., dict[str, Any]]:
    """Builder for one GNews-shaped article."""

    def article(
        title: str | None = "Local bakery wins award",
        source: str = "Example Wire",
        published_at: str = "2026-10-11T09:30:00Z",
    ) -> dict[str, Any]:
        return {
            "title": title,
            "description": None,
            "url": "https://example.org/article",
            "image": None,
            "publishedAt": published_at,
            "source": {"name": source, "url": "https://example.org"},
        }

    return article


@pytest.fixture
def gnews_payload() -> Callable[..., dict[str, Any]]:
    """Builder for a GNews search response body."""

    def payload(*articles: dict[str, Any]) -> dict[str, Any]:
        return {"totalArticles": len(articles), "articles": list(articles)}

    return payload


@pytest.fixture
def seeded_random() -> Iterator[Callable[[int], None]]:
    """Yield a seeding function and restore the global random state afterwards."""
    state = random.getstate()

    def seed(n: int) -> None:
        random.seed(n)

    yield seed
    random.setstate(state)
