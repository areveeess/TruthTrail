---
last_mapped_commit: 1fedcd29ba790edf42ebc1ffbffe62b9f643177f
last_mapped_at: 2026-10-11
---
# Coding Conventions

**Analysis Date:** 2026-10-11

## Scope of the Codebase

The repository is a small Python backend (FastAPI) at the repo root, plus a `package.json` that declares only `recharts` (no frontend source is tracked). All Python conventions below come from these files:

- `main.py` (FastAPI app and `/analyze` route)
- `models.py` (Pydantic model)
- `users.py` (static user data)
- `gnews_fetcher.py` (external news API client)
- `risk_analyzer.py` (rule-based risk classifier)
- `spread_simulator.py` (synthetic spread event generator)

No linter, formatter, or type-checker configuration is present (no `.eslintrc*`, `.prettierrc*`, `pyproject.toml`, `setup.cfg`, `.editorconfig`, `ruff.toml`, `.flake8`, or `mypy.ini`). The conventions are therefore what the code currently does, not what a tool enforces.

## Naming Patterns

**Files:**
- Python modules use `snake_case.py` with a single noun or noun phrase: `gnews_fetcher.py`, `risk_analyzer.py`, `spread_simulator.py`, `users.py`, `models.py`, `main.py`.
- Keep new modules in this flat style at the repo root unless the project grows into packages (see `STRUCTURE.md`).

**Functions:**
- `snake_case` verbs describing the action: `fetch_news(query)` in `gnews_fetcher.py`, `analyze_risk(text)` in `risk_analyzer.py`, `create_root_event(article)` and `simulate_spread(root, risk)` in `spread_simulator.py`, `analyze(query)` route handler in `main.py`.

**Variables:**
- `snake_case` for locals and parameters: `articles`, `risk`, `root`, `parent`, `base`, `spread`.
- Short single-letter loop variables are used for throwaway values: `a` (article in `gnews_fetcher.py`), `u` (user in `spread_simulator.py`), `r` (HTTP response in `gnews_fetcher.py`), `_` for unused loop counters.

**Constants and module-level data:**
- `UPPER_SNAKE_CASE` for module-level constants: `GNEWS_API_KEY` in `gnews_fetcher.py`, `USERS` in `users.py`.
- Keyword lists inside `analyze_risk` are local variables in lowercase `snake_case`: `high_risk_keywords`, `medium_risk_keywords`, `low_risk_keywords` in `risk_analyzer.py`.

**Dictionary keys and API fields:**
- Event and API payload keys use `snake_case` (`event_id`, `parent_event_id`, `content_id`, `user_influence`) in `spread_simulator.py` and the `Event` model in `models.py`.
- Response keys returned by `/analyze` use `camelCase` for the article timestamp (`publishedAt`) and `headline`/`risk`/`events` in `main.py`. This is an inconsistency: `publishedAt` is camelCase while `event_id` and `user_influence` are snake_case. Follow the existing shape per payload when editing a given structure, and do not rename keys without updating every consumer.

**Types:**
- Pydantic models use `PascalCase` class names: `Event` in `models.py`.

## Code Style

**Formatting:**
- Indentation is 4 spaces in all Python files.
- Double quotes are used for strings in most places (`"title"`, `"news"`), with single quotes not used.
- No enforced line-length limit; lines in `risk_analyzer.py` and `spread_simulator.py` run to roughly 100 characters.
- Trailing commas are used in multi-line dict and list literals in `main.py`, `users.py`, and `risk_analyzer.py`, but not consistently in `spread_simulator.py`.
- Blank lines: two blank lines between top-level imports and definitions are not used; one blank line separates functions in `main.py`, and `spread_simulator.py` uses one blank line between functions.
- Formatting tool: Not detected. If you add one, `ruff format` or `black` matches the existing 4-space, double-quote style.

**Linting:**
- Not detected. No lint configuration or CI config exists.

**Type hints:**
- Inconsistent. `analyze_risk(text: str) -> str` in `risk_analyzer.py` is the only fully annotated function. `fetch_news`, `create_root_event`, `simulate_spread`, and the `analyze` route in `main.py` have no annotations, while `main.py` uses FastAPI's typed query parameter `query: str`.
- For new code, annotate function signatures and return types. Use `Optional[X]` from `typing` in `models.py` style or `X | None` if the target Python version allows it (Python version is not pinned in the repo).

## Import Organization

**Order (as observed):**
1. Third-party framework imports first: `from fastapi import FastAPI`, `from fastapi.middleware.cors import CORSMiddleware` in `main.py`; `from pydantic import BaseModel` in `models.py`; `import requests` in `gnews_fetcher.py`.
2. Standard library imports: `import uuid`, `import random`, `from datetime import datetime, timedelta` in `spread_simulator.py`; `from typing import Optional` in `models.py`. Note that `models.py` and `spread_simulator.py` do not follow the stdlib-before-third-party order used elsewhere; `models.py` imports pydantic before typing.
3. Local project imports last: `from gnews_fetcher import fetch_news`, `from risk_analyzer import analyze_risk`, `from spread_simulator import create_root_event, simulate_spread` in `main.py`; `from users import USERS` in `spread_simulator.py`.

**Path Aliases:**
- Not applicable. Modules are imported by bare name from the repo root (flat layout), so scripts must be run from the repository root.

## Error Handling

**Patterns observed:**
- Little explicit error handling exists. There are no `try`/`except` blocks in any file.
- `main.py` uses a fallback instead of an error response: when `fetch_news` returns an empty list, it substitutes a single synthetic article (`"source": "unknown"`, fixed `publishedAt` of `2025-01-01T10:00:00Z`) so the frontend always receives data. Keep this "never break the frontend" behavior in mind when changing `/analyze`.
- `gnews_fetcher.py` returns `[]` to signal "no data or not configured". Callers treat an empty list as the normal fallback path, so do not raise from `fetch_news` for missing data. The API-key guard in that function is written as `if not "<literal>" or "PUT_" in "<literal>":` (line 6), which tests a string literal rather than the `GNEWS_API_KEY` variable and does not behave as a real placeholder check. Reference `gnews_fetcher.py` directly when touching this guard.
- `gnews_fetcher.py` calls `r.json()` and indexes `a["title"]`, `a["source"]["name"]`, `a["publishedAt"]` without checking HTTP status or missing keys. A failed request or malformed article raises `KeyError`/`ValueError` up to the FastAPI handler, which returns a 500.
- Recommended for new code: check `r.status_code` / use `r.raise_for_status()` and wrap the external call in `try`/`except requests.RequestException`, returning `[]` to match the existing fallback contract.

## Logging

**Framework:** None. No `logging` import and no `print` calls exist in the Python source.

**Patterns:**
- Not applicable today. If logging is added, use the standard library `logging` module with `logger = logging.getLogger(__name__)` per module rather than `print`.

## Comments

**When to Comment:**
- Comments are used sparingly to label sections of logic, and they are often prefixed with an emoji marker: `# 🔥 FALLBACK so frontend NEVER breaks` in `main.py`, `# 🔴 HIGH RISK`, `# 🟡 MEDIUM RISK`, `# 🔵 LOW RISK`, and `# 🔍 Scoring logic` in `risk_analyzer.py`.
- Inline comments explain intent for non-obvious rules, such as `# Default (neutral but cautious)` before the final `return "Medium"` in `risk_analyzer.py`.

**Docstrings:**
- One docstring exists: `analyze_risk` in `risk_analyzer.py` describes the function as a "Rule-based risk analyzer for misinformation" with a short note on keyword patterns. Other functions have no docstrings.
- Use triple-double-quoted docstrings in the same style for new public functions.

**JSDoc/TSDoc:**
- Not applicable (no TypeScript/JavaScript source tracked).

## Function Design

**Size:**
- Functions are short (roughly 5 to 40 lines). `analyze_risk` is the longest and is a keyword-list pipeline.

**Parameters:**
- Positional parameters for required inputs: `fetch_news(query)`, `simulate_spread(root, risk)`.
- Keyword arguments for API calls: `requests.get(url, params=params)`.

**Return Values:**
- Return plain `dict`s and `list`s, not Pydantic models, from the pipeline functions in `spread_simulator.py` and `gnews_fetcher.py`.
- Return a string label (`"High"`, `"Medium"`, `"Low"`) from `analyze_risk`. These literal strings are the contract used by `simulate_spread` (`risk == "High"` selects spread depth 6, otherwise 3). Do not introduce new labels without updating that comparison.
- Return `[]` for "no results" in `fetch_news`.

## Module Design

**Exports:**
- Each module exposes its public functions directly by name. No `__all__` declarations are used.
- Module-level state: `GNEWS_API_KEY` in `gnews_fetcher.py` and `USERS` in `users.py` are module-level globals read at import time.

**Barrel Files:**
- Not used. There is no `__init__.py`; imports go directly to the defining module.

## Data Models

- Pydantic `BaseModel` is used for the `Event` schema in `models.py`, but the pipeline in `spread_simulator.py` builds plain dicts and `main.py` does not use `Event` as a `response_model`. Treat `Event` as documentation of the event shape unless you wire it in explicitly.
- `Event` declares `parent_event_id: Optional[str]` without a default. Under Pydantic v2 this field is required (it must be passed explicitly, even as `None`).

## Secrets Handling

- `gnews_fetcher.py` contains a hardcoded GNews API key as a module-level constant (`GNEWS_API_KEY`, line 3). This violates the convention that secrets come from the environment. New code must read credentials from environment variables (for example `os.environ["GNEWS_API_KEY"]`) and must never copy the literal value into other files or documents. Rotate the key and move it out of source control.

---

*Convention analysis: 2026-10-11*
