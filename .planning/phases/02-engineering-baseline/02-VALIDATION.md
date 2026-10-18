---
phase: "2"
slug: "engineering-baseline"
# status lifecycle: draft (seeded by plan-phase) -> validated (set by plan 02-12 Task 3 step 6 when the phase gate passes; /gsd-validate-phase may re-audit it afterwards)
# audit-milestone section 5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-10-17"
---

# Phase 2 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Seeded from `02-RESEARCH.md` "Validation Architecture"; the per-task rows below are filled from the twelve PLAN files. Commands assume cwd = repo root and the virtualenv `.venv` (pip-created in plans 02-01 and 02-02, created by `uv sync` from plan 02-03 onward; `.venv/bin/python` works in both). Docker and the GitHub Actions workflow cannot be executed in the dev container (no daemon, no runner, no GitHub API for this repository): they are covered by static tests plus the NON-GATING human follow-ups listed under "Manual-Only Verifications".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1, pytest-cov 7.1.0, hypothesis 6.170.1, responses 0.26.3, Starlette `TestClient` (httpx 0.28.1), PyYAML 6.0.3 (static CI test) |
| **Config file** | `pytest.ini` until plan 02-03; afterwards `pyproject.toml` `[tool.pytest.ini_options]` (pytest.ini is deleted in 02-03). Hypothesis profiles `ci` and `dev` are registered in `tests/conftest.py` (plan 02-10); coverage in `[tool.coverage.*]` (plan 02-12) |
| **Quick run command** | `.venv/bin/python -m pytest -q -x tests/{affected file}.py` |
| **Full suite command** | `.venv/bin/python -m pytest -q` (plans 02-01 to 02-11); `.venv/bin/python -m pytest --cov --hypothesis-profile=ci -q` (final form, plan 02-12) |
| **Non-pytest gates** | `.venv/bin/ruff check . && .venv/bin/ruff format --check .` (from 02-04); `.venv/bin/mypy` (from 02-04); `.venv/bin/python scripts/copy_guard.py`; `.venv/bin/python scripts/generate_demo_fixture.py --check`; `uv lock --check`; `uv export --locked --no-emit-project --all-groups --format requirements-txt -o {file}` + `.venv/bin/pip-audit -r {file} --require-hashes --disable-pip --progress-spinner off`; `bash scripts/gitleaks_scan.sh {bin} <floor> HEAD <floor>` and `bash scripts/gitleaks_selftest.sh {bin}`; `python scripts/smoke_app.py --python {venv python}` against a `--locked --no-dev --no-editable` install |
| **Invariants after every plan** | passed count only grows from 274; xfailed stays 10; no XPASS; the Phase 1 tests change only by import paths, string patch targets, path constants and the edits tabulated under "Expected Phase 1 test edits" below (any other changed assertion line in a Phase 1 test file is a defect) |
| **Estimated runtime** | about 15 s without coverage, about 40 s with `--cov --hypothesis-profile=ci` (Phase 1 suite: 3.6 s; Hypothesis ci profile: about 4 s for the four properties; uv sync from a cold cache adds 10-30 s) |

---

## Sampling Rate

- **After every task commit:** the quick run for the touched test files, `.venv/bin/python -m pytest -q tests/test_no_hardcoded_credentials.py`, the word-bounded 32-hex added-lines scan, and (from plan 02-04) `ruff check`, `ruff format --check`, `mypy`.
- **After every plan (one wave each):** the full suite (`.venv/bin/python -m pytest -q`), `tests/test_openapi_golden.py` and `tests/test_legacy_frozen.py` explicitly named in the plan verify, plus `python scripts/copy_guard.py` once the README or OpenAPI strings changed.
- **Deliberate exception:** the pure-rename commit of plan 02-02 Task 1 is red by design (imports unresolved) and repaired by the next commit of the same plan; the credentials test cannot run there (conftest imports the moved config module) and the added-line scan is empty for a pure rename. Executors never push; the orchestrator pushes only at plan boundaries, so this red commit is never pushed on its own and never becomes the remote branch tip (02-02 Task 1 also asserts that no remote-tracking branch contains it).
- **Before `/gsd-verify-work`:** the phase gate in 02-12 Task 3 (full suite with coverage and the CI Hypothesis profile, ruff, mypy, copy guard, fixture check, lock check, pip-audit pair, gitleaks scan from the floor and selftest, smoke script, frozen-file blob comparisons against 9b5b085, clean tree). The post-push Actions run is a NON-GATING follow-up harvested into the phase UAT (config `human_verify_mode: end-of-phase`); until it is confirmed, ROADMAP criterion 2 is 'pending human confirmation', never passed (same for criterion 4 and the docker build and run).
- **Max feedback latency:** 60 seconds.

---

## Per-Task Verification Map

Threat refs point at the `<threat_model>` tables in the PLAN files (IDs T-02-01 to T-02-42 are unique within the phase; T-02-SC is kept in every plan).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 02-01 | 1 | ENG-01 | T-02-01, T-02-03 | CR+LF normalised in one standalone commit of seven named paths; legacy files identical modulo line endings; suite unchanged | regression | `.venv/bin/python -m pytest -q` and `git diff --quiet --ignore-cr-at-eol 9b5b085 -- risk_analyzer.py spread_simulator.py users.py` | existing | green |
| 02-01-02 | 02-01 | 1 | ENG-01 | T-02-02 | Phase 1 OpenAPI document frozen from unmoved code; only declared additions allowed; golden sha256 pinned | contract | `.venv/bin/python -m pytest -q tests/test_openapi_golden.py` | W0 | green |
| 02-01-03 | 02-01 | 1 | ENG-01 | T-02-03 | LF-normalised sha256 pins for the files that will move; patch targets and subprocess env centralised (SYSTEMROOT) | unit | `.venv/bin/python -m pytest -q tests/test_legacy_frozen.py tests/test_provenance_demo.py tests/test_request_validation.py` | W0 | green |
| 02-02-01 | 02-02 | 2 | ENG-01 | T-02-05 | Nine pure renames at 100 percent similarity; history reachable with `--follow`; deliberate red commit | git | `names=$(git show -M --name-status --format= HEAD) && test -z "$(printf '%s\n' "$names" \| grep -v '^R100')" && test "$(printf '%s\n' "$names" \| wc -l)" = 9` | n/a | green |
| 02-02-02 | 02-02 | 2 | ENG-01 | T-02-05, T-02-06 | Suite green again with only import/patch-target/path edits; fixture and legacy bytes unchanged; shim keeps `uvicorn main:app` fail-fast (exit 3) | regression | `.venv/bin/python -m pytest -q` and `.venv/bin/python scripts/generate_demo_fixture.py --check` | existing | green |
| 02-02-03 | 02-02 | 2 | ENG-01 | T-02-04 | Package never imports legacy (AST walk with negative control); importing the app loads no legacy module; legacy not findable on the serving path; shim identity | unit + subprocess | `.venv/bin/python -m pytest -q tests/test_no_legacy_imports.py tests/test_main_shim.py` | W0 | green |
| 02-03-01 | 02-03 | 3 | ENG-02 | T-02-07, T-02-08, T-02-SC | Exact-pinned deps, serving/dev/train split with `train` excluded by default, lock accepted by uv 0.13.1 and 0.11.32, fresh clone installs, no `readme`, pytest.ini and requirements files retired | unit + tooling | `.venv/bin/python -m pytest -q tests/test_dependency_groups.py` and `uv lock --check` and `bash scripts/gitleaks_scan.sh {bin} a5dd8257e920923677c60e70611a6f36d87747b2 HEAD a5dd8257e920923677c60e70611a6f36d87747b2` | W0 | green |
| 02-03-02 | 02-03 | 3 | ENG-04, ENG-02 | T-02-09 | CI copy-guard and tests jobs use SHA-pinned setup-uv and locked sync; job names and gitleaks job unchanged; README setup text on uv | static contract | `.venv/bin/python -m pytest -q tests/test_ci_workflow.py` and `.venv/bin/python scripts/copy_guard.py` | W0 | green |
| 02-04-01 | 02-04 | 4 | ENG-04 | T-02-10 | Ruff configured; mechanical autofix and format in one commit; legacy and keyword_baseline untouched | lint + regression | `.venv/bin/ruff format --check .` and `.venv/bin/python -m pytest -q tests/test_legacy_frozen.py tests/test_openapi_golden.py` | existing | green |
| 02-04-02 | 02-04 | 4 | ENG-04 | T-02-10, T-02-11 | Remaining 24 findings fixed by hand without blanket noqa; OpenAPI strings byte-identical; formatter commit recorded for blame | lint | `.venv/bin/ruff check . && .venv/bin/ruff format --check .` | existing | green |
| 02-04-03 | 02-04 | 4 | ENG-04 | T-02-11 | mypy strict clean on src/truthtrail (generics, Mapping headers, decorator handlers, lifespan type); behaviour and handler order unchanged | typecheck | `.venv/bin/mypy` and `.venv/bin/python -m pytest -q` | existing | green |
| 02-05-01 | 02-05 | 5 | ENG-06 | T-02-15 | `create_app()` factory builds independent apps; only BootSettings at construction (fail-fast exit 3 preserved); Problem.synthetic is Literal[False] with const declared | integration | `.venv/bin/python -m pytest -q tests/test_app_factory.py tests/test_openapi_golden.py tests/test_settings.py::test_uvicorn_exits_on_missing_key` | W0 | green |
| 02-05-02 | 02-05 | 5 | ENG-06 | T-02-12, T-02-13, T-02-14 | CORS only for configured origins; invalid origins fail construction without echoing; 500/404/422 carry ACAO; catch-all logs class name only | integration | `.venv/bin/python -m pytest -q tests/test_cors.py` | W0 | green |
| 02-06-01 | 02-06 | 6 | ENG-05 | T-02-18 | Readiness registry fails closed (raise, non-True), rejects duplicates and blank names, never logs exception text | unit | `.venv/bin/python -m pytest -q tests/test_readiness_registry.py` | W0 | green |
| 02-06-02 | 02-06 | 6 | ENG-05 | T-02-16, T-02-17 | `/health` 200; `/ready` 200 with no checks, 503 problem+json naming only failed checks (injected failing and raising checks), recovery; OpenAPI additions limited to /health and /ready | integration + contract | `.venv/bin/python -m pytest -q tests/test_health_ready.py tests/test_openapi_golden.py tests/test_openapi_contract.py` | W0 | green |
| 02-07-01 | 02-07 | 7 | ENG-06 | T-02-19, T-02-22 | `/analyze` limited per IP (default 10 per minute), 429 problem+json with Retry-After >= 1 and provenance, health endpoints and 422s not counted, per-IP and per-app isolation, invalid limit fails startup, 429 declared in OpenAPI | integration | `.venv/bin/python -m pytest -q tests/test_rate_limit.py tests/test_openapi_golden.py` | W0 | green |
| 02-07-02 | 02-07 | 7 | ENG-06 | T-02-20, T-02-21 | `/v1` LimitedRouter returns 429 for a probe route (fail-closed proof), handler without `request` cannot register, spoofed X-Forwarded-For ignored unless trusted; a REAL uvicorn started with `--no-proxy-headers` ignores a spoofed X-Forwarded-For (negative control: uvicorn default flags let it through) | integration + subprocess | `.venv/bin/python -m pytest -q tests/test_v1_limits.py tests/test_proxy_headers_server.py` | W0 | green |
| 02-08-01 | 02-08 | 8 | ENG-06 | T-02-28, T-02-29, T-02-31 | AnalyzeCache: TTL (599 s hit, 601 s miss), LRU bound 256, normalised keys, lock-guarded, injectable clock | unit | `.venv/bin/python -m pytest -q tests/test_cache_unit.py` | W0 | green |
| 02-08-02 | 02-08 | 8 | ENG-06 | T-02-28, T-02-30 | `/analyze` hit/miss with `X-Cache`, original `data_as_of` kept, errors never cached, empty result cached, limit applies before cache | integration | `.venv/bin/python -m pytest -q tests/test_cache.py` | W0 | green |
| 02-09-01 | 02-09 | 9 | ENG-06 | T-02-32, T-02-33, T-02-34 | Retry loop: 3 attempts, 0.3/0.6 s backoff, no retry on 4xx/429/3xx/SSL, 8 s budget, Phase 1 mapping unchanged on exhaustion, no real sleeping | integration (responses) | `.venv/bin/python -m pytest -q tests/test_retries.py tests/test_upstream_errors.py` | W0 | green |
| 02-09-02 | 02-09 | 9 | ENG-06 | T-02-32, T-02-33, T-02-35 | Failing and slow upstream stop at the bound through `GET /analyze`; log hygiene across retries; `Retry-After: 0` becomes 1 | integration | `.venv/bin/python -m pytest -q tests/test_retries.py tests/test_upstream_errors.py` | W0 | green |
| 02-10-01 | 02-10 | 10 | ENG-03 | T-02-38 | `order_events`/`validate_cascade` properties on arbitrary cascades (ties, shuffles, mutants killed); Hypothesis `ci` profile | property | `.venv/bin/python -m pytest -q tests/test_cascade_properties.py --hypothesis-profile=ci` | W0 | green |
| 02-10-02 | 02-10 | 10 | ENG-03 | T-02-36, T-02-37 | Fixture load is gated by `validate_cascade`; demo startup fails on a violating fixture; served order unchanged; stdlib-only core module | integration | `.venv/bin/python -m pytest -q tests/test_cascade_gate.py tests/test_demo_fixture.py tests/test_legacy_frozen.py` | W0 | green |
| 02-11-01 | 02-11 | 11 | ENG-05 | T-02-24, T-02-25, T-02-26 | Dockerfile static contract: digest-pinned stages, non-root, no secrets, HEALTHCHECK on /health, exact CMD including `--no-proxy-headers`, legacy/tests/scripts not copied, .dockerignore entries | static | `.venv/bin/python -m pytest -q tests/test_container_files.py` | W0 | green |
| 02-11-02 | 02-11 | 11 | ENG-05 | T-02-25 | `--locked --no-dev --no-editable` install serves /health, /ready and demo /analyze (X-Cache miss then hit); legacy, dev and train modules not importable | smoke | `env_dir=...; UV_PROJECT_ENVIRONMENT="$env_dir" uv sync --locked --no-dev --no-editable && "$env_dir/bin/python" scripts/smoke_app.py --python "$env_dir/bin/python"` | W0 | green |
| 02-12-01 | 02-12 | 12 | ENG-03 | T-02-42 | Coverage measured on the final tree; `fail_under` = floor(total) minus 2; gate fires on a 100 percent negative control; not in addopts | coverage | `.venv/bin/python -m pytest --cov --hypothesis-profile=ci -q` and `.venv/bin/python -m pytest -q tests/test_coverage_config.py` | W0 | green |
| 02-12-02 | 02-12 | 12 | ENG-04, ENG-05 | T-02-39, T-02-40, T-02-41 | Seven CI jobs (lint, typecheck, audit, docker added); SHA-pinned actions, read-only permissions, timeouts, no secrets; every job command proven locally | static contract | `.venv/bin/python -m pytest -q tests/test_ci_workflow.py` and `uv lock --check` and the pip-audit pair | existing | green |
| 02-12-03 | 02-12 | 12 | ENG-02, ENG-04 | T-02-40 | README complete and honest, Windows and uv instructions, all ten environment names documented; phase gate: copy guard, gitleaks from the floor, fixture check, frozen-file blob comparisons, clean tree | doc contract + gate | `.venv/bin/python -m pytest -q tests/test_readme_env_table.py` and `.venv/bin/python scripts/copy_guard.py` and `bash scripts/gitleaks_scan.sh {bin} a5dd8257e920923677c60e70611a6f36d87747b2 HEAD a5dd8257e920923677c60e70611a6f36d87747b2` | W0 | green |

*Status: pending / green / red / flaky. Update from the SUMMARY of each plan.*

---

## Requirement -> Test Map (ROADMAP success criteria)

| Criterion | Requirement | Behavior | Proof |
|-----------|-------------|----------|-------|
| SC1 | ENG-01 | `src/truthtrail` serves the same endpoints; Phase 1 tests pass through the refactor; simulator and users unreachable | `tests/test_openapi_golden.py`, full suite, `tests/test_no_legacy_imports.py`, `tests/test_legacy_frozen.py`, `tests/test_main_shim.py` |
| SC2 | ENG-02, ENG-04 | Fresh clone installs from uv lock on 3.13 with split groups; CI runs ruff, mypy, pytest, pip-audit, secret scan; green on the final commit | `tests/test_dependency_groups.py`, fresh-clone `uv sync --locked`, `tests/test_ci_workflow.py`, local runs of every CI command; **green Actions run = NON-GATING human follow-up; status 'pending human confirmation' (OPEN), never 'passed' before it** |
| SC3 | ENG-03 | pytest + hypothesis suite, coverage reported, ordering and parent-before-child properties | `tests/test_cascade_properties.py` (ci profile), `tests/test_cascade_gate.py`, coverage gate (02-12) |
| SC4 | ENG-05 | `docker build` succeeds and the container answers `/health`; `/ready` 503 on a failing registered check | `tests/test_health_ready.py` (injected failing check); `tests/test_container_files.py` + smoke script; **docker build/run = NON-GATING human follow-up and CI docker job; status 'pending human confirmation' (OPEN), never 'passed' before it** |
| SC5 | ENG-06 | CORS only configured origins; 429; TTL cache; timeouts and bounded retries incl. slow/failing upstream | `tests/test_cors.py`, `tests/test_rate_limit.py`, `tests/test_v1_limits.py`, `tests/test_cache.py`, `tests/test_retries.py` |

---

## Expected Phase 1 test edits

The Phase 1 suite (274 passed, 10 xfailed) must keep passing with its assertions unchanged except for the rows below. This is the single list the verifier uses: any other changed assertion line in a Phase 1 test file (`tests/test_char_risk_analyzer.py`, `test_char_simulator.py`, `test_copy_guard.py`, `test_demo_fixture.py`, `test_network_guard.py`, `test_no_hardcoded_credentials.py`, `test_openapi_contract.py`, `test_provenance_demo.py`, `test_request_validation.py`, `test_response_models.py`, `test_settings.py`, `test_upstream_errors.py`) is unexpected and a defect.

Standing categories that are NOT listed row by row: import statements, string patch targets (built from the `app_module` fixture, plans 02-01, 02-02 and 02-05), path constants and frozen-file keys (02-02), and the output of the mechanical ruff autofix and format commit (02-04, recorded in `.git-blame-ignore-revs`; review with `git diff --ignore-all-space` and skip that commit). Rows 1 to 5 are the edits the verifier must expect beyond those categories; rows 6 to 8 are smaller ones listed for completeness.

| # | Plan | File | Edit | Kind | Justification |
|---|------|------|------|------|---------------|
| 1 | 02-09 | `tests/test_upstream_errors.py` | In `test_request_uses_timeout_header_and_fixed_params` the whole-tuple equality `request.req_kwargs["timeout"] == (3.05, 10)` becomes two booleans: the connect timeout equals 3.05 and the read timeout is greater than 7.9 and at most 8.0 | assertion edit | D-12 caps the first attempt's read timeout at the 8 s total budget, so the old read timeout of 10 can no longer occur; the exact `(3.05, 8.0)` is asserted with a fake clock in `tests/test_retries.py`. The only Phase 1 assertion that necessarily changes |
| 2 | 02-04 | `tests/test_copy_guard.py` | `assert len(far) == 1 and far[0].line == 3` is split into two consecutive asserts (ruff PT018) | assertion edit, semantically identical | PT018 is in the D-15 rule selection; same conditions, same order |
| 3 | 02-04 | `tests/test_demo_fixture.py` | `assert spec is not None and spec.loader is not None` is split into two consecutive asserts (ruff PT018) | assertion edit, semantically identical | same as row 2 |
| 4 | 02-02 | `tests/test_upstream_errors.py` | In `test_no_key_or_url_in_logs` the logger-name string in the record filter `r.name == "gnews_fetcher"` becomes `"truthtrail.services.gnews"` | string retarget (a list-comprehension filter, not an assert line) | the adapter's logger is named after its module `__name__`, which changes with the move (D-04); the test still requires a WARNING record from that logger, so it cannot pass vacuously |
| 5 | 02-05 | `src/truthtrail/api/problems.py` (production code; the test below passes unchanged apart from the 02-01 patch-target constant) | The generic `Exception` handler registered by `register_problem_handlers` is removed; its job moves into `CatchAllMiddleware` | production change under a Phase 1 test | A handler registered for `Exception` renders in Starlette's outermost ServerErrorMiddleware, outside CORS, so a 500 would carry no CORS headers (review item IN-02, D-09). The catch-all inside CORS produces the identical body and log line, and `tests/test_request_validation.py::test_unexpected_error_is_generic_500` must pass with no assertion edit |
| 6 | 02-04 | `tests/test_char_simulator.py` | `zip(chain, chain[1:])` becomes `itertools.pairwise(chain)` (ruff B905 and RUF007) | code edit in a test body, no assertion change | same successive pairs; keeps the rule selection clean without a blanket ignore |
| 7 | 02-05, 02-07 | `tests/test_no_hardcoded_credentials.py` | `EXPECTED_ENV_NAMES` gains CORS_ORIGINS (02-05) and RATE_LIMIT_ANALYZE, RATE_LIMIT_V1, TRUST_PROXY_HEADERS, FORWARDED_ALLOW_IPS (02-07) | expected-value list extended | the test requires every non-comment line of the example environment file to be a bare `NAME=` from this list (research Pitfall 12); new variables are added together with their code |
| 8 | 02-02 | `tests/test_no_hardcoded_credentials.py`, `tests/test_settings.py` | gitignore-semantics parametrisation paths (`fixtures/demo_analyze.json` and `models.py` take their new paths); the PYTHONPATH value in `test_uvicorn_exits_on_missing_key` (repo root plus `src`); the in-function imports | path and import retarget | the files moved; listed because they are not plain top-of-file imports |
| 9 | 02-04 | `tests/test_char_simulator.py`, `test_copy_guard.py`, `test_demo_fixture.py`, `test_legacy_frozen.py`, `test_no_hardcoded_credentials.py`, `test_openapi_contract.py`, `test_settings.py` | Long module docstrings, comments and the xfail `reason` string are wrapped to 100 columns (adjacent literals, identical runtime value); the two long sha256 pins in `LEGACY_FILES` are written as parenthesised string literals; `import itertools` is added (row 6) | line wrap, no assertion change | ruff E501 is in the D-15 rule selection and no `noqa: E501` is allowed; the pinned hash values and the xfail reason text are byte-identical |
| 10 | review WR-04 | `tests/test_upstream_errors.py` | In `test_request_uses_timeout_header_and_fixed_params` the read-timeout bound `7.9 < read_timeout <= 8.0` becomes `4.8 < read_timeout <= 4.95` | assertion edit | The review found that connect and read timeouts are applied separately, so one attempt could take about 11 s. Each attempt now gets a connect timeout of at most half the remaining budget and a read timeout of the rest, so the first attempt is (3.05, 4.95); `tests/test_retries.py` asserts the sum with a fake clock |

Additions that edit no existing assertion: new tests appended to `tests/test_response_models.py` and `tests/test_openapi_golden.py` (02-05), new parametrised `FAILURE_CASES` rows for `Retry-After: 0` and `00` in `tests/test_upstream_errors.py` (02-09, closes review item IN-03), and fixtures added to `tests/conftest.py` (02-01, 02-05, 02-09, 02-10).

---

## Wave 0 Requirements

Test files and infrastructure created by the plans (all must exist before the phase gate):

- [x] `tests/golden/openapi_phase1.json`, `tests/test_openapi_golden.py`, `tests/test_legacy_frozen.py`; conftest additions `APP_MODULE`, `app_module`, `subprocess_env` (02-01)
- [x] `tests/test_no_legacy_imports.py`, `tests/test_main_shim.py` (02-02)
- [x] `tests/test_dependency_groups.py`, `tests/test_ci_workflow.py`; framework install `uv sync` (02-03)
- [x] `tests/test_app_factory.py`, `tests/test_cors.py`; conftest `client_factory(env, client, app_kwargs)` (02-05)
- [x] `tests/test_readiness_registry.py`, `tests/test_health_ready.py` (02-06)
- [x] `tests/test_rate_limit.py`, `tests/test_v1_limits.py`, `tests/test_proxy_headers_server.py` (02-07)
- [x] `tests/test_cache_unit.py`, `tests/test_cache.py` (02-08)
- [x] `tests/test_retries.py`; conftest autouse `no_real_sleep` (02-09)
- [x] `tests/test_cascade_properties.py`, `tests/test_cascade_gate.py`; conftest Hypothesis profiles (02-10)
- [x] `tests/test_container_files.py`, `scripts/smoke_app.py` (02-11)
- [x] `tests/test_coverage_config.py`, `tests/test_readme_env_table.py`; extended `tests/test_ci_workflow.py` (02-12)
- [x] Tool configuration: `pyproject.toml` (pytest, ruff, mypy, coverage), `.gitattributes`, `.gitignore` (`.hypothesis/`), `.dockerignore`, `Dockerfile`, `.github/workflows/ci.yml`

---

## Manual-Only Verifications

All items are **NON-GATING**: they never block a plan, the phase gate or `/gsd-verify-work`; the verifier harvests them into the phase UAT (config `human_verify_mode: end-of-phase`). Non-gating does not mean passed: ROADMAP success criteria 2 (CI green on the final commit) and 4 (`docker build` and a running container answering `/health`) stay 'pending human confirmation' until the first two rows below are confirmed, and the verifier must list them as OPEN human-verify items, never as passed.

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| CI green on the pushed final commit: copy-guard, gitleaks, tests, lint, typecheck, audit, docker | ENG-04, ENG-05 (ROADMAP SC2: "green on the phase's final commit") | The workflow cannot run in the dev container (no runner; GitHub API not reachable for this repository). Research assumptions A1-A4 (Docker and curl on ubuntu-latest, setup-uv v9.0.0 inputs, YAML details) are unverified | After the push, open the Actions run for the final commit and read all seven jobs; apply the one-line fixes named in 02-RESEARCH.md if a first run fails |
| `docker build` and a running container answering `/health` as a non-root user | ENG-05 (SC4) | No Docker daemon in the dev container | `docker build -t truthtrail:ci .`; `docker run --rm -d -p 8000:8000 -e DEMO_MODE=true truthtrail:ci`; `curl -fsS http://127.0.0.1:8000/health`; `docker exec <id> id -u` is not 0 |
| README setup on native Windows 11 (PowerShell, Python 3.13) | ENG-02 | Dev container is Linux (research A5) | Follow the README Windows block: install uv, delete the old `.venv`, `uv sync`, `uv run pytest -q`, run with `DEMO_MODE` true and open `/health` |
| Base-image digests still resolve | ENG-05 | Registry API reachability varies | Re-check tag-to-digest for python:3.13-slim and ghcr.io/astral-sh/uv:0.13.1 against the values in the Dockerfile (research dated 2026-10-17) |
| Branch-protection required checks | D-26 | Repository setting, not visible in the repo | Confirm whether `copy-guard`, `gitleaks`, `tests` are required checks; the names were deliberately not changed |
| Owner review of the dependency list | D-26 (repeats Phase 1 D-18 waiver) | Package legitimacy tooling reports every PyPI package as suspicious only for missing download counts | Read the "Dependency review (D-26)" table in `02-03-SUMMARY.md` |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** executor-validated on 2026-10-17; ROADMAP criteria 2 and 4 pending human confirmation (see Manual-Only Verifications)

**Ownership of the flip:** plan 02-12 Task 3 step 6 sets `status: validated`, `nyquist_compliant: true` and `wave_0_complete: true`, ticks the boxes the evidence supports and sets the approval line, but only if every command of that plan's phase gate exited 0; otherwise the fields stay as they are and the SUMMARY names the failing command. It never marks a Manual-Only item as verified (ROADMAP criteria 2 and 4 stay 'pending human confirmation'). `/gsd-validate-phase` may re-audit the file afterwards.

---

## Coverage Audit (planner)

### Multi-source audit

| SOURCE | ID | Feature / Requirement | Plan | Status |
|--------|----|-----------------------|------|--------|
| GOAL | - | Packaged, tested, containerised, CI-guarded FastAPI app with a versioned `/v1` router mount point | 02-02, 02-03, 02-07, 02-11, 02-12 | COVERED |
| REQ | ENG-01 | `src/truthtrail` package; legacy off the live path | 02-01, 02-02 | COVERED |
| REQ | ENG-02 | uv lockfile, Python 3.13, training/serving split | 02-03, 02-12 (README) | COVERED |
| REQ | ENG-03 | pytest + hypothesis, ordering invariants, coverage | 02-10, 02-12 | COVERED |
| REQ | ENG-04 | CI: ruff, mypy, pytest, pip-audit, secret scan | 02-03, 02-04, 02-12 | COVERED (green run = non-gating follow-up) |
| REQ | ENG-05 | Dockerfile; `/health`; `/ready` 503 on failed check | 02-06, 02-11, 02-12 | COVERED (docker build = non-gating follow-up) |
| REQ | ENG-06 | CORS, rate limit, TTL cache, timeouts + bounded retries | 02-05, 02-07, 02-08, 02-09 | COVERED |
| RESEARCH | Finding 1 | `order_events` at fixture load would reorder the served body | 02-10 (validate gate, order not applied; D-19) | COVERED |
| RESEARCH | Finding 2 | `Problem.synthetic` const in OpenAPI needs a declared exception | 02-01 (test), 02-05 | COVERED |
| RESEARCH | Finding 3 / Pitfall 2 | slowapi fail-open under `include_router`; decorators + LimitedRouter + /v1 429 proof | 02-07 | COVERED |
| RESEARCH | Finding 4 / Pitfall 4 | CR+LF vs byte-identical; legacy flat import needs `legacy/` on sys.path | 02-01, 02-02 | COVERED |
| RESEARCH | Finding 5 / Pitfall 3 | Import-time settings break fail-fast; BootSettings | 02-05 | COVERED |
| RESEARCH | Finding 6 | Per-app limiter/cache/registry | 02-05 to 02-08 | COVERED |
| RESEARCH | Finding 7 / Pitfalls 7, 8 | Fixture in package; no `readme` in pyproject | 02-02, 02-03, 02-11 | COVERED |
| RESEARCH | Finding 8 / Pattern 2 | Exact existing-test retargets | 02-02 (plus two found during planning: `tests/test_demo_fixture.py` in-function import, `tests/test_settings.py` in-function import, `scripts/copy_guard.py` import) | COVERED |
| RESEARCH | Pitfall 5 | ruff format would rewrite keyword_baseline.py | 02-04 | COVERED |
| RESEARCH | Pitfall 6 | `.hypothesis/` in `.gitignore` | 02-03 | COVERED |
| RESEARCH | Pitfall 9 | `write_text` newline on Windows | 02-02 (`newline="\n"`) | COVERED |
| RESEARCH | Pitfall 10 | `Literal[False]` OpenAPI diff | 02-01, 02-05 | COVERED |
| RESEARCH | Pitfall 11 | mypy `add_exception_handler` variance | 02-04 | COVERED |
| RESEARCH | Pitfall 12 | `.env.example` machine-checked | 02-05, 02-07 (names added with their code) | COVERED |
| RESEARCH | Pitfall 13 | pytest.ini silently overrides pyproject | 02-03 | COVERED |
| RESEARCH | Pitfall 14 | uv/Docker version drift | 02-03 (CI pin, `lock --check`), 02-11 (digests), 02-12 | COVERED |
| RESEARCH | Pitfall 15 / A1-A4 | First docker build and workflow run happen in CI | 02-11, 02-12 (non-gating human follow-ups) | COVERED |
| RESEARCH | Open Q 7 | Proxy trust semantics (low) | 02-07 implements flag + trusted hosts; Phase 6 chooses the proxy address | COVERED (decision deferred to Phase 6 by the research) |
| RESEARCH | Open Q 8 | Dependency policy | D-24 exact pins | COVERED |
| RESEARCH | Open Q 9 | Coverage gate measured last | 02-12 Task 1 | COVERED |
| RESEARCH | Package Legitimacy Audit | All packages SUS for artefacts; waiver or checkpoint | 02-03 (D-26 waiver, SUMMARY dependency table) | COVERED |
| RESEARCH | Security Domain | CORS, limits, retry amplification, cache poisoning, non-root image, supply chain | threat registers T-02-01 to T-02-42 | COVERED |
| CONTEXT | D-01 | Legacy moved unchanged outside src, not packaged, not in image | 02-01, 02-02, 02-11 | COVERED |
| CONTEXT | D-02 | risk_analyzer to services/keyword_baseline.py, rules identical | 02-01, 02-02, 02-04 | COVERED |
| CONTEXT | D-03 | `order_events()`, `validate_cascade()` in core/cascade.py | 02-10 | COVERED |
| CONTEXT | D-04 | Layout and `truthtrail.main:app` | 02-02, 02-05 | COVERED |
| CONTEXT | D-05 | Root `main.py` shim | 02-02, 02-12 (README) | COVERED |
| CONTEXT | D-06 | `/analyze` unchanged; empty `/v1` router; `/health`, `/ready` at root | 02-05, 02-06, 02-07 | COVERED |
| CONTEXT | D-07 | Readiness registry; 503 problem+json naming failed checks | 02-06 | COVERED |
| CONTEXT | D-08 | Golden OpenAPI snapshot | 02-01 (+ allowances exercised in 02-05 to 02-07) | COVERED |
| CONTEXT | D-09 | CORS from `CORS_ORIGINS`, unset = none, CORS outermost for errors | 02-05 | COVERED |
| CONTEXT | D-10 | slowapi in-memory per-IP limits, proxy trust flag, defaults 10/60 per minute | 02-07 | COVERED |
| CONTEXT | D-11 | TTL cache 600 s / 256, successes only, `X-Cache`, limit before cache | 02-08 | COVERED |
| CONTEXT | D-12 | Explicit retry loop, 3 attempts, backoff, 8 s budget | 02-09 | COVERED |
| CONTEXT | D-13 | Retry-After 0 clamp; Problem.synthetic Literal[False] | 02-09; 02-05 | COVERED |
| CONTEXT | D-14 | uv, Python 3.13, groups, lock, requirements retired | 02-03 | COVERED |
| CONTEXT | D-15 | ruff/mypy/coverage/Hypothesis profile | 02-04, 02-10, 02-12 | COVERED |
| CONTEXT | D-16 | Line-ending commit first | 02-01 | COVERED |
| CONTEXT | D-17 | CI jobs (lint, typecheck, audit, docker) + existing kept | 02-03, 02-12 | COVERED |
| CONTEXT | D-18 | Dockerfile | 02-11 | COVERED |
| CONTEXT | D-19 | validate gate at fixture load, order not applied | 02-10 | COVERED |
| CONTEXT | D-20 | Golden allowances: Problem const, /health, /ready, 429; failed names in detail; X-Cache undocumented | 02-01, 02-05, 02-06, 02-07, 02-08 | COVERED |
| CONTEXT | D-21 | "Byte-identical" means identical after CR+LF to LF; sha256 gate | 02-01, 02-02, 02-12 | COVERED |
| CONTEXT | D-22 | Fixture in package; no `readme` | 02-02, 02-03, 02-11 | COVERED |
| CONTEXT | D-23 | Per-app state, BootSettings, decorators only, LimitedRouter | 02-05, 02-07, 02-08 | COVERED |
| CONTEXT | D-24 | Exact pins; no required-version above 0.11 | 02-03 | COVERED |
| CONTEXT | D-25 | mypy on src only; ruff excludes; retargets; pytest.ini deleted; env names | 02-02, 02-03, 02-04, 02-05, 02-07 | COVERED |
| CONTEXT | D-26 | Keep job names; legitimacy waiver; human-verify items | 02-03, 02-11, 02-12 | COVERED |

No row is MISSING. Deferred ideas (shared rate-limit store, pre-commit hooks, structured logging, metrics endpoint, API-key auth, load test, shim removal, retiring `/analyze`) appear in no plan.

### Planner refinements and assumptions

1. **Ordering refinement.** The orchestrator hint put ruff and mypy last; they are placed right after the uv switch (plan 02-04) so every later plan is written, formatted and typed against the gates. Hints 2 and 3 are split into: factory + CORS (02-05), readiness (02-06), rate limit + `/v1` (02-07), cache (02-08), retries (02-09); the cascade module is 02-10 (after the factory because it gates `load_demo_fixture`); the container is 02-11 (after all runtime behaviour, so the smoke test exercises the final app); CI jobs, coverage gate and README are 02-12.
2. **Serialised waves.** Twelve plans, twelve waves. Plans 02-08 to 02-12 would have disjoint files in places, but every plan's gates run repo-wide (full suite, ruff, mypy) in one shared working tree, so they are serialised (`use_worktrees` is false).
3. **Move split.** The pure `git mv` (02-02 Task 1) is deliberately red for one commit; the repair commit is in the same plan. The `.venv` stays pip-created through 02-02 (temporary `pythonpath = src legacy .` in pytest.ini) and becomes uv-created in 02-03, because `uv_build` needs the package directory to exist before `uv sync`.
4. **Golden snapshot taken before the move**, from the unmoved Phase 1 code (13.9 KB), not from commit 765b844 (same code, simpler to obtain); its sha256 is pinned in the test.
5. **`limits==5.8.0` is declared as a direct pin** (plan 02-03) because plan 02-07 imports it to validate rate-limit settings at startup; it is slowapi's engine and already in the research lock.
6. **One Phase 1 assertion changes by necessity** (plan 02-09): the first attempt's timeout is `(3.05, at most 8.0)` instead of `(3.05, 10)`, because D-12's 8 s total budget caps the read timeout. All other upstream tests pass unchanged. Two PT018 compound asserts are split by ruff-driven edits (plan 02-04), semantically identical. Every Phase 1 test edit beyond import paths and patch targets is tabulated under "Expected Phase 1 test edits".
7. **The generic `Exception` handler is removed** in plan 02-05 (its job moves into the catch-all that sits inside CORS); the produced 500 body and log line are identical, and the Phase 1 test `test_unexpected_error_is_generic_500` still passes unchanged (row 5 of "Expected Phase 1 test edits").
8. **Startup check in demo mode** (plan 02-10) loads the fixture in the lifespan so a violating fixture stops startup; this is the second half of review item IN-02 and an application of D-19's "fails loudly", not a new feature.
9. **Package legitimacy.** The tool reports SUS for every package; D-26 repeats the owner's waiver, so no `checkpoint:human-verify` task is inserted (also suppressed by `human_verify_mode: end-of-phase`); the owner reviews the table in the 02-03 SUMMARY. slowapi is flagged as the one low-adoption package.
10. **Environment variable names added with their code** (CORS_ORIGINS in 02-05; RATE_LIMIT_ANALYZE, RATE_LIMIT_V1, TRUST_PROXY_HEADERS, FORWARDED_ALLOW_IPS in 02-07), each time in all three places the credentials test requires (example file, `EXPECTED_ENV_NAMES`, conftest `ENV_NAMES`).
11. **uvicorn's own proxy handling is switched off.** uvicorn 0.54.0 has `--proxy-headers` on by default and trusts X-Forwarded-For from 127.0.0.1, ::1 and FORWARDED_ALLOW_IPS, which bypasses D-10's `TRUST_PROXY_HEADERS` default of false in a real server (TestClient never passes through that layer). Every start command carries `--no-proxy-headers` (image CMD in 02-11, smoke script in 02-11, README in 02-12) and the in-app middleware of 02-07 is the only trust switch. 02-07 proves it with a real-uvicorn subprocess test (SYSTEMROOT passthrough) plus a default-flags negative control, and 02-11's static test pins the CMD. D-18's command gains this one flag, per D-10; no decision changes.
12. **Self-contained process guards.** The root pin guard in every plan is an inline `git rev-parse --show-toplevel` / `git branch --show-current` check; no plan depends on a session-specific file outside the repository. Plan 02-03 stops and asks the orchestrator if uv 0.13.1 cannot be installed (no silent lock-version downgrade).
13. **Push discipline.** Executors never push; the orchestrator pushes only at plan boundaries, so plan 02-02's deliberate red rename commit is never pushed on its own.
14. **Validation ownership and open criteria.** Plan 02-12 Task 3 step 6 flips this file to validated when the phase gate passes; ROADMAP criteria 2 and 4 remain 'pending human confirmation' (OPEN human-verify items) and are never reported as passed before the Actions run and the docker build and run are confirmed.
