---
gsd_state_version: "1.0"
milestone: v1.0
current_phase: 3
current_phase_name: Real Propagation Data
current_plan: Not started
status: ready_to_execute
stopped_at: Phase 3 planned (12 plans, plan checker passed); executing plan 03-01 (source spike) then owner gate
last_updated: "2026-10-18T12:36:49.966Z"
last_activity: 2026-10-18
last_activity_desc: Phase 3 plans verified by plan checker; starting spike
state_head: 7ce8bf637af0a3a203fe2210861a8f43eb77a906
progress:
  total_phases: 6
  completed_phases: 2
  total_plans: 18
  completed_plans: 18
  percent: 33
milestone_name: Lean MVP
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-10-11)

**Core value:** Every risk score and every cascade the system shows is backed by real data and a measured, reproducible evaluation. Nothing fabricated is ever presented as analysis.
**Current focus:** Phase 01 — Secure & Honest Foundation

## Current Position

Phase: 3 — Real Propagation Data
Current Plan: Not started
Total Plans in Phase: 12
Status: Ready to plan
Last activity: 2026-10-18 — Phase 2 complete, transitioned to Phase 3

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

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 3]: Bluesky data-use terms, live-tail cascade yield and repost/quote record shapes are unverified; the DATA-01 spike must settle them before the schema migration
- [Phase 3]: Owner decisions needed on retention policy for stored text and on merging cascades when a provisional root resolves later
- [Phase 3]: The fate of the legacy query-driven `/analyze` (retire or serve stored news context) must be settled to satisfy DATA-06
- [Phase 6]: Render RAM and cold start, and Neon pooler behaviour with psycopg, are untested; GitHub Actions scheduled jobs are disabled after 60 days of repo inactivity

## Deferred Items

Items acknowledged and deferred at milestone close, most recent first:

| Category | Item | Status | Deferred At | Milestone |
|----------|------|--------|-------------|-----------|
| *(none)* | | | | |

## Session Continuity

Last session: 2026-10-18T06:51:38.196Z
Stopped at: Phase 2 complete, ready to plan Phase 3
Resume file: None

See `.planning/HANDOFF.md` for the full session handoff (constraints, workflow pattern, Phase 2 notes).
