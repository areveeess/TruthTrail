# Roadmap: TruthTrail

## Overview

TruthTrail began as a hackathon prototype whose "risk" score is keyword matching and whose "spread" is a random generator. Milestone v1.0 "Lean MVP" rebuilds it into a credible, deployed portfolio piece in six horizontal layers. First the existing service is made honest and secret-free (Phase 1) and moved onto a tested, containerised, CI-guarded package (Phase 2). Then real Bluesky propagation data is collected and stored (Phase 3) and a calibrated text classifier is trained and measured against the old keyword rules (Phase 4); these two both depend only on Phase 2 and may run in parallel. A React dashboard surfaces both (Phase 5), and the milestone closes with a live demo, a clean-clone docker-compose path and an honest README (Phase 6). Results are always framed as "flag for human review", never truth detection. Milestone v2 "Showcase" items stay deferred in REQUIREMENTS.md and have no phases here.

## Milestones

- **v1.0 Lean MVP** - Phases 1-6 (in progress)

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Secure & Honest Foundation** - Secrets out of the repo, honest upstream errors, provenance flags, validated typed responses, and tests that pin current behaviour before any refactor (completed 2026-10-17)
- [ ] **Phase 2: Engineering Baseline** - `src/truthtrail` package, pinned dependencies, pytest + hypothesis, CI, Dockerfile, `/health` and `/ready`, CORS, rate limiting, caching, timeouts
- [ ] **Phase 3: Real Propagation Data** - Source spike, Postgres schema, bounded Bluesky Jetstream collector, enrich step, `/v1` read API and DB-served news context
- [ ] **Phase 4: Baseline Detection & Evaluation** - Dataset scripts and disjoint splits, evaluation harness with baseline 0, calibrated TF-IDF + LR, integrity checks, hash-verified model serving, model card
- [ ] **Phase 5: Dashboard** - React + TypeScript triage feed, cascade detail view, risk badge with abstain state, score-this-text playground, all failure states, generated API client
- [ ] **Phase 6: Deploy & Package v1** - Clean-clone docker compose, deployed live demo with seeded real cascades, README with results table, limitations and ethics

## Phase Details

### Phase 1: Secure & Honest Foundation

**Goal**: The existing service stops misleading its users: no secrets in the repo, upstream failures surface as honest errors, any demo data is explicitly labelled, input is validated, and the prototype's current behaviour is pinned by tests before anything is refactored.
**Depends on**: Nothing (first phase)
**Requirements**: FND-01, FND-02, FND-03, FND-04, FND-05, FND-06
**Success Criteria** (what must be TRUE):
  1. A clean checkout contains no credential values: the news API key, Bluesky app password and database URL are defined as environment-only settings documented in `.env.example`, a secret scan over the working tree passes, and starting the service without the news key reports an explicit configuration error instead of calling upstream with a placeholder.
  2. When the news API returns 401/403, times out, or fails in any other way, the API responds 502 or 503 with a machine-readable error body (code, message, upstream source) and never a fabricated article; a test proves that a GNews 401 returns 502, not 200.
  3. Every API response carries `synthetic`, `data_as_of` and `source_status`; with `DEMO_MODE` unset or false no fixture data can be served, and with `DEMO_MODE=true` any fixture response is flagged `synthetic: true` (both proven by tests).
  4. An empty, oversize or malformed query is rejected with 422, and `/openapi.json` shows a Pydantic response model for every endpoint (checked by a test that walks the schema).
  5. Characterization tests pinning current `/analyze` behaviour, known keyword defects included (e.g. "secure" matching "cure", "studies" matching "dies", "couple" matching "coup"), are committed before any behavioural change, and a CI check fails when README, API docs or UI copy contains banned phrases such as "detects the truth" or a "FAKE" verdict badge; the README now says "flag for human review".

**Plans**: 6/6 plans complete

Plans:
**Wave 1**
- [x] 01-01-PLAN.md — Wave 1: test harness, autouse network guard and characterization tests (defects as strict xfails), before any behavioural change (FND-05)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 01-02-PLAN.md — Wave 2: env-only settings, fail-fast startup, key out of source and into the X-Api-Key header, .env.example/.gitignore, credential backstop (FND-01)

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 01-03-PLAN.md — Wave 3 (after 01-02, parallel with 01-04): envelope/Problem models and the deterministic, labelled synthetic demo fixture (FND-03)
- [x] 01-04-PLAN.md — Wave 3 (parallel with 01-03): typed GNews errors, RFC 9457 problem+json for every error, 401 -> 502 test, 422 input validation (FND-02, FND-04)

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 01-05-PLAN.md — Wave 4: provenance envelope on /analyze, DEMO_MODE-only fixture, provenance on every response, typed OpenAPI contract (FND-03, FND-04)

**Wave 5** *(blocked on Wave 4 completion)*
- [x] 01-06-PLAN.md — Wave 5: honest README, copy guard, pinned fail-closed gitleaks scan, minimal CI workflow (FND-06, FND-01)

### Phase 2: Engineering Baseline

**Goal**: The service is a properly packaged, tested, containerised and CI-guarded FastAPI app, with a versioned `/v1` router mount point that Phases 3 and 4 can extend independently, so data and ML code land on a solid base.
**Depends on**: Phase 1
**Requirements**: ENG-01, ENG-02, ENG-03, ENG-04, ENG-05, ENG-06
**Success Criteria** (what must be TRUE):
  1. The code lives in a `src/truthtrail` package (api, services, schemas, core) that serves the same endpoints as before, the Phase 1 characterization tests still pass unchanged through the refactor, and `spread_simulator.py` and `users.py` are no longer reachable from any route or import.
  2. A fresh clone installs from the uv lockfile on Python 3.13 with training and serving dependency sets split, and GitHub Actions runs ruff, mypy, pytest, pip-audit and the secret scan on every push and is green on the phase's final commit.
  3. A pytest + hypothesis suite covers the API and reports coverage; property tests prove, for arbitrary generated cascades, that events come back ordered by `observed_at` and that a child is never earlier than its parent.
  4. `docker build` succeeds and the running container answers `/health` with 200, while `/ready` returns 503 whenever a registered dependency check fails (proved by a test with an injected failing check); the database check lands in Phase 3 and the model-artifact check in Phase 4.
  5. CORS accepts only configured origins, requests over the rate limit receive 429, repeated reads are served from a TTL cache, and outbound HTTP uses timeouts and bounded retries (each proven by a test, including a mocked slow or failing upstream that stops after the retry bound).

**Plans**: 1/12 plans executed

Plans:
**Wave 1**
- [x] 02-01-PLAN.md — Wave 1: standalone line-ending commit, frozen Phase 1 OpenAPI golden snapshot, hash pins for the files that move (ENG-01)

**Wave 2** *(blocked on Wave 1 completion)*
- [ ] 02-02-PLAN.md — Wave 2: pure git mv into src/truthtrail and legacy/, retarget imports and tests, root shim, legacy-unreachable proof (ENG-01)

**Wave 3** *(blocked on Wave 2 completion)*
- [ ] 02-03-PLAN.md — Wave 3: pyproject.toml, uv.lock on Python 3.13, serving/dev/train groups, CI copy-guard and tests on uv (ENG-02, ENG-04)

**Wave 4** *(blocked on Wave 3 completion)*
- [ ] 02-04-PLAN.md — Wave 4: ruff and mypy strict to green (mechanical format commit, hand fixes, types) (ENG-04)

**Wave 5** *(blocked on Wave 4 completion)*
- [ ] 02-05-PLAN.md — Wave 5: create_app() factory, BootSettings, configured-origin CORS, catch-all inside CORS, Problem.synthetic Literal[False] (ENG-06)

**Wave 6** *(blocked on Wave 5 completion)*
- [ ] 02-06-PLAN.md — Wave 6: /health and /ready with a fail-closed readiness registry (503 proved by an injected failing check) (ENG-05)

**Wave 7** *(blocked on Wave 6 completion)*
- [ ] 02-07-PLAN.md — Wave 7: per-IP rate limit and 429 problem+json, /v1 LimitedRouter mount with probe-route proof, trusted-proxy switch (ENG-06)

**Wave 8** *(blocked on Wave 7 completion)*
- [ ] 02-08-PLAN.md — Wave 8: TTL cache for /analyze with X-Cache, successes only, limit before cache (ENG-06)

**Wave 9** *(blocked on Wave 8 completion)*
- [ ] 02-09-PLAN.md — Wave 9: bounded retry loop with 8 s budget, injected clock tests, Retry-After 0 clamp (ENG-06)

**Wave 10** *(blocked on Wave 9 completion)*
- [ ] 02-10-PLAN.md — Wave 10: cascade invariants (order_events, validate_cascade), Hypothesis properties, fixture load gate (ENG-03)

**Wave 11** *(blocked on Wave 10 completion)*
- [ ] 02-11-PLAN.md — Wave 11: Dockerfile, .dockerignore, static container contract, installed-package smoke test (ENG-05)

**Wave 12** *(blocked on Wave 11 completion)*
- [ ] 02-12-PLAN.md — Wave 12: coverage gate, CI jobs lint/typecheck/audit/docker, README with Windows and uv setup, phase gate (ENG-02, ENG-03, ENG-04, ENG-05)

### Phase 3: Real Propagation Data

**Goal**: Real Bluesky propagation data is collected within stated bounds, stored in Postgres with honest edge semantics, and served by a typed read API; there are no fabricated users or events on the live path.
**Depends on**: Phase 2
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06
**Success Criteria** (what must be TRUE):
  1. The source spike is complete before any schema work: a written decision exists covering source terms, live-tail volume, measured cascade yield, edge semantics (replies and quotes versus reposts attached to the root), tracked-root selection policy and retention policy, and a recorded real-data fixture is in the repo.
  2. `alembic upgrade head` on an empty Postgres creates the accounts, claims, cascades and events tables with `observed_at`, `occurred_at`, `edge_kind`, `inferred` and `parent_uri`, and upgrade/downgrade runs in CI against a real Postgres.
  3. The bounded Jetstream collector stores events only for tracked roots; replaying the same input twice leaves identical row counts (idempotent upserts keyed on the `at://` URI), a run killed mid-stream resumes from its checkpoint without loss or duplicates (checkpoint after commit), and a delete event removes the content.
  4. The enrich step resolves parents and rolls up cascades, orphans are an explicit stored state with parents never invented, and a property test shows that shuffled arrival order of the same events yields identical state.
  5. The `/v1` API serves cascade trees, timelines and stats from the database with "observed since" and orphan counts, honours the Phase 1 provenance and error contract (a database outage returns 503 with the machine-readable body and `/ready` reports not ready), and news context for a bounded query set is refreshed by a job into the database; a test asserts that no request handler can trigger a news-API call.

**Plans**: TBD

### Phase 4: Baseline Detection & Evaluation

**Goal**: A calibrated text classifier exists whose measured performance against the old keyword rules is reproducible from scripts, and it is served from a hash-verified artifact that never silently falls back to keyword rules.
**Depends on**: Phase 2 (independent of Phase 3; the two may run in parallel)
**Requirements**: ML-01, ML-02, ML-03, ML-04, ML-05, ML-06
**Success Criteria** (what must be TRUE):
  1. Running the documented scripts from a clean environment downloads LIAR and PHEME at pinned revisions (nothing committed), de-duplicates them and produces group/event-disjoint train, calibration and test splits, and a test asserts zero duplicate or group/event overlap across splits.
  2. The evaluation harness reports macro-F1, PR-AUC, Brier and ECE with bootstrap confidence intervals for a majority baseline and for "baseline 0" (the old keyword rules, both as shipped and word-boundary-fixed), and the ECE helper has its own unit tests.
  3. The TF-IDF + logistic-regression model is calibrated on the held-out calibration split only and returns a score band, an abstain state and top-token explanations for each prediction; its test-set metrics are reported against both baselines with confidence intervals, whichever way the comparison falls.
  4. Integrity checks run and are recorded in `metrics.json`: source-only and shuffled-label canaries (the shuffled-label canary scores near chance), entity slices, a name-swap test and an out-of-domain probe set with its own false-flag row; the README results table is generated from `metrics.json` and a check fails if it drifts.
  5. The model artifact is hash-verified against `manifest.json` (sha256, calibration, thresholds, metrics) at startup, a tampered or missing artifact makes `/ready` return 503 (completing the model check deferred from Phase 2), `POST /v1/score` returns a band and abstain flag for pasted text, and a model card documents training data, metrics, limits and the LIAR/PHEME-to-Bluesky domain shift.

**Plans**: TBD

### Phase 5: Dashboard

**Goal**: A reviewer can open the dashboard, scan a triage feed of tracked cascades, drill into one, and score pasted text, with every failure and staleness state handled honestly.
**Depends on**: Phase 3, Phase 4
**Requirements**: UI-01, UI-02, UI-03, UI-04, UI-05
**Success Criteria** (what must be TRUE):
  1. Opening the app shows a triage feed of tracked cascades ranked by risk x velocity, each row showing its risk badge and "observed since" time.
  2. Selecting a cascade shows the tree graph (labelled "showing N of M" when capped), a timeline, stats including orphan counts, and an edge legend in which inferred edges are visually distinct from observed ones.
  3. The risk badge always shows a calibrated band or the abstain state, never a bare verdict or bare percentage, and the "score this text" playground submits to `/v1/score` and displays the band or abstain state with top tokens, using "flag for human review" wording.
  4. Loading, error, empty, stale-data and "server waking up" states each render (reproducible by stopping the API, emptying the database or delaying the first response), data the API marks `synthetic: true` is visibly labelled, and the layout is responsive, keyboard-navigable from feed to detail, and passes an automated contrast and accessibility check.
  5. The frontend uses a client generated from the OpenAPI schema, and CI fails when the generated file is out of date (demonstrated by changing a response field without regenerating).

**Plans**: TBD
**UI hint**: yes

### Phase 6: Deploy & Package v1

**Goal**: A stranger can run TruthTrail from a clean clone or open the live demo, and can read an honest README that states what the results do and do not show.
**Depends on**: Phase 5
**Requirements**: OPS-01, OPS-02, DOC-01, DOC-02
**Success Criteria** (what must be TRUE):
  1. `docker compose up` from a clean clone brings up api, db and web with migrations applied, and a scripted acceptance test passes (`/health` and `/ready` return 200, the dashboard loads and shows data).
  2. A live demo URL serves the dashboard from a single image with managed Postgres, seeded with real cascades; a scheduled collector job refreshes the data within its bounds, a periodic health check reports when the demo is down, and the Bluesky terms were re-read and the result recorded in the Phase 3 decision document before the URL was made public.
  3. The README contains the problem statement, architecture diagram, setup instructions, demo GIF or video, live link, and a results table that matches `metrics.json`.
  4. A limitations and ethics section covers domain shift, the repost-star caveat, no truth adjudication, pseudonymized accounts and honoured deletions, and the copy guard from Phase 1 passes on the final README.

**Plans**: TBD

## Cross-Phase Notes

**Execution order:** 1 -> 2 -> (3 and 4, parallelisable) -> 5 -> 6. Phase 5 needs both 3 and 4 because it renders cascades and scores.

**Gating decisions inside phases (not extra phases):**
- Phase 3: the source spike (DATA-01) gates the schema migration (DATA-02). Decide `edge_kind` / `inferred` semantics (repost-star caveat) and the tracked-root seed filter before the migration. Owner decisions needed: retention policy for stored text, and whether to merge cascades when a provisional root resolves later. Persist `observed_at` and `occurred_at` separately and keep the `features(events, t0, horizon)` interface in mind for v2.
- Phase 4: the evaluation harness and baseline 0 (ML-02) precede any model (ML-03). Calibration uses the calibration split only.
- Phase 3 and Phase 4 both add routes under the `/v1` mount point created in Phase 2.

**Cross-cutting contracts:** The error contract (FND-02) and provenance fields (FND-03) are established in Phase 1 and must hold for every endpoint added later; Phases 3 and 4 criteria verify this for their endpoints. `/ready` (ENG-05) is built in Phase 2 with a pluggable dependency check; the database check arrives in Phase 3 and the model-artifact check in Phase 4. The README results table is generated from `metrics.json` in Phase 4 and verified as part of the final README in Phase 6.

**Open scoping question for Phase 3 planning:** DATA-06 forbids proxying arbitrary user queries to the news API, so the legacy query-driven `/analyze` must be retired or reduced to serving stored news context; its Phase 1 characterization tests are then retired deliberately, not silently.

**Research flags:** Phase 3 (deep research: Bluesky terms and data-use, live-tail volume, cascade yield, record shapes, retention, dataset audit) and Phase 6 (Render RAM and cold start, Neon pooler with psycopg, scheduled-job behaviour). Moderate: Phase 4 calibration with small validation sets and abstain thresholds; Phase 5 large-tree strategy and accessibility. Phases 1 and 2 are standard patterns.

**Known operational risk:** GitHub Actions scheduled workflows are disabled after 60 days of repository inactivity, which affects the Phase 6 collector and health-check jobs.

**Out of this roadmap:** v2 "Showcase" items (ML2-01, ML2-02, SIM-01, SIM-02, DATA2-01, FEAT2-01, OPS2-01, DOC2-01) and any purge of the old GNews key from git history, which is not part of any phase unless the owner explicitly asks.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 (Phases 3 and 4 may run in parallel)

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Secure & Honest Foundation | 6/6 | Complete    | 2026-10-17 |
| 2. Engineering Baseline | 1/12 | In Progress | - |
| 3. Real Propagation Data | 0/TBD | Not started | - |
| 4. Baseline Detection & Evaluation | 0/TBD | Not started | - |
| 5. Dashboard | 0/TBD | Not started | - |
| 6. Deploy & Package v1 | 0/TBD | Not started | - |
