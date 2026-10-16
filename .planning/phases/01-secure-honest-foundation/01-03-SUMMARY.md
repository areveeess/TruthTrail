---
phase: 01-secure-honest-foundation
plan: 03
subsystem: api
tags: [pydantic, response-envelope, rfc9457, fixture, deterministic, synthetic-data]

requires:
  - phase: 01-secure-honest-foundation
    provides: network guard and seeded_random fixtures (01-01), .gitignore and credential backstop test (01-02)
provides:
  - models.py response contract (AnalyzeResponse, LiveResult, DemoResult, Meta, RiskLabel, FieldIssue, Problem) with Event unchanged
  - scripts/generate_demo_fixture.py, a deterministic generator with --check and --path
  - fixtures/demo_analyze.json, a committed synthetic fixture (High 19 events, Medium 10, Low 10)
affects: [01-04, 01-05, 01-06, phase-02]

actuals:
  tokens: 9341
  tasks: 3
  commits: 3
plan_head_before: 13e7986b299170c55e71ea1161c8c95e45d08eff
plan_head_after: 3a2a8c75b6f3214ef41dbbd3b8c4f816763ff400

tech-stack:
  added: []
  patterns:
    - "extra=forbid models make the DemoResult | LiveResult union unambiguous; a live result has no events field at all"
    - "Generator patches uuid4 inside a context manager and restores global random state in finally"
    - "--check regenerates and compares byte for byte, so a hand edit (even flipping synthetic) fails"

key-files:
  created:
    - scripts/generate_demo_fixture.py
    - fixtures/demo_analyze.json
    - tests/test_demo_fixture.py
    - tests/test_response_models.py
  modified:
    - models.py

key-decisions:
  - "models.py keeps its CRLF line endings; appended models use CRLF too, so the only change to the Event class is the missing final newline"
  - "Fixture timestamps are re-based by _monotone_utc (child = parent's new time + original offset from root), the simulator stays untouched"
  - "Problem.source_status is a plain required str (not the Meta Literal) because error states such as upstream_error are not Meta states"

patterns-established:
  - "Provenance trio (synthetic, source_status, data_as_of) on both Meta and Problem so errors cannot be mistaken for data"
  - "Committed-fixture tests run without the simulator; only generator tests use importorskip so Phase 2 can delete the simulator"

requirements-completed: [FND-03]

coverage:
  - id: D1
    description: "Response envelope and RFC 9457 Problem models with extra=forbid; Event reused unchanged; live results cannot carry events"
    requirement: FND-03
    verification:
      - kind: unit
        ref: "tests/test_response_models.py (9 tests: test_event_model_unchanged, test_live_result_rejects_events, test_demo_result_requires_events, test_problem_model_shape and others)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Committed fixture covers High, Medium and Low from the unmodified simulator, validates as AnalyzeResponse, and is visibly labelled synthetic with a constant data_as_of"
    requirement: FND-03
    verification:
      - kind: unit
        ref: "tests/test_demo_fixture.py#test_fixture_validates_and_is_labelled_synthetic"
        status: pass
      - kind: unit
        ref: "tests/test_demo_fixture.py#test_fixture_is_visibly_synthetic"
        status: pass
      - kind: unit
        ref: "tests/test_demo_fixture.py#test_fixture_covers_each_risk_label"
        status: pass
    human_judgment: false
  - id: D3
    description: "Fixture timelines are honest: no child before its parent and every timestamp UTC with a Z suffix, even though the simulator still has the defect"
    requirement: FND-03
    verification:
      - kind: unit
        ref: "tests/test_demo_fixture.py#test_fixture_child_never_before_parent"
        status: pass
      - kind: unit
        ref: "tests/test_demo_fixture.py#test_fixture_timestamps_are_utc_z"
        status: pass
    human_judgment: false
  - id: D4
    description: "Regeneration reproduces the fixture byte for byte, restores random and uuid4 state, and --check fails on a hand edit or a missing file"
    requirement: FND-03
    verification:
      - kind: other
        ref: ".venv/bin/python scripts/generate_demo_fixture.py --check exits 0"
        status: pass
      - kind: unit
        ref: "tests/test_demo_fixture.py#test_build_is_deterministic"
        status: pass
      - kind: unit
        ref: "tests/test_demo_fixture.py#test_check_detects_hand_edit"
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-10-16
status: complete
---

# Phase 1 Plan 03: Response Contract and Synthetic Demo Fixture Summary

**Pydantic response envelope (results plus provenance meta, extra=forbid, live results with no events key) and RFC 9457 Problem model, plus a seeded, byte-for-byte reproducible synthetic demo fixture generated from the untouched simulator with monotone UTC timelines.**

## Performance

- **Duration:** about 6 min (start time was not captured at launch; approximate)
- **Started:** 2026-10-16T10:13:00Z (approximate)
- **Completed:** 2026-10-16T10:16:00Z
- **Tasks:** 3
- **Files modified:** 5 (4 created, 1 modified)

## Accomplishments

- `models.py` now defines the envelope every later endpoint copies: `AnalyzeResponse{results: list[DemoResult | LiveResult], meta: Meta}`, `FieldIssue` and `Problem`. All use `extra="forbid"`; `risk` is a closed `High/Medium/Low` set and `risk_method` is the single literal `keyword_baseline`. Field descriptions use "flag for human review" wording and document the `data_as_of` semantics (live: provider response received by this server, with the free-plan lag noted; demo: constant fixture instant).
- A live result cannot carry `events`: `LiveResult` rejects the key and serialises without it, while `DemoResult` requires it, so "no spread data" is never an empty list.
- `scripts/generate_demo_fixture.py` seeds the global `random` state, patches `spread_simulator.uuid.uuid4` with a seeded generator inside a context manager, calls the real `analyze_risk`, `create_root_event` and `simulate_spread`, re-bases timestamps so each child is later than its parent, validates through `AnalyzeResponse.model_validate`, and restores state in `finally`.
- `fixtures/demo_analyze.json` holds three fictional "Example Town" results (High 19 events, Medium 10, Low 10), every headline and source ending in "(synthetic demo)", meta `{synthetic: true, data_as_of: "2026-10-11T12:00:00Z", source_status: "fixture"}`. It sits under `fixtures/`, which `.gitignore` keeps visible.
- `spread_simulator.py`, `users.py` and `risk_analyzer.py` are byte-identical to `9b5b085`.
- Full suite: 82 passed, 19 xfailed, no XPASS.

## Task Commits

1. **Task 1: Envelope models and a one-article fixture (tracer)** - `5542829` (feat) - models.py, scripts/generate_demo_fixture.py, fixtures/demo_analyze.json, tests/test_demo_fixture.py
2. **Task 2: Three-label fixture with honest timelines and model contract tests** - `c381235` (test) - generator, fixture, both test modules
3. **Task 3: Byte-for-byte reproducibility and drift detection** - `3a2a8c7` (test) - tests/test_demo_fixture.py

**Plan metadata:** committed separately after this file (docs commit).

Tracer gate: after the Task 1 commit the verify was re-run (fixture test passed, simulator diff clean, credential backstop 13 passed) and the plan expanded with `Tracer verified end-to-end`.

## Files Created/Modified

- `models.py` - `Event` unchanged; adds `RiskLabel`, `ResultBase`, `LiveResult`, `DemoResult`, `Meta`, `AnalyzeResponse`, `FieldIssue`, `Problem` (CRLF kept)
- `scripts/generate_demo_fixture.py` - `SEED`, `FIXTURE_PATH`, `FIXTURE_DATA_AS_OF`, `DEMO_ARTICLES`, `_seeded_uuid4`, `_monotone_utc`, `build_fixture`, `render`, `main`
- `fixtures/demo_analyze.json` - committed synthetic payload (3 results, 39 events)
- `tests/test_demo_fixture.py` - 15 tests (9 committed-file tests that need no simulator, 6 generator tests behind `importorskip`)
- `tests/test_response_models.py` - 9 model contract tests

## Decisions Made

- `models.py` is CRLF in the repository; the appended models use CRLF as well so the file stays consistent. The only change to the `Event` class is the final newline the plan said to add.
- `Problem.source_status` is a plain required string because error states (for example `upstream_error`) are outside the `Meta` literal set; `data_as_of` is typed `None` so an error can never carry a timestamp.
- Task 1 generated the fixture from the first article only (as the plan specified); the other two articles were added in Task 2 and the fixture regenerated.

## Deviations from Plan

None - plan executed exactly as written. Notes that are not deviations:

- Tasks 2 and 3 are marked `tdd="true"`, but `models.py` and the generator already existed from Task 1 and `workflow.tdd_mode` is not enabled, so the new tests passed on first run and no separate RED commit was possible (the same situation as 01-02 Task 2). As a sensitivity check, deleting the `random.setstate` restore in a scratch edit made `test_build_restores_global_random_state` fail; the edit was reverted from a saved copy before committing.
- The model contract tests (Task 2) were committed with the fixture-invariant tests in a single `test(...)` commit, per the plan's single-task structure.
- The generator's `_monotone_utc` adds the child's original offset from the root directly (offsets are 5 to 60 minutes, so they are always positive and children are strictly later than parents).

**Total deviations:** 0.

## Issues Encountered

None. Untracked caches (`__pycache__/`, `.pytest_cache/`) are covered by the `.gitignore` from 01-02 and were not staged.

## Known Stubs

None. The fixture is intentional synthetic demo data; plan 01-05 wires it to the route under `DEMO_MODE=true`.

## Threat Flags

None. No new endpoint, auth path or trust boundary beyond the plan's threat model; T-01-12 to T-01-16 are mitigated as specified (synthetic labelling tests, `--check` drift test, monotone-UTC tests, state-restore tests, fictional content only).

## Authentication Gates

None.

## Next Phase Readiness

- Plan 01-05 can import `AnalyzeResponse`, `LiveResult`, `DemoResult`, `Meta` and `Problem` from `models`, load `fixtures/demo_analyze.json` via `AnalyzeResponse.model_validate_json`, and should refuse to serve a fixture whose `meta.synthetic` is not true (T-01-13).
- Plan 01-06 should document the `data_as_of` semantics in the README (live: server receive time, demo: constant) and copy-guard the new field descriptions.
- Phase 2 can delete `spread_simulator.py` and `users.py`; the committed-fixture tests keep running and the generator tests skip via `importorskip`.

## Self-Check: PASSED

- Created and modified files exist: models.py, scripts/generate_demo_fixture.py, fixtures/demo_analyze.json, tests/test_demo_fixture.py, tests/test_response_models.py (all FOUND).
- Commits are ancestors of HEAD: 5542829, c381235, 3a2a8c7 (all FOUND); `git rev-list --count` from the recorded base gives 3.
- Plan verification: `.venv/bin/python -m pytest -q` reports 82 passed, 19 xfailed, no XPASS; `scripts/generate_demo_fixture.py --check` exits 0; `git diff --quiet 9b5b085 -- spread_simulator.py users.py risk_analyzer.py` exits 0; `git check-ignore -q --no-index fixtures/demo_analyze.json` exits 1 (not ignored); regenerating leaves `git status` clean for `fixtures/`.
