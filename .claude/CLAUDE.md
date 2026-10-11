<!-- GSD:project-start source:PROJECT.md -->

## Project

**TruthTrail**

TruthTrail is a misinformation early-warning system: it ingests news and social-propagation data, scores how likely a claim is to be misleading using a trained and evaluated classifier, and visualizes how the claim spreads (cascade graph, timeline, risk with confidence) so a human reviewer can prioritize what to look at first. It began as a hackathon prototype (keyword rules plus a random "spread" generator) and is being rebuilt into a credible, deployed, portfolio-grade project aimed at hiring reviewers (SWE / ML / full-stack). Results are always framed as "flag for human review", never "truth detection".

**Core Value:** Every risk score and every cascade the system shows is backed by real data and a measured, reproducible evaluation. Nothing fabricated is ever presented as analysis.

### Constraints

- **Tech stack**: Keep Python + FastAPI for the backend; React + TypeScript (Vite) for the frontend; Postgres for storage — a coherent, mainstream stack that reviewers recognize and that reuses the existing service.
- **Timeline**: v1 targeted at ~4-6 weeks part-time; v2 (~6 more weeks) is optional — v1 must stand alone as a shippable portfolio piece.
- **Data access**: Free and open sources only (Bluesky Jetstream / Mastodon, public research datasets) — paid APIs are out of reach; verify each source's terms and rate limits in a spike before building on it.
- **Compute**: No GPU in the dev environment — model fine-tuning (v2) is trained offline (Colab/Kaggle); the repo ships code, metrics and a model card, never weights.
- **Security**: Secrets only via environment variables, never committed; scan `.planning/` and code for key material before every commit.
- **Process / git**: All work on branch `claude/sleepy-lovelace-13aums`; no per-phase branches; no pull requests unless the owner explicitly asks; push after each phase (the dev container is ephemeral).
- **Honesty**: User-facing copy must say "flag for human review", never "detects the truth"; synthetic or demo data is always labelled as such in both API and UI.

<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->

## Technology Stack

## Languages

- Python 3 - All backend code: `main.py`, `gnews_fetcher.py`, `risk_analyzer.py`, `spread_simulator.py`, `users.py`, `models.py`
- JavaScript (npm ecosystem) - Only a dependency manifest is present (`package.json`, `package-lock.json`). No `.js`, `.jsx`, `.ts`, or `.tsx` source files exist in the repository, so the frontend is either absent or lives outside this repo.

## Runtime

- Python 3 (exact version not pinned; no `.python-version`, `runtime.txt`, or `pyproject.toml` present)
- Node.js (version not pinned; no `.nvmrc` or `engines` field in `package.json`)
- pip - Python dependencies from `requirements.txt` (unpinned)
- npm - JavaScript dependencies from `package.json`

## Frameworks

- FastAPI (unpinned) - HTTP API framework; single app object `app = FastAPI()` in `main.py`
- Uvicorn (unpinned) - ASGI server listed in `requirements.txt`. No launch command or config file is in the repo; it is presumably run as `uvicorn main:app`.
- Pydantic - Used for the `Event` model in `models.py` (`BaseModel`). Not declared in `requirements.txt`; it is available only as a transitive dependency of FastAPI.
- Recharts `^3.7.0` (lockfile resolves to 3.7.0) - React charting library declared in `package.json`. No code in this repo imports it.
- Not detected. No test framework, test files, or test config are present.
- Not detected. No bundler, linter, formatter, or type-checker config is present.

## Key Dependencies

- `fastapi` (unpinned) - API routing, query parameter validation, CORS middleware (`main.py`)
- `uvicorn` (unpinned) - ASGI server
- `requests` (unpinned) - Outbound HTTP to the GNews API in `gnews_fetcher.py`
- `uuid`, `random`, `datetime` (incl. `timedelta`) - Event IDs and spread simulation in `spread_simulator.py`
- `typing.Optional` - `models.py`
- `recharts` `^3.7.0` - Declared dependency; no consuming code in repo
- `react` 19.2.4, `react-dom` 19.2.4, `react-redux` 9.2.0, `@reduxjs/toolkit` 2.11.2, `redux` 5.0.1
- Recharts' own dependencies (`d3-*`, `victory-vendor`, `immer`, `es-toolkit`, etc.)
- Note: the lockfile root entry (`""`) lists only `recharts`, so `@reduxjs/toolkit`, `react-redux`, and `react-dom` appear to be leftovers from an earlier `npm install` and are not used by any source file. Treat them as undeclared.

## Configuration

- No `.env` file is present in the repository. Reads of configuration are not implemented through environment variables; the GNews key is hardcoded (see `gnews_fetcher.py:3`). See INTEGRATIONS.md for the security implications.
- No `config/` directory or settings module exists.
- No build configuration (`tsconfig.json`, `vite.config.*`, `webpack.config.*`, `Dockerfile`, `Makefile`, CI workflows) detected.

## Platform Requirements

- Python 3 with `pip install -r requirements.txt`
- Node.js with npm to install `package.json` dependencies (only needed for the Recharts dependency)
- Run backend: `uvicorn main:app --reload` (inferred from the `app` object in `main.py`; not documented in `README.md`)
- Not configured. No deployment target, container image, or process manager is defined. The FastAPI app permits all CORS origins (`main.py:9-14`), which is only appropriate for local development.

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

## Scope of the Codebase

- `main.py` (FastAPI app and `/analyze` route)
- `models.py` (Pydantic model)
- `users.py` (static user data)
- `gnews_fetcher.py` (external news API client)
- `risk_analyzer.py` (rule-based risk classifier)
- `spread_simulator.py` (synthetic spread event generator)

## Naming Patterns

- Python modules use `snake_case.py` with a single noun or noun phrase: `gnews_fetcher.py`, `risk_analyzer.py`, `spread_simulator.py`, `users.py`, `models.py`, `main.py`.
- Keep new modules in this flat style at the repo root unless the project grows into packages (see `STRUCTURE.md`).
- `snake_case` verbs describing the action: `fetch_news(query)` in `gnews_fetcher.py`, `analyze_risk(text)` in `risk_analyzer.py`, `create_root_event(article)` and `simulate_spread(root, risk)` in `spread_simulator.py`, `analyze(query)` route handler in `main.py`.
- `snake_case` for locals and parameters: `articles`, `risk`, `root`, `parent`, `base`, `spread`.
- Short single-letter loop variables are used for throwaway values: `a` (article in `gnews_fetcher.py`), `u` (user in `spread_simulator.py`), `r` (HTTP response in `gnews_fetcher.py`), `_` for unused loop counters.
- `UPPER_SNAKE_CASE` for module-level constants: `GNEWS_API_KEY` in `gnews_fetcher.py`, `USERS` in `users.py`.
- Keyword lists inside `analyze_risk` are local variables in lowercase `snake_case`: `high_risk_keywords`, `medium_risk_keywords`, `low_risk_keywords` in `risk_analyzer.py`.
- Event and API payload keys use `snake_case` (`event_id`, `parent_event_id`, `content_id`, `user_influence`) in `spread_simulator.py` and the `Event` model in `models.py`.
- Response keys returned by `/analyze` use `camelCase` for the article timestamp (`publishedAt`) and `headline`/`risk`/`events` in `main.py`. This is an inconsistency: `publishedAt` is camelCase while `event_id` and `user_influence` are snake_case. Follow the existing shape per payload when editing a given structure, and do not rename keys without updating every consumer.
- Pydantic models use `PascalCase` class names: `Event` in `models.py`.

## Code Style

- Indentation is 4 spaces in all Python files.
- Double quotes are used for strings in most places (`"title"`, `"news"`), with single quotes not used.
- No enforced line-length limit; lines in `risk_analyzer.py` and `spread_simulator.py` run to roughly 100 characters.
- Trailing commas are used in multi-line dict and list literals in `main.py`, `users.py`, and `risk_analyzer.py`, but not consistently in `spread_simulator.py`.
- Blank lines: two blank lines between top-level imports and definitions are not used; one blank line separates functions in `main.py`, and `spread_simulator.py` uses one blank line between functions.
- Formatting tool: Not detected. If you add one, `ruff format` or `black` matches the existing 4-space, double-quote style.
- Not detected. No lint configuration or CI config exists.
- Inconsistent. `analyze_risk(text: str) -> str` in `risk_analyzer.py` is the only fully annotated function. `fetch_news`, `create_root_event`, `simulate_spread`, and the `analyze` route in `main.py` have no annotations, while `main.py` uses FastAPI's typed query parameter `query: str`.
- For new code, annotate function signatures and return types. Use `Optional[X]` from `typing` in `models.py` style or `X | None` if the target Python version allows it (Python version is not pinned in the repo).

## Import Organization

- Not applicable. Modules are imported by bare name from the repo root (flat layout), so scripts must be run from the repository root.

## Error Handling

- Little explicit error handling exists. There are no `try`/`except` blocks in any file.
- `main.py` uses a fallback instead of an error response: when `fetch_news` returns an empty list, it substitutes a single synthetic article (`"source": "unknown"`, fixed `publishedAt` of `2025-01-01T10:00:00Z`) so the frontend always receives data. Keep this "never break the frontend" behavior in mind when changing `/analyze`.
- `gnews_fetcher.py` returns `[]` to signal "no data or not configured". Callers treat an empty list as the normal fallback path, so do not raise from `fetch_news` for missing data. The API-key guard in that function is written as `if not "<literal>" or "PUT_" in "<literal>":` (line 6), which tests a string literal rather than the `GNEWS_API_KEY` variable and does not behave as a real placeholder check. Reference `gnews_fetcher.py` directly when touching this guard.
- `gnews_fetcher.py` calls `r.json()` and indexes `a["title"]`, `a["source"]["name"]`, `a["publishedAt"]` without checking HTTP status or missing keys. A failed request or malformed article raises `KeyError`/`ValueError` up to the FastAPI handler, which returns a 500.
- Recommended for new code: check `r.status_code` / use `r.raise_for_status()` and wrap the external call in `try`/`except requests.RequestException`, returning `[]` to match the existing fallback contract.

## Logging

- Not applicable today. If logging is added, use the standard library `logging` module with `logger = logging.getLogger(__name__)` per module rather than `print`.

## Comments

- Comments are used sparingly to label sections of logic, and they are often prefixed with an emoji marker: `# 🔥 FALLBACK so frontend NEVER breaks` in `main.py`, `# 🔴 HIGH RISK`, `# 🟡 MEDIUM RISK`, `# 🔵 LOW RISK`, and `# 🔍 Scoring logic` in `risk_analyzer.py`.
- Inline comments explain intent for non-obvious rules, such as `# Default (neutral but cautious)` before the final `return "Medium"` in `risk_analyzer.py`.
- One docstring exists: `analyze_risk` in `risk_analyzer.py` describes the function as a "Rule-based risk analyzer for misinformation" with a short note on keyword patterns. Other functions have no docstrings.
- Use triple-double-quoted docstrings in the same style for new public functions.
- Not applicable (no TypeScript/JavaScript source tracked).

## Function Design

- Functions are short (roughly 5 to 40 lines). `analyze_risk` is the longest and is a keyword-list pipeline.
- Positional parameters for required inputs: `fetch_news(query)`, `simulate_spread(root, risk)`.
- Keyword arguments for API calls: `requests.get(url, params=params)`.
- Return plain `dict`s and `list`s, not Pydantic models, from the pipeline functions in `spread_simulator.py` and `gnews_fetcher.py`.
- Return a string label (`"High"`, `"Medium"`, `"Low"`) from `analyze_risk`. These literal strings are the contract used by `simulate_spread` (`risk == "High"` selects spread depth 6, otherwise 3). Do not introduce new labels without updating that comparison.
- Return `[]` for "no results" in `fetch_news`.

## Module Design

- Each module exposes its public functions directly by name. No `__all__` declarations are used.
- Module-level state: `GNEWS_API_KEY` in `gnews_fetcher.py` and `USERS` in `users.py` are module-level globals read at import time.
- Not used. There is no `__init__.py`; imports go directly to the defining module.

## Data Models

- Pydantic `BaseModel` is used for the `Event` schema in `models.py`, but the pipeline in `spread_simulator.py` builds plain dicts and `main.py` does not use `Event` as a `response_model`. Treat `Event` as documentation of the event shape unless you wire it in explicitly.
- `Event` declares `parent_event_id: Optional[str]` without a default. Under Pydantic v2 this field is required (it must be passed explicitly, even as `None`).

## Secrets Handling

- `gnews_fetcher.py` contains a hardcoded GNews API key as a module-level constant (`GNEWS_API_KEY`, line 3). This violates the convention that secrets come from the environment. New code must read credentials from environment variables (for example `os.environ["GNEWS_API_KEY"]`) and must never copy the literal value into other files or documents. Rotate the key and move it out of source control.

<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

## System Overview

```text

```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| API / orchestration | Defines the `/analyze` route, applies CORS, runs the fetch → classify → simulate pipeline per article, applies a fallback article | `main.py` |
| News ingestion | Calls the GNews search endpoint and normalises articles to `{title, source, publishedAt}` | `gnews_fetcher.py` |
| Risk classifier | Keyword-based scoring of a headline into `High`, `Medium`, or `Low` | `risk_analyzer.py` |
| Spread simulator | Builds a root event and synthetic propagation events across platforms | `spread_simulator.py` |
| Static user pools | Hard-coded simulated accounts per platform with influence scores | `users.py` |
| Event schema | Pydantic model describing a propagation event; not imported by any module | `models.py` |
| Dependency manifests | Python packages for the backend; npm package for the (absent) frontend | `requirements.txt`, `package.json` |

## Pattern Overview

- Single request/response flow: each `GET /analyze` call performs ingestion, classification, and simulation synchronously and returns the result in the response body.
- All state is per-request. Nothing is persisted; event IDs are random UUID4 values regenerated on every call.
- Modules are imported by name from the repository root (`from gnews_fetcher import fetch_news`), so the process must be started from the repository root.
- Simulated data (users, spread) is generated locally; only news titles come from an external service.

## Layers

- Purpose: HTTP surface and orchestration.
- Location: `main.py`
- Contains: `FastAPI` app instance, `CORSMiddleware` configuration, the `analyze` route handler.
- Depends on: `gnews_fetcher`, `risk_analyzer`, `spread_simulator`
- Used by: HTTP clients (no client code in this repository).
- Purpose: Retrieve recent news headlines for a query.
- Location: `gnews_fetcher.py`
- Contains: `fetch_news(query)`, module-level constants `GNEWS_API_KEY` and `url`.
- Depends on: `requests`, external GNews API at `https://gnews.io/api/v4/search`.
- Used by: `main.py` only.
- Purpose: Score misinformation risk and generate spread events.
- Location: `risk_analyzer.py`, `spread_simulator.py`
- Contains: `analyze_risk(text) -> str`, `create_root_event(article) -> dict`, `simulate_spread(root, risk) -> list[dict]`.
- Depends on: `spread_simulator.py` depends on `users.py` (`USERS`), and on `uuid`, `random`, `datetime` from the standard library.
- Used by: `main.py` only.
- Purpose: Static reference data for simulation.
- Location: `users.py`
- Contains: `USERS` dict keyed by platform (`twitter`, `facebook`, `reddit`), each a list of `{id, influence}` records.
- Depends on: nothing.
- Used by: `spread_simulator.py`.
- Purpose: Intended typed shape of a propagation event.
- Location: `models.py`
- Contains: `Event(BaseModel)` with fields `event_id`, `platform`, `content_id`, `parent_event_id`, `user_id`, `timestamp`, `user_influence`.
- Depends on: `pydantic`
- Used by: Nothing currently. `spread_simulator.py` returns plain dicts with the same keys.

## Data Flow

### Primary Request Path

### Secondary Flow: CORS preflight

### State Management

- No server-side state. No session, cache, database, or queue.
- Randomness (`random.choice`, `random.randint`) and UUIDs are generated per call, so identical queries produce different event graphs.

## Key Abstractions

- Purpose: One node in a spread tree.
- Examples: `spread_simulator.py:6-15` (root), `spread_simulator.py:27-35` (child); `models.py:4-11` (declared schema).
- Pattern: Plain `dict` with keys `event_id`, `platform`, `content_id`, `parent_event_id`, `user_id`, `timestamp`, `user_influence`. Parent linkage through `parent_event_id`.
- Purpose: Model amplification as one chain per platform rooted at the news event.
- Examples: `spread_simulator.py:17-38`
- Pattern: For each platform, `parent` starts at root and advances each iteration, so the result is three independent chains of length `spread` hanging from the root. Total events = `1 + 3 * spread`.
- Purpose: Three-valued label that controls spread depth.
- Examples: `risk_analyzer.py:1-67`, `spread_simulator.py:21`
- Pattern: Ordered keyword lists checked in priority order High → Medium → Low; first match wins; default `"Medium"`.

## Entry Points

- Location: `main.py` (module-level `app = FastAPI()`)
- Triggers: Run with an ASGI server from the repository root, for example `uvicorn main:app` (`uvicorn` is listed in `requirements.txt`; no run script or Dockerfile exists).
- Responsibilities: Route registration, CORS, orchestration of the pipeline.
- None. Helper modules define functions only; importing them has no side effects beyond the `GNEWS_API_KEY` constant and the `USERS` dict.

## Architectural Constraints

- **Threading:** Single process. FastAPI runs the sync `analyze` handler in its threadpool; `fetch_news` performs a blocking `requests.get` with no timeout.
- **Global state:** Module-level constants only: `GNEWS_API_KEY` in `gnews_fetcher.py:3`, `USERS` in `users.py:1`, keyword lists local to `analyze_risk`. No mutable globals.
- **Circular imports:** None. Dependency graph is acyclic: `main` → {`gnews_fetcher`, `risk_analyzer`, `spread_simulator`}; `spread_simulator` → `users`.
- **Import path:** Modules are top-level, so the repository root must be on `sys.path`. There is no package (`__init__.py`) structure.
- **External dependency:** Availability of `gnews.io` determines whether real headlines or the fallback are used.
- **Frontend contract:** Comments in `main.py:20` state the fallback exists so the frontend never breaks; the frontend itself is not in this repository.

## Anti-Patterns

### Hard-coded API credential in source

### Placeholder guard that never fires

### Unvalidated upstream response

### Keyword matching by substring

### Persistence-free random simulation presented as data

## Error Handling

- Empty-result fallback in `main.py:21-26` substitutes the query as the headline.
- `fetch_news` returns `[]` only when the (ineffective) guard triggers or when GNews returns no `articles` key (`gnews_fetcher.py:21`).

## Cross-Cutting Concerns

<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-fast` for a trivial task inline, with no subagents and no PLAN.md
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
