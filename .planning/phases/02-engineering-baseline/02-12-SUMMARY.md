---
phase: 02-engineering-baseline
plan: 12
subsystem: infra
tags: [coverage, ci, github-actions, pip-audit, docker, readme, validation]

requires:
  - phase: 02-engineering-baseline
    provides: plan 02-11 Dockerfile and smoke script; plans 02-03/02-04 uv lock, ruff, mypy; plan 02-10 Hypothesis ci profile
provides:
  - "[tool.coverage.run]/[tool.coverage.report] with branch coverage of truthtrail and fail_under = 96 (measured 98.342 minus the floor rule)"
  - "ci.yml with seven jobs: copy-guard, gitleaks (untouched), tests (--cov --hypothesis-profile=ci), lint, typecheck, audit, docker"
  - "tests/test_ci_workflow.py static contract for all seven jobs (17 tests)"
  - "README rewritten for the packaged service (uv and Windows setup, operations, config table, Docker, CI, layout)"
  - "tests/test_readme_env_table.py and tests/test_coverage_config.py"
  - "02-VALIDATION.md flipped to validated / nyquist_compliant / wave_0_complete"
affects: [phase-verification, 03-data-ingestion]

actuals:
  tokens: 21000
  tasks: 3
  commits: 4
plan_head_before: ab7c3a29a298d55918ee7473b79402541b12bd69
plan_head_after: 22574c71fbd8c6fd60851213d5ddec5d11a03ddd

tech-stack:
  added: []
  patterns:
    - "Coverage gate lives in [tool.coverage.report], enforced by --cov in CI only (not addopts)"
    - "Workflow drift caught by a PyYAML static test instead of a runner"

key-files:
  created:
    - tests/test_coverage_config.py
    - tests/test_readme_env_table.py
  modified:
    - pyproject.toml
    - .github/workflows/ci.yml
    - tests/test_ci_workflow.py
    - README.md
    - .planning/phases/02-engineering-baseline/02-VALIDATION.md

key-decisions:
  - "fail_under = 96: measured total 98.342 percent (650 statements, 6 missed, 134 branches, 7 partial), floor 98, minus 2"
  - "ENG-04 and ENG-05 stay Pending in REQUIREMENTS.md: a green Actions run and a real docker build and run have not happened (D-26); ENG-02, ENG-03 were already complete"
  - "pip-audit found no vulnerability, so no --ignore-vuln was added"

requirements-completed: []

duration: 25min
completed: 2026-10-17
status: complete
---

# Phase 2 Plan 12: Coverage Gate, Seven CI Jobs, README and Phase Gate Summary

**Branch coverage of `truthtrail` is gated at 96 percent (measured 98.342), CI now has the seven roadmap jobs including pip-audit and a container smoke job, the README documents the packaged service with uv and native Windows setup, and every local phase-gate command passes. The Actions run and the real docker build are NOT verified here.**

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | d195efb | test(coverage): gate pytest-cov at measured baseline minus 2 (branch coverage of truthtrail) |
| 2 | 1a23a5f | ci: add lint, typecheck, audit and docker jobs; coverage and Hypothesis ci profile in tests job; extend static workflow contract |
| 3 | 8af75c9 | docs: README for the packaged service (uv and Windows setup, operations, Docker, CI); env-table test |
| 3 (step 6) | 22574c7 | docs(02): mark phase 2 validation contract validated (phase gate passed) |

## Coverage (Task 1, ENG-03, D-15)

- Measured on the final tree with `pytest --cov=truthtrail --cov-branch --hypothesis-profile=ci`: TOTAL 98.342 percent (650 statements, 6 missed; 134 branches, 7 partial). Lowest modules: `api/catchall.py` 93 percent, `core/boot.py` 94 percent, `services/gnews.py` 96 percent.
- Chosen `fail_under = 96` (floor(98.342) = 98, minus 2). The comment in pyproject.toml says it may only be raised. `--cov` is not in `addopts`.
- `pytest --cov --hypothesis-profile=ci -q`: pass ("Required test coverage of 96.0% reached. Total coverage: 98.34%").
- Negative control (not committed): `pytest --cov --cov-fail-under=100 ...` exit status 1, so the gate mechanism fires.
- `tests/test_coverage_config.py`: 4 tests (source and branch, integer fail_under 1..100, no `--cov` in addopts, legacy not measured).

## CI (Task 2, ENG-04, ENG-05, D-17, D-26)

Local proof of every command the jobs run, executed before the workflow edit (uv 0.11.32 locally; CI pins 0.13.1):

| Command | Result |
|---|---|
| `uv lock --check` | exit 0 |
| `ruff check .` / `ruff format --check .` | exit 0 / exit 0 |
| `mypy` | exit 0 (22 source files) |
| `uv export --locked --no-emit-project --all-groups --format requirements-txt -o FILE` then `pip-audit -r FILE --require-hashes --disable-pip --progress-spinner off` | export exit 0; "No known vulnerabilities found", exit 0 |
| `pytest --cov --hypothesis-profile=ci -q` | 509 passed, 10 xfailed (at that commit) |
| `scripts/copy_guard.py` | clean |

- ci.yml: the gitleaks job is textually unchanged (the staged diff had hunks only at the header comment and the `tests` job). `tests` now runs `uv run --locked pytest --cov --hypothesis-profile=ci -q`. New `lint`, `typecheck`, `audit` (timeout 10) and `docker` (timeout 15, checkout only, no uv, no secrets). The docker job builds `truthtrail:ci`, runs it detached with `DEMO_MODE=true`, probes `/health` (with retry), `/ready` and `/analyze` (asserts `"synthetic":true`), asserts `id -u` is not 0 and that spread_simulator, users, risk_analyzer and pytest are not importable (`python -I`), and ends with an `if: always()` step that prints logs and stops the container (it cannot mask an earlier failure; the job still fails).
- `tests/test_ci_workflow.py`: 17 tests (was 9): seven job names, per-job key commands, setup-uv `0.13.1` for the five uv jobs, SHA pins with version comments, timeouts, `persist-credentials: false` on all seven checkouts, read-only permissions, no `secrets.`, no `continue-on-error`, dated comment required if `--ignore-vuln` is ever used, docker cleanup step last and `always()`.
- Best-effort pin check: `git ls-remote https://github.com/astral-sh/setup-uv refs/tags/v9.0.0` returned `c771a70e6277c0a99b617c7a806ffedaca235ff9`, equal to the pinned SHA.

## README (Task 3, ENG-02, FND-06, D-05)

Rewritten with the sections listed in the plan: status, `/analyze` contract, `/health`, `/ready`, the empty `/v1` mount, operational behaviour (rate limits, cache and `X-Cache`, retry bounds, CORS, proxy trust and why every start command passes `--no-proxy-headers`, the rate-limit warning-line note), the ten-variable configuration table, uv setup for Linux/macOS and a separate native Windows PowerShell block, dependency groups, the root `main.py` shim, quality gates and the seven CI job names, Docker, layout, and what is not built yet. Opening honesty statement and "flag for human review" kept; no key values. `tests/test_readme_env_table.py`: 3 tests (ten names in the example file, each in the README, required strings).

## Phase gate (all run on the final tree, after commit 8af75c9 unless noted)

| Command | Result |
|---|---|
| `pytest --cov --hypothesis-profile=ci -q` | exit 0; 512 passed, 10 xfailed, no XPASS; coverage 98.34 percent vs gate 96 (the 22574c7 commit only edits a planning file) |
| `ruff check .`, `ruff format --check .` | exit 0, exit 0 (59 files formatted) |
| `mypy` | exit 0 |
| `scripts/copy_guard.py` | exit 0 (clean, 160 OpenAPI strings) |
| `scripts/generate_demo_fixture.py --check` | exit 0 |
| `uv lock --check` | exit 0 |
| uv export + pip-audit pair | exit 0, no known vulnerabilities |
| `install_gitleaks.sh`, `gitleaks_scan.sh` from the floor to HEAD, `gitleaks_selftest.sh` | exit 0; scan clean over 104 commits after the floor and the working tree (re-run on HEAD 8af75c9); selftest "all scenarios passed" |
| frozen-file comparisons vs 9b5b085 (`risk_analyzer.py` to `keyword_baseline.py`, `spread_simulator.py`, `users.py` to `legacy/`), `--ignore-cr-at-eol` | all three exit 0 |
| smoke script on a fresh `--locked --no-dev --no-editable` install | exit 0: health, ready, analyze demo (X-Cache miss then hit), installed non-editable and legacy/dev/train not importable |
| `tests/test_no_hardcoded_credentials.py` | 13 passed before each commit; added-lines 32-hex scan found 0 each time |
| Clean tree, no stray `__pycache__` outside `.venv` | `git status --short` empty after each commit |

Test counts: 497 passed, 10 xfailed at the start of this plan; 512 passed, 10 xfailed at the end (+4 coverage config, +8 CI contract, +3 README = +15). The 274 Phase 1 tests remain; the 10 strict xfails are unchanged and none XPASS.

## Validation contract flip

Every phase-gate command exited 0 and the tree was clean after the README commit, so `02-VALIDATION.md` now has `status: validated`, `nyquist_compliant: true`, `wave_0_complete: true`. All Wave 0 files were checked with `test -e` (none missing) and ticked, the 28 Per-Task rows are `green` (each plan SUMMARY, 02-01 to 02-11, is `status: complete`; this plan's rows proven above), the sign-off boxes are ticked, and the approval line reads "executor-validated on 2026-10-17; ROADMAP criteria 2 and 4 pending human confirmation (see Manual-Only Verifications)". No Manual-Only item is marked verified.

## ROADMAP success criteria status

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | `src/truthtrail` serves the same endpoints; Phase 1 tests pass through the refactor; simulator and users off the live path | passed | `tests/test_openapi_golden.py`, full suite 512 passed / 10 xfailed, `tests/test_no_legacy_imports.py`, `tests/test_legacy_frozen.py`, `tests/test_main_shim.py`, frozen-file blob comparisons |
| 2 | CI runs ruff, mypy, pytest, pip-audit and the secret scan, green on the final commit | **pending human confirmation (OPEN)** | Automated half only: workflow configured, `tests/test_ci_workflow.py`, every job command run locally. No Actions run has been observed |
| 3 | pytest + hypothesis suite with ordering invariants; coverage reported | passed | `tests/test_cascade_properties.py` (ci profile), `tests/test_cascade_gate.py`, coverage 98.34 percent vs gate 96 |
| 4 | `docker build` succeeds and a running container answers `/health`; `/ready` 503 on a failing registered check | **pending human confirmation (OPEN)** | Automated half only: `tests/test_container_files.py`, `scripts/smoke_app.py` run against a non-editable install, `tests/test_health_ready.py` (injected failing check). No docker build or container run happened (no daemon) |
| 5 | CORS restricted, 429, TTL cache, timeouts and bounded retries | passed | `tests/test_cors.py`, `test_rate_limit.py`, `test_v1_limits.py`, `test_cache.py`, `test_retries.py` |

## Non-gating follow-ups (OPEN, harvested by the verifier)

1. Green GitHub Actions run of all seven jobs (copy-guard, gitleaks, tests, lint, typecheck, audit, docker) on the final pushed commit; research assumptions A1-A4 (Docker and curl on ubuntu-latest, setup-uv v9.0.0 inputs, YAML details) are unverified. The docker job log should show a successful build, `/health` ok, `/ready` ready, a synthetic `/analyze` body, a non-zero uid and no importable legacy modules; the tests job should print the coverage table above the gate.
2. A real `docker build -t truthtrail:ci .`, `docker run -d -p 8000:8000 -e DEMO_MODE=true truthtrail:ci`, `curl -fsS http://127.0.0.1:8000/health` and `docker exec <id> id -u` (expect not 0) on a machine with Docker.
3. Owner run of the README Windows block on native Windows 11 (PowerShell, Python 3.13): uv install, delete old `.venv`, `uv sync`, `uv run pytest -q`, start with `DEMO_MODE` true and open `/health` (research A5).
4. Repository settings: confirm whether the status checks `copy-guard`, `gitleaks` and `tests` are required for merging (names deliberately unchanged).
5. Still open from earlier plans: owner review of the dependency table in `02-03-SUMMARY.md` (D-26).

## Decision and requirement coverage

Requirements (this plan's share):

| Item | Where covered |
|---|---|
| ENG-02 (README setup) | README uv, Windows and dependency-group sections; `tests/test_readme_env_table.py` |
| ENG-03 (coverage reported and gated) | `[tool.coverage.*]`, `tests/test_coverage_config.py`, tests job `--cov` |
| ENG-04 (ruff, mypy, pytest, pip-audit, secret scan on every push) | ci.yml seven jobs, `tests/test_ci_workflow.py`; Actions run OPEN |
| ENG-05 (docker job) | ci.yml `docker` job; real build OPEN |

Requirement coverage across the phase: ENG-01 plans 02-01, 02-02; ENG-02 plans 02-03, 02-12; ENG-03 plans 02-10, 02-12; ENG-04 plans 02-03, 02-04, 02-12; ENG-05 plans 02-06, 02-11, 02-12; ENG-06 plans 02-05, 02-07, 02-08, 02-09.

Decision-to-plan coverage map (D-xx: plans; the entries naming 02-12 are implemented by this plan):

| Decision | Plans | Decision | Plans |
|---|---|---|---|
| D-01 | 02-01, 02-02, 02-11 | D-14 | 02-03 |
| D-02 | 02-01, 02-02, 02-04 | D-15 | 02-04 (ruff, mypy), 02-10 (Hypothesis profile), **02-12 (coverage gate)** |
| D-03 | 02-10 | D-16 | 02-01 |
| D-04 | 02-02, 02-05 | D-17 | 02-03, **02-12 (lint, typecheck, audit, docker jobs)** |
| D-05 | 02-02, **02-12 (README documents the shim and its removal)** | D-18 | 02-11 |
| D-06 | 02-05, 02-06, 02-07 | D-19 | 02-10 |
| D-07 | 02-06 | D-20 | 02-01, 02-05, 02-06, 02-07, 02-08 |
| D-08 | 02-01, 02-05, 02-06, 02-07 | D-21 | 02-01, 02-02 |
| D-09 | 02-05 | D-22 | 02-02, 02-03, 02-11 |
| D-10 | 02-07 (README in 02-12 explains why every start command passes `--no-proxy-headers`) | D-23 | 02-05, 02-07, 02-08 |
| D-11 | 02-08 | D-24 | 02-03 |
| D-12 | 02-09 | D-25 | 02-02, 02-03, 02-04, 02-05 |
| D-13 | 02-05 (Literal[False]), 02-09 (Retry-After clamp) | D-26 | 02-03, 02-11, **02-12 (job names kept, gitleaks untouched, human-verify items recorded as non-gating)** |

## Dependencies and packages

No package was added, removed or re-pinned by this plan (`uv.lock` and the dependency tables of `pyproject.toml` are untouched; the only `pyproject.toml` change is the two coverage tables). The plan therefore requires no new package review table; the owner review of the dependency table in `02-03-SUMMARY.md` (D-26) remains open from earlier. pip-audit on the exported lock found no known vulnerability, so no `--ignore-vuln` exists.

## Re-verification after executor interruption (2026-10-18)

The first executor stopped on an API usage limit after commit 22574c7 and before the state updates. A second executor re-checked everything at HEAD 22574c7 without redoing any task. Results, all fresh runs at that commit:

| Check | Result |
|---|---|
| `pytest --cov --hypothesis-profile=ci -q` | exit 0; 512 passed, 10 xfailed, no XPASS; total 98.34 percent against the gate 96 ("Required test coverage of 96.0% reached") |
| Negative control `--cov-fail-under=100` | exit 1 (gate fires) |
| `ruff check .`, `ruff format --check .`, `mypy` | exit 0, 0, 0 (59 files formatted, 22 source files) |
| `scripts/copy_guard.py`, `generate_demo_fixture.py --check`, `uv lock --check` | exit 0 each |
| `uv export ...` and `pip-audit ... --require-hashes --disable-pip` | exit 0; no known vulnerabilities |
| `install_gitleaks.sh`, `gitleaks_scan.sh` from the floor a5dd825 to HEAD (105 commits plus working tree), `gitleaks_selftest.sh` | exit 0; clean; all scenarios passed |
| Frozen-file comparisons vs 9b5b085 (three, `--ignore-cr-at-eol`) | exit 0 |
| `smoke_app.py` against a fresh `--locked --no-dev --no-editable` install | exit 0 (health, ready, analyze demo with X-Cache miss then hit, non-editable install, legacy/dev/train not importable) |
| Wave 0 file list (`test -e` on every path) | none missing |
| ci.yml review | seven jobs; gitleaks job absent from the diff against ab7c3a2 (only the header comment and the `tests` job changed); docker job fails on any failing step and its `if: always()` cleanup is the last step |

Verdict on the 22574c7 validation flip: legitimate. Every phase-gate command exits 0 at HEAD, Wave 0 files all exist and the tree was clean; no revert was needed. The flip marks no Manual-Only item as verified. The fresh run adds one honest caveat that the flip text already carries: status `validated` is executor-validated only, and ROADMAP criteria 2 and 4 remain open.

State updates in this docs commit: STATE.md (plan 12 of 12 executed, status ready for verification, decision and metric rows), ROADMAP.md (plan 02-12 ticked, 12/12 plans, phase row still "In Progress"), state.json. The phase is NOT marked complete and REQUIREMENTS.md is unchanged (ENG-04 and ENG-05 stay Pending, see Deviations).

## Deviations from Plan

- **ENG-04 and ENG-05 not marked complete in REQUIREMENTS.md.** The plan frontmatter lists ENG-02 to ENG-05, but both requirements need a run that cannot happen here (green Actions run; docker build and run), and the plan itself forbids reporting criteria 2 and 4 as passed. ENG-02 and ENG-03 were already complete. Same stance as plan 02-11 for ENG-05.
- **Vacuous guard removed from the test draft.** While writing `tests/test_ci_workflow.py` I replaced a weak "ignore-vuln implies some comment" assertion with a dated-comment check conditional on `--ignore-vuln` being used in the audit job; and narrowed the old `"requirements" not in text` check to `"requirements.txt"` because the audit job legitimately uses `uv export --format requirements-txt`. The intent (no pip/requirements-file installs) is unchanged.
- **Checkout count assertion tightened** from `>= 3` to exactly the seven jobs.
- Test additions exceed the floor (17 workflow tests vs 12 required).
- **Executor interrupted by an API usage limit** after the four task commits; the SUMMARY, state updates and docs commit were completed by a second executor after a full re-verification (see above). `commits: 4` in the frontmatter counts the four task commits (measured with `git rev-list --count`); the docs commit that carries this SUMMARY follows and `plan_head_after` is the last task commit.

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model. T-02-39 (SHA pins, read-only permissions, timeouts, no secrets, enforced statically), T-02-40 (no `secrets.`, docker job keyless, gitleaks untouched and run locally), T-02-41 (no advisory present; dated `--ignore-vuln` rule enforced by a test), T-02-42 (gate derived from measurement, config test, negative control) and T-02-SC (no package added; `uv.lock` unchanged) are implemented.

## Self-Check: PASSED

- Files pyproject.toml, .github/workflows/ci.yml, README.md, tests/test_coverage_config.py, tests/test_ci_workflow.py, tests/test_readme_env_table.py, 02-VALIDATION.md: FOUND
- Commits d195efb, 1a23a5f, 8af75c9, 22574c7 are ancestors of HEAD: FOUND
