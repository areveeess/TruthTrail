# Phase 3: Real Propagation Data - Research

**Researched:** 2026-10-18
**Domain:** Bluesky Jetstream v2 live-tail collection, Postgres persistence (SQLAlchemy 2.1, psycopg 3, Alembic), deterministic cascade enrichment, typed `/v1` read API, bounded GNews context job
**Confidence:** HIGH for protocol, cursor, frame-shape, error-mapping, migration and test-infrastructure facts (executed here against the live public hosts and a throwaway local PostgreSQL 16.15); MEDIUM for yield and storage figures (one 17.8-minute window, Sunday 13:10-13:28 UTC, a 59-domain draft allowlist; the real spike S-5/S-8 settles them); LOW-MEDIUM for the terms and privacy reading (public pages read, not legal advice). Everything not executed is listed in the Assumptions Log.

All probes ran from a scratch directory outside the repository (`$SCRATCH` = `/tmp/claude-0/-home-user-TruthTrail/92aa1a2e-0a51-57d6-846d-a61e78cb81bd/scratchpad/ph3-research/`, with its own Python 3.13.16 venv, `python -I` for anything that reads downloaded data). No repository file other than this one was modified. No credential was used or needed; the real GNews API was never called. Raw frames recorded for analysis stay in `$SCRATCH/raw/` and are not copied anywhere; every frame shown below is rewritten with sequential placeholder tokens and its text dropped.

## Project Constraints (from CLAUDE.md)

Source: `/home/user/TruthTrail/.claude/CLAUDE.md` (its Architecture/Conventions text still describes the original prototype; `HANDOFF.md` and the Phase 1/2 summaries are the current truth). No project skills exist.

- **Honesty:** user-facing copy says "flag for human review", never wording that claims to detect truth; synthetic data always labelled; nothing fabricated on the live path. API descriptions added in this phase pass `scripts/copy_guard.py`.
- **Security:** secrets only via environment variables; scan `.planning/` and code for key material before every commit; never print or write the old GNews key; never call the real GNews API from this container. `tests/test_no_hardcoded_credentials.py` scans `.planning/` too, so this file and every plan must avoid quoted 16+ character literals after `secret`/`password`/`token`/`api_key` names (the backstop regex is quoted in the Security Domain below).
- **Process / git:** work only on `claude/sleepy-lovelace-13aums`; no PRs; no history rewrite; push after each plan; commits end with the two attribution trailers. This stage writes planning documents only.
- **Stack:** Python + FastAPI, Postgres, React/TypeScript later; free and open sources only.
- **Conventions:** 4-space indent, double quotes, `snake_case`, annotate all new signatures (mypy strict on `src/truthtrail`), `logging.getLogger(__name__)` (no `print`), triple-double-quoted docstrings, no emoji.
- **Workflow enforcement:** repo edits go through a GSD command (plan then `/gsd-execute-phase`).
- **Owner platform:** native Windows 11, PowerShell, Python 3.13 via uv. Subprocess tests pass `SYSTEMROOT`.

<user_constraints>
## User Constraints (from CONTEXT.md)

The full text lives in `.planning/phases/03-real-propagation-data/03-CONTEXT.md` (31 locked decisions D-01..D-31 plus three OWNER DECISIONS OD-1..OD-3). The planner must read it; the condensed restatement below changes no decision, and the parameter register at the end of the CONTEXT decisions section is authoritative.

### Locked Decisions

- **D-01 Spike-first.** Plan 03-01 is the source spike: bounded read-only credential-free recorder and analyzer under `scripts/` (stdlib plus `websockets`; `--max-seconds` <= 7200, `--max-bytes`; writes only to git-ignored `spike-output/`; on HTTP 403 stop and report); a >= 60 min real run in this container (two runs at different times of day if possible) plus an owner PowerShell run of >= 5 min; decision document `03-SPIKE-DECISION.md`; fixture. Measurements S-1..S-12 (reachability and dialect; volume; cursor lookback and catch-up; time; seed yield; shapes; deletes and account events; storage footprint; merge frequency; terms; reconnect; environments).
- **D-02 Gate.** Plan 03-01 ends at a `checkpoint:decision`. No Alembic revision, SQLAlchemy model, database dependency, collector, enrich, `/v1` or news-job code before `03-SPIKE-DECISION.md` carries `ratified: true`, `ratified_by: owner`, `ratified_on:` and the OD-1/OD-2/OD-3 choices (or the explicit instruction to take recommended defaults). Only the owner's own message or edit ratifies.
- **D-03 Parameters.** OD-dependent values live in one typed policy object (`core/policy.py`, settings-backed, environment-overridable) with `PROVISIONAL (OD-n)` comments; no schema column, query or API field hard-codes an OD value.
- **D-04 Fixture.** Real, scrubbed, small, produced only from the spike's real run; deterministic scrub (DIDs and rkeys to sequential valid tokens in first-seen order, cid/text/card title/description/thumbnail/URL query and fragment dropped); `src/truthtrail/data/recorded/bluesky-<date>.jsonl` plus `.manifest.json` (`source_mode: "recorded-real"`); <= 1.5 MB; sha256 pinned in a test; the synthetic fixture is never loaded into the events tables; tokens must not look like key material.
- **D-05 Instances.** Jetstream v2 on public Bluesky hosts: primary `jetstream.us-east.bsky.network`, failover `jetstream.us-west.bsky.network`, subprotocol `xrpc.v1.json`; all generation-specific parts in one dialect module; downstream sees only `NormalizedEvent`; failover resumes by microsecond-timestamp cursor, never a per-instance `seq`.
- **D-06 Subscription.** `app.bsky.feed.post` and `app.bsky.feed.repost`, no wildcard, no likes, no `dids`; v2 `kinds=commit`, `account`, `sync`; no `identity`; compression off in v1; bounded `max_size` (2 MiB); bad frames counted by reason and dropped.
- **D-07 Credentials.** No Bluesky credential; `User-Agent: TruthTrail/<version>` with repository URL and optional `COLLECTOR_CONTACT`; TLS verification always on; 401/403 on upgrade is fatal, no retry.
- **D-08 Time.** `observed_at` = stream event time (UTC `timestamptz`, microseconds), never the wall clock; `occurred_at` = untrusted `createdAt` (NULL when unparseable or outside 1970..now+1y), never used for ordering; order violations are a counted metric (`order_violation_count`), never a constraint; add non-raising `find_order_violations()` to `core/cascade.py`.
- **D-09 Reconnect/checkpoint.** One transaction per batch writes upserts, tombstones and the `ingest_checkpoints` row; resume at `cursor = last_committed_time_us - INGEST_REWIND_SECONDS` (30 s); exponential backoff with full jitter 1-60 s, give up after 8 consecutive failures or the deadline, 60 s of silence = dead; a checkpoint older than 30 h or a refused cursor starts at tip/floor and records a `resume_gap`.
- **D-10 Run model.** Bounded batch job `python -m truthtrail.ingest run` (`--max-seconds` 300, `--max-events` 500,000, `--max-stored` 20,000, plus capacity stops); collect, enrich, purge each idempotent and callable alone; exit 0 for every normal stop; no POSIX signals.
- **D-11 Sources.** `EventSource` yields `(NormalizedEvent, cursor)`; `JetstreamSource`, `ReplaySource`; `source_mode` `live`/`replay`; tests never reach the real Jetstream (loopback `websockets` server).
- **D-12 Edges.** `edge_kind` in root/reply/quote/repost as record facts; reply `parent_uri`=`reply.parent.uri`, `reply_root_uri`=`reply.root.uri`; quote `parent_uri`=`embed.record.uri` (or `embed.record.record.uri`); reply+quote is a reply with `quoted_uri` secondary; repost `parent_uri`=`subject.uri`, `inferred=true`, no depth, never attached to another repost; DB enforces `(edge_kind='root') = (parent_uri IS NULL)` and `inferred = (edge_kind='repost')`.
- **D-13 Seed mechanics.** Link sources `embed.external.uri` and link facets; canonicalise (lowercase host, strip `www.`, drop fragment and tracking parameters, normalise trailing slash); never fetch or resolve; shorteners never seed; `en` in `langs` required; adult self-labels (`porn`, `sexual`, `nudity`, `graphic-media`) excluded; every refusal counted by reason.
- **D-14 Orphans.** `parent_state` in none/resolved/orphan/invalid; parents never invented; a child is stored only when its root or subject is stored; `orphan_count`, `disconnected_count`.
- **D-15 Idempotency.** `INSERT ... ON CONFLICT (uri) DO NOTHING`, observation immutable, `update` ignored and counted; `uri` holds the keyed form of the `at://` URI.
- **D-16 Deletes.** Delete commits, `account` events with `status` deleted/takendown, and `sync` markers all tombstone (keep structure, drop account/occurred_at/text/claim/lang); tombstones are never resurrected; purge removes them after `RETENTION_TOMBSTONE_DAYS`; `deactivated`/`suspended`/`desynchronized` are ignored.
- **D-17 Privacy.** `accounts.pseudonym` = lowercase base32 of `HMAC-SHA256(PSEUDONYM_SECRET, "acct\0" + did)` truncated to 16 chars; every URI column holds lowercase base32 of `HMAC-SHA256(secret, "uri\0" + canonical at:// URI)` truncated to 20 chars; no DID, handle, rkey, display name; API shows at most 8 characters; the secret is read only by processes that ingest or erase; one-way.
- **D-18 Minimisation.** Post text only on root events under the ratified OD-1; claim rows hold publisher link-card title, canonical URL, host; news headlines hold headline, URL, source, times only; no raw frames, DIDs, handles or text in logs, bodies, metrics or fixtures.
- **D-19 Access layer.** SQLAlchemy 2.x, `psycopg` 3.3.x only driver, Alembic 1.20.x, all synchronous; declarative models are the schema's single source, `alembic check` proves agreement; hot paths in Core; no f-string SQL (AST test); migrations inside the package (`src/truthtrail/db/migrations/`) with a root `alembic.ini`; `DATABASE_URL` normalised to the psycopg dialect; engine: `pool_pre_ping`, pool 5 + overflow 5, `pool_timeout` 2 s, connect timeout 3 s, API `statement_timeout` 5 s, collector 30 s, `lock_timeout` 2 s, built per app in the lifespan and disposed at shutdown.
- **D-20 Schema.** accounts, claims, cascades, events, ingest_checkpoints, ingest_runs, news_queries, news_fetches (columns as in CONTEXT); `timestamptz` throughout; enums as text plus CHECK; no synthetic column; no `claim_scores`.
- **D-21 Budget.** Application data and indexes under 300 MB (`DB_BUDGET_BYTES`), stored events under 300,000, 5,000 per cascade, 500 active roots; stop with `capacity_reached` at 80%.
- **D-22 Enrich.** Pure Python resolver `resolve_cascade(rows)`; deterministic as a function of the set of rows; never raises on data; Hypothesis over the pure resolver plus a bounded database permutation test; `enrich/` pure modules import nothing from `db/`, `api/` or `ingest/`.
- **D-23 `/v1` shape.** Routes through `V1_REGISTRARS` on the `LimitedRouter`: `/v1/cascades` (keyset pagination, `limit` 25/100, `sort` recent|velocity, filters), `/v1/cascades/{id}`, `/tree` (5,000 nodes), `/timeline` (<= 500 buckets), `/v1/stats`, `/v1/news`; sync `def` handlers, short-lived sessions, statement timeouts, TTL cache pattern; problem+json 422, 429, 500, 503 only.
- **D-24 Provenance.** Every `/v1` success body has `meta` with `synthetic: Literal[False]`, `data_as_of`, `source_status` in ok/empty/stale, `source_mode` live/replay, `observed_since`.
- **D-25 Errors/readiness.** DB connection failure or pool exhaustion -> 503 `database_unavailable` + `Retry-After`; statement timeout -> 503 `database_timeout`; other DB errors -> generic 500; `database` readiness check (`SELECT 1` plus `alembic_version` equals packaged head) registered via `register_default_checks`; proof stops the DB and checks body, header, logs and `/ready`.
- **D-26 News job.** `python -m truthtrail.jobs news`; committed `news_topics.toml` (<= 20 subject phrases, never named individuals); DB ledger `news_fetches` (daily budget 60, per-run 10, refresh 12 h); `services/gnews.py` reused with a `max_results` parameter; stop the run on a 503 `UpstreamError`, record a 502 as a failed topic; results stored as `claims(kind='news_headline')`; proof that no request handler can reach the news API (import graph, dynamic sweep, app starts with the key unset).
- **D-27 `/analyze`.** Retire it in the last plan; `DEMO_MODE` keeps its name and fail-closed guarantee; settings split per entrypoint.
- **D-28 Test database.** Real PostgreSQL, `@pytest.mark.requires_db`; provisioning order `TEST_DATABASE_URL` -> throwaway local cluster (run as the `postgres` system user when euid is 0) -> loud failure; never skip silently; `REQUIRE_DB=1` plus an executed-test floor in CI; autouse socket guard; crash-resume proof runs the CLI as a subprocess.
- **D-29 CI.** Postgres 17 service container pinned by tag and digest with health check, `TEST_DATABASE_URL`, `REQUIRE_DB=1`; real `alembic upgrade head`, `downgrade base`, `upgrade head`, `alembic check`; coverage only ratchets up; `pip-audit` covers new dependencies.
- **D-30 Windows.** `uv sync`/`uv run`, no `uvloop`/`fork`/`add_signal_handler`, `pathlib`, explicit encodings; spike tool `uv run python scripts/bluesky_spike.py record --seconds 300 --out spike-output`; three test routes documented.
- **D-31 Layout.** `db/`, `ingest/`, `enrich/`, `jobs/`, `schemas/v1.py`, `core/policy.py`; AST import-rule test (api never imports ingest, jobs, `services.gnews`, `requests` or `websockets`; ingest/enrich/jobs never import api; enrich pure modules import nothing from db; the API process never imports the pseudonymiser).

### OWNER DECISIONS (research supplies facts below; nothing here decides them)

- **OD-1 Retention** (RT-1 minimal / RT-2 short-TTL text, recommended 14/90/7 days, PROVISIONAL / RT-3 demo lifetime).
- **OD-2 How provisional and duplicate cascades merge** (M0 never merge / M1 never merge, group by claim, recommended, PROVISIONAL / M2 derived full merge).
- **OD-3 Tracked-root selection policy and bounds** (A allowlist seed, recommended, PROVISIONAL / B claim-URL match additive / C engagement promotion / D authenticated search, rejected for v1; bounds 500 active roots, 48 h, 5,000 events per cascade, 300,000 total).

### Claude's Discretion

Module, file and class names inside the new packages; migration revision naming; token alphabet details within D-17's length and no-hex-lookalike rules; the allowlist's entries (reviewed by the owner at the spike checkpoint); the keyset cursor encoding; error-code strings beyond those named; the socket guard; `ingest_runs.counters` shape; the optional operator `erase` command; slicing of plans (indicative 03-01 .. 03-08 in CONTEXT).

### Deferred Ideas (OUT OF SCOPE)

Engagement-promotion and authenticated `searchPosts` seeding (v2); derived merging M2 (only with a promotion-based seed policy); Jetstream Replay/Snapshot and Mastodon (v2); linking news headlines to cascades beyond optional B; risk x velocity ranking (Phase 5); a "view on Bluesky" deep link (rejected by D-17); a pending buffer for children before roots (only if S-4 > 1%); Jetstream zstd (only if S-2 shows bandwidth is a problem); scheduling and the 60-day cron risk (Phase 6); renaming `DEMO_MODE` (Phase 6); pre-commit hooks, structured logging, metrics, API-key auth, load test (v2); re-reading the Bluesky terms before the public URL (Phase 6).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-01 | Source spike: written decision (terms, volume, yield, edge semantics, selection, retention) plus a recorded real-data fixture | Source Facts (hosts, parameters, cursors, volume, terms), Spike Tool Design Brief, selection and retention fact tables, fixture token finding F-01 |
| DATA-02 | Postgres schema with Alembic migrations (`observed_at`, `occurred_at`, `edge_kind`, `inferred`, `parent_uri`) | Pattern 6 (schema, upsert, indexes, measured row sizes), Pattern 8 (Alembic layout, programmatic up/down/check, verified), pitfalls on UTF-8 clusters, time zones, undisposed engines |
| DATA-03 | Bounded Jetstream v2 collector: idempotent upserts keyed on the `at://` URI, checkpoint after commit, deletes honoured | Patterns 1-5 (dialect, run loop, pseudonymiser, writer SQL with RETURNING and GREATEST, tombstones), rewind and seam test results, loopback server pattern |
| DATA-04 | Enrich resolves parents and rolls up; orphans explicit; property test on shuffled arrival | Pattern 7 (pure resolver prototype, Hypothesis strategy, mutation evidence, DB-level layer) |
| DATA-05 | `/v1` read API: trees, timelines, stats, "observed since", orphan counts; Phase 1 error/provenance contract; DB outage 503 and `/ready` | Pattern 9 (prototype against the repo's real `create_app`, `LimitedRouter`, `problem_body`: pagination, 422, OpenAPI codes, outage injection, timeout mapping, readiness head check) |
| DATA-06 | News context refreshed by a job for a bounded query set, served from the database; no proxying of user queries | Pattern 10 (GNews facts verified from public pages, ledger, advisory lock, import-graph and `sys.modules` proofs) |
| FND-02 (Bluesky and database paths) | 502/503 with machine-readable body for Bluesky/database failures | Error mapping table (Pattern 9), `UpstreamError` handler hard-codes `source_status`, so a database error type is separate |
| ML-05, UI-01, UI-02, UI-04, DOC-02, OPS-02 (downstream) | Depend on this phase's fields and caveats | Findings F-05, F-07, F-19 and the honesty caveats list |
</phase_requirements>

## Summary

The architecture in CONTEXT.md holds. The Jetstream, AppView, GNews and library claims it makes were re-checked against the live hosts and public pages, and the design was prototyped against the repository's real `create_app()`, `LimitedRouter` and `problem_body` with a throwaway PostgreSQL 16 started from `initdb` as the `postgres` user. All four public Jetstream hosts stream through the container proxy with plain `websockets` 17.2 defaults (no proxy argument needed). The v2 live tail honours timestamp cursors up to the 36 hour floor with no key, replays at roughly 1,900 to 2,800 post and repost events per second (20 to 30 times real time), re-delivers the seam exactly as documented, and carries no ordering inversions on a single instance. SQLAlchemy 2.1.5, psycopg 3.3.6 (binary), Alembic 1.20.0 and websockets 17.2 resolve into the existing `uv.lock` with zero changes to any existing pin (73 to 81 packages), pass strict mypy, have Windows cp313 wheels and have no known vulnerabilities in pip-audit.

Twenty findings (table below) refine how locked decisions are implemented; none requires abandoning one. The ones that bite hardest: (F-01) the repository's own gitleaks 8.30.1 default rule flags 844 of 3,000 fixture-style frames when `rkey` values are random base32, so D-04's token rule must be "sequential low-entropy counters", not "lowercase base32"; (F-02) a timestamp cursor older than the floor is not an HTTP 400, it is clamped with an in-band seq-less `#info OutdatedCursor` frame, so gap detection must read frames, not only status codes; (F-06) at the measured yield (about 780 eligible allowlist roots per hour) the 500-active-root cap fills in 38 minutes and then refuses 98.7 percent of eligible roots for 48 hours, a sampling-bias problem the owner must see before ratifying OD-3; (F-07) 24.2 percent of repost records carry an observed `via` reference to the repost they came through, which contradicts D-12's "no field anywhere implies who saw the post from whom" and is a cheap schema hedge now but costly later; (F-09/F-10) the repository's `filterwarnings = error` turns any undisposed SQLAlchemy engine into a failing test, and an `initdb` without an explicit locale in this container creates a SQL_ASCII database from which psycopg 3 returns `bytes`.

**Primary recommendation:** Proceed with the CONTEXT plan slicing. Make plan 03-01 (spike) carry the extra measurements named in "Spike Tool Design Brief" (notably S-13, the AppView count cross-check, which this research showed works), keep every OD-dependent number a parameter, add the nullable `via_uri` column to the baseline migration decision for the owner's checkpoint, and bake the verified recipes (Postgres fixture, outage injection, engine factory with UTC and disposal, programmatic Alembic) into the database-foundation plan so the executor does not rediscover them.

### Findings that touch a locked decision (read before planning)

Severity: **A** = the decision text as written would fail or mislead; **B** = adjust implementation, decision intent intact; **C** = information for the owner or later phases. "Proposed handling" never overrides CONTEXT; the planner carries it into plans or the spike checkpoint.

| # | Finding | Evidence | Touches | Proposed handling | Sev |
|---|---------|----------|---------|-------------------|-----|
| F-01 | gitleaks 8.30.1 default `generic-api-key` flags random base32 under field names containing `key`: 844 of 3,000 fixture-style frames flagged for `rkey`; `uri_key`, `account_key`, `ROOT_KEY_n` flagged. Sequential padded counters (entropy near 1) in the real field names `rkey`, `did`, `uri`: 0 findings; random 20-char tokens under `uri`, `parent_uri`, `pseudonym`, `account`: 0 findings | [VERIFIED: gitleaks 8.30.1 via `scripts/install_gitleaks.sh` into scratch, `gitleaks dir`, JSON report] | D-04 ("lowercase base32 or sequential counters ... cannot mistake them for a key") | Scrubber uses sequential left-padded base32 counters for DIDs, rkeys and `rev`; never random tokens in a field whose name contains `key`/`secret`/`token`/`password`; test constants named `ROOT_URI_n`, not `*_KEY`; run the scratch gitleaks over the fixture in the plan | A |
| F-02 | A timestamp cursor older than the retention floor is accepted and clamped; the first frame is `{"$type":"message","payload":{"$type":"...#info","name":"OutdatedCursor","message":"requested timestamp cursor below retention floor; starting at seq 26111682562"}}`. Only a **seq** cursor below the floor is refused (HTTP 400 `CursorTooOld`). A seq cursor beyond the tip yields `#info FutureCursor` then the live tip. `#info` frames carry no `seq` and no `time` | [VERIFIED: probe at now-37 h/-48 h, seq=1, seq=9e14] [CITED: jetstream RFD section 5.1, lexicon `subscribeEvents.json`] | D-09 ("a connect refused with HTTP 400 and a new floor"), D-05, D-11 | Dialect module treats `#info` and `{"$type":"error"}` frames as control frames (never events, never advance the cursor); `OutdatedCursor` on the first frame records the `resume_gap`; keep the 30 h `INGEST_MAX_RESUME_AGE_HOURS` pre-check so the case is rare | B |
| F-03 | `seq` is per instance (east and west differ by about 956.3 million); `witnessedAt` is the documented portable resume position; `time` may be overridden by an operator "timestamp import" (never observed; `time == witnessedAt` in all 100,000 frames); east-versus-west `witnessedAt` offsets over 90 s: P1 -0.31 s, P50 -0.008 s, P99 +0.31 s, min -2.02 s, max +0.91 s; same event set (0 and 2 missing in the overlap window) | [VERIFIED: two concurrent recordings, 8,292 matched events] [CITED: lexicon `commit.witnessedAt`] | D-08 (`observed_at` = v2 `time`), D-05 | Use `witnessedAt` when present, else `time`, for `observed_at`; the 30 s rewind covers failover with a 15x margin; document that the first-stored observation wins (`DO NOTHING`), so a stored value can differ by up to about 2 s depending on which instance delivered it | B |
| F-04 | An oversized frame cannot be "counted and dropped" client-side: `websockets` closes the connection with an error when a frame exceeds `max_size`, and a reconnect with rewind would hit the same frame again (poison loop). `maxMessageSizeBytes` (v2) is honoured by the server | [VERIFIED: loopback test, `ConnectionClosedError`; live `maxMessageSizeBytes=1048576` accepted, frames still flow] | D-06 ("exceeds the bound ... counted by reason and dropped") | Send `maxMessageSizeBytes=1048576` (below the client `max_size` of 2 MiB) so the server skips giants; count a `ConnectionClosed` with code 1009 as `oversize_frame` and fail the run loudly rather than looping; observed max frame in 100,000 frames: 34,839 bytes | B |
| F-05 | Catch-up arithmetic: the stream is 93.8 events/s (post + repost + control), replay runs 1,900-2,800 events/s. D-10's `--max-events 500,000` covers 1.5 h of stream; `--max-seconds 300` covers 1.7-2.5 h at replay speed. A 6 h gap = 2.03 million events (12-18 min, 1.5 GiB uncompressed, 0.6 GiB with zstd); a 24 h gap = 49-71 min | [VERIFIED: probes + 17.8 min recording; arithmetic in this section] | D-10 defaults, D-06 (no compression), D-09 (30 h resume age) | Defaults are right for the live tail and for a manual run; they cannot catch up a 6 h cron gap. Phase 6 must pick cadence and bounds together (for example hourly with defaults, or 6-hourly with `--max-events 2,500,000 --max-seconds 1,500`); record this in the spike document so "observed since" and gap semantics are stated honestly. Consider enabling zstd only for catch-up | B |
| F-06 | At the measured yield the draft 59-domain allowlist produces 780 eligible roots per hour (299 seed candidates in 17.8 min, 231 eligible = en, not adult; 178 distinct authors). `TRACK_MAX_ACTIVE_ROOTS=500` with a 48 h TTL fills in 38 minutes and then refuses about 98.7 percent of eligible roots until slots expire: a first-come window bias, not a sample. Only 16 percent of roots (38 of 231) had at least one child within the window | [VERIFIED: `analyze.py`, `analyze3.py` over 100,000 frames; indicative, one window] | OD-3 bounds, D-21, D-10 | OWNER DECISION input (see OD-3 facts): add a deterministic sampling parameter `TRACK_SAMPLE_PER_10K` (hash of the raw URI, replay-reproducible) so the cap is a safety valve, not the selector; disclose whatever is ratified in DOC-02 | B/C |
| F-07 | 24.2 percent (11,204 of 46,212) of `app.bsky.feed.repost` records carry an optional `via` strong reference to **another repost record**; where both are in the window, the `via` repost has the same subject (3,347 of 3,347). The lexicon field exists in SDK 0.0.73 generated models | [VERIFIED: 100,000-frame analysis] [CITED: atproto SDK 0.0.73 `AppBskyFeedRepost.Record.via`] | D-12 ("no field anywhere implies who saw the post from whom"; reposts never attached to another repost), D-20 schema, DOC-02 repost-star caveat | Store a nullable `via_uri` (keyed, secondary relation, never an edge in v1, exactly like `quoted_uri`) in the baseline migration; keep D-12's star semantics; let the owner decide at the spike checkpoint whether Phase 5 or v2 draws observed reshare chains. Adding the column later is a migration plus a re-ingest | C (schema-costly) |
| F-08 | Reference targets are not always posts or `did:plc`: of 69,507 reference events, 3 pointed at non-post collections (a quote of an `app.bsky.feed.generator`; two reposts of `site.standard.document`); authorities were `did:plc` 90,104 and `did:web` 12; no handle-form URIs; unknown embed types occur (`app.bsky.embed.gallery` 146, custom `app.midnightsky.post`, `dev.chomu.embed.secret`) | [VERIFIED: `analyze2.py`] | D-12, D-13, D-15 | Normaliser: parse `at://<authority>/<collection>/<rkey>` and accept an edge target only when the collection is `app.bsky.feed.post`; accept `did:web:` authorities; treat any unknown `embed.$type` as "no quote, no card" without error; `bridgyOriginalUrl/Text` and `via` (post) keys are ignored | B |
| F-09 | With the repository's `filterwarnings = ["error", ...]`, an SQLAlchemy engine garbage-collected with open pooled connections raises psycopg `ResourceWarning`, surfaced as `PytestUnraisableExceptionWarning`: the test fails. Disposing every engine deterministically makes `-W error` pass | [VERIFIED: fixture prototype with and without `dispose()`] [VERIFIED: `pyproject.toml` quote below] | D-19 (engine disposed at shutdown), D-28 | Engine factory owns disposal; fixtures register `engine.dispose` finalizers; lifespan disposes; no engine at module level; any helper that builds an engine in tests uses a tracking fixture | B |
| F-10 | `initdb` in this container picks SQL_ASCII (no `LANG`); psycopg 3 then returns `bytes` for text, and SQLAlchemy dies in `re.match` while reading `version()`. `initdb -E UTF8 --locale=C` works on Linux and is portable to Windows. `pytest-postgresql` 9.1.1 fails as root (Postgres refuses to run as root). A pytest `tmp_path` under `/tmp/pytest-of-root` (mode 0700) is not traversable by the `postgres` user | [VERIFIED: failed engine start; `pytest-postgresql` run; `namei -m`] | D-28 provisioning | Own fixture (80 lines, verified, 0.97 s startup) that creates a world-traversable `mkdtemp`, `chown`s it to `postgres` when euid is 0, `runuser -u postgres --`, `-E UTF8 --locale=C`, unix socket (TCP loopback on Windows); create databases `ENCODING 'UTF8' TEMPLATE template0` | A |
| F-11 | `register_default_checks(registry)` receives only the registry, while D-19 builds the engine in the lifespan and many existing tests use `TestClient(app)` without `with` (no lifespan). The readiness check therefore cannot see the engine as written | [VERIFIED: `api/app.py:50-55`, `:69-78`; `tests/conftest.py` `client_factory`] | D-19, D-25 | Extend additively: `create_app(*, engine: Engine | None = None, ...)` and `register_default_checks(registry, get_engine)`; the check returns `False` (fail closed) when no engine exists; the lifespan builds the engine only when none was injected; DB tests inject or enter the lifespan | B |
| F-12 | `psycopg[pool]` is not needed: SQLAlchemy's own `QueuePool` serves the sync engine; the engine ran with plain `psycopg[binary]` and `psycopg_pool` is never imported | [VERIFIED: venv without `psycopg-pool`] | D-19 (`psycopg[binary,pool]`) | Depend on `psycopg[binary]==3.3.6` only (one fewer package to audit) | C |
| F-13 | GNews facts, all from public pages read 2026-10-18: Free plan = 100 requests/day, up to 10 articles/request, 12-hour delay, 30 days of history, 1 request/second, non-commercial; a 403 means the **daily quota** is reached (resets 00:00 UTC) and is account-wide; terms permit "reasonable caching of API responses for application performance" and forbid redistributing, reselling or sublicensing **access to the API** and building a database "for the purpose of creating a competing service, redistributing the data, or avoiding API usage limits" | [CITED: docs.gnews.io/endpoints/search-endpoint, /error-handling, gnews.io/pricing, gnews.io/legal/terms-of-service (Last Updated October 16, 2026)] | D-26 (a 502 is "a failed topic with a non-zero exit"), `max_results` default | `max_results` default = 10; on `upstream_forbidden` (403) stop the whole run like a 503 (the quota is account-wide, so continuing burns nothing but also learns nothing); sleep >= 1.1 s between calls; keep the stored set small, headline/URL/source/time only, no bulk export route, attribute GNews in the UI; the owner should read the Free-plan "non-commercial" wording before a public deploy | B/C |
| F-14 | `alembic.config.Config.set_main_option("sqlalchemy.url", url)` with a URL containing `%` (a URL-encoded password) raises `ValueError: invalid interpolation syntax in '<the full URL>'`: the error text **contains the credential** | [VERIFIED: alembic 1.20.0] | D-19, D-29, secret handling | Never put the URL in the ini or `set_main_option`; `env.py` reads `config.attributes["connection"]` (tests, packaged CLI) or the `DATABASE_URL` environment variable; wrap CLI errors to class names only | A (secret leak) |
| F-15 | psycopg returns `timestamptz` in the **session** time zone, and `PGTZ` (or the cluster default, which on Windows is the OS zone) wins over `options=-c timezone=UTC` (verified: still `Asia/Kolkata`). A `connect` event that runs `SET TIME ZONE 'UTC'` and commits fixes it. `date_trunc('day', ...)` is session-zone dependent; `date_bin` with an explicit origin is not | [VERIFIED: PGTZ experiment] | D-20 (`timestamptz` throughout), timeline buckets | Engine factory registers the `connect` event; repository mappers still call `.astimezone(UTC)`; timeline buckets use `date_bin(interval, observed_at, origin)`; ban `date_trunc`/`extract` in queries (AST or review rule) | B |
| F-16 | In 10,547 child-and-parent pairs where both frames fall in the recording, there were **zero** cases where the parent was witnessed after its child (reply 6,623, repost 3,607, quote 317). The tree "prefix is closed under ancestors" property therefore holds on this data, but only because no inversion occurred; `order_events` ties break on `(observed_at, depth, uri)` | [VERIFIED: pair scan, 17.8 min, one instance] | D-14, D-23 tree cap | Keep the property as a documented assumption with a runtime guard: when `order_violation_count > 0` in a capped tree, the response sets `truncated` and the UI shows "some links may be missing" rather than claiming closure | C |
| F-17 | `/v1/stats` over `events` is a parallel sequential scan (48.6 ms at 195,102 rows); the tree, timeline and enrich loads of a 5,000-row cascade take 1-3 ms; keyset list queries 0.1-0.15 ms at 500 cascades; the account-wide tombstone lookup without an `account_id` index is a 16 ms scan at 195,102 rows | [VERIFIED: `EXPLAIN (ANALYZE)` on the prototype schema] | D-20 indexes, D-23 stats | Serve `/v1/stats` from the `cascades` rollup columns and `ingest_runs` (O(cascades), cacheable); keep the three indexes of D-20; add a partial `account_id` index only if S-7 shows account-wide events for known accounts above about one per second | C |
| F-18 | Account events seen in 17.8 min: 263 active, 42 deleted, 30 takendown, 15 deactivated, 2 `throttled`; 4 `sync` events; 19 post `update` operations in 47,635 post creates (0.04 percent; none for reposts) | [VERIFIED: `analyze.py`, `analyze2.py`] | D-16, D-15 | Deletion statuses are an allow-list (`deleted`, `takendown`); every other status, including `throttled` and any future value, is ignored and counted; `update` is ignored and counted | B |
| F-19 | 2 of 354 labelled posts carry the self-label `!no-unauthenticated` (a request not to be shown to logged-out viewers); adult labels: porn 201, sexual 48, graphic-media 23, nudity 19 | [VERIFIED: `analyze.py`] | D-13 | Add `!no-unauthenticated` to the exclusion list (a public, logged-out dashboard would defeat the author's stated intent) | B |
| F-20 | `websockets` 17.2 `connect()` defaults to `proxy=True`, which reads `urllib.request.getproxies()` and honours `proxy_bypass`; with `HTTPS_PROXY` and `SSL_CERT_FILE` set it connected with no argument. `proxy=None` fails here (no direct DNS). The CONTEXT note "pass proxy=HTTPS_PROXY" is unnecessary | [VERIFIED: three-way probe] [VERIFIED: `websockets/proxy.py:102-117`] | D-07, S-12 | The adapter keeps websockets' default and exposes an optional explicit `proxy` argument for odd networks; loopback tests pass `proxy=None` explicitly (the container sets proxy variables) | C |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Receive frames, reconnect, rewind | Collector job (batch process, asyncio at the socket edge only) | - | Never in the API process (D-10, D-31); the only code importing `websockets` |
| Parse and normalise frames, drop control frames | Collector (`ingest/dialect`, `ingest/normalise`) | - | One module per Jetstream generation; everything downstream sees `NormalizedEvent` |
| Pseudonymise DIDs and URIs | Collector and erase command | - | The secret is read only here; the API never holds it (least privilege, D-17) |
| Select tracked roots, bounds, sampling | Collector (`ingest/selection`, `core/policy`) | Spike analyzer (same pure functions) | One implementation measured in the spike and used live |
| Persist batch, checkpoint, tombstones | Database | Collector writer | One transaction per batch; constraints enforce edge invariants (D-12, D-15) |
| Resolve parents, roll up, order, count violations | Pure Python (`enrich/`), no I/O | Database for work selection and write-back | Deterministic and property-testable without a database (D-22) |
| Purge text, cascades, tombstones | Database job (`enrich/purge`) | - | Idempotent, callable alone |
| Serve cascades, trees, timelines, stats | API process (sync handlers) | Database reads | Rate limited by `LimitedRouter`; never calls Bluesky or GNews |
| Provenance and failure mapping | API (`schemas/v1`, problem handlers) | Core error builder | Reuses `problem_body`; database errors map to 503 |
| Readiness | API registry check | Database (`SELECT 1`, `alembic_version`) | Fails closed; 2 s check timeout |
| News refresh | Job process (`jobs/news`) | Database ledger | The only code path with `GNEWS_API_KEY`; API only reads stored rows |
| Recorded fixture replay | `ReplaySource` (package data) | Tests, Phase 6 seed | Same normaliser and writer as live (D-11) |
| Dashboard rendering of user text | Browser (Phase 5) | - | Plain text only (D-31) |

## Standard Stack

### Core (serving group, additions to `[project].dependencies`)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| sqlalchemy | 2.1.5 (PyPI upload 2026-10-16; `requires_python >=3.11`) | ORM models as single schema source, Core for hot paths | Native `Mapped[]` typing (passes strict mypy), `postgresql://` defaults to psycopg 3 in 2.1 [VERIFIED: `create_engine("postgresql://...").dialect.driver == "psycopg"`] |
| psycopg[binary] | 3.3.6 (2026-09-18; psycopg-binary 3.3.6 has win_amd64, manylinux and macOS cp313 wheels) | Only PostgreSQL driver | Sync, typed, no `pool` extra needed (F-12); needs a UTF-8 database (F-10) |
| alembic | 1.20.0 (2026-09-11) | Migrations, `alembic check` drift gate | `command.check` raises `AutogenerateDiffsDetected` on drift [VERIFIED]; works with a shared `Connection` via `config.attributes` |
| websockets | 17.2 (2026-10-03; pure-Python fallback plus wheels incl. win_amd64) | Jetstream client (collector) and loopback server (tests) | New asyncio API: `websockets.asyncio.client.connect`, `websockets.asyncio.server.serve`, `process_request`, default proxy support [VERIFIED] |

Already pinned and unchanged: fastapi 0.143.0 (PyPI latest is 0.144.0 uploaded today; the repository pin stays), starlette 1.8.0, pydantic 2.14.0, pydantic-settings 2.15.0, uvicorn 0.54.0, requests 2.34.2, slowapi 0.1.10, limits 5.8.0, cachetools 7.2.3; dev: pytest 9.1.1, hypothesis 6.170.1, responses 0.26.3, httpx 0.28.1, mypy 2.4.0, ruff 0.17.1, pip-audit 2.10.1.

### Optional

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| zstandard | 0.25.0 (2025-09-14; zero dependencies; ships `py.typed`; win_amd64 wheel) | Decompress dictionary-compressed frames | Only if the spike or Phase 6 enables compression (F-05); `ZstdDecompressor(dict_data=...).decompress(frame, max_output_size=...)` verified; always pass a size bound |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| psycopg 3 (sync) | asyncpg 0.32.0 | Faster, but needs async SQLAlchemy plus greenlet and a second style; CONTEXT locks sync (D-19). Not chosen |
| Own Postgres fixture | pytest-postgresql 9.1.1 | Extra dependencies (mirakuru, port-for, psutil), fails as root in this container [VERIFIED], no built-in `runuser` or UTF-8 handling. Not chosen; it remains a fine option on the owner's machine |
| Own Postgres fixture | testing.postgresql 1.3.0 | Last release 2016; unmaintained. Rejected |
| `websockets` | `atproto` SDK 0.0.73 (`AsyncJetstreamClient`) | STACK.md notes pre-1.0 churn; its docs target v1 hosts; the v2 wire is simple enough for ~150 lines. Not chosen |
| hand-rolled backoff | tenacity 9.2.1 | D-09's loop is ten lines and must interleave cursor and checkpoint logic. Not chosen |

**Installation (verified in a scratch copy of the real `pyproject.toml` and `uv.lock`):**
```bash
uv add "sqlalchemy==2.1.5" "psycopg[binary]==3.3.6" "alembic==1.20.0" "websockets==17.2"
# optional, only if compression is enabled:  uv add "zstandard==0.25.0"
```
Result: `uv lock --check` clean before; after the add, **no existing pin changed**; packages 73 -> 81 (added: alembic 1.20.0, mako 1.4.3, markupsafe 3.0.4, psycopg 3.3.6, psycopg-binary 3.3.6, sqlalchemy 2.1.5, tzdata 2026.5, websockets 17.2). `pip-audit --no-deps` on the pinned set: "No known vulnerabilities found" (2026-10-18). `mypy --strict` on imports and calls of all five libraries: "Success: no issues found".

**Version verification:** PyPI JSON on 2026-10-18 (versions, upload dates, first-upload years: websockets 2013, zstandard 2016, sqlalchemy 2006, psycopg 2021, alembic 2011).

### Pinned versions in the repository (verbatim, `pyproject.toml:10-20`)

```
dependencies = [
    "fastapi==0.143.0",
    "starlette==1.8.0",
    "pydantic==2.14.0",
    ...
    "cachetools==7.2.3",
]
```
[VERIFIED: pyproject.toml:10-20]

## Package Legitimacy Audit

Run: `gsd_run query package-legitimacy check --ecosystem pypi <names>`. The seam returned **SUS** for every package; the reasons are `unknown-downloads` (its download-statistics source is unreachable from this container: pypistats.org is blocked, which Phase 2 also recorded) and, for packages with a very recent latest release, `too-new` (it measures the latest release date, not the package age). These are limits of the seam, not signals about the packages; independent evidence is in the table. The planner should still honour the protocol with **one** consolidated `checkpoint:human-verify` on the dependency-add task (review the `uv.lock` diff, which is exactly the 8 added packages listed above), not one per package.

| Package | Registry | Age (first upload) | Source repo | Seam verdict | Independent evidence | Disposition |
|---------|----------|--------------------|-------------|--------------|----------------------|-------------|
| sqlalchemy | PyPI | 2006 | github.com/sqlalchemy/sqlalchemy | SUS (too-new, unknown-downloads) | Project named by CONTEXT, STACK.md and the SQLAlchemy 2.1 migration notes; pip-audit clean; installed and exercised | Approved (consolidated checkpoint) |
| psycopg, psycopg-binary | PyPI | 2021 | psycopg.org / github.com/psycopg | SUS (unknown-downloads) | Same; official `[binary]` extra; exercised | Approved (consolidated checkpoint) |
| alembic | PyPI | 2011 | github.com/sqlalchemy/alembic | SUS (unknown-downloads) | Same author organisation as SQLAlchemy; exercised | Approved (consolidated checkpoint) |
| websockets | PyPI | 2013 | github.com/python-websockets/websockets | SUS (too-new, unknown-downloads) | Named in Bluesky's own Jetstream Python example [CITED: bsky.network/docs/jetstream]; exercised | Approved (consolidated checkpoint) |
| zstandard | PyPI | 2016 | github.com/indygreg/python-zstandard | SUS (unknown-downloads) | Optional; exercised | Approved if adopted |
| mako, markupsafe, tzdata | PyPI | long-established | - | not checked individually | Transitive via alembic and psycopg; present in the lock diff | Approved (lock review) |
| pytest-postgresql | PyPI | 2016 | github.com/dbfixtures/pytest-postgresql | SUS (too-new, unknown-downloads) | **Not recommended** (fails as root, extra dependencies) | Not installed |

**Packages removed due to SLOP verdict:** none. **Packages flagged SUS by the seam:** all of the above, for the seam-limit reasons stated; no `postinstall` concept applies on PyPI. No package name in this research came from search results or training memory alone: each was named in CONTEXT/STACK, in Bluesky's documentation, or in the repository.

## Source Facts: Bluesky Jetstream and the Public AppView (questions 1 and 2)

Documentation read 2026-10-18: `bsky.network/docs/jetstream/`, `/jetstream-replay/`, `/developer-guidelines/`, `/rate-limits/`, `/api-directory/`; the Jetstream repository's RFD (`docs/README.md`) and lexicon `lexicons/network/bsky/jetstream/subscribeEvents.json` (fetched from `raw.githubusercontent.com/bluesky-social/jetstream/main`); the announcement blog `atproto.com/blog/jetstream`. The lexicon is declared authoritative by the RFD ("The wire contract is declared in `lexicons/network/bsky/jetstream/subscribeEvents.json` - the lexicon is authoritative"). The documentation page still says v2 events "carry a cursor field"; **the live v2 frames carry `seq`, `time` and `witnessedAt` and no `cursor` field** (0 matches in 100,000 frames) - trust the lexicon and the frames.

### Hosts and dialects (S-1, verified from this container with `websockets` 17.2 defaults)

| Host | Dialect | Path | Result |
|------|---------|------|--------|
| `jetstream.us-east.bsky.network` | v2 | `/xrpc/network.bsky.jetstream.subscribeEvents` | 101, subprotocol `xrpc.v1.json` negotiated, handshake 0.43-0.87 s, 531 frames in 6.65 s |
| `jetstream.us-west.bsky.network` | v2 | same | 101, handshake 0.40-0.44 s, 497 frames in 6.5 s |
| `jetstream2.us-east.bsky.network` | v1 (legacy wire) | `/subscribe` | 101, no subprotocol, 561 frames in 6.7 s |
| `jetstream1.us-west.bsky.network` | v1 | `/subscribe` | 101, 583 frames in 6.5 s |

HTTP `GET /` answers 200 on the v2 hosts (`server: openresty`). Intermittent transport failures through the container proxy occurred early (2 of about 12 WebSocket connects ended in `ConnectionResetError`; about 7 retried attempts across roughly 12 early AppView requests were `ConnectionResetError` or `ConnectError`) and not later (30 of 30 AppView requests succeeded; a loop of 30 connects reached a first frame 27 times, the 3 misses being timeouts while waiting for a rare `account` event, not connection failures): the reconnect loop of D-09 and an HTTP retry in the spike tool must treat them as transient. The documentation states the tail "needs no key and is not metered", and the RFD adds: "The v2 stream is not authenticated, so we may more strictly rate limit it compared to the v1 firehose on the Bluesky-hosted instance" - a rate-limit risk that no short probe can exercise (see Open Questions).

### Parameters

**v2** (lexicon): `cursor` (integer), `kinds` (repeated; `commit`, `identity`, `account`, `sync`), `dids` (repeated, max 10,000), `collections` (repeated NSIDs or `prefix.*`, max 100), `maxMessageSizeBytes` (0 = no limit), `zstdDictionary` (integer). Filters are independent predicates ANDed together. `collections` constrains **commit events only**; account, identity and sync events flow regardless unless `kinds` excludes them.

| Probe (v2 east) | Observed |
|-----------------|----------|
| `collections=A&collections=B` only | commits + account + identity (no `kinds`) |
| `kinds=commit&kinds=account&kinds=sync` + collections | 2,710 commits + 9 account events in 30 s, **no identity**; `sync` rare (0 in 30 s; 4 in 17.8 min) |
| `kinds=commit&collections=app.bsky.feed.*` | wildcard accepted |
| `wantedCollections=...` (v1 name) | HTTP 400 `{"error":"InvalidRequest","message":"subscribe: invalid options: wantedCollections is the legacy /subscribe parameter; use collections"}` |
| `kinds=bogus` | 400 "unknown kind \"bogus\" (valid: commit, identity, account, sync)" |
| `kinds=account&collections=...` | 400 "collections filter can never apply: kinds excludes commit" |
| 101 `collections` values | 400 "too many collections values: 101 > 100" |
| `dids=notadid` | 400 "invalid DID: notadid" |
| no `Sec-WebSocket-Protocol` offered | connects, same JSON framing |
| `maxMessageSizeBytes=1048576` | accepted, frames flow |
| `zstdDictionary=123` | 400 `UnknownZstdDictionary`: "unknown zstd dictionary id 123; current dictionary id is 20260811 (fetch it via getZstdDictionary and reconnect)" |

**v1 legacy wire** (served on `jetstream1.us-west` / `jetstream2.us-east`): `wantedCollections`, `wantedDids`, `cursor` (microseconds), `maxMessageSizeBytes`, `compress`, `requireHello`. Observed pitfalls: `kinds=commit` is **not honoured** (identity and account still arrive); `collections=` (the v2 name) is **silently ignored** and streams the whole network (4,351 frames in 10 s = 435 events/s, 64 percent likes); a 48 h cursor is silently clamped and streamed (86,430 frames in 4 s); `compress=true` together with `websockets`' default permessage-deflate offer returns HTTP 400 "choose one compression scheme: custom zstd (compress=true / Socket-Encoding: zstd) or RFC 7692 permessage-deflate, not both" (pass `compression=None`). v1 frames carry both `time_us` and `cursor` (the latter in the same sequence space as the v2 `seq`: 26,162,267,251 at 13:05:06 on `jetstream2.us-east` against v2 `seq` 26,162,258,015 at 13:04:42).

### Frame shapes (sanitised from live v2 frames; DIDs and rkeys rewritten, text and CIDs dropped)

Envelope: `{"$type":"message","payload":{...}}`; terminal error frame `{"$type":"error","error":"ConsumerTooSlow","message":"..."}` (documented: the connection then closes); pre-upgrade rejections are plain XRPC JSON `{"error","message"}` with HTTP 400. Payload `$type` suffixes: `#commit`, `#identity`, `#account`, `#sync`, `#info`.

```json
{"$type":"message","payload":{"$type":"network.bsky.jetstream.subscribeEvents#commit","cid":"<dropped>","collection":"app.bsky.feed.post","did":"did:plc:aaaaaaaaaaaaaaaaaaaaaaah","operation":"create","record":{"$type":"app.bsky.feed.post","createdAt":"2026-10-18T13:10:23.477Z","langs":["en"],"reply":{"parent":{"cid":"<dropped>","uri":"at://did:plc:aaaaaaaaaaaaaaaaaaaaaaai/app.bsky.feed.post/222222222222j"},"root":{"cid":"<dropped>","uri":"at://did:plc:aaaaaaaaaaaaaaaaaaaaaaaj/app.bsky.feed.post/222222222222k"}},"text":"<155 chars>"},"rev":"222222222222l","rkey":"222222222222m","seq":26162393135,"time":"2026-10-18T13:10:24.504221Z","witnessedAt":"2026-10-18T13:10:24.504221Z"}}
```
Top-level link post (card plus facet), quote, quote with media, reply plus quote, repost (with `via`) and delete:
```json
"record":{"$type":"app.bsky.feed.post","createdAt":"...","embed":{"$type":"app.bsky.embed.external","external":{"description":"<dropped>","thumb":"<dropped>","title":"<dropped>","uri":"https://example-news.test/path"}},"facets":[{"features":[{"$type":"app.bsky.richtext.facet#link","uri":"https://example-news.test/path"}],"index":{"byteEnd":26,"byteStart":0}}],"langs":["en"],"text":"<38 chars>"}
"embed":{"$type":"app.bsky.embed.record","record":{"cid":"<dropped>","uri":"at://did:plc:.../app.bsky.feed.post/..."}}
"embed":{"$type":"app.bsky.embed.recordWithMedia","media":{"$type":"app.bsky.embed.images","images":[...]},"record":{"$type":"app.bsky.embed.record","record":{"cid":"<dropped>","uri":"at://.../app.bsky.feed.post/..."}}}
"record":{"$type":"app.bsky.feed.repost","createdAt":"...","subject":{"cid":"<dropped>","uri":"at://.../app.bsky.feed.post/..."},"via":{"cid":"<dropped>","uri":"at://.../app.bsky.feed.repost/..."}}
{"$type":"message","payload":{"$type":"...#commit","collection":"app.bsky.feed.post","did":"did:plc:...","operation":"delete","rev":"...","rkey":"...","seq":26162393260,"time":"...","witnessedAt":"..."}}
```
A delete carries no `record` and no `cid`; its identity is `did` + `collection` + `rkey`, which is enough to recompute the keyed URI of the stored row. Account, identity and sync (the wrapped upstream event keeps its own `seq` and `time`, distinct from Jetstream's):
```json
{"$type":"...#account","account":{"active":false,"did":"did:plc:...","seq":34603673080,"status":"deleted","time":"2026-10-18T13:11:18.581Z"},"did":"did:plc:...","seq":26162415058,"time":"...","witnessedAt":"..."}
{"$type":"...#identity","did":"did:plc:...","identity":{"did":"did:plc:...","seq":34603654755,"time":"..."},"seq":...,"time":"...","witnessedAt":"..."}
{"$type":"...#sync","did":"did:plc:...","seq":26162485785,"sync":{"blocks":{"$bytes":"<380 base64 chars>"},"did":"did:plc:...","rev":"...","seq":34603741870,"time":"..."},"time":"...","witnessedAt":"..."}
{"$type":"...#info","name":"OutdatedCursor","message":"requested timestamp cursor below retention floor; starting at seq 26111682562"}
```
Record facts: `createdAt` is documented as "Client-declared timestamp when this post was originally created"; `text` max 3,000 characters in the SDK model (300 graphemes in the lexicon; observed max 572 characters); `langs` max 3 entries; `tags` max 8; `embed` is an open union (images, video, **gallery**, external, record, recordWithMedia) [CITED: atproto SDK 0.0.73 generated models for `app.bsky.feed.post`]. Every record `rkey` observed (99,300) was 13 characters; 13,226 `#tag` and 912 `#mention` facets coexist with link facets.

### Time, cursor and rewind semantics (S-3, S-4, S-11; all [VERIFIED] live unless cited)

| Test | Result |
|------|--------|
| Timestamp cursor now-10 min / now-2 h / now-24 h / now-35 h | accepted; first event 23 / 54 / 54 / 24 ms after the requested instant; no `#info` |
| Replay rate (post + repost, `kinds=commit`) | 1,892 to 2,790 events/s (20,000-30,000 events in about 10.6 s), 1.6-2.4 MB/s uncompressed; identical bytes on repeating the same cursor (16,541,915 B twice) |
| Timestamp cursor now-37 h / now-48 h | accepted but **clamped**: first frame `#info OutdatedCursor ... starting at seq 26111682562`, stream begins at 2026-10-17T01:01:58Z (36.1 h back) |
| Seq cursor 1 | HTTP 400 `{"error":"CursorTooOld","message":"subscribe: cursor too old: cursor 1 below lookback floor 26111682562; re-backfill from your last seq"}` |
| Seq cursor 9e14 | first frame `#info FutureCursor ... starting at the live tip` |
| Seq cursor = last processed seq | first frame is that same event (inclusive, confirmed by key and seq equality) |
| Timestamp cursor = last `witnessedAt` - 30 s | first replayed event 2 ms after the cursor; all 1,814 events of the preceding 20 s re-delivered; zero loss at the seam; duplicates are the expected overlap |
| Floor | `lookback` 36 h (RFD: "Cursor lookback is bounded to the most recent 36 hours by default ... tunable via `--cursor-lookback`") |
| Same-instance ordering | 0 inversions of `witnessedAt` and 0 non-monotonic `seq` in 100,000 frames |
| Cross-instance | seq spaces differ (about 956.3 M apart); `witnessedAt` east vs west: see F-03 |
| Long idle | 17.8 min uninterrupted with `websockets` default keepalive (20 s ping, 20 s timeout): no server-initiated close; server-initiated closes over hours are not covered (Open Questions) |
| Sparse filter on a long cursor | `collections=org.user-intents.declaration` with a 35 h cursor produced nothing in 25 s: a sparse filter over a long replay can be silent for a long time (the scan is server-side), so D-09's "60 s of silence = dead" is safe for post and repost (dense) but must not be reused for sparse filters |

Safe rewind: `INGEST_REWIND_SECONDS = 30` covers the cross-instance offset (max 2.02 s) with a 15x margin and costs about 2,800 re-delivered events per resume at 93.8 events/s, which `ON CONFLICT DO NOTHING` absorbs. A `ConsumerTooSlow` error is documented ("far behind the live tip AND reading below the server's floor rate for a sustained window"; the floor rate is not published): the writer must keep the reader moving (Pattern 2) and a terminal error frame is a normal reconnect cause.

### Volume (S-2; one window, Sunday 13:10:24-13:28:10 UTC, `jetstream.us-east`, post + repost, 100,000 frames)

| Measure | Value |
|---------|-------|
| Events per second | 93.8 mean; per-second P50/P95/max 92 / 118 / 766; per-minute min / median / max 4,156 / 5,536 / 6,234 |
| Bytes | 72.7 KiB/s uncompressed (6.0 GiB/day, 1.5 GiB per 6 h); frame bytes P50 / P95 / P99 / max 700 / 1,341 / 2,002 / 34,839 |
| Mix | post create 47.6 percent, repost create 46.2, post delete 4.0, repost delete 1.4, account 0.35, identity 0.34, post update 0.02, sync 0.004 |
| Post creates (47,635) | top-level 51.1 percent, reply 42.3, quote 6.1 (of which quote-with-media 1.0), reply+quote 0.5 |
| Languages | `en` in `langs` 50.5 percent; no `langs` 10.2; other 39.3 |
| Embeds | none 61 percent, images 15, link card 14, record (quote) 5.6, video 3.0, recordWithMedia 1.0, gallery 0.3 |
| Link source on top-level posts (24,340) | card only 2,534; facet only 2,891; both 2,900; neither 16,015 |
| Self-labels | porn 201, sexual 48, graphic-media 23, nudity 19, `!no-unauthenticated` 2 |
| `createdAt - witnessedAt` | median -0.51 s; 510 posts (1.1 percent) more than 60 s in the future (max +39,572 s); 1,142 (2.4 percent) more than 1 h old; the oldest 52.5 million seconds (about 1.7 years); none before 2023 |
| Reference structure | 34,518 distinct referenced subjects; 70 percent referenced once |
| Whole network (v1 host without a working filter, 10 s) | about 435 events/s; post + repost is about 21 percent of events |

Official figures: the Jetstream announcement blog (October 2024) says only "hundreds of events per second" for the full firehose and "over a thousand events per second" during a surge; neither it nor the docs give per-collection rates, so these measurements are the planning figures. The CONTEXT sanity probe's "about 21 percent of post creates carry a reply" is a share of **all events**; of post creates alone the reply share is 42.3 percent.

### Compression (S-2 follow-up; D-06 keeps it off)

The dictionary is **an HTTP resource, not a vendored artifact**: `GET /xrpc/network.bsky.jetstream.getZstdDictionary` returns 65,536 bytes, header `x-zstd-dictionary-id: 20260811`, `etag: "zstd-dict-20260811"`, `cache-control: public, max-age=31536000, immutable`; the east and west bodies are byte-identical (sha256 `f631a689a829b84b042ba45bcd7a7c2f792467192c5832fcfc1fc48afbec96aa`). Connecting with `zstdDictionary=20260811` delivers **binary** frames, each one zstd frame whose decompressed bytes are the text frame (lexicon). Measured: 731 frames in 238,696 wire bytes against 752 frames in 610,566 bytes uncompressed: 326 versus 812 bytes per frame (ratio 0.39, 61 percent saved; 2.3 GiB/day instead of 6.0). `zstandard` 0.25.0 decodes it with `ZstdDecompressor(dict_data=ZstdCompressionDict(dict_bytes)).decompress(frame, max_output_size=bound)`. Parsing speed is not the limit: `json.loads` alone 163,500 events/s, parse plus three HMAC-base32 per event 35,600 events/s, against a replay rate of at most 2,800 events/s.

### Terms, privacy and acceptable use (S-10; pages read 2026-10-18; not legal advice)

| Source (date) | Dated quote | Consequence for this phase |
|---------------|-------------|----------------------------|
| Bluesky Terms of Service (Last Updated: 14 August, 2025) | "These Terms only apply to social networking that happens on Bluesky. If you're using another social networking application on the AT Protocol that isn't Bluesky Social (a \"Developer Application\"), the terms and conditions of that Developer Application will govern your experience." | The ToS binds Bluesky users and the Bluesky app, not a reader of public network data; it contains no scraping, research or ML clause |
| same, section 3 | "Bluesky does not control how others may use your Content." and "Due to the decentralized nature of the AT Protocol, we cannot control or force other services and Developer Applications on the AT Protocol to treat your Content in a particular way and some posts may continue to exist on these services that are outside our control. That means that complete deletion across the network may not always be possible." | Honouring deletes is our responsibility as a downstream copy |
| AT Protocol Network Services Privacy Notice (Last Updated: May 22, 2024) | "User Content is Public." and "Given the decentralized nature of the AT Protocol, we may share your public personal information such as your public posts and profile with third-party actors that operate on the AT Protocol. We are not responsible for the processing of personal information by third-party actors that operate on the AT Protocol." | Public posts are personal data we process as an independent party; minimisation, deletion propagation and retention are our defence |
| Bluesky Privacy Policy | "Your posts and comments are public, so exercise care when deciding what to share." and "Bluesky is a decentralized microblogging service where most user activity is public by design." | same |
| Developer Guidelines (no date shown) | "All services must have a method for deleting content a user has requested to be deleted."; "Developers must maintain updated contact information accessible to the public including an email address that is regularly monitored."; "Developers should maintain reasonable security measures to protect against unauthorized access or disclosure of any end-user information or app data."; apps with user-generated content "must include: A method to report illegal content ... A method for blocking forbidden content ... A method for blocking abusive users"; failure "may result in suspension of access to services or features run on Bluesky's infrastructure" | The guidelines are addressed to "Developers who federate their apps or services"; whether a read-only analysis dashboard is covered is unclear, so treat them as binding: deletion path (D-16), public contact (README, `COLLECTOR_CONTACT` in the User-Agent), a documented way to report content and an operator hide/erase command (recommended small addition; not in CONTEXT) |
| Community Guidelines | no scraping or research clause; "Do not send spam" etc. | read-only consumption is not spam; keep the User-Agent honest |
| `bsky.network/docs/rate-limits/` | "These API services have generous rate-limits. Please contact us if you encounter rate-limiting." (public AppView) | The live tail has no published limit beyond the RFD's caution |
| Draft proposal 0008 "User Intents for Data Reuse" (bluesky-social/proposals) | declarations could say no to generative AI, protocol bridging, bulk datasets, public archiving; "good actors are expected to abide"; "Intent preferences would be tri-state"; automated classification is explicitly **not** covered by the generative-AI intent; "bulk dataset" is about publicly redistributed snapshot corpora and "captures of the relay firehose" | A draft, "not legally enforceable"; whether `org.user-intents.declaration` records exist on the network is unverified (a 35 h cursor scan found none in 25 s but may not have completed). We build a classifier and serve cascades, not a bulk corpus: add no bulk export route; the committed scrubbed fixture carries structure only |
| GDPR (Recital 26 and Article 89(1), eur-lex text via gdpr-info.eu) | "Personal data which have undergone pseudonymisation, which could be attributed to a natural person by the use of additional information should be considered to be information on an identifiable natural person."; Article 89(1) safeguards "may include pseudonymisation provided that those purposes can be fulfilled in that manner" | D-17 is pseudonymisation, not anonymisation; DOC-02 must say so (already planned). Not legal advice; the owner is the controller |

No research, machine-learning or scraping clause was found in any of these pages, as CONTEXT already recorded; absence is not a licence. Re-read before the Phase 6 public deploy.

### Record semantics and cascade reconstruction

| Relation | Source field | Edge | Stored as | Notes from data |
|----------|--------------|------|-----------|-----------------|
| Root | top-level post (no `reply`, no quote embed) that passed selection | none | `edge_kind='root'` | 51.1 percent of posts are top-level; the link must come from card or facet (sources overlap, so check both and union) |
| Reply | `reply.parent.uri`, `reply.root.uri` | observed, `inferred=false` | `parent_uri`, `reply_root_uri` | 42.3 percent of posts; `root != parent` in 43 percent of replies (depth > 1); `reply.root` is the thread root, so every descendant of a tracked root names it |
| Quote | `embed.record.uri` or `embed.record.record.uri` (recordWithMedia) | observed | `parent_uri` | 6.1 percent of posts; 1 of 3,135 quote targets was a feed generator (F-08) |
| Reply + quote | both present | reply wins | `quoted_uri` secondary | 0.5 percent |
| Repost | `subject.uri` | `inferred=true`, no depth | `parent_uri` | 46 percent of all events; `via` on 24.2 percent (F-07) |

Tracked-set membership (what the collector must test per frame): a reply is stored when `reply.parent` is a stored event **or** `reply.root` is a stored root (the second case yields an orphan when the parent is unknown); a quote or repost is stored when its target is a stored event. All tests are set lookups on the keyed form of the referenced URI (about 28 microseconds per frame including three HMACs). Cascade rollups never need AppView data.

### Public AppView (S-5 hydration, question 2; unauthenticated, `public.api.bsky.app`)

| Endpoint | Observed limits and behaviour |
|----------|-------------------------------|
| `app.bsky.feed.getPosts` | max **25** URIs ("array too big (maximum 25, got 26)" 400); unavailable or deleted posts are silently omitted (24 of 25 returned; a missing URI returns `{"posts":[]}`); fields `replyCount` (direct replies), `repostCount`, `quoteCount`, `likeCount`, `bookmarkCount`, `indexedAt`, author profile; `cache-control: public, max-age=30`, served by BunnyCDN; no rate-limit headers on 200 responses |
| `app.bsky.feed.getPostThread` | `depth` max 1000 (default 6), `parentHeight` max 1000 (default 80); a post with `replyCount` 688 returned **243** nodes at default and at depth 1000: the thread view is a ranked, truncated sample, **not a completeness oracle**; a missing post answers HTTP 400 `{"error":"NotFound"}`; 345 KB for 243 nodes |
| `getQuotes` | `limit` <= 100, paginated by `cursor`; 466 KB for 100 posts |
| `getRepostedBy` | returns profile views (`repostedBy`, `cursor`); STACK.md already notes it carries no repost time |
| `searchPosts` | **403 Forbidden** from the CDN (load-shedding on the public host); not used, no workaround |

**Coverage cross-check (new, recommended as spike measurement S-13).** For 97 eligible roots with at least 10 minutes of observation in the recording, `getPosts` (4 calls, 95 hydrated, 2 already unavailable) agreed with the stream-reconstructed child counts: reposts 28 observed vs 32 at AppView (the difference accrues after the recording ended), direct replies 14 vs 15, quotes 0 vs 1; exact match on 91 / 92 / 94 of 95 roots, observed <= AppView on 95 / 94 / 95. This is a cheap, read-only, key-free way to show that the collector's reconstruction is complete for tracked roots, and it needs no AppView data in the product.

### Tracked-root selection policies (OD-3 facts; indicative, one window; nothing here decides OD-3)

| Option | Measured or derived cost |
|--------|--------------------------|
| A allowlist (59 draft domains, `en`, no adult label, no shortener) | 299 candidates / 17.8 min = 1,010 per hour; eligible 231 = 780 per hour (18,700 per day); 178 distinct authors (top author 7.4 percent of roots); per-domain distinct authors e.g. nytimes.com 40, theguardian.com 30, cbc.ca 13; draft allowlist domains with at least one eligible root: nytimes.com 61, theguardian.com 45, apnews.com 21, cbc.ca 15; children seen in-window: median 0, P90 1, max 10; 38 of 231 roots (16 percent) had >= 1 child (kinds: 56 reposts, 29 replies, 2 quotes); among 37 roots with a full 15 min horizon, P(any child within 15 min) = 0.24 (reply 0.14, quote 0.00, repost 0.14, n too small to trust) |
| B claim-URL match | needs stored GNews headlines (none exist yet); at most 20 topics x 10 articles per refresh, so the matching set is tiny; precise, near-zero cost, near-zero yield |
| C engagement promotion | 34,518 distinct referenced subjects in 17.8 min (about 116,000 per hour); a one-hour counter table is about 116,000 keys (about 17 MB in Python); subjects with >= 10 references: 2,225 per hour; >= 25: 584 per hour; >= 100: 71 per hour (the 21 subjects with >= 100 references hold 5.6 percent of all reference events); events before promotion are lost unless the collector buffers every reference (about 235,000 per hour); stores any topic including adult and abusive content; creates the OD-2 re-rooting situation |
| D authenticated search | rejected by CONTEXT (credential, 403 on the public host) |

What the cap does: with `TRACK_MAX_ACTIVE_ROOTS=500` and `TRACK_ROOT_TTL_HOURS=48` the steady state is at most 250 new roots per day (500 slots / 2 days) against 18,700 eligible, i.e. 1.34 percent of eligible roots, taken first-come after each slot frees. **Deterministic hash sampling** (keep a root when `sha256(raw_at_uri) mod 10,000 < TRACK_SAMPLE_PER_10K`, computed before keying) gives a time-unbiased, replay-reproducible sample whose rate the owner can state in DOC-02; the caps then only protect against bursts. Sampling by the raw URI hash is independent of `PSEUDONYM_SECRET`, so the fixture's selection reproduces without the secret.

## Architecture Patterns

### System Architecture Diagram

```
   batch job process:  python -m truthtrail.ingest run         (PSEUDONYM_SECRET read here only, from the environment)

   wss://jetstream.us-east.bsky.network  (failover: jetstream.us-west...)
                 |  JSON text frames (v2, subprotocol xrpc.v1.json)
                 v
   +----------------+  control frames (#info, error)  +-----------------------------+
   | JetstreamSource|-------------------------------->| counted / reconnect logic   |
   | connect, cursor|                                 +-----------------------------+
   | backoff, 60 s  |  ReplaySource (recorded fixture) uses the SAME normaliser below
   | silence, rewind|
   +-------+--------+
           | frames
           v
   +-----------------------------+   drop reasons    +--------------------------------+
   | dialect + normaliser        |------------------>| run summary (counts by reason)  |
   | -> NormalizedEvent          |                   +--------------------------------+
   +--------------+--------------+
                  v
   +-----------------------------+
   | pseudonymise (HMAC keys)    |
   | selection: allowlist, hygiene filters, sampling, caps; tracked-set membership
   +--------------+--------------+
                  | tracked events only (roots, replies, quotes, reposts, deletes, account/sync tombstone requests)
                  v     one transaction per batch (500 rows or 2 s)
   +-------------------------------------------------------------------------------+
   | INSERT ... ON CONFLICT (uri) DO NOTHING RETURNING uri                          |
   | tombstone UPDATEs (delete, account deleted/takendown, sync)                    |
   | checkpoint upsert with GREATEST(cursor_time_us)            -> COMMIT           |
   +---------------------------------------+---------------------------------------+
        ^ resume: cursor = checkpoint - 30 s |
        +------------------------------------+
                                             v
   PostgreSQL: accounts, claims, cascades, events, ingest_checkpoints, ingest_runs, news_queries, news_fetches
        ^                         ^                                   ^
        | enrich_dirty            | rollups, parent_state, depth      | ledger + stored headlines
   python -m truthtrail.enrich    purge (text, cascades, tombstones)  python -m truthtrail.jobs news --> GNews (key lives here only)
   (pure resolve_cascade, one transaction per cascade)

        | read-only, short sessions, statement_timeout
        v
   API process (no secret, no websockets, no requests): create_app(), LimitedRouter /v1/*, meta {synthetic: false, data_as_of, ...}
       database error -> 503 problem+json + Retry-After         /ready: SELECT 1 + alembic_version equals packaged head
```

### Recommended Project Structure (D-31, with research additions marked +)

```
src/truthtrail/
├── core/        cascade.py (+find_order_violations), policy.py (parameter register), readiness.py (unchanged)
├── db/          models.py, engine.py (+ factory: UTC connect event, timeouts, disposal), url.py, migrations/ (env.py, versions/), repos/
├── ingest/      dialect.py (v2 + v1), normalise.py, pseudonym.py, selection.py, writer.py, source.py, run.py, __main__.py
├── enrich/      resolve.py (pure), rollup.py (pure), apply.py (db), purge.py (db)
├── jobs/        news.py, __main__.py
├── schemas/     v1.py (V1Meta, CascadePage, TreeNode, ...)
├── api/         v1_cascades.py, v1_stats.py, v1_news.py (registrars), db_errors.py (+ exception handlers)
└── data/        recorded/bluesky-<date>.jsonl + .manifest.json, seed_domains.txt, news_topics.toml
alembic.ini      script_location = %(here)s/src/truthtrail/db/migrations
scripts/         bluesky_spike.py (stdlib + websockets)
tests/           conftest.py (+ pg fixtures), test_db_*.py, test_ingest_*.py, test_enrich_*.py, test_v1_*.py, test_news_*.py
```

### Pattern 1: Dialect module and control frames

One function per Jetstream generation turns a text frame into either `NormalizedEvent` or a `Control` value; nothing else in the code base knows `witnessedAt`, `time_us` or `cursor`.

| Frame | v2 action | v1 action |
|-------|-----------|-----------|
| `{"$type":"message","payload":{"$type":"...#commit"}}` | event; `observed_at` = `witnessedAt` else `time`; resume cursor value = that instant in microseconds | `time_us` |
| `#account` | `account.status` in {`deleted`, `takendown`} -> tombstone-all request for the pseudonym of `did`; everything else counted and ignored (F-18) | same fields |
| `#sync` | tombstone-all request for the pseudonym of `did` | not emitted on v1 |
| `#identity` | not requested; if received, count and ignore | count and ignore |
| `#info` (`OutdatedCursor`, `FutureCursor`) | control: no cursor movement; `OutdatedCursor` records `resume_gap` | not emitted |
| `{"$type":"error",...}` | control, terminal: reconnect | closes |
| `operation: update` | counted `update_ignored` | same |
| anything unparseable, non-object, wrong shape, unknown `$type` | counted by reason, dropped | same |

Shape validation should be tolerant of fields the fixture scrubber removes (`cid` is dropped from fixtures, so the normaliser must never require it) and strict about the ones it uses (`did`, `rkey`, `collection`, `operation`, `time`/`witnessedAt`, `record.createdAt` parse). Edge targets are accepted only for the `app.bsky.feed.post` collection (F-08). The cursor value written to the checkpoint is the stream time of the **last committed event**, in microseconds. Derive the integer with `(dt - epoch) // timedelta(microseconds=1)`, which is exact by construction (the float form `int(dt.timestamp() * 1_000_000)` also matched on 200,000 random microsecond values at this magnitude, but needs no such luck to be avoided).

### Pattern 2: Run loop (asyncio at the socket edge, synchronous database)

```python
# sketch, all values from D-09/D-10 and the probes above; names are discretionary
URL = (f"wss://{host}/xrpc/network.bsky.jetstream.subscribeEvents"
       "?kinds=commit&kinds=account&kinds=sync"
       "&collections=app.bsky.feed.post&collections=app.bsky.feed.repost"
       "&maxMessageSizeBytes=1048576" + (f"&cursor={cursor_us}" if cursor_us else ""))
async with connect(URL, subprotocols=[Subprotocol("xrpc.v1.json")], max_size=2 * 1024 * 1024,
                   max_queue=1024, user_agent_header=USER_AGENT, open_timeout=10) as ws:
    while not bounds.reached():
        frame = await asyncio.wait_for(ws.recv(), timeout=60)      # silence => dead => reconnect
        ...normalise, select; append to batch...
        if batch.full_or_old():                                    # 500 rows or 2 s
            await asyncio.to_thread(write_batch, batch)            # sync engine, one transaction
```
Verified facts that shape it: websockets answers pings itself (17.8 min uninterrupted with defaults); its built-in `async for ws in connect(...)` reconnect reuses the **same URI**, so it cannot carry a new cursor and is not used; `max_queue` (default 16 messages) is raised so a 30-100 ms batch flush does not stall reading at 94 events/s; during replay at 2,000-2,800 events/s a flush pauses reading and TCP back-pressure holds the data (no loss), which is the intended behaviour; a frame above `max_size` closes the connection (F-04); `HTTP 403/401` on upgrade surfaces as `InvalidStatus` and is fatal (D-07); `InvalidStatus` with 400 carries a JSON body to classify (`CursorTooOld`, `UnknownZstdDictionary`, `InvalidRequest`). The loop's exit status maps to D-10: bound reached -> 0, `capacity_reached` -> 0, eight consecutive failures -> non-zero.

Reconnect arithmetic: the next cursor is `checkpoint_us - 30_000_000`; a resume older than `INGEST_MAX_RESUME_AGE_HOURS` (30) starts at the tip and records a gap; on an `OutdatedCursor` info frame the run also records a gap with `from` = requested instant, `to` = first event time. Backoff `random.uniform(0, min(60, 1 * 2**attempt))` (full jitter); reset after a connection that delivered at least one event.

### Pattern 3: Keyed pseudonymiser (D-17), verified

```python
import base64, hashlib, hmac

def make_keyer(secret: bytes):
    base = hmac.new(secret, digestmod=hashlib.sha256)               # key schedule computed once
    def key(domain: bytes, value: str, chars: int) -> str:
        h = base.copy(); h.update(domain + b"\0" + value.encode())
        return base64.b32encode(h.digest()).decode().lower().rstrip("=")[:chars]
    return key
# uri key:  key(b"uri",  "at://did:plc:.../app.bsky.feed.post/...", 20)   (100 bits)
# account:  key(b"acct", did, 16)                                         (80 bits)
```
28 microseconds per frame including parsing and three keys (35,600 events/s). Birthday collision probability: 3.9e-17 for 10 million URI keys at 100 bits; 4.1e-13 for one million accounts at 80 bits. `hmac.compare_digest` is not needed (no secret comparison). Enforce `len(secret) >= 32` bytes at start (accept base64url or hex text, decode, check length), hold it as `SecretStr`, never include it in an exception. `PSEUDONYM_SECRET`, `COLLECTOR_CONTACT` and the new settings go into `ENV_NAMES` (conftest), `EXPECTED_ENV_NAMES` (credential test) and `.env.example`. A leaked database plus a leaked secret re-enables dictionary reversal of DIDs (D-17's stated limit).

### Pattern 4: Writer SQL, executed against PostgreSQL 16 (batch, checkpoint, tombstones)

```python
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import func, update

with engine.begin() as conn:                                                # ONE transaction
    ins = pg_insert(Event).on_conflict_do_nothing(index_elements=["uri"]).returning(Event.uri)
    inserted = conn.execute(ins, rows).scalars().all()                      # rows = list[dict], IDENTICAL KEYS in every dict
    conn.execute(update(Event).where(Event.uri.in_(delete_keys), Event.deleted_at.is_(None))
                 .values(deleted_at=observed_at, account_id=None, occurred_at=None, text=None, lang=None, claim_id=None))
    ck = pg_insert(IngestCheckpoint).values(source="bluesky", dialect="v2", host=host, cursor_time_us=cursor_us, cursor_seq=None)
    conn.execute(ck.on_conflict_do_update(index_elements=["source"], set_={
        "cursor_time_us": func.greatest(IngestCheckpoint.cursor_time_us, ck.excluded.cursor_time_us),
        "updated_at": func.now()}))
```
Verified: `RETURNING` after `DO NOTHING` yields only the newly inserted URIs, so inserted and duplicate counts are exact (`rowcount` is -1 for executemany); `GREATEST` keeps a rewound batch (older cursor) from moving the checkpoint backwards; a replayed create after a tombstone returns `[]` and the row stays deleted; the second identical tombstone `UPDATE` touches 0 rows; CHECK constraints reject `inferred=true` on a non-repost, a root with a parent, and text on a non-root. 500-row batches inserted 195,102 rows at 13,000 rows/s (20,000 all-conflict rows in 1.1 s), orders of magnitude above the roughly 0.1 to 10 stored rows/s the policy will produce. Batch rows of mixed kinds must be built by one function so every dict has the same keys (SQLAlchemy takes the key set from the first dict and raises "A value is required for bind parameter" for a row that lacks one, verified). Order inside a batch: inserts, then tombstones, then checkpoint, so a create and its delete in one batch end as a tombstone.

Tombstone lookups by key use `uq_events_uri` (0.02 ms). Account-wide tombstones need the pseudonym -> `accounts.id` lookup first (unique index on `pseudonym`), then `UPDATE ... WHERE account_id = :id AND deleted_at IS NULL`; at 195,102 rows that scan costs 16 ms without an index (F-17), acceptable at the measured rate of known-account deletions.

### Pattern 5: Delete and account events, and the missed-delete bound

D-16 is implementable exactly as written. Data to keep in mind: post deletes are 4.0 percent and repost deletes 1.4 percent of events, i.e. about 15 per second network-wide, and only deletes whose key exists in `events` do anything (the bulk are no-ops, counted). The `account` events that matter are `deleted` (42 in 17.8 min network-wide) and `takendown` (30); a `takendown` account can later return to `active`, but a tombstone is deliberately irreversible. A delete missed during an ingest gap lives at most `RETENTION_TEXT_DAYS` for text and `RETENTION_CASCADE_DAYS` for structure (OD-1). The recommended operator command `erase` (stdin DID, never an argument; computes the pseudonym; tombstones; prints counts) closes the residual window and satisfies the Developer Guidelines' "method for deleting content a user has requested".

### Pattern 6: Schema notes from the prototype (D-20 as written was built and migrated)

The D-20 outline was created with SQLAlchemy 2.1.5 declarative models (naming convention `ix/uq/ck/fk/pk`), autogenerated into a baseline revision, and run `upgrade -> check -> downgrade base -> upgrade -> check` (Pattern 8) with no drift.

| Item | Measured or decided |
|------|---------------------|
| Row cost (all indexes) | events 283-297 bytes with PK, `uq_events_uri`, `(cascade_id, observed_at, uri)`, partial orphan index (the extra `parent_uri` index I tried added about 16 bytes per row, 3.06 MB over 195,102 rows, and is not needed: enrich loads a cascade by `cascade_id`); cascades 622 bytes; claims 567 bytes (89-char title, 100-char URL, one unique index); accounts 143 bytes; root text adds about its length |
| Claims uniqueness | the expression index `(kind, text_hash, coalesce(url_canonical,''))` works, but an `ON CONFLICT` target on it needs the expression repeated; recommend an additional `claim_key text NOT NULL UNIQUE` (hash of kind + canonical URL or text) for plain `ON CONFLICT (claim_key)` upserts. Claude's discretion |
| `via_uri` | add `via_uri varchar(20) NULL` to `events` (F-07) |
| Types | `varchar(20)` for URI keys and `varchar(16)` for pseudonyms match the fixed key lengths; `timestamptz` everywhere (F-15) |
| Stats | maintain per-cascade rollups in `cascades`; compute `/v1/stats` from them (F-17) |
| Single-flight | `pg_try_advisory_lock(<constant>)` per command (`ingest`, `enrich`, `purge`, `news`) on the job's own connection: verified that an overlapping run gets `False` and succeeds after release; a job exits with a clear non-zero status when it cannot take its lock (not in CONTEXT; recommended, it also protects the news ledger) |

Query plans on 195,102 events / 500 cascades (heavy-tailed sizes, max 5,000; PostgreSQL 16.15): tree page `ORDER BY observed_at, uri LIMIT 5001` 3.0 ms; timeline `date_bin('5 minutes', observed_at, <fixed origin>)` grouped by kind 2.4 ms for 5,000 rows; keyset list (recent and velocity) 0.11-0.15 ms; one-cascade enrich load 1.0 ms; global scan stats 48.6 ms (avoid); delete by key 0.02 ms. All parameters bound; none of these needs a covering index beyond D-20's three.

### Pattern 7: Deterministic enrich and the Hypothesis proof (prototype executed)

Resolver contract implemented in the prototype (scratch, 100 lines, standard library only): input rows `(uri, edge_kind, parent_uri, observed_at, account, deleted)`; output per-uri `state` in none/resolved/orphan/invalid, `parent`, `depth` (None for reposts and disconnected events), canonical order, and rollups `event_count, reply, quote, repost, unique_accounts, max_depth, orphan_count, invalid_count, disconnected_count, deleted_count, order_violation_count, events_1h(as_of), duplicates`. Rules that made it order-independent: iterate `sorted(uris)`; conflicting duplicates of one uri keep the smallest tuple; reposts are never attachable parents; self-parent and cycle members become `invalid` (all cycle members regardless of start node); a child of a present-but-orphan parent is `resolved` but `disconnected` (depth None); the order key is `(observed_at, known-ancestor count, uri)`; `events_1h` takes an explicit `as_of`.

The strategy that proves it (this is the part that matters; the first version was too weak):

```python
IDS = [f"u{i:02d}" for i in range(12)]

@st.composite
def rows_st(draw):
    n = draw(st.integers(1, 10)); ids = draw(st.permutations(IDS).map(lambda p: p[:n])); rows = []
    for i, u in enumerate(ids):
        kind = draw(st.sampled_from(["root", "reply", "reply", "quote", "repost"]))
        pool = ids * 4 + IDS + [None]                       # mostly INSIDE the set: cycles, shared parents; some outside: orphans
        parent = None if kind == "root" else draw(st.sampled_from(pool))
        ts = T0 + timedelta(seconds=draw(st.integers(0, 6)), microseconds=draw(st.sampled_from([0, 1])))   # many ties
        rows.append(Row(u, kind, parent, ts, draw(st.sampled_from([None, "a", "b", "c"])), deleted=draw(...)))
    rows += draw(st.lists(st.sampled_from(rows), max_size=3))                     # duplicate deliveries
    rows += draw(st.lists(st.builds(replace_account_and_deleted, st.sampled_from(rows), ...), max_size=2))   # CONFLICTING duplicates
    return rows

@given(rows=rows_st(), data=st.data())
@settings(max_examples=200, derandomize=True, deadline=None, database=None)       # the repository's ci profile
def test_order_independent(rows, data):
    assert projection(resolve(rows, AS_OF)) == projection(resolve(data.draw(st.permutations(rows)), AS_OF))
```
Mutation evidence (executed): with the first strategy (parents drawn from the whole universe, only identical duplicates) **all three mutants survived 200 examples**; with parents biased into the set and conflicting duplicates added, **all three were caught**: (1) "first duplicate wins" (arrival-dependent), (2) tie-break without the uri plus iteration in arrival order, (3) "cycle tail also marked invalid, start node chosen by arrival order". Keep the three mutants as tests with `pytest.raises(AssertionError)` around the property so the guard cannot rot. The same prototype also passed an invariants property (states in the allowed set, no cycle in the resolved parent graph, `orphan_count` equals the orphan states, reposts never get a depth, parents' depths differ by exactly one) and ran in 22.7 s for five tests under the `ci` profile.

Database layer (bounded, 25 examples, `deadline=None`, `suppress_health_check=[HealthCheck.function_scoped_fixture]`): for each example truncate, insert permutation A (surrogate ids differ from permutation B by construction), run `enrich`, read the projection keyed by uri; truncate, insert permutation B, enrich, read, assert equal; also assert idempotence (a second enrich run changes nothing). Verified pattern (3 tests, 1.7 s, passing under `-W error`).

### Pattern 8: Alembic layout and programmatic commands (executed)

- Root `alembic.ini`: `script_location = %(here)s/src/truthtrail/db/migrations` (path relative to the ini, not the cwd).
- `env.py`: online mode only; `connection = config.attributes.get("connection")` else build an engine from the `DATABASE_URL` environment variable with `NullPool`; `compare_type=True`, `compare_server_default=True`. The URL never goes through `config.set_main_option` (F-14).
- Packaged head for readiness without an ini: `cfg = Config(); cfg.set_main_option("script_location", str(Path(truthtrail.db.__file__).parent / "migrations")); head = ScriptDirectory.from_config(cfg).get_current_head()` (1 ms; `get_heads()` should have length 1, assert it in a test).
- Programmatic proof used by the migration test and by a packaged `python -m truthtrail.db migrate` command (no ini needed in the image): `with engine.begin() as conn: cfg.attributes["connection"] = conn; command.upgrade(cfg, "head")`, then `command.check(cfg)` (raises `AutogenerateDiffsDetected`, a `CommandError`, on drift; verified by adding a column by hand), `command.downgrade(cfg, "base")` (leaves only `alembic_version`), `command.upgrade(cfg, "head")`. The CLI form `alembic check` exits 255 on drift.
- CI steps (D-29) run the CLI forms with `DATABASE_URL` pointing at the service container; the pytest migration test runs the programmatic forms in a fresh `truthtrail_test_<random>` database.
- Revisions are hand-reviewed; the functional unique index and the partial indexes autogenerate correctly (`postgresql_where`), and `alembic check` reports no phantom diffs for them on PostgreSQL 16.

### Pattern 9: `/v1` under the real `LimitedRouter`, errors and readiness (prototype executed against `create_app()`)

A scratch module registered `GET /v1/cascades` via `create_app(v1_registrars=[register])` with a sync `Depends(get_conn)`, a `V1Meta` model (`synthetic: Literal[False]`, `data_as_of: AwareDatetime | None`, `source_status: Literal["ok","empty","stale"]`, `source_mode: Literal["live","replay"]`) and the same `problem_body`/`problem_response` the repository uses. Observed:

| Check | Result |
|-------|--------|
| Router wrapping | `LimitedRouter.add_api_route` wrapping preserved the FastAPI signature: the dependency, `Query(ge=1, le=100)` and `Annotated` validators all worked (FastAPI 0.143.0, slowapi 0.1.10) |
| Keyset pagination | `(last_event_at, id) < (to_timestamp(:us / 1e6), :cid)` with `ORDER BY last_event_at DESC, id DESC LIMIT limit+1`; opaque cursor `base64url([microseconds, id])`; a walk with `limit=100` returned all 500 cascades once each, 500 unique |
| Malformed cursor | an `AfterValidator` on the query type raising `ValueError` gives 422 `application/problem+json` with `loc ["query","cursor"]` for 4 malformed samples; `limit=0` and `limit=101` also 422 |
| OpenAPI | declared responses `200, 422, 429, 500, 503` only (502 omitted by building the declaration dict from `PROBLEM_RESPONSES` minus 502); 503 content type `application/problem+json`; `Retry-After` header declared; `V1Meta.synthetic` renders `{"type":"boolean","const":false}`, `data_as_of` renders `anyOf string/date-time or null` |
| Outage | `ALTER DATABASE x ALLOW_CONNECTIONS false` plus `pg_terminate_backend` of the pooled sessions -> **503** `application/problem+json`, `Retry-After: 5`, body `{"type":"about:blank","title":"Service Unavailable","status":503,"detail":"The database is temporarily unavailable.","code":"database_unavailable","upstream":"database","synthetic":false,"source_status":"database_unavailable","data_as_of":null}`; captured logs contained only `database unavailable: OperationalError` (no host, socket path, database name or `port`); after `ALLOW_CONNECTIONS true` the next request returned 200 (pre-ping reconnect) |
| Statement timeout | a 300 ms `statement_timeout` with `pg_sleep(2)` -> 503 `database_timeout`, `Retry-After: 5` |

Exception classes (executed): a statement or lock timeout is `sqlalchemy.exc.OperationalError` with `orig` `psycopg.errors.QueryCanceled` (SQLSTATE 57014; a lock timeout is 55P03 `LockNotAvailable`); connection refusal, missing socket, a blackhole host (3.00 s with `connect_timeout=3`) and `ALLOW_CONNECTIONS false` are `OperationalError` with other SQLSTATEs or none; **pool exhaustion is `sqlalchemy.exc.TimeoutError`, which is not a `DBAPIError`** and must be registered separately (`QueuePool limit of size 2 overflow 0 reached, connection timed out, timeout 1.00`); `IntegrityError` for unique violations (23505). The text of connection errors includes the host or socket path (not the password), so handlers and logs use `type(exc).__name__` only. A request under pool exhaustion waits `pool_timeout` (2 s) before the 503; a blackhole database waits `connect_timeout` (3 s).

Registration facts: the repository's `UpstreamError` handler hard-codes `source_status="upstream_error"` (`api/problems.py:89`), so database errors need their own exception handlers (`app.exception_handler(OperationalError)` and `...(sqlalchemy.exc.TimeoutError)`), which Starlette selects by exception MRO. `Problem.source_status` is a free `str`, so the new values need no schema change. The `/v1` success `Meta` must be a **new** model: the existing `Meta` has `source_status: Literal["ok","empty","fixture"]` and a required non-null `data_as_of` (`schemas/models.py`). Readiness: the check callable is `SELECT 1` under a short `SET LOCAL statement_timeout`, then `SELECT version_num FROM alembic_version` compared to the packaged head (10 ms; a wrong revision returns `False`; a missing table raises and the registry logs the class name and fails closed); the registry already bounds each check at `CHECK_TIMEOUT = 2.0` (`core/readiness.py:29`), which a blackhole connect (3 s) exceeds, so the check fails closed by timeout first. F-11 applies to wiring.

Engine factory (one function; verified pieces): `create_engine(url, pool_size=5, max_overflow=5, pool_timeout=2, pool_pre_ping=True, connect_args={"connect_timeout": 3, "options": "-c statement_timeout=5000 -c lock_timeout=2000"})` plus `@event.listens_for(engine, "connect")` running `SET TIME ZONE 'UTC'` and committing (F-15). A statement timeout as small as 1 ms made SQLAlchemy's first-connect initialisation query fail (`QueryCanceled` inside `dialect.initialize`), so tests that provoke a timeout use a few hundred milliseconds and a slow query, not 1 ms. `postgresql://`, `postgresql+psycopg://` map to psycopg; `postgres://` raises `NoSuchModuleError`, so the single normalisation function rewrites the scheme; `str(url)` and `repr(url)` of a SQLAlchemy `URL` mask the password.

### Pattern 10: DATA-06 news job (facts verified; the container never calls GNews)

- **Quota facts (F-13):** Free = 100 requests/day, `max` up to 10, 12-hour delay, 1 request per second, daily reset 00:00 UTC; 403 "daily quota limit" is account-wide; 429 is the per-second limit. The defaults in the parameter register (60 per day, 10 per run, 12 h refresh, 20 topics) leave a margin: 20 topics x 2 refreshes = 40 calls per day.
- **Ledger:** insert the `news_fetches` row (`called_at`, outcome pending) in its own committed transaction **before** the call, count `called_at > now() - interval '24 hours'` inside the same transaction under the job's advisory lock, then update the outcome after the call; a crash between insert and call over-counts (safe).
- **Adapter reuse:** `services/gnews.py` keeps its key-in-header, no-redirect, typed-error behaviour (`GNEWS_URL = "https://gnews.io/api/v4/search"`, `BACKOFFS = (0.3, 0.6)`, `MAX_ATTEMPTS = 3`, `BUDGET = 8.0`, `RETRY_STATUSES = frozenset({500, 502, 503, 504})` [VERIFIED: src/truthtrail/services/gnews.py:30-43]; a 403 maps to 502 `upstream_forbidden` and a 429 to 503 `upstream_rate_limited` in `_classify_status`). New: `max_results` parameter (default 10) sent as `max`, `lang=en`. Add `from=` only if the owner wants a window. A topic phrase is at most 200 characters (provider rule).
- **Proof that no handler can reach the news client** (three layers, all runnable without the network): (1) a static AST import-closure over first-party modules reachable from `truthtrail.api`, with a negative control that injects a fake import; (2) a **fresh-interpreter** test: `python -I -c "import truthtrail.main; from truthtrail.api.app import create_app; create_app(); import sys; assert not {'requests','urllib3','websockets','zstandard','truthtrail.services.gnews'} & set(sys.modules)"` - verified that the third-party application dependencies (fastapi, starlette, pydantic, pydantic-settings, slowapi, limits, cachetools, uvicorn's proxy middleware) import none of `requests`, `urllib3`, `websockets`, `httpx`; today `import truthtrail.api.app` loads `requests` and `truthtrail.services.gnews` only through `api/analyze.py`, which D-27 removes, so the test is green after the last plan and red (as it should be) before; SQLAlchemy, psycopg and Alembic do not require `requests` (the scratch venv with them has none installed); (3) a dynamic sweep of every GET route with `fetch_news` patched to fail the test and `responses` rejecting any GNews URL, plus a run with `GNEWS_API_KEY` unset.
- **Topics:** subject or event phrases in `news_topics.toml` (parsed with `tomllib`), validated by a test (<= 20, <= 200 characters, no personal-name heuristics beyond the review in the plan summary).

### Pattern 11: Test infrastructure (all executed here)

**Postgres provisioning (D-28), 2.5 s for three tests including cluster start:**

```python
exe = bindir / "initdb"                                    # TRUTHTRAIL_PG_BIN, PATH, /usr/lib/postgresql/*/bin, Program Files\PostgreSQL\*\bin
root = Path(tempfile.mkdtemp(prefix="tt-pg-"))             # NOT pytest tmp_path: /tmp/pytest-of-root is 0700 and the postgres user cannot enter it
if os.name != "nt" and os.geteuid() == 0:
    pw = pwd.getpwnam("postgres"); os.chown(root, pw.pw_uid, pw.pw_gid); os.chmod(root, 0o755)
    prefix = ["runuser", "-u", "postgres", "--"]
run(prefix + [initdb, "-D", root/"data", "-A", "trust", "-U", "postgres", "-E", "UTF8", "--locale=C", "--no-sync"])
run(prefix + [pg_ctl, "-D", root/"data", "-w", "-l", root/"log", "-o",
   f"-c listen_addresses='' -c unix_socket_directories={root} -c fsync=off -c synchronous_commit=off -c full_page_writes=off -c port={port}", "start"])
# URL: postgresql+psycopg://postgres@/postgres?host=<root>&port=<port>      (Windows: listen_addresses='127.0.0.1', host=127.0.0.1)
# per session: CREATE DATABASE "truthtrail_test_<random>" ENCODING 'UTF8' TEMPLATE template0 ; alembic upgrade head ; DROP DATABASE ... WITH (FORCE)
# teardown: pg_ctl -m immediate -w stop ; rmtree
```
Failure modes reproduced: default `initdb` here gives SQL_ASCII (psycopg returns `bytes`; F-10); `pytest-postgresql` as root fails at `pg_ctl stop`; a socket directory under a 0700 parent is unreachable. `runuser` is util-linux, present here; it is only reached when euid is 0, which is the container, never the owner's Windows machine or GitHub runners. `TEST_DATABASE_URL` takes precedence; tests never read `DATABASE_URL` (the existing autouse fixture scrubs it).

**Outage injection without stopping the server** (portable to CI service containers): `ALTER DATABASE <name> ALLOW_CONNECTIONS false` followed by `pg_terminate_backend` of that database's backends (excluding the admin connection) makes every new connection fail immediately (`FATAL: database "..." is not currently accepting connections`), and `ALLOW_CONNECTIONS true` restores service; use it with `try/finally`. A closed TCP port (`127.0.0.1:1`) is the fast static variant (refusal in 0.00 s). Both were verified to produce `OperationalError`.

**Engines and warnings (F-09):** every engine created in a test is disposed in a finalizer; `pytest -W error` passed only after that.

**Hypothesis with a real database:** `@settings(max_examples=25, deadline=None, derandomize=True, database=None, suppress_health_check=[HealthCheck.function_scoped_fixture])`, `TRUNCATE` at the start of each example (a function-scoped fixture is not reset between examples). Idempotent-upsert property verified (30 examples).

**Markers and the floor:** register `requires_db` and run with `--strict-markers`; the CI step asserts the count of executed `requires_db` tests above a floor read from the collected set.

### Pattern 12: Loopback WebSocket server for adapter tests (executed with websockets 17.2)

```python
from websockets.asyncio.server import serve
from websockets.http11 import Response
from websockets.datastructures import Headers

def process_request(connection, request):          # refuse by returning a Response; return None to accept
    if cursor_param(request.path) == "1":
        return Response(400, "Bad Request", Headers({"Content-Type": "application/json"}), b'{"error":"CursorTooOld","message":"floor 5"}')
async with serve(handler, "127.0.0.1", 0, subprotocols=["xrpc.v1.json"], process_request=process_request) as server:
    port = server.sockets[0].getsockname()[1]
    ...connect(f"ws://127.0.0.1:{port}/xrpc/network.bsky.jetstream.subscribeEvents?cursor=7", proxy=None)
```
Verified: replay from `cursor=7` delivered 7, 8, 9 only; closing with code 1011 after four frames surfaces as `ConnectionClosed` on the client; a 400 with a JSON body surfaces as `InvalidStatus` whose `response.body` carries the bytes; a 403 likewise. `proxy=None` is mandatory in tests because the container (and many corporate machines) set proxy variables and the default `proxy=True` would route loopback through them unless `NO_PROXY` covers it. Frames served by the loopback server come from the recorded fixture (one real frame per dialect is the contract input).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| WebSocket protocol, ping/pong, framing, proxy | raw sockets or a custom handshake | `websockets` 17.2 | Keepalive, proxy discovery, `max_size`, loopback server for tests are built in |
| Dictionary zstd | a custom decoder | `zstandard` 0.25.0 with `max_output_size` | Bounded output blocks decompression bombs |
| Keyed pseudonyms | plain or salted hashes, home-made MACs | `hmac` + `hashlib.sha256` + `base64.b32encode` (stdlib) | Constant-time primitives, domain separation by prefix |
| Idempotent writes | read-then-write | `INSERT ... ON CONFLICT DO NOTHING RETURNING` | Race-free, exact counts |
| Schema migrations and drift checks | hand-written SQL scripts | Alembic 1.20.0 + `command.check` | Drift fails CI |
| Pagination | OFFSET | keyset on `(sort_key, id)` | Stable under inserts, index-friendly |
| Time buckets | Python loops over rows | `date_bin(interval, ts, origin)` | Session-zone independent, one query |
| URL parsing | regex | `urllib.parse.urlsplit` (`hostname` is lowercased and strips userinfo and port) | `https://nytimes.com@evil.example/` resolves to `evil.example` |
| Suffix matching of allowlisted hosts | a public-suffix library or `rsplit('.', 2)` heuristics | exact host or `host.endswith("." + entry)` against explicit allowlist entries | `evilnytimes.com` and `nytimes.com.evil.example` do not match; no registrable-domain guessing |
| Single-flight jobs | lock files | `pg_try_advisory_lock` | Verified; dies with the connection |
| Test Postgres on a developer machine | Docker-only assumptions | the 80-line fixture above | Works as root in the container, on Windows and in CI |

**Key insight:** every hard part of this phase is already a solved problem in a library or in PostgreSQL; the risk is in glue (cursor semantics, control frames, timezone, encoding, disposal), which is why this document records the executed recipes.

## Common Pitfalls

| # | Pitfall | What goes wrong | How to avoid | Warning sign |
|---|---------|-----------------|--------------|--------------|
| 1 | Fixture tokens that look like keys (F-01) | `gitleaks` default `generic-api-key` fires on `"rkey":"<random base32>"` (844 of 3,000 frames); CI gitleaks job goes red; the temptation is a path allowlist D-04 forbids | Sequential padded base32 counters; never random tokens under a field name containing `key`/`secret`/`token`/`password`; run the pinned scratch gitleaks over the fixture inside the fixture plan | `leaks found: N` for the fixture path |
| 2 | SQL_ASCII database (F-10) | psycopg 3 returns `bytes` for text; SQLAlchemy's dialect start-up fails with `TypeError: cannot use a string pattern on a bytes-like object` | `initdb -E UTF8 --locale=C`; `CREATE DATABASE ... ENCODING 'UTF8' TEMPLATE template0`; assert `show server_encoding` in the fixture | That `TypeError` on the first connect |
| 3 | `postgres` user cannot enter the data directory | `initdb` or `pg_ctl` fails with permission errors when the directory sits under pytest's 0700 temp root | `tempfile.mkdtemp` plus `chown`/`chmod 755` before switching user | "could not access directory" |
| 4 | Undisposed engines under `filterwarnings = error` (F-09) | psycopg `ResourceWarning: <Connection> was deleted while still open` becomes a failing `PytestUnraisableExceptionWarning`, often in an unrelated later test | Single engine factory; `dispose()` in lifespan shutdown and in fixture finalizers | Failures that mention a connection object address |
| 5 | URL through `Config.set_main_option` (F-14) | `%` in an encoded password raises `ValueError` whose message contains the whole URL | `config.attributes["connection"]` or the environment in `env.py` | Any traceback printing a `postgresql://` string |
| 6 | Session time zone (F-15) | `timestamptz` comes back in `PGTZ` or the cluster zone; `options=-c timezone=UTC` is overridden by `PGTZ` | `connect` event `SET TIME ZONE 'UTC'`; `.astimezone(UTC)` at the boundary; `date_bin`, not `date_trunc` | Offsets other than `Z` in API output |
| 7 | Control frames treated as events (F-02) | A seq-less `#info` frame has no `time`; code that reads `payload["time"]` crashes or stores a bogus cursor | Dialect returns `Control`; only events move the cursor | `KeyError: 'time'` right after connecting with an old cursor |
| 8 | Poison oversized frame (F-04) | `ConnectionClosedError` at the same frame on every rewind | `maxMessageSizeBytes` below `max_size`; classify 1009 as `oversize_frame` and stop | Reconnect loop with an unchanged cursor |
| 9 | v1 host surprises | `kinds` ignored, `collections` silently ignored (full network, 435 events/s), `compress=true` conflicts with permessage-deflate | One dialect module; contract test per dialect from one real frame; `compression=None` for v1 compress | Counts of unexpected collections |
| 10 | Mixed-key bulk insert | `StatementError: A value is required for bind parameter 'text'` for rows missing a key | One `to_row()` builds every dict with the full key set | First batch containing a root and a reply |
| 11 | `rowcount` after `executemany` | `-1`, so duplicate counts silently wrong | `RETURNING uri` and count the result | `inserted + duplicates != received` |
| 12 | Weak property strategy (Pattern 7) | Order-dependent resolver passes 200 random examples | Parents biased into the set, conflicting duplicates, ties; keep the three mutants as tests | Mutants surviving |
| 13 | Function-scoped fixtures and Hypothesis | `FailedHealthCheck` and state leaking across examples | Suppress `function_scoped_fixture`; `TRUNCATE` at the start of each example | Flaky DB properties |
| 14 | Tiny `statement_timeout` | SQLAlchemy's first-connect `initialize()` queries are cancelled | Use 200-300 ms with a deliberately slow query in tests | `QueryCanceled` inside `dialect.initialize` |
| 15 | Pool exhaustion is not a `DBAPIError` | An `OperationalError`-only handler lets `sqlalchemy.exc.TimeoutError` fall to a generic 500 | Register both classes | 500 under concurrent load with a small pool |
| 16 | Logging `str(exc)` | Connection errors include the host or socket path | `type(exc).__name__` only, enforced by a marker-value log test (Phase 2 pattern) | Host names in `caplog` |
| 17 | Readiness wiring (F-11) | `register_default_checks(registry)` has no engine; `TestClient(app)` without `with` never runs the lifespan | Inject `engine` into `create_app`; the check fails closed without one | `/ready` 503 in tests that forgot the engine |
| 18 | `/v1` `Meta` reuse | The existing `Meta` has `Literal["ok","empty","fixture"]` and a non-null `data_as_of` | New `V1Meta` (D-24) | OpenAPI shows `fixture` on a `/v1` route |
| 19 | Declaring 502 on `/v1` | D-23 forbids it; `PROBLEM_RESPONSES` includes 502 | Build the `/v1` declaration dict from `PROBLEM_RESPONSES` minus 502; a test walks OpenAPI | A 502 entry in the golden |
| 20 | Catch-up bounds vs cadence (F-05) | A cron gap larger than the per-run coverage never closes; lag grows | Bounds and cadence chosen together; `data_as_of` and gap counts shown | `ingest lag` rising run over run |
| 21 | First-come selection bias (F-06) | The feed is the roots of the first 38 minutes after each slot frees | Deterministic sampling parameter; disclose | Cascades clustered in time |
| 22 | 90-day retention at full yield (storage) | About 2.9 GB for 90 days of every eligible root | Ratify OD-1 and OD-3 together (storage table below) | `capacity_reached` runs |
| 23 | Trusting `createdAt` | 1.1 percent of posts claim more than 60 s in the future, 2.4 percent are over an hour old (backdated or imported) | Never order by it; NULL when outside 1970..now+1y | Negative cascade durations |
| 24 | AppView thread as ground truth | A 688-reply post returned 243 nodes | Use `getPosts` counts for cross-checks only | Thread node counts below `replyCount` |
| 25 | GNews 403 as a per-topic failure | Every remaining topic repeats the same quota error | Stop the run on 403 like on 503 | Ten identical failures in a run |
| 26 | Docker Hub digest resolution | The registry API answered HTTP 429 during this research | Resolve digests at planning time with a retry or from the Hub tags API (values below are CITED, not registry-verified) | `docker pull` by digest fails |
| 27 | Windows | No `runuser`, no unix sockets, `winget` package id unverified, psycopg needs `tzdata` (in the lock) | Branch on `os.name`; TCP loopback; the owner routes in D-30; commands below marked unverified | Fixture errors naming `geteuid` |

## Code Examples

### Edge derivation and allowlist matching (executed over 93,847 live create frames: 24,341 root candidates, 20,381 replies, 46,210 reposts, 2,913 quotes, 2 dropped, no exception)

```python
AT_URI = re.compile(r"^at://(did:(?:plc|web):[A-Za-z0-9._%:-]+)/([A-Za-z0-9.]+)/([A-Za-z0-9._~:-]+)$")
POST = "app.bsky.feed.post"

def post_target(uri: object) -> str | None:
    m = AT_URI.match(uri) if isinstance(uri, str) else None
    return uri if m and m.group(2) == POST else None             # quotes of feeds and reposts of other records fall out here

def derive(collection: str, record: dict) -> Edge | None:        # Edge(kind, parent, reply_root, quoted, via)
    if collection == "app.bsky.feed.repost":
        subject = post_target((record.get("subject") or {}).get("uri"))
        return None if subject is None else Edge("repost", subject, via=(record.get("via") or {}).get("uri"))
    if collection != POST:
        return None
    emb = record.get("embed") or {}
    et = emb.get("$type")
    rec = emb.get("record") if et == "app.bsky.embed.record" else (
        (emb.get("record") or {}).get("record") if et == "app.bsky.embed.recordWithMedia" else None)
    quoted = post_target((rec or {}).get("uri"))
    if isinstance(record.get("reply"), dict):                    # reply wins over quote (D-12)
        parent = post_target(record["reply"].get("parent", {}).get("uri")); root = post_target(record["reply"].get("root", {}).get("uri"))
        return None if parent is None and root is None else Edge("reply", parent, reply_root=root, quoted=quoted)
    return Edge("quote", quoted) if quoted else Edge("root-candidate", None)

def allowed(host: str, allowlist: frozenset[str]) -> bool:        # host from urlsplit().hostname, www. stripped
    return host in allowlist or any(host.endswith("." + d) for d in allowlist)
```
Executed assertions: `nytimes.com`, `www.nytimes.com`, `news.bbc.co.uk` allowed; `evilnytimes.com`, `nytimes.com.evil.example`, `bbc.co.uk.evil.example`, empty host refused; `https://nytimes.com@evil.example/x` resolves to host `evil.example`. A post that only quotes a non-post record becomes a root candidate (it is a top-level post; it may still seed if it carries an allowlisted link).

### Sequential scrub tokens (passes gitleaks 8.30.1 with 0 findings over 3,000 frames)

```python
TID = "234567abcdefghijklmnopqrstuvwxyz"            # base32-sortable alphabet used by TIDs and rkeys
def counter_token(i: int, width: int, pad: str) -> str:
    s = ""
    while True:
        s = TID[i % 32] + s; i //= 32
        if i == 0: break
    return pad * (width - len(s)) + s
# rkey / rev: counter_token(n, 13, "2")   did:plc: counter_token(n, 24, "a")   (lowercase base32, syntactically valid, entropy near 1)
```

### Scratch gitleaks over a candidate fixture (outside the repository)

```bash
bash scripts/install_gitleaks.sh "$SCRATCH/gl"          # pinned 8.30.1, checksum verified, destination refused inside the repo
"$SCRATCH/gl/gitleaks" dir <fixture-dir> --no-banner --redact --exit-code 1
```

### Recorded-frame sizes for the fixture budget (D-04, 1.5 MB)

Frames of the 231 eligible roots plus their 87 children total about 318 frames, about 250 KB before scrubbing; 1,000 negative-control frames add about 700 KB; text, cid and card text removal shrinks both. A 17.8-minute window yields cascades with at most 10 children, so the cut must be **stratified**, not "all tracked roots": take every cascade above a size threshold from the 60-minute run, a bounded random sample of small ones, a bounded negative-control sample, and a few delete and account frames, with the byte budget enforced by the cutter and recorded in the manifest.

## State of the Art

| Old approach | Current approach | When changed | Impact |
|--------------|------------------|--------------|--------|
| Jetstream v1 `wantedCollections`, `time_us`, `cursor` as sequence | v2 `collections`/`kinds`/`dids`, `time`/`witnessedAt`, `seq`, subprotocol `xrpc.v1.json`, `#info` frames, `maxMessageSizeBytes`, `zstdDictionary` | v2 launched with the 2026-08-13 protocol-services announcement (STACK.md) | One dialect module (D-05) |
| zstd dictionary vendored in the client repo | Dictionary fetched by id from `getZstdDictionary` (immutable, cacheable) | v2 | No artifact to vendor if compression is ever enabled |
| Reposts as anonymous stars | Optional `via` strong reference on repost records (24.2 percent populated) | recent lexicon addition | Observed reshare attribution is available (F-07) |
| SQLAlchemy 2.0 with explicit `postgresql+psycopg://` | 2.1: `postgresql://` defaults to psycopg 3 | 2026 | URL normalisation is only needed for `postgres://` |
| websockets legacy client | `websockets.asyncio.client.connect`, `proxy=True` default, built-in reconnect iterator | websockets 14-17 | Use the new API; own reconnect loop for cursor changes |
| `searchPosts` on the public AppView | 403 load-shedding | known | Seeding stays on the stream (OD-3 option D rejected) |
| User consent for reuse implicit | Draft "User Intents for Data Reuse" (proposal 0008) | March 2025 draft | Watch; not enforceable, status unverified |

**Deprecated/outdated:** the documentation sentence that v2 events carry a `cursor` field (frames carry `seq`); the CONTEXT note to pass `proxy=HTTPS_PROXY` (default works); `psycopg[pool]` for this design.

## Privacy, Retention and Storage (question 7; inputs for OD-1, OD-2, OD-3 - not decisions)

**Pseudonymisation (D-17, locked) - implementation facts.** The scheme works as designed: parent resolution, delete matching and unique-account counts are equality joins on keyed values (Pattern 3). Considered and not needed: per-row salts (break joins), plain or publicly salted hashes (dictionary-reversible; the DID space is enumerable), a tokenisation table (would store DIDs). The API shows at most 8 characters of a pseudonym. Honest limits for DOC-02: pseudonymisation is not anonymisation (GDPR Recital 26 quoted above); stored `observed_at` plus, during the retention window, root text and the publisher link allow re-linking by anyone holding a network archive; a leaked secret plus a leaked database allows dictionary reversal; rotating the secret re-keys everything and is a rebuild.

**Deletion propagation (four paths, all by the same tombstone rule).** (1) `delete` commit on a post or repost: keyed lookup, 0.02 ms; (2) `account` event with `status` `deleted` or `takendown`: pseudonym lookup then account-wide tombstone; (3) `sync` event: same as (2) per the Jetstream documentation ("a sync divergence marker removes all of that account's records"); (4) the retention purge (text NULLed after `RETENTION_TEXT_DAYS`, cascades hard-deleted after `RETENTION_CASCADE_DAYS`, tombstones after `RETENTION_TOMBSTONE_DAYS`) bounds anything missed during a gap; plus the optional operator `erase` by DID read from stdin. Measured deletion behaviour in the 17.8-minute window: 4,005 post deletes (4.0 percent of events) of which 763 targeted posts created inside the window (1.6 percent of window post creates were deleted within the window; in-window delete latency median 41 s, P90 338 s, max 999 s; the sample is censored at 17.8 minutes); 1,429 repost deletes of which 366 in-window (0.8 percent; median 26 s). So about 19 percent of post deletions retract content younger than 18 minutes, and the rest remove older content; a short text TTL covers only the first kind by itself, which is why the deletion path matters more than the TTL (S-7 must extend this over hours).

**Per-row storage (S-8 inputs, measured on PostgreSQL 16.15 with the D-20 shape):** event 283 bytes with its indexes; cascade 622 bytes; claim 567 bytes; account 143 bytes; root text adds about its length (median post text 65 characters, P95 286, max 572 in 47,635 posts, so about 150 bytes on average with overhead). Database size of the 195,102-event prototype (60,000 accounts, 500 cascades, no claims yet): 75 MB. Per root all-in: about 1.7 KB (root event with text 0.43 KB, cascade 0.62 KB, claim 0.51 KB at 90 percent uniqueness, account share 0.08 KB).

**Storage by scenario** (formula: roots x 1.7 KB + children x 0.29 KB; the child rate is the **window-truncated lower bound** of 1,074 stored events/hour less roots, so real cascades will be larger; budget `DB_BUDGET_BYTES` = 300 MB, free tier about 0.5 GB):

| Scenario (eligible roots 780/h = 18,720/day) | Roots retained | Approx. size |
|-----------------------------------------------|----------------|--------------|
| Every eligible root, 90-day cascade retention (RT-2 as written) | 1.68 M | about 2.9 GB (infeasible) |
| Every eligible root, 14 days | 262,000 | about 450 MB (over budget) |
| Every eligible root, 7 days | 131,000 | about 230 MB |
| Cap 500 active / 48 h (at most 250 roots/day), 90 days | 22,500 | about 45 MB (but 1.34 percent of eligible roots, first-come) |
| Cap 2,000 active / 48 h, 90 days | 90,000 | about 180 MB |
| Hash sample 1-in-8 (2,340 roots/day), 90 days | 211,000 | about 365 MB (over budget) |
| Hash sample 1-in-8, 30 days | 70,000 | about 120 MB |
| Hash sample 1-in-8, 90 days, cascades with zero children dropped at 7 days (84 percent of roots in-window) | 34,000 | about 77 MB |

Reading for the owner: the binding constraint is **root count times retention**, not text and not events. The three OD choices interact: OD-3's sampling rate and caps set the roots per day; OD-1's cascade retention multiplies them; a "drop dormant cascades early" rule (a retention refinement not in CONTEXT's RT options) is the cheapest way to keep a long feed history. Whatever is ratified must be re-checked against the measured S-8 bytes per row from the real 60-minute run.

**OD-2 facts.** Situation (A) re-rooting cannot occur under allowlist seeding because roots are top-level, non-reply, non-quote posts and every reply names the thread root. In the window 38 of the 231 tracked cascades had children: 56 reposts, 29 replies and 2 quotes. Situation (B) claim-level duplicates: 59 domains, 178 authors for 231 roots; the same canonical article URL shared by several roots is expected for wire stories (not yet counted; S-9 counts it). M1's `claim_key` unique column makes (B) a plain upsert.

**Honesty caveats this phase hands to DOC-02 (unchanged list plus two):** repost-star caveat (now with the `via` nuance, F-07); allowlist selection bias and whatever sampling is ratified; pseudonymised not anonymised; deletions honoured with the stated lag and the retention windows; observed subset of public posts; plus (new) the GNews Free-plan context is delayed 12 hours and non-commercial, and (new) cascades start at the moment the root was first seen, so a cascade view never shows what happened before tracking began.

## Security Domain

Config: `security_enforcement` true, ASVS level 1, `block_on: high` (`.planning/config.json`).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V1 Architecture / V14 Configuration | yes | Env-only secrets (`DATABASE_URL`, `PSEUDONYM_SECRET`, `COLLECTOR_CONTACT`, `GNEWS_API_KEY`), `SecretStr`, fail-fast per entrypoint, least privilege (the API holds no pseudonym secret and no news key), digest-pinned service image |
| V2/V3 Authentication, sessions | no | Public read-only API; no Bluesky credential in this phase |
| V4 Access Control | limited | CORS allow-list unchanged; `/v1` read-only; no write route |
| V5 Input Validation | yes | Pydantic models with `extra="forbid"`, `Query(ge/le)`, validated opaque cursor, typed `Literal` filters; frame validation in the normaliser; at:// URI regex |
| V6 Cryptography | yes | `hmac`/`hashlib`/`base64` stdlib only; 32-byte secret minimum; domain-separated prefixes; no custom crypto |
| V7 Error Handling and Logging | yes | problem+json for 503/422/500; class names only; marker-value tests prove no URL, SQL, DID or secret in bodies or logs |
| V8 Data Protection | yes | Pseudonymised identifiers, text only on roots with TTL, tombstones, purge, `erase` |
| V10 Malicious Code / supply chain | yes | Exact pins, lock review of the 8 added packages, `pip-audit`, SHA/digest pinning |
| V12/V13 API and Web Service | yes | Rate limiting by construction, bounded responses (5,000 nodes, 100 per page, 500 buckets), statement timeouts, golden OpenAPI |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Hostile or malformed frame (huge, wrong types, deep JSON) | DoS / Tampering | `maxMessageSizeBytes`, `max_size`, strict shape validation, counted drops, bounded run (events, seconds, stored rows) |
| Poison frame causing a reconnect loop | DoS | Classify 1009, stop loudly (F-04) |
| Server-controlled zstd dictionary or frames | DoS | Fetch by id from the same host, verify `dict_id`, `max_output_size` on every decompress; compression stays optional |
| SSRF through post links | Info disclosure | Links are parsed, never fetched, followed or resolved (D-13); test with a socket guard |
| Allowlist spoofing (`evilnytimes.com`, `nytimes.com@evil.example`) | Spoofing | `urlsplit().hostname`, exact-or-dot-suffix match, shorteners never seed |
| SQL injection | Tampering | Parameterised Core/ORM only; AST test forbids f-string SQL; `SET LOCAL statement_timeout` uses integer literals from settings, not user input |
| Keyset cursor tampering | Tampering | Cursor decoded and type-checked, used only as bound parameters; sort and filters re-validated |
| Unbounded response | DoS | Hard caps and `truncated` fields (D-23); rate limit per IP by `LimitedRouter` |
| Credential or PII leak through errors/logs | Info disclosure | F-14, Pitfall 16; SQLAlchemy URL masking; `COLLECTOR_CONTACT` treated as operator data; log lines carry counts, classes, 8-character pseudonym prefixes |
| Pseudonym reversal | Info disclosure | HMAC with a server-side secret; API holds none; one-way rebuild on rotation |
| Tombstone resurrection by replay | Tampering | `ON CONFLICT DO NOTHING` keeps the tombstone row (verified) |
| Missed delete during a gap | Info disclosure (stale content) | Retention purge bounds exposure; `erase`; gap counts exposed |
| Double run of the same job | Tampering (ledger, quota) | `pg_try_advisory_lock` single-flight (verified) |
| GNews quota exhaustion | DoS (quota) | DB ledger, per-run and per-day budgets, stop on 403/503, no request handler can reach the client |
| Tracked-set memory growth | DoS | Cap on active roots and stored events; sampling parameter |
| Bluesky TLS interception by the container proxy | Tampering | Verification stays on; trust store from `SSL_CERT_FILE`; never disable |
| Dependency compromise | Tampering | Exact pins in `uv.lock` with hashes, `pip-audit`, gitleaks, one consolidated lock-review checkpoint |

The repository's credential backstop is `CREDENTIAL_RX = (?i)(api[_-]?key|passw(or)?d|secret|token)\s*[:=]\s*["'][A-Za-z0-9_\-./+]{16,}["']` over git-visible `.py .md .json .yml .yaml .toml .txt .ini .cfg .sh` files outside `tests/` [VERIFIED: tests/test_no_hardcoded_credentials.py:15-18]: plan documents, workflow YAML and `.env.example` must not contain a quoted 16+ character literal after those words. A CI service password of `ci-throwaway` and a DSN `postgresql+psycopg://postgres:ci-throwaway@localhost:5432/postgres` passed both that regex and gitleaks 8.30.1 (0 findings) in a scratch test.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.13 | everything | yes | 3.13.16 | - |
| uv | lock, sync | yes | 0.11.32 (repo CI pins 0.13.1; `uv lock --check` passes with 0.11.32) | - |
| PostgreSQL server binaries | DB tests | yes, `/usr/lib/postgresql/16/bin` (`initdb`, `pg_ctl`, `postgres`, `pg_isready`, `pgbench`), `postgres` user uid 102 | 16.15 | CI service container (17) |
| `psql` client | debugging | yes | 16 | - |
| Docker | image build, CI service container | no | - | GitHub Actions (service container, `docker` job); first run is the verification |
| Outbound to Bluesky (Jetstream v2 east/west, v1, `public.api.bsky.app`, `bsky.network`, `bsky.social`, `atproto.com`) | spike, probes | yes through the agent proxy | - | if 403 returns: stop and report, never substitute data (D-01) |
| `raw.githubusercontent.com`, PyPI JSON, Docker Hub tags API, `docs.github.com` | research, planning | yes | - | - |
| `github.com` HTML and the GitHub REST API for other repositories | - | no (HTTP 403) | - | `raw.githubusercontent.com` works |
| `WebFetch` tool to `docs.github.com` and `gdpr-info.eu` | - | DNS failure in the tool; both pages were reachable with `curl` through the proxy | - | `curl` |
| Docker Hub registry (manifests) | digest pinning | rate limited (HTTP 429 once) | - | resolve at planning time; the Hub tags API returned `17.11-bookworm` -> `sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826` and `17.11` (trixie) -> `sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3` (2026-10-18; CITED, not registry-verified) |
| gitleaks | fixture and docs scan | yes in scratch via `scripts/install_gitleaks.sh` | 8.30.1 | - |
| pypistats.org | package statistics | no | - | PyPI first-upload dates used |
| `gh` / GitHub API for this repository | CI status | not used here | - | owner or `mcp__github` tools |
| Windows 11 + PowerShell + uv | S-12, owner UAT | not testable here | - | owner-side (below) |
| Free-tier Postgres (Neon), GitHub-hosted runner egress to Bluesky | Phase 6 | not testable here | - | Phase 6 verification items |

**Missing with no fallback:** none for planning. **Missing with fallback:** Docker (CI), Windows (owner), runner egress (Phase 6).

### What is verifiable where

| Claim or deliverable | In this container | Owner side or CI |
|----------------------|-------------------|------------------|
| Jetstream v2 behaviour, cursors, volume, shapes | yes (done; the spike repeats it for 60 minutes twice) | Windows 5-minute run for S-12 |
| AppView limits and cross-check | yes | - |
| SQL, constraints, Alembic up/down/check, Hypothesis with DB, outage injection, fixture provisioning as root | yes (PostgreSQL 16) | CI repeats on 17 with a service container |
| Docker build, `docker` job, service container health check, pinned digest pull | no | CI (first push is the proof) |
| Windows provisioning (`winget`, TCP loopback cluster, wheels, system proxy) | no | owner |
| Runner reachability of Bluesky, long-run server behaviour, sustained rate limiting | no | Phase 6 verification |
| Live GNews behaviour with a real key | never from here | owner, UAT item |

### Owner commands (PowerShell, Python 3.13, uv) - optional re-run of the spike on Windows

Windows behaviour is **not verified from here**; the Linux equivalents were executed. Before plan 03-01 lands, a standalone read-only probe (no repository, no credentials, no database) can be run from any folder; it opens each of the two v2 hosts for the given seconds (default 20, capped at 300) and prints counts only:

```powershell
# save the probe below as win_probe.py, then:
uv run --no-project --python 3.13 --with websockets==17.2 python .\win_probe.py 30
# behind a corporate proxy or TLS inspection (verification stays ON):
$env:HTTPS_PROXY = "http://proxy.example:8080"
$env:SSL_CERT_FILE = "C:\path\to\your-corporate-ca.pem"
```
```python
import asyncio, json, sys, time
import websockets

HOSTS = ["jetstream.us-east.bsky.network", "jetstream.us-west.bsky.network"]
SECONDS = min(float(sys.argv[1]) if len(sys.argv) > 1 else 20.0, 300.0)

async def probe(host: str) -> None:
    url = (f"wss://{host}/xrpc/network.bsky.jetstream.subscribeEvents"
           "?collections=app.bsky.feed.post&collections=app.bsky.feed.repost")
    t0 = time.monotonic(); counts: dict[str, int] = {}; nbytes = 0
    try:
        async with websockets.connect(url, subprotocols=["xrpc.v1.json"], open_timeout=15, max_size=2 * 1024 * 1024) as ws:
            handshake = time.monotonic() - t0; end = time.monotonic() + SECONDS
            while time.monotonic() < end:
                try:
                    frame = await asyncio.wait_for(ws.recv(), timeout=max(0.1, end - time.monotonic()))
                except asyncio.TimeoutError:
                    break
                nbytes += len(frame); p = json.loads(frame)["payload"]
                key = p["$type"].split("#")[-1] + ("/" + p["operation"] + "/" + p["collection"] if "operation" in p else "")
                counts[key] = counts.get(key, 0) + 1
        elapsed = time.monotonic() - t0; total = sum(counts.values())
        print(f"{host}: OK handshake={handshake:.2f}s events={total} ({total/elapsed:.0f}/s) bytes={nbytes}")
        for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"    {v:6d} {k}")
    except Exception as exc:
        print(f"{host}: FAILED {type(exc).__name__}: {str(exc)[:160]}")

async def main() -> None:
    for h in HOSTS:
        await probe(h)
asyncio.run(main())
```
(On this container the same script printed `OK ... events=439 (73/s)` for east and `451 (82/s)` for west in 5 seconds.) After plan 03-01 lands, the owner commands from D-30 apply unchanged and are the ones to use:

```powershell
cd C:\path\to\TruthTrail
git pull
uv sync
uv run python scripts\bluesky_spike.py probe
uv run python scripts\bluesky_spike.py record --seconds 300 --out spike-output
uv run python scripts\bluesky_spike.py analyze --in spike-output --summary
# paste the printed summary (counts and rates only) under "Windows result" in 03-SPIKE-DECISION.md
```
For the owner's own test database (D-30): `winget install PostgreSQL.PostgreSQL.17` then `$env:TEST_DATABASE_URL = "postgresql+psycopg://postgres:<password>@localhost:5432/postgres"` (the winget package id and the installer's default port are **unverified here**), or `$env:TRUTHTRAIL_PG_BIN = "C:\Program Files\PostgreSQL\17\bin"` so the fixture builds a throwaway cluster (it passes `-E UTF8 --locale=C`; `--locale=C` with `-E UTF8` is expected to work on Windows but is unverified), or `uv run pytest -m "not requires_db"` and rely on CI.

## Spike Tool Design Brief (for plan 03-01; facts this research learned)

- **Shape:** `scripts/bluesky_spike.py` with subcommands `probe` (S-1/S-12: four hosts, HTTPS status, WebSocket upgrade, subprotocol, first frame, handshake time, one sample frame per dialect, whether `kinds` is honoured - v2 honours it, v1 does not), `record` (bounded raw log), `analyze` (offline, from the raw log: S-2, S-4, S-5, S-6, S-7, S-9), `cursor-test` (S-3), `reconnect-test` (S-11), `appview-check` (S-13), and an S-8 helper that uses the throwaway-cluster recipe above. Standard library plus `websockets`; HTTP via `urllib` (verified to honour the proxy variables and `SSL_CERT_FILE`).
- **Raw log:** write gzip level 1 (`.jsonl.gz`): the 100,000-frame log was 81.0 MB raw and 24.1 MB gzipped at level 1 (ratio 0.30, 85 MB/s); a 2-hour run is about 550 MB raw, 165 MB gzipped. Wrap each frame with the arrival time (`{"rx": <unix ms>, "f": <frame>}`) so ingest lag and arrival-order inversions are computable; keep it git-ignored under `spike-output/`.
- **Safety:** hard `--max-seconds` <= 7200 and `--max-bytes`; stop on HTTP 401/403; User-Agent with the repository URL; transient `ConnectionResetError`/`ConnectError` retried with backoff (observed early in the session); never store credentials (there are none); analysis outputs contain counts and rates only, never DIDs, handles or text.
- **Additions this research recommends:** S-13 coverage cross-check (`getPosts`, 25 URIs per call, compare child counts to `replyCount`/`repostCount`/`quoteCount`, report exact-match and observed-at-most shares); in S-3 also test a seq cursor below the floor, a future seq cursor and the `#info` frames (F-02); in S-4 compare east and west `witnessedAt` for the same event over >= 5 minutes (F-03); in S-5 report the eligible-root rate per hour **and** the fill time of the proposed cap and the share of eligible roots accepted (F-06), plus children per root at 15 min, 1 h, 6 h and the horizon; in S-6 count reposts with `via` and the share whose `via` target is stored (F-07), posts whose quote target is not a post, `did:web` authorities, unknown embed types; in S-7 extend the delete-latency table to hours (this research only has a censored 17.8 minutes) and count account statuses including unknown ones; in S-9 count roots sharing a canonical URL; in S-10 re-read the pages listed above and the User Intents proposal status.
- **Selection functions** used by the analyzer (`derive`, `allowed`, canonicalisation, hash sampling) should be the same pure functions later moved into `ingest/selection.py`, so the measured yield is the shipped yield.
- **Time of day:** this research measured one Sunday 13:10 UTC window; schedule the two runs at different times (for example a weekday US evening and a weekday European morning, UTC) and report both, because the yield and the burst profile (766 events/s peak second here) vary.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1, pytest-cov 7.1.0, hypothesis 6.170.1, responses 0.26.3, Starlette `TestClient` (httpx 0.28.1); new test dependencies: none (the Postgres fixture is ours) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (adds marker `requires_db` and `--strict-markers`; `filterwarnings = error` stays - see F-09; `fail_under = 96` coverage only ratchets up) |
| Quick run command | `uv run pytest -x -q -m "not requires_db" tests/<file>.py` (no database needed) |
| Database loop | `uv run pytest -x -q -m requires_db tests/<file>.py` (provisions a throwaway cluster; as root in this container it runs `initdb`/`pg_ctl` as `postgres`) |
| Full suite command | `REQUIRE_DB=1 uv run pytest --cov --hypothesis-profile=ci` |
| Non-pytest gates | `uv run ruff check . && uv run ruff format --check .`; `uv run mypy`; `uv run python scripts/copy_guard.py`; `uv lock --check`; pip-audit pair; gitleaks scan (and the scratch scan over the fixture); CI: `alembic upgrade head`, `downgrade base`, `upgrade head`, `alembic check` against the Postgres 17 service |

### Phase Requirements -> Test Map

| Req / SC | Behavior | Test Type | Automated Command | File Exists? |
|----------|----------|-----------|-------------------|-------------|
| DATA-01 / SC1 | Decision document front matter parses and a plan task reads it first; fixture manifest has `source_mode: "recorded-real"`, counts and tool sha; fixture <= 1.5 MB and sha256 pinned; scrub invariants (all DIDs/rkeys match the sequential-counter grammar, no `cid`, no text, no URL query or fragment); scratch gitleaks clean; `ReplaySource` refuses a manifest that is not `recorded-real`; the synthetic fixture never reaches the events tables | unit + static | `uv run pytest -q tests/test_recorded_fixture.py` | Wave 0 |
| DATA-01 | Spike tool: caps enforced (`--max-seconds` > 7200 rejected), 403 stops without retry, outputs carry no DID/handle/text (marker test), analyzer pure functions on a tiny hand-built log | unit | `uv run pytest -q tests/test_spike_tool.py` | Wave 0 |
| DATA-02 / SC2 | Migration test: `upgrade head`, `check` clean, `downgrade base` leaves only `alembic_version`, `upgrade head` again; one head; CHECK constraints reject bad rows (`inferred` on non-repost, root with parent, text on non-root, self-parent); packaged head equals DB head; no f-string SQL (AST) | integration (real PG) | `uv run pytest -q -m requires_db tests/test_migrations.py` | Wave 0 |
| DATA-03 / SC3 | Normaliser table tests from one real frame per shape (reply, quote, quote-with-media, reply+quote, repost with and without `via`, delete, account statuses, sync, `#info`, `error`, oversize, malformed); non-post targets dropped; allowlist spoof table; `!no-unauthenticated` and adult exclusions; pseudonymiser determinism and domain separation | unit | `uv run pytest -q tests/test_ingest_normalise.py tests/test_pseudonym.py tests/test_selection.py` | Wave 0 |
| DATA-03 / SC3 | Replay the fixture twice: identical row counts per table and identical canonical projection by natural key; replay after a constructed delete does not resurrect; checkpoint written in the same transaction (kill before commit repeats the batch); crash-resume: CLI subprocess, small batch, per-batch delay, kill once a checkpoint row exists, rerun, compare with an uninterrupted run (pass `SYSTEMROOT`); golden row counts derived from the first verified run | integration | `REQUIRE_DB=1 uv run pytest -q -m requires_db tests/test_ingest_idempotency.py tests/test_ingest_crash_resume.py` | Wave 0 |
| DATA-03 | Loopback server: reconnect after 1011, refused cursor (400 `CursorTooOld`), first-frame `#info OutdatedCursor` records a gap, 403 fatal, backoff bounded with injected clock/sleep, 60 s silence, run bounds (`events`, `seconds`, `stored`, `capacity_reached`) | integration (loopback) | `uv run pytest -q tests/test_jetstream_source.py` | Wave 0 |
| DATA-04 / SC4 | Hypothesis order-independence and invariants over the pure resolver (200 examples, `ci` profile) with the three mutants asserted to fail the property; bounded DB permutation test (25 examples) plus idempotence; orphans stay `orphan`, flip to `resolved` when the parent arrives; `find_order_violations` non-raising | property + integration | `uv run pytest -q --hypothesis-profile=ci tests/test_enrich_properties.py; uv run pytest -q -m requires_db tests/test_enrich_db.py` | Wave 0 |
| DATA-05 / SC5 | `/v1` contract: list pagination walk (all pages, no duplicates), malformed cursor 422, `limit` bounds, tree cap with `truncated/shown/total`, timeline <= 500 buckets, stats from rollups, provenance `meta` (`synthetic` false, `source_status` stale when `data_as_of` is older than `INGEST_STALE_AFTER_SECONDS`), empty database -> `empty`; OpenAPI walk (every `/v1` operation declares exactly 422/429/500/503, problem+json only, no 502); golden updated deliberately; copy guard clean | integration | `uv run pytest -q -m requires_db tests/test_v1_cascades.py tests/test_v1_openapi.py` | Wave 0 |
| DATA-05 / FND-02 / SC5 | Outage injection (`ALLOW_CONNECTIONS false` + terminate) gives 503 problem+json with `Retry-After`, no URL/host/socket/DB name in body or `caplog`, `/ready` 503 naming only `database`; recovery returns 200; statement timeout -> `database_timeout`; closed-port engine -> 503; pool exhaustion -> 503; any other DB error -> generic 500 `internal_error`; no `DATABASE_URL` without `DEMO_MODE` -> startup exit code 3 | integration | `uv run pytest -q -m requires_db tests/test_v1_outage.py tests/test_readiness_database.py` | Wave 0 |
| DATA-06 / SC5 | Ledger arithmetic (daily budget, per-run cap, min refresh) with an injected clock; stop on 503 and 403, record 502 as a failed topic with non-zero exit; `max_results` sent as `max`; key only in the `X-Api-Key` header; topics file validation; `/v1/news` serves stored rows with `data_as_of` = last successful fetch | unit + integration | `uv run pytest -q tests/test_news_job.py; uv run pytest -q -m requires_db tests/test_v1_news.py` | Wave 0 |
| DATA-06 / SC5 | No request handler reaches the news client: AST import closure from `truthtrail.api` with a negative control; fresh-interpreter `sys.modules` test (`requests`, `urllib3`, `websockets`, `zstandard`, `truthtrail.services.gnews` absent after `create_app()`); route sweep with `fetch_news` patched to fail and `responses` rejecting GNews; app starts and every route answers with `GNEWS_API_KEY` unset | static + subprocess + integration | `uv run pytest -q tests/test_no_news_in_handlers.py tests/test_import_rules.py` | Wave 0 |
| D-31 security | No URL from a post is fetched (socket guard asserts no non-loopback connect during normalisation); parameterised SQL only; marker-value test: no DID, handle, text, URL or secret in logs, bodies or fixtures; `PSEUDONYM_SECRET` absent from the API process environment requirement | unit | `uv run pytest -q tests/test_no_pii_in_logs.py tests/test_sql_parameterised.py` | Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest -x -q -m "not requires_db" <touched files>` plus `uv run ruff check <files>`; database tasks add `-m requires_db <files>` (about 3 s of provisioning overhead).
- **Per wave merge:** `REQUIRE_DB=1 uv run pytest -q`, `uv run mypy`, `ruff check/format --check`, copy guard, `uv lock --check`.
- **Phase gate:** full suite with coverage and `--hypothesis-profile=ci`, the executed-database-test floor, pip-audit pair, gitleaks from the floor, the CI Alembic steps green on the pushed commit, then `/gsd-verify-work`.

### Wave 0 Gaps

- [ ] `tests/conftest.py`: `requires_db` marker, Postgres session fixtures (Pattern 11), engine tracking with disposal, `ENV_NAMES` additions (`PSEUDONYM_SECRET`, `COLLECTOR_CONTACT`, `TEST_DATABASE_URL`, `TRUTHTRAIL_PG_BIN`, `REQUIRE_DB`, the new settings), socket guard (loopback and unix sockets only)
- [ ] `tests/test_*` files named in the map above; `tests/golden/openapi_phase3.json` (declared-diff discipline, replacing `openapi_phase1.json` in the last plan)
- [ ] `src/truthtrail/data/recorded/*` (from the spike), `seed_domains.txt`, `news_topics.toml`
- [ ] `.env.example` and `EXPECTED_ENV_NAMES` extended; `tests/test_readme_env_table.py` updated; `.gitignore` gets `spike-output/`
- [ ] Framework install: `uv add "sqlalchemy==2.1.5" "psycopg[binary]==3.3.6" "alembic==1.20.0" "websockets==17.2"`

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The `winget` id `PostgreSQL.PostgreSQL.17`, its default port and `initdb -E UTF8 --locale=C` behaviour on Windows | Environment (owner commands), Pitfall 27 | Owner route 1 or 2 needs a tweak; route 3 (`-m "not requires_db"`) still works |
| A2 | psycopg-binary and zstandard wheels *run* on Windows (wheels exist for win_amd64 cp313; not executed) | Standard Stack | `uv sync` on Windows fails; fallback to the pure-Python psycopg needs libpq |
| A3 | The Docker Hub digests quoted for `postgres:17.11-bookworm` and `17.11` are current and are manifest-list digests (taken from the Hub tags API; the registry API returned HTTP 429) | Environment | The CI pull fails by digest; re-resolve at planning time |
| A4 | The Postgres service container syntax (health options, port mapping, `localhost` from a job running on the runner) works as documented, and the migrations behave identically on PostgreSQL 17 (they use no 17-only feature; 16.15 was tested) | Validation | First CI run needs a fix; local logic unaffected |
| A5 | GitHub-hosted runners can reach the public Jetstream hosts | Validation, F-05 | Phase 6 scheduling must change (self-hosted or different egress); noted as a Phase 6 verification item |
| A6 | The public Bluesky instances will not rate-limit or drop a long-lived, key-less consumer; no server-initiated close was seen in 17.8 minutes; `ConsumerTooSlow`'s floor rate is unpublished | Source Facts | Collector exits non-zero more often; bounds and cadence adapt |
| A7 | Account statuses `suspended` and `desynchronized` (named by CONTEXT) exist; this research saw `deleted`, `takendown`, `deactivated`, `throttled` and active | F-18 | None: the allow-list ignores unknown statuses |
| A8 | `org.user-intents.declaration` records may or may not exist on the network (a 25 s scan of a 35 h cursor found none, possibly incomplete); the proposal is a draft | Terms | If widely adopted, honouring intents becomes an ethical expectation; revisit at Phase 6 |
| A9 | Yield, child counts and delete latencies from one Sunday 17.8-minute window are indicative only; time of day and day of week will change them | Selection, Retention | OD-1/OD-3 ratified on thin data; the spike's two long runs exist to prevent this |
| A10 | The Bluesky Developer Guidelines apply to this read-only consumer; the GDPR reading (Recital 26, Article 89(1)) is general, not legal advice, and the owner is the controller | Terms | Missing a duty (report path, contact); small cost to add them |
| A11 | GNews counts every HTTP attempt, including retried 5xx, against the Free-plan daily quota; a public portfolio demo served from the Free plan stays within its "non-commercial" wording | Pattern 10, F-13 | Quota consumed faster; account suspension risk if the use is judged commercial |
| A12 | `app.bsky.feed.repost.via` means "the repost record through which the reposter saw the post"; inferred from the field name, the 24.2 percent populated rate and 3,347 of 3,347 same-subject matches, because the lexicon text for `via` was not reachable (the atproto lexicon paths returned 404 and the SDK models carry only the field) | F-07 | A wrong reading would mislabel a secondary relation; since it is stored as a secondary column and not drawn in v1 the cost is low |
| A13 | `time` may be overridden by an operator timestamp import on some instance; it never differed from `witnessedAt` in 100,000 public-instance frames | F-03 | None if `witnessedAt` is used with `time` as fallback |
| A14 | The Neon free-tier limits quoted in STACK.md (1 GB, autosuspend) are current | Privacy, Retention and Storage | Budget arithmetic only; Phase 6 re-verifies |
| A15 | `runuser` (util-linux) exists wherever the fixture runs as euid 0 | Pattern 11 | Fixture error; add `su -s /bin/sh postgres -c` fallback |

## Open Questions (RESOLVED)

> RESOLVED here means every question has a named disposition and no planning input is missing. An answer that only the owner or a later phase can supply is not claimed as answered: its `Disposition:` line names the plan task, phase or non-gating manual item that collects it (plans 03-01 to 03-12 and `03-VALIDATION.md` route each one).

1. **Which v2 host is primary and does failover work? (RESOLVED)**
   - Both v2 hosts stream through the proxy; seq spaces differ, `witnessedAt` offsets stay within about +/-2 s over 90 s; resume by microsecond timestamp with a 30 s rewind (F-03).
2. **Can the key-less live tail catch up after downtime? (RESOLVED)**
   - Yes, up to the 36 h floor, at 1,900-2,800 events/s; beyond it a timestamp cursor is clamped with an in-band `#info` (F-02). Whether a *scheduled* job can keep up is a cadence question (F-05; deferred to Phase 6, item 14).
3. **Does a dictionary have to be vendored for zstd? (RESOLVED)**
   - No: fetch by id over HTTP (immutable, identical on both hosts). Compression stays off (D-06); enable only for catch-up if bandwidth matters.
4. **psycopg 3 or asyncpg? (RESOLVED)** psycopg 3 sync (D-19); `pool` extra dropped (F-12).
5. **pytest-postgresql or a plain `TEST_DATABASE_URL`? (RESOLVED)** Both: the own fixture builds a throwaway cluster when no `TEST_DATABASE_URL` is set; `pytest-postgresql` fails as root here and adds dependencies.
6. **Can Postgres run as root here? (RESOLVED)** No; `runuser -u postgres --` with a traversable, `postgres`-owned directory, `-E UTF8 --locale=C` (F-10).
7. **How is Alembic proven in CI and in pytest? (RESOLVED)** CLI steps in CI; programmatic `command.upgrade/check/downgrade` with a shared connection in pytest (Pattern 8).
8. **What strategy proves arrival-order independence? (RESOLVED)** Pattern 7, with mutation evidence.
9. **Is the public AppView needed in the product? (RESOLVED)** No. It is useful only as a read-only completeness cross-check in the spike (S-13); its thread view is truncated and `searchPosts` is 403.
10. **Should repost `via` be stored? (RESOLVED for planning - owner confirmation at the spike checkpoint)**
    - What we know: 24.2 percent of reposts carry it; it is cheap now and a re-ingest later.
    - What's unclear: whether Phase 5 or v2 will draw observed reshare chains.
    - Recommendation: add nullable `via_uri` to the baseline migration; keep D-12's star semantics.
    - Disposition: owner decision at plan 03-01 Task 5 (checkpoint item 4, front matter key `schema_via_uri`); plan 03-03 adds the column iff the owner confirms; plan 03-01 Task 4 measures the `via` share (S-6).
11. **OD-3: tracked-root selection and bounds. (RESOLVED for planning - OWNER DECISION, stays an owner decision)** Facts in "Tracked-root selection policies" and F-06. Recommendation unchanged (A, PROVISIONAL), with a deterministic sampling parameter added to the policy object so the cap is a safety valve; ratify after S-5 and S-9 from the long runs. Disposition: owner decision at plan 03-01 Task 5; the plans take it as the TRACK_* policy parameters (plan 03-02), option B is built and tested in plans 03-04 and 03-05, option C is outside the plans.
12. **OD-1: retention. (RESOLVED for planning - OWNER DECISION, stays an owner decision)** Facts in "Storage by scenario" and the deletion measurements. Recommendation unchanged (RT-2, 14/90/7, PROVISIONAL) but the 90-day cascade window is only affordable together with a root cap or sampling and, ideally, early removal of dormant (zero-child) cascades; re-check with S-8's bytes per row. Disposition: owner decision at plan 03-01 Task 5; the plans take it as the RETENTION_* policy parameters (plan 03-02), enforced by the purge of plan 03-06.
13. **OD-2: merging. (RESOLVED for planning - OWNER DECISION, stays an owner decision)** Recommendation unchanged (M1, PROVISIONAL); situation (A) cannot occur under allowlist seeding; S-9 counts situation (B). Disposition: owner decision at plan 03-01 Task 5; the plans take it as CASCADE_MERGE_POLICY (plans 03-02, 03-03, 03-07); M2 is outside the plans.
14. **Scheduled-job cadence and bounds (RESOLVED for planning - deferred to Phase 6, stated in the spike document).** F-05 arithmetic. Disposition: plan 03-01 Task 4 writes the catch-up and cadence arithmetic into 03-SPIKE.md from measured events per hour; Phase 6 chooses the schedule; no Phase 3 plan builds a scheduler.
15. **GNews Free-plan wording vs a public portfolio demo (RESOLVED for planning - owner action before the Phase 6 deploy, non-gating).** The terms say non-commercial/personal/academic/evaluation use; a free public demo is plausibly within it, but the owner should read section 3 of the GNews terms before the public deploy. Disposition: plan 03-01 Task 4 step 8 re-quotes the terms with dates (S-10); the owner re-reads them before Phase 6 (non-gating row in 03-VALIDATION.md Manual-Only Verifications).
16. **Developer Guidelines duties for a read-only dashboard (RESOLVED for planning - adopted as Claude's discretion).** Add a public contact in the README and User-Agent, a documented report path and an operator hide/erase command (Claude's discretion; small). Disposition: COLLECTOR_CONTACT in the User-Agent (plan 03-02), the operator erase command (plan 03-05), the documented report path and limits (plan 03-10 Task 1); the public contact in the deployed README is Phase 6.
17. **Runner reachability and rate limiting of Jetstream from GitHub Actions (RESOLVED for planning - Phase 6 verification, non-gating).** Disposition: no Phase 3 plan depends on it (pytest never contacts Jetstream); it is a non-gating row in 03-VALIDATION.md Manual-Only Verifications and a Phase 6 deploy check.
18. **Windows run of the spike (RESOLVED for planning - owner action, non-gating).** Commands above; result pasted into the decision document. Disposition: requested at the plan 03-01 checkpoint (front matter `windows_result`, S-12); ratification does not wait for it.
19. **Docker digest for the service container (RESOLVED - planner re-resolved).** Values above are from the Hub tags API. Disposition: plan 03-03 Task 3 pins the digest it re-resolved at planning time (`postgres:17.11-bookworm`).
20. **Status of the User Intents proposal and any live declarations (RESOLVED for planning - watch item, non-gating).** Disposition: no Phase 3 behaviour depends on it; it is re-read together with the terms before the Phase 6 deploy (non-gating row in 03-VALIDATION.md Manual-Only Verifications).

## Sources

### Primary (HIGH confidence)
- Live probes against `jetstream.us-east|us-west.bsky.network`, `jetstream2.us-east`, `jetstream1.us-west.bsky.network` and `public.api.bsky.app`, 2026-10-18 (scripts and raw logs in `$SCRATCH`; 100,000-frame recording 13:10-13:28 UTC; dual-instance recording; cursor, rewind, kinds, parameter, zstd, size-limit and error probes).
- https://bsky.network/docs/jetstream/, /jetstream-replay/, /developer-guidelines/, /rate-limits/, /api-directory/ (read 2026-10-18); https://atproto.com/blog/jetstream (the old blog URLs redirect there).
- https://raw.githubusercontent.com/bluesky-social/jetstream/main/lexicons/network/bsky/jetstream/subscribeEvents.json and `getZstdDictionary.json` (authoritative wire contract); `.../main/docs/README.md` (RFD sections 5.1, 5.2, 7, 8); `.../jetstream/main/README.md`.
- https://bsky.social/about/support/tos (Last Updated 14 August 2025), `/privacy-policy`, `/community-guidelines`, `/network-services-privacy-policy` (Last Updated May 22, 2024); https://github.com/bluesky-social/proposals `0008-user-intents` (draft).
- https://docs.gnews.io/endpoints/search-endpoint, `/error-handling`; https://gnews.io/pricing; https://gnews.io/legal/terms-of-service (Last Updated October 16, 2026) - public pages only, no API call.
- `pip index`-equivalent PyPI JSON for every package named, 2026-10-18; `uv add` against a scratch copy of the repository's `pyproject.toml` and `uv.lock`; `pip-audit`; `mypy --strict`; the package-legitimacy seam.
- Executed prototypes in `$SCRATCH`: schema and Alembic (`proto/`), row sizes and query plans, writer SQL, error mapping and outage injection, `/v1` route under the repository's real `create_app()` (`v1proto/`), pure resolver and Hypothesis (`proto/test_resolve.py`), Postgres fixture (`fxt/`), loopback WebSocket server, edge derivation (`edges.py`), gitleaks token experiments (`glt/`).
- In-repo files read this session: `pyproject.toml:1-48`, `src/truthtrail/api/app.py:40-79`, `api/problems.py:44-91`, `api/limits.py:47-65`, `core/errors.py:45-66`, `core/readiness.py:22-29`, `services/gnews.py:26-43`, `schemas/models.py` (Meta, Problem), `core/config.py`, `core/boot.py`, `core/cascade.py`, `tests/conftest.py`, `tests/test_no_hardcoded_credentials.py:15-18`, `.github/workflows/ci.yml`, plus CONTEXT, HANDOFF, ROADMAP, REQUIREMENTS, STACK.md and the Phase 1 and Phase 2 research/security files.

### Secondary (MEDIUM confidence)
- https://docs.github.com/en/actions/using-containerized-services/creating-postgresql-service-containers (service container YAML, health options, port mapping; read via `curl`).
- https://hub.docker.com/v2/repositories/library/postgres/tags (tags and digests, 2026-10-18).
- https://gdpr-info.eu/recitals/no-26/ and /art-89-gdpr/ (GDPR text).
- atproto Python SDK 0.0.73 generated models (installed into a scratch directory) for the `app.bsky.feed.post` and `app.bsky.feed.repost` record fields (the lexicon JSON paths in the atproto repository returned 404 from `raw.githubusercontent.com`).

### Tertiary (LOW confidence)
- Legal and policy reading of the terms (A10); proposal 0008 status (A8); `via` semantics (A12); Windows behaviours (A1, A2); everything about Neon and Phase 6 runners.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - exact versions resolved into the real lock, audited, type-checked, exercised.
- Source protocol, cursors, shapes: HIGH - live probes plus the authoritative lexicon.
- Database design, error mapping, Alembic, fixtures: HIGH - executed against PostgreSQL 16 and the repository's own app factory; PostgreSQL 17 and Docker only via CI.
- Yield, volume mix, deletion timing, storage scenarios: MEDIUM - single short window; the spike measures them properly.
- Terms and privacy: LOW-MEDIUM - public text read and quoted; interpretation is not legal advice.
- Windows and Phase 6 items: LOW - not testable here.

**Research date:** 2026-10-18
**Valid until:** 2026-11-01 for Jetstream/AppView operational facts (v2 is new and the documentation and wire still disagree in places); the package versions until the next planning pass; re-read the Bluesky and GNews terms before the Phase 6 public deploy.

