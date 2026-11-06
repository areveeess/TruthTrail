---
phase: 03-real-propagation-data
plan: 05
subsystem: ingest
tags: [ingest, jetstream, writer, tombstones, checkpoint, advisory-lock, cli, erase, crash-resume, live-smoke]
status: complete

requires:
  - phase: 03-real-propagation-data
    provides: "03-01 ratified 03-SPIKE.md (RT-2, M1, A, via_uri true, d17-hmac-v1); 03-02 Policy, IngestSettings; 03-03 schema with overflow_through_us and the CHECK constraints; 03-04 dialect, Keyer, normaliser, seed_decision_for, ReplaySource, conftest fixture helpers"
provides:
  - "db/locks.py: try_advisory_lock / release_advisory_lock, one key per command (ingest, enrich, purge, news)"
  - "ingest/writer.py: TrackedIndex, Decider, Batch, flush (one transaction), FlushResult, event_row, claim_key_for, db_size_bytes, stored_event_count, load_known_claim_urls, known_claim_urls_for"
  - "ingest/source.py: JetstreamSource, GapNotice, SourceForbidden / SourceRejected / SourceFailed, user_agent, connect_default"
  - "ingest/run.py: run_ingest, RunBounds, RunSummary, status, stop-reason and exit-code constants, LIVE_SOURCE_NAME bluesky, REPLAY_SOURCE_NAME bluesky-replay"
  - "ingest/__main__.py: python -m truthtrail.ingest run|erase; ingest/erase.py: erase_dids, is_did"
  - "tests: loopback_server.py (LoopbackJetstream, Behaviour), conftest make_test_policy / explicit_policy / ListSource / fixture_items / run_pipeline / canonical_projection / row_counts, live_smoke.py"
affects: [03-06, 03-07, 03-08, 03-12, ci]

actuals:
  tokens: 58631      # chars/4 over the added lines of ec69367..bbdd018
  tasks: 3
  commits: 3         # git rev-list --count ec69367..HEAD before the docs commit
plan_head_before: ec69367975bffc9172a4e8d4dfd5f818d068e8f4
plan_head_after: bbdd018f5d8bf8634f322abb64faf4182972a8c8

tech-stack:
  added: []
  patterns:
    - "Tracked set keyed by root key (cascades.root_uri is unique), so a cascade created in the open batch needs no surrogate id before the flush"
    - "Duplicate test of the event's own key before every cap; overflow tallied by a per-cascade stream-time high-water mark that advances in memory only after commit"
    - "One transaction per batch: accounts, claims, cascades, events (RETURNING), overflow, key tombstones, account tombstones, checkpoint with GREATEST"
    - "Own reconnect loop over websockets (the built-in iterator cannot carry a new cursor); control results never carry a cursor"
    - "Deterministic failure injection with test-owned triggers created and dropped in try/finally, plus a non-atomic control"

key-files:
  created:
    - src/truthtrail/db/locks.py
    - src/truthtrail/ingest/writer.py
    - src/truthtrail/ingest/run.py
    - src/truthtrail/ingest/erase.py
    - src/truthtrail/ingest/__main__.py
    - tests/loopback_server.py
    - tests/live_smoke.py
    - tests/test_ingest_writer.py
    - tests/test_ingest_idempotency.py
    - tests/test_ingest_deletes.py
    - tests/test_jetstream_source.py
    - tests/test_ingest_run.py
    - tests/test_ingest_cli.py
    - tests/test_ingest_crash_resume.py
    - tests/test_no_pii_in_logs.py
  modified:
    - src/truthtrail/ingest/source.py
    - tests/conftest.py
    - tests/test_import_rules.py
    - .github/workflows/ci.yml
    - tests/test_ci_workflow.py

key-decisions:
  - "Account-wide tombstones (account deleted, takendown, sync, erase) remove only rows observed at or before the action's stream time; without this a replay meeting the action again would remove content the account published after it (found in the real fixture, see Deviations 1)"
  - "A reply whose parent reference is unusable (only a root reference) is refused as reply_without_parent; no edge is invented (the CHECK root_iff_no_parent also forbids it). The fixture has none"
  - "An overflow refusal at or below the high-water mark is counted under its own name, overflow_uncounted, so the documented lower bound is visible in the run counters"
  - "The run row has no stop-reason column; the stop reason is the counter stop:<reason> in ingest_runs.counters"
  - "run_ingest is the top-level task: it catches KeyboardInterrupt and cancellation, flushes, finalises the run row as interrupted and returns (exit 0); no signal handler is installed"
  - "A cascade pruned from the in-memory index (its window closed at a flush) makes later children count as untracked; before the prune they count as tracking_ended"
  - "Usage errors exit 2 through an argparse subclass whose error text never echoes the argument (a DID passed to erase is refused without being printed)"
  - "erase reads at most 10,000 lines and validates did:plc (24 base32 characters) or did:web"
  - "CI REQUIRE_DB_FLOOR raised from 65 to 174, the collected requires_db count at the end of this plan; test_ci_workflow MIN_DB_FLOOR follows"

requirements-completed: [DATA-03]

duration: about 95 min of work over two sessions (the first stopped on a usage limit before any commit)
completed: 2026-11-06
---

# Phase 3 Plan 05: The bounded Jetstream collector Summary

**The collector's write path now exists, and so does its live edge. Events are stored only for tracked roots: inserts are idempotent (`ON CONFLICT DO NOTHING RETURNING`), deletes become minimal tombstones, and the checkpoint is written in the same transaction as the rows it covers. JetstreamSource handles reconnects with full-jitter backoff, timestamp-cursor rewind, failover and explicit gaps. A bounded run loop and a CLI with documented exit codes sit on top, plus a stdin-only erase command. Every guarantee is proved on a real PostgreSQL and on a loopback WebSocket server serving real recorded frames. A CLI killed twice with `Popen.kill()` resumes to the same projection as an uninterrupted run. One bounded live run against the public stream stored 38 real tracked cascades.**

## Gate output

At the start of the resumed session, `.venv/bin/python scripts/check_spike_ratified.py --json` exited 0 (resolved_od1 RT-2, od2 M1, od3 A, schema_via_uri true, pseudonym_scheme d17-hmac-v1). The effective parameters matched the ratified values: TRACK_SAMPLE_PER_10K 625, TRACK_MAX_ACTIVE_ROOTS 2850, STORE_MAX_EVENTS_TOTAL 300000, INGEST_REWIND_SECONDS 30. Nothing was written to 03-SPIKE.md. The root pin guard printed `root pin ok` before the first write and before every commit. The first session stopped on a usage limit before committing anything, and this session resumed from the clean tree at ec69367.

## Task commits

1. **Task 1, writer:** `36d75b4` feat(03-05): collector writer (tracked set, idempotent upserts, tombstones, checkpoint in one transaction)
2. **Task 2, live source and run loop:** `c6ffd4c` feat(03-05): JetstreamSource (reconnect, backoff, silence, rewind, failover, gaps) and the bounded run loop
3. **Task 3, CLI, proofs, live smoke and the CI floor:** `bbdd018` feat(03-05): ingest CLI (run, replay, erase), crash-resume and no-personal-data proofs, live smoke

## Live smoke (real data, container only)

- **When:** 2026-11-06, 18:36:47Z to 18:39:49Z UTC. `.venv/bin/python tests/live_smoke.py` was run once against the public Jetstream (`jetstream.us-east.bsky.network`, primary) through the container proxy, with TLS verification on.
- **Setup:** a throwaway cluster and database, migrated with `python -m truthtrail.db migrate`; a throwaway in-memory PSEUDONYM_SECRET; TRACK_SAMPLE_PER_10K=10000; the ratified allowlist and bounds otherwise.
- **Result:** exit 0, status ok, stop max_seconds after 180 s. 43,180 frames; 38 root events in 38 cascades with 38 claims and 35 accounts; 0 children in the 3-minute window (children arrive over hours, D-14); 0 gaps; no error class.
- **Checks:** every identifier is a keyed token (20 or 16 characters). No text column holds `did:` or `at://`, and the collector output holds no `did:`. Only counts were printed. The database was dropped and the cluster stopped; nothing raw reached the repository.

## Golden row counts (tests/test_ingest_idempotency.py)

These are derived from the first verified run, under the explicit test policy `make_test_policy`: the manifest's `selection_policy` (sample 10000, require_lang en, TTL 48 h, the 54 cut-time allowlist domains), with the caps raised above the fixture size.

| Table | Uncapped | Capped (TRACK_MAX_EVENTS_PER_CASCADE = 4) |
|---|---|---|
| events | 805 = 149 roots + 245 replies + 29 quotes + 382 reposts (`coverage.children_by_kind`) | 426 |
| cascades | 149 = `coverage.tracked_roots` | 149 |
| accounts | 562 | 317 |
| claims | 118 (the distinct canonical URLs of the 149 roots) | 118 |
| ingest_checkpoints | 1 | 1 |

The capped dict is the one the crash-resume subprocess runs must reproduce, because they use `fixture_policy_environment()` plus the same cap of 4. Under that cap, 348 overflow refusals are counted and 11 are not (out of stream-time order or at an already counted microsecond), and none of these numbers change on a replay, a 30 s rewind or a stop and resume. Over the whole fixture, 10 rows are tombstoned by delete, which equals `coverage.deletes` (5 post + 5 repost).

## Exit codes (python -m truthtrail.ingest)

| Code | Meaning |
|---|---|
| 0 | normal stop: source end, max_seconds, max_events, max_stored, capacity_reached (store_max_events_total or db_budget), interrupted |
| 2 | usage error (unknown subcommand or argument; never echoed) |
| 3 | configuration error (missing or invalid DATABASE_URL / PSEUDONYM_SECRET, bad bound, bad allowlist, refused replay file); names the variable, never the value |
| 4 | source failure: SourceFailed (reconnect_budget, oversize_frame), SourceForbidden (HTTP 401/403), SourceRejected (other HTTP 400) |
| 5 | database failure (class name only) |
| 6 | another run is active (ingest advisory lock held; erase shares it) |

## OutdatedCursor and gap behaviour (as tested)

- An in-band `#info` OutdatedCursor yields `InfoFrame("OutdatedCursor")`, then `GapNotice(requested_cursor, None, "outdated_cursor")`. Neither item carries a cursor. The run loop closes the gap at the next event's stream time.
- An HTTP 400 with JSON `CursorTooOld` yields `GapNotice(requested, None, "cursor_too_old")`, and the source reconnects with no cursor (at the tip) without counting a failure. Any other 400 is SourceRejected after one attempt.
- A live checkpoint older than INGEST_MAX_RESUME_AGE_HOURS starts at the tip. It sets `resume_gap` and records the gap from the checkpoint to the first event. Replay mode never does this.
- Gaps in one run merge into one span (min from, max to) with `gap_count`, and each is counted as `gap:<reason>`.
- Reconnects after a close, silence (60 s by default) or an error frame such as ConsumerTooSlow resume from `last stream time - INGEST_REWIND_SECONDS`, and the overlap is redelivered. Delays are full jitter `uniform(0, min(60, 2^(n-1)))`, reset after a connection that delivered an event. Two consecutive failures on a host move to the next host, still with the timestamp cursor. The eighth consecutive failure is fatal.

## Verification results

- Plan verify, Task 1: three files, 73 tests (38 + 11 + 24; at least 40 required), no skips. `test_sql_parameterised` and `test_import_rules` pass.
- Plan verify, Task 2: the first two files hold 42 tests (18 + 24; at least 28 required). `pytest -m "not requires_db"`: 1230 passed, 162 deselected, 10 xfailed.
- Plan verify, Task 3: three files, 32 tests (26 + 2 + 4; at least 18 required). The live smoke exited 0.
- Full `uv run pytest -q`: **1424 passed, 10 xfailed, 0 XPASS**, up from 1274.
- `REQUIRE_DB=1 REQUIRE_DB_FLOOR=174 uv run pytest -m requires_db`: 174 passed, exit 0.
- `REQUIRE_DB=1 uv run pytest --cov --hypothesis-profile=ci`: **97.44 %** against the 96.00 gate. writer 96.80, source 98.30, run 92.52, erase 96.61, `__main__` 85.05 (its subprocess runs are not measured).
- ruff check, ruff format --check, strict mypy (44 files), `scripts/copy_guard.py` (clean) and the CI pip-audit pair ("No known vulnerabilities found") all pass. The gitleaks range scan `a5dd825..bbdd018` plus the working tree is clean.
- Before each of the three commits, the staged diff had 0 lines with 32-hex strings and 0 lines with the old key (derived in a script, counts only). `test_no_hardcoded_credentials.py` passed and `gitleaks git --pre-commit --staged` exited 0.
- Clean: no postgres process, no tt-pg-* directory, no collector process, no stray `__pycache__`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Account-wide tombstones were not idempotent on replay**
- **Found during:** Task 1 (the replay-twice projection test failed on one repost).
- **Issue:** The real fixture holds an account event (deleted) that arrives before a later create from the same account. The first replay stored the create after the action had been a no-op. A second replay met the action again and tombstoned the row, so the projection differed.
- **Fix:** Account-wide tombstones now apply only to rows with `observed_at <= action time`. This is the correct reading of D-16, because an action removes the content that existed when it happened. Key deletes are unchanged.
- **Files:** src/truthtrail/ingest/writer.py. **Commit:** 36d75b4

**2. [Rule 1 - Bug] The 1009 close was only detected when the server echoed it**
- **Found during:** Task 2 (oversize test).
- **Issue:** When the client itself closes with 1009 (frame above max_size), `ConnectionClosed.rcvd` can be None, so the source looped.
- **Fix:** The source checks both `rcvd` and `sent` close frames.
- **Commit:** c6ffd4c

**3. [Rule 2 - Correctness] A reply without a usable parent is refused, not stored with an invented edge**
- **Issue:** `derive_edge` returns a reply with `parent=None` when only the root reference is usable. Storing it would need an invented `parent_uri`, and the CHECK `root_iff_no_parent` forbids NULL.
- **Fix:** The source refuses it and counts it as `reply_without_parent` (tested with `constructed_rootonly`). The fixture has none, so no count changes.
- **Commit:** 36d75b4

### Other deviations

- **CI floor (orchestrator instruction):** `REQUIRE_DB_FLOOR` went from 65 to 174 in .github/workflows/ci.yml, and `MIN_DB_FLOOR` followed in tests/test_ci_workflow.py. Both files are outside files_modified.
- **Import rule shape:** `Rule` in tests/test_import_rules.py gained an `allowed` tuple, so "only truthtrail.ingest.source imports websockets" is one row. Three negative controls and two allowed controls were added; the walker is unchanged.
- **No-personal-data test:** the URL query markers are tracking parameters (`utm_source`, `fbclid`), which canonicalisation removes, plus a fragment. A non-tracking query parameter is part of the canonical claim URL that D-13 and D-18 store, so it is not personal-data output. A control test proves that the scan is not blind. The test also covers the live source's reconnect log line.
- **Exit code 2 for usage errors:** the plan's table lists 0, 3, 4, 5 and 6. Argparse usage errors exit 2, and the subclass never echoes the argument.
- **Stop reason storage:** `ingest_runs` has no stop-reason column, so the reason is stored as the counter `stop:<reason>`.
- **Commit trailer:** following the orchestrator and HANDOFF, the trailer is `Co-Authored-By: Claude Opus 5.5` instead of the plan's Sonnet line.
- **Secrets:** test HMAC keys are runtime-generated (`FAKE_PSEUDONYM_SECRET`), and the live smoke generates its own throwaway secret in memory.

## Issues Encountered

- Two loopback tests at first waited for more items than the scripted server could deliver and hung. Every source scenario now runs under a 15 s `asyncio.wait_for` bound, and the item counts are computed from the frames.
- The DB-budget test needed room for the run row and checkpoint pages: the budget is the empty size plus 48 KiB.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register. The live network edge (T-03-31, T-03-34), the erase command (T-03-38) and the write path (T-03-29, T-03-30, T-03-36, T-03-37) are all planned surfaces with their mitigations tested.

## User Setup Required

None. DATABASE_URL, PSEUDONYM_SECRET and COLLECTOR_CONTACT are documented by plan 03-02.

## Non-gating Windows follow-up (owner, PowerShell)

With a local PostgreSQL reachable through TEST_DATABASE_URL, or TRUTHTRAIL_PG_BIN set to its bin directory:

1. `uv run pytest -q tests/test_ingest_crash_resume.py`
2. Set DATABASE_URL and PSEUDONYM_SECRET (a random 48-character value) in the session, then run `uv run python -m truthtrail.ingest run --replay packaged --max-seconds 30`

Expected: the crash-resume test passes (Popen.kill works on Windows), and the replay prints a one-line counts summary and exits 0. Record the result in the phase UAT file.

## Next Phase Readiness

- Plan 03-06 (enrich and purge) reads `cascades.enrich_dirty`, resolves `parent_state` orphan rows and computes the rollups. It must not write `overflow_count` or `overflow_through_us`, and it uses `PURGE_LOCK_KEY` and `ENRICH_LOCK_KEY` from db/locks.py. A claim unlinked by a root delete stays until the purge finds it unreferenced.
- Plan 03-07 (API) reads `ingest_runs` (status, gap fields, `last_time_us`) for freshness and gaps, and presents `overflow_count` as "at least".

## Self-Check: PASSED

- All 15 created files and the 5 modified files exist.
- Commits 36d75b4, c6ffd4c and bbdd018 are ancestors of HEAD.
- `git rev-list --count ec69367..bbdd018` = 3.
