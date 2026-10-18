# Phase 3: Real Propagation Data - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-18
**Phase:** 03-real-propagation-data
**Areas discussed:** Spike gate and fixture; Jetstream instance and protocol generation; Collections, kinds and compression; Reconnect, cursor rewind and checkpointing; Collector run model; Edge semantics; Orphan handling; Idempotency; Deletes; Account pseudonymisation; Data minimisation; Postgres access layer; Schema and derived state; Enrich (SQL vs Python) and determinism; `/v1` API shape; Provenance and outage behaviour; News context job; Fate of legacy `/analyze`; Testing against real Postgres; Windows ergonomics; Free-tier resource bounds; OWNER DECISIONS (retention, cascade merging, tracked-root selection)

**How this discussion was run:** The owner was not available to answer questions and had delegated decisions. For every gray area the recommended option was taken by Claude and is marked with a check mark below, with "User's choice" stating that. The three areas the owner reserved (retention, cascade merging, tracked-root selection) were not decided: their tables mark the recommendation but select nothing, and CONTEXT.md carries them as OD-1, OD-2 and OD-3 with the facts and the spike measurements that settle them. Environment facts were verified on 2026-10-18 from the container (Bluesky egress works through the proxy; Jetstream and developer-guideline documentation read the same day; PostgreSQL 16 server binaries present, Postgres must run as a non-root user).

---

## Spike gate and the real-data fixture

| Option | Description | Selected |
|--------|-------------|----------|
| Spike as plan 03-01 with a hard owner gate | Bounded read-only tool, real run in the container, decision document, scrubbed real fixture; no schema or collector work until the owner ratifies | ✓ |
| Spike as a research note, plans proceed in parallel | Faster, but the schema (highest cost to change) would be built on assumed numbers | |
| Skip the spike, use the 8-second probe | The probe is a sanity check; it measures no yield, lookback, deletes or storage | |

**User's choice:** Recommended option taken by Claude (owner unavailable).
**Notes:** Fixture choices considered: hand-written synthetic fixture (rejected: the task and DATA-01 require a recorded real-data fixture, and invented data would be fabricated); raw committed posts (rejected: privacy and terms exposure, Pitfall 11); scrubbed real frames (chosen: structure and times kept, identities and text removed, deterministic from a transient raw log that is deleted). Location inside the package so the Phase 6 image can seed by replay.

## Jetstream instance(s) and protocol generation

| Option | Description | Selected |
|--------|-------------|----------|
| v2 us-east primary, us-west failover, dialect isolated, v1 only on spike evidence | Docs say v2 is recommended for new projects and v1 is legacy; the only stream verified from the container so far is a v1 host, so the spike must confirm v2 first | ✓ |
| v1 `jetstream2.us-east` only | Verified from the container today, but frozen legacy protocol with legacy timestamps, no `kinds` filter, may be retired | |
| Both dialects supported at runtime | Maximum resilience, double the parsing and test surface for a solo part-time project | |

**User's choice:** Recommended option taken by Claude (owner unavailable).
**Notes:** Community-run instances and a self-hosted Jetstream were rejected (unvetted operators; self-hosting archives the whole network). Cross-instance failover resumes by microsecond-timestamp cursor because per-instance sequence numbers are not assumed comparable.

## Collections, kinds and compression

| Option | Description | Selected |
|--------|-------------|----------|
| Posts and reposts only; commit, account and sync kinds; no compression | Smallest stream that carries cascade edges and the events needed to honour account deletion; compression deferred until bytes/s is measured | ✓ |
| Add likes | Roughly an order of magnitude more events and no cascade edge | |
| Enable Jetstream zstd with its dictionary | About 65% less bandwidth per the SDK docs, but adds a vendored dictionary artifact for a stream that measured about 77 events/s | |

**User's choice:** Recommended option taken by Claude (owner unavailable).
**Notes:** The `sync` kind is included because the documentation says a sync divergence marker removes all of an account's records; its rate is measured (S-7) because the rule is conservative and could over-delete.

## Reconnect, cursor rewind and checkpointing

| Option | Description | Selected |
|--------|-------------|----------|
| Time-based cursor with a 30 s rewind, checkpoint in the same transaction as the batch, explicit gap records | Idempotent writes make the rewind free; the timestamp cursor works across hosts; gaps are recorded, never hidden | ✓ |
| Per-instance `seq` cursor, no rewind | Simple, but not portable across hosts and exposes lost events if time and arrival order differ | |
| Checkpoint every N seconds in a separate write | Cheaper, but a crash can lose or duplicate work and violates checkpoint-after-commit | |

**User's choice:** Recommended option taken by Claude (owner unavailable).
**Notes:** Backoff: exponential with full jitter, 1 s to 60 s, give up after 8 consecutive failures. HTTP 403 on upgrade is fatal and reported, never retried or worked around. A too-old cursor yields an HTTP 400 with the new floor, which becomes a recorded gap.

## Collector run model

| Option | Description | Selected |
|--------|-------------|----------|
| Bounded batch job with time, volume and capacity bounds; collect then enrich then purge; scheduling in Phase 6 | Fits free hosting (Render sleeps, free Render Postgres expires); the 36-hour lookback lets a scheduled run catch up | ✓ |
| Always-on worker service | Best completeness, but no free host for it and it couples lifecycle and cost to the demo | |
| Ingest inside the API process (background task) | Rejected by the architecture research: duplicate consumers, hidden crashes, untestable API | |

**User's choice:** Recommended option taken by Claude (owner unavailable).
**Notes:** If the spike shows catch-up from a cursor is unavailable without a key, the design degrades to sampling windows and the decision document must say that completeness changes.

## Edge semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Reply and quote are observed edges with `parent_uri`; repost attached to its subject and the cascade root, `inferred`, never a reshare tree | Matches what the protocol states: reposts carry no parent chain | ✓ |
| Draw reposts as chains by inferring "who reposted from whom" | Fabricates structure the data does not contain | |
| Drop reposts entirely | Honest but loses the amplification signal the cascade is about | |

**User's choice:** Recommended option taken by Claude (owner unavailable).
**Notes:** A post that is both reply and quote is a reply; the quote target goes to a secondary `quoted_uri`, never a second edge (single-parent forest). Reposts have no depth and no chain; the database enforces the edge-kind invariants.

## Orphan handling

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit stored `parent_state`; parents never invented; detached subtrees in the API | Orphans are countable, filterable and honest | ✓ |
| Attach orphans to the root to complete the tree | Fake completeness | |
| Hold children in a pending buffer until the parent arrives | More complete, but extra state; deferred unless the spike shows inversions above 1% | |

**User's choice:** Recommended option taken by Claude (owner unavailable).
**Notes:** A child that arrives before its root is dropped and counted in v1.

## Idempotency

| Option | Description | Selected |
|--------|-------------|----------|
| Unique key on the pseudonymous `at://` URI, `ON CONFLICT DO NOTHING`, observations immutable | Replay-safe, tombstones cannot be resurrected | ✓ |
| Upsert that updates changed fields | Lets a later redelivery overwrite a tombstone or edit an observation | |
| Natural composite key (author, collection, rkey) in clear | Needs the raw DID, defeating pseudonymisation | |

**User's choice:** Recommended option taken by Claude (owner unavailable).

## Deletes

| Option | Description | Selected |
|--------|-------------|----------|
| One rule: tombstone (remove content and author link, keep skeleton), purge later; account deletion, takedown and sync apply it account-wide | Keeps cascades connected, honours deletes, no resurrection | ✓ |
| Hard-delete rows immediately | Orphans every child at once and loses rollup integrity | |
| Ignore deletes in v1 | Violates the Developer Guidelines and the project's honesty rule | |

**User's choice:** Recommended option taken by Claude (owner unavailable).
**Notes:** Deactivated, suspended and desynchronized accounts are not treated as deletions. Delete lookups cover all stored events, not only active cascades.

## Account pseudonymisation

| Option | Description | Selected |
|--------|-------------|----------|
| Keyed hash (HMAC-SHA256, server-side secret) for accounts and for every stored URI; no DID, handle or clear rkey stored | `at://` URIs contain the DID, so hashing only the account row would not pseudonymise; the keyed form keeps equality joins and resists a dictionary over the enumerable DID space | ✓ |
| Hash only the account table, keep raw `at://` URIs | URIs re-expose the DID; pseudonymisation would be cosmetic | |
| Raw DIDs stored, pseudonymise at the API only | Simplest and allows a deep link, but the database becomes an index of who engaged with what; one leak undoes it | |
| Plain or fixed-salt hash | Reversible by hashing all public DIDs | |
| Random per-row salt | Breaks equality joins needed for unique-account counts and delete matching | |

**User's choice:** Recommended option taken by Claude (owner unavailable).
**Notes:** Stated limits: pseudonymised, not anonymised; secret is long-lived and rotation is a rebuild (one-way); only ingest and erase processes hold the secret, the API does not. Token format avoids 32-hex lookalikes so the repo key-material scan cannot misfire.

## Data minimisation (what is stored)

| Option | Description | Selected |
|--------|-------------|----------|
| Text only on root events, nothing on replies, quotes or reposts; link-card title and canonical URL on the claim | No v1 feature needs reply text; smallest privacy footprint that still supports scoring | ✓ |
| Store text for every event | Enables later stance work but multiplies exposure and storage | |
| Store no text anywhere | Strongest privacy; this is OD-1 option RT-1, left to the owner | |

**User's choice:** Recommended option taken by Claude for the structural rule (text only on roots); how long root text lives is OD-1.

## Postgres access layer

| Option | Description | Selected |
|--------|-------------|----------|
| SQLAlchemy 2.x + psycopg 3 + Alembic, all synchronous, async only at the socket edge | Matches the sync Phase 2 service; STACK.md names it as the allowed alternative; no async test plugin | ✓ |
| Async SQLAlchemy 2.1 + psycopg 3 | Researched default; one async stack, but mixes poorly with sync handlers, readiness callables and slowapi | |
| psycopg only, hand-written SQL and migrations | Fewer layers, but no model/migration consistency check and weaker reviewer signal | |

**User's choice:** Recommended option taken by Claude (owner unavailable).
**Notes:** ORM models as the schema's source of truth with `alembic check`; Core statements for hot paths; migrations inside the package.

## Schema and derived state

| Option | Description | Selected |
|--------|-------------|----------|
| Accounts, claims, cascades, events plus checkpoints, runs, news queries and ledger; derived columns recomputed by enrich | Matches DATA-02 and the architecture sketch; few indexes for the size budget | ✓ |
| Store the tree as a JSON blob per cascade | Cannot ingest incrementally, dedupe or resolve orphans | |
| Add scoring, features and simulation tables now | Pre-builds Phase 4 and v2 and risks contradicting them | |

**User's choice:** Recommended option taken by Claude (owner unavailable).

## Enrich: SQL vs Python, and determinism

| Option | Description | Selected |
|--------|-------------|----------|
| Pure Python resolver per dirty cascade, SQL only to select work and write back; natural-key canonical projection | Reuses the Phase 2 pure functions, property-testable without a database, explicit tie-breaks | ✓ |
| Set-based SQL (`UPDATE ... FROM`, recursive CTE) | Efficient, but a second implementation of the invariants and harder to property-test | |
| Incremental maintenance by triggers | Order-dependent and hard to prove deterministic | |

**User's choice:** Recommended option taken by Claude (owner unavailable).
**Notes:** Equality is checked by natural key (URI), never by surrogate `id`, because ids depend on insertion order; time-dependent values take an explicit `as_of`.

## `/v1` read API shape

| Option | Description | Selected |
|--------|-------------|----------|
| List, detail, tree, timeline, stats and news; keyset pagination; tree capped at 5,000 nodes with `truncated`/`shown`/`total`; typed models | Covers DATA-05 and the Phase 5 needs; bounded responses | ✓ |
| Offset pagination | Unstable under inserts and unbounded scans | |
| One large cascade document endpoint | Unbounded payloads for viral cascades | |

**User's choice:** Recommended option taken by Claude (owner unavailable).
**Notes:** Sorts are `recent` and `velocity`; risk x velocity is Phase 5 after Phase 4 supplies risk.

## Provenance and outage behaviour

| Option | Description | Selected |
|--------|-------------|----------|
| `/v1` meta with `synthetic: false`, `data_as_of` = last checkpoint stream time, `source_status` ok/empty/stale, `source_mode` live/replay; database outage = 503 + Retry-After; readiness compares schema head | Reuses the frozen contract; a Bluesky outage shows as stale data, not an API error | ✓ |
| Map a Bluesky outage to 502/503 on the API | The API never calls Bluesky, so this would be invented | |
| Map every database error to 503 | Hides our own bugs as outages; only connection and timeout errors are outages | |

**User's choice:** Recommended option taken by Claude (owner unavailable).

## News context job (DATA-06)

| Option | Description | Selected |
|--------|-------------|----------|
| CLI job over a committed bounded topic set, quota ledger in the database, stored as claims, served by `/v1/news`; proof by import graph, route sweep and key-less startup | The in-memory budget of Phase 2 cannot bound a batch job; three independent proofs that no handler reaches the news API | ✓ |
| Keep per-request GNews calls behind the cache | Violates DATA-06 | |
| Refresh inside the API on a timer | Couples jobs to the web process, which the project avoids | |

**User's choice:** Recommended option taken by Claude (owner unavailable).
**Notes:** Default budget 60 calls a day, under the plan's reported 100. The first live run needs the owner's key and machine.

## Fate of legacy `/analyze`

| Option | Description | Selected |
|--------|-------------|----------|
| Retire, last in the phase, after `/v1/news` exists | Clean contract, no user-controlled path to the news API, no keyword label in the public API | ✓ |
| Reduce to stored topics at the same path | Preserves some tests, but two overlapping surfaces and a closed set that looks like a search box | |
| Keep behind a flag | Retains a user-controlled upstream path; contradicts DATA-06 | |

**User's choice:** Recommended option taken by Claude (owner unavailable).
**Notes:** `legacy/`, the synthetic fixture, its generator and the 10 strict-xfail tests stay. `DEMO_MODE` keeps its name and fail-closed guarantee but only means "start without a database"; rename or removal is Phase 6. Tests are retired with a written replacement map.

## Testing against real Postgres

| Option | Description | Selected |
|--------|-------------|----------|
| Marker plus fail-loudly by default; `TEST_DATABASE_URL` or a throwaway local cluster; CI service container; `REQUIRE_DB=1` and a floor on executed DB tests | A green run always means the database tests ran; never touches `DATABASE_URL` | ✓ |
| Deselect database tests by default | A green local run could hide untested database paths | |
| Mock the database layer | Cannot prove constraints, upserts, transactions, timeouts or migrations | |
| Testcontainers | Docker is not available in the container or necessarily on the owner's machine | |

**User's choice:** Recommended option taken by Claude (owner unavailable).
**Notes:** As root the container fixture runs initdb and pg_ctl as the existing `postgres` user; tests create and drop their own `truthtrail_test_<random>` database.

## Windows ergonomics

| Option | Description | Selected |
|--------|-------------|----------|
| Pure `uv` workflow, Python helper scripts, no POSIX-only calls, three documented routes for database tests | Matches how the owner runs the project | ✓ |
| Require WSL or Docker Desktop | Extra setup for a solo owner | |
| CI-only database tests | Owner cannot reproduce failures locally | |

**User's choice:** Recommended option taken by Claude (owner unavailable).

## Free-tier resource bounds (about 0.5 GB)

| Option | Description | Selected |
|--------|-------------|----------|
| 300 MB data budget, 300,000 events, 5,000 per cascade, 500 active roots, stop at 80%, few indexes, text on roots only | Conservative against the smaller of the two quoted free-tier sizes | ✓ |
| Use the 1 GB figure from STACK.md | Optimistic; the smaller figure was given for this task | |
| No explicit bounds, rely on retention | A viral cascade could fill the database between purges | |

**User's choice:** Recommended option taken by Claude (owner unavailable).
**Notes:** All numbers are PROVISIONAL and recomputed from the spike's bytes-per-row (S-8).

---

## OWNER DECISION OD-1: Retention policy

| Option | Description | Selected |
|--------|-------------|----------|
| RT-1 Minimal | No post text stored; claim text is the link-card title; structure 30 days | |
| RT-2 Short-TTL text | Root text 14 days, link title and structure 90 days, tombstones 7 days; no text on non-roots | recommended (not selected) |
| RT-3 Demo lifetime | Root text for the life of the cascade | |

**User's choice:** Not decided. OWNER DECISION, ratified after the spike.
**Notes:** Settled by S-5 (roots per day, share with commentary), S-8 (bytes per root, runway), S-7 (time-to-delete) and S-10 (terms). Plans read `RETENTION_*` parameters with PROVISIONAL defaults.

## OWNER DECISION OD-2: How provisional and duplicate cascades merge

| Option | Description | Selected |
|--------|-------------|----------|
| M0 Never merge | Cascade identity fixed at root creation; relations shown | |
| M1 Never merge, group by claim | M0 plus a claim key to filter and summarise cascades sharing an article URL | recommended (not selected) |
| M2 Derived full merge | Enrich absorbs overlapping cascades; ids redirect | |

**User's choice:** Not decided. OWNER DECISION, ratified after the spike.
**Notes:** Conditional on OD-3: under allowlist seeding re-rooting cannot occur by construction, so only claim-level duplicates exist. Settled by S-9 together with the OD-3 choice. Plans read `CASCADE_MERGE_POLICY`.

## OWNER DECISION OD-3: Tracked-root selection policy and bounds

| Option | Description | Selected |
|--------|-------------|----------|
| A Allowlist seed | Top-level link post on a curated news and fact-check domain list, English, no adult self-label | recommended (not selected) |
| B Claim-URL match | Also seed when the URL equals a stored news headline URL (additive) | |
| C Engagement promotion | Promote any post crossing a reply/quote/repost threshold; needs a bounded buffer of untracked references | |
| D Authenticated search seed | Seed from `searchPosts` with an app password | |

**User's choice:** Not decided. OWNER DECISION, ratified after the spike.
**Notes:** D is recommended against for v1 (credential, load-shed endpoint, backfill breaks stream-time semantics). Bounds (500 active roots, 48 h tracking, 5,000 events per cascade, 300,000 total) are provisional and settled by S-5 and S-8. The allowlist is an editorial selection bias to be disclosed.

---

## Claude's Discretion

Module and file names inside the new packages, migration naming, token-alphabet details within the stated lengths, the keyset cursor encoding, the exact allowlist entries (owner reviews them at the spike checkpoint), error-code strings beyond those named, the socket guard implementation, the counters shape in `ingest_runs`, the optional operator erase command, and plan slicing.

## Deferred Ideas

Engagement-promotion and authenticated-search seeding; derived cascade merging; Jetstream Replay or Snapshot history and Mastodon; linking news headlines to cascades beyond the optional seed and claim clustering; risk x velocity ranking (Phase 5); a "view on Bluesky" link; a pending buffer for children before roots; Jetstream compression; scheduling, health checks and the 60-day workflow-inactivity risk (Phase 6); renaming or removing `DEMO_MODE`, the root `main.py` shim and the synthetic fixture (Phase 6); the operator erase command; structured logging, metrics, API-key auth and a load test (v2); re-reading the Bluesky terms before the public URL (Phase 6).
