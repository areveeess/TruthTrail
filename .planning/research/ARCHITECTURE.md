# Architecture Research

**Domain:** Misinformation early-warning system (ingest -> store -> features -> model -> API -> dashboard)
**Researched:** 2026-10-11
**Mode:** Ecosystem + integration (subsequent milestone: how target features integrate with the existing flat 7-module FastAPI service)
**Overall confidence:** MEDIUM-HIGH. Structural patterns (modular monolith, Postgres-as-the-only-integration-point, offline train / online serve, adjacency-list trees) are well-established (HIGH). Source-specific facts (Jetstream query parameters and API version, Mastodon boost semantics, GNews terms) come from secondary sources or training knowledge and are tagged MEDIUM/LOW inline; all of them are inputs to the Phase 3 source spike, not decisions to bake in now.

---

## Executive Position (opinionated)

1. **One repo, one Python package, three process types, one datastore.** `api` (FastAPI, read-mostly), `worker` (ingest + enrich, no HTTP surface), and `web` (static React build). Postgres is the *only* integration point between api and worker. No Redis, no message broker, no separate "model service" in v1. A solo part-time portfolio project that adds a broker or a model microservice is spending its budget on plumbing reviewers do not grade.
2. **Model inference is in-process in the API (and the worker's scorer), behind a `Predictor` protocol; training is a separate offline package that never ships in the runtime image.** The two sides meet only at a versioned artifact directory with a `manifest.json`, plus one shared preprocessing function (to prevent train/serve skew).
3. **The cascade is a forest of single-parent events** (a tree per root post), stored as an adjacency list with denormalized `root_uri`/`cascade_id`/`depth`. Whole-cascade reads are one indexed flat scan; recursion is only needed in the resolver job. A "DAG" only appears if you model multiple parents; do not. Secondary relationships (quote-of-X-that-is-a-reply-to-Y, same article shared by many roots, cross-platform links) are separate columns/tables, not extra parent edges.
4. **Observed data and synthetic data never share tables.** The v2 simulator is a pure, seeded library that returns the same domain objects but writes nothing to observed tables; only the run recipe (seed, params, intervention) is persisted. The API envelope carries `synthetic: true` on every simulator route.
5. **Two data planes.** (a) Labelled research datasets -> `ml/` -> artifact + metrics (offline, files). (b) Live observations -> Postgres -> serving (online, unlabelled). Live data is *scored*, never *evaluated*; evaluation numbers come only from (a). This is what makes "every score is backed by a measured, reproducible evaluation" true.
6. **Product shape implication for the roadmap:** a firehose/stream source cannot answer "show me the cascade for this arbitrary query". The primary UX is a **triage feed of tracked claims/cascades ranked by risk x velocity**, with an ad-hoc "score this text" playground as secondary. The old query-driven `/analyze` flow does not survive as the core experience. Flag this as an explicit product decision in the roadmap.

---

## Standard Architecture

### System Overview

```
 EXTERNAL                       RUNTIME (docker-compose)                              OFFLINE (not deployed)
┌──────────────────┐
│ Bluesky Jetstream│──ws push──┐
│ (or Mastodon pull)│          │
├──────────────────┤           ▼
│ Recorded fixture │─────► ┌─────────────────────────────┐
│ (replay source)  │       │  worker  (python -m ... )   │       ┌──────────────────────────┐
├──────────────────┤       │  ┌────────┐   ┌───────────┐ │       │ ml/ (train + eval)        │
│ GNews (batch     │─pull─►│  │ ingest │──►│  enrich   │ │       │  datasets -> features ->  │
│ claim refresh)   │       │  │ filter │   │ resolve / │ │       │  fit -> calibrate -> eval │
└──────────────────┘       │  │ + write│   │ rollup /  │ │       │  baseline 0 vs model     │
                           │  └───┬────┘   │ score     │ │       └────────────┬─────────────┘
                           │      │        └─────┬─────┘ │                    │ writes
                           └──────┼──────────────┼───────┘                    ▼
                                  ▼              ▼                 ┌──────────────────────────┐
                           ┌─────────────────────────────┐         │ model artifact dir        │
                           │        PostgreSQL            │◄────────│  model.{joblib|onnx}      │
                           │ accounts claims events       │ reads   │  manifest.json (sha256,   │
                           │ cascades cascade_features    │ manifest│  version, metrics, calib) │
                           │ model_versions claim_scores  │ at start│ + committed: metrics.json │
                           │ ingest_checkpoints news_cache│         │   and model_card.md       │
                           │ simulation_runs (v2)         │         └────────────┬─────────────┘
                           └──────────────┬──────────────┘                      │ mounted read-only
                                          │ SELECT (+ INSERT scores/cache)      │ (volume / release asset)
                                          ▼                                     ▼
                           ┌─────────────────────────────────────────────────────────────┐
                           │ api (FastAPI)  /v1/*  /health /ready                         │
                           │  routers -> services -> {repositories, Predictor, sim}       │
                           │  rate limit (middleware) · TTL cache · ETag · problem+json   │
                           └──────────────────────────────┬──────────────────────────────┘
                                                          │ JSON (OpenAPI = the contract)
                                                          ▼
                           ┌─────────────────────────────────────────────────────────────┐
                           │ web (React + TS + Vite, served by nginx/Caddy; /v1 proxied)  │
                           │  triage list · cascade graph · timeline · risk badge         │
                           └─────────────────────────────────────────────────────────────┘
```

Direction of data flow is strictly left-to-right / top-to-bottom at runtime: **sources -> worker -> Postgres -> api -> web**. The artifact directory is a second, read-only inbound arrow into api and worker (never the reverse). The web app never talks to Postgres, the worker, or the model directly.

### Component Boundaries

| Component | Owns | Reads | Writes | Talks to | Must NOT |
|-----------|------|-------|--------|----------|----------|
| **worker: ingest** | Source adapters, normalization, selection policy ("which roots do we track"), idempotent batch writes, checkpointing | Source streams; `events` (tracked-URI lookup); `ingest_checkpoints` | `accounts`, `events`, `claims` (social_link), `ingest_checkpoints` | Postgres, external sources | Serve HTTP; score; build trees |
| **worker: enrich** | Orphan/parent resolution, root + cascade assignment, rollup aggregates, claim<->cascade linking, scoring of unscored claims, GNews batch refresh | `events`, `claims`, `claim_scores`, artifact dir | `events` (resolved cols), `cascades`, `cascade_features`, `claim_scores`, `model_versions`, `claims` (news_headline), `news_cache` | Postgres, artifact dir, GNews | Hold long-lived state in memory that Postgres lacks |
| **api** | HTTP contract (`/v1`), validation, pagination, error mapping, rate limit, read caching, ad-hoc scoring, (v2) simulation endpoints | Postgres, artifact dir | `claim_scores` (optional persist), `news_cache` | Postgres, artifact dir; GNews only via cache-guarded client | Run ingest; train; block on upstream without timeout; fall back silently to keyword rules |
| **domain** (library) | Pure types and functions: `Event`, `CascadeTree`, tree builder, features, URL canonicalization, text normalization | nothing (pure) | nothing | nothing | Import DB, HTTP, FastAPI, sklearn |
| **inference** (library) | `Predictor` protocol, artifact loader/verifier, calibration application, `KeywordBaseline` (baseline 0) | artifact dir | nothing | domain | Know about Postgres or HTTP |
| **ml/** (offline) | Dataset loading, training, calibration, evaluation harness, model card, artifact export | Datasets (files), shared `preprocess` from the package | artifact dir, `ml/results/metrics.json`, `ml/model_card.md` | the `truthtrail` package (preprocess + baseline) | Be imported by api/worker; be installed in the runtime image |
| **sim** (v2 library) | Seeded cascade generator, interventions, calibration from observed cascades | observed cascades (read-only, for calibration) | `simulation_runs` only | domain | Write to `events`/`cascades`; emit anything without `synthetic=True` |
| **web** | Rendering, client state, loading/error/empty states | API only | nothing | api (via same-origin proxy) | Embed fabricated/mock data in production bundle |
| **Postgres** | Durable state, uniqueness/idempotency, FK integrity | - | - | api, worker | Be used as a time-series DB or a blob store for tree JSON |

### Dependency rule (enforce in CI with `import-linter` or a simple test)

```
api  ──► services ──► repositories (db) ─┐
 │           │                           ├──► domain   (domain imports nothing internal)
 │           └──► inference ─────────────┤
worker(ingest, enrich) ──► {db, inference, domain, news}
ml/  ──► {domain.text (preprocess), inference.baseline}        (one-way; runtime never imports ml/)
sim  ──► domain
```

`api` and `worker` never import each other. They share only `domain`, `db`, `inference`, `core`.

---

## Recommended Project Structure

Monorepo, `src` layout, single Python distribution with optional dependency groups so the runtime image stays light (no torch/transformers).

```
TruthTrail/
├── pyproject.toml                  # runtime deps pinned; extras: [train], [dev]; ruff/mypy/pytest config
├── uv.lock | requirements.lock     # pinned lock (pip-audit target)
├── docker-compose.yml              # db, migrate, api, worker-ingest, worker-enrich, web  (+ profiles: train, redis)
├── Dockerfile                      # multi-stage; target=api and target=worker share a base
├── Makefile                        # up, test, lint, eval, fetch-model, gen-types
├── alembic.ini
├── migrations/                     # Alembic revisions (schema is code; reviewable)
├── src/truthtrail/
│   ├── core/                       # settings (pydantic-settings, env only), logging, errors
│   ├── domain/                     # PURE: events.py, cascade.py (tree builder), features.py, urls.py, text.py (preprocess)
│   ├── db/                         # SQLAlchemy 2.0 models, session, repositories/ (events, cascades, claims, scores)
│   ├── inference/                  # predictor.py (Protocol), loader.py (manifest+sha256), sklearn_.py, onnx_.py(v2), baseline_keywords.py
│   ├── news/                       # gnews.py (timeouts, status checks, typed errors), cache.py
│   ├── ingest/                     # sources/{base.py, bluesky_jetstream.py, mastodon.py, replay.py}, select.py, normalize.py, writer.py
│   ├── enrich/                     # resolve.py, rollup.py, scorer.py, link_claims.py
│   ├── worker/                     # __main__.py: `python -m truthtrail.worker ingest|enrich`
│   ├── services/                   # use-cases the routers call (orchestration, caching decisions)
│   ├── api/
│   │   ├── app.py                  # create_app(), lifespan (load model once, open pool), middleware
│   │   ├── deps.py                 # DB session, Predictor, settings, rate-limit deps
│   │   ├── schemas.py              # Pydantic response/request models (the public contract)
│   │   ├── errors.py               # exception -> problem+json (502/503 honest mapping)
│   │   └── routers/{health.py, claims.py, cascades.py, score.py, status.py, simulations.py(v2), legacy.py(temporary)}
│   └── sim/                        # v2: model.py, interventions.py, calibrate.py (pure, seeded)
├── ml/                             # OFFLINE; not in runtime image
│   ├── datasets/                   # loaders + download scripts (data itself gitignored)
│   ├── train.py  evaluate.py  export.py
│   ├── results/metrics.json        # committed
│   └── model_card.md               # committed
├── tests/
│   ├── unit/                       # domain, inference (toy model built in-fixture), sim invariants
│   ├── integration/                # Postgres (CI service container / testcontainers): repos, ingest replay, resolver
│   ├── contract/                   # OpenAPI snapshot + schemathesis-style checks
│   └── characterization/           # pins legacy /analyze behaviour BEFORE refactor
├── fixtures/
│   └── recorded/                   # small recorded real-source sample (JSONL), handles pseudonymized
├── frontend/                       # Vite + React + TS; src/api/schema.d.ts generated from OpenAPI
│   ├── src/{api,components,features/{triage,cascade,timeline},lib}
│   └── e2e/                        # Playwright smoke against compose + replay data
└── .github/workflows/ci.yml
```

### Structure Rationale

- **`domain/` is pure and import-free.** Tree building, feature extraction, URL canonicalization, text preprocessing are the things most worth unit-testing and the things shared by api, worker, ml and sim. Purity makes them property-testable (shuffle events -> same tree).
- **`src/` layout + package** fixes the existing "must run from repo root / flat top-level imports" constraint noted in the codebase map.
- **`ml/` outside `src/`** makes the offline/online split structural: the runtime Dockerfile `COPY`s only `src/`, so torch cannot sneak in.
- **`worker/` is a separate entrypoint, not a FastAPI background task.** Lifecycle, restarts, and horizontal scaling are independent of the HTTP process (see Anti-Patterns).
- **Legacy module mapping (strangler, not big-bang):**

| Existing | Becomes | Note |
|----------|---------|------|
| `main.py` | `api/app.py` + `api/routers/legacy.py` (temporary `/analyze` shim), then removed | Characterization tests pin it first; remove once `/v1` + dashboard exist |
| `gnews_fetcher.py` | `news/gnews.py` | Env key, timeout, status check, typed `UpstreamError` -> 502/503 |
| `risk_analyzer.py` | `inference/baseline_keywords.py` | Frozen as "baseline 0" and scored on the same eval split. Report as-is (substring bugs included); optionally add word-boundary "baseline 0b" so the table shows both |
| `spread_simulator.py`, `users.py` | **Deleted** (fabricated data, ~40% events precede parents) | v2 `sim/` is a rewrite, not a port |
| `models.py` (`Event`, unused) | `domain/events.py` + `api/schemas.py` | Split domain type from wire type |
| `package.json` (root, recharts only) | `frontend/package.json` | Move/reconcile |

---

## Data Model (Postgres)

### Modelling decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Cascade shape | **Forest of single-parent trees** (adjacency list `parent_uri`/`parent_event_id`) | Replies, quotes, reposts each respond to exactly one thing. A true DAG needs multiple parents per node; the data does not have them. |
| Tree storage | Adjacency list + denormalized `root_uri`, `cascade_id`, `depth` | Fetch whole tree = `WHERE cascade_id = $1` flat index scan, tree built in Python. No `ltree`, no closure table: both add write complexity for read patterns you do not have at this scale. |
| Out-of-order arrival | Store `parent_uri` (text, always) separately from `parent_event_id` (FK, resolved lazily) | Streams deliver children before parents and children of posts you never saw. An orphan is a first-class state, never an invented parent. |
| Timestamps | `occurred_at` (author-asserted `createdAt`, untrusted/backdatable) vs `observed_at` (stream `time_us` / fetch time) | Ordering, velocity and early-warning windows use `observed_at`. This is the direct fix for the old "events precede their parent" defect: enforce `observed_at(child) >= observed_at(parent)` as an invariant on live data and report violations of `occurred_at` as a data-quality metric, not a DB constraint. |
| Claim vs cascade | `claims` 1 -- N `cascades` (a cascade has one root post; a claim, e.g. one article, is shared by many independent root posts) | Matches reality: one news item spawns many independent threads. Dashboard claim view = forest of cascades. |
| Event enums | `text` + `CHECK`, not Postgres `ENUM` | Cheaper migrations. |
| Derived data | `cascades` counters and `cascade_features` are **recomputed idempotently by `enrich`**, not maintained by triggers | Correctness and testability over micro-latency. |
| Synthetic data | **Not in these tables** (v2 sim persists recipes only) | Physical separation makes contamination of eval/analytics impossible. |
| Labels | **Not in these tables** | Labels live in the offline datasets; live rows are unlabelled. (Optional later: `reference_labels` for claims matched to published fact-checks.) |

### Platform semantics that shape the model (MEDIUM; verify in Phase 3 spike)

- **Bluesky/atproto:** a reply record carries `reply.root` and `reply.parent` (strong refs: `uri` + `cid`), so the thread root is known from the record itself even when intermediate parents were never seen. A quote post carries `embed.record` (or record-with-media). A repost is its own record (`app.bsky.feed.repost`) with a `subject` strong ref, delivered as a timestamped event. Link-share posts carry `app.bsky.embed.external` (`uri`, `title`, `description`), so a **claim text/URL is available free from the post itself**, no GNews call needed.
- **Honest limitation to document:** reposts/boosts attach to the *original* post (you cannot repost a repost). So the observed "cascade" is a record of **interactions with a root** (replies tree + quote chains + a repost fan-out), **not** a who-saw-it-from-whom exposure path. The README limitations section and the simulator's framing must say so.
- **Mastodon:** replies via `in_reply_to_id`; a boost is a status with a `reblog` field pointing at the original. Pull-based reconstruction uses `GET /api/v1/statuses/:id/context` (ancestors/descendants). Boosters are listable but individual boost *timing* is weaker than Bluesky's per-record timestamps (MEDIUM/LOW; verify). Default rate limit is 300 requests / 5 minutes with `X-RateLimit-*` headers (official docs, last updated 2022; instance-specific). This is a reason the spike should lean Bluesky for cascade timing, but the spike decides.

### Schema sketch (DDL shown for design; real schema is Alembic migrations)

```sql
-- Who. Public identifiers only; see Retention below.
CREATE TABLE accounts (
  id            bigserial PRIMARY KEY,
  platform      text        NOT NULL,            -- 'bluesky' | 'mastodon:<instance>'
  external_id   text        NOT NULL,            -- DID / account URI
  handle        text,
  followers     integer,                          -- snapshot at first sight, nullable
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (platform, external_id)
);

-- What is being asserted/linked. Unit of scoring.
CREATE TABLE claims (
  id            bigserial PRIMARY KEY,
  kind          text        NOT NULL CHECK (kind IN ('news_headline','social_link','social_text')),
  text          text        NOT NULL,             -- headline / embed title / post text
  text_hash     bytea       NOT NULL,             -- sha256(normalize(text)) from domain.text
  url_canonical text,                             -- canonicalized, redirects NOT followed in hot path
  source_name   text,
  published_at  timestamptz,
  lang          text,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX claims_dedupe ON claims (kind, text_hash, coalesce(url_canonical, ''));
CREATE INDEX claims_url ON claims (url_canonical) WHERE url_canonical IS NOT NULL;

-- One row per cascade = one root post. Aggregates are derived/recomputed.
CREATE TABLE cascades (
  id              bigserial PRIMARY KEY,
  platform        text        NOT NULL,
  root_uri        text        NOT NULL,
  claim_id        bigint      REFERENCES claims(id),
  first_event_at  timestamptz,                   -- observed_at
  last_event_at   timestamptz,
  event_count     integer     NOT NULL DEFAULT 0,
  unique_accounts integer     NOT NULL DEFAULT 0,
  max_depth       integer     NOT NULL DEFAULT 0,
  orphan_count    integer     NOT NULL DEFAULT 0, -- completeness signal surfaced by the API
  status          text        NOT NULL DEFAULT 'active' CHECK (status IN ('active','closed')),
  rollup_version  integer     NOT NULL DEFAULT 1,
  rolled_up_at    timestamptz,
  UNIQUE (platform, root_uri)
);
CREATE INDEX cascades_recent ON cascades (last_event_at DESC);
CREATE INDEX cascades_claim  ON cascades (claim_id);

-- Every observed propagation action (post, reply, quote, repost). Append-mostly.
CREATE TABLE events (
  id              bigserial PRIMARY KEY,
  platform        text        NOT NULL,
  external_uri    text        NOT NULL,           -- at:// URI or status URL = idempotency key
  kind            text        NOT NULL CHECK (kind IN ('post','reply','quote','repost')),
  account_id      bigint      NOT NULL REFERENCES accounts(id),
  occurred_at     timestamptz NOT NULL,           -- author-asserted, untrusted
  observed_at     timestamptz NOT NULL,           -- stream/fetch time, used for ordering & windows
  parent_uri      text,                           -- what this responds to; NULL only for kind='post'
  root_uri        text        NOT NULL,           -- = external_uri for roots; reply.root for replies
  root_resolved   boolean     NOT NULL DEFAULT true, -- false for repost/quote of a not-yet-seen reply
  parent_event_id bigint      REFERENCES events(id), -- resolved lazily by enrich; NULL + parent_uri => orphan
  cascade_id      bigint      REFERENCES cascades(id),
  depth           integer,                        -- from root; NULL until resolved
  claim_id        bigint      REFERENCES claims(id), -- set on roots (and quotes carrying a link)
  text            text,                           -- NULL for reposts; NULLed on delete
  link_url        text,                           -- canonicalized
  lang            text,
  deleted_at      timestamptz,
  UNIQUE (platform, external_uri),
  CHECK ((kind = 'post') = (parent_uri IS NULL)),
  CHECK (parent_event_id IS NULL OR parent_event_id <> id)
);
CREATE INDEX events_cascade_time ON events (cascade_id, observed_at);
CREATE INDEX events_orphans      ON events (platform, parent_uri) WHERE parent_event_id IS NULL AND parent_uri IS NOT NULL;
CREATE INDEX events_account      ON events (account_id);
CREATE INDEX events_claim        ON events (claim_id) WHERE claim_id IS NOT NULL;

-- Derived, versioned, snapshot-able. as_of enforces "only information available at that time".
CREATE TABLE cascade_features (
  cascade_id      bigint      NOT NULL REFERENCES cascades(id) ON DELETE CASCADE,
  feature_version integer     NOT NULL,
  as_of           timestamptz NOT NULL,           -- features use only events with observed_at <= as_of
  values          jsonb       NOT NULL,           -- size, depth, breadth, duration, structural virality, ...
  computed_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (cascade_id, feature_version, as_of)
);

-- Model registry: scores are always attributable to an artifact.
CREATE TABLE model_versions (
  version         text PRIMARY KEY,               -- e.g. 'tfidf-lr-2026.10.1'
  artifact_sha256 text NOT NULL,
  git_sha         text,
  dataset_id      text,
  trained_at      timestamptz,
  metrics         jsonb NOT NULL,                 -- macro-F1, PR-AUC, ECE copied from manifest
  manifest        jsonb NOT NULL
);

CREATE TABLE claim_scores (
  claim_id      bigint NOT NULL REFERENCES claims(id),
  model_version text   NOT NULL REFERENCES model_versions(version),
  score         real   NOT NULL,                  -- calibrated P(flag for review)
  band          text   NOT NULL CHECK (band IN ('low','review','high','abstain')),
  confidence    real   NOT NULL,
  scored_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (claim_id, model_version)
);
-- "Current" score = the row whose model_version = settings.ACTIVE_MODEL_VERSION (not "latest scored_at").

CREATE TABLE ingest_checkpoints (
  source     text PRIMARY KEY,                    -- 'bluesky-jetstream', 'mastodon:<instance>:<stream>'
  cursor     text NOT NULL,                       -- e.g. Jetstream time_us
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE news_cache (                          -- protects GNews quota; serve-stale-on-error
  cache_key  text PRIMARY KEY,                    -- hash(normalized query + params)
  payload    jsonb NOT NULL,
  status     text  NOT NULL,                      -- 'ok' | 'empty' | 'error'
  fetched_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL
);

-- v2: recipes only. Events are regenerated deterministically from (seed, params, intervention).
CREATE TABLE simulation_runs (
  id          uuid PRIMARY KEY,
  seed        bigint NOT NULL,
  params      jsonb  NOT NULL,
  intervention jsonb,
  sim_version text   NOT NULL,
  summary     jsonb,
  created_at  timestamptz NOT NULL DEFAULT now()
);
```

### Key queries / jobs

```sql
-- Read a whole cascade (API tree endpoint): no recursion needed, cap and flag truncation.
SELECT e.id, e.kind, e.parent_event_id, e.parent_uri, e.depth, e.observed_at, a.handle
FROM events e JOIN accounts a ON a.id = e.account_id
WHERE e.cascade_id = $1 AND e.deleted_at IS NULL
ORDER BY e.observed_at
LIMIT 5001;                               -- 5001th row => truncated=true

-- Resolver (enrich): link orphans whose parents have since arrived. Idempotent, re-runnable.
UPDATE events c SET parent_event_id = p.id
FROM events p
WHERE c.parent_event_id IS NULL AND c.parent_uri IS NOT NULL
  AND p.platform = c.platform AND p.external_uri = c.parent_uri;

-- Idempotent ingest write (at-least-once delivery from the stream):
INSERT INTO events (...) VALUES (...) ON CONFLICT (platform, external_uri) DO NOTHING;
```

`depth` and `root_resolved` are filled by the resolver walking up with a `WITH RECURSIVE` over `parent_event_id` limited to the affected subtree. This is the only place recursion appears.

### Selection policy: what gets stored (critical, decide in the Phase 3 spike)

A firehose cannot be queried by claim; you only see what you collect, and collecting everything is wasteful and ethically heavy. Recommended **tracked-root ingest**:

1. A new top-level post becomes a **root** only if it passes a *seed filter*: link embed whose canonical domain is on a curated news/fact-check list, or text/URL matching an active claim (from GNews batch refresh or a watchlist).
2. A reply/quote/repost is stored **only if** its `root_uri` / `subject` is already a tracked URI (O(1) check against an in-memory LRU backed by `events`).
3. Everything else is dropped at the adapter boundary (server-side collection filters where the source supports it; client-side filter otherwise).

Consequence: cascades only start growing from the moment their root was seen. A cascade whose root predates ingestion is *not* tracked. The API must expose `first_seen_at`/`orphan_count` so the UI can show "observed since", never imply completeness.

---

## Architectural Patterns

### Pattern 1: Source adapter + replay source (testable, offline-capable ingest)

**What:** A tiny async interface every source implements, yielding normalized events plus a resumable cursor. A `ReplaySource` reads recorded real data from JSONL.
**When:** Always. It makes CI network-free, makes the clean-clone `docker compose up` work with no secrets, and lets the deployed demo run deterministically if a live source is down.
**Trade-offs:** Needs a small recorded fixture (keep it tiny; pseudonymize handles; check terms before committing real posts). Label `source_mode: "live" | "replay"` in `/v1/status` and the UI so replayed real data is never mistaken for live (it is real, but not live; it is never "synthetic").

```python
# ingest/sources/base.py
class NormalizedEvent(BaseModel):          # platform-agnostic; maps 1:1 to events columns
    platform: str; external_uri: str; kind: Literal["post","reply","quote","repost","delete"]
    account_external_id: str; handle: str | None
    occurred_at: datetime; observed_at: datetime
    parent_uri: str | None; root_uri: str
    text: str | None; link_url: str | None; lang: str | None

class EventSource(Protocol):
    def stream(self, cursor: str | None) -> AsyncIterator[tuple[NormalizedEvent, str]]: ...
    # yields (event, cursor_after_event). Adapter owns reconnect/backoff, never the writer.
```

### Pattern 2: Idempotent batch writer with checkpoint-after-commit

**What:** Bounded `asyncio.Queue` between reader and writer; writer commits batches with `ON CONFLICT DO NOTHING`, **then** persists the cursor in the same transaction.
**When:** Any resumable stream. Jetstream is cursor-resumable (Unix-microsecond `time_us` cursor), delivery is described as at-least-once with an inclusive cursor, so the same event can arrive twice (MEDIUM; confirm against current docs in the spike, including which API path/parameter names are current: community guides use `/subscribe` with `wantedCollections`, newer official docs describe an XRPC path with `collections`/`kinds`). On reconnect, rewind a few seconds; uniqueness makes it harmless.
**Trade-offs:** Backpressure blocks the reader (acceptable: the stream is resumable). Expose lag = `now - last cursor time` on `/v1/status`.

### Pattern 3: Postgres as the job board (no broker)

**What:** `enrich` picks work with `SELECT ... FOR UPDATE SKIP LOCKED` (e.g., claims lacking a score for the active model version; cascades whose `last_event_at > rolled_up_at`). Each job is idempotent.
**When:** Single small deployment, low job rate. **Trade-offs:** Polling latency of seconds; fine for "early warning" on a portfolio scale. Upgrade path (Redis/RQ/Arq) exists but is deliberately not taken.

### Pattern 4: Train offline, serve online; meet at a versioned artifact

**What:**

```
ml/train.py ──► artifacts/<version>/
                  model.joblib | model.onnx
                  manifest.json   { version, sha256(model), preprocess_version, label_schema,
                                    calibration:{method,params}, thresholds:{review,high,abstain_band},
                                    dataset_id+hash, git_sha, metrics, created_at }
                (committed separately: ml/results/metrics.json, ml/model_card.md)

api/worker lifespan: load_predictor(MODEL_DIR) -> verify sha256 vs manifest -> upsert model_versions
                     -> app.state.predictor      (loaded ONCE, never per request)
```

```python
# inference/predictor.py
class Prediction(BaseModel):
    score: float            # calibrated P(flag for review), [0,1]
    band: Literal["low","review","high","abstain"]
    confidence: float       # derived from calibration reliability / abstain band, NOT a fabricated CI
    model_version: str

class Predictor(Protocol):
    version: str
    def predict(self, texts: Sequence[str]) -> list[Prediction]: ...
```

Rules that keep the split honest:
- **One shared `domain.text.preprocess`** imported by both `ml/train.py` and `inference/*`. A unit test asserts byte-identical preprocessing on a golden string set (train/serve skew guard).
- **Artifact distribution without committing weights:** build/fetch step (`make fetch-model`) downloads a pinned release asset (or Hub file) and verifies the manifest hash; compose mounts it read-only. For a small TF-IDF + logistic-regression baseline, training can also run inside a CI/Docker build stage so a clean clone reproduces it without a download (decide in Phase 4).
- **Pickle is code execution.** Load `joblib` only after sha256 verification against the manifest; prefer ONNX when the v2 transformer lands (`onnxruntime` CPU, int8) so the loader is data-only. `Predictor` hides the swap: the API contract does not change between baseline and fine-tuned model.
- **No silent fallback.** Missing/invalid artifact -> `/ready` fails and `/v1/score` returns 503; the keyword baseline is selectable only by explicit config for evaluation, never as a quiet degrade.
- **Where scoring runs:** claims in the DB are scored by `enrich` (batch, cached in `claim_scores` keyed by `(claim_id, model_version)`); ad-hoc text goes through `POST /v1/score` (stateless, not persisted by default, tighter rate limit). Both call the same `Predictor`.
- A fine-tuned transformer (v2, CPU ONNX) is still in-process unless memory on the chosen host forces a split; do not pre-split.

### Pattern 5: Pure domain core, tree built in Python

**What:** `domain.cascade.build_tree(events) -> CascadeTree` never invents a parent: events whose parent is missing become *detached subtrees* flagged `parent_missing`, counted in `orphan_count`. Features are pure functions `features(tree, as_of)`.
**When:** Always. **Trade-offs:** Large viral cascades make big payloads: cap nodes server-side (`truncated: true`), and let the UI collapse/aggregate; expose `/timeline` as server-side bucketed counts rather than shipping every event.

### Pattern 6: OpenAPI as the single contract between api and web

**What:** Pydantic response models -> `openapi.json` -> `openapi-typescript` generates `frontend/src/api/schema.d.ts`; CI regenerates and fails on diff. Contract tests (schemathesis-style fuzz on `/v1`) run against the app with a test DB.
**Trade-offs:** One extra CI step; eliminates the most common full-stack drift bug.

### Pattern 7 (v2): Seeded, deterministic simulator with common random numbers

**What:** `simulate(seed, params, intervention) -> CascadeTree(synthetic=True)` using a seeded generator with per-node derived streams (`SeedSequence`/hash of `(seed, node_id)`), so a what-if (remove top-k amplifiers, apply a label at time t that scales branching probability, delay reshares) changes **only** the intervened mechanism. Baseline vs intervention is then a paired comparison with real attribution, not noise. Params can be calibrated from observed cascades (read-only). Persist only `simulation_runs`; regenerate events on demand; cache by hash of the recipe.
**Verification (cheap, strong):** same seed -> identical output; every child's time >= parent's; intervention-off == baseline exactly; monotonicity (stronger intervention never increases expected size over many seeds); `synthetic` is set at the type level and appears in every response envelope.

---

## Data Flow

### Flow A: Ingest (push, continuous)

```
Jetstream/Mastodon/Replay
   ──► adapter (reconnect, backoff, normalize -> NormalizedEvent)
   ──► select.py (seed filter for new roots; tracked-URI check for replies/quotes/reposts; drop rest)
   ──► bounded queue ──► writer: upsert accounts, INSERT events ON CONFLICT DO NOTHING,
                         create claim for link-share roots, UPDATE ingest_checkpoints  [one tx per batch]
   deletes ──► events.deleted_at = now(), text = NULL (privacy + honesty)
```

### Flow B: Enrich (poll, seconds)

```
resolve.py   : link orphans (UPDATE above), set root_resolved/depth, assign cascade_id (get-or-create by (platform, root_uri))
rollup.py    : recompute cascades counters + orphan_count; write cascade_features snapshots (as_of = now)
link_claims.py: match cascade root link_url_canonical <-> claims.url_canonical (joins news claims to social cascades)
scorer.py    : SELECT claims WITHOUT claim_scores for ACTIVE_MODEL_VERSION FOR UPDATE SKIP LOCKED -> Predictor -> INSERT
news refresh : (batch, quota-aware) GNews -> claims(kind='news_headline') via news_cache
```

### Flow C: Read (request/response)

```
web ──► (proxy) api /v1/cascades?sort=priority&cursor=...
          rate-limit dep ─► service ─► TTL cache (short) ─► repository (keyset pagination) ─► Postgres
        ◄── Pydantic response {data, next_cursor, model_version, as_of, synthetic:false, source_mode}
web ──► /v1/cascades/{id}/tree   ─► flat scan by cascade_id ─► domain.build_tree ─► capped JSON
web ──► /v1/cascades/{id}/timeline ─► SQL date_bin bucketing ─► counts
web ──► POST /v1/score {text}    ─► rate-limit (strict) ─► Predictor (in-process) ─► Prediction (not stored)
```

Priority for triage: `priority = f(calibrated score, recent growth rate, size)`, computed from stored columns; the formula is documented and versioned, not a black box.

### Flow D: Offline training (manual / CI-scheduled, never in the request path)

```
datasets (files, hash-pinned) ─► ml/train.py ─► calibrate (held-out) ─► ml/evaluate.py
   ├─ baseline 0 (inference.baseline_keywords) and model evaluated on the SAME split
   ├─ metrics.json (macro-F1, PR-AUC, ECE/reliability) + model_card.md  ──► committed
   └─ artifacts/<version>/ (model + manifest) ──► release asset / volume (not committed)
```

### Flow E (v2): Simulation

```
POST /v1/simulations {seed, params, intervention?} ─► sim.simulate (pure) ─► CascadeTree(synthetic=True)
   ─► (optionally) INSERT simulation_runs ─► response {synthetic: true, baseline, intervened, delta}
```

### State management (frontend)

Server state via TanStack Query (cache, retry, stale-while-revalidate, polling interval for the triage list; no websockets/SSE in v1), local UI state in component state or a tiny store. Every data view has explicit loading / error / empty / "partial (truncated, N orphans)" states. Types come from the generated OpenAPI schema.

---

## Caching and Rate Limiting: where each sits

| Concern | Layer | Mechanism (v1) | Notes |
|---------|-------|----------------|-------|
| TLS, static assets, coarse abuse | Edge reverse proxy (Caddy/nginx/host CDN) | Per-IP connection/request limits | The compose `web` service doubles as the proxy; same-origin `/v1` also removes CORS in prod (still restrict CORS to the known origin for dev) |
| Per-route rate limit | API (middleware / dependency, e.g. `slowapi`) | Token bucket keyed by client IP; tight on `POST /v1/score` and anything that can reach upstream; loose on reads; `429` + `Retry-After` | In-memory storage is **per process**: run a single uvicorn worker process (async) or accept N x limit. Configure forwarded-IP trust explicitly (`--forwarded-allow-ips`) or every client appears as the proxy IP |
| Upstream protection (GNews) | `news_cache` table (+ small in-process TTL front) | Cache key = hash(normalized query); positive TTL hours; negative-cache empties/errors briefly; **serve stale on upstream error with `stale: true`** | GNews free tier is reported at 100 requests/day, 1 req/s and, per third-party listings, restricted to non-commercial development/testing (LOW: aggregator sources; read gnews.io terms). Therefore: **the public demo must not proxy arbitrary user queries to GNews**; refresh a bounded query set from the worker on a schedule and serve from the DB |
| Score cache | Postgres `claim_scores` | PK `(claim_id, model_version)` | Natural cache and audit trail; no TTL needed, invalidated by version bump |
| Hot read cache | API in-process `TTLCache` + HTTP `Cache-Control: max-age` / `ETag` (keyed by `cascades.rolled_up_at`/`event_count`) | Seconds-scale TTL for list/summary endpoints | `ETag` lets the browser revalidate cheaply; tree endpoint keyed by `(cascade_id, event_count)` |
| Feature cache | `cascade_features` + in-process cache | `(cascade_id, feature_version, as_of)` | Versioned so stale features are detectable |
| Ingest-side limits | Adapter | Mastodon: honor `X-RateLimit-*` and back off; Jetstream: reconnect with jittered backoff, server-side collection filter | The worker is never behind the API limiter |
| Redis | **Not in v1** | Add only for multi-replica shared rate-limit counters or cross-process caches; ship as an optional compose profile | Mention in README as the known scale-out step |

---

## Scaling Considerations (realistic)

| Scale | Architecture adjustments |
|-------|--------------------------|
| Portfolio demo (a handful of concurrent viewers, tracked-root ingest) | Exactly the layout above: 1 Postgres, 1 api process, 1-2 worker processes, in-memory limiter and cache. This is the target. |
| ~1k-100k daily viewers | Add proper HTTP caching at the edge/CDN (list endpoints are cacheable for seconds), Redis for rate-limit counters, 2+ api replicas (read replicas of Postgres only if reads dominate), partial indexes reviewed with `EXPLAIN`. |
| Whole-network ingest | Server-side filtering, partition `events` by month on `observed_at`, move scoring to a queue with batched ONNX inference, consider a dedicated model service; at that point re-evaluate Kafka-class tooling. Out of scope. |

**What breaks first:** (1) Python-side filtering CPU on a firehose (mitigate: collection filters + compression at the source, tracked-root policy); (2) payload size and render cost of viral trees (cap/aggregate server-side, collapse in the UI); (3) rollup recompute cost as cascades grow (switch from full recompute to incremental by `last_event_at > rolled_up_at`); (4) per-process rate-limit state when replicas are added (Redis).

---

## Anti-Patterns

### Anti-Pattern 1: Ingest as a FastAPI background task or startup thread
**What people do:** Start the websocket consumer inside the API process.
**Why it's wrong:** Couples HTTP and ingest lifecycles, duplicates consumers under multiple uvicorn workers, hides crashes, and makes the API untestable without a live source.
**Do this instead:** Separate `worker` entrypoint/service; communicate through Postgres only.

### Anti-Pattern 2: Loading or training the model per request, or shipping training deps in the API image
**What people do:** `joblib.load` inside the route; install torch in the runtime image.
**Why it's wrong:** Latency spikes, memory bloat, slow cold starts, large attack surface.
**Do this instead:** Load once in `lifespan`; `ml/` is outside the runtime image; verify artifact hash.

### Anti-Pattern 3: Silent fallback to keyword rules (or fabricated data) when the model/upstream is down
**What people do:** Return a plausible 200 so "the frontend never breaks" (the existing `main.py` pattern).
**Why it's wrong:** Violates the project's Core Value; presents unmeasured output as analysis.
**Do this instead:** 502/503 with problem+json, `/ready` false, explicit `DEMO_MODE` + `synthetic: true` if demo data is ever served.

### Anti-Pattern 4: Cascade stored as a JSON blob (or a graph DB "because graphs")
**What people do:** One `jsonb` tree per cascade, or Neo4j for a forest.
**Why it's wrong:** Cannot ingest incrementally, cannot dedupe, cannot resolve orphans, cannot query by account/time; an extra datastore for a shallow forest.
**Do this instead:** Event rows with parent pointers; build the tree in the domain layer.

### Anti-Pattern 5: Trusting author-supplied timestamps and inventing missing parents
**What people do:** Sort by `createdAt`; attach orphans to the root to "complete" the tree.
**Why it's wrong:** Backdated records and out-of-order delivery produce impossible cascades (the old simulator's defect, now from real data) and fake completeness.
**Do this instead:** Order by `observed_at`; keep orphans as detached subtrees with `orphan_count`; property test "shuffled arrival -> identical final state".

### Anti-Pattern 6: Mixing observed and synthetic rows, or evaluating on live data
**What people do:** Put simulated events in `events` with a flag; "evaluate" on whatever was scored.
**Why it's wrong:** One missing `WHERE` leaks fabricated data into analytics or eval; live data has no ground truth.
**Do this instead:** Separate planes (see Executive Position 4 and 5).

### Anti-Pattern 7: Premature infrastructure
**What people do:** Kafka/Redis/Celery/microservices/websockets "for realism".
**Why it's wrong:** Burns the 4-6 week budget; reviewers grade correctness, evaluation and clarity.
**Do this instead:** Modular monolith, Postgres jobs, polling dashboard; document the scale-out path in the README.

### Anti-Pattern 8: Offset pagination and unbounded responses
**Do this instead:** Keyset cursors (`(last_event_at, id)`), hard caps with `truncated: true`.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Bluesky Jetstream | Websocket client in `ingest/sources/bluesky_jetstream.py`; filter to post + repost collections; resumable cursor; compression optional | MEDIUM: cursor = Unix microseconds, inclusive, at-least-once; endpoint/path/param names differ between community guides and newer docs, so pin them in the spike and add a contract test with a recorded frame |
| Mastodon (alternative) | Pull: public timelines/hashtag + `statuses/:id/context`; respect `X-RateLimit-*` | Weaker boost timing; instance-specific limits and terms; per-instance `platform` value |
| GNews | `news/gnews.py` behind `ClaimSource` port; env key; explicit timeout; status check; typed errors | Batch refresh from worker, not per user request; quota and non-commercial terms (LOW confidence) |
| Labelled datasets (e.g., fact-check / fake-news corpora) | `ml/datasets/` loaders, hash-pinned downloads | Domain shift: news headlines vs social posts; document in model card (see PITFALLS) |
| Artifact store (release asset / model hub) | `make fetch-model` + sha256 verify | Never commit weights |
| Hosting | Needs managed Postgres + container runtime | Free-tier constraints are a Phase 6 research item |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| worker <-> api | Postgres only | No HTTP, no queue; schema is the interface, migrations owned by one `migrate` step |
| api/worker <-> model | In-process `Predictor` | Artifact dir is the only coupling to `ml/` |
| ml/ -> runtime | Versioned artifact + committed metrics/model card | One shared `preprocess` function |
| api <-> web | JSON over `/v1`, OpenAPI-generated TS types | CI diff check on generated types |
| domain <-> everything | Imported, never importing | Enforced by import-linter |
| sim <-> observed data | Read-only calibration input; writes only `simulation_runs` | `synthetic` at type + envelope level |

### API surface sketch (`/v1`, typed, versioned)

| Method / Path | Purpose |
|---------------|---------|
| `GET /health`, `GET /ready` | Liveness; readiness (DB reachable, model loaded and hash-verified) |
| `GET /v1/status` | `source_mode`, ingest lag, counts, `model_version`, `as_of` |
| `GET /v1/cascades?sort=priority&claim_id=&cursor=` | Triage list (keyset pagination) |
| `GET /v1/cascades/{id}` | Summary + score + features + completeness (`orphan_count`, `first_seen_at`) |
| `GET /v1/cascades/{id}/tree` | Capped nodes+edges, `truncated` flag |
| `GET /v1/cascades/{id}/timeline` | Bucketed counts |
| `GET /v1/claims`, `GET /v1/claims/{id}` | Claims with current score and linked cascades |
| `POST /v1/score` | Ad-hoc text -> `Prediction` (not persisted; strict limit) |
| `POST /v1/simulations`, `GET /v1/simulations/{id}` (v2) | Seeded run + what-if; always `synthetic: true` |
| `GET /analyze` (temporary) | Legacy shim, deprecated, removed after dashboard ships |

Errors are `application/problem+json`; upstream failures map to 502/503; every payload carries `model_version`/`as_of` where relevant.

### docker-compose topology

`db` (healthcheck) -> `migrate` (one-shot `alembic upgrade head`, `service_completed_successfully`) -> `api`, `worker-ingest`, `worker-enrich` -> `web`. Default `INGEST_SOURCE=replay` so a clean clone runs with no secrets; live mode needs only env vars (GNews key optional). `ml` training is a separate `train` profile, off by default. Model artifact mounted read-only at `MODEL_DIR`.

---

## Suggested Build Order (every phase independently verifiable)

Maps onto the approved horizontal-layer roadmap (foundation, engineering, data, detection, dashboard, deploy) with two refinements: a **source spike before schema**, and **eval harness + baseline 0 before any model**.

```
P1 Foundation ─► P2 Eng skeleton ─┬─► P3 Data (spike -> schema -> ingest -> enrich -> read API) ─┐
                                  │                                                              ├─► P5 Dashboard ─► P6 Deploy
                                  └─► P4 Detection (eval harness -> baseline 0 -> model -> serve)┘
                                      (offline half has no dependency on P3; serving half needs P2 + P3 tables)
v2:  P7 Fine-tuned model (ONNX swap behind Predictor)   P8 Simulator -> what-if API -> UI panel
```

| # | Phase | Delivers | How it is independently verified | Depends on | Pitfall it retires |
|---|-------|----------|----------------------------------|------------|--------------------|
| 1 | Foundation / safety | Secrets out of repo, env config, honest 502/503 instead of fabricated 200, `.gitignore`, **characterization tests that pin current `/analyze` behaviour**, typed models | `pytest` green on characterization suite; secret scan clean; upstream-failure test returns 502/503 | - | Refactoring without a safety net; leaked/hardcoded keys |
| 2 | Engineering skeleton | `src/truthtrail` package (strangler: legacy shim now runs on new layout), pinned lock, ruff/mypy/pytest/pip-audit CI, Dockerfile, `/health`, `/ready`, restricted CORS, rate limit + GNews cache (in-process TTL first; the `news_cache` table lands with P3), import-linter | CI green; `docker build && run` + `/health`; 429 test; characterization suite unchanged | 1 | Flat-module import path; unpinned deps |
| 3a | **Source spike** (time-boxed) | Decision record: Bluesky vs Mastodon, endpoint/param names, rate limits, terms, record shapes, ~N minutes of **recorded fixture** (JSONL), selection-policy decision, throughput measurement | Written decision + fixture committed; a script replays it and prints event-kind counts | 2 | Building on a source whose terms/limits/shape were assumed |
| 3b | Schema + repositories | Alembic migrations for the schema above, repositories, `docker-compose` `db`+`migrate` | Integration tests vs real Postgres (CI service container): constraints, unique/idempotency, keyset queries; migration up/down | 3a | Late schema rework |
| 3c | Ingest worker | Adapters (`replay` first, then live), selection policy, batch writer, checkpoints, deletes | Replay fixture -> golden DB state; **ingest twice = identical counts**; kill/restart resumes from checkpoint; live smoke is a manual/optional check, not a CI gate | 3b | At-least-once duplicates; lost cursor |
| 3d | Enrich | Resolver, cascade assignment, rollup, features (pure), claim linking | **Property test: shuffled arrival order -> identical final state**; invariants (`observed_at` child >= parent, no cycles, `root_uri` consistent); orphan accounting; golden feature values on hand-built trees | 3c | Orphans, wrong roots, fake completeness |
| 3e | Read API `/v1` (cascades, tree, timeline, status) | Typed routers, keyset pagination, caps, ETag, OpenAPI snapshot | Contract tests; OpenAPI snapshot diff; truncation behaviour; load smoke on the replay dataset | 3d, 2 | Unbounded payloads; contract drift |
| 4a | Eval harness + **baseline 0** | Dataset loaders (hash-pinned), splits, metric code (macro-F1, PR-AUC, calibration/ECE), keyword rules scored | `make eval` reproduces baseline numbers deterministically; metrics unit-tested on toy inputs | 2 (parallelizable with 3) | Evaluating a model with no reference point |
| 4b | Offline model + artifact contract | TF-IDF + linear model (or equivalent), calibration, `manifest.json`, `metrics.json`, `model_card.md` | `make eval` reproduces committed metrics within tolerance; manifest hash check test | 4a | Train/serve skew; unverifiable claims |
| 4c | Online serving | `Predictor`, loader/verifier, lifespan load, `POST /v1/score`, `claim_scores` + scorer in enrich, `/ready` gating | Toy model built in a fixture (no weights committed): golden predictions; API refuses to be ready without artifact; skew test (shared `preprocess`); scoring idempotent per `(claim, version)` | 4b, 3b, 3e | Silent fallback; per-request model loading |
| 5 | Dashboard | `frontend/` Vite+React+TS, generated API types, triage list, cascade graph, timeline, risk badge with confidence, all states | Vitest component tests incl. loading/error/empty/truncated; Playwright smoke against compose + replay data; type-check against generated schema | 3e (badge needs 4c) | Contract drift; unhandled states |
| 6 | Deploy | Clean-clone `docker compose up`, hosting, README with architecture diagram, results table, limitations/ethics | Fresh-clone test in CI or clean VM; live URL smoke; README claims each trace to a command | 3-5 | "Works on my machine"; overclaiming |
| 7 (v2) | Fine-tuned model | Offline Colab/Kaggle training, ONNX export, `OnnxPredictor` | Same eval harness, new row in results table; API contract tests unchanged | 4 | Heavy deps in runtime |
| 8 (v2) | Simulator + what-if | `sim/`, `/v1/simulations`, UI "SYNTHETIC" panel | Determinism, parent-before-child, intervention-off == baseline, monotonicity property tests; `synthetic` in every response | 3d (domain + features) | Fabricated data presented as analysis |

**Ordering rationale:** The legacy code has no tests, so characterization tests must precede any move (P1). The Postgres schema is the highest-cost-to-change artifact, so the source spike must precede it (3a before 3b), and the recorded fixture it produces becomes the test fixture for every later data phase. Pure domain code (tree, features) comes before the API that serves it so it is property-tested in isolation. The eval harness and baseline 0 precede any model so improvement is always measured against a reference. The dashboard comes after a stable, snapshot-tested `/v1` contract, and can use generated types plus test-only fixtures (never shipped) to start before P4 finishes. P4a/P4b are independent of P3 and can interleave with it for scheduling flexibility.

---

## Research Flags for Phases

| Phase | Flag | Reason |
|-------|------|--------|
| 3a Source spike | **Deeper research required** | Jetstream endpoint/param versions, Mastodon boost-timing, terms of use, volumes, whether on-demand search by query is available without auth, privacy rules for storing posts in a fixture |
| 3d Enrich | Moderate | Root re-resolution when a repost/quote targets a reply whose own root arrives later; decide whether v1 merges cascades or leaves provisional roots flagged |
| 4b Model | Moderate | Dataset choice and domain shift (news headlines vs social posts); calibration and abstain-band method; leakage guard (only information available at prediction time) |
| 5 Dashboard | Moderate | Graph rendering library choice and large-tree strategy (collapse/aggregate); accessibility |
| 6 Deploy | **Deeper research required** | Hosting with managed Postgres on a free/cheap tier; worker process hosting; secrets handling |
| 8 Simulator | Moderate | Branching/Hawkes-style model choice and calibration from sparse observed cascades |
| 1, 2, 3b, 3c, 3e, 4a, 4c, 7 | Standard patterns | Well-trodden; unlikely to need phase research beyond library docs |

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Component boundaries / process model | HIGH | Standard modular-monolith + worker + Postgres pattern; matches constraints (solo, part-time, no GPU, free data) |
| Offline train / online serve split | HIGH | Widely used; artifact + manifest + shared preprocessing is the standard skew defence |
| Cascade modelling (forest, adjacency list, orphans) | HIGH for structure; MEDIUM for platform field names | Bluesky reply root/parent strong refs and quote/repost shapes confirmed via official docs summaries and community references; verify exact lexicon fields in the spike |
| Jetstream operational details | MEDIUM | Cursor/at-least-once from secondary summaries; two API generations referenced; official docs host was unreachable from this environment |
| Mastodon details | MEDIUM | Rate limits from official docs (2022 revision); boost-timing weakness is from knowledge, unverified |
| GNews limits/terms | LOW | Aggregator sites only; official terms not retrieved |
| Caching / rate-limit placement | HIGH for placement; MEDIUM for library specifics | Per-process limiter caveat is a known property of in-memory limiters |
| Build order | HIGH | Derived from dependency analysis of the above and the existing roadmap |

## Gaps to Address

- Exact current Jetstream API surface (path, parameter names, compression option, retention window for replay) and its terms: resolve in 3a.
- Whether an unauthenticated on-demand search (Bluesky AppView `searchPosts`, Mastodon search) is available and permitted: determines whether any query-driven UX is possible beyond the triage feed.
- Hosting choice and whether the worker can run continuously on a free tier: Phase 6 research; may force `replay`-only live demo plus documented live mode.
- Dataset selection and licence for training/evaluation (STACK/FEATURES researchers); architecture only requires hash-pinned, file-based loaders.
- Retention and privacy policy for stored public posts (handles, text): recommend TTL purge of `text` after N days and honoring deletes; owner decision needed.
- Whether v1 merges cascades when a provisional root is later resolved, or flags and defers.

## Sources

- Bluesky Jetstream repository (README, confirms design/location of docs): https://github.com/bluesky-social/jetstream (MEDIUM; consumer docs were not retrievable here)
- Jetstream consumer docs referenced by search results: https://bsky.network/docs/jetstream (host unreachable from this environment; details taken from search-result summaries) and community write-up https://jakelazaroff.com/words/drinking-from-the-bluesky-firehose/ (MEDIUM)
- atproto/Bluesky posts guide (reply root/parent strong refs, quote via `app.bsky.embed.record`): https://docs.bsky.app/docs/advanced-guides/posts and https://atproto.com/blog/create-post (search-result summaries; MEDIUM-HIGH)
- Mastodon API rate limits: https://docs.joinmastodon.org/api/rate-limits/ (HIGH for defaults, dated 2022; instance-specific)
- GNews plan limits via third-party listings (e.g., https://us.fitgap.com/products/gnews-api); official terms at gnews.io not retrieved (LOW)
- Existing codebase maps: `/home/user/TruthTrail/.planning/codebase/ARCHITECTURE.md`, `/home/user/TruthTrail/.planning/codebase/STRUCTURE.md`; project definition `/home/user/TruthTrail/.planning/PROJECT.md`
- Pattern knowledge (not individually sourced): adjacency-list trees with denormalized root in Postgres, `FOR UPDATE SKIP LOCKED` job queues, `ON CONFLICT DO NOTHING` idempotent ingest, ONNX Runtime CPU serving, common-random-numbers variance reduction for paired what-if simulation (MEDIUM-HIGH, standard practice)

---
*Architecture research for: misinformation early-warning system (TruthTrail)*
*Researched: 2026-10-11*
