---
phase: 03-real-propagation-data
plan: 03
subsystem: database
tags: [postgres, sqlalchemy, alembic, readiness, ci, schema, migrations]

requires:
  - phase: 03-real-propagation-data
    provides: "03-01 ratified 03-SPIKE.md (RT-2, M1, A, via_uri true, d17-hmac-v1) and the gate; 03-02 pins, create_db_engine, normalise_database_url, the real-PostgreSQL fixtures and REQUIRE_DB_FLOOR"
provides:
  - "src/truthtrail/db/models.py: the D-20 schema as declarative models with a naming convention and the D-12/D-14/D-16/D-18 invariants as named CHECK constraints"
  - "Packaged Alembic migrations (src/truthtrail/db/migrations, baseline revision 0001) with a root alembic.ini that carries no URL"
  - "truthtrail.db.migration_config(), truthtrail.db.packaged_head(), python -m truthtrail.db {migrate,check,heads}"
  - "truthtrail.db.health.database_ready() and the `database` readiness check on /ready"
  - "create_app(engine=...), register_default_checks(registry, get_engine), a lifespan-owned api engine"
  - "conftest fixtures migrated_db_url, clean_db and helper upgrade_to_head"
  - "CI: PostgreSQL 17 service, REQUIRE_DB=1, REQUIRE_DB_FLOOR=65, the Alembic CLI round trip, the image migration check"
affects: [03-04, 03-05, 03-06, 03-07, 03-08, 03-09, 03-11, 03-12, ci, docker]

actuals:
  tokens: 28111      # chars/4 over the added lines of 8f9bb12..5afa686
  tasks: 3
  commits: 4         # git rev-list --count 8f9bb12..HEAD before the docs commit
plan_head_before: 8f9bb12bb7e1bd98892e81d202466f7cda5804ac
plan_head_after: 5afa686f10a32939b258ab7fb191a3002210ed18

tech-stack:
  added: []
  patterns:
    - "Models are the single source of truth; `alembic check` / `command.check` proves the migrations agree"
    - "Alembic Config built in code (migration_config) with the connection in config.attributes; never a URL in the ini or set_main_option"
    - "Constraint tests assert the NAME of the constraint that fired (psycopg diag.constraint_name)"
    - "Readiness checks read app state lazily and fail closed when the dependency is absent"
    - "Code that a framework loads under a foreign module name lives in a normal package module behind a thin shim (coverage)"

key-files:
  created:
    - alembic.ini
    - src/truthtrail/db/models.py
    - src/truthtrail/db/__main__.py
    - src/truthtrail/db/health.py
    - src/truthtrail/db/migration_env.py
    - src/truthtrail/db/migrations/__init__.py
    - src/truthtrail/db/migrations/env.py
    - src/truthtrail/db/migrations/script.py.mako
    - src/truthtrail/db/migrations/versions/0001_baseline.py
    - tests/test_migrations.py
    - tests/test_db_constraints.py
    - tests/test_sql_parameterised.py
    - tests/test_readiness_database.py
  modified:
    - src/truthtrail/db/__init__.py
    - src/truthtrail/core/boot.py
    - src/truthtrail/api/app.py
    - tests/conftest.py
    - tests/test_db_url.py
    - .github/workflows/ci.yml
    - tests/test_ci_workflow.py
    - tests/test_container_files.py
    - .planning/phases/03-real-propagation-data/deferred-items.md

key-decisions:
  - "Key column widths follow the ratified d17-hmac-v1 scheme exactly: URI keys varchar(20), accounts.pseudonym varchar(16), claim_key and text_hash varchar(26); the plan's widths matched the spike, so nothing halted"
  - "events.via_uri is in the baseline (gate schema_via_uri true), a secondary relation like quoted_uri"
  - "ingest_checkpoints.dialect and host are NOT NULL (a cursor is meaningless without them); ingest_runs.dialect and host are nullable (the run row is written before a host is chosen)"
  - "The two partial indexes carry explicit names (ix_cascades_enrich_dirty, ix_events_orphans); every other name is the convention name"
  - "Migrations through the CLI use create_db_engine(role=jobs) instead of a bare NullPool engine, so they inherit the connect, 30 s statement and 2 s lock timeouts (T-03-18)"
  - "python -m truthtrail.db exit codes: 0 ok, 1 drift, 3 configuration error, 5 database failure"
  - "BootSettings.demo_mode is lenient at construction (unparseable = false, so the database check is registered and fails closed); the strict Settings in the lifespan still refuses to start on it"
  - "An invalid DATABASE_URL scheme stops startup in the lifespan (ConfigurationError, value never echoed); an unreachable database does not"
  - "After disposing an owned engine the lifespan resets app.state.engine to None"
  - "REQUIRE_DB_FLOOR in CI is 65, the collected requires_db count at the end of this plan"

patterns-established:
  - "assert_rejected(engine, constraint_name, statement, params): one transaction per rejected write"
  - "A tracked-but-pending runtime file (PENDING_RUNTIME_DATA) fails the test with an instruction once it exists"

requirements-completed: [DATA-02]

coverage:
  - id: D1
    description: "alembic upgrade head on an empty PostgreSQL creates exactly the eight tables with the DATA-02 columns, timestamptz throughout, via_uri iff ratified, nothing synthetic; check clean; downgrade base leaves alembic_version; upgrade again clean (programmatic and CLI)"
    requirement: DATA-02
    verification:
      - kind: integration
        ref: "REQUIRE_DB=1 .venv/bin/python -m pytest -q tests/test_migrations.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every edge, orphan, tombstone and minimisation invariant is rejected by the named constraint; FK cascade and SET NULL behave"
    requirement: DATA-02
    verification:
      - kind: integration
        ref: "REQUIRE_DB=1 .venv/bin/python -m pytest -q tests/test_db_constraints.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "No f-string, percent or format() SQL and no date_trunc/extract anywhere in src (AST rule with negative controls)"
    requirement: DATA-02
    verification:
      - kind: unit
        ref: "tests/test_sql_parameterised.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "/ready database check fails closed (missing engine, closed port, missing table, wrong or extra revision, refused connection) and recovers; plain and demo apps unchanged; no URL in body or logs"
    requirement: DATA-02
    verification:
      - kind: integration
        ref: "REQUIRE_DB=1 .venv/bin/python -m pytest -q tests/test_readiness_database.py tests/test_health_ready.py tests/test_readiness_registry.py tests/test_app_factory.py"
        status: pass
    human_judgment: false
  - id: D5
    description: "CI workflow and container contract (static)"
    requirement: DATA-02
    verification:
      - kind: unit
        ref: "tests/test_ci_workflow.py tests/test_container_files.py"
        status: pass
    human_judgment: false
  - id: D6
    description: "First GitHub Actions run: postgres 17 service healthy, four alembic steps green, pytest with REQUIRE_DB=1 at or above the floor, coverage gate, packaged head printed inside the image"
    requirement: DATA-02
    verification: []
    human_judgment: true
    rationale: "No Actions runner or Docker daemon in this container (RESEARCH A4); OPEN non-gating follow-up"

duration: 34min
completed: 2026-11-06
status: complete
---

# Phase 3 Plan 03: Postgres schema, packaged Alembic baseline, database readiness and CI Postgres Summary

**The D-20 schema is now defined once, as declarative models. A hand-reviewed baseline revision ships inside the package. The database itself rejects every edge, tombstone and minimisation violation by a named CHECK constraint. `/ready` fails closed on the database. CI runs the real Alembic round trip against a digest-pinned PostgreSQL 17 service, with a floor of 65 database tests.**

## Performance

- **Duration:** about 34 min (2026-11-06T08:56:48Z to 09:31Z)
- **Tasks:** 3 of 3, plus one fix commit for a problem found in Task 3
- **Files:** 13 created, 9 modified

## Gate output (D-02)

`.venv/bin/python scripts/check_spike_ratified.py --json` exited 0 before the first write and again at the start of each task. The fields used here: `"schema_via_uri": "true"`, `"resolved_od1": "RT-2"`, `"resolved_od2": "M1"`, `"resolved_od3": "A"`, `"pseudonym_scheme": "d17-hmac-v1"`. These are the same effective parameters 03-02-SUMMARY recorded. The root pin guard printed `root pin ok` before every commit.

**Key widths against the ratified scheme.** 03-SPIKE.md and D-17 specify a URI key of 20 base32 characters (100 bits) and an account pseudonym of 16 (80 bits). The plan's `varchar(20)` and `varchar(16)` match, so there was no conflict to report. `claim_key` and `text_hash` are `varchar(26)`, the 26-character truncated SHA-256 that plans 03-05 and 03-08 compute.

## Reviewed baseline revision (`0001_baseline.py`), highlights

- It was autogenerated with `alembic revision --autogenerate -m baseline --rev-id 0001` against an empty throwaway PostgreSQL 16.15 cluster, then rewritten by hand. Tables are created in dependency order: news_queries, accounts, claims, cascades, events, ingest_checkpoints, ingest_runs, news_fetches. `downgrade()` drops them in exact reverse order, with each table's indexes dropped first.
- Every name is the convention name, passed through `op.f`: `pk_<t>`, `uq_<t>_<cols>`, `ck_<t>_<name>`, `fk_<t>_<col>_<ref>`, `ix_<t>_<cols>`. The two partial indexes carry explicit names, `ix_cascades_enrich_dirty (id) WHERE enrich_dirty` and `ix_events_orphans (cascade_id) WHERE parent_state = 'orphan'`.
- Ten named CHECKs on events:
  - `edge_kind` IN root, reply, quote, repost
  - `root_iff_no_parent`: `(edge_kind = 'root') = (parent_uri IS NULL)`
  - `inferred_iff_repost`
  - `repost_has_no_depth`
  - `parent_state` IN none, resolved, orphan, invalid
  - `none_iff_root`
  - `no_self_parent`
  - `text_only_on_root`
  - `purged_text_is_null`
  - `tombstone_is_minimal`: `deleted_at IS NULL OR (account_id, occurred_at, text, claim_id, lang all NULL)`

  There are also `ck_claims_kind` and `ck_ingest_runs_mode`.
- Foreign keys:
  - claims.query_id SET NULL
  - cascades.claim_id SET NULL
  - events.parent_event_id SET NULL
  - events.cascade_id CASCADE
  - events.account_id SET NULL
  - events.claim_id SET NULL
  - news_fetches.query_id CASCADE
- Server defaults:
  - identity ids
  - counters 0
  - `parent_state` 'orphan'
  - `enrich_dirty` true
  - `resume_gap` false
  - `outcome` 'pending'
  - `now()` for claims.created_at and ingest_checkpoints.updated_at
  - `'{}'::jsonb` counters
- Indexes:
  - cascades: `(last_event_at, id)`, `(events_1h, id)`, the partial dirty index and `(claim_id)`
  - events: `uq_events_uri`, `(cascade_id, observed_at, uri)` and the partial orphan index
  - news_fetches: `(called_at)`

  There is no `parent_uri` or `account_id` index (RESEARCH Pattern 6, F-17).
- The schema has no `synthetic` column, no claim_scores, model_versions, cascade_features or simulation table, and no OD number. `cascades.overflow_through_us` is a nullable bigint.
- `alembic check` against the models reports no drift on PostgreSQL 16, including the partial indexes, the identity columns and the jsonb default.

**For the verifier (D-15).** DATA-02's column names are `uri` and `parent_uri`. Their values are the keyed forms of the `at://` URIs (D-17, lowercase base32 HMAC-SHA256, 20 characters), not clear URIs. The same holds for `reply_root_uri`, `quoted_uri`, `via_uri` and `cascades.root_uri`.

## CI service image digest and how it was verified

- At planning time (2026-10-18) `postgres:17.11-bookworm` was `sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826`.
- **The tag has moved.** On 2026-11-06 the Docker Hub tags API (`last_updated` 2026-11-05T10:12:51Z) and, as the authoritative check, the registry manifest HEAD with an anonymous pull token both returned `sha256:665dc7b37ac52a17e298511414c21d23ffa4e6a6ef6225b3e5d59c7afb35e994`. The registry header was `docker-content-digest`, the media type an OCI image index, the status HTTP 200 with no 429.
- The workflow pins `postgres:17.11-bookworm@sha256:665dc7b37ac52a17e298511414c21d23ffa4e6a6ef6225b3e5d59c7afb35e994`.

## Database test floor

`REQUIRE_DB_FLOOR: "65"` in CI. This is the count from `pytest -m requires_db --collect-only -q` at the end of the plan (65/1048): 15 from 03-02, plus 13 in test_migrations, 29 in test_db_constraints and 8 in test_readiness_database. `tests/test_ci_workflow.py::MIN_DB_FLOOR = 65` makes the floor ratchet upward only.

## OPEN follow-up (non-gating, human)

After the orchestrator pushes, open the GitHub Actions run for `5afa686` (or a later commit) and read two jobs. In the tests job:

- the postgres service is healthy;
- the four steps `Alembic upgrade head`, `downgrade base`, `upgrade head again` and `check` are green;
- pytest runs with REQUIRE_DB=1 and does not fail with a REQUIRE_DB_FLOOR message;
- the coverage gate passes.

In the docker job, the step "Assert the packaged migrations are in the image" prints `0001`.

**Status: OPEN.** Only CI exercises PostgreSQL 17; every local run used 16.15.

## Accomplishments

- Models, the packaged migrations, `migration_config()`, `packaged_head()` and `python -m truthtrail.db migrate|check|heads`. The command works with no ini file (tested from an empty directory). Every failure message is the exception class name or a variable name only: a `%`-encoded marker password never appears in the output of the packaged command or of the `alembic` CLI. A negative control shows that `Config.set_main_option` really does leak such a URL.
- `/ready` registers `database` exactly when an engine is injected, or when DATABASE_URL is set without DEMO_MODE. The response is 503 `Not ready: database.` for each of these cases, and recovers to 200:
  - a missing engine
  - a closed port, within the registry timeout
  - no alembic_version table (the log shows `error=ProgrammingError`)
  - a wrong revision
  - an extra revision row
  - `ALLOW_CONNECTIONS false` with the backends terminated

  The probe's 1.5 s statement timeout is transaction-local (`SHOW statement_timeout` is still `5s` on the same pooled connection).
- The lifespan builds and owns an api-role engine, and the `engine_disposed` event confirms it is disposed. It never disposes an injected engine. An unreachable database does not stop startup.
- In CI, the tests job gains the service, the job env, a 15-minute timeout and the four Alembic CLI steps before pytest. The docker job gains the `packaged_head()` check. The header comment is updated, and the gitleaks job is byte-identical (compared with `cmp`).
- `test_container_files.py` changes:
  - its ENV/ARG pattern also forbids DATABASE_URL, PSEUDONYM and COLLECTOR;
  - a `.dockerignore` matcher (anchored at the root, `*`/`?` within one segment, `**` across segments, `!` re-includes, last rule wins), with 9 hiding and 10 harmless negative controls, proves that no rule hides the four runtime paths;
  - the paths that exist are required to exist.

## Task Commits

1. **Task 1: schema, packaged Alembic, `python -m truthtrail.db`, migration/constraint/SQL-hygiene tests**: `e8193c5` (feat)
2. **Task 2: database readiness check and engine wiring**: `030b72f` (feat)
3. **Fix found in Task 3: Alembic environment moved to a traced module (coverage gate)**: `75d1b56` (fix)
4. **Task 3: CI PostgreSQL service, Alembic round trip, DB floor, image check**: `5afa686` (ci)

The per-plan ledger recorded `8f9bb12` at plan start; `git rev-list --count 8f9bb12..HEAD` = 4 before the docs commit. Every commit carries the two trailers `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01RrbnqswEy1t46d655GHDjC`, as the orchestrator instructed. The plan text names `Claude Sonnet 5.5`; the orchestrator's instruction took precedence.

## Verification results

- `uv run pytest -q`: **1038 passed, 10 xfailed, 0 XPASS**. The baseline was 951; this plan adds 87 tests:
  - test_migrations 24
  - test_db_constraints 29
  - test_sql_parameterised 7
  - test_readiness_database 19
  - test_ci_workflow +5 (18 to 23)
  - test_container_files +3 (13 to 16)
- `REQUIRE_DB=1 uv run pytest -q -m requires_db`: 65 passed. With `REQUIRE_DB_FLOOR=65`: 65 passed, exit 0.
- `pytest -m "not requires_db"`: 973 passed, 65 deselected, 10 xfailed.
- Plan verify commands:
  - The two DB test files together have 53 tests (42 requires_db), with none skipped.
  - test_sql_parameterised has 7 tests.
  - `packaged_head()` prints `0001`.
  - The OpenAPI golden, OpenAPI contract and v1-limits tests pass unchanged (22).
  - The Phase 2 readiness, registry and app-factory tests pass with no assertion edits.
- CI simulation, the tests job reproduced locally: a throwaway cluster stood in for the service; `alembic upgrade head / downgrade base / upgrade head / check` against its default database all exited 0; then `pytest --cov --hypothesis-profile=ci -q` ran with TEST_DATABASE_URL, REQUIRE_DB=1 and REQUIRE_DB_FLOOR=65. Result: 1038 passed, **coverage 98.75 percent** (gate 96), exit 0.
- `uv run ruff check .`, `ruff format --check .` and `mypy` (strict, 33 files) are clean. `uv run python scripts/copy_guard.py` is clean, and so is `scripts/generate_demo_fixture.py --check`.
- The pip-audit command from ci.yml (`uv export --locked --no-emit-project --all-groups ...` then `pip-audit -r ... --require-hashes --disable-pip`) reports no known vulnerabilities.
- gitleaks 8.30.1:
  - `scripts/gitleaks_scan.sh` over the plan range 8f9bb12..5afa686 (4 commits): clean
  - floor range a5dd825..HEAD (149 commits): clean
  - working tree: clean
  - `gitleaks dir src/truthtrail/data/recorded`: clean
- Before each commit:
  - root pin ok;
  - `tests/test_no_hardcoded_credentials.py` 13 passed;
  - the 32-hex added-lines scan found 0;
  - the old-key scan (key derived inside Python from `git show 9b5b085:gnews_fetcher.py`, counts only) derived 1 candidate with 0 occurrences;
  - `gitleaks git --pre-commit --staged` exited 0.
- A wheel built with `uv build --wheel` into a scratch directory contains `truthtrail/db/migrations/{__init__,env}.py`, `script.py.mako` and `versions/0001_baseline.py`, so the non-editable image install ships the migrations.
- The frozen files are unchanged in this range: `legacy/`, `keyword_baseline.py`, the demo fixture, `test_char_*`, `test_demo_fixture.py`, `test_legacy_frozen.py` and the golden. Their content equals `9b5b085` apart from Phase 2's LF normalisation.
- No postgres process, no `tt-pg-*` directory and no `__pycache__` outside `.venv` remain.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] A plan 03-02 AST test forbade every `create_db_engine` call outside `db/engine.py`**
- **Found during:** Task 1 (full suite)
- **Issue:** `tests/test_db_url.py::test_no_module_level_engine_and_one_factory` counted calls to `create_db_engine` anywhere as offenders. That contradicts this plan, which requires the packaged command and the lifespan to call the factory, and it contradicts the test's own docstring ("`create_engine` is called only inside `create_db_engine`; nothing builds an engine at import time").
- **Fix:** The call-site rule now covers raw `create_engine` and `engine_from_config` outside `db/engine.py`. The module-level rule, which forbids any engine-building assignment at import time (`create_db_engine` included), is unchanged.
- **Files modified:** tests/test_db_url.py
- **Commit:** e8193c5

**2. [Rule 2 - Missing critical functionality] The `alembic` CLI engine had no timeouts**
- **Found during:** Task 1
- **Issue:** The plan's env.py built a bare `NullPool` engine for the CLI path, which has no connect, statement or lock timeout (T-03-18).
- **Fix:** It now uses `create_db_engine(raw, role="jobs", pool_size=1, max_overflow=0)`, disposed after the run.
- **Commit:** e8193c5

**3. [Rule 3 - Blocking] The CI coverage gate would have failed**
- **Found during:** Task 3 (local reproduction of the CI tests job)
- **Issue:** Alembic loads `env.py` under its own module name, so coverage (`source = ["truthtrail"]`, pinned by `tests/test_coverage_config.py`) discovered the file but never traced it. The total was 95.75 percent against the 96 gate.
- **Fix:** The environment logic moved to `truthtrail.db.migration_env`; `env.py` is a two-statement shim. An in-process exit-code test of the packaged command was added, and an unreachable branch in `health.py` was removed. The total is now 98.75 percent.
- **Files:** src/truthtrail/db/migration_env.py (new, not in the plan's file list), src/truthtrail/db/migrations/env.py, src/truthtrail/db/health.py, tests/test_migrations.py, tests/test_sql_parameterised.py
- **Commit:** 75d1b56

**4. [Rule 3 - Blocking] Two contradictions in Task 3 step 4 (`tests/test_container_files.py`)**
- **Topics file:** the plan says the four runtime paths must exist on disk, but `src/truthtrail/data/news_topics.toml` is created by plan 03-08. The ignore-rule check covers all four paths now. Existence is required for the three that exist; `news_topics.toml` is listed in `PENDING_RUNTIME_DATA`, and the test fails with an instruction to move it as soon as the file exists. This is recorded in deferred-items.md for 03-08.
- **Recorded fixture:** the plan says "the recorded fixture directory is likewise asserted not hidden", but `.dockerignore` hides it on purpose. The existing test `test_the_recorded_fixture_stays_out_of_the_image_while_no_runtime_code_reads_it` requires it to stay hidden while no runtime code reads it, and it may not be weakened. The new test is that test's mirror: the fixture is hidden **exactly** while no package module reads it, so it must ship once a reader appears. Neither `.dockerignore` nor the image contents changed.
- **Commit:** 5afa686

**Other notes:**
- `migrated_db_url` and `clean_db` were added to the conftest `DB_FIXTURES` set, so using them without `requires_db` is a collection error.
- The `alembic.ini` sets `path_separator = os` (required by Alembic 1.20 to avoid a deprecation warning under `filterwarnings = error`) and `file_template = %%(rev)s_%%(slug)s`.
- `python -m truthtrail.db check` returns exit 1 on drift, which the plan's exit-code list (0/3/5) did not cover.

**Total deviations:** 4 auto-fixed (1 Rule 1, 1 Rule 2, 2 Rule 3). **Impact:** each keeps the plan's own requirements (factory use, T-03-18, the coverage gate, "extended, not weakened") consistent. No scope creep.

## Issues Encountered

- **Coverage rounding (pre-existing, deferred).** pytest-cov compares the total rounded to coverage's `precision`, which defaults to 0. The run at 95.75 percent therefore exited 0 even though the summary printed `FAIL Required test coverage of 96.0% not reached`, so the effective gate is about 95.5 percent. Changing the Phase 2 gate configuration is outside this plan; the suggested fix is `precision = 2` plus a pin in test_coverage_config. It is recorded in deferred-items.md.
- After `pg_ctl -m immediate stop`, a `<defunct>` postmaster can show briefly until PID 1 reaps it, as 03-02 noted. None was left running.

## Known Stubs

None. No table, column or route serves placeholder data.

## Threat Flags

None. The new surface is in the plan's register, with mitigations implemented and tested:
- the packaged migration command (T-03-15, marker-password tests)
- the SQL hygiene rule (T-03-16)
- the schema invariants (T-03-17)
- the timeouts and readiness bound (T-03-18)
- the digest pin and the throwaway credential (T-03-19)
- the not_ready body and logs (T-03-20)

## Requirement status

DATA-02 (Postgres schema with Alembic migrations) is complete for the repository: the schema, the baseline, the upgrade/downgrade/check proof on a real PostgreSQL, and the CI steps. The PostgreSQL 17 CI run is the OPEN non-gating follow-up above.

## Next Phase Readiness

Plan 03-04 onward can use:
- `truthtrail.db.models` and its table and column names
- `migrated_db_url` with `clean_db` for writer tests
- `upgrade_to_head(url)` for isolated databases
- `create_app(engine=...)` for API tests

Plan 03-08 must move `news_topics.toml` out of `PENDING_RUNTIME_DATA`. Plan 03-12's `require_database_unless_demo` can rely on `app.state.engine` and `engine_owned`.

---
*Phase: 03-real-propagation-data*
*Completed: 2026-11-06*

## Self-Check: PASSED

All 13 created files exist; commits e8193c5, 030b72f, 75d1b56 and 5afa686 are ancestors of HEAD and each carries both trailers.
