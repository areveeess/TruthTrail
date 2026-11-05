---
phase: 03-real-propagation-data
plan: 01
subsystem: data
tags: [bluesky, jetstream, spike, fixture, scrubber, gate, websockets]

requires:
  - phase: 02-engineering-baseline
    provides: ruff, strict mypy, pytest conventions, CI guards (gitleaks, copy guard, credential test)
provides:
  - "scripts/bluesky_spike.py: bounded, read-only, credential-free recorder, probes, analyzer, storage probe and fixture cutter"
  - "scripts/spike_lib: selection (stdlib, mypy --strict, moved unchanged by plan 03-04), analysis, scrub and the stratified cutter"
  - "03-SPIKE.md: measured decision document with three OWNER DECISION blocks and the one-way D-17 section (ratified: false)"
  - "scripts/check_spike_ratified.py: the machine gate for plans 03-02 to 03-12 with the OD_IMPLICATIONS table"
  - "src/truthtrail/data/recorded/bluesky-2026-10-19.*: real scrubbed fixture (scrub-2, 681,821 bytes) with the coverage data contract"
  - "src/truthtrail/data/seed_domains.txt: 54-domain DRAFT allowlist"
affects: [03-02, 03-03, 03-04, 03-05, 03-06, 03-07, 03-08, 03-09, 03-10, 03-11, 03-12]

actuals:
  tokens: 93000
  tasks: 4
  commits: 8
plan_head_before: cf29c1f4a05c9b181ce97009748d21c54093cb8a
plan_head_after: 193daeaaf25a5791847bf34faad09e492f9f7527

tech-stack:
  added: ["websockets 17.2 (ephemeral uv install only; pyproject.toml and uv.lock untouched)"]
  patterns:
    - "one extraction pass shared by analyze, storage-probe and cut-fixture"
    - "deterministic cutter ordered by sha256, no random module; --check re-cut equals the committed bytes"
    - "front-matter gate script with an importable OD table mapping every owner option to parameter values"

key-files:
  created:
    - scripts/bluesky_spike.py
    - scripts/check_spike_ratified.py
    - scripts/spike_lib/__init__.py
    - scripts/spike_lib/selection.py
    - scripts/spike_lib/analysis.py
    - scripts/spike_lib/scrub.py
    - .planning/phases/03-real-propagation-data/03-SPIKE.md
    - .planning/phases/03-real-propagation-data/03-SPIKE-REPORT-TEMPLATE.md
    - src/truthtrail/data/seed_domains.txt
    - src/truthtrail/data/recorded/bluesky-2026-10-19.jsonl
    - src/truthtrail/data/recorded/bluesky-2026-10-19.samples.jsonl
    - src/truthtrail/data/recorded/bluesky-2026-10-19.manifest.json
    - tests/test_spike_analysis.py
    - tests/test_spike_tool.py
    - tests/test_spike_gate.py
    - tests/test_spike_template.py
    - tests/test_seed_domains.py
    - tests/test_recorded_fixture.py
  modified:
    - .gitignore

key-decisions:
  - "Recommended (PROVISIONAL, owner decides): OD-1 RT-2 14/90/7 together with TRACK_SAMPLE_PER_10K 625; OD-2 M1; OD-3 A with B off; via_uri true"
  - "TRACK_MAX_ACTIVE_ROOTS is recommended at 2,850, not 500: the 500 cap is a first-come window bias (fills in 47 minutes, 1.6 percent of eligible roots)"
  - "Hex runs of 32 or more characters in scrubbed URL paths are mapped to letters g to v (bijective) so the fixture holds no key-lookalike"
  - "scrub-2 (verification fix round): only allowlisted publisher URLs keep a path; every other URL is a numbered .invalid placeholder per distinct URL; adult-labelled frames are dropped"
  - "The gate enforces explicit owner tokens (pseudonym=d17, dependencies=approved, via_uri=<value>), override types and ranges, and the storage coupling of sampling, retention, cap and budget"

requirements-completed: []

duration: "about 6.5 hours wall clock (three recording windows, one usage-limit pause)"
completed: 2026-10-19
status: complete
---

# Phase 3 Plan 1: Source Spike Summary

**A bounded read-only tool recorded 7,259.5 s of the live public Bluesky Jetstream v2 in three windows, the measured numbers and three framed OWNER DECISIONS are in 03-SPIKE.md, a real 687 KB scrubbed fixture is committed, and the plan now waits at the blocking owner checkpoint (Task 5): `ratified` is false and no agent ratified anything.**

DATA-01 stays open (`requirements-completed` is empty) until the owner ratifies 03-SPIKE.md.

## Commits (plan_head_before cf29c1f)

| Task | Commit | Message |
|---|---|---|
| 1 | a2f2481 | feat(03-01): pure spike libraries (selection, analysis, scrubber and cutter) |
| 2 | b0c29c3 | feat(03-01): bounded read-only Bluesky spike CLI |
| 3 | 3d41049 | docs(03-01): spike report template, decision-document scaffold and ratification gate script |
| fix | c6fe9be | fix(03-01): read truncated raw logs and keep the active account status in the scrubber |
| fix | d145e40 | fix(03-01): map long hex runs in scrubbed URL paths |
| fix | 8e37d75 | test(03-01): build the long hex id at run time instead of a literal |
| 4 | 68a96ef | docs(03-01): run the source spike and record the measurements |
| 4 | 193daea | test(03-01): add the recorded real-data fixture and its contract tests |

## Windows run (live, inside this container, host jetstream.us-east.bsky.network, v2, tool sha c6fe9be at the end of the windows)

| Window | Bounds | UTC start - end | Stop reason | Measured stream span | Frames | Raw log sha256 |
|---|---|---|---|---|---|---|
| w1 | 3660 s, 800,000,000 B | 2026-10-19 07:41:47 - 08:42:47 | seconds | 3,659.4 s | 207,687 | 0729f7fb54615c8c0265f47819338450951df4d36fb02b7b1f68579a0db0adf0 |
| w2 | 1800 s, 400,000,000 B | 12:10:42 - 12:40:42 | seconds | 1,800.8 s | 190,019 | 1eff7899fa238df1eb7e6514c861e04e0a9ff27a51e79d34bc0ad9a4df7556e5 |
| w3 | 1800 s, 400,000,000 B | 13:27:07 - 13:57:07 | seconds | 1,799.3 s | 185,778 | 6365bdac31472a7e584f2ac6e4f94693994b8ec7ebdb56f288cb509ed0981d2c |

Total **7,259.5 s** (floor 3,600 s). 0 reconnects, 0 server closes, 0 ConsumerTooSlow. Raw logs deleted after the cut (hashes kept above and in 03-SPIKE.md); no postgres or recorder process left.

## Headline measurements (details and per-window tables in 03-SPIKE.md)

- Volume: 80.4 events/s mean (56.8 in the W1 morning, 103 to 106 in W2 and W3), 68.4 KB/s, frame P50/P95/P99 794/1,493/2,216 B; one 21,031-event burst in a single stream second (W2).
- Time: 0 stream-time inversions in 583,484 frames; child-before-parent NOT measured in the windows (analyzer defect, fixed in cf9a646; an independent live re-measure on 2026-11-05 found 0 of 1,545, 95% upper bound about 0.2%, different day); createdAt unreliable (0.41 percent more than 60 s in the future, 10.5 percent over an hour old).
- Yield with the 54-domain draft list: 1,277 eligible roots = 633 per hour (15,199 a day if the mean held); 500-root cap fills in 47 minutes (1.6 percent of eligible roots a day, first-come); P(any child within 15 min) 20.2 percent (n 734; an upper bound including self-replies, 44 percent of fixture replies are by the root author), 6-hour outcomes unmeasurable (windows at most 61 minutes); cascades small (median 0, P99 10, max 60).
- Edge semantics: repost `via` on 25.6 percent of reposts; card and facet links overlap only partly (union needed); 0 re-rooted children; 38.6 percent of roots share an article URL.
- Deletes: 1.3 percent of posts are deleted inside the window (a censored lower bound), 80 percent of deletes retract older posts; tracked roots deleted in-window 0.7 percent (n 9, median not reported); deletion-type account events about 190 an hour, sync 13.4 an hour.
- Cursor: timestamp cursors accepted to the 36.6 h floor, older ones clamped with `#info OutdatedCursor`, seq 1 gives HTTP 400 CursorTooOld; replay 7,900 to 8,500 events/s received (a receive-path lower bound: the reads hit the 100 MiB cap; the 2,126/s read ran out of backlog and is not a speed figure).
- Storage (throwaway PostgreSQL 16.15, fresh load into scratch tables; excludes bloat, WAL, via_uri and news headlines): events 364.0 B/row, cascades 233.2, claims 538.7, accounts 145.4; 1,426 B per root all-in (derived).
- AppView cross-check: no evidence of loss in a small sample (100 roots per window, about 79 percent childless, direct children only); fresh windows equal for 98 to 100 percent of hydrated roots, three shortfall cells of one root each (W2 replies, W2 reposts, W3 reposts); W1 stale.

## Recommended parameters (PROVISIONAL, all in 03-SPIKE.md with arithmetic)

TRACK_SAMPLE_PER_10K 625 (950 roots/day, 122 MB at 90 days = 41 percent of 300 MB; 1250 would be 81 percent and the gate now rejects it; headroom 1.47x to the 60 percent line, 1.97x to the 80 percent stop), TRACK_MAX_ACTIVE_ROOTS 2,850, RETENTION 14/90/7 (+30 news), STORE_MAX_EVENTS_TOTAL 300,000, INGEST_REWIND_SECONDS 30, CASCADE_MERGE_POLICY claim_group, TRACK_SEED_CLAIM_URL_MATCH false, TRACK_MAX_EVENTS_PER_CASCADE 5,000, ingest bounds unchanged. `recommended_options`: od1 RT-2, od2 M1, od3 A.

## Fixture

`src/truthtrail/data/recorded/bluesky-2026-10-19.{jsonl,samples.jsonl,manifest.json}`, 681,821 bytes of 1,500,000 after the scrub-2 pass (687,551 at the scrub-1 cut), `source_mode` recorded-real, scrubber scrub-2, cut at tool sha 8e37d757ddaa4f7fd32621110e8ee117d435449f (`--check` re-cut identical before the raw logs were deleted), then rewritten by `rescrub-fixture`. sha256 pinned in tests/test_recorded_fixture.py: jsonl 4ef9bd30a8d67a361488186822ad4193348f42f4fd3ddd483fd08c3dbe3ad91d, samples 59a2ab8c5054f46328d336136fbfb810fb0a8d1ae1e074d63ddcb1f370878015 (scrub-1: 6e39a1f9..., a0beaefb..., recorded in the manifest). Coverage: 149 tracked roots; children reply 245, quote 29, repost 382; 75/22/75 cascades with replies/quotes/reposts, 38 with depth-2 replies; 1 orphan reply; 5 post and 5 repost deletes of included records; accounts active 5, deactivated 5, deleted 5, takendown 5, throttled 2; 3 sync; 325 negative controls (adult-labelled 0: the 3 adult-labelled frames were dropped). Pinned gitleaks 8.30.1: no leaks in the directory.

## Verification

Full suite 714 passed, 10 xfailed, no XPASS (533 at start; +181); ruff check, ruff format --check, mypy and `mypy --strict scripts/spike_lib/selection.py` clean; tests/test_no_hardcoded_credentials.py passes; the gate script exits 1 on the committed document; zero fill-in markers remain in 03-SPIKE.md; the 32-hex scan of every commit is clean except the literal noted below.

## Deviations from Plan

**1. [Rule 1 - Bug] Plan test spec `bound_seconds >= stream_seconds` fails on real data.** W2's measured stream span is 1,800.8 s against a 1,800 s bound (the first frame's stream time leads the recorder's wall clock). `test_stream_span_floor` allows 5 s of tolerance. File: tests/test_recorded_fixture.py (193daea).

**2. [Rule 1 - Bug] First real cut contained key-lookalikes.** Real article paths carry 32-hex ids; `test_no_hex_run...` failed. The scrubber now maps hex runs of 32+ characters to letters g to v (d145e40) and the fixture was re-cut from the still-present raw logs. The commit d145e40 itself spelled one of those ids as a literal in a test (my pipe hid the pre-commit scan's failing exit); 8e37d75 replaces it with a run-time value. The literal (an article id, not key material) remains in the unpushed history of d145e40; no history was rewritten per the hard rule.

**3. [Rule 1 - Bug] Two analyzer/scrubber defects found by a trial on the first minutes of the real W1 log** (c6fe9be): a still-being-written (truncated) gzip log raised instead of being read to the cut and counted; an active account event (no status field) was scrubbed to `other`. Tests added.

**4. Sequencing.** Task 3 was written and committed while W1 was recording (the recorder code was not touched; scripts/bluesky_spike.py is unchanged since b0c29c3). Commit order is still task order.

**5. Schedule.** A usage-limit pause separated W1 (07:41 to 08:42) from W2 (12:10): the W1 to W2 gap is 3 h 28 min, so the W1 AppView check ran stale (reported as such); W2 to W3 gap 46 min 25 s. All windows fall on one Monday between 07:41 and 13:57 UTC (no US evening, night or weekend), recorded as a risk.

**6. Re-read of terms (corrected in the verification fix round).** The research quote "not metered" is verbatim on the Jetstream Replay page, section "Authentication and metering": "The live WebSocket needs no key and is not metered." (retrieved 2026-11-05); the first reading looked only at the Jetstream page and wrongly reported it as not found. The GNews terms carry "Last Updated: October 18, 2026" where the research reading recorded October 16, 2026; what changed between the two versions is unverified (the Free plan's non-commercial limit and the caching clause are in the current text). The GNews pricing and error-handling quotes were paraphrases and are now verbatim with a retrieval date. All in S-10.

**7. Recommendation differs from CONTEXT's premise.** RT-2's 90-day window at full yield needs about 1.95 GB; it fits only with sampling 625 per 10,000 and a cap of 2,850 active roots (not 500). The document says so and shows alternatives; the owner decides.

**8. Plan wording not followed literally.** `cut-fixture` writes to the package directory (not below spike-output) as Task 4 step 12 requires; its `--out` is limited to a directory named `recorded` or below spike-output. The throwaway storage measurement replicates the 2,151 recorded tracked rows 93 times with re-keyed identifiers (documented as a measurement device).

**9. Gate behaviour for `recommended-defaults` (listed in the verification fix round).** When an OD field is `recommended-defaults` and resolves to an option whose OD table entry sets a parameter (for example OD-3 B sets `TRACK_SEED_CLAIM_URL_MATCH` true), the option's overlay wins over a contradicting value in `recommended_parameters` instead of exiting 2; only the owner's explicit `ratified_parameters` are checked against the option. Pinned by `test_recommended_defaults_with_b_requires_matching_recommended_parameters`; the committed recommended values agree with their options, so this changes nothing today.

## Known Stubs

None. Every fixture frame is a real recorded frame; tests that need text, link-card titles or an adult-labelled post must build `constructed_*` frames (stated in the manifest section).

## Threat Flags

None beyond the plan's register (T-03-01 to T-03-08, T-03-SC all mitigated as specified).

## Open owner items (Task 5, blocking-human, no auto_select)

1. OD-1 retention (RT-1, RT-2, RT-3), 2. OD-2 merge (M0, M1, M2), 3. OD-3 tracking (A, B, C) with the sampling parameter and bounds, 4. `via_uri` hedge (recommend true), 5. dependency list approval (sqlalchemy 2.1.5, psycopg 3.3.6 binary, alembic 1.20.0, websockets 17.2 and four transitive packages), 6. the ONE-WAY D-17 scheme: confirm only with the token `pseudonym=d17`; items 4 and 5 likewise need the explicit tokens `via_uri=true` (or false) and `dependencies=approved` (a blanket `ratify recommended` keeps the gate closed; the missing-token follow-up is a reply of exactly `pseudonym=d17`, not yes or no). Review the draft allowlist (an editorial choice and disclosed bias). Non-blocking: a 5-minute run of the same tool on Windows, pasted into the S-12 block. Gate: `python scripts/check_spike_ratified.py --json` (exit 1 now). No plan 03-02+ work has been started.

## Verification fix round (2026-11-05)

Verifier findings fixed with new commits only (no rewrite, nothing pushed by the executor); the gate still exits 1 and nothing was ratified.

| Commit | What changed |
|---|---|
| dea4ad6 | **Fixture privacy (blocker).** `scrub.rescrub` (scrub-2), a pure host-aware URL pass wired into `cut()` and applied once to the committed fixture by the new `rescrub-fixture` subcommand: allowlisted publisher URLs keep their path with UUIDs and 20+ hex runs mapped to counters, gift links keep only the publisher and `/redeem/` paths are dropped; shorteners keep the host; every other URL (and always the Bluesky, Substack, note.com, Telegram, X/Twitter, Instagram, Facebook, TikTok, Linktree, Bandcamp and Blogspot hosts) becomes `https://nonlisted-<n>.invalid/`, numbered per distinct URL in first-seen order, one universe per file. The 3 adult-labelled frames are dropped (D-13). `compute_coverage` counts adult labels on every negative control whatever gate refused it first (3 before the drop, 0 after). Manifest: scrub-2, pre-pass sha256 of both files, pass counters, privacy notes (pseudonymised not anonymised; stratified, not for rates; the samples file; a removal-request contact at the repo issues page). Tests: re-pinned hashes, URL invariants, placeholder hosts, constructed negative controls (`alice.example` permalink and Substack `@` URL), fixed point, coverage. Tracked roots unchanged at 149. |
| cf9a646 | **Analyzer B1.** The S-4 pair counter keeps a per-window pending-target counter, so a child whose target arrives later is counted child-first; a constructed 3-frame log (reply and repost before the root) gives 2, and the test fails on the old code. |
| 84e4ce8 | Type annotations in the scrub-2 helpers (mypy on the touched scripts). |
| c278b6e | **03-SPIKE.md honesty and the gate.** Child-before-parent marked not measured with the independent 2026-11-05 re-measure (0 of 1,545); replay rates as receive-path lower bounds (2,126/s dropped); AppView claim softened (small sample, three shortfall cells, W1 stale); break-evens (event cap at 2.51 children per root, 60 percent line at 2.55, 80 percent stop at 4.48; headroom 1.47x and 1.97x) replace the false "1.5x still fits" sentence; allowlist yield in-sample and concentration (30.5 / 46.8 / 66.5 percent); verbatim dated quotes for the Replay "not metered" line, GNews pricing and error handling (403 ambiguous, classify by body; 250-character content; CORS localhost only), GNews terms date corrected; upper-bound labels for P(reply) and P(any child) (44 percent self-replies in the fixture); censored delete timing, 1.3 percent as a lower bound, n/a for n = 9 and 10 medians; ex-burst rates (W2 93.8/s, combined about 77.5/s); storage scope (fresh load only, excludes bloat, WAL, via_uri, about 10 MB of news); hourly job extrapolated; takendown counting conservative; per-option storage table; deterministic-encryption alternative in D-17; sibling share after sampling about 8 to 10 percent (estimate); redundant `factcheck.afp.com` noted; Risks for the budget source (Neon Free "1 GB/project", retrieved 2026-11-05; CONTEXT assumed 0.5 GB), bloat, `capacity_reached`, GNews limits, concentration; replan range "03-03 to 03-07, plus 03-02 (OD-3 C) and 03-10 (docs)". Gate: ratified overrides must be recommended keys of the same type and in range; front-matter `eligible_roots_per_day` 15199 and `bytes_per_root` 1426 with the storage coupling (at most 80 percent of `DB_BUDGET_BYTES`, warning above 60 percent; cap at least ceil(1.5 x TTL/24 x roots/day x sample/10000)); explicit `dependencies=approved` and `via_uri=<value>` tokens; reply templates use 312 and the coupled RT-1 pair 2500/11400 (162.6 MB); utf-8-sig, NaN/Infinity and unhashable values exit 2. |
| adb5521 | `.dockerignore` excludes `src/truthtrail/data/recorded` (no runtime module reads it today; a test ties the entry to that fact, so the 03-04 ReplaySource must remove it deliberately if it runs inside the image). |
| 8c7166e | Rewords one sentence of c278b6e that the pinned gitleaks read as a `generic-api-key` (a false positive on the reply-format sentence that put the word for the confirmations, a colon and the D-17 confirmation together). The working tree is clean, but the commit-range scan still flags c278b6e until it is rewritten or allowlisted (history is the lead's call). |

The scrub-1 fixture files remain in the branch history (193daea); removing them from history needs an explicit owner decision.

Verification after the round: full suite 762 passed, 10 xfailed, no XPASS (714 before the round; +48); ruff check, ruff format --check, mypy (src) and `mypy --strict scripts/spike_lib/selection.py` clean; `scripts/copy_guard.py` clean; tests/test_no_hardcoded_credentials.py passes; the 32-hex and old-key scan of every new commit's added lines is clean; `check_spike_ratified.py` exits 1 on the committed document. Pinned gitleaks 8.30.1: the working tree and the fixture directory are clean; the commit-range scan flags only the false positive in c278b6e described above. Privacy self-check over both fixture files (counts): Bluesky profile links 0, `bsky.social` hosts 0, Substack `@` URLs 0, note.com user paths 0, gift-article URLs 0, `/redeem/` paths 0, UUIDs 0, adult-labelled frames 0.

## Self-Check: PASSED

Files and commits listed above exist; the tree is clean after the summary commit; no background process is running.
