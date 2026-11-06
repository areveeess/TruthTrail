---
phase: 03-real-propagation-data
plan: 07
subsystem: api
tags: [v1, read-api, keyset-pagination, cursor, tree, timeline, date_bin, stats, provenance, problem-json, outage, cache, openapi]
status: complete

requires:
  - phase: 03-real-propagation-data
    provides: "03-01 ratified 03-SPIKE.md (RT-2, M1 claim_group, A, via_uri true, d17-hmac-v1); 03-02 Policy (page sizes, MAX_TREE_NODES, MAX_TIMELINE_BUCKETS, INGEST_STALE_AFTER_SECONDS, CASCADE_MERGE_POLICY); 03-03 schema, engine factory, /ready database check; 03-04 order_events and find_order_violations; 03-05 writer, run_pipeline; 03-06 enrich rollups, purge"
provides:
  - "schemas/v1.py: V1Meta, ClaimSummary, CascadeSummary, CascadeDetail, EdgeKindCounts, CascadePage, CascadeResponse, TreeNode, TreeEdge, TreeRoot, TreeResponse, TimelineBucket, TimelineResponse, LastRun, EventKindTotals, StatsResponse, CAPTION"
  - "api/v1_deps.py: get_connection / read_connection (read-only, opened after the limiter), build_meta, source_status_for, data_version, datetime_from_us, us_from_datetime, utc_now"
  - "api/db_errors.py: register_db_error_handlers (503 database_unavailable / database_timeout, Retry-After 5), classify_operational_error"
  - "api/v1_cache.py: V1Cache (per app, success only, single flight, size bound), TTL constants"
  - "api/problems.py: V1_PROBLEM_RESPONSES (422, 429, 500, 503)"
  - "api/v1_cascades.py: register_cascades, encode_cursor, decode_cursor, choose_bucket_seconds, count_overlapping_gaps, canonical_tree_order"
  - "api/v1_stats.py: register_stats, ingest_lag_seconds"
  - "create_app(clock=...), app.state.policy, app.state.clock, app.state.v1_cache"
  - "tests/conftest.py: seeded_db_url (session), v1_client factory, V1_TEST_RATE_LIMIT"
affects: [03-08, 03-09, 03-10, 03-11, 03-12, phase-5, phase-6, ci]

estimate:
  tokens: 180000
  tasks: 3
actuals:
  tokens: 45232      # chars/4 over the added lines of 7f6cd30..efaea20
  tasks: 3
  commits: 3         # git rev-list --count 7f6cd30..HEAD before the docs commit
plan_head_before: 7f6cd304cb8f4ce7b43e268306b7c3255798f822
plan_head_after: efaea2061eec6de3392be0a297571e10b97f09b9

tech-stack:
  added: []
  patterns:
    - "Connection opened inside the handler body (read_connection), never as a FastAPI dependency: the limiter wraps the handler, so a rejected request never takes a pool connection"
    - "Cache payload without meta, keyed on (route, data_version, parameters); the meta is built per request because staleness depends on now"
    - "Opaque keyset cursor: base64url JSON [sort, value, id], validated by an AfterValidator (422 without echo), timestamp rebuilt from integer microseconds"
    - "Timeline buckets with date_bin(:stride, observed_at, :origin) and dense filling in Python; no date_trunc or extract"

key-files:
  created:
    - src/truthtrail/schemas/v1.py
    - src/truthtrail/api/db_errors.py
    - src/truthtrail/api/v1_deps.py
    - src/truthtrail/api/v1_cache.py
    - src/truthtrail/api/v1_cascades.py
    - src/truthtrail/api/v1_stats.py
    - tests/test_v1_meta_errors.py
    - tests/test_v1_outage.py
    - tests/test_v1_cache.py
    - tests/test_v1_cascades.py
    - tests/test_v1_tree_timeline.py
    - tests/test_v1_stats.py
    - tests/test_v1_openapi.py
  modified:
    - src/truthtrail/api/problems.py
    - src/truthtrail/api/app.py
    - src/truthtrail/api/v1.py
    - tests/conftest.py
    - tests/test_import_rules.py
    - tests/test_v1_limits.py
    - tests/test_openapi_golden.py
    - .github/workflows/ci.yml
    - tests/test_ci_workflow.py

key-decisions:
  - "Handlers open the read-only connection inside their body (read_connection), not through Depends: FastAPI resolves dependencies before slowapi's wrapper runs, so a dependency would check out a pool connection for a request the limiter then rejects (T-03-46). A test proves a 429 never takes a pool connection."
  - "Parameter validation (limit, cursor format, filters) happens before the limiter, as on the Phase 2 /analyze route, so a 422 costs no quota and no database work; checks made in the handler (claim_id under CASCADE_MERGE_POLICY none, a cursor of another sort) are counted. The plan's 'an invalid query is counted like a valid one' does not match FastAPI's order; the test asserts the real behaviour."
  - "Tree node ids are the events' surrogate ids, never the keyed uri, so the API exposes no identifier derived from an at:// URI. order_events still breaks ties on the keyed uri internally."
  - "ingest_gaps counts gap spans that overlap the tracked life [first_event_at, max(last_event_at, tracking_ends_at)], not only [first, last]: a gap after the last stored event can hide events that were never seen."
  - "events_by_kind.root in /v1/stats is the number of non-deleted roots (sum of event_count minus the child counts), not cascades_total, so the four kinds add up to events_total when a root was deleted."
  - "data_version = max checkpoint updated_at and cursor, latest run start, max rolled_up_at, cascade count, dirty count and deleted-root count, in one constant query. A purge of root text alone does not change it, so a cached detail can show purged text for at most its 10 s TTL."
  - "A cascade whose root row was hard-deleted by purge reports observed_since = first_event_at (the root's observed_at is gone)."
  - "CI REQUIRE_DB_FLOOR and MIN_DB_FLOOR raised 217 -> 311 (the collected requires_db count)."

requirements-completed: [DATA-05]

duration: 30 min
completed: 2026-11-06
---

# Phase 3 Plan 07: The /v1 read API Summary

**`/v1` now serves stored cascades from PostgreSQL: a keyset-paginated list, a detail view with every completeness count, a capped canonical tree, a dense date_bin timeline and rollup-only stats. Every success body carries a typed `V1Meta` (`synthetic` false, `data_as_of`, ok/empty/stale, live/replay, `observed_since`). Database failures use the frozen Phase 1 problem+json contract: 503 `database_unavailable` or `database_timeout` with Retry-After, and the generic 500 for anything else. This was proved by taking a real test database offline, and `/ready` reports only `database` while it is down.**

## Gate output

`.venv/bin/python scripts/check_spike_ratified.py --json` exited 0 before the first write: resolved_od1 RT-2, od2 M1 (`CASCADE_MERGE_POLICY claim_group`), od3 A, schema_via_uri true, pseudonym_scheme d17-hmac-v1. Nothing was written to 03-SPIKE.md. The root pin guard printed `root pin ok` before the first write and before every commit. No OD value is hard-coded in the code or the tests. The routes read `app.state.policy` and `get_policy()`, and the tests pass explicit environment overrides (`CASCADE_MERGE_POLICY`, `PAGE_SIZE_MAX`, `MAX_TREE_NODES`, `MAX_TIMELINE_BUCKETS`, `INGEST_STALE_AFTER_SECONDS`).

## Task commits

1. **Task 1, foundation and outage proof:** `652b277` feat(03-07): /v1 models and provenance, database error contract (503 database_unavailable/database_timeout), cache and app wiring; outage proof
2. **Task 2, cascades:** `99ed889` feat(03-07): /v1 cascades list (keyset pagination), detail, tree and timeline; golden /v1 allowance
3. **Task 3, stats and contract:** `efaea20` feat(03-07): /v1/stats from rollups; OpenAPI response-set walk; provenance on every route

## Routes and models

| Route | Response model | Notes |
|---|---|---|
| `GET /v1/cascades` | `CascadePage` (items: `CascadeSummary[]`, next_cursor, limit, sort, meta) | `limit` defaults to PAGE_SIZE_DEFAULT, max PAGE_SIZE_MAX; `sort` recent or velocity; filters `claim_id`, `min_events`, `has_orphans`, `include_deleted_roots` (default false) |
| `GET /v1/cascades/{cascade_id}` | `CascadeResponse` (cascade: `CascadeDetail`, meta) | adds `counts_by_kind` (root, reply, quote, repost, deleted), `invalid_count` (counted on demand), `ingest_gaps` |
| `GET /v1/cascades/{cascade_id}/tree` | `TreeResponse` | nodes, edges, roots (`TreeRoot{event_id, detached}`), shown, total, truncated, links_may_be_missing, enrich_pending; optional repeatable `kinds` (reply, quote, repost) |
| `GET /v1/cascades/{cascade_id}/timeline` | `TimelineResponse` | bucket_seconds, origin, dense `TimelineBucket{start, root, reply, quote, repost}` |
| `GET /v1/stats` | `StatsResponse` | cascades_total, cascades_with_deleted_root, events_by_kind, events_total, orphans/disconnected/deleted totals, observed_since, ingest_lag_seconds, ingest_gaps_total, last_run |

`CascadeSummary` holds cascade_id, observed_since, last_event_at, tracking_ends_at, event_count, reply_count, quote_count, repost_count, unique_accounts, max_depth, events_1h, orphan_count, disconnected_count, overflow_count, deleted_count, order_violation_count, root_deleted, claim, root_text, text_purged, enrich_pending and rolled_up_at. The `overflow_count` description says it is a lower bound ("at least ..."). Every model has `extra="forbid"` and a description on every field, and none has a `risk`, `risk_method` or `claim_scores` member. Each operation declares exactly 200, 422, 429, 500 and 503, and never 502, through `V1_PROBLEM_RESPONSES`, which is built with `_problem_declaration`. Retry-After is declared on 429 and 503. Every summary says "flag for human review", and every description starts with the caption "Observed subset of public Bluesky posts, as of the stated time."

## Cursor format

The cursor is the base64url form, without padding, of the compact JSON array `[sort, value, id]`. `sort` is `recent` or `velocity`. `value` is `last_event_at` in integer microseconds since the epoch for recent, or `events_1h` for velocity. `id` is the cascade id. An `AfterValidator` on the query parameter decodes the cursor and type-checks it: the alphabet, at most 200 characters, valid base64, UTF-8 JSON, a list of length 3, a known sort, integers that are not bools, a value from 0 up to the datetime maximum (or 2^31-1 for velocity), and an id from 1 to 2^63-1. A failed check raises `ValueError("malformed cursor")`, which renders as the existing 422 problem+json with `loc ["query","cursor"]` and never echoes the value. A cursor issued for another sort is also a 422 on `cursor`. The bound is rebuilt exactly as `EPOCH + timedelta(microseconds=value)`, with no float. The predicate is `(key, id) < (:bound, :id)` with bound parameters, ordered `key DESC, id DESC`, with `LIMIT limit + 1`. Walks for both sorts at limits 1, 7, 25 and 100 return each of the 148 visible fixture cascades exactly once, in the order SQL computes independently. A walk that runs while newer cascades are inserted between pages returns no duplicates and misses none of the original cascades.

## Status rule (D-24)

- `data_as_of` is the stream time (`cursor_time_us`) of the most recently updated `ingest_checkpoints` row. It is null when there is no checkpoint, and `source_status` is then `empty`.
- `stale` when the app clock minus `data_as_of` exceeds `INGEST_STALE_AFTER_SECONDS` (strictly greater), otherwise `ok`. An empty filtered result is `ok` when data exists.
- `source_mode` is `replay` when the most recent `ingest_runs` row (by started_at, then id) is a replay, otherwise `live`, including when no run exists.
- `observed_since`: the root's `observed_at` for the detail, tree and timeline routes, the earliest `first_event_at` for stats, and null for the list.
- The clock is `create_app(clock=...)`, which defaults to the UTC wall clock. A Bluesky outage can only appear as stale data, because the API never calls an upstream.

## Error contract and the 404 stance

- `OperationalError` with SQLSTATE 57014 (statement timeout) or 55P03 (lock timeout) gives 503 `database_timeout`. Any other `OperationalError`, and `sqlalchemy.exc.TimeoutError` (pool exhaustion, which is not a DBAPIError), give 503 `database_unavailable`. The body is `{type: about:blank, title, status 503, detail (fixed text), code, upstream: "database", synthetic: false, source_status: <code>, data_as_of: null}`, with the header `Retry-After: 5`. The log line is `<code>: <ExceptionClassName>` and nothing else.
- Every other database error (IntegrityError, ProgrammingError, a write on the read-only connection) reaches the catch-all middleware as the generic 500 `internal_error`. The body and the log contain no SQL, parameter, host or URL.
- An app without an engine (DEMO_MODE, or no database) answers every /v1 data route with the existing 500 `not_configured`, and the response contains no data.
- **An unknown cascade id returns the generic router 404** (problem+json, `code: http_error`, `source_status: error`, with the provenance members). It is deliberately not declared in OpenAPI, exactly like an unknown path. An id that is not a positive bigint is a 422 on `["path","cascade_id"]`.

## Outage evidence (tests/test_v1_outage.py, real PostgreSQL 16 in this container)

- `ALTER DATABASE <isolated> ALLOW_CONNECTIONS false` plus `pg_terminate_backend` makes a probe route return 503 problem+json `database_unavailable` with a positive integer Retry-After. The same holds for `/v1/cascades`, `/v1/cascades/1` and `/v1/cascades/1/tree` on the real routes. `/ready` returns 503 "Not ready: database." After `ALLOW_CONNECTIONS true` the next request is a 200 again (pre-ping reconnect), and `/ready` is 200 with `{"database": "ok"}`. The engine URL carries a marker password, which trust authentication ignores. The marker, the socket directory, the database name, the port and the words postgresql and psycopg appear in neither the bodies nor caplog. The only log line is `database_unavailable: OperationalError`.
- An engine on `127.0.0.1:1` (closed port) gives the same 503, and `/ready` is not ready.
- A 300 ms statement timeout with `pg_sleep(2)` gives 503 `database_timeout` in under 2 s.
- Pool exhaustion (pool 1, overflow 0, a connection held by the test) gives 503 `database_unavailable` after about the 2 s pool timeout. A concurrent request behind a slow one gets 503, never 500.
- A CHECK violation gives the generic 500, and a write on the read-only connection gives the generic 500 and leaves no row.

## Edits to existing tests (both in the Task 2 commit, the first that registers a /v1 route)

1. `tests/test_v1_limits.py::test_no_registrars_means_no_v1_path_in_openapi` now passes `app_kwargs={"v1_registrars": []}`. No other line changed.
2. `tests/test_openapi_golden.py::test_only_declared_additions_exist` now accepts a new path that is in `ALLOWED_NEW_PATHS` or starts with `ALLOWED_NEW_PREFIX = "/v1/"`. The module docstring names the addition. `test_phase1_contract_is_preserved` passed unchanged, because `phase1_view` already drops new paths and schemas. The golden file and its sha256 pin are untouched. **The Phase 2 OpenAPI golden snapshot did not change.**

Other existing files changed: `tests/test_import_rules.py` (the planned api rules), `tests/conftest.py` (additive fixtures, plus `seeded_db_url` in `DB_FIXTURES`), and, on orchestrator instruction, `.github/workflows/ci.yml` and `tests/test_ci_workflow.py` (the floor).

## Import rules added (D-31)

- "api never imports jobs, enrich or websockets": no exemption.
- "api never reaches the news client" (`truthtrail.services.gnews`, `requests`): ONE named exemption, `API_NEWS_EXEMPT = ("truthtrail.api.analyze",)`. Plan 03-11 retires that module and plan 03-12 empties the tuple. `test_the_api_news_exemption_cannot_grow` pins the set, and `test_the_exemption_is_only_for_the_news_rule` proves that the exempt module still follows every other rule. Six new negative controls cover the walker.

## Verification results

- Task 1: the meta, outage and cache files have 62 tests (41 + 7 + 14; the plan asks for at least 30), and they pass together with `test_import_rules` under `REQUIRE_DB=1`. The golden, contract, app-factory, health and CORS tests pass unchanged. The full `REQUIRE_DB=1` suite had 1634 passed and 10 xfailed.
- Task 2: `test_v1_cascades.py` and `test_v1_tree_timeline.py` have 76 tests (at least 40 required), all passing with 0 skipped, together with the limits, golden and contract tests (98 passed). The SQL-parameterised and import-rule tests pass. The full `REQUIRE_DB=1 --hypothesis-profile=ci` suite had 1711 passed and 10 xfailed.
- Task 3: `test_v1_stats.py` and `test_v1_openapi.py` have 19 tests (at least 18 required), and they pass with the golden test (23 passed).
- `REQUIRE_DB=1 REQUIRE_DB_FLOOR=311 pytest --cov --hypothesis-profile=ci` gave **1730 passed, 10 xfailed, 0 XPASS, coverage 97.65 %** against the 96 gate. v1_cascades is at 99.65 %, v1_cache at 98.59 %, and v1_deps, v1_stats, db_errors and schemas/v1 are fully covered.
- `uv run pytest -q`: **1730 passed, 10 xfailed, 0 XPASS**, up from 1564 at the end of plan 03-06. `REQUIRE_DB=1 REQUIRE_DB_FLOOR=311 uv run pytest -m requires_db`: **311 passed**, exit 0.
- ruff check, ruff format --check and strict mypy (56 files) are clean. `scripts/copy_guard.py` is clean over 678 OpenAPI strings. The CI pip-audit pair (`uv export --locked --no-emit-project --all-groups` plus `pip-audit --require-hashes --disable-pip`) reported "No known vulnerabilities found". The gitleaks range scan `a5dd825..efaea20` plus the working tree is clean.
- Before each of the three commits, the staged diff had 0 lines with a 32-hex string and 0 lines with the old key (derived in a script from `git show 9b5b085:gnews_fetcher.py`, counts only). `test_no_hardcoded_credentials.py` passed (13), and `gitleaks git --pre-commit --staged` exited 0.
- No test opens a network connection or calls GNews. Test HMAC keys are generated at runtime (`FAKE_PSEUDONYM_SECRET`). The recording carries no post text, so the purge test puts a constructed sentence on a constructed root. No real handle or post content is printed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Correctness/DoS] Connection opened after the limiter, not as a dependency (T-03-46)**
- **Found during:** Task 1 design.
- **Issue:** The plan describes `get_connection(request)` as a sync dependency. FastAPI resolves dependencies before slowapi's wrapper checks the limit, so every rate-limited request would still check out a pool connection (and run a pre-ping), which is what the limit is meant to prevent.
- **Fix:** `get_connection` stays a generator with the planned behaviour. Handlers use it as `read_connection(request)` (a contextmanager) inside their body, so the limiter runs first. `test_the_limit_applies_before_any_database_work` counts pool checkouts and finds none for 429s.
- **Commit:** 652b277 (the helper), 99ed889 (the routes), efaea20 (the test).

**2. [Rule 2 - Honesty] Gap overlap uses the tracked life, not just [first, last]**
- **Issue:** A gap between the last stored event and the end of tracking can hide events that were never seen. Counting only [first_event_at, last_event_at] would under-report it.
- **Fix:** The window is [first_event_at, max(last_event_at, tracking_ends_at)]. The test has gaps before, at the start, inside, after the last event within tracking (all counted except the first) and after tracking (not counted).
- **Commit:** 99ed889

**3. [Rule 1 - Consistency] events_by_kind.root is the number of non-deleted roots**
- **Issue:** The plan says "root equals the number of cascades". With a deleted root, which the fixture has, the four kinds would then not add up to `events_total`.
- **Fix:** root = sum(event_count - reply_count - quote_count - repost_count). The test compares every kind with a recount from `events`.
- **Commit:** efaea20

### Other deviations

- **Rate limit and invalid queries.** The plan asks that "an invalid query is not counted differently from a valid one". FastAPI validates parameters before the limiter wrapper runs, so a 422 from parameter validation does not consume quota, and the Phase 2 `/analyze` test asserts the same. The test documents the real order: a parameter 422 is uncounted and touches no database, while a 422 raised inside the handler (claim_id under merge policy none) is counted. Changing that order would need a middleware-level limiter, which is a Phase 2 architecture decision (D-23).
- **Tree node identity.** `event_id` is the surrogate `events.id`, so no keyed at:// URI is exposed. Roots are `TreeRoot{event_id, detached}` objects, and edges are `{parent_id, child_id, edge_kind, inferred}`.
- **Order-violation guard.** `links_may_be_missing` is computed from `find_order_violations` over the loaded rows, not from the rollup column, so it is correct even before enrich catches up. A parent cycle written outside enrich makes every node detached, never an error.
- **Timeline origin.** The origin is the earliest non-deleted `observed_at`, which equals `first_event_at` after enrich. It is still correct while a cascade waits for enrich.
- **The plan's conftest edit in Task 1** was not needed. The conftest additions (`seeded_db_url`, `v1_client`) came in Task 2 as the plan describes.
- **CI floor (orchestrator instruction):** `REQUIRE_DB_FLOOR` and `MIN_DB_FLOOR` went from 217 to 311. Both files are outside files_modified.
- **Commit trailer:** following the orchestrator and HANDOFF, the trailer is `Co-Authored-By: Claude Opus 5.5` instead of the plan's Sonnet line.

## Known Stubs

None. Every field is read from stored data. `claim.published_at` and `claim.source_name` are null for social_link claims because the collector does not store them; this is documented as "if known".

## Threat Flags

None beyond the plan's register. T-03-45 to T-03-52 are mitigated and tested: fixed bodies and class-only logs, bounds from the Policy, a validated cursor bound as parameters, 8-character pseudonym prefixes and no account on tombstones, provenance plus completeness counts, `Literal[False]` synthetic, a version-keyed success-only cache, and GET-only read-only connections behind the LimitedRouter.

## User Setup Required

None.

## Next Phase Readiness

- Plan 03-08 adds `/v1/news` with the same `V1_PROBLEM_RESPONSES`, `read_connection`, `build_meta` and `V1Cache` pattern, and extends `EXPECTED_PATHS` in `tests/test_v1_openapi.py`.
- Plan 03-12 empties `API_NEWS_EXEMPT` and proves the key-unset app. The `v1_client` factory keeps the fake news key and sets no DATABASE_URL, so these tests stay valid after the settings split.
- Phase 5 can generate its client from the declared models. The 404 is intentionally undeclared.

## Self-Check: PASSED

- All 13 created files and the 9 modified files exist.
- Commits 652b277, 99ed889 and efaea20 are ancestors of HEAD.
- `git rev-list --count 7f6cd30..efaea20` = 3.
