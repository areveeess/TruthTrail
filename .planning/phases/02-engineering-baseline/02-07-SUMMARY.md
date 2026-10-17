---
phase: 02-engineering-baseline
plan: 07
subsystem: api
tags: [rate-limit, slowapi, problem-json, proxy-headers, uvicorn, fastapi]

requires:
  - phase: 02-engineering-baseline
    provides: plan 02-06 create_app() with readiness registry, problem+json builders, BootSettings, client_factory
provides:
  - "Per-client-IP in-memory rate limit on GET /analyze (default 10/minute, RATE_LIMIT_ANALYZE) with a 429 problem+json answer and computed Retry-After"
  - "LimitedRouter and an empty /v1 mount (V1_REGISTRARS, build_v1_router) that rate limits every route registered on it (default 60/minute, RATE_LIMIT_V1)"
  - "Trusted-proxy switch: TRUST_PROXY_HEADERS (default false) and FORWARDED_ALLOW_IPS, with the server always started with --no-proxy-headers"
  - "Real-uvicorn subprocess proof, with a default-flags negative control, that a spoofed X-Forwarded-For cannot change the rate-limit key"
affects: [02-08, 02-09, 02-11, 02-12, 03, 04]

actuals:
  tokens: 7600
  tasks: 2
  commits: 2
plan_head_before: e5ff4c80596abc156470d65d4670314fe75cb925
plan_head_after: ed335cf3a778324ee3504ddd96915a77da9712f9

tech-stack:
  added: []
  patterns:
    - "slowapi through decorators only; limiter built per app by create_app() and stored on app.state.limiter"
    - "Callable limits (lambda: get_settings().rate_limit_*) are evaluated per request, so create_app() stays import-safe"
    - "LimitedRouter wraps every endpoint at add_api_route, so forgetting a /v1 limit is impossible"
    - "Retry-After is computed in the 429 handler from limiter.limiter.get_window_stats, never from slowapi headers"

key-files:
  created:
    - src/truthtrail/api/limits.py
    - src/truthtrail/api/v1.py
    - tests/test_rate_limit.py
    - tests/test_v1_limits.py
    - tests/test_proxy_headers_server.py
  modified:
    - src/truthtrail/api/analyze.py
    - src/truthtrail/api/app.py
    - src/truthtrail/api/problems.py
    - src/truthtrail/core/config.py
    - src/truthtrail/core/boot.py
    - tests/conftest.py
    - tests/test_no_hardcoded_credentials.py
    - .env.example

key-decisions:
  - "slowapi was used as planned; the limits-only fallback was not needed"
  - "429 is the only new response code and is declared on /analyze only (problem+json, integer Retry-After header); the golden OpenAPI test passes unchanged"
  - "The server is always started with --no-proxy-headers; the in-app ProxyHeadersMiddleware (same uvicorn class) is the only place proxy headers are trusted, and only when TRUST_PROXY_HEADERS=true"

requirements-completed: []

status: complete
completed: 2026-10-17
---

# Phase 2 Plan 07: Rate Limiting and the /v1 Mount Summary

**`/analyze` is limited to 10 requests per minute per client IP (the 11th gets a 429 problem+json with `Retry-After` and the provenance members), a `LimitedRouter` mounted at `/v1` rate limits every future route by construction, and a spoofed `X-Forwarded-For` cannot change the limit key unless `TRUST_PROXY_HEADERS=true` and the peer is trusted, proven against a real uvicorn started with `--no-proxy-headers`.**

slowapi was used as planned (decorators only); the `limits`-only fallback from the research doc was not needed.

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | 26e6526 | feat(ratelimit): per-IP limiter on /analyze, 429 problem+json with Retry-After, declared in OpenAPI |
| 2 | ed335cf | feat(ratelimit): /v1 LimitedRouter mount with probe-route 429 proof; trusted-proxy switch; real-uvicorn test that --no-proxy-headers closes the spoof |

## What was built

- **Settings (Task 1).** `Settings.rate_limit_analyze` (`10/minute`) and `rate_limit_v1` (`60/minute`) are validated with `limits.parse_many`. An invalid value raises a `ConfigurationError` through `get_settings()` in the lifespan (exit 3 under uvicorn) whose message names `RATE_LIMIT_ANALYZE` or `RATE_LIMIT_V1` and never the value.
- **Limiter (Task 1).** `api/limits.py`: `client_ip` (peer host or `"unknown"`), `build_limiter()` (`memory://`, `headers_enabled` left off so no `Retry-After` on 200s). `create_app()` builds one limiter per app and stores it on `app.state.limiter`. No `SlowAPIMiddleware`, no `default_limits` anywhere.
- **429 (Task 1).** A dedicated `RateLimitExceeded` handler (decorator form, so mypy strict passes and the class-MRO lookup beats the generic HTTP handler) computes `Retry-After = max(1, ceil(reset_at - now))` from the limiter window and returns `rate_limited` problem+json with `synthetic: false`, `source_status: rate_limited`, `data_as_of: null`. The body holds no client address. `PROBLEM_RESPONSES[429]` declares problem+json and an integer `Retry-After` header; `_problem_only_openapi` strips the duplicate JSON entry for 429.
- **/analyze (Task 1).** `build_analyze_router(limiter)`; the handler gained `request: Request` and `@limiter.limit(lambda: get_settings().rate_limit_analyze)` below the route decorator. Query validation and the settings dependency run before the wrapped function, so 422 and not-configured 500 requests consume no quota. `/health` and `/ready` carry no limit.
- **/v1 (Task 2).** `LimitedRouter(APIRouter)` wraps each endpoint with `limiter.limit(limit)` at `add_api_route`; `api/v1.py` holds `V1_REGISTRARS` (empty; Phases 3 and 4 append) and `build_v1_router(limiter, registrars=None)`. `create_app(*, v1_registrars=None)` includes it. With no registrar nothing appears in OpenAPI.
- **Proxy trust (Task 2).** `BootSettings.trust_proxy_headers` (false) and `forwarded_allow_ips` (`127.0.0.1,::1`). When enabled, `create_app()` adds uvicorn's `ProxyHeadersMiddleware` last (outermost) with the comma-split trusted hosts. The module docstring and a code comment state that the server must always run with `--no-proxy-headers` and never use `*` for `FORWARDED_ALLOW_IPS` unless the container is reachable only through the proxy.
- **Environment names.** `RATE_LIMIT_ANALYZE`, `RATE_LIMIT_V1`, `TRUST_PROXY_HEADERS`, `FORWARDED_ALLOW_IPS` added to `.env.example` (blank `NAME=` lines with comments, including the `--no-proxy-headers` note), `ENV_NAMES` in `tests/conftest.py` (so a developer's or CI's own `FORWARDED_ALLOW_IPS` never leaks into tests) and `EXPECTED_ENV_NAMES` in the credentials test.

## Tests

- `tests/test_rate_limit.py` (14): 11th default request is a full 429 problem+json (Retry-After 1..60, no key or peer in body); no `Retry-After` or `X-RateLimit*` on 200s; `2/minute` via env; limit applies in demo mode; 15 invalid requests do not consume quota; another peer on the same app is unaffected; two apps have independent counters; `/health` and `/ready` answer 200 fifty times each under `1/minute`; CORS headers on a 429 for an allowed origin; invalid `RATE_LIMIT_ANALYZE` and `RATE_LIMIT_V1` stop startup naming the variable without the value; OpenAPI declares the 429; AST guard (with a negative control proving the scanner is not blind) that nothing in `src/truthtrail` imports slowapi's middleware or passes `default_limits`.
- `tests/test_v1_limits.py` (10): probe route registered through `include_router` returns 429 after the configured count (the fail-closed proof); each route has its own bucket; a handler without `request` cannot be registered; defaults are `60/minute` and `10/minute`; the default 60 limit applies with no configuration (61st is 429); no `/v1` path without registrars; spoofed `X-Forwarded-For` ignored with the flag unset; honoured from a trusted peer with the flag on; ignored from an untrusted peer with the flag on; invalid `TRUST_PROXY_HEADERS` names the variable without the value.
- `tests/test_proxy_headers_server.py` (3, about 2.3 s): real `python -m uvicorn truthtrail.main:app` subprocess. (a) `--no-proxy-headers`, flag unset: three spoofed addresses give 200, 200, 429. (b) flag on, `FORWARDED_ALLOW_IPS=127.0.0.1`: three addresses give 200, 200, 200 and a repeat gives 429. (c) negative control with uvicorn defaults: 200, 200, 200, which shows the hole the flag closes and that (a) is not vacuous.

## Verification

- `pytest -q`: 390 passed, 10 xfailed, no XPASS (363 passed at the start; 377 after Task 1, +14; 390 after Task 2, +13).
- `tests/test_openapi_golden.py` and `tests/test_openapi_contract.py` pass with 429 as the only new response code and no `/v1` path. `scripts/copy_guard.py` clean (160 OpenAPI strings).
- `ruff check`, `ruff format --check`, `mypy` (20 source files) clean. `tests/test_no_hardcoded_credentials.py`: 13 passed before each commit; the added-lines scan for 32-hex strings found nothing.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `get_boot_settings` error text hardcoded `CORS_ORIGINS`**
- **Found during:** Task 2 (adding `TRUST_PROXY_HEADERS` to `BootSettings`)
- **Issue:** The `ConfigurationError` raised for any `BootSettings` validation failure always said `CORS_ORIGINS`, so an invalid `TRUST_PROXY_HEADERS` would have blamed the wrong variable.
- **Fix:** The message now names the failing field (upper-cased from the pydantic error location, falling back to `CORS_ORIGINS`) and still omits the value. Existing CORS messages are unchanged.
- **Files modified:** src/truthtrail/core/boot.py
- **Commit:** ed335cf

**2. [Rule 1 - Lint] Unused `noqa` directives**
- **Found during:** Task 2 verification
- **Issue:** ruff RUF100 flagged `# noqa: S310` and `# noqa: S603` in the new subprocess test because `tests/` relaxes the `S` rules.
- **Fix:** Removed the directives.
- **Files modified:** tests/test_proxy_headers_server.py
- **Commit:** ed335cf

Beyond the plan's list I added a few tests (a default-60 behavioural test, a per-route bucket test, an invalid-trust-flag test, a scanner negative control). Otherwise the plan was executed as written.

## Human-verify items carried forward

- No Docker daemon exists in this container. The image `CMD` carrying `--no-proxy-headers` is wired in plan 02-11 (its container test asserts the flag) and documented in plan 02-12; nothing here claims a docker build or a CI run passed.
- Phase 6 hosting: whether the platform proxy needs `TRUST_PROXY_HEADERS=true` with a specific `FORWARDED_ALLOW_IPS` (research assumption A7) is re-decided there; behind a proxy with the flag off every client shares the proxy's address, so the limit becomes global (fails closed).

## Known Stubs

None. `V1_REGISTRARS` is an intentionally empty extension list (documented); Phases 3 and 4 populate it.

## Threat Flags

None beyond the plan's threat model. T-02-19, T-02-20 and T-02-21 are implemented and tested as above. T-02-22 is accepted as planned: slowapi logs a WARNING with the client address when a limit is hit; the 429 body never contains it. ENG-06 stays Pending: the TTL cache and bounded retries land in plans 02-08 and 02-09.

## Self-Check: PASSED

- Files src/truthtrail/api/limits.py, src/truthtrail/api/v1.py, tests/test_rate_limit.py, tests/test_v1_limits.py, tests/test_proxy_headers_server.py: FOUND
- Commits 26e6526 and ed335cf are ancestors of HEAD: FOUND
