---
phase: 02-engineering-baseline
plan: 05
subsystem: api
tags: [fastapi, app-factory, cors, asgi-middleware, pydantic-settings, problem-json]

requires:
  - phase: 02-engineering-baseline
    provides: plan 02-04 ruff and mypy strict baseline; plans 02-01 to 02-03 package layout, golden OpenAPI snapshot and uv project
provides:
  - "create_app() factory (truthtrail.api.app) that builds an independent FastAPI app per call"
  - "build_analyze_router() with SearchQuery, FIXTURE_PATH and load_demo_fixture owned by truthtrail.api.analyze"
  - "BootSettings and get_boot_settings() (truthtrail.core.boot) with validated CORS_ORIGINS"
  - "CatchAllMiddleware (truthtrail.api.catchall) rendering unhandled errors as problem+json inside CORS"
  - "Configured-origin CORS (GET/HEAD/OPTIONS, no credentials); unset means no cross-origin access"
  - "tests/conftest.py client_factory keywords env, client and app_kwargs"
affects: [02-06, 02-07, 02-08, 02-09, 02-10, 02-11, 02-12]

actuals:
  tokens: 40000
  tasks: 2
  commits: 2
plan_head_before: 4ed6a1d4b3a2aeea0e6bbe2e948fa23f75431ddb
plan_head_after: c30f5ed

tech-stack:
  added: []
  patterns:
    - "App factory: every stateful or construction-time object is built inside create_app(); truthtrail.main is only app = create_app()"
    - "Route handlers are defined inside build_*_router() so a later per-app limiter exists when the function is decorated"
    - "Construction-time env values come from a no-required-fields BootSettings; strict Settings are read only in the lifespan (uvicorn exit code 3 is preserved)"
    - "Catch-all pure-ASGI middleware added BEFORE CORSMiddleware (last added is outermost) so 500 responses carry CORS headers"

key-files:
  created:
    - src/truthtrail/api/app.py
    - src/truthtrail/api/analyze.py
    - src/truthtrail/api/catchall.py
    - src/truthtrail/core/boot.py
    - tests/test_app_factory.py
    - tests/test_cors.py
  modified:
    - src/truthtrail/main.py
    - src/truthtrail/api/problems.py
    - src/truthtrail/schemas/models.py
    - tests/conftest.py
    - tests/test_openapi_golden.py
    - tests/test_response_models.py
    - tests/test_no_hardcoded_credentials.py
    - .env.example

key-decisions:
  - "The generic Exception handler is removed from register_problem_handlers; CatchAllMiddleware produces the identical 500 body and log line inside CORS"
  - "Problem.synthetic is Literal[False]; the OpenAPI Problem schema gains exactly const: false (declared D-20 exception, tested)"
  - "Origins must equal scheme://host[:port] exactly (no wildcard, path, query, fragment, userinfo or trailing slash); an invalid value fails construction with a ConfigurationError that names CORS_ORIGINS and the rule, never the value"

requirements-completed: []

status: complete
completed: 2026-10-17
---

# Phase 2 Plan 05: App Factory and Configured-Origin CORS Summary

**`create_app()` builds an independent FastAPI app per call, `truthtrail.main` is just `app = create_app()`, CORS now allows only origins listed in `CORS_ORIGINS` (unset means none), and a catch-all inside CORS keeps 500, 404 and 422 problem+json responses readable to an allowed browser origin. The `/analyze` contract is unchanged except the declared `const: false` on `Problem.synthetic`.**

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | 9ea22ad | refactor: create_app() factory, analyze router builder, thin truthtrail.main entrypoint; Problem.synthetic is Literal[False] |
| 2 | c30f5ed | feat(cors): BootSettings, configured-origin CORS, catch-all keeps 500 responses inside CORS |

## What was built

- **Factory split (Task 1).** `api/analyze.py` owns `SearchQuery`, `FIXTURE_PATH`, `load_demo_fixture`, the imported `analyze_risk`, and `build_analyze_router()`, which defines the `analyze` handler (same decorator keywords, summary, Query description and body) on a local `APIRouter`. `api/app.py` holds `APP_DESCRIPTION` (moved verbatim), the `lifespan` (the only place strict `Settings` are read) and `create_app()`. `truthtrail/main.py` is four lines. `tests/conftest.py` points `APP_MODULE` at `truthtrail.api.analyze` and `client_factory` sets the environment, clears the settings cache and builds `create_app(**app_kwargs)` per call; it gained keyword parameters `env`, `client` and `app_kwargs`.
- **`Problem.synthetic: Literal[False]`.** The golden-document helper already stripped the `const` keyword; `test_problem_synthetic_is_const_false` asserts the live document has `const: false`, and a model test proves `synthetic=True` is rejected and the default is `False`.
- **CORS (Task 2).** `BootSettings.cors_origins` is `Annotated[list[str], NoDecode]`, split on commas, stripped and emptied of blanks, then each entry is checked against the exact `scheme://host[:port]` form. `create_app()` adds `CatchAllMiddleware` first and `CORSMiddleware` second (allow_origins from settings, methods GET/HEAD/OPTIONS, no credentials, default headers). `.env.example`, `EXPECTED_ENV_NAMES` and conftest `ENV_NAMES` gained `CORS_ORIGINS`; the Vite origin is in a comment only.

## Verification

- `pytest -q`: 331 passed, 10 xfailed, no XPASS (303 passed at the start of the plan; +6 in Task 1, +22 in Task 2).
- `tests/test_cors.py`: 22 tests collected and passing (plan required at least 12). `tests/test_openapi_golden.py`, `tests/test_settings.py::test_uvicorn_exits_on_missing_key` (exit code 3 and "Application startup failed" intact), `tests/test_request_validation.py::test_unexpected_error_is_generic_500` (no edit beyond the patch-target constant) and `tests/test_no_hardcoded_credentials.py` (13 passed) all pass.
- `ruff check`, `ruff format --check` and `mypy` (16 source files) clean. `scripts/copy_guard.py` clean (135 OpenAPI strings). The added-lines scan for 32-hex strings found nothing before either commit.
- `grep -n add_middleware src/truthtrail/api/app.py`: the `CatchAllMiddleware` line (51) precedes the `CORSMiddleware` line (52).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug in plan assertion] Preflight for a disallowed method from a listed origin does carry ACAO**
- **Found during:** Task 2, first run of `tests/test_cors.py`
- **Issue:** the plan said a preflight for POST is rejected "with status 400 and no ACAO". Starlette 1.8.0 answers it with 400 text/plain but still echoes `Access-Control-Allow-Origin` for a listed origin (the research note about "no ACAO" holds for an unlisted origin, which the new `test_preflight_for_unlisted_origin_is_rejected` covers).
- **Fix:** the test asserts status 400, a `text/plain` body, and that `Access-Control-Allow-Methods` does not contain POST (so a browser still refuses the real request). The plain-text limitation is documented in a test comment, as the plan asked.
- **Files modified:** tests/test_cors.py
- **Commit:** c30f5ed

**2. [Rule 1 - Bug] FastAPI 0.143 keeps included routers as one nested route with an empty path**
- **Found during:** Task 1, `tests/test_app_factory.py`
- **Issue:** `app.routes` no longer lists `/analyze`, so route-list independence cannot be read from it.
- **Fix:** the factory test reads the served paths from the OpenAPI document (clearing the cached schema first) and also asserts `app.router` and `app.routes` are distinct objects per call.
- **Files modified:** tests/test_app_factory.py
- **Commit:** 9ea22ad

**3. [Honesty] ENG-06 left unchecked.** The plan lists ENG-06 and the GSD tooling marked it complete, but ENG-06 also requires rate limiting, the TTL cache and bounded retries, which land in plans 02-07 to 02-09. The REQUIREMENTS.md change was reverted so the requirement is not reported done early; this plan delivers only its CORS part (ROADMAP criterion 5, CORS clause). `requirements-completed` is therefore empty.

**4. Method note.** A first draft of `analyze.py` accidentally contained the literal U+2028 and U+2029 characters inside the `SearchQuery` pattern instead of their escape sequences (backslash, u, 2028 / 2029) (ruff RUF001 and the golden test caught it). The escapes were restored byte-for-byte as in the original `main.py`; the committed pattern is identical to Phase 1. The new tests were inserted before `test_only_declared_additions_exist` rather than appended at the end of `tests/test_openapi_golden.py` (no existing assertion changed).

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model; T-02-12 to T-02-15 mitigations are implemented and tested (denied origins get no ACAO, ACAO and Vary on 500/404/422 for an allowed origin, only the exception class name logged, import-safe construction with exit code 3 preserved).

## Self-Check: PASSED

- Files src/truthtrail/api/app.py, api/analyze.py, api/catchall.py, core/boot.py, tests/test_cors.py, tests/test_app_factory.py: FOUND
- Commits 9ea22ad and c30f5ed are ancestors of HEAD: FOUND
