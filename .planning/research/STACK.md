# Stack Research

**Domain:** Misinformation early-warning system (open-source social propagation ingest, text risk classifier, cascade visualization), subsequent milestone on an existing FastAPI prototype
**Researched:** 2026-10-11
**Overall confidence:** MEDIUM-HIGH (versions and data-source facts verified against registries and primary docs; items I could not verify are listed in "Unverified / Needs a Spike" and tagged LOW)

Scope: this file covers only what the target features need on top of the existing prototype (see `.planning/codebase/STACK.md`). Dev environment: Python 3.13, Node 22. All versions below were read from PyPI/npm on 2026-10-11, and the Python set was checked to resolve together on 3.13 with `uv pip compile`. The npm set was checked with `npm install --package-lock-only`.

Confidence legend: HIGH = verified from a registry or primary vendor doc this session. MEDIUM = verified in part, or standard practice I did not re-verify. LOW = inferred or unverified; do not treat as settled.

## Headline Decisions (read these first)

1. **Propagation source: Bluesky, not Mastodon.** Bluesky's Jetstream live tail is free, unauthenticated and unmetered. Reposts, replies and quotes are first-class records with explicit parent/subject URIs and `createdAt`, which is exactly what a cascade needs. Mastodon's `reblogged_by` returns only account lists (no per-boost timestamp), and the REST rate limit is 300 calls per 5 minutes. Mastodon is a v2 add-on at most.
2. **Collect forward in time, not backward.** Jetstream filters only by collection and DID, never by text or subject. Historical repost cascades therefore cost a metered, API-key-gated replay of the whole collection. Plan on a seeded, bounded collector (seed posts from authenticated `searchPosts`, then track their reposts, replies and quotes going forward). Do not promise "any claim, any time".
3. **Text classifier trains on LIAR (primary) with PHEME leave-one-event-out as the second benchmark.** Neither needs the X API. FakeNewsNet and CoAID ship IDs that need X API credentials to rehydrate, so only their title/content CSV columns are usable.
4. **One Postgres driver: psycopg 3 (sync for Alembic, async for the app) with SQLAlchemy 2.1.** SQLAlchemy 2.1 made psycopg 3 its default PostgreSQL driver. Skip asyncpg.
5. **Frontend cascade view is custom D3 layout primitives rendered by React; Recharts for the timeline.** No off-the-shelf graph library gives a time-aligned reply/repost tree, and the one WebGL option (Sigma 4) has a peer-dependency mismatch with its React wrapper.
6. **TypeScript 7 + Biome, not typescript-eslint.** TS 7.0.2 is `latest` on npm, but `typescript-eslint` (peer `<6.1.0`) and `openapi-typescript` (peer `^5.x`) both refuse to install against it (verified). Fallback is `typescript@6.0.3`.
7. **Deploy as one Docker image (FastAPI serves the built SPA) on Render free, with Neon free for Postgres and a GitHub Actions scheduled job as the collector.** Render's free web service sleeps after 15 minutes and cannot run background workers, and Render's free Postgres expires after 30 days (all verified), so neither the always-on websocket worker nor the Render database fits.

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| Python | 3.13 (dev env) | Runtime | Matches the dev environment. Every dependency below supports 3.13. `atproto` caps at `<3.15`; `networkx 3.7` excludes 3.14.1. | HIGH |
| FastAPI | 0.143.0 | HTTP API | Already the project's backend. Pydantic v2 native, OpenAPI feeds the TS client. Pin the minor (0.x versioning). | HIGH |
| Pydantic / pydantic-settings | 2.14.0 / 2.15.0 | Response models, env config | Typed responses and env-only secrets are explicit v1 requirements. | HIGH |
| Uvicorn | 0.54.0 (`uvicorn[standard]`) | ASGI server | Already used by the prototype. | HIGH |
| SQLAlchemy | 2.1.4 (`sqlalchemy[asyncio]`) | ORM / Core | Python >=3.11. 2.1 defaults to psycopg 3 and requires the `[asyncio]` extra for greenlet (verified in the 2.1 migration notes). | HIGH |
| Alembic | 1.20.0 | Migrations | Standard partner of SQLAlchemy. Use `alembic check` in CI to prove models and migrations agree. | HIGH |
| psycopg | 3.3.6 (`psycopg[binary,pool]`) | Postgres driver (sync + async) | One driver for Alembic (sync) and the app (async). URL scheme `postgresql+psycopg://`. | HIGH |
| PostgreSQL | 17 | Storage | Neon supports 14-18 (verified). Pin 17 in docker-compose, CI service container and Neon so dev matches prod. | HIGH |
| atproto (MarshalX SDK) | 0.0.72 (pin exactly) | Bluesky AppView calls + Jetstream v2 client | Wheel verified to contain `atproto_jetstream` (live tail, `replay()`, `snapshot()`) plus `network.bsky.jetstream.*` models. Pre-1.0, so pin exactly and hide behind a `PropagationSource` adapter. | HIGH (exists), MEDIUM (stability) |
| httpx | 0.28.1 | Outbound HTTP (GNews etc.) | Replaces `requests`: async, explicit timeouts. Also what FastAPI's TestClient uses. Slow release cadence (last release Dec 2024) but the standard choice. | HIGH |
| scikit-learn | 1.9.1 | TF-IDF + logistic regression baseline, calibration, metrics | Verified on 3.13: `FrozenEstimator`, `CalibratedClassifierCV`, `CalibrationDisplay`, `TunedThresholdClassifierCV`, `StratifiedGroupKFold`, `average_precision_score`, `brier_score_loss` all import. | HIGH |
| React | 19.3.0 | Dashboard UI | Current stable. | HIGH |
| Vite | 8.3.4 | Frontend build/dev server | Node engine `^20.19 || >=22.12` (Node 22 OK). `@vitejs/plugin-react 6.1.2` requires Vite ^8. | HIGH |
| TypeScript | 7.0.2 (fallback 6.0.3) | Type checking (`tsc --noEmit`) | `latest` on npm. Vite transpiles on its own, so tsc is only the type gate. See compatibility warnings. | MEDIUM |
| Docker + Compose | n/a | Local and deploy packaging | One multi-stage image: Node stage builds the SPA, Python stage serves API + static files. | MEDIUM |

### (a) Propagation Data Ingest (free sources)

#### Bluesky / AT Protocol (RECOMMENDED primary source)

Verified from `bsky.network/docs/jetstream`, `/jetstream-replay`, the 2026-08-13 AT Protocol announcement, and the `atproto.blue` SDK docs.

| Item | Fact | Confidence |
|------|------|------------|
| Live tail endpoints | v2: `wss://jetstream.us-east.bsky.network`, `wss://jetstream.us-west.bsky.network`. v1: `jetstream1.us-west`, `jetstream2.us-east` (still running "for a while", frozen protocol). **Build on v2.** | HIGH |
| Live tail auth / metering | None. "We have no plans to introduce an auth requirement for the live stream." | HIGH |
| Path / protocol | `wss://<host>/xrpc/network.bsky.jetstream.subscribeEvents`, WebSocket subprotocol `xrpc.v1.json`. Envelope `{"$type":"message","payload":{...}}`. | HIGH |
| Filters | `collections` (repeatable, `app.bsky.feed.*` wildcard allowed), `dids` (repeatable), `kinds` (`commit`, `identity`, `account`, `sync`). Limits: 100 collections, 10,000 DIDs per subscription. Collection filter applies to commits only; identity/account/sync events always flow. | HIGH |
| Cascade-relevant records | `app.bsky.feed.post` (replies carry `reply.root` / `reply.parent` URIs; quotes carry an embedded record), `app.bsky.feed.repost` (`subject.uri`, `createdAt`). Do not subscribe to `app.bsky.feed.like` (volume, no cascade value). | HIGH |
| Delivery semantics | At-least-once, in order per DID. Cursor is `seq`, inclusive, so dedupe on the record `at://` URI and make writes idempotent (`INSERT ... ON CONFLICT DO NOTHING`). Live lookback window is 36 hours on Bluesky-hosted instances. | HIGH |
| Deletes | `delete` commits carry no record. Account deletion arrives as an `account` event (`active:false`, `status:"deleted"`) and must remove that account's records. Bluesky Developer Guidelines: "All services must have a method for deleting content a user has requested to be deleted." The collector must process deletes. | HIGH |
| Replay / snapshot (history) | v2 only. Needs an API key (created at `bsky.network/account`) on the HTTP calls. Metered in response bytes, `429` with `Retry-After` when exceeded, resumable via HTTP `Range`. **Filters are by DID and collection only**, so replaying `app.bsky.feed.repost` means downloading all reposts network-wide. A community report observed roughly 2 MB/s quota refill; this is unofficial. | HIGH (mechanics), LOW (quota numbers, whether free accounts have a cap) |
| Integrity | Jetstream carries no repository signatures or MST proofs, so data cannot be cryptographically verified (SDK docs warning). Acceptable for analysis, say so in the limitations section. | HIGH |
| Hosted-account rate limit | 3,000 requests per 5 minutes overall (PDS/hosted account). AppView limits are described only as "generous", with no published number. | HIGH (3000), LOW (AppView) |
| Seeding by claim | `app.bsky.feed.searchPosts` accepts `q`, `url`, `domain`, `tag`, `lang`, `since`, `until`, `author`, `limit<=100`. **`public.api.bsky.app` deliberately load-sheds this endpoint with 403** (maintainer-confirmed in bsky-docs issue #332). Use an authenticated session (free Bluesky account + app password, from env vars). Do NOT use the URL-capitalization trick that circumvents the 403. | HIGH |
| Thread / quotes / reposters | `getPostThread` (no auth; `depth` max 1000, default 6; `parentHeight` max 1000, default 80). `getQuotes` (`limit<=100`) returns post views with `record.createdAt`. `getRepostedBy` returns `profileView[]`, whose only timestamp is the profile's `indexedAt`, **not the repost time** (verified from the lexicon JSON). So repost timing is only available from Jetstream repost records. | HIGH |
| Terms | Bluesky ToS (14 Aug 2025) and the Developer Guidelines contain no explicit research/ML-scraping clause that I could find; the privacy notice states user content is public. Absence is not a license grant. Mitigation: store minimal fields, honor deletes, never republish raw post text beyond what the UI displays, set a descriptive User-Agent with a contact address. | LOW (could not find a data-use clause; treat as unresolved) |

**Python client:** `atproto==0.0.72` (MarshalX). Use `atproto_jetstream.AsyncJetstreamClient` for the live tail (it tracks the cursor, drops redelivered events, reconnects after 60 s of silence, compresses by default; the SDK docs advertise dict-zstd with about 65% less bandwidth), and `atproto.AsyncClient` for `searchPosts` / `getPostThread` / `getQuotes`. Fallback with zero SDK risk: plain `websockets` 17.2 plus `json`, which Bluesky documents with a Python example.

**Consequence for architecture:** run the collector as a bounded batch job (N minutes of live tail, tracked-URI set held in Postgres), not as a 24/7 worker, because the chosen free hosts cannot run one (see deploy table).

#### Mastodon (SECONDARY / v2 only)

| Item | Fact | Confidence |
|------|------|------------|
| Client | `Mastodon.py` 2.2.2 | HIGH |
| REST rate limit | 300 calls per 5 minutes per account and per IP; 30 media uploads per 30 min etc. Headers `X-RateLimit-*`. | HIGH |
| Public timelines | Public, but require an app token with `read:statuses` when the instance disables public preview; unauthenticated remote-status access can also be switched off (401). Page size max 40. | HIGH |
| Thread context | `GET /api/v1/statuses/:id/context`: unauthenticated max 40 ancestors, 60 descendants, depth 20; authenticated up to 4,096 each, unlimited depth. | HIGH |
| Boosters / favouriters | `reblogged_by` / `favourited_by` return account lists, max 80 per page. The API returns Account entities, which carry no boost time. | MEDIUM (inferred from the entity type; not verified on the page) |
| Federation / ToS | Each instance sets its own rules; a single server sees only the slice of the fediverse it federates with, so cascades are truncated by construction. | MEDIUM |

Verdict: Mastodon cascades have no boost timestamps via REST and are partial by federation, so it cannot support a faithful timeline. Revisit only for a v2 "second platform" story.

### (b) Labelled Datasets Usable Without the X/Twitter API

| Dataset | What it actually ships | License / terms | Rehydration problem | Use it for |
|---------|------------------------|-----------------|---------------------|------------|
| **LIAR** (Wang, ACL 2017) | 12.8K PolitiFact statements, six truth labels, speaker/party/context metadata. Text only, no propagation. Hugging Face `ucsbai/liar`, revision `ff3a1531...`, last modified 2024-01-18. | HF metadata says `license: unknown`. Download in a script; do not commit or redistribute. | None. | **Primary text classifier benchmark.** Use the official splits. Binary mapping (pants-fire/false/barely-true vs the rest) is a convention, so document it and also report 6-way. |
| **PHEME** (figshare 6392078, 44.38 MB; earlier 5-event set figshare 4010619) | 9 breaking-news events. Per event: `rumours/` and `non-rumours/` folders named by source tweet ID, each with `source-tweet/`, `reactions/` (replies), `structure.json` (reply tree) and `annotation.json` (veracity True/False/Unverified). The 5-event set reports e.g. Charlie Hebdo 458 rumours / 1,621 non-rumours. | Annotations CC BY 4.0; "Twitter retains the ownership and rights of the content of the tweets". | None for structure and annotations: the download includes the tweets (I did not open the archive; confirm tweet JSON is present in the spike). | **Only reply-tree cascade dataset here that works offline**, for the cascade demo, structural features, and **leave-one-event-out** evaluation (`LeaveOneGroupOut`). Reactions are replies, not retweets. |
| **FakeNewsNet** (KaiDMML) | Four CSVs (`politifact_fake/real`, `gossipcop_fake/real`) with columns `id, news_url, title, tweet_ids`; verified header. No article body in the CSV. Last commit Sep 2021. | No LICENSE file in the repo (raw URL 404). Treat as research-only; docs recommend non-commercial use. | **Tweets, retweets and user data all require X API credentials** (README). Article text needs scraping `news_url` (link rot). | Titles only, as a secondary, out-of-domain test set. **Not** usable for cascades. GossipCop is celebrity gossip, so it shifts domain sharply. |
| **CoAID** (cuilimeng) | News CSVs include `title`, `content`, `abstract`, `publish_date`, fact-check URL (verified header); 5,216 news, 296,752 engagements, 958 posts; versions through v0.4 (Jan 2021). | No LICENSE file in the repo (404). Cite the paper; do not redistribute. | Engagement tweet IDs need hydration (X API). | COVID-only, 2020-era out-of-domain test of text transfer. Do not train the headline model on it. |
| **Twitter15 / Twitter16** (Ma et al.) | Propagation trees (user, tweet ID, time) plus labelled source tweets; counts differ across papers (e.g. 1,490 / 818 events vs 739 / 404 source tweets). | Unclear. | Reply/retweet text is not included, only IDs and times. | Structure-only cascade features in v2. Verify exact contents and license in a spike. |
| **UPFD** (PyG `torch_geometric.datasets.UPFD`) | Pre-built tree-structured propagation graphs for PolitiFact/GossipCop with precomputed node features (no raw text). Derived from FakeNewsNet. | Inherits FakeNewsNet terms. | None. | v2 graph-model experiments only, not the text classifier. |
| **MuMiN** | 12,914 fact-checked claims, 21.6M tweets. | CC BY-NC 4.0. | Distributed as IDs for Twitter hydration, so unusable without the X API. | Exclude. |

**Avoid:** ISOT / the Kaggle "Fake and Real News" set and WELFake. They are widely reported to leak source style (e.g. outlet boilerplate), which inflates scores; I did not verify this here (LOW), so if a reviewer asks, the safe answer is "excluded on known leakage risk, unverified by us".

**Hard truth to write into the README:** there is no labelled misinformation dataset collected on Bluesky that I could find. The classifier is trained on political statements (LIAR) and tested on Twitter rumours (PHEME), then applied to Bluesky posts and news headlines. That is domain shift. Report it, and treat "weakly labelled Bluesky eval set from fact-check-linked posts" as a v2 item. Expect modest absolute scores on LIAR (LOW; literature numbers for text-only models are not high). The credibility story is the honest, reproducible measurement, not the number.

### (c) ML and Evaluation Libraries

| Library | Version | Purpose | Notes |
|---------|---------|---------|-------|
| scikit-learn | 1.9.1 | `Pipeline(TfidfVectorizer, LogisticRegression)`, calibration, metrics | `CalibratedClassifierCV(FrozenEstimator(fitted_pipe), method="sigmoid"\|"isotonic")` on a held-out calibration split (the old `cv="prefit"` pattern is replaced by `FrozenEstimator`; verified in 1.9.1). `TunedThresholdClassifierCV` for an operating point. `StratifiedGroupKFold` / `LeaveOneGroupOut` for grouped splits. |
| scipy | 1.18.1 | `scipy.stats.bootstrap` for confidence intervals on macro-F1 and PR-AUC | Reports intervals, not single numbers. Needs Python >=3.12. |
| numpy | 2.5.4 | Arrays | Needs Python >=3.12. |
| pandas | 3.0.6 | Dataset loading in training scripts only | Major version 3 (stricter string/copy semantics); keep it out of the API image. |
| matplotlib | 3.11.2 | Reliability diagrams, PR curves saved to `reports/` | Training group only. |
| joblib | 1.6.0 | Persist the sklearn pipeline | Pickle-based: load only artifacts you built yourself and check a SHA-256. `skops` 0.16.0 is the safer persistence format if artifacts ever come from outside. |
| huggingface_hub | latest | Download LIAR at a pinned revision | Pin the dataset commit hash in code for reproducibility. |
| networkx | 3.7 | v2 cascade features (depth, breadth, Wiener index / structural virality) | Needs Python >=3.12 and excludes 3.14.1. |

**Expected-calibration-error:** scikit-learn has no ECE function (checked `dir(sklearn.calibration)`), so write a small, unit-tested `ece()` helper (equal-width bins, plus Brier score and a reliability diagram). Do not add `netcal` 1.4.0 just for this.

**Metrics to report (matches the PROJECT.md requirement):** macro-F1, PR-AUC (`average_precision_score`), Brier, ECE with a reliability diagram, bootstrap 95% CIs, and the old keyword rules as "baseline 0", all on identical splits. Write results to a committed `reports/metrics.json` plus a model card, and render the README results table from that file (no hand-typed numbers).

**v2 transformer fine-tune (Colab/Kaggle, offline):**

| Library | Version | Notes |
|---------|---------|-------|
| transformers | 5.19.0 | **Major version 5 is PyTorch-only** (TensorFlow and Flax removed). Read `MIGRATION_GUIDE_V5.md` at phase start; older tutorials will not match. |
| torch | 2.14.1 | CPU-only is fine for inference; install from the PyTorch CPU index for the API. Keep it out of the default API image. |
| datasets / accelerate | 5.1.0 / 1.15.0 | Optional; plain `Trainer` plus pandas is enough for LIAR-sized data. |
| Model choice | `distilbert-base-uncased` first, `roberta-base` if budget allows | Fits a free Colab T4; `max_length=128` suffices for statements. |
| Calibration | Temperature scaling on validation logits | Small torch routine, evaluated with the same ECE helper. |

Do not use the `evaluate` package: 0.4.6 was last released 2025-09-18 and scikit-learn metrics cover everything. Do not use MLflow 3.17.0 here; a committed `metrics.json` plus model card is lighter and more reviewable. **Weights are never committed** (PROJECT.md): publish to a Hugging Face Hub model repo and download at build or runtime. The TF-IDF + LR baseline is small and trains in seconds, so retrain it inside the Docker build or a release job instead of storing it.

**Serving the v2 model:** a 512 MB-class free web service cannot comfortably hold torch plus a transformer. Serve v2 from a Hugging Face Docker Space (free CPU: 2 vCPU, 16 GB RAM, verified) or keep v2 as an evaluated-offline result with the live demo on the TF-IDF model. Decide in the v2 planning phase; the RAM of Render's free tier is not stated on the doc page I read (LOW).

### (d) Postgres Access and Migrations

**Decision: async SQLAlchemy 2.1 + psycopg 3 for the app and collector; sync engine (same driver) for Alembic.**

Why async: the collector is a WebSocket consumer (inherently async) and the API is I/O-bound reads. One async stack avoids threadpool juggling. Why psycopg 3 and not asyncpg: SQLAlchemy 2.1 made psycopg 3 the default PostgreSQL driver, one package serves both sync and async URLs (`postgresql+psycopg://`), and it avoids asyncpg's prepared-statement problems behind transaction poolers.

| Concern | Recommendation |
|---------|----------------|
| Install | `sqlalchemy[asyncio]` (2.1 no longer installs greenlet by default). |
| Session settings | `async_sessionmaker(expire_on_commit=False)`; no lazy loading in async code (use `selectinload` / explicit queries). |
| Models | `Mapped[...]` typed declarative models; no SQLAlchemy mypy plugin (2.x is natively typed). Note 2.1 changes: dataclass defaults, unconditional autoflush, `filter_by` ambiguity errors. |
| Migrations | `alembic` with `compare_type=True`, a `MetaData(naming_convention=...)`, and CI steps `alembic upgrade head` then `alembic check` on a Postgres service container. |
| Idempotent ingest | Primary key or unique constraint on the record `at://` URI; `INSERT ... ON CONFLICT DO NOTHING` (delivery is at-least-once). Tombstone or hard-delete on `delete`/account-deletion events. |
| Cascade storage | Adjacency list (`event_id`, `parent_event_id`, `root_event_id`, `kind`, `platform`, `ts`) plus `JSONB` for raw payload; query subtrees with `WITH RECURSIVE`. Index `(root_event_id, ts)`. Keeps the existing event-record data model. No graph database. |
| Neon pooling (LOW, verify at deploy) | Run migrations over the direct (non-pooled) connection string. For the app, start with `connect_args={"prepare_threshold": None}` if using Neon's pooled endpoint, to avoid server-side prepared statements under a transaction pooler. |
| Test database | CI `services: postgres:17`; locally `docker compose up db`. `testcontainers` 4.15.0 is optional (needs a Docker daemon). |
| Async tests | `pytest-asyncio` 1.4.0 with `asyncio_mode = "auto"`. |

### (e) Frontend: React + TypeScript + Vite

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| @tanstack/react-query | 5.104.1 | Server state, retries, polling, loading/error/empty states | Directly supports the "loading/error/empty states" requirement and a cold-starting API. |
| Recharts | 3.10.1 | Timeline (events per time bucket), risk distribution | Already in the repo's `package.json` (^3.7.0); React 19 peers satisfied. Declarative and enough for time series. |
| d3-hierarchy / d3-scale / d3-zoom / d3-selection | 3.1.2 / 4.0.2 / 3.0.0 / 3.0.0 | **Cascade graph layout and zoom**, rendered as React SVG | Cascades are trees. Encode elapsed time on x, tidy-tree slot on y, node radius from influence, colour/shape from event kind (post, reply, quote, repost). Import individual `d3-*` modules, not the `d3` bundle. These packages are finished (unchanged since 2022-2023) and stable. `@types/d3-hierarchy` 3.1.7. |
| Tailwind CSS | 4.3.3 (`@tailwindcss/vite`) | Styling | Vite plugin, no config sprawl. UI kit choice belongs to the later UI-spec phase. |
| zod | 4.6.5 | Runtime-validate API responses at the boundary | "Parse, don't trust" supports the project rule that nothing fabricated is displayed. |
| @hey-api/openapi-ts | 0.99.0 (pin exact) | Generate a typed client from FastAPI's OpenAPI | Peer TS `>=5.5.3 || >=6.0.0`; resolved with TS 7 in my test. Pre-1.0, so pin it; fallback is hand-written types plus zod. |

**Cascade rendering limits (be honest in the UI):** SVG is fine to roughly 2,000 nodes. Real cascades have heavy fan-out (thousands of reposts of one root), so cap server-side to the top N nodes by influence and label it "showing N of M events". Switch to canvas only if profiling demands it.

**Graph library comparison**

| Library | Version | Verdict |
|---------|---------|---------|
| Custom D3 primitives (recommended) | see above | Only way to get a time-aligned cascade tree; about 200 lines; fully accessible and testable. |
| react-force-graph-2d | 1.29.2 (active, modified 2026-09-29) | Best fallback for a quick force-directed view or very large graphs (canvas). Force layout hides time and parent-child order, which is the point of a cascade. |
| @xyflow/react (React Flow) | 12.12.0 | Polished node-editor UX, but one DOM element per node and needs dagre/ELK layout; poor fit for fan-out of thousands. |
| Cytoscape.js + react-cytoscapejs | 3.34.3 / 2.0.0 | Mature and feature-rich, but a large imperative API for little benefit here. |
| Sigma.js | 4.0.0 (published 2026-10-08) | WebGL for 10k+ nodes. `@react-sigma/core` 5.0.6 peers `sigma ^3.0.2`, so the wrapper does not match v4. Avoid unless you drop the wrapper. |
| ECharts | 6.1.0 | Powerful (has `tree` and `graph` series) but a second charting paradigm next to Recharts; `echarts-for-react` 3.0.6 is a thin wrapper. |

**Routing:** skip React Router for v1 (single dashboard). `react-router` 8.4.0 requires Node `>=22.22.0` in its engines field.

**Starting point:** the existing root `package.json` / lockfile contain only Recharts plus unrelated leftovers (react-redux, RTK). Re-scaffold with `npm create vite@latest` (`create-vite` 9.2.1) in `frontend/`, template `react-ts`, and delete the root manifest.

**Node-version gotcha (verified):** with Node 22.22.0, installing `jsdom` 30.1.2 triggered an `EBADENGINE` warning (its dependency `w3c-xmlserializer@6.0.0` wants `^22.22.2`). Either upgrade Node 22 to the latest patch (set `.nvmrc` to `22` and CI `node-version: 22`) or use `happy-dom` 20.14.6 as the Vitest DOM.

### (f) Tooling, CI and Deploy

#### Development tools

| Tool | Version | Purpose | Notes |
|------|---------|---------|-------|
| uv | 0.13.0 on PyPI (dev box has 0.11.32) | Env, lockfile, Python pin | `pyproject.toml` + `uv.lock` + `.python-version` (3.13). CI uses `uv sync --locked`. Use `[dependency-groups]` (`dev`, `train`, `nlp`). `uv audit` exists in 0.11.32 (maturity not verified), so use `pip-audit` as the gate. |
| Ruff | 0.17.0 | Lint + format | Replaces black/isort/flake8. |
| mypy | 2.4.0 | Type check, strict, with `pydantic.mypy` plugin | Preferred gate. `ty` 0.0.86 is pre-1.0; not a CI gate. `pyright` 1.1.414 is a fine alternative if mypy plugin friction appears. |
| pytest / pytest-asyncio / pytest-cov | 9.1.1 / 1.4.0 / 7.1.0 | Tests | Characterization tests of the current endpoint first, then simulator/ingest invariants. |
| respx | 0.23.1 | Mock httpx (GNews, AppView) | Stops tests hitting the network. |
| hypothesis | 6.169.0 | Property tests (cascade invariants: child timestamp >= parent, tree acyclic; ECE bounds) | Directly addresses the prototype's "40% of events precede their parent" bug. |
| pip-audit | 2.10.1 | Dependency vulnerability scan | `pypa/gh-action-pip-audit@v1.1.0` per its README. |
| Biome | 2.5.15 | JS/TS lint + format | Chosen because `typescript-eslint` cannot install against TS 7 (peer `<6.1.0`). Alternative if you need type-aware lint: `typescript@6.0.3` + ESLint 10.12.0 + typescript-eslint 8.71.1 (resolved cleanly in my test). |
| Vitest / Testing Library | 5.0.3 / 16.3.3 | Frontend unit/component tests | Vitest 5 supports Vite 6-8. |
| Playwright + axe | 1.64.0 / `@axe-core/playwright` 4.13.0 | One e2e smoke + accessibility check | Run against the built image in CI. |
| msw | 3.0.3 | API mocking in tests | Optional; Node >=22.12. |

#### GitHub Actions (versions read from each action's README on 2026-10-11)

`actions/checkout@v7`, `actions/setup-node@v7`, `actions/upload-artifact@v7`, `actions/cache@v6`, `docker/build-push-action@v7`, `docker/setup-buildx-action@v4`, `pypa/gh-action-pip-audit@v1.1.0`. `astral-sh/setup-uv` documents pinning to a full commit SHA rather than a major tag, so pin third-party actions by SHA and let Dependabot (ecosystems: `uv`, `npm`, `github-actions`) bump them (MEDIUM; confirm Dependabot's `uv` ecosystem support when writing the config).

Suggested workflows: **ci** (backend: ruff, format check, mypy, pytest with Postgres 17 service, alembic upgrade + check, pip-audit; frontend: `npm ci`, `biome ci`, `tsc --noEmit`, vitest, `vite build`, `npm audit --omit=dev`; docker: build + compose smoke test of `/health`), **eval** (`workflow_dispatch` plus weekly: train, evaluate, upload `metrics.json`; LIAR is small enough to run in CI), **collect** (scheduled bounded Jetstream collection into Neon via secrets `DATABASE_URL`, `BSKY_HANDLE`, `BSKY_APP_PASSWORD`). GitHub disables scheduled workflows after 60 days of repo inactivity and public-repo Actions minutes are free (MEDIUM; both from general knowledge, not re-verified).

#### Deploy targets (free tier facts verified from each vendor's docs on 2026-10-11)

| Target | Verified facts | Fit |
|--------|----------------|-----|
| **Neon Free (Postgres)** | 1 GB storage/project, 100 CU-hours/project/month, autosuspend after 5 min (cannot be disabled), 100 projects, 10 branches, 5 GB egress, 6-hour history. Postgres 14-18. | **Use for the database.** Wakes on connect, so first query after idle is slower; the UI must tolerate it. |
| **Render Free (web service)** | 750 instance-hours/workspace/month; spins down after 15 min without inbound traffic (HTTP requests and WebSocket messages count as traffic); no persistent disk; single instance; cannot run one-off jobs or background workers; outbound SMTP blocked. | **Use for the single API+SPA image.** Expect a cold start after idle; build a "server waking up" state into the dashboard. |
| Render Free Postgres | Expires 30 days after creation; 1 GB; no backups. | **Do not use.** A portfolio demo must stay up. |
| Hugging Face Spaces (free CPU, Docker) | 2 vCPU, 16 GB RAM, 50 GB non-persistent disk; sleeps when unused. | Candidate host for v2 transformer inference, or an alternative API host. Docker Space port convention (7860) is from memory (MEDIUM). |
| Google Cloud Run | Free monthly: 2M requests, 180,000 vCPU-seconds, 360,000 GiB-seconds. Needs a billing account (not stated on the page I read). | Credible fallback if a card is acceptable; set a budget alert. |
| Fly.io | New organizations have no free tier; trial is up to 2 machine-hours or 7 days. | **Avoid.** |
| Static hosting (Cloudflare Pages, GitHub Pages, Vercel Hobby) | Not verified this session. | Not needed if FastAPI serves the SPA. |

**Why one image:** FastAPI serves `/api/*` and the built SPA from the same origin, so the production CORS allow-list can be empty and `docker compose up` from a clean clone is the same artifact as the deploy. In development, use the Vite proxy to `localhost:8000` and a narrow dev-origin CORS list.

**Dockerfile pattern (MEDIUM, standard practice):** multi-stage; Node 22 stage runs `npm ci && npm run build`; Python 3.13-slim stage installs `uv` and runs `uv sync --locked --no-dev`; non-root user; `HEALTHCHECK` on `/health`; install only default dependencies (no `train`/`nlp` groups).

## Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tenacity | 9.2.1 | Retry with backoff | AppView and GNews calls; reconnect logic around Jetstream if not using the SDK's built-in reconnect. |
| slowapi | 0.1.10 | Per-IP rate limiting for the public API | In-memory counters, correct for the single-instance deployment. Move to Redis only if you scale out. |
| websockets | 17.2 | Raw Jetstream client fallback | If `atproto` pre-1.0 churn becomes a problem. Already a transitive dependency. |
| structlog | 26.1.0 | Structured logs | Optional; stdlib `logging` with a JSON formatter is enough. |
| orjson | 3.13.0 | Fast JSON | Optional; only if profiling shows JSON parsing of the stream is hot. |
| Mastodon.py | 2.2.2 | Mastodon client | Only if a v2 second-platform story is built. |
| networkx | 3.7 | Cascade metrics | v2 cascade features; training/analysis group, optional in the API. |
| skops | 0.16.0 | Safer model persistence | If model artifacts are ever fetched from outside the build. |
| testcontainers | 4.15.0 | Disposable Postgres in tests | Optional; the CI service container is simpler. |
| Faker / polyfactory | 40.43.0 / 3.3.0 | Test data | Only for test fixtures, never for the live path. |

## Installation

```toml
# pyproject.toml (illustrative; uv.lock pins exact versions)
[project]
name = "truthtrail"
requires-python = ">=3.13,<3.14"
dependencies = [
  "fastapi>=0.143,<0.144",
  "uvicorn[standard]>=0.54,<0.55",
  "pydantic>=2.14,<3",
  "pydantic-settings>=2.15,<3",
  "sqlalchemy[asyncio]>=2.1.4,<2.2",
  "alembic>=1.20,<1.21",
  "psycopg[binary,pool]>=3.3.6,<3.4",
  "httpx>=0.28.1,<0.29",
  "atproto==0.0.72",
  "tenacity>=9.2,<10",
  "slowapi>=0.1.10,<0.2",
  "scikit-learn>=1.9.1,<1.10",   # serving the TF-IDF+LR pipeline
  "joblib>=1.6,<2",
]

[dependency-groups]
dev   = ["pytest>=9.1", "pytest-asyncio>=1.4", "pytest-cov>=7.1", "respx>=0.23",
         "hypothesis>=6.169", "ruff>=0.17", "mypy>=2.4", "pip-audit>=2.10"]
train = ["pandas>=3.0.6", "scipy>=1.18", "matplotlib>=3.11", "huggingface_hub", "networkx>=3.7"]
nlp   = ["torch>=2.14", "transformers>=5.19", "datasets>=5.1", "accelerate>=1.15"]   # v2, Colab/Kaggle only
```

```bash
# Python
uv sync --locked                      # runtime + dev
uv sync --locked --group train        # offline training/eval
# Frontend (re-scaffold in frontend/)
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install react@19.3.0 react-dom@19.3.0 recharts@3.10.1 @tanstack/react-query@5.104.1 \
  d3-hierarchy@3.1.2 d3-scale@4.0.2 d3-zoom@3.0.0 d3-selection@3.0.0 zod@4.6.5
npm install -D typescript@7.0.2 vite@8.3.4 @vitejs/plugin-react@6.1.2 tailwindcss@4.3.3 @tailwindcss/vite@4.3.3 \
  @biomejs/biome@2.5.15 vitest@5.0.3 @testing-library/react@16.3.3 happy-dom@20.14.6 \
  @playwright/test@1.64.0 @types/react@19.3.0 @types/react-dom@19.3.0 @types/node@22 \
  @types/d3-hierarchy@3.1.7 @hey-api/openapi-ts@0.99.0
```

Pin `@types/node@22` (latest is 26.x, which does not match the Node 22 runtime).

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Bluesky Jetstream | Mastodon.py | Only for a v2 multi-platform story; accept truncated, untimed boost data. |
| Jetstream via `atproto` SDK | Raw `websockets` + `json` | If the pre-1.0 SDK breaks or you want zero SDK coupling. |
| psycopg 3 (sync + async) | asyncpg 0.32.0 | If profiling shows driver overhead matters and you are not behind a transaction pooler. |
| Async SQLAlchemy | Sync SQLAlchemy | If async session pitfalls slow the team; `def` endpoints plus a thread pool are acceptable at demo scale. Do not mix both styles. |
| Custom D3 cascade view | react-force-graph-2d | If schedule is tight or a graph exceeds ~2,000 nodes and a force layout is acceptable. |
| Biome + TS 7 | ESLint 10 + typescript-eslint + TS 6.0.3 | If a reviewer expects the ESLint ecosystem or you need type-aware lint rules. |
| @hey-api/openapi-ts | Hand-written types + zod | If the generator misbehaves with TS 7. |
| mypy 2.4 | pyright 1.1.414 | If mypy plugin friction with Pydantic/SQLAlchemy blocks you. |
| Neon + Render | Cloud Run + Neon | If you accept entering a card for a more generous, always-warm-capable runtime. |
| Committed `metrics.json` + model card | MLflow 3.17 | Only if experiment volume grows well beyond a handful of runs. |
| GitHub Actions scheduled collector | 24/7 worker on a paid host | If you later fund a small VM; the collector code is the same. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| X/Twitter API (any tier), tweet "rehydration" of FakeNewsNet / CoAID / MuMiN / Twitter15-16 | Paid or restricted access, explicitly out of scope | PHEME (self-contained), LIAR, Bluesky live data |
| Jetstream v1 hosts (`jetstream1.*`, `jetstream2.*`) | Frozen legacy protocol; the SDK documents they will not work with the v2 client; may be retired | v2 hosts `jetstream.us-east.bsky.network` / `jetstream.us-west.bsky.network` |
| `public.api.bsky.app` `searchPosts`, or the URL-case workaround | Deliberately load-shed with 403; the workaround evades a block | Authenticated session (app password from env) |
| `getRepostedBy` for repost timing | Returns profiles without repost timestamps (lexicon-verified) | Jetstream `app.bsky.feed.repost` records (`createdAt`) |
| Jetstream replay as a "search" | Filters are DID/collection only; metered bytes | Seed with `searchPosts`, then track forward on the live tail |
| `requests` | No async, and the prototype already misused it without a timeout | `httpx` with explicit timeouts |
| `asyncpg` plus psycopg together | Two drivers for one database | psycopg 3 only |
| Render free Postgres | Expires in 30 days, no backups | Neon free |
| Fly.io for "free" hosting | No free tier for new orgs | Render free / Cloud Run |
| `typescript-eslint` or `openapi-typescript` with TS 7 | Peer ranges (`<6.1.0`, `^5.x`) make `npm install` fail (verified) | Biome and `@hey-api/openapi-ts`, or pin TS 6.0.3 |
| `@react-sigma/core` 5.0.6 with Sigma 4.0.0 | Wrapper peers `sigma ^3.0.2` | Custom D3, or pin Sigma 3 deliberately |
| `evaluate` package, `netcal` for one metric | Stale / unnecessary dependency | scikit-learn metrics + a tested `ece()` helper |
| ISOT / Kaggle "Fake and Real News", WELFake | Reported source-style leakage (unverified here) | LIAR + PHEME with grouped splits |
| Committing model weights or datasets | PROJECT.md constraint; LIAR license is `unknown`, FNN/CoAID have no LICENSE file | Download scripts with pinned revisions; Hub model repo |
| Server-side random "spread" generator on the live path | Core Value: nothing fabricated | Real collected cascades; any simulator output labelled `synthetic: true` (v2) |
| `@types/node` latest (26.x) | Mismatch with Node 22 | `@types/node@22` |

## Stack Patterns by Variant

**If the Phase 3 spike shows the live tail cannot yield enough multi-node cascades in a bounded window:**
- Seed with authenticated `searchPosts(url=/domain=)` for links to news and fact-check domains, take a `getPostThread` + `getQuotes` snapshot, then follow reposts, replies and quotes of those root URIs on the live tail.
- Because repost timestamps are not available historically via AppView, label snapshot-only cascades as "partial (reposts untimed)" in the API and UI.

**If you want deeper history (v2):**
- Use Jetstream replay with an API key, collections `app.bsky.feed.repost` and `app.bsky.feed.post`, a bounded `afterSeq/beforeSeq` window, and a byte-budget guard honoring `Retry-After`. Expect to download all matching network events and filter client-side.

**If the free Render instance cannot hold the model (v2 transformer):**
- Serve inference from a Hugging Face Docker Space and have the API call it, or ship only the TF-IDF model live and present the transformer as an offline-evaluated result.

**If Neon's pooled endpoint misbehaves with psycopg:**
- Use the direct endpoint for the app, set `prepare_threshold=None`, and keep pool size small (scale-to-zero plus 100 CU-hours/month).

**If the cascade for a post exceeds ~2,000 nodes:**
- Return a server-side capped subtree with `shown`/`total` counts and render that; add canvas rendering only if a real cascade demands it.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| Python 3.13 | all Python deps above | Verified: `uv pip compile --python-version 3.13` resolved core, ML and dev sets. |
| `atproto` 0.0.72 | Python `>=3.9,<3.15` | Jetstream v2 client in `atproto_jetstream`; v1 hosts unsupported. |
| `sqlalchemy` 2.1.4 | Python `>=3.11`; psycopg 3.x | Needs `[asyncio]` extra; default PG driver is psycopg 3. |
| `numpy` 2.5.4, `scipy` 1.18.1, `networkx` 3.7 | Python `>=3.12` | `networkx` excludes 3.14.1. |
| `pandas` 3.0.6, `scikit-learn` 1.9.1 | Python `>=3.11` | pandas 3 is a major release; keep it out of the runtime image. |
| `transformers` 5.19.0 | PyTorch only | TF/Flax removed in v5. |
| `typescript` 7.0.2 | Vite 8, Vitest 5, Biome 2.5 | `typescript-eslint` (`<6.1.0`) and `openapi-typescript` (`^5.x`) conflict; TS 6.0.3 satisfies typescript-eslint only. |
| `vite` 8.3.4 | Node `^20.19 || >=22.12`; `@vitejs/plugin-react` 6.1.2 (needs Vite ^8) | Vitest 5.0.3 supports Vite 6-8; `@tailwindcss/vite` 4.3.3 supports Vite 5-8. |
| `react-router` 8.4.0 | Node `>=22.22.0` | Not needed for v1. |
| `jsdom` 30.1.2 | Node `^22.22.2` (transitive) | `EBADENGINE` on 22.22.0; use `happy-dom` or update Node. |
| `@react-sigma/core` 5.0.6 | `sigma ^3.0.2` only | Do not pair with Sigma 4.0.0. |
| `eslint` 10.12.0 | Node `^20.19 || ^22.13 || >=24` | Only relevant if you choose the ESLint path. |

## Unverified / Needs a Spike

1. **Replay quotas and cost:** docs show byte metering, `429`/`Retry-After`, and API keys, but no price or free-tier quota number. The "about 2 MB/s" figure is a community observation (LOW).
2. **Bluesky data-use terms:** no explicit scraping/research/ML clause found in the ToS or Developer Guidelines pages I could extract. Read them in full once before the first public deploy.
3. **Live-tail volume:** bandwidth and events/second for `post` + `repost` (and what fraction are repost/reply/quote of a tracked URI) were not measured. Measure in the Phase 3 spike, including how many multi-node cascades a 10-minute window yields.
4. **PHEME archive contents:** confirm full tweet JSON presence, per-event counts for the 9-event set, and timestamp format by downloading it (figshare was reachable only through the scraper in this environment).
5. **Twitter15/16 and UPFD:** exact contents and licenses not verified.
6. **FakeNewsNet and CoAID licenses:** repos have no LICENSE file; the legal status is "unspecified", not "open".
7. **Mastodon:** unauthenticated streaming access and per-instance policies not checked; the "no boost timestamp" claim is inferred from the Account entity.
8. **Render free RAM and cold-start duration:** not stated on the page read; test with the real image.
9. **Neon + psycopg prepared statements behind the pooler:** verify at deploy time.
10. **`@hey-api/openapi-ts` 0.99 behavior with TS 7 end to end:** only npm resolution was tested, not generation.
11. **GitHub Actions scheduled-workflow policy** (free minutes, 60-day inactivity disable) and Dependabot `uv` ecosystem: standard knowledge, not re-verified.
12. **Static-host free tiers** (Cloudflare Pages, Vercel, GitHub Pages): not checked, and not needed under the single-image deploy.

## Sources

- Bluesky Jetstream docs (live tail, filters, cursor, endpoints): https://bsky.network/docs/jetstream/ (HIGH)
- Jetstream Network Replay, authentication and metering, 36-hour window: https://bsky.network/docs/jetstream-replay (HIGH)
- Bluesky Protocol Services announcement, 2026-08-13 (Jetstream v2, API token for archive requests only, v1 stays "for a while"): https://atproto.com/blog/introducing-bluesky-protocol-services (HIGH)
- Bluesky rate limits (3,000 per 5 min hosted account; AppView "generous"): https://bsky.network/docs/rate-limits/ (HIGH for the number)
- Bluesky API hosts and auth: https://bsky.network/docs/api-directory/ (HIGH)
- Bluesky Developer Guidelines (content deletion, public contact): https://bsky.network/docs/developer-guidelines/ (HIGH for quoted items)
- Bluesky ToS (no data-use clause found): https://bsky.social/about/support/tos (LOW on absence)
- `searchPosts` 403 on the public AppView, maintainer-confirmed load shedding: https://github.com/bluesky-social/bsky-docs/issues/332 (HIGH)
- Lexicons (`getRepostedBy`, `getQuotes`, `getPostThread`, `searchPosts`, `actor.defs#profileView`): `raw.githubusercontent.com/bluesky-social/atproto/main/lexicons/app/bsky/...` (HIGH)
- Python Jetstream client docs: https://atproto.blue/atproto_jetstream/ and the `atproto` 0.0.72 wheel contents (HIGH)
- Mastodon rate limits: https://docs.joinmastodon.org/api/rate-limits/ ; timelines: https://docs.joinmastodon.org/methods/timelines/ ; statuses: https://docs.joinmastodon.org/methods/statuses/ (HIGH)
- PHEME: https://figshare.com/articles/dataset/PHEME_dataset_for_Rumour_Detection_and_Veracity_Classification/6392078 and https://figshare.com/articles/dataset/PHEME_dataset_of_rumours_and_non-rumours/4010619 (HIGH for license/structure)
- LIAR: https://aclanthology.org/P17-2067/ ; Hugging Face API metadata for `ucsbai/liar` (license `unknown`) (HIGH)
- FakeNewsNet repo and CSV header: https://github.com/KaiDMML/FakeNewsNet (HIGH); class counts from a secondary summary (MEDIUM)
- CoAID repo README and CSV header: https://github.com/cuilimeng/CoAID (HIGH)
- MuMiN: https://mumin-dataset.github.io/ and arXiv 2202.11684 (CC BY-NC 4.0) (HIGH for license; hydration need MEDIUM)
- UPFD in PyG: https://pytorch-geometric.readthedocs.io/en/2.5.0/generated/torch_geometric.datasets.UPFD.html (MEDIUM)
- SQLAlchemy 2.1 migration notes: https://docs.sqlalchemy.org/en/21/changelog/migration_21.html (HIGH)
- Transformers v5 migration guide (PyTorch only): https://github.com/huggingface/transformers/blob/main/MIGRATION_GUIDE_V5.md (MEDIUM, read via search excerpt)
- Render free tier: https://render.com/docs/free ; Neon plans: https://neon.com/docs/introduction/plans ; Neon Postgres versions: https://neon.com/docs/postgresql/postgres-version-support ; Hugging Face Spaces: https://huggingface.co/docs/hub/spaces-overview ; Cloud Run pricing: https://cloud.google.com/run/pricing ; Fly.io pricing: https://docs.fly.io/about/pricing (HIGH, read 2026-10-11)
- Package versions: PyPI JSON API and `npm view` on 2026-10-11; Python set resolved with `uv pip compile --python-version 3.13`; scikit-learn API imports checked in an isolated 3.13 venv; npm combinations tested with `npm install --package-lock-only` (HIGH)
- GitHub Actions versions: each action's README on `raw.githubusercontent.com` (MEDIUM; `gh api` was blocked in this environment)

---
*Stack research for: misinformation early-warning system (Bluesky cascades, text risk classifier, React cascade dashboard)*
*Researched: 2026-10-11*
