---
phase: 02-engineering-baseline
plan: 02
subsystem: packaging
tags: [src-layout, git-mv, legacy-isolation, ast-boundary-test, root-shim, core-errors]

requires:
  - phase: 02-engineering-baseline
    provides: plan 02-01 line-ending commit, OpenAPI golden snapshot, sha256 content pins, conftest APP_MODULE and subprocess_env
provides:
  - src/truthtrail package (api, core, schemas, services, data) with history-preserving renames
  - legacy/ directory holding spread_simulator.py and users.py, unreachable from the live path
  - core/errors.py (UpstreamError, problem_body, problem_response, PROBLEM_MEDIA_TYPE) so services never import from api/
  - root main.py compatibility shim for `uvicorn main:app`
  - tests/test_no_legacy_imports.py and tests/test_main_shim.py (machine-checked ROADMAP criterion 1)
affects: [02-03, 02-04, 02-05, 02-06, 02-07]

actuals:
  tokens: 14000
  tasks: 3
  commits: 3
plan_head_before: 531da4fd9255ce754ea8313476a6e0a86743c92d
plan_head_after: a067b33f6ae43098fbe1522c56851a4d7b747428

tech-stack:
  added: []
  patterns:
    - "Rename-only commit first, retarget second (git log --follow survives)"
    - "Legacy code kept on pytest pythonpath only; the package is proved not to import it by AST walk plus fresh-interpreter checks"

key-files:
  created:
    - main.py
    - src/truthtrail/__init__.py
    - src/truthtrail/api/__init__.py
    - src/truthtrail/core/__init__.py
    - src/truthtrail/core/errors.py
    - src/truthtrail/schemas/__init__.py
    - src/truthtrail/services/__init__.py
    - tests/test_no_legacy_imports.py
    - tests/test_main_shim.py
  modified:
    - src/truthtrail/main.py
    - src/truthtrail/api/problems.py
    - src/truthtrail/services/gnews.py
    - pytest.ini
    - scripts/copy_guard.py
    - scripts/generate_demo_fixture.py
    - tests/conftest.py
    - tests/test_char_risk_analyzer.py
    - tests/test_char_simulator.py
    - tests/test_demo_fixture.py
    - tests/test_legacy_frozen.py
    - tests/test_no_hardcoded_credentials.py
    - tests/test_openapi_contract.py
    - tests/test_provenance_demo.py
    - tests/test_response_models.py
    - tests/test_settings.py
    - tests/test_upstream_errors.py

key-decisions:
  - "Followed the plan as written; no new decisions beyond D-01, D-02, D-04, D-05, D-21, D-22, D-25"

requirements-completed: [ENG-01]

status: complete
completed: 2026-10-17
---

# Phase 2 Plan 02: Package Move and Legacy Isolation Summary

**The Phase 1 code now lives in `src/truthtrail` (api, core, schemas, services, data), the simulator and user pools sit in `legacy/`, the move kept full history, and two new tests prove the live package can neither import nor even find the legacy modules.**

## Commits

| Task | Commit | Notes |
|------|--------|-------|
| 1. Pure renames | `1473d89` | Nine R100 renames, nothing else. Deliberately red (imports unresolved). **Never pushed alone**: the orchestrator pushes only at the plan boundary, after `a067b33`. At verification time no remote-tracking branch contained it. |
| 2. Retarget, errors split, shim | `05428ba` | Green: 281 passed, 10 xfailed |
| 3. Boundary tests | `a067b33` | Green: 286 passed, 10 xfailed |

## What was built

- The nine moves (main, config, problems, models, gnews_fetcher, risk_analyzer, spread_simulator, users, demo fixture) are all `R100` in one commit. `git log --follow` reaches 9 commits for `services/gnews.py` and 3 for `legacy/users.py`.
- `core/errors.py` holds `PROBLEM_MEDIA_TYPE`, `UpstreamError`, `problem_body` and `problem_response` with identical code and text. `api/problems.py` and `services/gnews.py` import them from there.
- Root `main.py` re-exports `truthtrail.main.app`. `test_uvicorn_exits_on_missing_key` still sees exit code 3 and "Application startup failed" through the shim.
- `pytest.ini` pythonpath is `src legacy .` (plan 02-03 replaces the file once the package is installed).
- `scripts/copy_guard.py` puts the repo root and `src` on `sys.path` and imports `truthtrail.main` lazily. `scripts/generate_demo_fixture.py` puts `legacy` and `src` on `sys.path`, targets the new fixture path and writes with `newline="\n"`.
- `tests/test_no_legacy_imports.py` (4 tests): AST walk over 8 or more package files, negative control on the walker, fresh interpreter importing `truthtrail.main` leaves no forbidden name in `sys.modules`, and `find_spec` finds none of the forbidden names with `PYTHONPATH` set to `src` only. `tests/test_main_shim.py` (1 test): `main.app is truthtrail.main.app` and `__all__ == ["app"]`.

## Task 2 test edits (git diff --stat, 1473d89..05428ba, tests/)

```
 tests/conftest.py                      | 6 +++---
 tests/test_char_risk_analyzer.py       | 2 +-
 tests/test_char_simulator.py           | 2 +-
 tests/test_demo_fixture.py             | 6 +++---
 tests/test_legacy_frozen.py            | 8 ++++----
 tests/test_no_hardcoded_credentials.py | 4 ++--
 tests/test_openapi_contract.py         | 2 +-
 tests/test_provenance_demo.py          | 2 +-
 tests/test_response_models.py          | 2 +-
 tests/test_settings.py                 | 6 +++---
 tests/test_upstream_errors.py          | 6 +++---
 11 files changed, 23 insertions(+), 23 deletions(-)
```

No assertion line changed: the staged-diff check (`^[-+]\s*assert` count) returned 0 before the commit. The edits are import lines, the `APP_MODULE` constant and the `import truthtrail.main as main` line in `client_factory`, path constants, the frozen-test keys (same hashes), the logger-name string, the `PYTHONPATH` value in the uvicorn test and two parametrisation paths.

## Verification

| Check | Result |
|-------|--------|
| Full suite after Task 2 | 281 passed, 10 xfailed, no XPASS (same passed count as end of 02-01) |
| Full suite after Task 3 | 286 passed, 10 xfailed, no XPASS (+5 new tests) |
| `tests/test_openapi_golden.py`, `tests/test_legacy_frozen.py` | pass unchanged in substance (OpenAPI document still the frozen Phase 1 document; legacy files, baseline and fixture keep their pinned hashes) |
| `scripts/generate_demo_fixture.py --check` | "demo fixture is up to date" |
| `scripts/copy_guard.py` | clean (1 file, 135 OpenAPI strings) |
| Credential backstop and 32-hex added-lines scan | clean before every commit (the rename commit adds no lines) |
| Task 2 staged set | did not touch `legacy/`, `keyword_baseline.py` or `src/truthtrail/data/` |

No Docker daemon and no GitHub Actions run were involved; neither is claimed.

## Deviations from Plan

**1. [Note - Rule 1, stale reference] Docstring in `services/gnews.py`**
- The module docstring said "see ``problems.py``"; it now says ``core/errors.py``, because that is where `UpstreamError` lives after the move. Docstring text only, no behaviour change.

**2. [Note] Import ordering in `src/truthtrail/main.py`**
- The five rewritten import lines are alphabetised by module path; the plan listed them in a different order. Same names, no behaviour change.

**3. [Note] `api/problems.py` docstring and imports trimmed**
- After the errors split the module docstring was shortened to describe handlers and OpenAPI declarations only (the body-shape explanation moved to `core/errors.py` as the plan prescribes), and the now unused `HTTPStatus` and `Optional` imports were dropped.

**4. [Note] Empty `fixtures/` directory removed** from the working tree after the fixture rename (git does not track empty directories).

No plan stop condition was reached. No architectural change.

## Known Stubs

None.

## Threat Flags

None. No endpoint, auth path, schema or trust boundary was added; the legacy simulator was moved further from the live path, and T-02-04, T-02-05 and T-02-06 mitigations are in place as planned.

## Self-Check: PASSED

Created files exist (`main.py`, `src/truthtrail/core/errors.py`, the five `__init__.py` files, `tests/test_no_legacy_imports.py`, `tests/test_main_shim.py`); commits `1473d89`, `05428ba`, `a067b33` are ancestors of HEAD.
