# Phase 3: Real Propagation Data - Pattern Map

**Mapped:** 2026-10-18
**Files analyzed:** 62 (new or modified; 6 existing source files modified, 4 retired, rest new)
**Analogs found:** 54 in-repo analogs / 62. The 8 without an in-repo analog take their source from 03-RESEARCH.md (listed in "No Analog Found").

All analog paths below are git-TRACKED at HEAD `78bfdfb` (checked against `git ls-files`; no gitignored mirror paths are used). Line numbers refer to the current files. Files that do not exist yet are marked NEW. Nothing under `src/truthtrail/{db,ingest,enrich,jobs}`, `schemas/v1.py`, `core/policy.py`, `alembic.ini` or `scripts/bluesky_spike.py` exists.

**Gate (CONTEXT D-02):** only the spike group (03-01) may execute before the owner ratifies `03-SPIKE-DECISION.md`. Every file in groups B to J is blocked on it. Values that depend on OD-1 (retention), OD-2 (merge) and OD-3 (root selection and bounds) are read from `core/policy.py` and are PROVISIONAL until ratified. This map does not decide them.

**Secret handling:** never print or write a key. Tests use the word token `FAKE_TEST_KEY` and obviously fake DB URLs and secrets (marker style of `tests/test_settings.py:13-14`). `PSEUDONYM_SECRET` fixtures are labelled fake and are not 32-char hex.

## File Classification

| New / modified file | Role | Data flow | Closest analog | Match |
|---|---|---|---|---|
| **A. Spike (03-01)** | | | | |
| `scripts/bluesky_spike.py` | utility script (CLI, bounded) | streaming + batch | `scripts/smoke_app.py` (stdlib-only, exit codes) + `scripts/copy_guard.py:225-248` (`main(argv)->int`) | role-match |
| `tests/test_spike_tool.py` | test | file-I/O + subprocess | `tests/test_copy_guard.py:15-24` (importlib load of a script) + `tests/test_demo_fixture.py:98-125` | role-match |
| `.planning/phases/03-real-propagation-data/03-SPIKE-DECISION.md` | decision doc | n/a | `01-CONTEXT.md` / `02-VERIFICATION.md` style (front matter + dated evidence) | partial |
| `src/truthtrail/data/recorded/bluesky-<date>.jsonl` + `.manifest.json` | fixture data | static | `src/truthtrail/data/demo_analyze.json` + `scripts/generate_demo_fixture.py` | role-match (real, not synthetic) |
| `src/truthtrail/data/seed_domains.txt` | config data | static | `src/truthtrail/data/demo_analyze.json` (package-data location, D-22) | partial |
| `tests/test_recorded_fixture.py` | test | file-I/O | `tests/test_demo_fixture.py:24-95,98-162` + `tests/test_legacy_frozen.py` (sha256 pin) | exact role |
| `.gitignore` (add `spike-output/`) | config | n/a | itself (`.hypothesis/` block) | self |
| **B. Database foundation (03-02)** | | | | |
| `pyproject.toml` (4 deps, `requires_db` marker) | config | n/a | itself (`pyproject.toml:10-20,35-45`) | self |
| `uv.lock` | config | n/a | itself | self |
| `src/truthtrail/core/policy.py` | config (typed policy) | startup | `src/truthtrail/core/boot.py:57-100` (`BootSettings`) | exact |
| `src/truthtrail/core/config.py` (split key requirement, new fields) | config | startup | itself (`:37-103`) | self |
| `src/truthtrail/db/engine.py`, `db/url.py` | utility (factory) | request-response | `core/boot.py:100-` (`get_boot_settings` error-wrapping) + `services/gnews.py` (timeouts as named constants) | partial |
| `src/truthtrail/db/models.py` | model | CRUD | `src/truthtrail/schemas/models.py` (typed, `extra="forbid"`) ; SQLAlchemy shape from 03-RESEARCH Pattern 6 | partial |
| `alembic.ini`, `src/truthtrail/db/migrations/{env.py,versions/*}` | migration | batch | none (03-RESEARCH Pattern 8) | no analog |
| `src/truthtrail/db/__main__.py` (`migrate`) | CLI | batch | `scripts/generate_demo_fixture.py:138-167` | role-match |
| `src/truthtrail/api/app.py` (engine, `database` check) | app wiring | request-response | itself (`:40-109`) | self |
| `src/truthtrail/api/db_errors.py` (handlers) | handler registration | request-response | `src/truthtrail/api/problems.py:83-93,96-107,167-178` | exact |
| `tests/conftest.py` (PG fixtures, socket guard, `ENV_NAMES`) | test infra | n/a | itself (`:36-77`, `:140-154`) | self |
| `tests/test_migrations.py`, `tests/test_readiness_database.py`, `tests/test_db_constraints.py` | test | CRUD (real PG) | `tests/test_health_ready.py:54-126` + `tests/test_readiness_registry.py` | role-match |
| `tests/test_sql_parameterised.py` | test | file-I/O (AST) | `tests/test_no_legacy_imports.py:24-60` | role-match |
| **C. Ingest pure layer (03-03)** | | | | |
| `src/truthtrail/ingest/dialect.py`, `normalise.py` | service | transform | `src/truthtrail/services/gnews.py:46-70` (pydantic payload models, tolerant `extra="ignore"`) | role-match |
| `src/truthtrail/ingest/pseudonym.py` | utility | transform | none (03-RESEARCH Pattern 3) | no analog |
| `src/truthtrail/ingest/selection.py` | service | transform | `src/truthtrail/core/cascade.py:68-137` (pure functions, closed error type) | role-match |
| `src/truthtrail/ingest/source.py` (`ReplaySource`) | service | streaming | none in repo; `api/analyze.py:51-71` (fixture loader with label guard) for the refusal rule | partial |
| `tests/test_ingest_normalise.py`, `test_pseudonym.py`, `test_selection.py` | test | transform | `tests/test_char_risk_analyzer.py` (table tests) + `tests/test_cascade_properties.py` | role-match |
| **D. Collector (03-04)** | | | | |
| `src/truthtrail/ingest/writer.py` | repository | CRUD (batch upsert) | none (03-RESEARCH Pattern 4) | no analog |
| `src/truthtrail/ingest/run.py`, `__main__.py` | job loop + CLI | streaming | `services/gnews.py:98-190` (retry loop, injected clocks) + `scripts/smoke_app.py` (subprocess) | role-match |
| `src/truthtrail/ingest/source.py` (`JetstreamSource`) | service | streaming | `services/gnews.py` (bounded retries, key-free `_fail`) | role-match |
| `tests/test_jetstream_source.py` (loopback server) | test | streaming | `tests/test_retries.py` (fake clock, call counting) | role-match |
| `tests/test_ingest_idempotency.py`, `test_ingest_crash_resume.py` | test | CRUD + subprocess | `tests/test_settings.py:119-146` (subprocess, SYSTEMROOT) | role-match |
| `tests/test_no_pii_in_logs.py` | test | request-response | `tests/test_upstream_errors.py:337-362` (`caplog` no key/url) | exact role |
| **E. Enrich (03-05)** | | | | |
| `src/truthtrail/core/cascade.py` (+`find_order_violations`) | utility (pure) | transform | itself (`:68-137`) | self |
| `src/truthtrail/enrich/resolve.py`, `rollup.py` (pure) | utility | transform | `core/cascade.py:68-137` | exact |
| `src/truthtrail/enrich/apply.py`, `purge.py` (db) | repository | CRUD | none (03-RESEARCH Patterns 4, 7) | no analog |
| `tests/test_enrich_properties.py` | test | transform | `tests/test_cascade_properties.py` (Hypothesis, `ci` profile) | exact |
| `tests/test_enrich_db.py` | test | CRUD | `tests/test_cascade_properties.py` + PG fixtures | partial |
| **F. `/v1` API (03-06)** | | | | |
| `src/truthtrail/schemas/v1.py` | model | transform | `src/truthtrail/schemas/models.py:63-152` (`Meta`, `Problem`, `Literal[False]`) | exact |
| `src/truthtrail/api/v1_cascades.py`, `v1_stats.py` (registrars) | controller | request-response | `tests/test_v1_limits.py:25-44` registrar shape + `api/analyze.py:74-103` route decl | role-match |
| `src/truthtrail/api/v1.py` (`V1_REGISTRARS`) | route wiring | request-response | itself (`:1-29`) | self |
| `src/truthtrail/api/v1_cache.py` (optional, generalised TTL cache) | utility | request-response | `src/truthtrail/api/cache.py` | exact |
| `tests/test_v1_cascades.py`, `test_v1_openapi.py`, `test_v1_outage.py` | test | request-response | `tests/test_v1_limits.py`, `tests/test_openapi_contract.py:34-100` | role-match |
| **G. News job (03-07)** | | | | |
| `src/truthtrail/jobs/news.py`, `jobs/__main__.py` | job + CLI | batch / request-response (outbound) | `services/gnews.py` + `api/limits.py:68-90` (`UpstreamBudget`, replaced by DB ledger) | role-match |
| `src/truthtrail/services/gnews.py` (+`max_results`) | service | request-response | itself (`:198-301`) | self |
| `src/truthtrail/data/news_topics.toml` | config data | static | `src/truthtrail/data/demo_analyze.json` (location); `tomllib` use in `tests/test_dependency_groups.py:22-27` | partial |
| `src/truthtrail/api/v1_news.py` | controller | CRUD read | `api/analyze.py` (provenance) + F-group registrar | role-match |
| `tests/test_news_job.py`, `test_v1_news.py` | test | request-response | `tests/test_retries.py`, `tests/test_upstream_budget.py` | exact role |
| `tests/test_no_news_in_handlers.py`, `tests/test_import_rules.py` | test | static + subprocess | `tests/test_no_legacy_imports.py` (whole file) | exact |
| **H. Retire `/analyze` (03-08)** | | | | |
| `src/truthtrail/api/analyze.py`, `api/cache.py`, `UpstreamBudget` in `api/limits.py:68-90` | retire | n/a | n/a | n/a |
| `tests/golden/openapi_phase3.json` + `tests/test_openapi_golden.py` | test | transform | `tests/test_openapi_golden.py:1-97` | exact role |
| **I. CI, env, docs** | | | | |
| `.github/workflows/ci.yml` | CI | batch | itself (`:73-86` tests job; `:136-` docker job) | self |
| `tests/test_ci_workflow.py` | static CI-contract test | file-I/O | itself (`:14-20,53-108`) | self |
| `.env.example`, `tests/test_no_hardcoded_credentials.py`, `tests/test_readme_env_table.py` | config + test | n/a | themselves | self |
| `README.md`, `docs/*` | docs | n/a | itself; `scripts/copy_guard.py` | self |
| `scripts/smoke_app.py`, `Dockerfile`/`.dockerignore` | script / config | request-response | themselves | self |

## Pattern Assignments

### A. `scripts/bluesky_spike.py` (CLI, bounded, read-only)

**Analog:** `scripts/copy_guard.py` (CLI shape) and `scripts/smoke_app.py` (stdlib-only, short failure messages, never prints a body).

**CLI shape to copy** (`copy_guard.py:225-248`, `generate_demo_fixture.py:138-167`): `main(argv: list[str] | None = None) -> int`, `argparse`, `sys.stdout.write(...)`, `raise SystemExit(main())`, write files with `encoding="utf-8", newline="\n"` (`generate_demo_fixture.py:165`). Subcommands per RESEARCH "Spike Tool Design Brief": `probe`, `record`, `analyze`, `cursor-test`, `reconnect-test`, `appview-check`, plus S-8 helper.

**Safety rules to encode** (CONTEXT D-01): `--max-seconds` hard maximum 7200 (argparse `type` that rejects more), `--max-bytes`, HTTP 401/403 stops and reports with no retry and no substitute data, output only under git-ignored `spike-output/`, raw log gzip level 1 with `{"rx": <ms>, "f": <frame>}` wrapper, analysis output carries counts and rates only (never DIDs, handles, text).

**Difference from the analog:** `smoke_app.py:62` uses `ProxyHandler({})` to ignore ambient proxies for loopback. The spike must do the opposite: honour `HTTPS_PROXY` and `SSL_CERT_FILE` (RESEARCH F-20: `websockets` 17.2 reads them by default; do not pass `proxy=`), and never disable TLS verification. `urllib` for HTTP needs `# noqa: S310 - fixed https URLs` (ruff `S` is on for `scripts/`, only `tests/**` ignores it, `pyproject.toml:71-72`); subprocess calls need the `# noqa: S603 - fixed argument vector` style of `smoke_app.py:140,205`.

**Shared-function rule:** `derive`, `allowed`, canonicalisation and hash sampling are the same pure functions later moved to `ingest/selection.py` (RESEARCH brief). Plan 03-01 should write them in `scripts/` only if they can be moved by `git mv` unchanged; otherwise write them in `src/truthtrail/ingest/selection.py` first and import them from the script (the script already inserts `src` on `sys.path`, see `generate_demo_fixture.py:26-29`). This keeps D-02 intact because pure selection code touches no database.

**Test pattern** (`tests/test_spike_tool.py`): load the script with `importlib.util.spec_from_file_location` exactly as `tests/test_copy_guard.py:19-24`; run the CLI in a subprocess with `env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "", **{SYSTEMROOT}}` per `tests/test_demo_fixture.py:115-125`. Assert cap rejection (`--max-seconds 7201` exits non-zero), 403 stop (loopback server returning 403, one connect only), and a marker test that DID/handle/text markers in a hand-built tiny log never appear in analyzer output.

### A. Recorded fixture, scrubber and `tests/test_recorded_fixture.py`

**Analog:** `src/truthtrail/data/demo_analyze.json` + `tests/test_demo_fixture.py` + `tests/test_legacy_frozen.py` (sha256 pin).

- Location is inside the package (`src/truthtrail/data/recorded/`), the D-22 lesson already followed by `FIXTURE_PATH = Path(__file__).resolve().parents[1] / "data" / ...` (`api/analyze.py:46-47`); resolve from `__file__`, never CWD. `.dockerignore` excludes `*.md` only, so `.jsonl`/`.json` travel with `COPY src` (`Dockerfile:12`).
- Loader guard to copy (`api/analyze.py:51-71`): refuse at load time when labelling is wrong. `ReplaySource` raises on a manifest whose `source_mode != "recorded-real"`, mirroring `RuntimeError("demo fixture is not labelled synthetic")`. Add the reverse guard: the synthetic fixture path can never be passed to the events writer (test with the Phase 1 file).
- Generator discipline to copy (`generate_demo_fixture.py`): deterministic transform, `render()` then `--check` compares bytes, LF via `newline="\n"`. The scrub step is a deterministic function of the raw log, so `--check` equivalent is "re-cut from the raw log equals the committed file" (only runnable locally while the raw log exists; the committed test pins the sha256 instead).
- Scrub tokens: RESEARCH F-01 supersedes CONTEXT D-04's "base32 or counters". Use sequential left-padded counters in the real field names (`rkey`, `did`, `uri`), and name test constants `ROOT_URI_n`, never `*_KEY`. Run scratch gitleaks over the fixture before commit (RESEARCH "Scratch gitleaks over a candidate fixture").
- The credential backstop (`tests/test_no_hardcoded_credentials.py:16-25`) scans `.json` and `.md` but not `.jsonl`; `scripts/gitleaks_scan.sh` scans everything. The manifest is `.json`, so keep any key-like field names out of it.
- Tests to write (pattern: `test_demo_fixture.py:29-95`): manifest keys and `source_mode`, size <= 1.5 MB, pinned sha256, every did/rkey matches the counter grammar, no `cid`, no free text, no URL query or fragment, root frames present with all their children, a few delete/account frames, negative-control frames present.

### B. `core/policy.py` (typed, env-overridable policy)

**Analog:** `src/truthtrail/core/boot.py` (`BootSettings`, lines 57-100) and `core/config.py:37-52`.

**Pattern to copy:**
```python
class BootSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", env_ignore_empty=True, hide_input_in_errors=True,
    )
    cors_origins: Annotated[list[str], NoDecode] = []
    ...
def get_boot_settings() -> BootSettings:   # not cached; errors name the variable, never the value
    try: return BootSettings()
    except ValidationError as exc:
        error = exc.errors(include_input=False, include_url=False)[0]
        ...
        raise ConfigurationError(f"Invalid configuration ({name}: {rule})") from None
```
Apply to: every row of the CONTEXT parameter register. No required fields (so building the app never fails), defaults equal the recommended values, each OD-dependent default carries a `# PROVISIONAL (OD-n)` comment. `CASCADE_MERGE_POLICY` as `Literal["none", "claim_group", "derived"]`. Validators reject out-of-range values with fixed text (`"RETENTION_TEXT_DAYS must be >= 0"`), as `_check_origins` does. Test by copying `tests/test_settings.py` style: a table of bad values, message names the variable, never echoes the value (`test_settings.py:100-112`).

Add `BootSettings.model_config["env_file"] = None`-style scrub for the policy class in the autouse fixture (`conftest.py:63-66`), and every new env name to `ENV_NAMES` (`conftest.py:36-47`).

### B. `core/config.py` (settings split, D-27)

**Analog:** itself. `_key_required_unless_demo` (`config.py:83-89`) currently requires `GNEWS_API_KEY` globally; D-27 moves that requirement to the news job and requires `DATABASE_URL` unless `DEMO_MODE`. Keep: `SecretStr`, `hide_input_in_errors`, `_blank_key_is_missing` (key trimming/ASCII rule, tests `test_settings.py:176-265` stay valid), `get_settings()` re-raise `from None` (`config.py:93-103`). Add `database_url` normalisation (one function, accepts `postgresql://`, `postgres://`, `postgresql+psycopg://`) in `db/url.py`, not in `Settings`. Lifespan exit code 3 behaviour must survive (`test_settings.py:119-146`).

### B. `db/engine.py` (engine factory)

No in-repo analog for SQLAlchemy. Source: RESEARCH Pattern 9 "Engine factory". Repo conventions to apply: timeouts as module constants with a comment naming the decision (as `gnews.py:30-43`), no module-level engine (Phase 2 D-23), per-app state on `app.state`, `logging.getLogger(__name__)`, type-annotated for mypy strict. Disposal: lifespan disposes, tests register `engine.dispose` finalizers (F-09; `filterwarnings = error` at `pyproject.toml:38-45` fails the suite otherwise).

### B/F. `create_app` wiring and the `database` readiness check

**Analog:** `api/app.py:50-109` and `core/readiness.py:54-93`.

**Hook that exists** (`app.py:50-55`):
```python
def register_default_checks(registry: ReadinessRegistry) -> None:
    """Extension hook ... Phase 3 registers the ``database`` check and Phase 4 the ``model``..."""
```
and the call site (`app.py:77-78`): `app.state.readiness = registry; register_default_checks(registry)`.

**Change (RESEARCH F-11, additive):** `create_app(*, engine: Engine | None = None, cache_timer=..., v1_registrars=...)` and `register_default_checks(registry, get_engine)`. The check is a sync callable `-> bool`, fails closed (`False`) when no engine exists, otherwise `SELECT 1` plus `alembic_version == packaged head`. Registry already enforces `CHECK_TIMEOUT = 2.0` (`readiness.py:29`) and logs only the exception class name (`readiness.py:49-51`); the check must never format the exception. Register with `registry.register("database", check)`; the name is what `/ready` prints (`health.py:42-47`: `f"Not ready: {', '.join(failed)}."`).

**Pitfall for the planner:** registering `database` unconditionally makes every plain `client_factory()` app answer `/ready` 503 (no engine). That breaks `tests/test_health_ready.py:38-43,45-52` (`checks == {}`), `test_readiness_registry.py`, and the CI docker `Probe /ready` (`ci.yml`). D-27 says DEMO_MODE registers no database check. `create_app()` must not call `get_settings()` (`app.py:3-5`, `test_app_factory.py:51`), so the plan has to choose how the factory learns "no database mode": recommended is a `demo_mode`-style field on `BootSettings` (construction-time value, no required fields) or the injected `engine` argument. Tests that need a plain app then pass `demo_mode="true"` via `client_factory`.

**Lifespan** (`app.py:39-47`): keep the fail-fast comment and shape; replace `get_settings()` strictness by "`DATABASE_URL` required unless demo"; build the engine only when none was injected; `engine.dispose()` after `yield`. In demo mode keep loading the synthetic fixture (see H for where the loader moves).

### B/F. DB error handlers (`api/db_errors.py`)

**Analog:** `api/problems.py:83-93` (`_upstream_error_handler`: body + optional `Retry-After`) and registration at `:167-178`.

**Pattern to copy:**
```python
async def _upstream_error_handler(request, exc):
    body = problem_body(exc.status, exc.detail, exc.code, source_status="upstream_error", upstream=exc.upstream)
    headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after is not None else None
    return problem_response(exc.status, body, headers)
```
New handlers (RESEARCH Pattern 9, exact body verified there): `OperationalError` and `sqlalchemy.exc.TimeoutError` (pool exhaustion; not a `DBAPIError`) register separately; `problem_body(503, "The database is temporarily unavailable.", "database_unavailable", source_status="database_unavailable", upstream="database")` with `Retry-After`; statement/lock timeout (SQLSTATE 57014/55P03) -> code `database_timeout`. Log `type(exc).__name__` only. Other `DBAPIError` is NOT handled here: it falls to `CatchAllMiddleware` (`catchall.py:35-43`) and renders the generic 500 `internal_error`. Register through `register_problem_handlers` using decorator form and keep the ordering comment (`problems.py:170-178`). `UpstreamError.upstream` and `Problem.upstream` already exist, so no schema change; `Problem.source_status` is a free `str`.

**OpenAPI declarations:** `/v1` operations declare 422, 429, 500, 503 only. Build from `PROBLEM_RESPONSES` (`problems.py:50-80`) minus 502 and keep the `Retry-After` header block of the 503 entry. A 502 entry on a `/v1` operation must fail `test_v1_openapi.py`. `_problem_only_openapi` (`problems.py:143-164`) already strips the JSON media type for the codes it lists; no change needed.

### B. `tests/conftest.py` additions

**Analog:** itself.

- `ENV_NAMES` (`:36-47`) add: `PSEUDONYM_SECRET`, `COLLECTOR_CONTACT`, `TEST_DATABASE_URL`, `TRUTHTRAIL_PG_BIN`, `REQUIRE_DB`, every policy/news/ingest name from the CONTEXT register. The autouse `network_guard` already `delenv`s them (`:56-71`), which is what stops a shell `DATABASE_URL` from touching a real DB. Do not relax this.
- Socket guard (CONTEXT D-28): a second autouse fixture beside `network_guard`; allow loopback and AF_UNIX only. The `responses` mock covers `requests` only (`:62-70`). Exempt the PG provisioning session fixture (unix socket or `127.0.0.1`) and the loopback WebSocket server.
- Session fixtures: PG provisioning per RESEARCH Pattern 11 (own fixture, `mkdtemp`, `chown` + `runuser -u postgres --` when `os.geteuid() == 0`, `initdb -E UTF8 --locale=C`, unix socket, `CREATE DATABASE truthtrail_test_<random> ... TEMPLATE template0`, `alembic upgrade head`, drop with `FORCE`). Precedence: `TEST_DATABASE_URL`, else throwaway cluster, else one loud session-level failure (`REQUIRE_DB=1` makes absence a hard error).
- `requires_db` marker registered in `[tool.pytest.ini_options]` with `--strict-markers` added to `addopts` (`pyproject.toml:36`); `tests/test_dependency_groups.py:97-100` asserts `addopts` content, re-read it before editing.
- Engine tracking fixture with `request.addfinalizer(engine.dispose)` (F-09).
- `client_factory` (`:87-126`): already forwards `app_kwargs`; add `engine=` through `app_kwargs`, no signature change. Its default `gnews_api_key=FAKE_KEY` becomes irrelevant after D-27; keep it so retained tests do not churn.
- Hypothesis `ci` profile (`:21-32`) is deterministic and database-free; DB property tests set their own `@settings(max_examples=25, deadline=None, derandomize=True, database=None, suppress_health_check=[HealthCheck.function_scoped_fixture])` (RESEARCH Pattern 11).
- `subprocess_env` fixture (`:140-154`) already passes `SYSTEMROOT`; reuse it for ingest/enrich/jobs CLI subprocess tests (see Shared Patterns).

### B. Migration tests (`tests/test_migrations.py`)

No in-repo analog; sequence from RESEARCH Pattern 8: `upgrade head` -> `command.check` clean -> `downgrade base` leaves only `alembic_version` -> `upgrade head`; `get_heads()` length 1; packaged head equals DB head; CHECK constraints reject (inferred on non-repost, root with parent, text on non-root, self-parent). Credential rule (F-14): never `set_main_option("sqlalchemy.url", ...)`; `env.py` reads `config.attributes["connection"]` or `DATABASE_URL`. Test the error path with a URL containing `%` and assert the credential is absent from the exception text.

### B/E. SQL hygiene test (`tests/test_sql_parameterised.py`)

**Analog:** `tests/test_no_legacy_imports.py:24-60`: walk `src/truthtrail/**/*.py` with `ast`, with a negative control function (`test_walker_flags_forbidden_imports`, `:63-77`). Forbid `JoinedStr` (f-string) and `%`/`.format` arguments reaching `text(...)`, `execute(...)`, `exec_driver_sql(...)`. Also assert `MIN_FILES`-style floor so the walk cannot go blind (`:23` `MIN_FILES = 8`). Ban `date_trunc`/`extract` (F-15) in the same walk.

### C. Ingest normaliser and dialect

**Analog:** `services/gnews.py:46-70` for tolerant payload validation (`ConfigDict(extra="ignore")`, `_NonEmptyStr`, `AwareDatetime`) and `_fail` semantics (log codes only). Tolerance rules from RESEARCH Pattern 1: never require `cid`; strict on `did`, `rkey`, `collection`, `operation`, `time`/`witnessedAt`, parseable `createdAt`; unknown `embed.$type` means no quote and no card, never an exception; edge targets only for `app.bsky.feed.post` (F-08). Counting by reason replaces raising: return a `Control`/drop reason, as `gnews._fail` maps every failure to one typed outcome. All dialect-specific names (`witnessedAt`, `time_us`, `cursor`) live in `ingest/dialect.py` only.

**Test pattern:** table tests from one real recorded frame per shape, like `tests/test_char_risk_analyzer.py` (parametrised rows). Frames come from the recorded fixture, not hand-written; constructed delete/account frames in tests are built from a real delete shape and named `constructed_*` (CONTEXT D-04).

### C. `ingest/selection.py` and `core/cascade.py` additions

**Analog:** `core/cascade.py` (pure functions, standard-library-only, one closed error type, messages name ids only). `selection.py` imports nothing from `db/`, `api/` or `jobs/`. Counters by refusal reason are returned, not logged per event.

`find_order_violations` (D-08) goes beside `validate_cascade` (`cascade.py:123-137`) and reuses `_index`/`_depths` (`:62-100`) but must not raise on a violation:
```python
def validate_cascade(events):            # raises on first violation: fixtures
    by_id = _index(events); _depths(by_id)
    for event in by_id.values():
        parent = by_id.get(event.parent_event_id) if event.parent_event_id is not None else None
        if parent is not None and parent.observed_at > event.observed_at:
            raise CascadeError(f"event {event.event_id} is observed before its parent")
```
New function returns the violating `event_id`s (sorted) and counts; cycles still quarantined by the caller (enrich), because `_depths` raises `CascadeError` on a cycle (`:84-85`). Existing signatures unchanged. `tests/test_cascade_gate.py:155` asserts `core/cascade.py` imports only the standard library: keep it so.

### C. `ingest/pseudonym.py`

No analog. Source: RESEARCH Pattern 3 (verified). Repo conventions: `SecretStr` held in settings, `len(secret) >= 32` check at start raises `ConfigurationError` with fixed text and `from None` (see `config.py:93-103`), never in exception text. API process must not import it (`test_import_rules.py`).

### D. Writer, run loop, CLI

**Writer:** no analog; SQL from RESEARCH Pattern 4 (one transaction, inserts then tombstones then checkpoint, `GREATEST` on cursor, every row dict has identical keys). Core statements only.

**Run loop and `JetstreamSource`:** analog `services/gnews.py` retry loop (`gnews.py:98-190` by line region; see the Phase 2 map's description at 02-PATTERNS.md "gnews.py"). Copy: injectable `sleep`, `monotonic`, `jitter` keyword args defaulting to real functions (`# noqa: S311` on `random.uniform`), named constants for bounds, per-attempt log line with attempt, code and status only, exception order `Timeout` before `ConnectionError` before `RequestException` translated to websockets equivalents (`InvalidStatus` 401/403 fatal, 400 classified from JSON body, `ConnectionClosed` 1009 = `oversize_frame` fails the run loudly, F-04). Backoff `random.uniform(0, min(60, 2**attempt))` (RESEARCH Pattern 2). Graceful stop on bounds and `KeyboardInterrupt` only (no POSIX signals, D-10).

**CLI exit codes:** follow `smoke_app.py` docstring convention (exit codes documented at the top), and `test_uvicorn_exits_on_missing_key` precedent of exit code 3 for configuration (`test_settings.py:119-146`). 0 = every normal stop including a reached bound; non-zero = configuration, source failure after 8 consecutive failures, or database failure. Run row stores `status` and error class only.

**Loopback WebSocket server tests:** RESEARCH Pattern 12 (`websockets.asyncio.server.serve`, `process_request` for refusals, `proxy=None` mandatory). Test structure copied from `tests/test_retries.py`: fake clock fixture (`fake_clock`), call counting (`len(mock_gnews.calls)` becomes a handler-side counter), assert bounded attempts and no real sleep (`no_real_sleep` autouse fixture at `conftest.py:73-77` patches `gnews._sleep`; add the equivalent seam for the ingest backoff).

**Crash-resume test:** copy `test_uvicorn_exits_on_missing_key` structure (`test_settings.py:119-146`): `subprocess.run([sys.executable, "-m", "truthtrail.ingest", "run", ...], env=..., timeout=60)`, env built from `subprocess_env` plus `TEST_DATABASE_URL`-derived `DATABASE_URL`, `PSEUDONYM_SECRET` (fake), `PYTHONPATH` with `src`. For the kill: `subprocess.Popen`, poll the `ingest_checkpoints` table, `proc.kill()` (works on Windows), rerun, compare projection with an uninterrupted run. Never `os.kill(SIGINT)`.

**Key-free logging test (`tests/test_no_pii_in_logs.py`):** copy `tests/test_upstream_errors.py:337-362` (`caplog.set_level`, run, assert marker not in `caplog.text`). Markers: a fake DID, handle, post text, URL, and `PSEUDONYM_SECRET` value; assert absence in logs, run summary, `ingest_runs.counters`, and `/v1` bodies.

### E. Enrich

**Analog:** `core/cascade.py` (pure, deterministic sort key `(observed_at, depth, event_id)`, `:96-106`) and `tests/test_cascade_properties.py` (Hypothesis, `ci` profile). `enrich/resolve.py` and `rollup.py` import only `core/cascade` and the standard library (import-rule test D-31). Pass the URI key as `event_id` so ties break on it (CONTEXT code_context).

**Property test:** RESEARCH Pattern 7 is the template (strategy biased so parents fall inside the set; conflicting duplicates; `st.permutations`). Keep the three mutants as `pytest.raises(AssertionError)` tests so the guard cannot rot. Settings come from the repository's `ci` profile; do not re-declare 200 examples inline. DB layer test: 25 examples, `TRUNCATE` at the start of each example, idempotence (second enrich changes nothing).

**Write-back:** one transaction per cascade (`engine.begin()`), `as_of` passed in explicitly (no `datetime.now()` inside the resolver; the repo already uses `datetime.now(UTC)` only at the edge, `api/analyze.py:113`).

### F. `schemas/v1.py`

**Analog:** `schemas/models.py:63-93` (`Meta`) and `:106-133` (`Problem`).

**Pattern to copy:**
```python
class Meta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    synthetic: bool = Field(description=...)
    data_as_of: AwareDatetime = Field(description=...)
    source_status: Literal["ok", "empty", "fixture"] = Field(description=...)
...
    synthetic: Literal[False] = Field(default=False, description="Always false: ...")   # Problem
```
New `V1Meta`: `synthetic: Literal[False]`, `data_as_of: AwareDatetime | None`, `source_status: Literal["ok","empty","stale"]`, `source_mode: Literal["live","replay"]`, optional `observed_since`. It must be a NEW model: the existing `Meta` has a required non-null `data_as_of` and `source_status` literal including `fixture` (RESEARCH Pattern 9). Every response model uses `extra="forbid"`, `Field(description=...)` on every field, `X | None` not `Optional` (ruff UP). Descriptions carry the caption "Observed subset of public Bluesky posts, as of the stated time" and "flag for human review" (copy guard scans every OpenAPI string, `copy_guard.py:150-165`; no "detects", "AI-based", "verified true").

**No `risk`, no `claim_scores`, no `synthetic: true` branch** in any `/v1` response (CONTEXT scope). Test: walk the OpenAPI component names and property names and assert none is `risk` or `risk_method` under `/v1` models (the legacy `LiveResult` still defines them for the fixture schema until Phase 6).

### F. `/v1` registrars

**Analog:** the probe registrars in `tests/test_v1_limits.py:25-44` (the exact shape) and the route declaration in `api/analyze.py:74-103`.

```python
def probe_item(router: LimitedRouter) -> None:
    @router.get("/items/{item_id}")
    def item_route(request: Request, item_id: str) -> dict[str, str]:
        return {"id": item_id}
```
Rules (from `limits.py:47-65`): handler declares `request: Request` (slowapi raises at registration otherwise); route function names unique within a module (bucket key is module + function name, `key_style="endpoint"`); handlers are sync `def`; declare `response_model=` and `responses={...}` from the `/v1` subset of `PROBLEM_RESPONSES`; `summary=` wording passes the copy guard. Append the registrar functions to `V1_REGISTRARS` (`v1.py:16`). Do not add `@limiter.limit` (the router applies it). DB session via a sync `Depends` that yields a short-lived connection from `request.app.state.engine`; `statement_timeout` set per session (5 s API).

**Keyset pagination:** cursor encoding and malformed-cursor 422 as verified in RESEARCH Pattern 9 (`AfterValidator` raising `ValueError`, 422 problem+json via `_validation_error_handler`, `problems.py:110-122`). `limit` uses `Query(ge=1, le=100)`.

**Caching (optional):** if kept, generalise `api/cache.py` (`TTLCache` + one lock, single-flight `Future`, success-only store, injected `timer`, `cache.py` lines 1-100), key on data version (`data_as_of`), per-app on `app.state`, and keep the "limit before cache" ordering comment from `analyze.py:90-93`. Do not import `AnalyzeResponse`; make the value type generic. If the planner drops the cache, delete `api/cache.py` in H without replacement and say so in the replacement map.

**Tests:** copy `tests/test_v1_limits.py` for 429 on a `/v1` route and `tests/test_openapi_contract.py:34-100` for "every operation has typed 2xx and problem+json errors". Add: walk OpenAPI, every `/v1` operation declares exactly {200, 422, 429, 500, 503}, `Retry-After` header on 503 and 429, content type `application/problem+json`. Provenance assertion helper modelled on `test_provenance_demo.py:259-` (`test_every_response_carries_provenance`) rewritten over every `/v1` route.

### G. News job

**Analog:** `services/gnews.py` (reused) and the retired `UpstreamBudget` (`limits.py:68-90`) for the arithmetic idea (budget before the call, 503 when exhausted, `Retry-After`), replaced by a DB ledger: `news_fetches` row committed BEFORE the call, 24 h moving count under an advisory lock (RESEARCH Pattern 6/10), outcome updated after. Injected clock for tests, as `UpstreamBudget`/`cache_timer` already do.

**Adapter changes (additive):** `fetch_news(query, api_key, *, max_results=10)` sends `max` (today fixed at 1: `params={"q": query, "lang": "en", "max": 1}`); keep `X-Api-Key` header-only, `allow_redirects=False`, `TIMEOUT`, `BACKOFFS`, `BUDGET`, `_fail`. F-13: a 403 (`upstream_forbidden`, daily quota) stops the whole run like a 503; sleep >= 1.1 s between calls (inject the sleep). Job error policy: 503 `UpstreamError` stops the run; 502 records a failed topic and ends non-zero (CONTEXT D-26).

**Key scope:** `GNEWS_API_KEY` is read only by `jobs/news.py`. Use `Settings` for this entrypoint only, or a small `NewsSettings(BaseSettings)` copying the `Settings.model_config` block (`config.py:37-44`) and `_blank_key_is_missing` (`:56-81`).

**Topics file:** `news_topics.toml` parsed with `tomllib` (as `tests/test_dependency_groups.py` does for `pyproject.toml`); validation test: <= 20 topics, each <= 200 chars, no personal-name heuristics beyond the plan-summary review.

**Tests:** copy `tests/test_retries.py` / `tests/test_upstream_errors.py` structure: `mock_gnews.get(gnews_url, json=gnews_payload(gnews_article()), status=...)`, `len(mock_gnews.calls)`, `request.headers["X-Api-Key"]` (`test_settings.py:24-34` shows the key-only-in-header assertion). Add `max` param assertion in place of the old `set(call.request.params) == {"q","lang","max"}`.

**"No handler can call the news API" proof (3 layers, RESEARCH Pattern 10):** (1) AST import closure test, copy `tests/test_no_legacy_imports.py:24-60` including its negative control; (2) fresh interpreter, copy `test_importing_the_app_loads_no_legacy_module` (`:80-97`) with `FORBIDDEN = {"requests","urllib3","websockets","zstandard","truthtrail.services.gnews"}` and `PYTHONPATH` = `src` only (`_serving_env`, `:75-78`); (3) dynamic sweep calling every GET route with `fetch_news` patched to fail and `responses` rejecting GNews. NOTE: this is red until H removes `api/analyze.py` (today `api/analyze.py:23,28` import `services.gnews`); mark it last-plan or add it as an xfail(strict) removed in H.

### G. `/v1/news` provenance

Copy the `Meta` pattern with `data_as_of` = last successful fetch per topic (not response time). `source_status` `empty` when the topic has no stored row.

### H. Retiring `/analyze` (03-08)

Remove: `src/truthtrail/api/analyze.py`, `src/truthtrail/api/cache.py` (unless generalised in F), `UpstreamBudget` and `UPSTREAM_BUDGET` from `api/limits.py` (`:24-30`, `:68-90`; the `limits`/`math`/`time` imports and `UpstreamError` import become unused: ruff F401), `app.state.analyze_cache` and `app.state.upstream_budget` (`app.py:83-84`), `include_router(build_analyze_router(...))` (`app.py:85`), `RATE_LIMIT_ANALYZE` setting and env name (`config.py:52`, `.env.example`, `EXPECTED_ENV_NAMES`, README). `APP_DESCRIPTION` (`app.py:29-36`) describes the keyword-baseline endpoint and must be rewritten (copy guard scans it).

**Must relocate, not delete:** `load_demo_fixture` and `FIXTURE_PATH` live in `api/analyze.py:46-71` and are used by the lifespan (`app.py:46-47`) and by retained tests (`test_cascade_gate.py`, `test_provenance_demo.py`, `conftest.py:33-34` `APP_MODULE`). D-27 keeps the fixture and the cascade-gate test. Move them (suggested: `truthtrail/data/demo.py`, not under `api/`) and retarget `APP_MODULE` and the string patch targets via the single constant, as 02-PATTERNS did for `main`.

**Golden OpenAPI:** analog `tests/test_openapi_golden.py` (whole file). Reuse its mechanics (pinned sha256, `phase_view()` removing only declared additions, "only declared additions exist", `Problem.synthetic` const exception). For Phase 3: dump `tests/golden/openapi_phase3.json` from the final code, pin its sha256, and declare the permitted diff against the Phase 2 document explicitly: `/analyze` removed, `/v1/*` paths added, `/v1` 429/503 responses. Keep `openapi_phase1.json` in place unchanged (its sha is pinned by `GOLDEN_SHA256`; the file is an immutable historic artefact) but retire its two tests that assert `list(paths) == ["/analyze"]` and Phase 1 contract preservation (`test_openapi_golden.py:63-97`), recorded in the replacement map.

### I. `ci.yml`

**Analog:** itself. Keep the header comment style and update the job count if a job is added (`ci.yml:1-3`), `permissions: contents: read`, `concurrency`, SHA-pinned actions with `# vX.Y.Z` comments, `persist-credentials: false`, `timeout-minutes` integer, gitleaks job byte-identical.

**Postgres service on the `tests` job (`ci.yml:73-86`):**
```yaml
  tests:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    services:
      postgres:
        image: postgres:17.<n>-bookworm@sha256:<digest resolved at planning time>
        env:
          POSTGRES_PASSWORD: ci-throwaway-password
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U postgres" --health-interval 5s --health-timeout 5s --health-retries 10
    env:
      TEST_DATABASE_URL: postgresql+psycopg://postgres:ci-throwaway-password@localhost:5432/postgres
      REQUIRE_DB: "1"
```
Credential-backstop constraint (`test_no_hardcoded_credentials.py:14-16`): the regex needs a quoted value of 16+ characters after `password|secret|token|api_key` and `:`/`=`; YAML unquoted values do not match, and `.yml` is scanned. Keep service credentials unquoted or under 16 chars and name them throwaway. Do not use `secrets.` (`test_no_secrets_are_referenced`, `test_ci_workflow.py:79-80`). Re-resolve the image digest with the registry API at planning/execution time (A3 in RESEARCH; Hub returned 429 once).

**Migration steps** (D-29), run with `DATABASE_URL` pointing at a dedicated empty database created in an earlier step (never the pytest DB): `uv run --locked alembic upgrade head`, `alembic downgrade base`, `alembic upgrade head`, `alembic check`. Either put them in the `tests` job or add a job `migrations` copying the job skeleton at 02-PATTERNS "Job skeleton". If a job is added, update `EXPECTED_JOBS` (`test_ci_workflow.py:16`), the `checkouts == len(EXPECTED_JOBS)` assertion (`:74`), and the uv-install job list (`:111`). Also add the executed-DB-tests floor step (`pytest -m requires_db --collect-only -q | tail`, count above a floor).

**Docker job:** keeps `DEMO_MODE=true` (`ci.yml` docker steps). The `Probe /analyze` step greps `"synthetic":true` (`ci.yml`, and `test_ci_workflow.py:139-146` asserts `/analyze` and `"synthetic":true` are in the job text). After H, `/analyze` is 404: replace the probe with `/v1/stats` expecting 500 `not_configured` (D-27) or drop the synthetic probe, and update that test and `scripts/smoke_app.py:check_analyze` (`:149-`, docstring `:5-8`). Add the "migration package importable in the image" check inside the existing `docker exec ... python -I -c` step pattern (`ci.yml` last docker steps). `pip-audit` job needs no change (it exports the whole lock).

### I. `tests/test_ci_workflow.py` (static CI-contract tests)

**Analog:** itself. Extend, do not weaken (CONTEXT D-29): add tests in the existing style `_jobs()`, `_steps()`, `_run_text()`:
- `test_tests_job_has_a_pinned_postgres_service`: `services.postgres.image` matches `r"^postgres:\d+\.\d+(-[\w.]+)?@sha256:[0-9a-f]{64}$"`, has `options` with `--health-cmd`.
- `test_tests_job_requires_the_database`: env has `REQUIRE_DB == "1"` and `TEST_DATABASE_URL`.
- `test_alembic_round_trip_steps`: `_run_text` contains `alembic upgrade head`, `downgrade base`, `alembic check` in that order.
- Update `test_docker_job_builds_runs_and_probes_the_image` (`:136-146`).

### I. `.env.example`, credential and README tests

**Analog:** itself. Format is a comment line plus blank `NAME=` per variable (`.env.example`); `tests/test_no_hardcoded_credentials.py:80` compares the file's names to `EXPECTED_ENV_NAMES` by set equality, and `:77-79` requires `[A-Z][A-Z0-9_]*=` lines only. `tests/test_readme_env_table.py:41-43` asserts `len(_env_names()) == 10` and `:46-48` that every name appears in the README. New names to add in all four places (`.env.example`, `EXPECTED_ENV_NAMES`, `conftest.ENV_NAMES` where scrub applies, README): `PSEUDONYM_SECRET`, `COLLECTOR_CONTACT`, the policy/ingest/news names from the CONTEXT register that are env-overridable (planner decides which stay code-only), `TEST_DATABASE_URL` and `TRUTHTRAIL_PG_BIN`/`REQUIRE_DB` (test-only: document in the README; list in `.env.example` only if the planner wants one list; if listed the three sets must stay equal). Removing `RATE_LIMIT_ANALYZE` changes the count. Update `len(...) == 10` to the new count in the same commit. The `# Optional until Phase 3.` comments on `BLUESKY_*` and `DATABASE_URL` must be rewritten: `DATABASE_URL` becomes required unless `DEMO_MODE=true`; `BLUESKY_HANDLE`/`BLUESKY_APP_PASSWORD` stay unused and say so.

### I. README and docs

**Analog:** itself plus `tests/test_readme_env_table.py:15-24` (`REQUIRED_STRINGS`: "flag for human review", "uv sync", "winget", "uvicorn main:app", "--no-proxy-headers", "/health", "/ready", "/v1") and `scripts/copy_guard.py` (README must match `flag ... for human review`). Add: spike tool Windows commands (D-30), three test-DB routes, collector/enrich/purge/news commands, limitations (repost star, allowlist bias, pseudonymised not anonymised, retention windows, deletes lag). Run `python scripts/copy_guard.py` after editing. LF line endings (`.gitattributes`).

## Existing tests that must change when `/analyze` is retired or reduced

Replacement-map pattern: `.planning/phases/01-secure-honest-foundation/01-05-SUMMARY.md` (deliberate retirement listing each test and where its intent now lives). Never delete silently. The 10 strict-xfail characterisation tests (`tests/test_char_risk_analyzer.py`, `tests/test_char_simulator.py`), `test_demo_fixture.py`, `test_legacy_frozen.py`, `test_no_legacy_imports.py` and `test_cascade_gate.py`'s unit tests stay (CONTEXT D-27).

| Test file | `/analyze` coupling | Action |
|---|---|---|
| `tests/test_cache.py`, `tests/test_cache_unit.py` | `AnalyzeCache`, `X-Cache` on `/analyze` | Retire. Intent moves to a `/v1` cache test only if F keeps a cache (generalise `test_cache_unit.py` against the new class); otherwise retire with no replacement and record it |
| `tests/test_upstream_budget.py` | `UpstreamBudget`, `app.state.upstream_budget` | Retire. Replaced by news-ledger tests (`test_news_job.py`): daily budget, per-run cap, min refresh, injected clock |
| `tests/test_provenance_demo.py` (16 uses) | live/empty/demo branches of `/analyze`; patches `"truthtrail.api.analyze.load_demo_fixture"` (`:160`), `"...FIXTURE_PATH"`, `importlib.import_module("truthtrail.api.analyze")` (`:178`) | Retire route tests. Keep and retarget fixture-label tests (`test_demo_mode_refuses_unlabelled_fixture` idea) onto the relocated loader. Provenance-on-every-response intent moves to `/v1` tests |
| `tests/test_cascade_gate.py` (`:75,98,112,123,132`) | request tests through `/analyze`; patches `truthtrail.api.analyze` | Keep the pure-fixture and lifespan tests, retarget the module name via `APP_MODULE`; the "request gets the generic 500" test (`:104`) moves to a `/v1` route in demo mode or is retired with a note |
| `tests/test_cors.py` (13 uses) | all CORS behaviour exercised via `/analyze` | Retarget to a probe route through `app_kwargs={"v1_registrars": [probe]}` exactly as `test_v1_limits.py:56-60`; the 500 and 429 CORS cases keep their assertions |
| `tests/test_rate_limit.py` (`:36,108,156,184`) | limits `/analyze`; OpenAPI `paths["/analyze"]...["429"]` | Retarget to probe `/v1` routes; `:108` (invalid query not counted?) must be re-examined: the limiter counts before validation, assert that on a probe with a validated parameter |
| `tests/test_openapi_contract.py` (`spec["paths"]["/analyze"]`, `:31,59,94,111-151`) | whole file assumes one operation | Rewrite over `/v1` operations; `test_query_parameter_is_constrained` and `test_analyze_200_is_analyze_response` retire; description-honesty test (`:146`) repoints at the new `APP_DESCRIPTION` |
| `tests/test_openapi_golden.py` | pinned Phase 1 sha, `paths == ["/analyze"]`, Phase 1 contract preserved | Replace with the Phase 3 golden (see H) |
| `tests/test_request_validation.py` | query-validation tests (`:37-96`), `main.analyze_risk` patch (`:142`), not_configured (`:121`) | Retire query tests (replacement: `/v1` limit/cursor 422 in `test_v1_cascades.py`); keep 404/405 problem+json (`:96,108`) retargeted to `/v1`; `test_unexpected_error_is_generic_500` retargets to a registrar that raises |
| `tests/test_retries.py` | 27 adapter-direct tests stay; 4 endpoint tests (`:347,369,386,456`) | Keep adapter tests untouched; move the 4 endpoint tests to the news job (job stops after bounded attempts) |
| `tests/test_upstream_errors.py` | `client.get("/analyze")` at `:16-42` and endpoint-mapped parametrisation (`:231`) | Keep adapter tests (`:44`, `:298-401`); the 502/503 mapping tests re-express through the job outcome and `UpstreamError` fields |
| `tests/test_settings.py` (`:28,48,119-146,215,262` etc.) | missing key fails startup; `test_key_sent_only_in_header` via `/analyze`; `test_uvicorn_exits_on_missing_key` expects `"GNEWS_API_KEY"` in output | Settings split: missing `DATABASE_URL` (no demo) fails startup with exit 3 and names `DATABASE_URL`; key-in-header test calls `fetch_news` or the job directly; keep key-trimming/BAD_KEYS tests that hit `Settings`/`fetch_news` (`:176-250`); retire the three that hit `/analyze` (`:215,262` and `test_malformed_key_without_lifespan_is_500_not_configured`) |
| `tests/test_app_factory.py:27` | asserts `"/analyze" in _route_paths(first)` | Assert `/health`, `/ready`, `/v1/...` instead; `:51` (strict settings read only at startup) must still hold |
| `tests/test_network_guard.py:20-31` | `test_mocked_gnews_reaches_real_handler` via `/analyze` | Retarget to the adapter or news job; keep `test_unmocked_request_is_blocked` and `test_env_is_scrubbed` |
| `tests/test_proxy_headers_server.py:59,106` | real uvicorn subprocess with `DEMO_MODE=true`, GETs `/analyze?query=spoof` to read 429s | Hit a `/v1` data route (in demo mode it answers 500 `not_configured` but is still limited first by `LimitedRouter`), or start with a test DB |
| `tests/test_ci_workflow.py:139-146` | requires `/analyze` and `"synthetic":true` in docker job text | Update with the CI change (see I) |
| `tests/test_v1_limits.py` `test_no_registrars_means_no_v1_path_in_openapi` (`:122-129`) | calls `client_factory()` expecting no `/v1` paths; once `V1_REGISTRARS` is populated it fails | Pass `app_kwargs={"v1_registrars": []}` |
| `tests/test_health_ready.py`, `tests/test_readiness_registry.py` | `checks == {}` on a default app | See B: plain apps need demo/no-database mode or an injected engine |
| `tests/test_readme_env_table.py:41-43`, `tests/test_no_hardcoded_credentials.py:19-25,80`, `tests/test_dependency_groups.py:10-22` | exact name count / exact `EXPECTED_SERVING` pin set | Update in the same commit as `.env.example` and `pyproject.toml`; `EXPECTED_SERVING` gains `sqlalchemy`, `psycopg[binary]` (check how the test strips extras), `alembic`, `websockets` at the exact pins resolved at plan time; the `uv.lock` package-count assertions, if any, move with it |
| `tests/test_container_files.py:153-157` | forbids `KEY|SECRET|...|DEMO_MODE` in Dockerfile `ENV`/`ARG` | Unchanged; `PSEUDONYM_SECRET` and `DATABASE_URL` must never be baked into the image |
| `scripts/smoke_app.py` (`check_analyze`, docstring) | probes `/analyze` and `X-Cache` | Retarget to `/health`, `/ready`, and a `/v1` `not_configured` check |

## Shared Patterns

### Problem+json for every new error path
**Source:** `core/errors.py:45-66` (`problem_body`, `problem_response`) consumed by `api/problems.py`.
**Apply to:** DB 503s (`database_unavailable`, `database_timeout`), `/ready` 503 (existing), `/v1` 422/429/500, news-job output, any new `LimitedRouter` rejection. Never a bare `JSONResponse` or `HTTPException(detail=...)`. Registration order: dedicated handlers before the generic `StarletteHTTPException` handler (`problems.py:170-178`).
```python
body = problem_body(503, "The database is temporarily unavailable.", "database_unavailable",
                    source_status="database_unavailable", upstream="database")
return problem_response(503, body, {"Retry-After": str(retry)})
```

### Provenance members on every response
**Source:** errors: `core/errors.py:54-58` (`"synthetic": False, "source_status": ..., "data_as_of": None` always last). Success: `schemas/models.py:63-82` pattern -> new `V1Meta` (F).
**Apply to:** every `/v1` success body (`meta.synthetic: false`, `data_as_of` = stream time of last committed checkpoint, `source_status` in ok/empty/stale, `source_mode` live/replay, plus orphan/disconnected/overflow/gap counts that travel with a cascade). `/health` and `/ready` 200 bodies stay operational (no `meta`). A Bluesky outage surfaces as `stale`, never a 502 (the API never calls Bluesky).

### Key-free, URL-free, PII-free logging
**Source:** `services/gnews.py` `_fail` (log code and upstream status only, `raise ... from None`), `core/readiness.py:49-51` (class name only), `api/catchall.py:39` (`type(exc).__name__`). Module logger: `logger = logging.getLogger(__name__)`.
**Apply to:** collector, enrich, news job, DB error handlers, engine factory, Alembic wrapper (F-14). Pseudonym prefixes of at most 8 chars are the only identifiers allowed in logs. Tests assert absence with `caplog` as in `tests/test_upstream_errors.py:337-362`.

### Settings: `SecretStr`, no echo, fail fast
**Source:** `core/config.py:37-103`, `core/boot.py:57-100`. `DATABASE_URL`, `PSEUDONYM_SECRET`, `COLLECTOR_CONTACT` are `SecretStr`/operator data; error messages name the variable and the rule, never the value, re-raised `from None`; `tests/test_settings.py:13-14,100-130` marker values show the test style.

### Per-app state, no module-level mutable state
**Source:** `api/app.py:77-87` (`app.state.readiness`, `limiter`, ...). Engine, session factory and any `/v1` cache live on `app.state` and are built in `create_app()`/lifespan. Module-level `app = create_app()` only in `truthtrail/main.py`.

### SYSTEMROOT in subprocess tests
**Source:** `tests/conftest.py:140-154` (`subprocess_env` fixture), duplicated inline at `tests/test_demo_fixture.py:110-112` and `tests/test_settings.py:129-131`. Comment text to keep: without it asyncio cannot initialise Winsock (WinError 10106).
**Apply to:** crash-resume CLI test, `migrate` CLI test, spike tool CLI test, fresh-interpreter import tests (`test_import_rules.py`, `test_no_news_in_handlers.py`). Build env from `subprocess_env` and extend; never `env=os.environ`. Also pass `PYTHONDONTWRITEBYTECODE=1`.

### LF line endings
**Source:** `.gitattributes` (`* text=auto eol=lf`), `generate_demo_fixture.py:165` (`write_text(..., encoding="utf-8", newline="\n")`). Every script, scrubber and generator that writes a committed file uses `newline="\n"` and explicit `encoding="utf-8"`; `.jsonl` fixture lines end in `\n` only so the pinned sha256 is the same on Windows and Linux. `.sh` files only for existing scripts: new developer helpers are Python (CONTEXT D-30).

### No network in tests
**Source:** `tests/conftest.py:55-70` (autouse `responses.RequestsMock`, env scrub) plus the new loopback-only socket guard (B). The live Jetstream, Bluesky AppView and GNews are never touched by `pytest`. WebSocket tests use `websockets.asyncio.server.serve` on `127.0.0.1` with `proxy=None`. The spike tool is the only code that touches Bluesky, and only when the owner or the 03-01 executor runs it by hand; if egress returns 403 stop and report, never substitute data.

### AST import-rule tests with negative controls
**Source:** `tests/test_no_legacy_imports.py` (walker function, negative-control test, `MIN_FILES` floor, fresh-interpreter `sys.modules` check, `_serving_env` with `PYTHONPATH=src`). **Apply to:** `test_import_rules.py` encoding D-31: `api` never imports `ingest`, `jobs`, `services.gnews`, `requests`, `websockets`; `ingest|enrich|jobs` never import `api`; pure `enrich` modules import nothing from `db`; API process never imports `ingest.pseudonym`; `core` imports no higher layer. Extend `FORBIDDEN`-style data, not the walker.

### Hypothesis profiles
**Source:** `tests/conftest.py:21-32` (`ci`: 200 examples, derandomized, `database=None`, `deadline=None`). Pure-resolver property tests run under `--hypothesis-profile=ci` (CI passes it, `ci.yml` tests job). DB property tests set explicit small `max_examples`.

### Conventions (CLAUDE.md)
4-space indent, double quotes, `snake_case`, annotate all signatures (mypy strict on `src/truthtrail`), `X | None` not `Optional`, `logging.getLogger(__name__)` never `print`, triple-double-quoted docstrings, no emoji comments. All new copy says "flag for human review", never "detects" (copy guard: `scripts/copy_guard.py` `BANNED`).

## No Analog Found

| File | Role | Data flow | Source instead |
|---|---|---|---|
| `alembic.ini`, `db/migrations/env.py`, `versions/*` | migration | batch | 03-RESEARCH Pattern 8 (programmatic commands, `config.attributes["connection"]`, F-14) |
| `src/truthtrail/db/models.py` (SQLAlchemy declarative) | model | CRUD | 03-RESEARCH Pattern 6 (naming convention, `via_uri` column pending owner checkpoint F-07) |
| `ingest/pseudonym.py` | utility | transform | 03-RESEARCH Pattern 3 |
| `ingest/writer.py` | repository | batch CRUD | 03-RESEARCH Pattern 4 |
| `enrich/apply.py`, `enrich/purge.py` | repository | CRUD | 03-RESEARCH Patterns 4 and 7 |
| `ingest/source.py` `JetstreamSource` (WebSocket) | service | streaming | 03-RESEARCH Patterns 1, 2, 12 (partial retry-loop analog in `gnews.py`) |
| PG provisioning fixture | test infra | n/a | 03-RESEARCH Pattern 11 |
| Postgres service container in `ci.yml` | CI | n/a | 03-RESEARCH Environment section (digest to be re-resolved) |

## OWNER DECISION touchpoints (parameters only; not decided here)

| Item | Files that must take it as a parameter | Where the recommended default lives |
|---|---|---|
| OD-1 retention | `enrich/purge.py`, `ingest/normalise.py` (text written or not), `db/models.py` (nullable text + `text_purged_at`), README limitations | `core/policy.py` `RETENTION_TEXT_DAYS` / `RETENTION_CASCADE_DAYS` / `RETENTION_TOMBSTONE_DAYS` (14 / 90 / 7, PROVISIONAL OD-1) |
| OD-2 merge | `db/models.py` (`cascades.claim_id` only), `api/v1_cascades.py` (`claim_id` filter), no merge code unless ratified | `CASCADE_MERGE_POLICY = "claim_group"`, PROVISIONAL OD-2 |
| OD-3 root selection and bounds | `ingest/selection.py`, `ingest/run.py` (caps, refusal counters), `data/seed_domains.txt` (<= 60 domains, categorised), `tests/test_selection.py` | `TRACK_*`, `STORE_MAX_EVENTS_TOTAL` PROVISIONAL OD-3; RESEARCH F-06 (500-root cap fills in 38 min at measured yield) is an input to the owner, add `TRACK_SAMPLE_PER_10K` as a parameter if the owner agrees |

No test may hard-code an OD value; tests read the policy defaults or pass explicit values.

## Metadata

**Analog search scope:** `src/truthtrail/**`, `tests/*.py`, `scripts/*`, `.github/workflows/ci.yml`, `Dockerfile`, `.dockerignore`, `.env.example`, `.gitignore`, `pyproject.toml`, `.planning/phases/{02-engineering-baseline,03-real-propagation-data}`.
**Files read:** `api/{app,v1,limits,problems,analyze,cache,health,catchall}.py`, `core/{config,boot,errors,cascade,readiness}.py`, `schemas/models.py`, `services/gnews.py` (header and signature), `tests/{conftest,test_ci_workflow,test_v1_limits,test_no_legacy_imports,test_openapi_golden,test_readme_env_table,test_no_hardcoded_credentials,test_settings,test_container_files}.py` (and function inventories of 12 more test files), `scripts/{copy_guard,generate_demo_fixture,smoke_app}.py`, `pyproject.toml`, `Dockerfile`, `.github/workflows/ci.yml`, `02-PATTERNS.md`, `03-CONTEXT.md`, `03-RESEARCH.md` (summary, findings, patterns 1-12, validation map, spike brief).
**Notes:** the pre-existing Phase 1 and 2 CONTEXT, VERIFICATION and SECURITY files, `PROJECT.md`, `ROADMAP.md`, `research/*.md` were not re-read line by line for this map; their frozen contracts are taken from the Phase 3 CONTEXT canonical-refs section and the code itself. Line numbers are for HEAD `78bfdfb`.
**Pattern extraction date:** 2026-10-18
