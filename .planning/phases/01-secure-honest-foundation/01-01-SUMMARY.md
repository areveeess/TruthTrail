---
phase: 01-secure-honest-foundation
plan: 01
subsystem: testing
tags: [pytest, responses, httpx, fastapi, characterization-tests, network-guard]

requires:
  - phase: none
    provides: first plan of the project
provides:
  - Autouse network guard that makes a live GNews call from any test impossible
  - Pinned test stack (pytest 9.1.1, responses 0.26.3, httpx 0.28.1) in requirements-dev.txt
  - Characterization suite pinning analyze_risk, the spread simulator and the legacy /analyze handler
  - Exact runtime pins in requirements.txt, proven behaviour-identical to the unpinned prototype runtime
affects: [01-02, 01-03, 01-04, 01-05, 01-06, phase-02]

actuals:
  tokens: 4174
  tasks: 3
  commits: 4
plan_head_before: 028a5a8a1db31acf2b839ab923f4521f1f2f4072
plan_head_after: c41c09439eeb724cfa731d41faf5dae322a3575c

tech-stack:
  added: [pytest==9.1.1, responses==0.26.3, httpx==0.28.1, pydantic==2.14.0, pydantic-settings==2.15.0]
  patterns:
    - "Autouse responses.RequestsMock fixture blocks every unregistered outbound request"
    - "Defects are strict xfails (xfail_strict=true, raises=AssertionError) that assert the DESIRED behaviour"
    - "App and fetcher imported lazily inside client_factory so one file owns app construction"

key-files:
  created:
    - requirements-dev.txt
    - pytest.ini
    - tests/conftest.py
    - tests/test_network_guard.py
    - tests/test_char_risk_analyzer.py
    - tests/test_char_simulator.py
    - tests/test_char_analyze_legacy.py
  modified:
    - requirements.txt

key-decisions:
  - "Test client backend is httpx 0.28.1 (D-18); filterwarnings=error with one message-regex ignore for Starlette's httpx deprecation"
  - "Runtime pins are the plan's last commit, after 48 per-test outcomes matched under the unpinned and pinned runtimes"
  - "client_factory monkeypatches the fetcher's module key constant to FAKE_TEST_KEY so no test request carries the rotated key"

patterns-established:
  - "Test hygiene: booleans or single values are computed before asserting, so no URL, params dict or header dict reaches an assert message"
  - "Defect rows removed from xfail in the same commit that fixes the defect (strict XPASS is a red build by design)"

requirements-completed: [FND-05]

coverage:
  - id: D1
    description: "Autouse network guard blocks unmocked requests, scrubs the five env names, and only the fake key travels on test requests"
    requirement: FND-05
    verification:
      - kind: unit
        ref: "tests/test_network_guard.py#test_unmocked_request_is_blocked"
        status: pass
      - kind: unit
        ref: "tests/test_network_guard.py#test_env_is_scrubbed"
        status: pass
      - kind: integration
        ref: "tests/test_network_guard.py#test_mocked_gnews_reaches_real_handler"
        status: pass
    human_judgment: false
  - id: D2
    description: "analyze_risk golden table plus 8 strict-xfail keyword defects"
    requirement: FND-05
    verification:
      - kind: unit
        ref: "tests/test_char_risk_analyzer.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "Simulator invariants pinned; child-before-parent and mixed timestamp formats as strict xfails"
    requirement: FND-05
    verification:
      - kind: unit
        ref: "tests/test_char_simulator.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "Legacy /analyze list shape pinned through the real handler; fabricated 200, unhandled upstream failures and missing validation as strict xfails"
    requirement: FND-05
    verification:
      - kind: integration
        ref: "tests/test_char_analyze_legacy.py"
        status: pass
    human_judgment: false
  - id: D5
    description: "Runtime dependencies pinned exactly, with identical per-test outcomes under the unpinned and pinned runtimes"
    requirement: FND-05
    verification:
      - kind: other
        ref: "diff of per-test outcome files (unpinned vs pinned), 48 outcomes, identical"
        status: pass
    human_judgment: false

duration: 4min
completed: 2026-10-16
status: complete
---

# Phase 1 Plan 01: Test Safety Net Summary

**Autouse `responses` network guard plus a 48-outcome characterization suite (29 passed, 19 strict xfails) pinning the prototype's `/analyze`, `analyze_risk` and simulator before any behavioural change, then exact runtime pins verified outcome-identical.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-10-16T10:01:30Z (approximate; start time was not captured at launch)
- **Completed:** 2026-10-16T10:05:30Z
- **Tasks:** 3
- **Files modified:** 8 (7 created, 1 modified)

## Accomplishments

- Any unmocked `requests` call inside a test raises `ConnectionError`, so the rotated GNews key still embedded in `gnews_fetcher.py` can never be sent to the provider from the suite. The five secret-bearing env names are scrubbed for every test.
- `analyze_risk` is pinned by 13 golden rows. Eight known keyword defects (secure/cure, studies/dies, couple/coup, deadline/dead, "Dead heat", two hardcoded celebrity names, negated "market crash") are strict xfails asserting the desired behaviour.
- The simulator is pinned (19 events for High, 10 otherwise, per-platform chain linkage, user pools, 5-60 minute offsets, seed-determinism of non-id fields, `Event` validation). Child-before-parent and mixed timestamp formats are strict xfails.
- Legacy `/analyze` is pinned through the real handler with mocked GNews: three stable tests; nine strict xfails cover the fabricated fallback article, the fabricated 200 on 401/403/429, the plain 500 on four malformed or failed upstream scenarios, and the missing empty-query validation.
- No production module changed: `main.py`, `gnews_fetcher.py`, `risk_analyzer.py`, `spread_simulator.py`, `users.py` and `models.py` are byte-identical to `9b5b085`.

## Task Commits

1. **Task 1: Test harness end to end (tracer)** - `e2b3fc5` (test) - requirements-dev.txt, pytest.ini, tests/conftest.py, tests/test_network_guard.py
2. **Task 2: Pin pure functions** - `7d9e4ac` (test) - tests/test_char_risk_analyzer.py, tests/test_char_simulator.py
3. **Task 3a: Pin legacy /analyze** - `f7a5040` (test) - tests/test_char_analyze_legacy.py
4. **Task 3b: Runtime pins (last commit)** - `c41c094` (chore) - requirements.txt

**Plan metadata:** committed separately after this file (docs commit).

Tracer gate: the Task 1 verify was re-run after the commit (3 passed, env scrub passed, production diff clean) and the plan expanded with `Tracer verified end-to-end`.

## Files Created/Modified

- `requirements-dev.txt` - `-r requirements.txt` plus pytest, responses and httpx pins
- `pytest.ini` - `pythonpath = .`, `testpaths = tests`, `xfail_strict = true`, `-ra`, `filterwarnings = error` plus the D-18 httpx/Starlette ignore
- `tests/conftest.py` - `network_guard` (autouse), `mock_gnews`, `client_factory`, `client`, `fake_key`, `gnews_url`, `gnews_article`, `gnews_payload`, `seeded_random`
- `tests/test_network_guard.py` - guard self-tests and one mocked call through the real handler
- `tests/test_char_risk_analyzer.py` - golden table, 8 strict xfails, None raises
- `tests/test_char_simulator.py` - 7 stable invariants, 2 strict xfails
- `tests/test_char_analyze_legacy.py` - 3 stable tests, 9 strict xfails (deleted in plan 01-05)
- `requirements.txt` - five exact pins (modified, last commit)

## Decisions Made

- httpx 0.28.1 is the test-client backend per D-18; no dependency human-verify checkpoint was raised.
- The Starlette deprecation ignore is a message regex with no category, so `error` stays in force for every other warning. No other third-party warning appeared.
- `from conftest import ENV_NAMES` in `test_network_guard.py` resolves via pytest's rootdir-based `sys.path` insertion for the `tests/` directory (no `__init__.py`); it works today and keeps the five env names in one place.

## Runtime pin comparison

Resolved on Python 3.13.16 in `.venv`.

| Package | Unpinned prototype runtime (characterized baseline) | Pinned set (final) |
|---|---|---|
| fastapi | 0.143.2 | 0.143.0 |
| starlette | 1.8.0 | 1.8.0 |
| pydantic | 2.14.1 | 2.14.0 |
| pydantic-settings | not installed | 2.15.0 |
| uvicorn | 0.54.0 | 0.54.0 |
| requests | 2.34.2 | 2.34.2 |

Test tools resolved to exactly their pins in both runs: pytest 9.1.1, responses 0.26.3, httpx 0.28.1.

The per-test outcomes of the full suite were captured with `pytest -q -rA` under the unpinned runtime and again under the pinned set (the trailing ` - reason` text of XFAIL lines was stripped so ids and outcomes are compared). 48 outcomes were compared (29 PASSED, 19 XFAIL); the two files were identical (`diff` exit 0). Only then was `requirements.txt` committed.

## Deviations from Plan

None - plan executed exactly as written. Notes that are not deviations:

- The unpinned install resolved fastapi 0.143.2 and pydantic 2.14.1, a patch ahead of the pins (0.143.0 and 2.14.0); the comparison above shows no behavioural difference for the characterized surface.
- `grep -c "strict=True" tests/test_char_risk_analyzer.py` prints 1 because the 8 defect rows share one marker built in a helper; the plan's acceptance criterion allows this form and `-rx` lists exactly 8 xfailed risk rows.
- The plan's capture command was run with an extra `sed` to strip XFAIL reasons from each line; ids and outcomes are unchanged, so the comparison is no weaker.

**Total deviations:** 0.

## Issues Encountered

None. Untracked `__pycache__/` and `tests/__pycache__/` directories exist in the working tree and were deliberately not staged; plan 01-02 adds the `.gitignore` that covers them. `.venv/` is untracked (its own ignore file keeps it out of `git status`).

## Known Stubs

None.

## Threat Flags

None. No new network endpoint, auth path or schema was introduced; the plan only adds tests and pins.

## Authentication Gates

None.

## Next Phase Readiness

- Wave 2 (plan 01-02) can build on `mock_gnews` and `client_factory`. It must delete the `monkeypatch.setattr(gnews_fetcher, "GNEWS_API_KEY", FAKE_KEY)` line in `client_factory` together with the module constant, and its `X-Api-Key` header move is already tolerated by `test_mocked_gnews_reaches_real_handler`.
- Every strict xfail will turn into a red XPASS the moment its defect is fixed; the fixing commit must remove the marker (and plan 01-05 replaces `test_char_analyze_legacy.py` wholesale).
- Secret-hygiene reminder: the rotated key literal still lives in `gnews_fetcher.py` and git history until 01-02 removes it from the working tree.

## Self-Check: PASSED

- Created files exist: requirements-dev.txt, pytest.ini, tests/conftest.py, tests/test_network_guard.py, tests/test_char_risk_analyzer.py, tests/test_char_simulator.py, tests/test_char_analyze_legacy.py (all present).
- Commits exist and are ancestors of HEAD: e2b3fc5, 7d9e4ac, f7a5040, c41c094.
- Plan verification: full suite `29 passed, 19 xfailed`, no XPASS; `git diff --quiet 9b5b085` over the six production modules exits 0; unpinned-vs-pinned outcome diff is empty; `requirements.txt` has exactly 5 pin lines; `requirements.txt` was last touched by `c41c094`, newer than every other task commit; `tests/conftest.py` and `pytest.ini` were added in `e2b3fc5`, the plan's first commit.
