---
last_mapped_commit: 1fedcd29ba790edf42ebc1ffbffe62b9f643177f
last_mapped_at: 2026-10-11
---
<!-- refreshed: 2026-10-11 -->

# Architecture

**Analysis Date:** 2026-10-11

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                  HTTP API (FastAPI app)                      │
│                     `main.py`                                │
│                 GET /analyze?query=...                       │
└────────┬──────────────────────┬──────────────────────┬───────┘
         │                      │                      │
         ▼                      ▼                      ▼
┌──────────────────┐  ┌──────────────────────┐  ┌────────────────────────┐
│  News ingestion  │  │   Risk classifier    │  │   Spread simulation    │
│ `gnews_fetcher.py`│ │ `risk_analyzer.py`   │  │ `spread_simulator.py`  │
└────────┬─────────┘  └──────────────────────┘  └───────────┬────────────┘
         │                                                  │
         ▼                                                  ▼
┌──────────────────┐                             ┌────────────────────────┐
│ GNews HTTP API   │                             │ Static user pools      │
│ (external)       │                             │ `users.py`            │
└──────────────────┘                             └────────────────────────┘

Unused by runtime path: `models.py` (Pydantic `Event` schema)
Absent: frontend (`package.json` declares `recharts` but no UI code exists)
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

**Overall:** Flat, single-process, script-style modular monolith. One FastAPI application module with stateless, function-based helper modules. No classes except the Pydantic model, no database, no background workers.

**Key Characteristics:**
- Single request/response flow: each `GET /analyze` call performs ingestion, classification, and simulation synchronously and returns the result in the response body.
- All state is per-request. Nothing is persisted; event IDs are random UUID4 values regenerated on every call.
- Modules are imported by name from the repository root (`from gnews_fetcher import fetch_news`), so the process must be started from the repository root.
- Simulated data (users, spread) is generated locally; only news titles come from an external service.

## Layers

**API layer:**
- Purpose: HTTP surface and orchestration.
- Location: `main.py`
- Contains: `FastAPI` app instance, `CORSMiddleware` configuration, the `analyze` route handler.
- Depends on: `gnews_fetcher`, `risk_analyzer`, `spread_simulator`
- Used by: HTTP clients (no client code in this repository).

**Ingestion layer:**
- Purpose: Retrieve recent news headlines for a query.
- Location: `gnews_fetcher.py`
- Contains: `fetch_news(query)`, module-level constants `GNEWS_API_KEY` and `url`.
- Depends on: `requests`, external GNews API at `https://gnews.io/api/v4/search`.
- Used by: `main.py` only.

**Domain logic layer:**
- Purpose: Score misinformation risk and generate spread events.
- Location: `risk_analyzer.py`, `spread_simulator.py`
- Contains: `analyze_risk(text) -> str`, `create_root_event(article) -> dict`, `simulate_spread(root, risk) -> list[dict]`.
- Depends on: `spread_simulator.py` depends on `users.py` (`USERS`), and on `uuid`, `random`, `datetime` from the standard library.
- Used by: `main.py` only.

**Data/reference layer:**
- Purpose: Static reference data for simulation.
- Location: `users.py`
- Contains: `USERS` dict keyed by platform (`twitter`, `facebook`, `reddit`), each a list of `{id, influence}` records.
- Depends on: nothing.
- Used by: `spread_simulator.py`.

**Schema layer (unused):**
- Purpose: Intended typed shape of a propagation event.
- Location: `models.py`
- Contains: `Event(BaseModel)` with fields `event_id`, `platform`, `content_id`, `parent_event_id`, `user_id`, `timestamp`, `user_influence`.
- Depends on: `pydantic`
- Used by: Nothing currently. `spread_simulator.py` returns plain dicts with the same keys.

## Data Flow

### Primary Request Path

1. Client sends `GET /analyze?query=<text>`; FastAPI binds `query` as a required string parameter (`main.py:16-17`).
2. `fetch_news(query)` requests up to 1 English article from GNews and returns a list of `{title, source, publishedAt}` dicts (`gnews_fetcher.py:5-26`).
3. If the list is empty, `main.py` substitutes a single fallback article whose title is the raw query, source is `"unknown"`, and `publishedAt` is `"2025-01-01T10:00:00Z"` (`main.py:21-26`).
4. For each article, `analyze_risk(article["title"])` returns `"High"`, `"Medium"`, or `"Low"` (`main.py:31`, `risk_analyzer.py:1-67`).
5. `create_root_event(article)` builds a root event with `platform: "news"`, `user_id` set to the article source name, and `user_influence: 90` (`main.py:32`, `spread_simulator.py:6-15`).
6. `simulate_spread(root, risk)` emits the root plus, for each platform in `USERS`, a chain of `N` events where `N = 6` for `High` risk and `3` otherwise; each event picks a random user from the platform pool and a timestamp 5–60 minutes after the root (`spread_simulator.py:17-38`).
7. The handler returns a JSON list of `{headline, risk, events}` objects, one per article (`main.py:35-41`).

Each request yields at most one article, so the list in the response has length 1 in normal operation.

### Secondary Flow: CORS preflight

1. Browser issues a preflight `OPTIONS` request.
2. `CORSMiddleware` answers with wildcard origin, methods, and headers (`main.py:9-14`).

### State Management

- No server-side state. No session, cache, database, or queue.
- Randomness (`random.choice`, `random.randint`) and UUIDs are generated per call, so identical queries produce different event graphs.

## Key Abstractions

**Event (propagation record):**
- Purpose: One node in a spread tree.
- Examples: `spread_simulator.py:6-15` (root), `spread_simulator.py:27-35` (child); `models.py:4-11` (declared schema).
- Pattern: Plain `dict` with keys `event_id`, `platform`, `content_id`, `parent_event_id`, `user_id`, `timestamp`, `user_influence`. Parent linkage through `parent_event_id`.

**Spread tree shape:**
- Purpose: Model amplification as one chain per platform rooted at the news event.
- Examples: `spread_simulator.py:17-38`
- Pattern: For each platform, `parent` starts at root and advances each iteration, so the result is three independent chains of length `spread` hanging from the root. Total events = `1 + 3 * spread`.

**Risk level:**
- Purpose: Three-valued label that controls spread depth.
- Examples: `risk_analyzer.py:1-67`, `spread_simulator.py:21`
- Pattern: Ordered keyword lists checked in priority order High → Medium → Low; first match wins; default `"Medium"`.

## Entry Points

**HTTP application:**
- Location: `main.py` (module-level `app = FastAPI()`)
- Triggers: Run with an ASGI server from the repository root, for example `uvicorn main:app` (`uvicorn` is listed in `requirements.txt`; no run script or Dockerfile exists).
- Responsibilities: Route registration, CORS, orchestration of the pipeline.

**Module-level execution:**
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

**What happens:** The GNews API key is assigned as a literal string constant at `gnews_fetcher.py:3` and repeated as a literal in the guard at `gnews_fetcher.py:6`.
**Why it's wrong:** The value is committed to version control and shipped with every copy of the repository. The key is therefore exposed to anyone with read access.
**Do this instead:** Read the key from the environment (for example `os.environ["GNEWS_API_KEY"]`) and keep it out of tracked files. Rotate the existing key.

### Placeholder guard that never fires

**What happens:** `gnews_fetcher.py:6` reads `if not "<literal>" or "PUT_" in "<literal>":`. `not` applied to a non-empty string literal is always `False`, and `"PUT_" in <literal>` is also `False`, so the early `return []` is unreachable.
**Why it's wrong:** The intended "missing key" short-circuit is dead code. A missing or placeholder key still triggers a network call, and the failure surfaces as a KeyError or an empty response instead of the intended fallback path.
**Do this instead:** Test the variable, not the literal: `if not GNEWS_API_KEY or "PUT_" in GNEWS_API_KEY: return []`.

### Unvalidated upstream response

**What happens:** `fetch_news` indexes `a["title"]`, `a["source"]["name"]`, and `a["publishedAt"]` directly (`gnews_fetcher.py:22-25`) and does not check the HTTP status before calling `r.json()` (`gnews_fetcher.py:17-18`).
**Why it's wrong:** A rate-limit or error response that lacks the expected keys raises an exception inside the request handler, producing a 500 instead of the fallback in `main.py:21-26`.
**Do this instead:** Check `r.status_code` and use `.get()` with defaults, returning `[]` on any malformed record so the fallback path is taken.

### Keyword matching by substring

**What happens:** `analyze_risk` tests `word in text` on raw substrings (`risk_analyzer.py:54-64`). Short terms such as `"dead"`, `"cure"`, and `"theory"` match inside longer words.
**Why it's wrong:** Headlines are misclassified (for example, "deadline" scores High). Because High is checked first, one false match changes spread depth from 3 to 6.
**Do this instead:** Match on word boundaries (`re.search(rf"\b{re.escape(word)}\b", text)`) and keep the priority order.

### Persistence-free random simulation presented as data

**What happens:** `simulate_spread` generates new random users and timestamps on every call (`spread_simulator.py:26-33`), and the response is indistinguishable from real propagation data.
**Why it's wrong:** Consumers cannot tell simulated events from observed ones, and results are not reproducible.
**Do this instead:** Mark events as simulated in the payload, or accept an injectable `random.Random` seed for reproducible tests.

## Error Handling

**Strategy:** Minimal. No try/except blocks in the codebase. Failures in the network call or JSON parsing propagate to FastAPI's default 500 handler.

**Patterns:**
- Empty-result fallback in `main.py:21-26` substitutes the query as the headline.
- `fetch_news` returns `[]` only when the (ineffective) guard triggers or when GNews returns no `articles` key (`gnews_fetcher.py:21`).

## Cross-Cutting Concerns

**Logging:** None. No `logging` import or print statements.
**Validation:** Only FastAPI's type coercion on `query: str` (`main.py:17`). The `models.py` `Event` schema is not applied to outputs.
**Authentication:** None on the API. CORS is open to all origins (`main.py:9-14`). The upstream GNews call authenticates with a query-string API key (`gnews_fetcher.py:14`).

---

*Architecture analysis: 2026-10-11*
