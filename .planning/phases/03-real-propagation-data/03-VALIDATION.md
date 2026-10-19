---
phase: "3"
slug: "real-propagation-data"
# status lifecycle: draft (seeded by plan-phase) -> validated (set by plan 03-10 Task 3 when the phase gate passes; /gsd-validate-phase may re-audit it afterwards)
# audit-milestone section 5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-18"
---

# Phase 3 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Seeded from `03-RESEARCH.md` "Validation Architecture"; the per-task rows below are filled from the twelve PLAN files. Commands assume cwd = repo root and the uv-created `.venv` (`.venv/bin/python` works everywhere). PostgreSQL 16 binaries exist in this container and the database fixture starts a throwaway cluster as the `postgres` system user, so database tests run here; Docker, the GitHub Actions runner (PostgreSQL 17 service container), Windows and the real GNews API cannot be exercised here and are covered by static tests plus the NON-GATING human follow-ups under "Manual-Only Verifications". The real Bluesky Jetstream is reachable from this container and is used by the spike (plan 03-01) and by `tests/live_smoke.py` (plans 03-05 and 03-10) outside pytest; an HTTP 403 from it stops the step and is reported, nothing is substituted.
>
> **Gate (CONTEXT D-02):** only plan 03-01 may run before the owner ratifies `03-SPIKE.md`. Every later plan starts with `.venv/bin/python scripts/check_spike_ratified.py --json` and halts on a non-zero exit; the gate also requires the owner's explicit confirmation of the one-way D-17 identifier scheme (`pseudonym_scheme d17-hmac-v1`, token `pseudonym=d17`), and plan 03-04 carries a checkpoint that verifies it before the first keyed identifier is computed. Execution order by wave: 03-01 (1), 03-02 (2), 03-03 (3), 03-04 (4), 03-05 (5), 03-06 (6), 03-07 (7), 03-08 (8), 03-09 (9), 03-11 (10), 03-12 (11), 03-10 (12): plan 03-10 is numbered 10 but runs last because the former plan 03-09 was split into 03-09, 03-11 and 03-12. The ratification itself is a GATING owner checkpoint (last task of 03-01), not a non-gating follow-up.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1, pytest-cov 7.1.0, hypothesis 6.170.1, responses 0.26.3, Starlette `TestClient` (httpx 0.28.1), PyYAML 6.0.3 (static CI test); new runtime libraries from plan 03-02: sqlalchemy 2.1.5, psycopg[binary] 3.3.6, alembic 1.20.0, websockets 17.2. No new test dependency: the PostgreSQL fixture is ours (`tests/pg_cluster.py`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (plan 03-02 adds the `requires_db` marker and `--strict-markers`; `filterwarnings = error` stays, so every engine is disposed); Hypothesis profiles `ci` and `dev` in `tests/conftest.py`; coverage in `[tool.coverage.*]` (gate ratcheted in plan 03-10, never below 96) |
| **Quick run command** | `.venv/bin/python -m pytest -x -q -m "not requires_db" tests/{affected file}.py` (no database needed) |
| **Database loop** | `REQUIRE_DB=1 .venv/bin/python -m pytest -x -q -m requires_db tests/{affected file}.py` (provisions a throwaway cluster, about 3 s overhead; as root it runs `initdb` and `pg_ctl` as `postgres` through `runuser`) |
| **Full suite command** | `REQUIRE_DB=1 .venv/bin/python -m pytest --cov --hypothesis-profile=ci -q` |
| **Non-pytest gates** | `.venv/bin/ruff check . && .venv/bin/ruff format --check .`; `.venv/bin/mypy`; `.venv/bin/python scripts/copy_guard.py`; `.venv/bin/python scripts/generate_demo_fixture.py --check`; `uv lock --check` (uv 0.11.32 and the scratch uv 0.13.1); the pip-audit pair (`uv export --locked --no-emit-project --all-groups --format requirements-txt -o {file}` then `.venv/bin/pip-audit -r {file} --require-hashes --disable-pip --progress-spinner off`); `bash scripts/gitleaks_scan.sh {bin} a5dd8257e920923677c60e70611a6f36d87747b2 HEAD a5dd8257e920923677c60e70611a6f36d87747b2`, `bash scripts/gitleaks_selftest.sh {bin}` and `{bin} dir src/truthtrail/data/recorded --no-banner --redact --exit-code 1`; `python scripts/smoke_app.py` against a `--locked --no-dev --no-editable` install; `.venv/bin/python scripts/check_spike_ratified.py`; `.venv/bin/python tests/live_smoke.py` (LIVE, container egress); CI (not runnable here): `alembic upgrade head`, `downgrade base`, `upgrade head`, `check` against the PostgreSQL 17 service |
| **Invariants after every plan** | xfailed stays 10 (the strict xfail characterization tests), no XPASS; the passed count only grows from 533 EXCEPT in plans 03-11 and 03-12, where the mapped retirements of the `/analyze` tests and the migration of the settings tests lower it before the replacements raise it again (recorded in the 03-11 and 03-12 SUMMARY replacement maps, whose starting point is the 03-09 baseline, checked by a collected-id diff; plan 03-09 itself deletes nothing and writes the job-level replacements first); `tests/golden/openapi_phase1.json` and its pin never change; `legacy/`, `src/truthtrail/data/demo_analyze.json`, `tests/test_char_*.py`, `tests/test_demo_fixture.py` and `tests/test_legacy_frozen.py` never change; no test hard-codes an OD value (explicit policy values only); a database test never skips silently |
| **Estimated runtime** | about 20 s without the database tests; about 2 to 4 minutes with coverage, the `ci` Hypothesis profile and the database tests (re-measured in plan 03-10, which sizes the CI timeout from it) |

---

## Sampling Rate

- **After every task commit:** the quick run (and, for database tasks, the database loop) for the touched test files, `tests/test_no_hardcoded_credentials.py`, the word-bounded 32-hex added-lines scan, `ruff check`, `ruff format --check`, `mypy` and, once API strings exist, `scripts/copy_guard.py`.
- **After every plan (one wave each):** `REQUIRE_DB=1 .venv/bin/python -m pytest -q` (the full suite), the tests named in the plan's verify block, `tests/test_openapi_golden.py` and `tests/test_import_rules.py` once they exist.
- **Before `/gsd-verify-work`:** the phase gate in plan 03-10 Task 3 (full suite with coverage and the CI profile, every non-pytest gate above, the live smoke, clean tree). The post-push Actions run on PostgreSQL 17 and the docker job are NON-GATING follow-ups harvested into the phase UAT (config `human_verify_mode: end-of-phase`); until they are confirmed, the parts of ROADMAP criteria 2 and 5 that depend on CI are 'pending human confirmation', never passed.
- **Max feedback latency:** 90 seconds for a task-level run.

---

## Per-Task Verification Map

Threat refs point at the `<threat_model>` tables in the PLAN files (IDs T-03-01 to T-03-68 are unique within the phase; T-03-SC is kept in every plan).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 03-01 | 1 | DATA-01 | T-03-01, T-03-06, T-03-SC | Pure spike libraries: selection strict-typed and stdlib-only, analysis outputs carry no DID or text (`ensure_no_identifiers`), scrubber and cutter deterministic, the manifest records the cut-time selection policy and per-window provenance | unit | `.venv/bin/python -m pytest -q tests/test_spike_analysis.py` and `MYPYPATH=scripts .venv/bin/mypy --strict scripts/spike_lib/selection.py` | W0 | pending |
| 03-01-02 | 03-01 | 1 | DATA-01 | T-03-01, T-03-04, T-03-06, T-03-SC | Spike CLI bounded (caps, 403 stops, key-free, no DB driver), analyze output carries no DID or text, live 6 s probe of four hosts | unit + live probe | `.venv/bin/python -m pytest -q tests/test_spike_tool.py tests/test_spike_analysis.py` | W0 | pending |
| 03-01-03 | 03-01 | 1 | DATA-01 | T-03-05 | Decision-document scaffold (with the D-17 one-way-door section), report template and ratification gate script (pseudonym_scheme and the explicit token); committed document unratified | unit | `.venv/bin/python -m pytest -q tests/test_spike_gate.py tests/test_spike_template.py` and `.venv/bin/python scripts/check_spike_ratified.py; test $? -eq 1` | W0 | pending |
| 03-01-04 | 03-01 | 1 | DATA-01 | T-03-01, T-03-02, T-03-03, T-03-07, T-03-08 | Real run (W1 3660 s plus W2 and W3), all S-1 to S-13 numbers recorded, real scrubbed fixture with sequential tokens, selection policy and windows in the manifest, 3600 s stream-span floor and run-log agreement tested, gitleaks clean, raw logs deleted | integration (live) + static | `.venv/bin/python -m pytest -q tests/test_recorded_fixture.py tests/test_seed_domains.py` and `"${TMPDIR:-/tmp}/truthtrail-gitleaks/gitleaks" dir src/truthtrail/data/recorded --no-banner --redact --exit-code 1` | W0 | pending |
| 03-01-05 | 03-01 | 1 | DATA-01 | T-03-05 | GATING owner checkpoint: OD-1, OD-2, OD-3, via_uri, dependency approval and the explicit D-17 confirmation (pseudonym=d17) ratified by the owner's own message or edit | checkpoint | `.venv/bin/python scripts/check_spike_ratified.py --json` (exit 0 only after the owner's reply) | n/a | pending |
| 03-02-01 | 03-02 | 2 | DATA-02 | T-03-11, T-03-13, T-03-SC | Four exact pins (eight packages added, none changed), policy object equals the ratified document, env lists drift-guarded | unit + tooling | `.venv/bin/python -m pytest -q tests/test_dependency_groups.py tests/test_policy.py tests/test_policy_docs.py` and `uv lock --check` | W0 | pending |
| 03-02-02 | 03-02 | 2 | DATA-02 | T-03-10, T-03-12, T-03-14 | Real-PostgreSQL fixtures never skip silently, non-root cluster, loopback-only socket guard, REQUIRE_DB floor | integration | `REQUIRE_DB=1 REQUIRE_DB_FLOOR=3 .venv/bin/python -m pytest -q -m requires_db tests/test_pg_fixture.py` and `.venv/bin/python -m pytest -q tests/test_socket_guard.py` | W0 | pending |
| 03-02-03 | 03-02 | 2 | DATA-02 | T-03-09 | Engine factory: timeouts, UTC session, pool exhaustion type, disposal; URL never echoed | integration | `REQUIRE_DB=1 .venv/bin/python -m pytest -q tests/test_db_url.py tests/test_db_engine.py` | W0 | pending |
| 03-03-01 | 03-03 | 3 | DATA-02 | T-03-15, T-03-16, T-03-17, T-03-18 | Schema with database-enforced edge, tombstone and privacy invariants; packaged Alembic; upgrade, check, downgrade, upgrade (programmatic and CLI); SQL parameterised only | integration (real PG) | `REQUIRE_DB=1 .venv/bin/python -m pytest -q tests/test_migrations.py tests/test_db_constraints.py tests/test_sql_parameterised.py` | W0 | pending |
| 03-03-02 | 03-03 | 3 | DATA-02, FND-02 | T-03-18, T-03-20 | `database` readiness check fails closed (missing engine, closed port, missing table, wrong revision, refused connection), plain and demo apps unchanged | integration | `REQUIRE_DB=1 .venv/bin/python -m pytest -q tests/test_readiness_database.py tests/test_health_ready.py` | W0 | pending |
| 03-03-03 | 03-03 | 3 | DATA-02 | T-03-19 | CI: digest-pinned PostgreSQL 17 service, REQUIRE_DB and floor, four-command Alembic round trip, image migration check | static contract | `.venv/bin/python -m pytest -q tests/test_ci_workflow.py` | W0 | pending |
| 03-04-00 | 03-04 | 4 | DATA-03 | T-03-22 | ONE-WAY D-17 door: the checkpoint verifies mechanically that the owner confirmed the identifier scheme (gate exit 0 and pseudonym_scheme d17-hmac-v1) before Task 1 computes any keyed identifier | checkpoint (evidence) | `.venv/bin/python scripts/check_spike_ratified.py --json` | n/a | pending |
| 03-04-01 | 03-04 | 4 | DATA-03 | T-03-21, T-03-22, T-03-25 | Non-raising `find_order_violations`; keyed HMAC pseudonymiser with known-answer test; dialect module classifies real frames, never raises | unit + property | `.venv/bin/python -m pytest -q tests/test_cascade_violations.py tests/test_pseudonym.py tests/test_ingest_dialect.py` | W0 | pending |
| 03-04-02 | 03-04 | 4 | DATA-03 | T-03-21, T-03-23, T-03-24, T-03-27 | Normaliser keeps no raw identifier, D-12 edges, bounded occurred_at; selection moved by git mv, spoof table, option B flag; fixture yield equals manifest | unit | `.venv/bin/python -m pytest -q tests/test_selection.py tests/test_ingest_normalise.py tests/test_spike_analysis.py` | W0 | pending |
| 03-04-03 | 03-04 | 4 | DATA-03 | T-03-26, T-03-28 | ReplaySource refuses non-recorded-real and hash-mismatched files and the synthetic fixture; AST import rules with negative controls; app import loads no ingest or websockets | unit + subprocess | `.venv/bin/python -m pytest -q tests/test_replay_source.py tests/test_import_rules.py` | W0 | pending |
| 03-05-01 | 03-05 | 5 | DATA-03 | T-03-29, T-03-30, T-03-32, T-03-36, T-03-37 | Writer: tracked-set only, idempotent upserts (replay twice identical, including the overflow tally of capped cascades), tombstones never resurrected, checkpoint in the same transaction (failure-injection proof), caps without eviction, OD-3 option B end to end | integration (real PG) | `REQUIRE_DB=1 .venv/bin/python -m pytest -q tests/test_ingest_writer.py tests/test_ingest_idempotency.py tests/test_ingest_deletes.py` | W0 | pending |
| 03-05-02 | 03-05 | 5 | DATA-03 | T-03-31, T-03-32, T-03-34, T-03-35 | JetstreamSource reconnect, backoff, silence, rewind by timestamp cursor, failover, 401/403 fatal, 1009 fatal, gaps; bounded run loop with named stops and lock, option B loader refreshed in the loop | integration (loopback) | `REQUIRE_DB=1 .venv/bin/python -m pytest -q tests/test_jetstream_source.py tests/test_ingest_run.py` | W0 | pending |
| 03-05-03 | 03-05 | 5 | DATA-03, FND-02 | T-03-33, T-03-37, T-03-38 | CLI exit codes, replay, erase from stdin, kill-and-resume equals uninterrupted run, no personal data in logs or rows, live run stores real cascades | integration + subprocess + live | `REQUIRE_DB=1 .venv/bin/python -m pytest -q tests/test_ingest_cli.py tests/test_ingest_crash_resume.py tests/test_no_pii_in_logs.py` and `.venv/bin/python tests/live_smoke.py` | W0 | pending |
| 03-06-01 | 03-06 | 6 | DATA-04 | T-03-39, T-03-40 | Pure resolver and rollup: order-independence and invariants under the `ci` profile, three mutants caught, orphans never re-parented, cycles invalid | property | `.venv/bin/python -m pytest -q --hypothesis-profile=ci tests/test_enrich_resolve.py tests/test_enrich_properties.py` | W0 | pending |
| 03-06-02 | 03-06 | 6 | DATA-04 | T-03-39, T-03-42, T-03-43 | Per-cascade write-back with row lock: permutation test with different surrogate ids, idempotence, orphan flips to resolved, lost-flag race impossible | integration (real PG) | `REQUIRE_DB=1 .venv/bin/python -m pytest -q tests/test_enrich_db.py` | W0 | pending |
| 03-06-03 | 03-06 | 6 | DATA-04 | T-03-41, T-03-44 | Retention purge from policy parameters at tested boundaries; idempotent, batched, dry-run, locked; enrich and purge commands | integration | `REQUIRE_DB=1 .venv/bin/python -m pytest -q tests/test_purge.py tests/test_enrich_cli.py` | W0 | pending |
| 03-07-01 | 03-07 | 7 | DATA-05, FND-02 | T-03-45, T-03-49, T-03-51 | V1Meta provenance, database error contract (503 database_unavailable and database_timeout with Retry-After, generic 500, not_configured), outage and recovery, success-only version-keyed cache | integration (real PG) | `REQUIRE_DB=1 .venv/bin/python -m pytest -q tests/test_v1_meta_errors.py tests/test_v1_outage.py tests/test_v1_cache.py` | W0 | pending |
| 03-07-02 | 03-07 | 7 | DATA-05 | T-03-46, T-03-47, T-03-48 | Cascade list (keyset pagination, malformed cursor 422), detail, tree (canonical, capped, detached orphans, inferred reposts), timeline (dense, date_bin, bounded) | integration (real PG) | `REQUIRE_DB=1 .venv/bin/python -m pytest -q tests/test_v1_cascades.py tests/test_v1_tree_timeline.py` | W0 | pending |
| 03-07-03 | 03-07 | 7 | DATA-05 | T-03-46, T-03-49, T-03-50, T-03-52 | `/v1/stats` from rollups only, OpenAPI walk (exactly 200, 422, 429, 500, 503; no 502; typed meta; no risk or claim_scores), golden /v1 allowance, rate limit, provenance on every route | integration + contract | `REQUIRE_DB=1 .venv/bin/python -m pytest -q tests/test_v1_stats.py tests/test_v1_openapi.py tests/test_openapi_golden.py` | W0 | pending |
| 03-08-01 | 03-08 | 8 | DATA-06 | T-03-54, T-03-58 | Adapter `max_results` and `with_url` keep defaults byte-identical; NewsSettings; committed topic set validated | unit | `.venv/bin/python -m pytest -q tests/test_gnews_max_results.py tests/test_news_topics.py tests/test_upstream_errors.py tests/test_retries.py tests/test_settings.py` | W0 | pending |
| 03-08-02 | 03-08 | 8 | DATA-06 | T-03-53, T-03-54, T-03-59 | Ledgered news job: daily budget, per-run cap, minimum refresh, committed-before-call, 1.1 s spacing, stop on 503 and 403, failed topics, exit codes; mock provider only | integration (real PG + responses) | `REQUIRE_DB=1 .venv/bin/python -m pytest -q tests/test_news_job.py tests/test_news_cli.py` | W0 | pending |
| 03-08-03 | 03-08 | 8 | DATA-06 | T-03-55, T-03-56, T-03-57 | `/v1/news` serves stored headlines with data_as_of = last fetch, works with the key unset and fetch patched to fail | integration | `REQUIRE_DB=1 .venv/bin/python -m pytest -q tests/test_v1_news.py tests/test_v1_openapi.py` | W0 | pending |
| 03-09-01 | 03-09 | 9 | DATA-06 | T-03-61 | Demo loader relocated; app-factory, cascade-gate, provenance-label and network-guard tests retargeted while the route still exists; nothing deleted | regression | `.venv/bin/python -m pytest -q tests/test_app_factory.py tests/test_cascade_gate.py tests/test_provenance_demo.py tests/test_network_guard.py` | existing | pending |
| 03-09-02 | 03-09 | 9 | DATA-06 | T-03-61 | CORS, rate-limit, request-validation and proxy-header tests retargeted to probe /v1 routes; job-level replacements for the endpoint retry and error tests written before the retirement | regression + integration | `.venv/bin/python -m pytest -q tests/test_cors.py tests/test_rate_limit.py tests/test_request_validation.py tests/test_proxy_headers_server.py` and `REQUIRE_DB=1 .venv/bin/python -m pytest -q tests/test_news_job.py` | existing | pending |
| 03-11-01 | 03-11 | 10 | DATA-06 | T-03-62, T-03-64 | `/analyze`, cache and budget retired in one commit; replacement map; id-diff gate; Phase 3 golden pinned; Phase 1 golden untouched | regression + contract | `REQUIRE_DB=1 .venv/bin/python -m pytest -q tests/test_openapi_golden.py tests/test_openapi_contract.py tests/test_news_job.py tests/test_v1_cache.py` and the collected-id diff check of the plan | W0 | pending |
| 03-11-02 | 03-11 | 10 | DATA-06 | T-03-62 | Retirement proved: 404 problem+json, absent from OpenAPI, zero provider calls, retired modules gone | unit | `.venv/bin/python -m pytest -q tests/test_analyze_retired.py` | W0 | pending |
| 03-12-01 | 03-12 | 11 | DATA-06, FND-02 | T-03-63 | Settings split (DATABASE_URL required unless demo, exit 3; the news key only in NewsSettings); environment lists agree at 45 names | unit + subprocess | `REQUIRE_DB=1 .venv/bin/python -m pytest -q tests/test_settings.py tests/test_upstream_errors.py tests/test_no_hardcoded_credentials.py tests/test_readme_env_table.py` | W0 | pending |
| 03-12-02 | 03-12 | 11 | DATA-06 | T-03-60 | Three-layer proof that no request handler can reach the news API; empty api exemption set; no news key under api | static + subprocess + integration | `REQUIRE_DB=1 .venv/bin/python -m pytest -q tests/test_no_news_in_handlers.py tests/test_import_rules.py` | W0 | pending |
| 03-12-03 | 03-12 | 11 | DATA-06 | T-03-60, T-03-63 | Smoke script and CI docker probes updated; README describes only routes that exist | static | `.venv/bin/python -m pytest -q tests/test_ci_workflow.py tests/test_analyze_retired.py tests/test_readme_env_table.py` | W0 | pending |
| 03-10-01 | 03-10 | 12 | DATA-01 to DATA-06 | T-03-65, T-03-66 | README and docs/data-and-ethics.md truthful, copy-guard clean, commands and /v1 paths resolve to real code | doc contract | `.venv/bin/python -m pytest -q tests/test_docs_data.py tests/test_readme_env_table.py` and `.venv/bin/python scripts/copy_guard.py` | W0 | pending |
| 03-10-02 | 03-10 | 12 | DATA-03, DATA-05 | T-03-67 | DB-test floor and coverage ratchet; real-data collect, enrich and serve confirmation | coverage + live | `REQUIRE_DB=1 .venv/bin/python -m pytest --cov --hypothesis-profile=ci -q` and `.venv/bin/python tests/live_smoke.py` | W0 | pending |
| 03-10-03 | 03-10 | 12 | DATA-01 to DATA-06 | T-03-68 | Phase gate: every command green, then this contract flips to validated | gate | the gate list in plan 03-10 Task 3 | n/a | pending |

*Status: pending / green / red / flaky. Update from the SUMMARY of each plan.*

---

## Requirement -> Test Map (ROADMAP success criteria)

| Criterion | Requirement | Behavior | Proof |
|-----------|-------------|----------|-------|
| SC1 | DATA-01 | A written decision covers source terms, live-tail volume, measured cascade yield, edge semantics, tracked-root selection and retention, and a real-data fixture is in the repo, before any schema work | `03-SPIKE.md` (S-1 to S-13 measured), `tests/test_recorded_fixture.py` (including the 3600 s measured stream-span floor and the agreement of the manifest windows with the run log and the fixture's own stream times), `tests/test_seed_domains.py`, the gitleaks scan of the fixture, `scripts/check_spike_ratified.py` exit 0 after the owner checkpoint, which includes the explicit D-17 confirmation (GATING) |
| SC2 | DATA-02 | `alembic upgrade head` on an empty Postgres creates accounts, claims, cascades and events with `observed_at`, `occurred_at`, `edge_kind`, `inferred`, `parent_uri`; upgrade and downgrade run against a real Postgres in CI | `tests/test_migrations.py` (programmatic and CLI, PostgreSQL 16 here), `tests/test_db_constraints.py`, `tests/test_ci_workflow.py`; **CI run on PostgreSQL 17 = NON-GATING human follow-up; status 'pending human confirmation' (OPEN), never 'passed' before it** |
| SC3 | DATA-03 | Bounded collector stores events only for tracked roots; replay twice leaves identical row counts; a killed run resumes without loss or duplicates; a delete removes the content | `tests/test_ingest_writer.py` (including the failure-injection atomicity proof and OD-3 option B), `tests/test_ingest_idempotency.py` (including the overflow tally of capped cascades), `tests/test_ingest_crash_resume.py`, `tests/test_ingest_deletes.py`, `tests/test_jetstream_source.py`, `tests/live_smoke.py` |
| SC4 | DATA-04 | Enrich resolves parents and rolls up; orphans explicit, parents never invented; shuffled arrival order yields identical state | `tests/test_enrich_properties.py` (`ci` profile plus three mutants), `tests/test_enrich_db.py` (permutations), `tests/test_enrich_resolve.py` |
| SC5 | DATA-05, DATA-06, FND-02 | `/v1` serves trees, timelines and stats from the database with observed since and orphan counts, honours the Phase 1 contract, a database outage returns 503 and `/ready` reports not ready; news context refreshed by a job; no handler can trigger a news-API call | `tests/test_v1_cascades.py`, `tests/test_v1_tree_timeline.py`, `tests/test_v1_stats.py`, `tests/test_v1_outage.py`, `tests/test_v1_openapi.py`, `tests/test_readiness_database.py`, `tests/test_news_job.py`, `tests/test_v1_news.py`, `tests/test_no_news_in_handlers.py`, `tests/test_analyze_retired.py`; **CI docker probes = NON-GATING human follow-up; the CI-dependent part is 'pending human confirmation' (OPEN)** |

---

## Source Coverage Audit

Every item of the four source types is covered by a plan, or excluded for a stated reason. (GOAL = ROADMAP Phase 3 goal; REQ = phase requirement IDs; RESEARCH = features and constraints of 03-RESEARCH.md; CONTEXT = D-01 to D-31 and OD-1 to OD-3 of 03-CONTEXT.md.)

| Source | ID | Feature or requirement | Plan | Status |
|--------|----|------------------------|------|--------|
| GOAL | - | Real Bluesky propagation data collected within stated bounds, stored in Postgres with honest edge semantics, served by a typed read API; nothing fabricated on the live path | 03-01 to 03-12 | COVERED |
| REQ | DATA-01 | Source spike: written decision plus recorded real fixture | 03-01 | COVERED |
| REQ | DATA-02 | Postgres schema with Alembic migrations | 03-02, 03-03 | COVERED |
| REQ | DATA-03 | Bounded Jetstream v2 collector: idempotent, checkpoint after commit, deletes honoured | 03-04, 03-05 | COVERED |
| REQ | DATA-04 | Enrich resolves parents and rolls up; orphans explicit; shuffled-order property test | 03-06 | COVERED |
| REQ | DATA-05 | `/v1` read API with trees, timelines, stats, observed since, orphan counts | 03-07 | COVERED |
| REQ | DATA-06 | News context by job, served from the database, no user-query proxying | 03-08, 03-09, 03-11, 03-12 | COVERED |
| REQ | FND-02 (Bluesky and database paths) | 502/503 machine-readable bodies for database and Bluesky failures | 03-03 (readiness), 03-05 (source failures as exit codes and stale data), 03-07 (503 contract) | COVERED |
| REQ | ML-05, UI-01, UI-02, UI-04, OPS-02 | Depend on this phase's fields and caveats | 03-07 (fields), 03-10 (documentation) | EXCLUDED (Phases 4 to 6 own the work; the data and caveats are handed over) |
| REQ | DOC-02 | Limitations and ethics section | 03-10 Task 1 (`docs/data-and-ethics.md` hand-off); the final README section is Phase 6 | COVERED (hand-off) |
| RESEARCH | F-01 | Fixture tokens: sequential counters, not random base32 | 03-01 T1, T4 | COVERED |
| RESEARCH | F-02 | Timestamp cursor below the floor is clamped with an in-band `#info OutdatedCursor` | 03-01 T2, 03-04 T1, 03-05 T2 | COVERED |
| RESEARCH | F-03 | `witnessedAt` is the portable position; `seq` is per instance | 03-04 T1, 03-05 T2 | COVERED |
| RESEARCH | F-04 | `maxMessageSizeBytes` below `max_size`; 1009 is fatal | 03-04 T1, 03-05 T2 | COVERED |
| RESEARCH | F-05 | Catch-up arithmetic versus cadence | 03-01 T4 (document), 03-10 T1 (README) | COVERED (Phase 6 chooses the cadence) |
| RESEARCH | F-06 | First-come cap bias; deterministic sampling parameter | 03-01 T4, 03-02 T1, 03-04 T2, 03-05 T1 | COVERED |
| RESEARCH | F-07 | Repost `via`: nullable `via_uri` hedge | 03-01 T3, T5, 03-03 T1, 03-04 T2 | COVERED |
| RESEARCH | F-08 | Edge targets only for posts; did:web; unknown embeds | 03-01 T1, 03-04 T2 | COVERED |
| RESEARCH | F-09 | Dispose every engine under `filterwarnings = error` | 03-02 T2, T3 | COVERED |
| RESEARCH | F-10 | `initdb -E UTF8 --locale=C`; non-root cluster | 03-02 T2 | COVERED |
| RESEARCH | F-11 | Engine injection into `create_app` and the readiness check | 03-03 T2 | COVERED |
| RESEARCH | F-12 | `psycopg[binary]` only | 03-02 T1 | COVERED |
| RESEARCH | F-13 | GNews facts: 100 per day, max 10, 403 means quota, 1 per second | 03-08 T1, T2 | COVERED |
| RESEARCH | F-14 | URL never through `set_main_option` | 03-03 T1 | COVERED |
| RESEARCH | F-15 | Session UTC; `date_bin`, not `date_trunc` | 03-02 T3, 03-03 T1, 03-07 T2 | COVERED |
| RESEARCH | F-16 | Tree prefix closure holds only without order violations; runtime guard | 03-07 T2 | COVERED |
| RESEARCH | F-17 | Stats from rollups; keep three indexes | 03-03 T1, 03-07 T3 | COVERED |
| RESEARCH | F-18 | Deletion statuses are an allow-list; updates ignored | 03-04 T1, T2, 03-05 T1 | COVERED |
| RESEARCH | F-19 | `!no-unauthenticated` exclusion | 03-01 T1, 03-04 T2 | COVERED |
| RESEARCH | F-20 | websockets default proxy; `proxy=None` for loopback | 03-01 T2, 03-05 T2 | COVERED |
| RESEARCH | Patterns 1 to 12 | Dialect, run loop, pseudonymiser, writer, deletes, schema, enrich, Alembic, `/v1`, news job, test infrastructure, loopback server | 03-04, 03-05, 03-04, 03-05, 03-05, 03-03, 03-06, 03-03, 03-07, 03-08 and 03-12, 03-02, 03-05 | COVERED |
| RESEARCH | Spike Tool Design Brief (incl. S-13 AppView cross-check) | Recorder, analyzer, cursor, reconnect, AppView, storage probe | 03-01 T1, T2, T4 | COVERED |
| RESEARCH | Package Legitimacy Audit | One consolidated approval of the eight added packages | 03-01 T5 (owner), 03-02 T1 (precondition) | COVERED |
| RESEARCH | Security Domain (ASVS 1) | Threat patterns for this stack | the `<threat_model>` of every plan (T-03-01 to T-03-68; the former T-03-60 to T-03-64 are split over plans 03-09, 03-11 and 03-12) | COVERED |
| RESEARCH | Open Questions 10 to 16, 19 | `via`, OD-1, OD-2, OD-3, cadence, GNews wording, Developer Guidelines duties, digest | 03-01 T5, 03-03 T1 and T3, 03-05 T3 (erase), 03-10 T1 | COVERED |
| RESEARCH | Open Questions 17, 18, 20; assumptions A1 to A15 | Runner reachability, Windows spike run, User Intents proposal status, unverified Windows and CI behaviours | Manual-Only items below; Phase 6 verification | EXCLUDED (cannot be verified here; recorded as non-gating) |
| CONTEXT | D-01 to D-31, OD-1 to OD-3 | see the Decision Coverage table | see below | COVERED |
| CONTEXT | Deferred Ideas | Option C and D seeding, M2 merge, Replay or Snapshot, Mastodon, risk x velocity ranking, deep links, pending buffer, zstd, scheduling, DEMO_MODE rename, pre-commit hooks, observability | none | EXCLUDED (deferred by the owner; no plan implements them) |

---

## Decision Coverage

| Decision | Plan: task | Decision | Plan: task |
|----------|------------|----------|------------|
| D-01 | 03-01: 1, 2, 4 | D-17 | 03-01: 3, 5 (shown and explicitly confirmed); 03-02: 1; 03-04: checkpoint, 1; 03-05: 3 |
| D-02 | 03-01: 3, 5; every later plan (gate) | D-18 | 03-04: 2; 03-05: 1, 3; 03-06: 3 |
| D-03 | 03-01: 3, 4; 03-02: 1 | D-19 | 03-02: 1, 3; 03-03: 1 |
| D-04 | 03-01: 1, 4; 03-04: 3 | D-20 | 03-03: 1 |
| D-05 | 03-04: 1; 03-05: 2 | D-21 | 03-02: 1; 03-05: 1, 2 |
| D-06 | 03-04: 1; 03-05: 2 | D-22 | 03-06: 1, 2 |
| D-07 | 03-01: 2; 03-02: 1; 03-05: 2 | D-23 | 03-07: 1 to 3; 03-08: 3 |
| D-08 | 03-04: 1, 2; 03-06: 1 | D-24 | 03-07: 1 to 3; 03-08: 3 |
| D-09 | 03-04: 1; 03-05: 1 to 3 | D-25 | 03-03: 2; 03-07: 1 |
| D-10 | 03-05: 2, 3; 03-06: 3 | D-26 | 03-08: 1 to 3; 03-12: 2 |
| D-11 | 03-04: 3; 03-05: 2 | D-27 | 03-09: 1, 2; 03-11: 1, 2; 03-12: 1, 3 |
| D-12 | 03-03: 1; 03-04: 2; 03-06: 1; 03-07: 2 | D-28 | 03-02: 2; 03-03 to 03-08 (used) |
| D-13 | 03-04: 2 | D-29 | 03-03: 3; 03-12: 3; 03-10: 2 |
| D-14 | 03-03: 1; 03-05: 1; 03-06: 1, 2; 03-07: 2 | D-30 | 03-01: 2, 4; 03-02: 2; 03-05: 3; 03-10: 1 |
| D-15 | 03-05: 1 | D-31 | 03-02: 1; 03-03: 1; 03-04: 3; 03-07: 1; 03-09: 1; 03-12: 2 |
| D-16 | 03-03: 1; 03-05: 1; 03-06: 3 | OD-1 retention | 03-01: 3, 4, 5; 03-02: 1; 03-05: 1; 03-06: 3 |
| OD-2 merge | 03-01: 3, 4, 5; 03-02: 1; 03-03: 1; 03-07: 2 | OD-3 tracking | 03-01: 3, 4, 5; 03-02: 1; 03-04: 2; 03-05: 1, 2 (option B built and tested) |

---

## Expected edits to existing tests

Phase 1 and Phase 2 tests must keep passing with their assertions unchanged except for the rows below (the single list the verifier uses). Standing categories not listed row by row: new fixtures and helpers added to `tests/conftest.py`, new environment names in the scrub list, and import lines.

| # | Plan | File | Edit | Kind | Justification |
|---|------|------|------|------|---------------|
| 1 | 03-02 | `tests/test_dependency_groups.py` | PIN regex accepts an optional extras bracket; EXPECTED_SERVING gains sqlalchemy, psycopg, alembic, websockets | expected-value extended | four approved dependencies (the extras bracket is needed for `psycopg[binary]`) |
| 2 | 03-02 | `tests/test_no_hardcoded_credentials.py`, `tests/test_readme_env_table.py` | EXPECTED_ENV_NAMES grows by 36 names; the example-file count 10 becomes 46 | expected-value extended | new variables are added together with their code (Phase 2 row 7 precedent) |
| 3 | 03-02 | `pyproject.toml` pytest table | `addopts` gains `--strict-markers`; marker `requires_db` registered | config | D-28; the existing test only forbids `--cov` there |
| 4 | 03-03 | `tests/test_ci_workflow.py` | tests added for the PostgreSQL service, REQUIRE_DB, the Alembic steps and the image check; no existing assertion changes | additions only | D-29 "extended, not weakened" |
| 5 | 03-07 | `tests/test_v1_limits.py` | `test_no_registrars_means_no_v1_path_in_openapi` passes an explicit empty registrar list | one-argument edit | the default registrar list is no longer empty |
| 6 | 03-07 | `tests/test_openapi_golden.py` | paths below `/v1/` become a declared allowed addition | declared tolerance | D-23; golden file and pin untouched |
| 7 | 03-08 | none | the adapter keeps its defaults, every adapter, retry, error and settings test passes unedited | - | proved by running them |
| 8 | 03-09, 03-11, 03-12 | the retargeted (03-09), retired (03-11) and migrated (03-12) tests of the replacement maps in `03-09-SUMMARY.md`, `03-11-SUMMARY.md` and `03-12-SUMMARY.md` | route-level tests retargeted to probe `/v1` routes first, with the job-level replacements for the endpoint retry and error tests written before anything is deleted (03-09); then the inherently `/analyze` tests retired in ONE commit with their intent mapped, including the three settings tests that request the route (03-11); Settings tests move to NewsSettings and DATABASE_URL (03-12); the old golden comparisons are replaced by the Phase 3 golden with declared differences (03-11); `APP_MODULE` changes (03-09) | deliberate retirement | D-27, same discipline as plan 01-05; a collected-id diff proves nothing is dropped silently |
| 9 | 03-12 | `tests/test_ci_workflow.py`, `scripts/smoke_app.py` | docker probes move from `/analyze` to `/v1/stats` (500 not_configured) and `/analyze` (404) | probe retarget | the route is retired |
| 10 | 03-10 | `tests/test_ci_workflow.py`, `tests/test_coverage_config.py` | floor ratchet and timeout checks added; `fail_under` at least 96 | additions only | D-29 ratchet |

---

## Wave 0 Requirements

Test files and infrastructure created by the plans (all must exist before the phase gate):

- [ ] `scripts/bluesky_spike.py`, `scripts/spike_lib/`, `scripts/check_spike_ratified.py`; `tests/test_spike_tool.py`, `tests/test_spike_analysis.py`, `tests/test_spike_gate.py`, `tests/test_spike_template.py`, `tests/test_seed_domains.py`, `tests/test_recorded_fixture.py`; `src/truthtrail/data/recorded/*`, `src/truthtrail/data/seed_domains.txt`; `03-SPIKE.md`, `03-SPIKE-REPORT-TEMPLATE.md` (03-01)
- [ ] `src/truthtrail/core/policy.py`; `tests/test_policy.py`, `tests/test_policy_docs.py`; `tests/pg_cluster.py`, `tests/test_pg_fixture.py`, `tests/test_socket_guard.py`, `tests/test_db_url.py`, `tests/test_db_engine.py`; conftest additions (`requires_db` fixtures, socket guard, tracked engines, REQUIRE_DB floor); framework install `uv add` of the four pins (03-02)
- [ ] `tests/test_migrations.py`, `tests/test_db_constraints.py`, `tests/test_sql_parameterised.py`, `tests/test_readiness_database.py`; conftest `migrated_db_url`, `clean_db`; `alembic.ini` and the packaged migrations (03-03)
- [ ] `tests/test_cascade_violations.py`, `tests/test_pseudonym.py`, `tests/test_ingest_dialect.py`, `tests/test_ingest_normalise.py`, `tests/test_selection.py`, `tests/test_replay_source.py`, `tests/test_import_rules.py` (03-04)
- [ ] `tests/loopback_server.py`, `tests/live_smoke.py`, `tests/test_ingest_writer.py`, `tests/test_ingest_idempotency.py`, `tests/test_ingest_deletes.py`, `tests/test_jetstream_source.py`, `tests/test_ingest_run.py`, `tests/test_ingest_cli.py`, `tests/test_ingest_crash_resume.py`, `tests/test_no_pii_in_logs.py` (03-05)
- [ ] `tests/test_enrich_resolve.py`, `tests/test_enrich_properties.py`, `tests/test_enrich_db.py`, `tests/test_purge.py`, `tests/test_enrich_cli.py` (03-06)
- [ ] `tests/test_v1_meta_errors.py`, `tests/test_v1_outage.py`, `tests/test_v1_cache.py`, `tests/test_v1_cascades.py`, `tests/test_v1_tree_timeline.py`, `tests/test_v1_stats.py`, `tests/test_v1_openapi.py` (03-07)
- [ ] `tests/test_gnews_max_results.py`, `tests/test_news_topics.py`, `tests/test_news_job.py`, `tests/test_news_cli.py`, `tests/test_v1_news.py`; `src/truthtrail/data/news_topics.toml` (03-08)
- [ ] `tests/test_analyze_retired.py`, `tests/golden/openapi_phase3.json` (03-11); `tests/test_no_news_in_handlers.py` (03-12)
- [ ] `tests/test_docs_data.py`, `docs/data-and-ethics.md` (03-10)
- [ ] Tool configuration: `pyproject.toml` (markers, strict markers, coverage gate), `.github/workflows/ci.yml` (PostgreSQL service, migration steps, floor), `.gitignore` (`spike-output/`), `.env.example` lists

---

## Manual-Only Verifications

The first row is GATING (it blocks plans 03-02 to 03-12). All others are **NON-GATING**: they never block a plan, the phase gate or `/gsd-verify-work`; the verifier harvests them into the phase UAT (config `human_verify_mode: end-of-phase`). Non-gating does not mean passed: ROADMAP criteria 2 and 5 keep their CI-dependent parts 'pending human confirmation' until the Actions rows below are confirmed, and the verifier must list them as OPEN, never as passed.

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| **GATING:** ratify `03-SPIKE.md` (OD-1 retention, OD-2 merge, OD-3 tracked-root selection and bounds, the `via_uri` hedge, the dependency list, the one-way D-17 pseudonymisation scheme with its explicit token `pseudonym=d17`, review of the draft allowlist) | DATA-01 | Only the owner may decide; no agent output counts as ratification (D-02) | Read `.planning/phases/03-real-propagation-data/03-SPIKE.md`, answer at the plan 03-01 checkpoint; the executor records the reply verbatim and `scripts/check_spike_ratified.py` must then exit 0 |
| Owner runs the spike tool for 5 minutes on native Windows 11 and pastes the summary into the Windows block of `03-SPIKE.md` | DATA-01 (S-12) | The dev container is Linux (research A1, A2) | `uv run --no-project --python 3.13 --with websockets==17.2 python scripts\bluesky_spike.py probe`, then `... record --seconds 300 --out spike-output`, then `uv run --no-project --python 3.13 python scripts\bluesky_spike.py analyze --in spike-output --summary` |
| CI green on the pushed final commit: all seven jobs, including the tests job on the PostgreSQL 17 service container with the Alembic round trip and the DB-test floor | DATA-02, DATA-03 (SC2) | No runner or GitHub API for this repository here (research A3, A4) | After the push, open the Actions run for the final commit and read the jobs; apply the one-line fixes named in the plan SUMMARY if the first run fails |
| Docker image builds and the container answers `/health`, `/ready`, `/v1/stats` (500 not_configured in demo mode) and `/analyze` (404), runs non-root, ships the migration package | DATA-06 (SC5) | No Docker daemon here | The `docker` CI job, or `docker build -t truthtrail:ci .` then `docker run -d -e DEMO_MODE=true -p 8000:8000 truthtrail:ci` and `curl` the paths |
| Windows run of the test suite fast loop and of the collector replay against a local PostgreSQL | DATA-03 | Windows is not available here (research A1, A2) | `uv sync`, `uv run pytest -m "not requires_db"`, set `TEST_DATABASE_URL` or `TRUTHTRAIL_PG_BIN`, `uv run pytest tests/test_ingest_crash_resume.py`, `uv run python -m truthtrail.ingest run --replay packaged --max-seconds 30` |
| First live news-job run with the owner's own GNews key, then read `/v1/news` | DATA-06 | The container never calls the real GNews API (project rule) | Set `GNEWS_API_KEY` and `DATABASE_URL` in the PowerShell session, `uv run python -m truthtrail.jobs news --max-calls 2`, open `/v1/news` |
| Branch-protection required checks | D-29 | Repository setting, not visible in the repo | Confirm whether `copy-guard`, `gitleaks` and `tests` are required; names were not changed |
| Re-read the Bluesky terms, the Developer Guidelines and the GNews free-plan wording; confirm GitHub-hosted runners can reach the public Jetstream | DATA-01 (S-10), OPS-02 | Phase 6 verification items (the public URL, scheduled jobs) | Re-read the pages listed in `03-SPIKE.md` and record the result in its Terms section before the Phase 6 public deploy; test a scheduled workflow's egress in Phase 6 |
| Review the committed topic list (`news_topics.toml`) | DATA-06 | Editorial choice (D-26) | Read the list reproduced in the plan 03-08 SUMMARY |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 90 s for a task-level run
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
