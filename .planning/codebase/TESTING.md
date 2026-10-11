---
last_mapped_commit: 1fedcd29ba790edf42ebc1ffbffe62b9f643177f
last_mapped_at: 2026-10-11
---
# Testing Patterns

**Analysis Date:** 2026-10-11

## Current State

**No automated tests exist in this repository.** Verified by:
- No `test_*.py`, `*_test.py`, `tests/` directory, `*.test.*`, or `*.spec.*` files in the tracked tree (`git ls-files` lists 10 files, none of them tests).
- No test framework in `requirements.txt` (`fastapi`, `uvicorn`, `requests` only). `pytest` and `httpx` (needed for FastAPI `TestClient`) are not declared.
- No `pytest.ini`, `pyproject.toml`, `setup.cfg`, `tox.ini`, `conftest.py`, or CI workflow (`.github/workflows/` absent).
- `package.json` declares only `recharts` with no `test` script, and no frontend test tooling.

Everything below under "Recommended Setup" is a proposal for the first tests, not an existing pattern.

## Test Framework

**Runner:**
- Not configured.
- Recommended: `pytest` (add to a dev requirements file, e.g. `requirements-dev.txt`).
- Config: none. If created, place settings in `pytest.ini` at the repo root.

**Assertion Library:**
- Built-in `assert` statements (pytest rewrites them).

**HTTP testing:**
- `fastapi.testclient.TestClient` requires the `httpx` package; add it to the dev requirements when testing `main.py`.

**Run Commands (once pytest is added):**

```bash
python -m pytest              # Run all tests
python -m pytest -q           # Quiet run
python -m pytest --cov        # Coverage (requires pytest-cov)
```

## Recommended Setup

Modules are imported by bare name from the repo root (`from risk_analyzer import analyze_risk`), so tests must run from the repository root or set `PYTHONPATH=.`. Put tests in a `tests/` directory at the root:

```
tests/
├── conftest.py             # Shared fixtures (optional)
├── test_risk_analyzer.py   # Unit tests for analyze_risk
├── test_spread_simulator.py
├── test_gnews_fetcher.py   # Mocks requests.get
└── test_main.py            # /analyze via TestClient
```

Naming: `test_<module>.py`, with functions named `test_<behavior>`.

## Test File Organization

**Location:**
- Not established. Recommended: separate `tests/` directory, not co-located, because the source is a flat set of root-level modules.

**Naming:**
- Recommended: `test_<module_name>.py`.

## Test Structure

**Suite Organization (recommended, plain functions per pytest convention):**

```python
from risk_analyzer import analyze_risk

def test_high_risk_keyword_returns_high():
    assert analyze_risk("Celebrity death hoax spreads") == "High"

def test_no_keyword_falls_back_to_medium():
    assert analyze_risk("Completely unrelated sentence") == "Medium"
```

**Patterns to test (behavior observed in source):**
- `analyze_risk` in `risk_analyzer.py` is case-insensitive (it lowercases input) and checks lists in priority order: High, then Medium, then Low, returning the first match. A text that contains both a High and a Low keyword returns `"High"`. Write tests for that precedence.
- Default return is `"Medium"` when no keyword matches.
- `simulate_spread` in `spread_simulator.py` produces `1 + 6 * len(USERS)` events when `risk == "High"` (6 per platform) and `1 + 3 * len(USERS)` otherwise. Each platform chain links `parent_event_id` to the previous event; the first event in each platform chain points to the root `event_id`.
- Spread `timestamp` values are `base + 5..60 minutes` and are emitted as ISO strings; the `Z` suffix is stripped from the root timestamp before parsing.
- `main.py` `/analyze` returns a fallback single article when `fetch_news` returns `[]`. Test this by monkeypatching `main.fetch_news`.

## Mocking

**Framework:** `unittest.mock` (stdlib) or the `pytest-mock` `mocker` fixture. Neither is installed yet.

**Recommended patterns:**

Mock the network call in `gnews_fetcher.py` rather than hitting gnews.io:

```python
from unittest import mock

import gnews_fetcher

def test_fetch_news_parses_articles(monkeypatch):
    fake_response = mock.Mock()
    fake_response.json.return_value = {
        "articles": [
            {"title": "T", "source": {"name": "S"}, "publishedAt": "2025-01-01T00:00:00Z"}
        ]
    }
    monkeypatch.setattr(gnews_fetcher.requests, "get", lambda *a, **k: fake_response)
    monkeypatch.setattr(gnews_fetcher, "GNEWS_API_KEY", "test-key")
    assert gnews_fetcher.fetch_news("q") == [
        {"title": "T", "source": "S", "publishedAt": "2025-01-01T00:00:00Z"}
    ]
```

Note: `fetch_news` contains a guard that tests a string literal, not `GNEWS_API_KEY`, so it never returns early for an empty key. Tests that expect `[]` for an unconfigured key will currently fail; see `CONVENTIONS.md` and `CONCERNS.md`.

Override the pipeline in `main.py` for route tests:

```python
from fastapi.testclient import TestClient

import main

def test_analyze_falls_back_when_no_articles(monkeypatch):
    monkeypatch.setattr(main, "fetch_news", lambda q: [])
    client = TestClient(main.app)
    body = client.get("/analyze", params={"query": "x"}).json()
    assert body[0]["headline"] == "x"
```

**What to Mock:**
- Outbound HTTP in `gnews_fetcher.py` (`requests.get`).
- `fetch_news` when testing `/analyze` routing and fallback logic.
- `random` in `spread_simulator.py` when asserting exact event contents (seed with `random.seed(...)` or patch `random.choice` / `random.randint`).

**What NOT to Mock:**
- `analyze_risk`: it is pure and cheap; test it directly.
- `simulate_spread` internals: exercise them with the real `USERS` data from `users.py`.
- Pydantic `Event` model: validate real dicts against it when testing shape.

## Fixtures and Factories

**Test Data:**
- No fixtures exist. The closest equivalent is the static `USERS` dict in `users.py`, which the spread simulator consumes directly.
- A typical article fixture (matching the shape `fetch_news` returns):

```python
ARTICLE = {
    "title": "Officials announce new policy",
    "source": "Example News",
    "publishedAt": "2025-01-01T10:00:00Z",
}
```

**Location:**
- Recommended: `tests/conftest.py` for shared fixtures.

## Coverage

**Requirements:** None enforced.

**View Coverage (once pytest-cov is installed):**

```bash
python -m pytest --cov=. --cov-report=term-missing
```

## Test Types

**Unit Tests:**
- Not present. Highest-value first targets: `analyze_risk` (`risk_analyzer.py`), `simulate_spread` and `create_root_event` (`spread_simulator.py`).

**Integration Tests:**
- Not present. Recommended: `TestClient` against `main.app` with `fetch_news` patched, as shown above.

**E2E Tests:**
- Not used. No frontend test tooling is present.

## Known Gaps (Untested Risk Areas)

- `gnews_fetcher.fetch_news`: no test for HTTP errors, non-JSON responses, or articles missing `title`/`source`/`publishedAt`.
- `models.Event`: not exercised by any code path.
- `spread_simulator.simulate_spread`: assumes `publishedAt` parses via `datetime.fromisoformat` after stripping `Z`; offsets like `+05:00` are not handled by the `replace` and will behave differently. No test covers this.
- Live network behavior: nothing verifies the real GNews response schema.

## Common Patterns

**Async Testing:**
- Not applicable. All functions are synchronous, including the FastAPI route `analyze` in `main.py` (defined with `def`, not `async def`).

**Error Testing (recommended):**

```python
import pytest

def test_simulate_spread_rejects_bad_timestamp():
    from spread_simulator import create_root_event, simulate_spread

    root = create_root_event({"title": "t", "source": "s", "publishedAt": "not-a-date"})
    with pytest.raises(ValueError):
        simulate_spread(root, "High")
```

---

*Testing analysis: 2026-10-11*
