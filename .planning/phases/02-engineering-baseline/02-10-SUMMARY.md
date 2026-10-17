---
phase: 02-engineering-baseline
plan: 10
subsystem: core
tags: [cascade, invariants, hypothesis, property-tests, fixture-gate, lifespan]

requires:
  - phase: 02-engineering-baseline
    provides: plan 02-09 retry loop; create_app(), client_factory, app_module fixture, load_demo_fixture string patch target
provides:
  - "core/cascade.py: CascadeEvent, CascadeError, order_events, validate_cascade, cascade_events_from (stdlib only), the signatures Phase 3 imports"
  - "Hypothesis ci (200 examples, derandomized, no database, no deadline) and dev (50) profiles in tests/conftest.py"
  - "validate_cascade hard gate in load_demo_fixture() and a fixture load in the lifespan when DEMO_MODE=true"
affects: [02-11, 02-12, 03]

actuals:
  tokens: 17000
  tasks: 2
  commits: 2
plan_head_before: 4b0f621109bc417e33b77caac7160fcd4d45f1d0
plan_head_after: 19f3d0165da8f37cc35b6b458cf8f21caef78777

tech-stack:
  added: []
  patterns:
    - "Pure invariant functions over a typed view (CascadeEvent) plus a structural-Protocol adapter that bridges schemas.Event.timestamp (str) to observed_at (aware datetime)"
    - "Validate, never reorder, the served demo body (D-19): the committed per-platform-chain order is the frozen contract"

key-files:
  created:
    - src/truthtrail/core/cascade.py
    - tests/test_cascade_properties.py
    - tests/test_cascade_gate.py
  modified:
    - src/truthtrail/api/analyze.py
    - src/truthtrail/api/app.py
    - tests/conftest.py

key-decisions:
  - "order_events also rejects duplicate ids, naive datetimes and cycles (shared _index/_depths), so a pathological input raises CascadeError instead of a TypeError or an ambiguous order"
  - "order_events is not applied to the served demo body; load_demo_fixture validates only (D-19)"
  - "The lifespan calls the loader through the truthtrail.api.analyze module attribute so a patched loader is honoured and demo mode off loads nothing"

requirements-completed: [ENG-03]

duration: 20min
completed: 2026-10-17
status: complete
---

# Phase 2 Plan 10: Cascade Invariants, Hypothesis Properties and Fixture Gate Summary

**Cascade ordering and parent-before-child are now pure stdlib functions (`order_events`, `validate_cascade`) proven by Hypothesis on arbitrary generated cascades with timestamp ties, and `validate_cascade` is a hard gate on the demo fixture (loader error, generic 500, demo-mode startup failure) while the served body keeps the committed event order.**

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | 2a1406c | feat(cascade): order_events/validate_cascade with Hypothesis properties and ci profile |
| 2 | 19f3d01 | feat(cascade): validate_cascade gates fixture load and demo startup; served order stays the committed order |

## What was built

- **`core/cascade.py` (Task 1).** Frozen dataclass `CascadeEvent(event_id, parent_event_id, observed_at)`, `CascadeError(ValueError)`, `order_events` (new list, sort key `(observed_at, depth, event_id)`, depth = known ancestors, so a parent precedes its child on equal timestamps), `validate_cascade` (duplicate ids, naive `observed_at`, self-parent or any cycle, present parent later than child; equal timestamps and orphans are valid) and `cascade_events_from` with the `HasTimestamp` Protocol (ISO-8601 including `Z`, offsets normalised to UTC, naive or unparseable raises `CascadeError`). Depth is computed with an explicit path set, so a cycle raises instead of looping. Error messages carry event ids only. Standard library imports only.
- **Hypothesis profiles.** `ci` (200 examples, derandomized, `database=None`, `deadline=None`, `too_slow` suppressed) and `dev` (50 examples), registered in `tests/conftest.py`; `HYPOTHESIS_PROFILE` or `--hypothesis-profile=ci` selects one.
- **`tests/test_cascade_properties.py` (22 tests).** A composite strategy builds forests incrementally (each event has no parent or an earlier parent; deltas of 0 are frequent so ties occur; ids are a drawn permutation unrelated to creation order), plus a shuffle strategy. Four properties: permutation sorted by `observed_at` with every present parent first, idempotent and arrival-order independent, generated cascades validate, a child moved one microsecond before its parent is rejected. Unit tests cover the adapter (`Z`, `+00:00`, `+05:30` to 09:30 UTC, naive, garbage, input order), duplicates, naive datetimes, self-parent, two-event cycle, orphans, equal timestamps, empty input, no input mutation, and that messages contain ids but no timestamps. Tests were seen failing (module missing) before the implementation.
- **Fixture gate (Task 2).** `load_demo_fixture()` runs `validate_cascade(cascade_events_from(result.events))` for every `DemoResult` after the synthetic-label check; the lifespan calls `analyze.load_demo_fixture()` when `settings.demo_mode` is true. `order_events` is not applied to the served body and the fixture bytes are untouched.
- **`tests/test_cascade_gate.py` (8 tests).** Committed cascades validate; `GET /analyze` with `DEMO_MODE=true` returns a body equal to the committed file with identical per-result event id sequences; sorting the committed fixture would change the id order of at least one cascade (documents why the gate does not reorder); a corrupted copy (first child one hour before its parent, `FIXTURE_PATH` patched, `cache_clear()` before and after) makes the loader raise `CascadeError`, makes a request return the generic 500 problem+json (`internal_error`, no `results`, no event ids in the body, `CascadeError` in the log), and makes entering the client with `DEMO_MODE=true` raise at startup; a recording loader proves the lifespan loads the fixture once in demo mode and never with demo mode off; an AST check shows `core/cascade.py` imports only standard-library modules. The three failure tests and the lifespan test were seen red before the gate was added.

## Mutation checks (not committed, recorded as required)

Both ran under `--hypothesis-profile=ci` against a temporary edit of `core/cascade.py`, which was restored byte-identically afterwards (verified with `cmp`):

1. **Depth tie-break dropped** (sort key `(observed_at, event_id)`): 2 failed, 20 passed. `test_order_is_sorted_permutation_with_parents_first` (the Hypothesis property) failed, and so did the unit test for equal timestamps with a child id that sorts first. Property 1 fails as required.
2. **Equal timestamp treated as invalid** (`parent.observed_at >= event.observed_at`): 2 failed, 20 passed. `test_generated_cascades_are_valid` (the Hypothesis property) and `test_valid_cascade_with_equal_parent_and_child_timestamps` failed. The valid-cascade property fails as required.

## Verification

- `pytest -q`: 485 passed, 10 xfailed, no XPASS, under both the dev profile and `--hypothesis-profile=ci` (455 passed at the start; 477 after Task 1, +22; 485 after Task 2, +8). The 10 strict xfails in `tests/test_char_simulator.py` and `tests/test_char_risk_analyzer.py` are unchanged and still xfail for their original reasons.
- `tests/test_provenance_demo.py`, `test_demo_fixture.py`, `test_legacy_frozen.py`, `test_openapi_golden.py`, `test_settings.py`: 98 passed. `scripts/generate_demo_fixture.py --check`: "demo fixture is up to date". `ruff check`, `ruff format --check`, `mypy` (22 source files) and `scripts/copy_guard.py` clean. `tests/test_no_hardcoded_credentials.py`: 13 passed before each commit; the added-lines scan for 32-hex strings found nothing.
- No Docker daemon or GitHub Actions run is involved; nothing here claims a docker build or a CI run passed.

## Deviations from Plan

None - plan executed as written. Notes:

- `order_events` additionally rejects duplicate ids, naive datetimes and cycles (it shares `_index`/`_depths` with `validate_cascade`). The plan specified this only for `validate_cascade`; without it a duplicate id would silently collapse an event and a naive datetime would raise a bare `TypeError`.
- Test counts exceed the plan's floors (12 and 7 collected) because of parametrisation and extra unit tests.
- ruff RUF007 asked for `itertools.pairwise` in the ordering property; applied.

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model. T-02-36 (validate gates the loader and demo startup, label check, sha256 pin and generator `--check` unchanged), T-02-38 (visited-set cycle detection, duplicates rejected, unit and property tests) are implemented and tested; T-02-37 is accepted as documented and recorded by a test. No packages were added (T-02-SC).

## Self-Check: PASSED

- Files src/truthtrail/core/cascade.py, tests/test_cascade_properties.py, tests/test_cascade_gate.py, src/truthtrail/api/analyze.py, src/truthtrail/api/app.py, tests/conftest.py: FOUND
- Commits 2a1406c and 19f3d01 are ancestors of HEAD: FOUND
