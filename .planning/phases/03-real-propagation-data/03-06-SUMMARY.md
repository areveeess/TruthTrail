---
phase: 03-real-propagation-data
plan: 06
subsystem: enrich
tags: [enrich, resolver, rollup, hypothesis, mutation-tests, orphans, purge, retention, advisory-lock, cli]
status: complete

requires:
  - phase: 03-real-propagation-data
    provides: "03-01 ratified 03-SPIKE.md (RT-2, M1, A, via_uri true, d17-hmac-v1); 03-02 Policy retention fields; 03-03 schema (parent_state, depth, rollup columns, enrich_dirty, rollup_version); 03-04 find_order_violations; 03-05 writer, locks, run_pipeline and fixture helpers"
provides:
  - "enrich/resolve.py: resolve_cascade(rows, as_of) -> ResolvedCascade (EventRow, ResolvedNode, PARENT_STATES)"
  - "enrich/rollup.py: Rollup, compute_rollup, ROLLUP_VERSION = 1, in_velocity_window"
  - "enrich/apply.py: enrich_dirty(engine, as_of, max_cascades, force) -> EnrichResult, default_as_of, select_work, datetime_from_us"
  - "enrich/purge.py: purge(engine, policy, as_of, max_seconds, dry_run, batch_rows, batch_cascades) -> PurgeResult, PASS_NAMES"
  - "enrich/__main__.py: python -m truthtrail.enrich run|purge (exit 0, 2, 3, 5, 6)"
  - "ingest/writer.py: mark_cascades_dirty (unconditional dirty mark)"
  - "tests/conftest.py: insert_forest, set_checkpoint, enrich_projection, truncate_application_tables, ENRICH_COUNTERS"
affects: [03-07, 03-10, 03-12, phase-6, ci]

estimate:
  tokens: 150000
  tasks: 3
actuals:
  tokens: 37637      # chars/4 over the added lines of bca980c..0551c7f
  tasks: 3
  commits: 3         # git rev-list --count bca980c..HEAD before the docs commit
plan_head_before: bca980c0d715e9b97b822cf95aa5f9e177a7b965
plan_head_after: 0551c7f675b902bf7a41b38098053c885c477da7

tech-stack:
  added: []
  patterns:
    - "Pure resolver keyed by uri: every place where arrival order could leak is a private module-level function, and a mutation test replaces exactly one of them"
    - "One transaction per cascade: SELECT ... FOR UPDATE SKIP LOCKED on the cascade row, changed event rows locked NOWAIT, only changed rows written"
    - "Purge passes as a table of literal statements (selection with ORDER BY id LIMIT :n FOR UPDATE OF t SKIP LOCKED, plus a dry-run count), looped in batches under a monotonic deadline"
    - "Retention cutoffs computed from an explicit as_of minus Policy days and bound as parameters; no now() in SQL"

key-files:
  created:
    - src/truthtrail/enrich/__init__.py
    - src/truthtrail/enrich/resolve.py
    - src/truthtrail/enrich/rollup.py
    - src/truthtrail/enrich/apply.py
    - src/truthtrail/enrich/purge.py
    - src/truthtrail/enrich/__main__.py
    - tests/test_enrich_resolve.py
    - tests/test_enrich_properties.py
    - tests/test_enrich_db.py
    - tests/test_purge.py
    - tests/test_enrich_cli.py
  modified:
    - src/truthtrail/ingest/writer.py
    - tests/conftest.py
    - tests/test_import_rules.py
    - .github/workflows/ci.yml
    - tests/test_ci_workflow.py

key-decisions:
  - "The collector's dirty mark is unconditional (mark_cascades_dirty). The former `WHERE enrich_dirty IS FALSE` filter loses the mark when it runs during an enrich transaction, because under READ COMMITTED it reads the still-true flag from its snapshot, matches nothing and does not wait. A negative-control test shows the loss."
  - "Enrich locks the changed event rows NOWAIT before updating them. A row held by an open collector batch then fails at once with 55P03, and that counts as contention: the cascade stays dirty. Enrich therefore never deadlocks with a collector whose dirty-mark UPDATE is already waiting for enrich's cascade lock."
  - "Enrich's default as_of is the stream time of the latest committed checkpoint (data_as_of), so events_1h agrees with what /v1 calls current. Purge's CLI default is the wall clock, because retention is a real-time privacy promise and has to keep running when ingestion stops."
  - "Several root rows in one cascade are each a root (state none, depth 0). Unknown edge kinds and self-parents are invalid. A non-root without a parent reference is an orphan. A naive timestamp is read as UTC. The resolver never raises on data."
  - "invalid_count counts non-deleted invalid rows, like the other counters. It lives in the result and in the run's log line, not in a cascade column (D-20)."
  - "An empty cascade, whose every event was purged, keeps its NOT NULL first_event_at and last_event_at, and its counters go to 0."
  - "Purge passes use FOR UPDATE SKIP LOCKED, so a row that a concurrent writer holds is left for the next run. The claims and accounts passes are meant to run with no collector batch open (see deferred-items.md)."
  - "CI REQUIRE_DB_FLOOR and MIN_DB_FLOOR were raised from 174 to 217, the requires_db count collected at the end of this plan."

requirements-completed: [DATA-04]

duration: 28 min
completed: 2026-11-06
---

# Phase 3 Plan 06: Deterministic enrich and the retention purge Summary

**A pure resolver now derives each cascade's parent states, depths, canonical order and counters from the set of its stored rows. Orphans are an explicit state and no parent is ever invented. Hypothesis proves on 200 derandomized examples that shuffled arrival gives the same state, and three arrival-dependent mutants are each caught. A per-cascade transactional write-back proves the same on real PostgreSQL, with different surrogate ids for the same rows. A purge job enforces the ratified retention windows as Policy parameters, and both jobs run as `python -m truthtrail.enrich run|purge`.**

## Gate output

`.venv/bin/python scripts/check_spike_ratified.py --json` exited 0 before the first write: resolved_od1 RT-2, od2 M1, od3 A, schema_via_uri true, pseudonym_scheme d17-hmac-v1. The effective retention parameters were RETENTION_TEXT_DAYS 14, RETENTION_CASCADE_DAYS 90, RETENTION_TOMBSTONE_DAYS 7, RETENTION_NEWS_DAYS 30 and RETENTION_DORMANT_DAYS 0. Nothing was written to 03-SPIKE.md. The root pin guard printed `root pin ok` before the first write and before every commit. None of these numbers appears in the purge code or in any test: the code reads the Policy object, and every test passes explicit small windows.

## Task commits

1. **Task 1, pure resolver and rollup:** `cb6e8bc` feat(03-06): pure cascade resolver and rollup; Hypothesis order-independence proof with mutation tests
2. **Task 2, write-back:** `1c11204` feat(03-06): per-cascade transactional enrich write-back; database permutation, idempotence, orphan-flip and lock tests
3. **Task 3, purge and CLI:** `0551c7f` feat(03-06): retention purge and the enrich/purge commands

## Rollup definitions as implemented (for the verifier)

- **Counters exclude tombstones.** `event_count`, `reply_count`, `quote_count`, `repost_count`, `unique_accounts` (distinct non-null accounts), `orphan_count`, `disconnected_count` and `events_1h` count NON-deleted rows only. `deleted_count` counts the tombstones.
- **Structure keeps tombstones.** A tombstone keeps its state, its resolved parent and its depth, so its children stay resolved and connected. `max_depth` is the largest depth of a connected non-repost row, tombstones included, and 0 when only the root is connected.
- `disconnected_count` counts the non-deleted non-root rows that are not connected to a root through resolved reply or quote edges: orphans, all their descendants, invalid rows and their descendants. A repost is connected when its subject is connected.
- `order_violation_count` is `len(find_order_violations(events))` over all rows, using the values the order uses. Invalid rows are given no parent, so cycles are never counted as violations. A violation is never raised and never repaired.
- `events_1h` counts the rows in the half-open window `(as_of - 1 h, as_of]`, and `rolled_up_at` = `as_of`.
- `first_event_at` and `last_event_at` are the min and max `observed_at` of the non-deleted rows, or of all rows when every row is deleted. They are unchanged for an empty cascade.
- **The invalid count is only in the result.** `ResolvedCascade.invalid_count` and `EnrichResult.invalid` carry it, plus the run's log line. There is no cascade column (D-20), and the tree endpoint shows `parent_state` per node.
- `ROLLUP_VERSION = 1`. A cascade whose stored version differs is selected as work even when it is clean.

## Parent-state rules (D-12, D-14)

| Case | State | Parent | Depth | Disconnected |
|---|---|---|---|---|
| root row | none | None | 0 | no |
| parent row stored, chain reaches a root | resolved | parent uri | parent + 1 | no |
| parent_uri matches no stored row (or is NULL) | orphan | None (never the root) | None | yes |
| child of an orphan, of an invalid row or of a cycle tail | resolved | parent uri | None | yes |
| repost of a connected subject | resolved | subject | None | no |
| repost of a missing subject | orphan | None | None | yes |
| self-parent, every cycle member, a child of a repost, an unknown kind | invalid | None | None | yes |

An orphan flips to resolved once its parent is stored and the cascade is marked dirty. This is tested at both layers.

## as_of default and why

- `enrich run`: `--as-of` defaults to `datetime_from_us(cursor_time_us)` of the most recently updated `ingest_checkpoints` row, which is D-24's `data_as_of`. Velocity and `rolled_up_at` are then consistent with the freshness the API reports, and a replay or a late enrich yields the same `events_1h` as an immediate one. With no checkpoint nothing has been ingested, and the run selects nothing.
- `enrich purge`: `--as-of` defaults to the current UTC time. Retention bounds how long personal data is kept in real time, so it has to advance while ingestion is stopped. The library function always takes an explicit `as_of`.

## Purge pass order

Each pass is a literal selection with `ORDER BY t.id LIMIT :n FOR UPDATE OF t SKIP LOCKED`, followed by the change, with one transaction per batch:

1. `text`: roots with `observed_at <= as_of - RETENTION_TEXT_DAYS` get `text = NULL` and `text_purged_at = as_of`. With 0 days every text is purged at once (RT-1).
2. `tombstones`: rows of every edge kind, roots included, with `deleted_at <= as_of - RETENTION_TOMBSTONE_DAYS` are hard-deleted. The touched cascades are marked dirty in the same transaction, and `cascades_marked_dirty` counts them.
3. `dormant`: runs only when `RETENTION_DORMANT_DAYS > 0`. It removes cascades that have no non-root event once `first_event_at` is that old.
4. `cascades`: whole cascades with `first_event_at <= as_of - RETENTION_CASCADE_DAYS` are deleted. Their events go through the foreign key, and `cascade_events` counts them.
5. `claims`: removes `social_link` claims that no cascade and no event references.
6. `news_claims`: removes `news_headline` claims by `created_at`, after RETENTION_NEWS_DAYS.
7. `news_fetches`: removes ledger rows by `called_at`, after RETENTION_NEWS_DAYS.
8. `accounts`: removes accounts that have no event.
9. `ingest_runs`: removes rows by `started_at`, after RETENTION_CASCADE_DAYS.

The loop stops at the `--max-seconds` deadline (a monotonic clock) with `status=partial`, and a rerun finishes the work. `--dry-run` runs the same predicates as counts. The later passes then count against the current data, so their numbers are lower bounds. Purge holds its own advisory lock (`PURGE_LOCK_KEY`), and a second purge prints `purge status=locked` and exits 6.

## Root-tombstone behaviour

A deleted root is a tombstone like any other row (D-16). The writer has already set `cascades.root_deleted_at` and unlinked the claim. After RETENTION_TOMBSTONE_DAYS the purge hard-deletes the root row and marks the cascade dirty. The next enrich makes the root's children honest orphans: `parent_uri` no longer matches a row, they are not re-parented, and `first_event_at` moves to the earliest remaining child. The cascade keeps `root_deleted_at`, so it stays hidden from the feed until the cascade window deletes it, or until the dormant pass does when that pass is enabled and the cascade has no children left. The unlinked claim is removed by the `claims` pass once no other cascade or event references it. The test also keeps it while another cascade still links the same article.

## How the three mutants were caught

The strategy follows RESEARCH Pattern 7. It draws a subset of 12 ids in a drawn permutation, with kinds weighted toward replies. Parents come mostly from inside the drawn set (`ids * 4 + IDS + [None]`), so chains, shared parents, cycles with tails and children of reposts are common. Timestamps span 0 to 6 s with microsecond 0 or 1, which gives many ties. Accounts come from `{None, a, b, c}`, tombstones are included, and both identical and CONFLICTING duplicate deliveries are appended. Each mutant replaces ONE private function of `truthtrail.enrich.resolve` by monkeypatching, then runs the order-independence property at an explicit `max_examples=200, derandomize=True` inside `pytest.raises(AssertionError)`:

1. `_choose_duplicate` becomes "first delivered wins". Conflicting duplicates then change `unique_accounts` or `deleted_count` with arrival order.
2. `_canonical_order` becomes a stable sort on `(observed_at, depth)` over the input order, which drops the uri tie-break. Timestamp ties then reorder `order`.
3. `_cycle_members` starts its walks in arrival order and marks the whole path. A tail that leads into a cycle then becomes invalid only when a walk starts on it.

All three were caught under both the `ci` and the `dev` profile. A control test runs the unmutated resolver under the same settings and passes. Three `find()` tests prove the strategy reaches a cycle with a tail, a conflicting duplicate and a tie together with an order violation. The arrival order reaches each function because `_collapse` and `_initial_states` iterate in first-arrival order, so each function has to be order-independent on its own.

## Verification results

- Task 1 verify: the two enrich files have 72 tests (61 + 11, at least 30 required). `--hypothesis-profile=ci` passes them plus the import rules (112 passed in 21 s), and the default dev profile passes too (11 passed). Full suite: 1512 passed, 10 xfailed.
- Task 2 verify: `REQUIRE_DB=1 pytest tests/test_enrich_db.py` gives 20 passed, 0 skipped (at least 12 required). `test_sql_parameterised` and `test_import_rules` pass. `REQUIRE_DB=1 pytest -q` gives 1532 passed, 10 xfailed.
- Task 3 verify: `test_purge.py` + `test_enrich_cli.py` give 32 passed, 0 skipped (18 + 14, at least 22 required). The SQL, import-rule, policy and policy-docs tests pass (131).
- `REQUIRE_DB=1 REQUIRE_DB_FLOOR=217 pytest -q --cov --hypothesis-profile=ci` gives **1564 passed, 10 xfailed, 0 XPASS, coverage 97.36 %** against the 96.00 gate. resolve 98.24, rollup 100, apply 99.44, purge 98.78, `__main__` 83.72 (its subprocess runs are not measured).
- Full `uv run pytest -q`: **1564 passed, 10 xfailed, 0 XPASS**, up from 1424 at the end of plan 03-05. `REQUIRE_DB=1 REQUIRE_DB_FLOOR=217 uv run pytest -m requires_db`: 217 passed, exit 0.
- ruff check, ruff format --check and strict mypy (50 files) are clean. `scripts/copy_guard.py` is clean, and the CI pip-audit pair reports "No known vulnerabilities found". The gitleaks range scan `a5dd825..0551c7f` plus the working tree is clean.
- Before each of the three commits, the staged diff had 0 lines with a 32-hex string and 0 lines with the old key (derived in a script, counts only). `test_no_hardcoded_credentials.py` passed (13), and `gitleaks git --pre-commit --staged` exited 0.
- Test HMAC keys are runtime-generated (`FAKE_PSEUDONYM_SECRET`), and enrich and purge never read PSEUDONYM_SECRET. No test opens a network connection, and no real handle or post text is printed: the recording carries no text, so tests put constructed text on roots.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] The collector's dirty mark could be lost during an enrich transaction (T-03-43)**
- **Found during:** Task 2, while designing the lost-flag test.
- **Issue:** `_flush_in` marked touched cascades with `UPDATE cascades SET enrich_dirty = true WHERE id IN (...) AND enrich_dirty IS FALSE`. Under READ COMMITTED, while enrich holds the cascade row (flag still true, cleared at its commit), that UPDATE reads true from its snapshot, matches nothing and does not wait. Enrich then commits `false`, and a tombstone the collector applied to already-loaded rows is never re-enriched. The plan's claim that the collector's UPDATE waits for the lock did not hold for the filtered statement.
- **Fix:** a new `mark_cascades_dirty(connection, ids)` in writer.py updates without the filter, with sorted ids. `test_a_dirty_mark_during_an_enrich_transaction_is_never_lost` proves that the UPDATE waits and the flag ends true. `test_the_filtered_dirty_mark_would_have_lost_the_flag` is the negative control. writer.py is outside files_modified.
- **Commit:** 1c11204

**2. [Rule 2 - Correctness] Deadlock between enrich and an open collector batch**
- **Found during:** Task 2.
- **Issue:** a collector batch that tombstones event E of cascade C holds E's row lock, then waits for C's row lock to mark it dirty. If enrich holds C and needs to update E, the two transactions deadlock. PostgreSQL would usually abort the collector, which waited first, so the batch fails with exit 5.
- **Fix:** enrich locks the changed event rows `FOR UPDATE NOWAIT` before updating them. A held row raises 55P03, which counts as contention (`errors: {LockNotAvailable: 1}`) and leaves the cascade dirty. 40P01 is treated the same way. Any other database error still propagates. This is tested with a second connection holding an event row.
- **Commit:** 1c11204

### Other deviations

- **Mutant 2 patches `_canonical_order`, not a separate "iteration order" function.** Arrival order reaches the ordering and the cycle finder through `_collapse` and `_initial_states`, which iterate in first-arrival order. The arrival-dependent tie-break and the arrival-chosen cycle start are therefore each ONE function replacement, as the plan's test requirement asks. The pure resolver still iterates sorted uris wherever the result could depend on order.
- **A usage-error exit code 2** was added to the plan's 0, 3, 5 and 6, mirroring the ingest CLI. A naive `--as-of`, a non-positive bound or an unknown argument exits 2 without echoing the argument.
- **Purge `--as-of` defaults to the wall clock.** The plan only says `--as-of`. The reason is given above.
- **CI floor (orchestrator instruction):** `REQUIRE_DB_FLOOR` and `MIN_DB_FLOOR` went from 174 to 217. Both files are outside files_modified.
- **Commit trailer:** following the orchestrator and HANDOFF, the trailer is `Co-Authored-By: Claude Opus 5.5` instead of the plan's Sonnet line.
- **deferred-items.md:** a Phase 6 scheduling item records the snapshot race of the claims and accounts passes.

## Issues Encountered

- Ruff's S608 rejects SQL composed by string concatenation, so the purge's pass table spells out every statement as a literal (a selection and a dry-run count per pass).
- Three of my own test expectations had wrong window arithmetic (events_1h boundaries). I fixed the tests, and the code was unchanged.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register. T-03-39 to T-03-44 are mitigated and tested. The new NOWAIT event lock and the unconditional dirty mark strengthen T-03-43, and the purge snapshot race is recorded for Phase 6 in deferred-items.md.

## User Setup Required

None. The commands need only DATABASE_URL, plus optional RETENTION_* overrides.

## Next Phase Readiness

- Plan 03-07 (API) can read `events.parent_state`, `depth` and `parent_event_id`, plus the cascade rollups: `orphan_count`, `disconnected_count`, `order_violation_count`, `events_1h` as of `rolled_up_at`, and `deleted_count`. It shows the invalid state per node from `parent_state`. A cascade with `rolled_up_at IS NULL` has not been enriched yet.
- Phase 6 schedules `ingest run`, then `enrich run`, then `enrich purge`, sequentially, and must not overlap purge with a collector batch (deferred-items.md).

## Self-Check: PASSED

- All 11 created files and the 5 modified files exist.
- Commits cb6e8bc, 1c11204 and 0551c7f are ancestors of HEAD.
- `git rev-list --count bca980c..0551c7f` = 3.
