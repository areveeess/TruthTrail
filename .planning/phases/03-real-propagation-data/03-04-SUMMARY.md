---
d17_confirmation: "D-17 confirmed by the owner on 2026-11-06 via owner-message"
phase: 03-real-propagation-data
plan: 04
subsystem: ingest
tags: [ingest, jetstream, pseudonymisation, hmac, normaliser, selection, replay, import-rules]
status: complete

requires:
  - phase: 03-real-propagation-data
    provides: "03-01 ratified 03-SPIKE.md (RT-2, M1, A, via_uri true, pseudonym d17-hmac-v1), the scrub-2 recorded fixture and its manifest coverage contract; 03-02 Policy, IngestSettings (PSEUDONYM_SECRET), socket guard; 03-03 schema with uri keys varchar(20) and pseudonym varchar(16)"
provides:
  - "core/cascade.py find_order_violations (non-raising, D-08)"
  - "ingest/pseudonym.py: parse_secret, make_keyer, Keyer.uri_key / account_key (d17-hmac-v1)"
  - "ingest/dialect.py: build_connect_url, subprotocols, classify_frame (closed result set), parse_stream_time, datetime_from_us, resume_cursor"
  - "ingest/normalise.py: NormalizedEvent, DeleteEvent, AccountAction, Dropped, LinkCandidate, normalise, occurred_at_from"
  - "ingest/selection.py (git mv from the spike): plus sample_bucket-based sample_keep, load_allowlist, SeedCandidate, seed_candidate, seed_decision_for, OD-3 option B arguments, SEED_REASONS"
  - "ingest/source.py: SourceItem, DropCounter, EventSource protocol, ReplaySource, ReplayRefused, DEFAULT_MANIFEST"
  - "conftest: fixture_manifest, recorded_lines, recorded_frames, find_frame, sample_rows, fixture_selection_policy, fixture_allowlist_file, fixture_policy_environment, FAKE_PSEUDONYM_SECRET, keyer"
  - "tests/test_import_rules.py FORBIDDEN rule table for later plans to extend"
affects: [03-05, 03-06, 03-07, 03-08, 03-12, docker]

actuals:
  tokens: 41704      # chars/4 over the added lines of 5397333..31b3b29
  tasks: 4           # Task 0 (precondition, no files) plus Tasks 1 to 3
  commits: 4         # git rev-list --count 5397333..HEAD before the docs commit
plan_head_before: 539733345b8ae75001b28bb7a9bb3a1654d57f95
plan_head_after: 31b3b29f61cf673c2f69aacc59ce2d9b01e59539

tech-stack:
  added: []
  patterns:
    - "Personal-data boundary: classify_frame -> normalise; nothing after normalise holds a raw DID, rkey, handle or at:// URI"
    - "Closed sets of frozen slotted dataclasses instead of exceptions for untrusted input (BadFrame reasons, Dropped reasons)"
    - "Selection on a normalised SeedCandidate; the record-based seed_decision delegates to it, so both paths are one implementation"
    - "Sources never yield Dropped items; drops go to the caller's DropCounter"
    - "Layer rules as data (FORBIDDEN) over a resolving AST walker with per-rule negative controls"

key-files:
  created:
    - src/truthtrail/ingest/__init__.py
    - src/truthtrail/ingest/pseudonym.py
    - src/truthtrail/ingest/dialect.py
    - src/truthtrail/ingest/normalise.py
    - src/truthtrail/ingest/source.py
    - tests/test_cascade_violations.py
    - tests/test_pseudonym.py
    - tests/test_ingest_dialect.py
    - tests/test_selection.py
    - tests/test_ingest_normalise.py
    - tests/test_replay_source.py
    - tests/test_import_rules.py
  renamed:
    - "scripts/spike_lib/selection.py -> src/truthtrail/ingest/selection.py (git mv, db2bb68)"
  modified:
    - src/truthtrail/core/cascade.py
    - src/truthtrail/ingest/selection.py
    - scripts/spike_lib/__init__.py
    - scripts/spike_lib/analysis.py
    - scripts/spike_lib/scrub.py
    - scripts/bluesky_spike.py
    - tests/conftest.py
    - tests/test_spike_analysis.py
    - tests/test_seed_domains.py
    - tests/test_spike_scrub2.py
    - .dockerignore

key-decisions:
  - "A quote of a non-post target (for example a feed generator) is a root candidate, exactly as the shipped derive_edge has always decided (RESEARCH Code Examples, existing test); the plan's Dropped(bad_edge) entry for that row would have changed the function that measured the ratified yield. A repost of a non-post target and a reply with both references unusable are Dropped(bad_edge)"
  - "The production seed path is seed_decision_for(event.seed_candidate(), ...): plan 03-05's Decider calls it on a NormalizedEvent; seed_decision(record, ...) keeps its signature and delegates, so both paths are one implementation"
  - "Sources never yield Dropped results; a DropCounter passed to items() counts them by reason (fixture: account_status_ignored 12)"
  - "find_order_violations also leaves out events that sit on a parent cycle (self-parents included), so a cycle is never reported as an order violation; enrich quarantines cycles"
  - "The Keyer holds the HMAC key schedule (hmac.HMAC state), not the raw secret bytes; repr and str are fixed text and the only public methods are uri_key and account_key"
  - "parse_secret tries hex first for an even-length all-hex string, then base64url with optional padding; both error texts are fixed and never contain the value"
  - "ReplaySource reads and hashes the data file once and iterates those same bytes (no time-of-check gap); a control or unparseable frame keeps the position of the frame before it when resuming"
  - "The recorded fixture now ships in the image: .dockerignore no longer excludes src/truthtrail/data/recorded because ReplaySource is runtime code that reads it (the rule test_container_files ties to its readers)"
  - "FAKE_PSEUDONYM_SECRET is 32 random bytes generated per test session, base64url encoded; no key material is a literal anywhere"

patterns-established:
  - "constructed_{shape} frames: built from the nearest real frame, and the test first asserts the fixture lacks the shape"
  - "Golden histograms are explained in a comment by the manifest's counts_by_kind and cross-checked against them"

requirements-completed: []

duration: 27min
completed: 2026-11-06
---

D-17 confirmed by the owner on 2026-11-06 via owner-message

# Phase 3 Plan 04: Ingest layer (pseudonymiser, dialect, normaliser, selection, replay) Summary

**The collector's database-free half now exists. A d17-hmac-v1 keyed pseudonymiser, a Jetstream v2/v1 dialect module that never raises, and a normaliser with D-12 edges together guarantee that no raw DID, rkey or at:// URI survives normalisation. The selection module that measured the spike's yield now ships from the package (moved with `git mv`) and reproduces the manifest's 149 tracked roots exactly. ReplaySource replays only a recorded-real, hash-matching recording. AST rules enforce the layer boundaries, and a fresh interpreter proves the API loads no ingest module and no websockets.**

## Performance

- **Duration:** about 27 min
- **Started:** 2026-11-06T09:38:49Z
- **Completed:** 2026-11-06T10:05:08Z
- **Tasks:** 4 of 4. Task 0 is the precondition check and writes no file; Tasks 1 to 3 each end with their own commit.
- **Files:** 23 changed in the code commits (12 created, 1 renamed, 10 modified)

## Gate output (Task 0, D-02 and D-17)

`.venv/bin/python scripts/check_spike_ratified.py --json` exited 0 at plan start and printed `pseudonym_scheme: d17-hmac-v1`, `resolved_od1 RT-2`, `resolved_od2 M1`, `resolved_od3 A` and `schema_via_uri true`. The front matter of 03-SPIKE.md records ratified_on 2026-11-06 and ratification_source owner-message. Nothing was written to 03-SPIKE.md and the owner was not prompted. The root pin guard printed `root pin ok` before the first write and again before every commit.

## For the verifier: DATA-03 keys (D-15)

DATA-03 says the collector is "keyed on the `at://` URI". In this layer, every such key is the keyed form of an `at://` URI: lowercase base32 of `HMAC-SHA256(PSEUDONYM_SECRET, "uri\0" + at://did/collection/rkey)`, first 20 characters. This covers `uri_key`, `parent_key`, `reply_root_key`, `quoted_key`, `via_key` and the `DeleteEvent.uri_key`. Accounts follow the same pattern with `HMAC(..., "acct\0" + did)`, first 16 characters. The schema columns keep the names `uri`, `parent_uri` and so on. Their values are these keyed forms; the raw URI is never stored. `tests/test_pseudonym.py` recomputes the scheme independently, and `tests/test_ingest_normalise.py::test_no_result_holds_a_raw_identifier` scans every field and repr of every result over the whole fixture for `did:`, `at://`, handle-shaped strings, and each raw DID and rkey.

## Golden histogram of result types over the fixture

`tests/test_ingest_normalise.py::GOLDEN_TYPES` and `GOLDEN_DETAIL` come from the first verified run. A comment in the test explains them through the manifest's `counts_by_kind`, and the test cross-checks them against those counts:

| Result | Count | From the manifest |
|---|---|---|
| NormalizedEvent | 1130 | post_create 605 (root-candidate 252, reply 313, quote 40) + repost_create 525 |
| DeleteEvent | 25 | post_delete 15 + repost_delete 10 |
| AccountAction | 13 | account deleted 5 + takendown 5, sync 3 |
| Dropped | 12 | account active 5 + deactivated 5 + throttled 2 (account_status_ignored) |

No line is a bad frame. ReplaySource yields the first three rows and puts the 12 drops into its DropCounter, so `tests/test_replay_source.py` adds the two and gets the same golden dict. Normaliser plus `seed_decision_for`, under the manifest's `selection_policy` (sample 10000, require_lang en, the 54 allowlist domains recorded at cut time), accept exactly `coverage.tracked_roots` = 149 roots. For every fixture root candidate, the record-based and candidate-based decisions agree.

## Shapes that needed constructed_* frames

Each test first asserts that the fixture really lacks the shape:

- error frame (`constructed_error_frame`, ConsumerTooSlow): the samples file holds only `#info` control frames
- update operation (`constructed_update`): there are 0 updates in the fixture
- quote of a non-post target (`constructed_quote_of_generator`) and repost of a non-post target (`constructed_repost_of_document`): a scan finds none
- reply with both references unusable, and a reply with only a usable root
- did:web subject (`constructed_did_web`), malformed via, unwanted collection (`constructed_like`)
- account statuses absent from `coverage.account_events_by_status` (suspended, desynchronized, a future status, a missing status)
- v1 account, identity and sync frames: the samples file has only v1 commits
- v2 identity, time-only and both-times sync variants
- `constructed_card_title`, `constructed_root_text`, a recordWithMedia card, and text on a reply, a quote and a repost: the scrubbed fixture carries no titles or text (D-04)
- `constructed_bad_created_at`
- the `constructed-recording` files used for the drop-counter and control-frame tests

## Import rules (tests/test_import_rules.py, FORBIDDEN)

| Rule | Modules | Must not import |
|---|---|---|
| core imports no higher layer | truthtrail.core | api, services, schemas, db, ingest, enrich, jobs |
| ingest never imports api, jobs or enrich | truthtrail.ingest | api, jobs, enrich |
| api never imports ingest | truthtrail.api | ingest |
| pure ingest modules import nothing from db | ingest.pseudonym, selection, dialect, normalise | db |

The walker resolves relative imports, `from X import name` (it adds both X and X.name) and literal `import_module` calls. There is one negative control per rule (15 cases), a test that each rule governs an existing module, and a floor of 35 files. Plans 03-06 to 03-08 and 03-12 add rows to `FORBIDDEN`; they do not touch the walker. The fresh-interpreter test sets `PYTHONPATH` to `src` only and uses `subprocess_env`. It imports `truthtrail.main`, calls `create_app()`, and finds 0 modules named `truthtrail.ingest*` or `websockets*`. Its control imports `truthtrail.ingest.dialect` and does see them.

## Accomplishments

- `find_order_violations` returns sorted ids. It does not raise for violations, cycles or self-parents, while duplicate ids and naive datetimes still raise. core/cascade.py remains standard-library only, and existing signatures and tests are unchanged.
- Pseudonymiser: an independent known-answer test, lengths 16 and 20, the lowercase base32 alphabet (never 32-character hex), domain separation, and different keys for different secrets. Every `parse_secret` failure uses a fixed text, checked with a marker value, and has no exception cause.
- Dialect: connect URLs for both generations with bare-hostname validation (scheme, path, port, userinfo and whitespace are refused). `maxMessageSizeBytes=1048576` is below the 2 MiB client bound (F-04). witnessedAt is preferred over time (F-03). Integer microsecond arithmetic is property-tested. Control results carry no cursor field, and bad frames are counted by reason: not_json, not_object, too_large, bad_shape or unknown_type. Hypothesis fuzzing of arbitrary JSON, text and bytes never raises.
- Normaliser: D-12 edges come from `derive_edge`. `occurred_at` is bounded by 1970 and the stream time plus 366 days (T-03-27). Text exists only on root candidates and is never in repr. Updates are ignored. The deletion statuses form an allow-list. No module logs anything, and a socket-refusing run over the whole fixture makes 0 network calls (T-03-24).
- ReplaySource refuses (T-03-26) a synthetic, missing or case-variant source_mode, a modified sha256, a modified data file, a missing data file, a truncated manifest, a manifest that is not an object, a missing files list, an unlisted data file, a bad sha field, the v1 dialect, and the Phase 1 demo fixture, including when it is renamed to look like a manifest. An AST walker with a negative control proves nothing under ingest or db references `demo_analyze`, `load_demo_fixture` or `FIXTURE_PATH`.

## Task Commits

1. **Task 1: find_order_violations, keyed pseudonymiser, Jetstream dialect module.** `a274682` (feat)
2. **Task 2a: move the spike selection functions into the package with git mv.** `db2bb68` (refactor). Content unchanged; `git log --follow -- src/truthtrail/ingest/selection.py` reaches `a2f2481` (03-01).
3. **Task 2b: normaliser, plus the selection additions.** `bf95741` (feat)
4. **Task 3: EventSource and ReplaySource, plus the AST import-rule tests.** `31b3b29` (feat)

## Verification results

- `pytest -q` (uv run): 1274 passed, 10 xfailed, 0 XPASS.
- `pytest -q -m "not requires_db"`: 1209 passed, 65 deselected, 10 xfailed. It contains every test of this plan.
- `REQUIRE_DB=1 REQUIRE_DB_FLOOR=65 pytest -m requires_db`: 65 passed (floor met, exit 0).
- `pytest --cov --hypothesis-profile=ci`: total 98.87% against the 96.00 gate (precision 2). normalise.py is at 98.90% and selection.py at 97.63%. Its misses are spike-era defensive branches.
- Plan task verifies: Task 1 five files, 145 tests (needs 45 or more). Task 2 four files, 160 tests with no skips (needs 55 or more). Task 3 two files, 52 tests with no skips (needs 18 or more). The spike script `analyze --help` exits 0 under `uv run --no-project --python 3.13 --with websockets==17.2`.
- New test counts by file: cascade_violations 14, pseudonym 29, ingest_dialect 72, selection 58 (selection tests moved from test_spike_analysis plus the additions), ingest_normalise 46, replay_source 31, import_rules 21.
- Clean: ruff check, ruff format --check, strict mypy (39 source files), `scripts/copy_guard.py`, the CI pip-audit pair ("No known vulnerabilities found"), and the gitleaks range scan `a5dd825..31b3b29` plus the working tree. Before each commit, the staged-diff scans found 0 lines with 32-hex strings and 0 old-key hits (counts only). `tests/test_no_hardcoded_credentials.py` passed and `gitleaks git --pre-commit --staged` returned exit 0.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Retargeted two more importers of the moved module**
- **Found during:** Task 2a
- **Issue:** `tests/test_seed_domains.py` and `tests/test_spike_scrub2.py` (not in files_modified) imported `spike_lib.selection`, which no longer exists after the git mv.
- **Fix:** They now import `truthtrail.ingest.selection`. `tests/test_recorded_fixture.py` already preferred the package module.
- **Commit:** db2bb68

**2. [Plan conflict, resolved toward the ratified yield] A quote of a non-post target is a root candidate, not Dropped(bad_edge)**
- **Found during:** Task 2
- **Issue:** One table row in the plan asked for Dropped(bad_edge) on a quote of a non-post target. The same plan says that edges come from `derive_edge`, and that existing selection functions keep their results. `derive_edge` returns a root for that shape, as pinned by the existing `test_derive_edge_drops_unusable_targets_and_tolerates_junk` and by RESEARCH Code Examples ("A post that only quotes a non-post record becomes a root candidate").
- **Fix:** The normaliser follows `derive_edge`. The test `test_constructed_quote_of_a_non_post_target_is_a_root_candidate` asserts it, with no parent_key and no quoted_key. A repost of a non-post target is Dropped(bad_edge) as planned. The fixture contains neither shape, so the tracked-root count does not depend on this choice.
- **Commit:** bf95741

**3. [Rule 3 - Blocking] .dockerignore no longer excludes the recorded fixture**
- **Found during:** Task 3
- **Issue:** `tests/test_container_files.py` ties the ignore rule to "no runtime code reads it". ReplaySource is runtime code that reads the recording (host `"recorded"`, DEFAULT_MANIFEST), and the `.dockerignore` comment itself said a plan that replays it inside the image must remove the line deliberately.
- **Fix:** Following the test's instruction, the line was removed and its comment replaced by one naming the reader. The test was not weakened, and its mirror test `test_the_recorded_fixture_ships_once_runtime_code_reads_it` now requires the fixture to ship.
- **Commit:** 31b3b29

**4. [Rule 2 - Missing critical functionality] Candidate-based seed decision**
- **Found during:** Task 2
- **Issue:** `seed_decision` takes the raw record, but the production path holds only a NormalizedEvent (D-17), and plan 03-05's Decider must apply selection to a NormalizedEvent.
- **Fix:** Added `SeedCandidate`, `seed_candidate()`, `seed_decision_for()` and `NormalizedEvent.seed_candidate()`. `seed_decision` keeps its signature and delegates, so results are identical (tested on constructed records and on every fixture root candidate).
- **Commit:** bf95741

### Other deviations

- **Commit trailer:** The plan text names `Claude Sonnet 5.5`. Following the orchestrator and HANDOFF, every commit carries `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and the Claude-Session line.
- **Test secret:** The plan asked for a literal constant. Under the owner's rule that test HMAC keys are generated at runtime, `FAKE_PSEUDONYM_SECRET` is `secrets.token_bytes(32)` per session, base64url encoded. The Hypothesis fuzz keyer is runtime-generated too.
- **SUMMARY first line:** The YAML front matter must start on line 1 for the GSD parser, so the D-17 confirmation line is the first front matter key (`d17_confirmation`) and the first line of the body.
- **Error frame:** The samples file holds no error frame, so the error test uses `constructed_error_frame` and asserts that path.
- **occurred_at bound:** The upper bound is inclusive at exactly stream time plus 366 days. The tests cover one second inside, exactly at, and one second beyond it.

## Issues Encountered

None blocking. Ruff's PT018 and E501 rules required splitting some test assertions and wrapping some lines.

## Known Stubs

None.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: information-disclosure | .dockerignore | The scrubbed, pseudonymised real recording (680 KB, scrub-2) now enters the image build context and the installed package, because ReplaySource reads it at runtime (D-04 planned this for the Phase 6 demo seed). It holds no text, titles, cids or queries, and only allowlisted link URLs, but it is pseudonymised, not anonymised (manifest privacy block). The Phase 6 public image should keep the manifest's removal-request route. |

## User Setup Required

None. `PSEUDONYM_SECRET` is already documented by plan 03-02; this plan only consumes it through `make_keyer(SecretStr)`.

## Requirement status

DATA-03 stays **Pending**. This plan is its first half (dialect, keyed identifiers, normalisation, selection, replay source). Plan 03-05 adds the writer, run loop, JetstreamSource, checkpoint and deletes, and completes it, following the 03-02 precedent for DATA-02.

## Next Phase Readiness

- Plan 03-05 builds the Decider on `NormalizedEvent.seed_candidate()` plus `seed_decision_for(...)`, with the allowlist from `load_allowlist(policy.track_allowlist_file)` and option B via `known_claim_urls` and `seed_claim_url_match`. Tests use `fixture_allowlist_file` and `fixture_policy_environment`, never seed_domains.txt.
- JetstreamSource must implement the `EventSource` protocol (`mode`, `dialect`, `host`, `items(resume_cursor_us, drops)`). It should use `dialect.build_connect_url`, `subprotocols`, `classify_frame` and `resume_cursor`, and send only Dropped results to the DropCounter.
- `find_order_violations` is ready for enrich's `order_violation_count`.

## Self-Check: PASSED

- All 12 created files, the renamed selection.py and the 11 modified files exist.
- Commits a274682, db2bb68, bf95741 and 31b3b29 are ancestors of HEAD.
- `git rev-list --count 5397333..31b3b29` = 4.
