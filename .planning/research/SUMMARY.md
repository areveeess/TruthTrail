# Project Research Summary

**Project:** TruthTrail
**Domain:** Misinformation claim-triage and propagation-cascade analysis (news + social data, calibrated text classifier, cascade dashboard)
**Researched:** 2026-10-11
**Confidence:** MEDIUM-HIGH

## Executive Summary

TruthTrail is a claim-triage and cascade-analysis tool. The reference tools (Hoaxy, CoVaxxy, ClaimBuster, Full Fact) all share one shape: an ingest layer over a public source, a ranking layer, a spread visual, and deference to humans for the verdict. None outputs a bare "FAKE" label, and TruthTrail should not either.

The recommended build is a modular monolith: one Python package with an `api` process, a bounded `worker`/collector, and Postgres as the only integration point; an offline `ml/` package that meets the runtime only through a hash-verified artifact (`manifest.json` with sha256, calibration, thresholds, metrics, plus one shared `preprocess` function); and a React/TypeScript SPA. The propagation source is Bluesky Jetstream v2 (via `atproto==0.0.72`), collected forward in time from a seeded, bounded set of tracked roots. The classifier is TF-IDF + logistic regression trained on LIAR, with PHEME leave-one-event-out as a second benchmark, calibrated, and compared against the old keyword rules as "baseline 0". Deploy is one Docker image (FastAPI serving the SPA) on Render free, Neon free Postgres, and a GitHub Actions scheduled job as the collector.

The main risks are validity and honesty risks, not engineering ones: outlet/source leakage and test contamination; domain shift (trained on LIAR statements and PHEME tweets, served on Bluesky posts and headlines); uncalibrated confidence; presenting reposts as a reshare tree; and an expired or dead demo. The tool must never fall back silently to keyword rules or fabricated data.

## Key Findings

### Recommended Stack

Versions were registry-verified on 2026-10-11; exact pins are in `STACK.md`. Bluesky is the propagation source (free, unauthenticated, unmetered Jetstream live tail; v2 launched 2026-08-13). Mastodon is a poor fit for cascades (REST limit 300 calls / 5 min; `reblogged_by` returns accounts with no per-boost timestamp, inferred from the entity type). Datasets need no X/Twitter API for the text benchmarks.

**Core technologies:**
- Python 3.13, FastAPI 0.143, Pydantic 2.14: API layer — extends the existing service
- SQLAlchemy 2.1 (async) + psycopg 3 only (no asyncpg), Alembic, Postgres 17: storage — SQLAlchemy 2.1 defaults to psycopg 3; Neon supports 14-18
- scikit-learn 1.9, httpx, uv, Ruff, mypy, pytest, hypothesis, pip-audit: ML baseline (calibration, tuned thresholds, grouped CV, PR-AUC) and tooling — scikit-learn has no ECE function, so write a small tested helper
- React 19, Vite 8, TanStack Query, Recharts, custom D3 layout rendered by React: dashboard — Sigma 4 does not match `@react-sigma/core`, so use d3-hierarchy/scale/zoom for the cascade tree
- TypeScript 7 + Biome + `@hey-api/openapi-ts` (pin exact): typed client — `typescript-eslint` and `openapi-typescript` fail to install against TS 7; fallback TS 6.0.3 + ESLint
- Render free (single image), Neon free Postgres, GitHub Actions scheduled collector: deploy — Render free Postgres expires after 30 days; Fly.io has no free tier for new orgs

### Expected Features

Full detail in `FEATURES.md`.

**Must have (table stakes, v1):**
- Honest 502/503 errors, `DEMO_MODE` (default false) and a `synthetic: true` flag that reaches the UI
- Real Bluesky ingest with edge types and an `inferred` flag on edges
- Calibrated score with a band, an abstain state and a per-prediction explanation
- Reproducible evaluation: macro-F1, PR-AUC, Brier/ECE, bootstrap CIs, disjoint splits, baseline 0 plus a majority baseline, model card, README table generated from `metrics.json`
- Dashboard: cascade graph, timeline, stats, and loading/error/empty/stale/"server waking up" states
- Tests, CI, Docker, rate limiting, restricted CORS; deployed demo from seeded real cascades; README with limitations and ethics

**Should have (v1.x, if time allows):**
- Google Fact Check Tools lookup; hand-labelled out-of-domain probe set (strongly recommended); cascade export; triage list; domain-credibility signal (per domain, not per user; check list licence)

**Defer (v2+):**
- Cascade features + early detection (PHEME / Twitter15-16); transformer fine-tune; simulator fitted to real cascades and labelled as a model; claim clustering; API-key auth; observability

**Anti-features:** verdict labels / "detects the truth" copy; per-user blacklists or bot scores; LLM-as-judge verdicts; synthetic data presented as analysis; X/Twitter ingestion; repost fan-out drawn as an observed reshare tree; hardcoded named public figures; real-time everything; accounts and moderation.

### Architecture Approach

Data flows source -> worker -> Postgres -> api -> web. The model is an in-process `Predictor` loaded once at startup (hash-verified; a missing artifact fails `/ready` with 503, never a silent keyword fallback). Cascades are a forest of single-parent trees stored as event rows with `parent_uri` and a lazily resolved `parent_event_id`; orphans are first-class and parents are never invented. Events are ordered by `observed_at` (stream receipt time), never the author-asserted `occurred_at` — this is the root-cause fix for the prototype's "child before parent" defect. Observed and synthetic data never share tables; live data is scored, never evaluated.

**Major components:**
1. Ingest worker — bounded forward-in-time collector; idempotent upserts keyed on `at://` URI; checkpoint-after-commit; delete handling
2. Enrich — parent resolver, rollups, versioned cascade features (`features(events, t0, horizon)`)
3. API (`/v1`) — typed read API, `/v1/score` playground, `/health` and `/ready`
4. `ml/` — offline training, evaluation harness, artifact + manifest
5. Web — React/TS SPA on OpenAPI-generated types

### Critical Pitfalls

Full list (15 critical, 14 moderate/minor) and an Evaluation Integrity Protocol in `PITFALLS.md`.

1. **Outlet/style leakage and test contamination** — use claim-level LIAR/PHEME, dedupe, split by group/event with a three-way split (train / calibration / test) and a canary suite (source-only baseline, shuffled labels, top-features table).
2. **Domain shift** — add an abstain state and report a separate out-of-domain false-flag row; state it in the README.
3. **Misleading metrics and uncalibrated confidence** — calibrate on validation, evaluate on test, show bands rather than bare percentages.
4. **Fake cascade structure and trusted timestamps** — order by `observed_at`; `createdAt` is untrusted; reposts attach to the root, so true edges exist only for replies/quotes; store `edge_kind` and `inferred`.
5. **Silent fallbacks and a dead demo** — provenance fields (`data_as_of`, `source_status`, `synthetic`), a recorded-replay mode distinct from synthetic data, and Neon rather than Render Postgres.

## Implications for Roadmap

Research confirms the 6-phase v1 plan. Add sub-steps and gating decisions inside the six phases; do not add phases.

### Phase 1: Foundation / Safety
**Rationale:** Everything else builds on honest behaviour and clean secrets.
**Delivers:** Secrets out, `.gitignore`; honest 502/503; `DEMO_MODE` default false; characterization tests pinning current `/analyze` (buggy keyword output included); secret scan; CI grep banning "detects" / "FAKE" copy.
**Avoids:** Silent fallbacks; overclaiming.

### Phase 2: Engineering Baseline
**Rationale:** CI and structure must exist before data and ML code lands.
**Delivers:** Strangler refactor onto `src/truthtrail`, uv lockfile, CI, Dockerfile, `/health` and `/ready`, CORS, slowapi, TTL cache, httpx timeouts; delete `spread_simulator.py` and `users.py`.
**Uses:** Python 3.13, FastAPI, uv, Ruff, mypy, pytest.

### Phase 3: Real Propagation Data
**Rationale:** The source spike must precede the schema.
**Delivers:** 3a spike (terms, volume, cascade yield, edge semantics, selection policy, retention, dataset audit); 3b schema; 3c ingest (replay source first, checkpoint-after-commit, deletes, idempotency); 3d enrich (including the property test "shuffled arrival gives identical state"); 3e read API.
**Implements:** Ingest worker, enrich, Postgres schema.

### Phase 4: Baseline Detection + Evaluation
**Rationale:** The eval harness and baseline 0 precede any model. This phase can run in parallel with Phase 3.
**Delivers:** 4a loaders, splits, metrics, baseline 0 (as-shipped and word-boundary-fixed) and a majority baseline; 4b TF-IDF+LR, calibration, canaries, slices, name-swap test, abstain logic, model card; 4c serving with a hash-verified loader and `/ready` gating.

### Phase 5: Dashboard
**Delivers:** Vite react-ts re-scaffold; typed client with zod; custom D3 cascade tree and Recharts timeline; risk badge with abstain state; loading, error, empty, stale and "server waking up" states; pseudonymized accounts.

### Phase 6: Deploy
**Delivers:** Single image on Render, Neon Postgres, GitHub Actions collector; seeded real cascades; clean-clone acceptance test; weekly health check; README with generated results table; re-read the Bluesky terms before launch.

### Where research refines or contradicts the plan
1. **Bluesky, not Mastodon.** Phase 3a confirms; Mastodon moves to v2.
2. **Forward collection changes the product.** Jetstream filters only by collection and DID, and Replay needs an API key and is byte-metered, so "any claim, any time" is not deliverable. The primary UX becomes a triage feed of tracked cascades ranked by risk x velocity plus a "score this text" playground; the query-driven `/analyze` flow does not survive as the core. **Record this as a product decision.** Show "observed since" and orphan counts in the UI.
3. **Repost-star caveat.** Reposts attach to the root; true edges exist only for replies and quotes. Store `edge_kind` and `inferred`; report depth with the caveat; label snapshot-only cascades "partial (reposts untimed)". Decide before the 3b migration.
4. **Tracked-root selection policy (new 3a gating decision).** Store a root only if it passes a seed filter (link on a curated news/fact-check domain, or match to an active claim); store replies/quotes/reposts only if their root is tracked. Seeding needs a free Bluesky account + app password in env vars. Measure cascade yield in the spike.
5. **Datasets.** LIAR (primary; license metadata `unknown`; download by script, never commit) and PHEME (only offline reply-tree dataset; leave-one-event-out). FakeNewsNet, CoAID, MuMiN, Twitter15/16 need X rehydration or have unclear licenses (out-of-domain probes at most). ISOT and WELFake excluded for leakage risk. No labelled Bluesky dataset exists, so numbers are cross-domain — say so in the README. Drop LIAR speaker/party metadata as features.
6. **Hosting.** Render free sleeps after 15 min and cannot run workers/jobs; its free Postgres expires after 30 days with no backups. So the collector is a bounded GitHub Actions scheduled batch job, not a 24/7 worker (keep the always-on compose worker for local use). Use Neon (autosuspend: build cold-start tolerance into Phase 5). Cloud Run (needs a card) is the fallback. Scheduled workflows are disabled after 60 days of repo inactivity.
7. **Ordering.** Source spike precedes schema; eval harness + baseline 0 precede any model.
8. **Tooling.** TS 7 + Biome with `@hey-api/openapi-ts` (pin exact); supersedes ARCHITECTURE.md's `openapi-typescript`.
9. **Minor.** Persist `observed_at` and `occurred_at` separately; bundle slices, name-swap test and out-of-domain probe into Phase 4; settle the `features(events, t0, horizon)` interface in Phase 3's data model for v2; GNews free tier (~100 req/day, non-commercial, LOW confidence) means the public demo must never proxy arbitrary user queries — refresh a bounded query set from the batch job and serve from the DB.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3a:** full read of Bluesky terms and data-use, live-tail volume and cascade yield, repost/quote record shapes, retention and privacy, dataset audit
- **Phase 6:** Render RAM and cold start, Neon pooler + psycopg (`prepare_threshold=None`), scheduled-job behaviour

Moderate: **Phase 4b** (calibration with small validation sets, abstain thresholds, slices), **Phase 5** (large-tree strategy, accessibility).

Standard patterns: **Phases 1 and 2**, and sub-steps 3b/3c/3e and 4a/4c.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Registry-verified versions; LOW items: replay quotas, Bluesky data-use terms, Render RAM, `@hey-api` with TS 7 |
| Features | MEDIUM-HIGH | Reference tools well sourced; ClaimBuster API and Meedan internals thinner |
| Architecture | MEDIUM-HIGH | Some Jetstream details from secondary sources (prefer STACK.md on conflicts); GNews LOW |
| Pitfalls | MEDIUM-HIGH | Platform facts verified; ML methodology is standard practice, not re-verified |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **Bluesky data-use terms:** no research/ML clause found, and absence is not a license. Read in full in 3a and again before launch; mitigate with minimal storage, honored deletes, no raw-post republication, and a descriptive User-Agent.
- **Live-tail cascade yield:** unmeasured — measure in the 3a spike.
- **Replay quota and cost:** unverified — treat history as v2.
- **PHEME contents; Twitter15/16 / UPFD licenses:** unconfirmed — audit on download.
- **GNews limits and terms:** LOW confidence — verify before relying on them.
- **Render RAM / cold start; Neon pooler behaviour:** untested with the real image — Phase 6.
- **Owner decisions needed in 3a/3d:** retention policy for stored text; whether to merge cascades when a provisional root resolves later.
- **Expect modest classifier scores.** Frame the README around measured improvement over baseline 0 with CIs.

## Sources

### Primary (HIGH confidence)
- Bluesky Jetstream, replay, rate-limit, API-directory and Developer Guidelines docs; 2026-08-13 AT Protocol announcement
- Bluesky lexicons; bsky-docs issue #332
- Mastodon docs
- PHEME, LIAR, FakeNewsNet and CoAID sources
- SQLAlchemy 2.1 migration notes
- Render, Neon, Hugging Face Spaces, Cloud Run and Fly.io docs
- PyPI / npm resolution tests

### Secondary (MEDIUM confidence)
- DeVerna et al., arXiv 2410.21554 (reshare attribution)
- Hoaxy, CoVaxxy, Full Fact, Fact Check Tools and ClaimBuster material
- Bluesky dataset ethics sources (arXiv 2404.18984, Zenodo, 404 Media)
- Transformers v5 migration guide
- GitHub Actions READMEs

### Tertiary (LOW confidence)
- ISOT source-confound preprint
- GNews third-party limit listings
- A community report of the Replay quota
- MurkySky

---
*Research completed: 2026-10-11*
*Ready for roadmap: yes*
