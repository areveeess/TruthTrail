# Requirements: TruthTrail

**Defined:** 2026-10-11
**Core Value:** Every risk score and every cascade the system shows is backed by real data and a measured, reproducible evaluation. Nothing fabricated is ever presented as analysis.

## v1 Requirements (Milestone: Lean MVP)

Requirements for the first shippable portfolio release. Each maps to a roadmap phase.

### Foundation (FND)

- [x] **FND-01**: All credentials (news API key, Bluesky app password, database URL) are read from environment variables; `.env.example` documents them and no secret exists in the repository tree
- [x] **FND-02**: When an upstream dependency (news API, Bluesky, database) fails, the API returns 502/503 with a machine-readable error body and never a fabricated 200 response *(Phase 1 covers the news API; the Bluesky and database failure paths are verified in Phase 3, SC5.)*
- [x] **FND-03**: Every API response carries provenance fields (`synthetic`, `data_as_of`, `source_status`); fixture or demo data is served only when `DEMO_MODE=true` (default false) and is always flagged `synthetic: true`
- [x] **FND-04**: Invalid or oversize input is rejected with 422, and every endpoint has a Pydantic response model visible in the OpenAPI schema
- [x] **FND-05**: Characterization tests pin the current `/analyze` behaviour, known keyword defects included, before any refactor
- [x] **FND-06**: User-facing copy (README, API docs, UI) says "flag for human review"; CI fails if banned phrases ("detects the truth", a "FAKE" verdict badge) appear

### Engineering (ENG)

- [x] **ENG-01**: Code lives in a `src/truthtrail` package (api, services, schemas, core); the legacy `spread_simulator.py` and `users.py` are removed from the live path
- [x] **ENG-02**: Dependencies are pinned with a uv lockfile on Python 3.13, with training and serving requirements split
- [x] **ENG-03**: A pytest + hypothesis suite covers the API and the invariants (events ordered by `observed_at`; a child is never earlier than its parent), with coverage reported
- [ ] **ENG-04**: GitHub Actions CI runs ruff, mypy, pytest, pip-audit and a secret scan on every push
- [ ] **ENG-05**: A Dockerfile builds and runs the service; `/health` reports liveness and `/ready` returns 503 when the model artifact or database is unavailable
- [x] **ENG-06**: CORS is restricted to configured origins, routes are rate limited, repeated reads are TTL-cached, and outbound HTTP uses timeouts and bounded retries

### Data (DATA)

- [ ] **DATA-01**: A source spike produces a written decision covering source terms, live-tail volume, cascade yield, edge semantics, tracked-root selection policy and retention policy, plus a recorded real-data fixture
- [ ] **DATA-02**: A Postgres schema with Alembic migrations stores accounts, claims, cascades and events, including `observed_at`, `occurred_at`, `edge_kind`, `inferred` and `parent_uri`
- [ ] **DATA-03**: A bounded Bluesky Jetstream v2 collector ingests tracked roots with idempotent upserts keyed on the `at://` URI, checkpoints after commit, and honours deletes
- [ ] **DATA-04**: An enrich step resolves parents and rolls up cascades; orphans are an explicit state; a property test shows shuffled arrival order yields identical state
- [ ] **DATA-05**: A `/v1` read API serves cascade trees, timelines and stats with "observed since" and orphan counts
- [ ] **DATA-06**: News context is refreshed for a bounded query set by a scheduled job and served from the database; the public API never proxies arbitrary user queries to the news API

### Detection (ML)

- [ ] **ML-01**: Scripts download LIAR and PHEME at pinned revisions (nothing committed), de-duplicate, and produce group/event-disjoint train / calibration / test splits
- [ ] **ML-02**: An evaluation harness reports macro-F1, PR-AUC, Brier/ECE and bootstrap confidence intervals, with a majority baseline and "baseline 0" (the old keyword rules, as shipped and word-boundary-fixed)
- [ ] **ML-03**: A TF-IDF + logistic-regression classifier is calibrated on held-out data and exposes a score band, an abstain state and a per-prediction top-token explanation
- [ ] **ML-04**: Integrity checks run and are reported: source-only and shuffled-label canaries, entity slices, a name-swap test and an out-of-domain probe set; results are written to `metrics.json` and the README table is generated from it
- [ ] **ML-05**: A hash-verified model artifact with `manifest.json` (sha256, calibration, thresholds, metrics) is loaded at startup, and `POST /v1/score` returns a band and abstain flag for pasted text
- [ ] **ML-06**: A model card documents training data, metrics, limits and the LIAR/PHEME-to-Bluesky domain shift

### Dashboard (UI)

- [ ] **UI-01**: A triage feed lists tracked cascades ranked by risk × velocity
- [ ] **UI-02**: A cascade detail view shows the tree graph (labelled "showing N of M" when capped), a timeline, stats, and an edge legend with inferred edges visually distinct
- [ ] **UI-03**: The risk badge shows a calibrated band or the abstain state, never a bare verdict, and a "score this text" playground uses `/v1/score`
- [ ] **UI-04**: Loading, error, empty, stale-data and "server waking up" states exist, and the layout is responsive with keyboard access and sufficient contrast
- [ ] **UI-05**: The frontend uses a client generated from the OpenAPI schema, and CI fails if the generated file is out of date

### Operations (OPS)

- [ ] **OPS-01**: `docker compose up` runs api + db + web from a clean clone, verified by an acceptance test
- [ ] **OPS-02**: A live demo is deployed (single image, managed Postgres, scheduled collector job) seeded with real cascades, with a periodic health check

### Documentation (DOC)

- [ ] **DOC-01**: The README has the problem statement, architecture diagram, setup, demo GIF/video, live link and a results table generated from `metrics.json`
- [ ] **DOC-02**: A limitations and ethics section covers domain shift, the repost-star caveat, no truth adjudication, pseudonymized accounts, and honoured deletions

## v2 Requirements (Milestone: Showcase)

Deferred to the next milestone. Tracked but not in the current roadmap.

### Detection and simulation

- **ML2-01**: Cascade features via `features(events, t0, horizon)` and an early-detection curve on labelled cascade data (PHEME / Twitter15-16) against a volume-only baseline
- **ML2-02**: Offline transformer fine-tune behind the `Predictor` interface (ONNX), with an ablation of text vs cascade vs both
- **SIM-01**: A seeded cascade simulator fitted to real cascades, labelled illustrative/synthetic, with Monte Carlo bands (cut or label "unvalidated" if it cannot be validated)
- **SIM-02**: What-if interventions (label at time t, remove top-k spreaders, reduce transmission) as paired comparisons, with UI controls

### Platform and polish

- **DATA2-01**: Mastodon as a second source; Replay-based history if its quota and cost allow
- **FEAT2-01**: Google Fact Check lookup, per-domain credibility signal, cascade export, claim clustering
- **OPS2-01**: Structured logging, metrics endpoint, API-key auth, load test
- **DOC2-01**: Blog post, demo video, final model card

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Truth verdicts / "detects the truth" labels | Overclaims; flag for human review only |
| Per-user blacklists or bot scores | Ethics and accuracy risk; research flags as an anti-feature |
| LLM-as-judge verdicts on truth | Unvalidated and unreproducible |
| Synthetic data presented as analysis | Violates the Core Value |
| X/Twitter ingestion | Paid API; open sources and public datasets instead |
| Reposts drawn as an observed reshare tree | Platforms attribute reposts to the root; cascades are partly inferred |
| Non-English content | Datasets and prototype are English-only in v1 |
| User accounts and content moderation | Out of the product's remit; single-tenant demo |
| Committing model weights or datasets | Reproducible scripts and a model card instead |
| Real-time everything | Bounded batch collection fits free hosting |
| Mobile app | Web dashboard only |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FND-01 | Phase 1 | Complete |
| FND-02 | Phase 1 | Complete |
| FND-03 | Phase 1 | Complete |
| FND-04 | Phase 1 | Complete |
| FND-05 | Phase 1 | Complete |
| FND-06 | Phase 1 | Complete |
| ENG-01 | Phase 2 | Complete |
| ENG-02 | Phase 2 | Complete |
| ENG-03 | Phase 2 | Complete |
| ENG-04 | Phase 2 | Pending |
| ENG-05 | Phase 2 | Pending |
| ENG-06 | Phase 2 | Complete |
| DATA-01 | Phase 3 | Pending |
| DATA-02 | Phase 3 | Pending |
| DATA-03 | Phase 3 | Pending |
| DATA-04 | Phase 3 | Pending |
| DATA-05 | Phase 3 | Pending |
| DATA-06 | Phase 3 | Pending |
| ML-01 | Phase 4 | Pending |
| ML-02 | Phase 4 | Pending |
| ML-03 | Phase 4 | Pending |
| ML-04 | Phase 4 | Pending |
| ML-05 | Phase 4 | Pending |
| ML-06 | Phase 4 | Pending |
| UI-01 | Phase 5 | Pending |
| UI-02 | Phase 5 | Pending |
| UI-03 | Phase 5 | Pending |
| UI-04 | Phase 5 | Pending |
| UI-05 | Phase 5 | Pending |
| OPS-01 | Phase 6 | Pending |
| OPS-02 | Phase 6 | Pending |
| DOC-01 | Phase 6 | Pending |
| DOC-02 | Phase 6 | Pending |

**Coverage:**
- v1 requirements: 33 total
- Mapped to phases: 33
- Unmapped: 0

---
*Requirements defined: 2026-10-11*
*Last updated: 2026-10-11 after roadmap creation (traceability filled)*
