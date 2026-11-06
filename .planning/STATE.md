---
gsd_state_version: "1.0"
milestone: v1.0
current_phase: 3
current_phase_name: Real Propagation Data
current_plan: 03-08 (next); 03-01 to 03-07 complete
status: executing
stopped_at: Completed 03-07-PLAN.md
last_updated: "2026-11-06T20:05:29.509Z"
last_activity: 2026-11-06
last_activity_desc: Plan 03-07 executed (/v1 read API - cascades list with keyset cursor, detail, capped canonical tree, date_bin timeline, rollup-only stats; V1Meta provenance; 503 database_unavailable/database_timeout contract with outage proof)
state_head: efaea2061eec6de3392be0a297571e10b97f09b9
progress:
  total_phases: 7
  completed_phases: 2
  total_plans: 30
  completed_plans: 25
milestone_name: Lean MVP
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-10-11)

**Core value:** Every risk score and every cascade the system shows is backed by real data and a measured, reproducible evaluation. Nothing fabricated is ever presented as analysis.
**Current focus:** Phase 01 — Secure & Honest Foundation

## Current Position

Phase: 3 — Real Propagation Data
Current Plan: 8
Total Plans in Phase: 12
Status: 03-01 to 03-07 complete; executing 03-08 next
Last activity: 2026-11-06 — plan 03-07 executed (the /v1 read API and the database error contract; DATA-05 complete)

Progress: [███░░░░░░░] 33%

## Performance Metrics

**Velocity:**
- Total plans completed: 18
- Average duration: - min
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 6 | - | - |
| 2 | 12 | - | - |

**Recent Trend:**
- Last 5 plans: none yet
- Trend: n/a

*Updated after each plan completion*
**Per-Plan Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 01 P01 | 4 min | 3 tasks | 8 files |
| Phase 01 P02 | 5 min | 3 tasks | 8 files |
| Phase 01 P03 | 6 min | 3 tasks | 5 files |
| Phase 01 P04 | 3 min | 3 tasks | 6 files |
| Phase 01 P05 | 9min | 3 tasks | 5 files |
| Phase 01 P06 | 6 min | 3 tasks | 8 files |
| Phase 02 P01 | 15 min | 3 tasks | 14 files |
| Phase 2 P02 | 30min | 3 tasks | 28 files |
| Phase 2 P03 | 25min | 2 tasks | 11 files |
| Phase 2 P04 | 20min | 3 tasks | 36 files |
| Phase 02 P05 | 25min | 2 tasks | 14 files |
| Phase 02 P06 | 15min | 2 tasks | 7 files |
| Phase 02 P07 | 30min | 2 tasks | 15 files |
| Phase 02 P08 | 10min | 2 tasks | 6 files |
| Phase 02 P09 | 15min | 2 tasks | 5 files |
| Phase 02 P10 | 20min | 2 tasks | 6 files |
| Phase 02 P11 | 15min | 2 tasks | 4 files |
| Phase 02 P12 | 25min | 3 tasks | 7 files |
| Phase 03 P02 | 22min | 3 tasks | 22 files |
| Phase 03 P03 | 34min | 3 tasks | 22 files |
| Phase 03 P04 | 27min | 4 tasks | 23 files |
| Phase 03 P05 | 95min | 3 tasks | 20 files |
| Phase 03 P06 | 28min | 3 tasks | 16 files |
| Phase 03 P07 | 30min | 3 tasks | 22 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: Six horizontal-layer phases (foundation, engineering, data, detection, dashboard, deploy); research confirmed, no phases added
- [Roadmap]: Phases 3 and 4 both depend only on Phase 2 and may run in parallel; Phase 5 needs both
- [Roadmap]: Bluesky Jetstream v2 is the propagation source (confirm in the Phase 3 spike); primary UX is a triage feed plus a "score this text" playground, not query-driven `/analyze`
- [Roadmap]: v2 "Showcase" items stay deferred with no phases; git-history purge of the rotated GNews key is not in any phase
- [Phase 01]: Test client backend is httpx 0.28.1 (D-18); filterwarnings=error with one message-regex ignore for Starlette's httpx deprecation
- [Phase 01]: Runtime pins committed last in 01-01 after 48 per-test outcomes matched under unpinned and pinned runtimes
- [Phase 01]: client_factory monkeypatches the fetcher key constant to FAKE_TEST_KEY; plan 01-02 removes that line with the constant
- [Phase 01]: 01-02: rewrote gnews_fetcher.py without reading it so the rotated key never entered tool output; key stays in history at 1fedcd2 (D-11)
- [Phase 01]: 01-02: settings are lazy and cached (get_settings); ConfigurationError is built from loc and msg only and raised from None; app lifespan calls get_settings for fail-fast (uvicorn exit 3)
- [Phase 01]: 01-03: Problem.source_status is a plain str (error states are outside Meta's Literal) and Problem.data_as_of is typed None
- [Phase 01]: 01-03: Demo fixture timestamps re-based by _monotone_utc (child = parent's new time + original offset), simulator untouched
- [Phase 01]: 403 maps to 502 upstream_forbidden (distinct code, detail names credentials, subscription or daily quota); an empty result is valid only when totalArticles is 0 (D-19)
- [Phase 01]: Retry-After honoured only for all-digit values capped at 3600, else 30; request-time ConfigurationError answered 500 not_configured; SearchQuery trims, caps at 200 characters and rejects control characters
- [Phase 01]: 01-05: article timestamp key is published_at and the response is the {results, meta} envelope (D-01 breaking change; no in-repo consumer)
- [Phase 01]: 01-05: declared OpenAPI errors list only application/problem+json; demo mode ignores the validated query
- [Phase 01]: 01-06: gitleaks range scan bounded with ^FLOOR in addition to the floor clamp so pre-floor history is never scanned (plan-check cap fix)
- [Phase 01]: 01-06: copy guard skips OpenAPI identifier keys only for string leaves so a property named type cannot hide its description
- [Phase 02]: 02-01: ENG-01 stays Pending until plan 02-02 performs the package move; 02-01 only freezes line endings, the Phase 1 OpenAPI golden snapshot and content hashes
- [Phase 02]: 02-01: byte-identical for legacy files means identical after CR+LF to LF; Phase 1 raw git diff gate now returns 1 by design, replaced by --ignore-cr-at-eol
- [Phase 02]: 02-05: Generic Exception handler removed; CatchAllMiddleware inside CORS renders the identical 500 problem+json so error responses carry CORS headers
- [Phase 02]: 02-05: CORS_ORIGINS must be exact scheme://host[:port]; unset means no cross-origin access; invalid value fails create_app() with a ConfigurationError that omits the value
- [Phase 02]: 02-06: /ready names only failed check names in the problem detail and sends no Retry-After; registry on app.state.readiness with register_default_checks hook
- [Phase 02]: 02-07: slowapi used through decorators only; LimitedRouter makes /v1 limits fail closed; server always started with --no-proxy-headers so TRUST_PROXY_HEADERS/FORWARDED_ALLOW_IPS are the only proxy-trust switches (real-uvicorn negative control proves the default hole)
- [Phase 02]: 02-08: /analyze TTL cache (600 s, 256 entries, key = trimmed casefolded query + demo flag) on app.state.analyze_cache; every access locked, fetch outside the lock, successes only, X-Cache hit/miss undocumented in OpenAPI, limit applies before the cache
- [Phase 02]: 02-09: explicit retry loop in services/gnews.py (3 attempts, 0.3/0.6 s backoff plus jitter, 8 s budget, only timeouts, non-TLS connect errors and 500/502/503/504); time seams _monotonic/_sleep/_jitter patched by tests, autouse no_real_sleep fixture; provider Retry-After clamped to 1..3600; ENG-06 complete
- [Phase 02]: 02-10: cascade invariants are pure stdlib functions in core/cascade.py (order_events key observed_at, depth, event_id; validate_cascade rejects duplicates, naive datetimes, cycles, parent later than child, tolerates orphans); load_demo_fixture validates every result and the lifespan loads the fixture in demo mode, but the served body is never reordered (D-19); Hypothesis ci/dev profiles; ENG-03 complete
- [Phase 02]: 02-11: Dockerfile is multi-stage with python:3.13-slim and uv 0.13.1 pinned by tag and digest (re-verified against the registries), uid 10001, urllib HEALTHCHECK, CMD with --no-proxy-headers; properties enforced by tests/test_container_files.py; scripts/smoke_app.py proves a non-editable no-dev install serves health, ready and demo analyze; docker build unverified (no daemon), ENG-05 stays Pending until plan 02-12
- [Phase 02]: 02-12: coverage gate fail_under = 96 (measured 98.342 minus 2, not in addopts); ci.yml now has seven jobs (lint, typecheck, audit, docker added; gitleaks untouched); README rewritten for the packaged service; local phase gate green and 02-VALIDATION flipped to validated; ENG-04 and ENG-05 stay Pending and ROADMAP criteria 2 and 4 stay pending human confirmation (no Actions run, no docker daemon)
- [Phase 03]: 03-02: Policy defaults are literals in core/policy.py proven equal to the ratified 03-SPIKE.md by tests that read the gate's effective_parameters; TRACK_ALLOWLIST_FILE compared package-relative (ratified value is repo-relative)
- [Phase 03]: 03-02: psycopg[binary] 3.3.6 without the pool extra (F-12), a documented deviation from D-19; eight packages added to uv.lock, none changed
- [Phase 03]: 03-02: Database tests use @pytest.mark.requires_db against a real PostgreSQL (TEST_DATABASE_URL, else a non-root throwaway cluster via runuser); a database fixture without the marker is a usage error; REQUIRE_DB_FLOOR fails runs below the floor
- [Phase 03]: 03-02: create_db_engine is the only engine builder (pool 5+5, pool_timeout 2 s, connect 3 s, statement 5 s api / 30 s collector and jobs, lock 2 s, SET TIME ZONE UTC on connect); URL options are kept
- [Phase 3]: 03-03: The D-20 schema is declarative models (single source of truth) with the edge, orphan, tombstone and minimisation invariants as named CHECKs; key widths follow d17-hmac-v1 (URI 20, pseudonym 16, digests 26); events.via_uri present
- [Phase 3]: 03-03: Migrations ship in src/truthtrail/db/migrations (baseline 0001); the URL never reaches the ini or set_main_option; python -m truthtrail.db migrate|check|heads exits 0/1/3/5 with no URL in output
- [Phase 3]: 03-03: /ready registers database for an injected engine or DATABASE_URL without DEMO_MODE; the check reads app.state.engine lazily and fails closed; the lifespan owns and disposes only the engine it builds
- [Phase 3]: 03-03: CI tests job uses postgres:17.11-bookworm@sha256:665dc7b3... (re-resolved; tag moved since planning), REQUIRE_DB=1, REQUIRE_DB_FLOOR=65 and the four-step Alembic CLI round trip
- [Phase 03]: 03-04: A quote of a non-post target is a root candidate (derive_edge, the function that measured the ratified yield), not Dropped(bad_edge); a repost of a non-post target and a reply with both references unusable are bad_edge
- [Phase 03]: 03-04: Production seed path is seed_decision_for(NormalizedEvent.seed_candidate()); seed_decision(record, ...) keeps its signature and delegates, so both paths are one implementation (plan 03-05 Decider uses the candidate path)
- [Phase 03]: 03-04: Sources never yield Dropped results; drops go to the caller's DropCounter by reason
- [Phase 03]: 03-04: The recorded fixture now ships in the image (.dockerignore line removed) because ReplaySource is runtime code that reads it; ReplaySource hashes the data once and iterates those bytes
- [Phase 03]: 03-04: find_order_violations leaves out events on a parent cycle; the Keyer holds the HMAC key schedule, not the raw secret; FAKE_PSEUDONYM_SECRET is runtime-generated per session
- [Phase 03]: 03-05: account-wide tombstones remove only rows observed at or before the action's stream time (replay idempotency)
- [Phase 03]: 03-05: overflow tallied by cascades.overflow_through_us high-water mark; out-of-order overflow counted as overflow_uncounted (lower bound)
- [Phase 03]: 03-05: CLI exit codes 0/2/3/4/5/6; stop reason stored as counter stop:<reason>; run_ingest catches KeyboardInterrupt and finalises as interrupted
- [Phase 03]: 03-05: CI REQUIRE_DB_FLOOR raised 65 -> 174
- [Phase 03]: 03-05: a reply without a usable parent is refused as reply_without_parent (no invented edge)
- [Phase 03]: 03-06: the collector's dirty mark is unconditional (mark_cascades_dirty); the old enrich_dirty IS FALSE filter lost the mark during an enrich transaction
- [Phase 03]: 03-06: enrich locks changed event rows NOWAIT, so an open collector batch is contention (cascade stays dirty), never a deadlock
- [Phase 03]: 03-06: enrich as_of defaults to the checkpoint stream time (data_as_of); purge CLI as_of defaults to the wall clock (retention is real time)
- [Phase 03]: 03-06: counters exclude tombstones, structure and max_depth keep them; invalid_count only in the result and log line; ROLLUP_VERSION 1
- [Phase 03]: 03-06: CI REQUIRE_DB_FLOOR raised 174 -> 217
- [Phase 3]: 03-07: /v1 handlers open the read-only connection inside the body (read_connection), after the limiter; a 429 never takes a pool connection
- [Phase 3]: 03-07: parameter 422s are rejected before the limiter (uncounted, no database); handler-level 422s (claim_id under merge policy none, cursor of another sort) are counted
- [Phase 3]: 03-07: cursor = base64url JSON [sort, value, id]; tree node ids are events.id (no keyed URI exposed); unknown cascade id is the generic undeclared 404
- [Phase 3]: 03-07: ingest_gaps counts gaps overlapping [first_event_at, max(last_event_at, tracking_ends_at)]; stats events_by_kind.root = non-deleted roots
- [Phase 3]: 03-07: CI REQUIRE_DB_FLOOR raised 217 -> 311

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 3]: Bluesky data-use terms, live-tail cascade yield and repost/quote record shapes are unverified; the DATA-01 spike must settle them before the schema migration
- [Phase 3]: Owner decisions needed on retention policy for stored text and on merging cascades when a provisional root resolves later
- [Phase 3]: The fate of the legacy query-driven `/analyze` (retire or serve stored news context) must be settled to satisfy DATA-06
- [Phase 6]: Render RAM and cold start, and Neon pooler behaviour with psycopg, are untested; GitHub Actions scheduled jobs are disabled after 60 days of repo inactivity
- [Phase 3]: RESOLVED 2026-11-06: certifi bumped 2026.7.22 -> 2026.10.23 (PYSEC-2026-4320); pip-audit clean

## Deferred Items

Items acknowledged and deferred at milestone close, most recent first:

| Category | Item | Status | Deferred At | Milestone |
|----------|------|--------|-------------|-----------|
| *(none)* | | | | |

## Session Continuity

Last session: 2026-11-06T20:05:29.406Z
Stopped at: Completed 03-07-PLAN.md
Resume file: None

See `.planning/HANDOFF.md` for the full session handoff (constraints, workflow pattern, Phase 2 notes).
