---
phase: 01-secure-honest-foundation
plan: 05
subsystem: api
tags: [response-envelope, provenance, demo-mode, openapi, rfc9457, fastapi, pydantic]

requires:
  - phase: 01-secure-honest-foundation
    provides: envelope models and the synthetic demo fixture (01-03), problem+json handlers, typed adapter and query validation (01-04), settings with DEMO_MODE (01-02), test harness (01-01)
provides:
  - GET /analyze returning the {results, meta} provenance envelope with event-free live results
  - honest empty 200 (results [], source_status empty) replacing the fabricated fallback article
  - DEMO_MODE-only fixture serving through main.load_demo_fixture, refused unless labelled synthetic
  - problems.PROBLEM_RESPONSES and an OpenAPI document with typed 2xx models and problem+json 422/500/502/503
  - honest OpenAPI title, description and /analyze summary ("flag for human review")
affects: [01-06, phase-02]

actuals:
  tokens: 12000
  tasks: 3
  commits: 4
plan_head_before: 134596ab18ac0b3ca2a4240fec63a6c69d6f66fb
plan_head_after: fbaab50fc6abbf5aaad1ab44551ee1d2689edc20

tech-stack:
  added: []
  patterns:
    - "Route returns AnalyzeResponse(results=[LiveResult...], meta=Meta(...)) with response_model and responses=PROBLEM_RESPONSES"
    - "Fixture loaded only from an lru_cached loader reachable through `if settings.demo_mode:`, validated and refused unless synthetic"
    - "OpenAPI error declarations pair a Problem model with explicit problem+json content; the app's openapi() drops the application/json duplicate FastAPI adds"
    - "OpenAPI walker test resolves $ref and rejects untyped 2xx schemas"

key-files:
  created:
    - tests/test_provenance_demo.py
    - tests/test_openapi_contract.py
  modified:
    - main.py
    - problems.py
  deleted:
    - tests/test_char_analyze_legacy.py

key-decisions:
  - "D-01 envelope is a deliberate breaking change; the article timestamp key is now snake_case published_at (exemption recorded below)"
  - "data_as_of for live responses is the server receive time truncated to whole seconds, UTC, Z suffix"
  - "The validated query is ignored in demo mode (the fixture never changes) but is still validated first"
  - "Declared error responses list only application/problem+json (the media type the handlers return)"

patterns-established:
  - "Every 2xx carries meta {synthetic, data_as_of, source_status}; every error carries the same trio at top level with data_as_of null"
  - "Fixture reachable from exactly one place; a recording stub in place of the loader proves it is never called with DEMO_MODE off"

requirements-completed: [FND-03, FND-04]

coverage:
  - id: D1
    description: "A live search returns exactly {results, meta}; the result has headline, source, published_at, risk, risk_method keyword_baseline and no events key; meta.synthetic false, source_status ok, data_as_of in second-precision Z format within 60 s of now; the fabricated 2025-01-01 article is gone and main.py no longer imports the simulator"
    requirement: FND-03
    verification:
      - kind: integration
        ref: "tests/test_provenance_demo.py#test_live_result_contract"
        status: pass
      - kind: integration
        ref: "tests/test_provenance_demo.py#test_live_result_has_no_events_key"
        status: pass
    human_judgment: false
  - id: D2
    description: "An empty provider answer is an honest 200 with results [], synthetic false, source_status empty and no fabricated article"
    requirement: FND-03
    verification:
      - kind: integration
        ref: "tests/test_provenance_demo.py#test_empty_result_is_honest_200"
        status: pass
    human_judgment: false
  - id: D3
    description: "With DEMO_MODE=true and no key the committed fixture is returned unchanged (synthetic true, source_status fixture, constant data_as_of, events present) with no upstream call, and the query is still validated"
    requirement: FND-03
    verification:
      - kind: integration
        ref: "tests/test_provenance_demo.py#test_demo_mode_serves_labelled_fixture"
        status: pass
      - kind: integration
        ref: "tests/test_provenance_demo.py#test_demo_mode_still_validates_query"
        status: pass
    human_judgment: false
  - id: D4
    description: "With DEMO_MODE unset or false the fixture loader is never called for any of four upstream outcomes (one article, empty, 401, timeout) and the response says synthetic false; a fixture not labelled synthetic is refused with a 500 problem+json and no results"
    requirement: FND-03
    verification:
      - kind: integration
        ref: "tests/test_provenance_demo.py#test_fixture_never_served_when_demo_mode_off (8 rows)"
        status: pass
      - kind: integration
        ref: "tests/test_provenance_demo.py#test_demo_mode_refuses_unlabelled_fixture"
        status: pass
    human_judgment: false
  - id: D5
    description: "Ten response kinds (live ok, live empty, demo, 401, 429, timeout, invalid query, unknown path, wrong method, missing configuration) all carry synthetic, source_status and data_as_of (under meta for 2xx, top level and null for errors)"
    requirement: FND-03
    verification:
      - kind: integration
        ref: "tests/test_provenance_demo.py#test_every_response_carries_provenance (10 rows)"
        status: pass
    human_judgment: false
  - id: D6
    description: "/openapi.json gives every operation a typed 2xx Pydantic schema, /analyze 200 resolves to AnalyzeResponse (DemoResult | LiveResult, LiveResult without events, Meta required fields and source_status enum), 422/500/502/503 are application/problem+json referencing Problem (503 with Retry-After), the query parameter is required with minLength 1, maxLength 200 and a pattern, and real bodies validate against the declared models"
    requirement: FND-04
    verification:
      - kind: integration
        ref: "tests/test_openapi_contract.py#test_every_operation_has_typed_2xx_response"
        status: pass
      - kind: integration
        ref: "tests/test_openapi_contract.py#test_analyze_200_is_analyze_response"
        status: pass
      - kind: integration
        ref: "tests/test_openapi_contract.py#test_error_responses_are_problem_json"
        status: pass
      - kind: integration
        ref: "tests/test_openapi_contract.py#test_query_parameter_is_constrained"
        status: pass
      - kind: integration
        ref: "tests/test_openapi_contract.py#test_actual_bodies_match_declared_models"
        status: pass
    human_judgment: false
  - id: D7
    description: "OpenAPI title is TruthTrail API; the description and the /analyze summary use flag for human review wording; the interim D-13 banned-wording walk over every OpenAPI string prints openapi copy ok"
    requirement: FND-04
    verification:
      - kind: integration
        ref: "tests/test_openapi_contract.py#test_openapi_copy_is_honest"
        status: pass
    human_judgment: false

duration: 9min
completed: 2026-10-16
status: complete
---

# Phase 1 Plan 05: Provenance Envelope and Typed OpenAPI Summary

**`GET /analyze` now answers `{results, meta:{synthetic, data_as_of, source_status}}` with event-free keyword-baseline results, an honest empty 200, a DEMO_MODE-only synthetic fixture path, and an OpenAPI document with typed success models and problem+json error models.**

## Performance

- **Duration:** about 9 min (end 2026-10-16T10:30Z)
- **Tasks:** 3
- **Files modified:** 5 (2 created, 2 modified, 1 deleted)

## Accomplishments

- Live results are `LiveResult` objects (`headline`, `source`, `published_at`, `risk`, `risk_method: keyword_baseline`) and carry no `events`; `main.py` no longer imports the simulator and the fabricated `unknown` / `2025-01-01` article is gone.
- `meta.data_as_of` is the server receive time, UTC, truncated to whole seconds with a `Z` suffix; an empty provider answer is `200` with `results: []` and `source_status: "empty"`.
- `load_demo_fixture()` (lru_cache, `Path(__file__)`-anchored `FIXTURE_PATH`) validates the committed fixture and raises unless `meta.synthetic is True` and `source_status == "fixture"`; the only call site is the `if settings.demo_mode:` branch, so with DEMO_MODE unset or false it is unreachable (proven with a recording stub across four upstream outcomes).
- `PROBLEM_RESPONSES` declares 422/500/502/503 as `application/problem+json` referencing `Problem`, with `Retry-After` on 503; the app is titled "TruthTrail API" v0.1.0 with a "flag for human review" description and summary.
- A walker test checks every operation has a typed 2xx schema and that real live, demo, 502, 422 and 404 bodies validate against the declared models.
- Full suite: 163 passed, 10 xfailed, no XPASS, no skips. Credential backstop passes (13 passed). The interim OpenAPI copy check prints `openapi copy ok`.

## Task Commits

1. **Task 1: Live result in the provenance envelope without events; legacy list tests retired (tracer)** - `ddcead7` (feat)
2. **Task 2: Honest empty results, DEMO_MODE-only fixture serving, provenance on every response** - `d45a389` (feat)
3. **Task 3: Typed OpenAPI success and problem+json error schemas, honest copy** - `2b4a1a6` (feat)
4. **Line-ending repair (deviation, below)** - `fbaab50` (chore)

**Plan metadata:** committed separately after this file (docs commit).

Tracer gate: `workflow.human_verify_mode` is `end-of-phase` and the Task 1 verify is automated-only, so it was re-run after the commit (2 passed, full suite 135 passed / 10 xfailed with no XPASS, credential backstop 13 passed) and the plan expanded: `Tracer verified end-to-end`.

## Retired legacy tests and replacement map (D-12)

`tests/test_char_analyze_legacy.py` was removed with `git rm` in `ddcead7`. The pure-function suites (`test_char_risk_analyzer.py`, `test_char_simulator.py`) and `test_network_guard.py` stay.

| Retired test | Replacement |
|---|---|
| `test_legacy_single_article_shape` | `tests/test_provenance_demo.py::test_live_result_contract` |
| `test_legacy_medium_article_has_10_events` | Retired on purpose: live results no longer carry simulated events (D-05). Guarded by `tests/test_provenance_demo.py::test_live_result_has_no_events_key` |
| `test_legacy_forwards_query_params` | `tests/test_upstream_errors.py::test_request_uses_timeout_header_and_fixed_params` |
| `test_empty_result_is_not_fabricated` (strict xfail) | `tests/test_provenance_demo.py::test_empty_result_is_honest_200` |
| `test_upstream_status_is_honest` (401, 403, 429 rows) | `tests/test_upstream_errors.py::test_upstream_failures_are_honest` |
| `test_malformed_or_failed_upstream_is_honest` (4 rows) | `tests/test_upstream_errors.py::test_upstream_failures_are_honest` |
| `test_empty_query_is_rejected` | `tests/test_request_validation.py::test_invalid_query_is_422_problem` |

Net test change: the suite went from 144 passed / 11 xfailed to 163 passed / 10 xfailed (the removed strict xfail was the empty-result row, now a passing test).

## Key-rename exemption (CLAUDE.md "do not rename keys without updating every consumer")

The article timestamp key changes from camelCase `publishedAt` to snake_case `published_at`, and the bare list becomes the `{results, meta}` envelope, as a deliberate breaking change governed by locked decision D-01. The CLAUDE.md rule is satisfied because no consumer of `/analyze` exists in this repository (no frontend source is tracked; the only consumers are this phase's tests, all updated here). The adapter's internal `publishedAt` dict key from 01-04 is unchanged.

## Files Created/Modified

- `main.py` - `FIXTURE_PATH`, `load_demo_fixture`, `APP_DESCRIPTION`, app metadata, envelope route with `response_model=AnalyzeResponse`, `responses=PROBLEM_RESPONSES` and the demo branch (CRLF kept)
- `problems.py` - `_problem_declaration`, `PROBLEM_RESPONSES`, `_problem_only_openapi`
- `tests/test_provenance_demo.py` - 24 test cases across eight test functions
- `tests/test_openapi_contract.py` - six tests
- `tests/test_char_analyze_legacy.py` - deleted

## Decisions Made

- Demo mode ignores the validated query (Assumption A5) but validation still runs first, so an empty query is a 422 in both modes.
- The 503 `Retry-After` header is declared as an integer to match what the adapter emits.
- Copy: the description is a module constant `APP_DESCRIPTION` so both required phrase occurrences sit on single lines for the acceptance grep.

## Deviations from Plan

**1. [Rule 1 - Bug] FastAPI emitted a false `application/json` entry on every declared error**
- **Found during:** Task 3
- **Issue:** A `responses` entry with `"model": Problem` makes FastAPI add an `application/json` content type next to the explicit `application/problem+json`, but every handler returns only `application/problem+json`; the declared contract would not match actual bodies.
- **Fix:** `register_problem_handlers` wraps `app.openapi` (`_problem_only_openapi`) to remove `application/json` from the 422/500/502/503 entries; `test_error_responses_are_problem_json` asserts the media type set is exactly `{application/problem+json}`. The `Problem` schema is still registered through the model.
- **Files modified:** `problems.py`
- **Commit:** `2b4a1a6`

**2. [Rule 1 - Bug] main.py was converted from CRLF to LF by the Task 1 rewrite**
- **Found during:** SUMMARY preparation (diff showed whole-file churn)
- **Issue:** `main.py` is a CRLF file (kept CRLF in 01-04); a text-mode rewrite normalised it to LF in `ddcead7`/`d45a389`/`2b4a1a6`.
- **Fix:** restored CRLF in `fbaab50`. The net diff of `main.py` against the pre-plan commit is now only the real changes (66 insertions, 27 deletions). Intermediate commits still show the churn.
- **Commit:** `fbaab50`

**3. Process note (not a code deviation):** Tasks 2 and 3 are `tdd="true"`. Task 2 was run red-first (11 failing tests observed before the implementation) but committed as a single feat commit with its tests; Task 3 wrote declarations first and tests after, so there is no separate RED commit (`workflow.tdd_mode` is not enabled, as in earlier plans). The plan-head ledger file was created after the first commit (from the recorded pre-plan HEAD `134596a`), not before it.

**Total deviations:** 2 auto-fixed (Rule 1), 1 process note.

## Issues Encountered

- A first draft of `test_actual_bodies_match_declared_models` called the demo client before the 401 case; `client_factory` sets `DEMO_MODE` through `monkeypatch.setenv`, which persists for the rest of the test and made the later call a demo 200. The demo case now runs last.
- The interim OpenAPI copy guard reported no hit on the 01-03 docstrings and descriptions that are now OpenAPI copy, so no model text was reworded.

## Known Stubs

None. The demo fixture is intentional synthetic data, served only under `DEMO_MODE=true` and labelled `synthetic: true`.

## Threat Flags

None. No new endpoint or trust boundary; the only new file read is the committed fixture, gated and validated (T-01-24, T-01-27 mitigated by tests above).

## Constraints verified

- `spread_simulator.py`, `users.py`, `risk_analyzer.py` are byte-identical to `9b5b085` (empty `git diff 9b5b085 --stat`); `models.py` is untouched, so the `Event` JSON schema is unchanged.
- No network access outside the `responses` mock; no key material written; the 32-hex scan over added lines was empty for each commit.

## Self-Check: PASSED

All created files exist, all four commits are ancestors of HEAD, the legacy test file is gone, and the full suite is green (163 passed, 10 xfailed).
