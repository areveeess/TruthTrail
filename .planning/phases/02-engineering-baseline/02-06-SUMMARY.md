---
phase: 02-engineering-baseline
plan: 06
subsystem: api
tags: [fastapi, readiness, liveness, problem-json, health-check]

requires:
  - phase: 02-engineering-baseline
    provides: plan 02-05 create_app() factory, problem+json builders, golden OpenAPI test allowing /health and /ready
provides:
  - "ReadinessRegistry (truthtrail.core.readiness): register(name, check) and run() with fail-closed semantics"
  - "GET /health (liveness) and GET /ready (readiness) at the root, unauthenticated, via build_health_router()"
  - "Health and Ready response models; READINESS_503 OpenAPI declaration without Retry-After"
  - "register_default_checks(registry) extension hook in truthtrail.api.app for Phase 3 (database) and Phase 4 (model)"
affects: [02-07, 02-11, 03, 04]

actuals:
  tokens: 14000
  tasks: 2
  commits: 2
plan_head_before: 19809f5c244f2a13cffd7e0f1b4ecdaac424f5e6
plan_head_after: 4e283775e872d153138ae8107ee1437fc8404c1d

tech-stack:
  added: []
  patterns:
    - "Readiness registry lives on app.state.readiness, built inside create_app(), never at module level"
    - "Fail closed: a check counts as passing only when it returns exactly True; exceptions are logged by class name only"
    - "/health is async def (no threadpool dependency); /ready is sync def so blocking checks run in the threadpool"

key-files:
  created:
    - src/truthtrail/core/readiness.py
    - src/truthtrail/api/health.py
    - tests/test_readiness_registry.py
    - tests/test_health_ready.py
  modified:
    - src/truthtrail/schemas/models.py
    - src/truthtrail/api/problems.py
    - src/truthtrail/api/app.py

key-decisions:
  - "Failed check names go in the problem detail (sorted, comma separated), not in a new Problem member, so no existing schema changes (D-20)"
  - "The /ready 503 sends and declares no Retry-After header; READINESS_503 is a separate declaration from the provider-case 503"

requirements-completed: []

status: complete
completed: 2026-10-17
---

# Phase 2 Plan 06: Liveness and Readiness Summary

**`/health` answers 200 whenever the process serves, and `/ready` runs a fail-closed registry of named dependency checks: 200 with all checks listed when they pass, otherwise a 503 problem+json (code `not_ready`) that names only the failed checks. Phases 3 and 4 add their checks through `register_default_checks` without touching this plan's code.**

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | 70d1ae7 | feat(ready): ReadinessRegistry with fail-closed named checks |
| 2 | 4e28377 | feat(ready): /health and /ready with injected-failure 503 path; registry on app.state |

## What was built

- **Registry (Task 1).** `core/readiness.py` imports only the standard library. `register()` rejects blank (whitespace-only) and duplicate names with `ValueError` and keeps the first check. `run()` returns `{name: bool}` in registration order; a check passes only when it returns exactly `True`; an `Exception` counts as failed and is logged as `name=... error=<ClassName>` (no message, no traceback); `KeyboardInterrupt` and `SystemExit` propagate. 19 test cases in `tests/test_readiness_registry.py` (plan required at least 7), including a marker-string test asserting the exception text is absent from `caplog.text`.
- **Endpoints (Task 2).** `api/health.py` provides `build_health_router()`. `/ready` returns `Ready(status="ready", checks={name: "ok"})` or `problem_response(503, problem_body(503, "Not ready: a, b.", "not_ready", source_status="not_ready"))`. No `Retry-After`, no `meta`, no exception text. `Health` and `Ready` are `extra="forbid"` models with descriptions. `create_app()` builds `ReadinessRegistry()`, stores it on `app.state.readiness`, calls `register_default_checks(registry)` (empty hook with a docstring naming the Phase 3 `database` and Phase 4 `model` checks) and includes the health router.
- **OpenAPI.** Only `/health` and `/ready` are new paths; `/ready` declares 200 (`Ready`) and a 503 whose content is exactly `application/problem+json` with no header entry (the existing `_problem_only_openapi` already strips the duplicate JSON entry). `/analyze` gained no response code.
- **Tests.** 13 cases in `tests/test_health_ready.py` (plan required at least 11): liveness with a failing check and no news key; empty registry 200; passing check; injected failing `database` check giving the full 503 problem shape (ROADMAP criterion 4, test half); sorted two-name detail excluding passing checks; raising check with a secret-looking message absent from body and logs while `RuntimeError` is logged; `None` result is 503; recovery (503 then 200); no query or auth needed; registry is per app; OpenAPI declarations and typed schemas.

## Verification

- `pytest -q`: 363 passed, 10 xfailed, no XPASS (331 passed at the start of the plan; +19 in Task 1, +13 in Task 2).
- `tests/test_openapi_golden.py` and `tests/test_openapi_contract.py`: 11 passed (typed-2xx walker covers the new operations). `scripts/copy_guard.py`: clean (158 OpenAPI strings).
- `ruff check`, `ruff format --check` and `mypy` (18 source files) clean. `tests/test_no_hardcoded_credentials.py`: 13 passed before each commit; the added-lines scan for 32-hex strings found nothing.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Lint] Dict comprehension flagged by ruff C420**
- **Found during:** Task 2 verification
- **Issue:** `{name: "ok" for name in results}` is reported as unnecessary (C420).
- **Fix:** `dict.fromkeys(results, "ok")`; mypy strict still passes and the response is unchanged.
- **Files modified:** src/truthtrail/api/health.py
- **Commit:** 4e28377

**2. [Honesty] ENG-05 left Pending.** ENG-05 also requires that a Dockerfile builds and runs the service; that lands in plan 02-11 and the database and model checks in Phases 3 and 4. This plan delivers only the liveness and readiness half, so REQUIREMENTS.md is not changed and `requirements-completed` is empty.

Otherwise the plan was executed as written.

## Human-verify items carried forward

- No Docker daemon exists in this container; the container `HEALTHCHECK` on `/health` (plan 02-11) is not exercised here and no docker build or CI run is claimed.

## Known Stubs

None. `register_default_checks` is an intentionally empty extension hook (documented in its docstring); Phase 3 and Phase 4 populate it.

## Threat Flags

None beyond the plan's threat model; T-02-16 (only names in detail, exception text never read, proven by body and caplog absence tests) and T-02-18 (fail closed, duplicate names rejected) are implemented and tested. T-02-17 is accepted as planned (constant-size bodies; rate-limit exemption arrives in plan 02-07).

## Self-Check: PASSED

- Files src/truthtrail/core/readiness.py, src/truthtrail/api/health.py, tests/test_readiness_registry.py, tests/test_health_ready.py: FOUND
- Commits 70d1ae7 and 4e28377 are ancestors of HEAD: FOUND
