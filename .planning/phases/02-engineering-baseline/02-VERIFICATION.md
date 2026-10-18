---
phase: 02-engineering-baseline
verified: 2026-10-18T12:36:00Z
status: passed
score: 5/5 roadmap success criteria verified (own runs, CI evidence, owner UAT); 0 failed
covered_files:
  - ".dockerignore"
  - ".github/workflows/ci.yml"
  - ".planning/phases/02-engineering-baseline/02-01-PLAN.md"
  - ".planning/phases/02-engineering-baseline/02-01-SUMMARY.md"
  - ".planning/phases/02-engineering-baseline/02-02-PLAN.md"
  - ".planning/phases/02-engineering-baseline/02-02-SUMMARY.md"
  - ".planning/phases/02-engineering-baseline/02-03-PLAN.md"
  - ".planning/phases/02-engineering-baseline/02-03-SUMMARY.md"
  - ".planning/phases/02-engineering-baseline/02-04-PLAN.md"
  - ".planning/phases/02-engineering-baseline/02-04-SUMMARY.md"
  - ".planning/phases/02-engineering-baseline/02-05-PLAN.md"
  - ".planning/phases/02-engineering-baseline/02-05-SUMMARY.md"
  - ".planning/phases/02-engineering-baseline/02-06-PLAN.md"
  - ".planning/phases/02-engineering-baseline/02-06-SUMMARY.md"
  - ".planning/phases/02-engineering-baseline/02-07-PLAN.md"
  - ".planning/phases/02-engineering-baseline/02-07-SUMMARY.md"
  - ".planning/phases/02-engineering-baseline/02-08-PLAN.md"
  - ".planning/phases/02-engineering-baseline/02-08-SUMMARY.md"
  - ".planning/phases/02-engineering-baseline/02-09-PLAN.md"
  - ".planning/phases/02-engineering-baseline/02-09-SUMMARY.md"
  - ".planning/phases/02-engineering-baseline/02-10-PLAN.md"
  - ".planning/phases/02-engineering-baseline/02-10-SUMMARY.md"
  - ".planning/phases/02-engineering-baseline/02-11-PLAN.md"
  - ".planning/phases/02-engineering-baseline/02-11-SUMMARY.md"
  - ".planning/phases/02-engineering-baseline/02-12-PLAN.md"
  - ".planning/phases/02-engineering-baseline/02-12-SUMMARY.md"
  - "Dockerfile"
  - "legacy/spread_simulator.py"
  - "legacy/users.py"
  - "main.py"
  - "pyproject.toml"
  - "scripts/copy_guard.py"
  - "scripts/generate_demo_fixture.py"
  - "scripts/gitleaks_scan.sh"
  - "scripts/gitleaks_selftest.sh"
  - "scripts/install_gitleaks.sh"
  - "scripts/smoke_app.py"
  - "src/truthtrail/__init__.py"
  - "src/truthtrail/api/__init__.py"
  - "src/truthtrail/api/analyze.py"
  - "src/truthtrail/api/app.py"
  - "src/truthtrail/api/cache.py"
  - "src/truthtrail/api/catchall.py"
  - "src/truthtrail/api/health.py"
  - "src/truthtrail/api/limits.py"
  - "src/truthtrail/api/problems.py"
  - "src/truthtrail/api/v1.py"
  - "src/truthtrail/core/__init__.py"
  - "src/truthtrail/core/boot.py"
  - "src/truthtrail/core/cascade.py"
  - "src/truthtrail/core/config.py"
  - "src/truthtrail/core/errors.py"
  - "src/truthtrail/core/readiness.py"
  - "src/truthtrail/data/demo_analyze.json"
  - "src/truthtrail/main.py"
  - "src/truthtrail/schemas/__init__.py"
  - "src/truthtrail/schemas/models.py"
  - "src/truthtrail/services/__init__.py"
  - "src/truthtrail/services/gnews.py"
  - "src/truthtrail/services/keyword_baseline.py"
  - "uv.lock"
covered_digest: "v3:sha256:8eaa0a26745276ea4b3e3bc7e8bd6a42fd76ddf3b41de77d5eb6ab439298d978"
behavior_unverified: 0
overrides_applied: 0
re_verification: false
advisory:
  - finding: "README.md line 85 still says the Windows commands 'have not been run by the maintainer on a Windows machine yet'. The owner UAT (02-UAT.md test 1) ran them on native Windows PowerShell on 2026-10-18 and they passed."
    category: other
    reason: "Documentation is stale relative to the UAT. Not a roadmap criterion, so it does not block. Edit the sentence (and keep tests/test_readme_env_table.py green) in the next docs touch."
    evidence_status: "README.md:85 read; 02-UAT.md test 1 result: pass"
  - finding: "REQUIREMENTS.md still shows ENG-04 and ENG-05 as Pending (checkbox and traceability table) and ROADMAP.md still shows Phase 2 unchecked."
    category: other
    reason: "Bookkeeping that follows this verification: with status passed, ENG-04 and ENG-05 can be flipped to Complete and Phase 2 checked off. This verifier does not edit those files."
    evidence_status: "REQUIREMENTS.md lines 24, 25, 115, 116 and ROADMAP.md line 20 read"
---

# Phase 2: Engineering Baseline Verification Report

**Phase Goal:** The service is a properly packaged, tested, containerised and CI-guarded FastAPI app, with a versioned `/v1` router mount point that Phases 3 and 4 can extend independently, so data and ML code land on a solid base.
**Verified:** 2026-10-18 against HEAD `0e90b03b5e2703074bb1f3cbfafdb8b9a01932ee` (branch `claude/sleepy-lovelace-13aums`, equal to `origin/claude/sleepy-lovelace-13aums`, clean working tree)
**Status:** passed
**Re-verification:** No. This report was regenerated from scratch; the earlier report (written against `fc59504`, status `human_needed`) was not used as evidence.

The previous report had four human items. Their disposition now:

| Earlier human item | Now |
|---|---|
| Docker build and run | Closed by real CI evidence (docker job, run 39127140928 and the HEAD run), with stated limits below |
| CI green on the exact final commit | Closed: the HEAD run is green on all seven jobs (checked by me with `gh`) |
| Windows run of the README commands | Closed by owner UAT (owner-provided evidence, not run by me) |
| Branch-protection required-check names | Closed by owner UAT (owner-provided evidence: no status checks are required) |

No code gap was found. Everything below labelled "ran" was executed by me in this container at HEAD; "CI" means a GitHub Actions result I read through the GitHub API with `gh`; "owner" means evidence supplied by the repository owner in `02-UAT.md`, which I did not and cannot reproduce.

## Goal Achievement

### Observable Truths (ROADMAP success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Code lives in `src/truthtrail` (api, services, schemas, core), serves the same endpoints, Phase 1 characterization tests still pass unchanged, `spread_simulator.py` and `users.py` are unreachable from any route or import | VERIFIED | Package tree present (mypy strict covers 22 source files). I added a git worktree at the Phase 1 completion commit `402d8c8`, imported its `main.app`, regenerated its OpenAPI document and compared it with `tests/golden/openapi_phase1.json`: equal (True). The live document differs from it only by the permitted entries (`/health`, `/ready`, 429 entries, `Problem.synthetic` const), enforced by `tests/test_openapi_golden.py` (passes). The 10 Phase 1 xfails (8 keyword defects, 2 simulator defects) still xfail under strict mode: 10 xfailed, no XPASS. Diff of Phase 1 tests against `402d8c8`: apart from import paths, ruff reformatting, the fixture path and an `app_module` fixture parameter, exactly two assertions changed, the first-attempt timeout tuple (the 8 s retry budget caps the read timeout, D-12 and WR-04) and one query string (avoids the new TTL cache, D-11); both are tabulated in `02-VALIDATION.md`. Legacy modules sit in `legacy/` outside `src/`; the wheel I built (`uv build --wheel`) has 29 `truthtrail/` entries and zero matches for legacy, users or spread_sim; `git ls-files` shows no `requirements*.txt`, `pytest.ini` or root `risk_analyzer.py`. In the fresh `--no-dev --no-editable` clone, `find_spec` for spread_simulator, users, risk_analyzer, legacy, pytest, sklearn and numpy are all absent. `tests/test_no_legacy_imports.py` and `tests/test_legacy_frozen.py` pass. |
| 2 | A fresh clone installs from the uv lockfile on Python 3.13 with training and serving sets split; GitHub Actions runs ruff, mypy, pytest, pip-audit and the secret scan on every push and is green on the final commit | VERIFIED | Ran: `git clone` of HEAD to a scratch dir, `uv sync --locked --no-dev --no-editable` gives Python 3.13.16 and installs cleanly; `scripts/smoke_app.py --python .venv/bin/python` passes all four checks. `uv export --locked --no-dev --no-emit-project` contains none of scikit-learn, numpy, pytest, hypothesis, ruff, mypy, responses (grep count 0); the `train` group lives in `uv.lock` only. `ci.yml` triggers on `push` and `pull_request` and defines seven jobs; actions are SHA-pinned. CI: run 39127140928 on `33acd1b` concluded success on all seven jobs (gitleaks, copy-guard, tests, docker, typecheck, lint, audit). CI: run 39127710210 on the current HEAD `0e90b03` is `completed`, `success`, all seven jobs success. `git diff --name-only 33acd1b HEAD` and `65aabff HEAD` outside `.planning/` are both empty, so the shipped code is identical across those runs. Step-level check of the HEAD run: lint ran `uv lock --check`, `ruff check`, `ruff format --check`; tests ran `pytest --cov --hypothesis-profile=ci`; typecheck ran `mypy`; audit exported the lock and ran pip-audit with `--require-hashes`; gitleaks installed the pinned binary, ran its selftest and the scan. Caveat from history: run 39105916724 on `0541300` failed (the WR-07 docker probe race), fixed in `f70b25d`. |
| 3 | pytest + hypothesis suite covers the API and reports coverage; property tests prove events come back ordered by `observed_at` and a child is never earlier than its parent | VERIFIED | Ran: `uv run --locked pytest --cov --hypothesis-profile=ci -q` with `GNEWS_API_KEY` unset: **533 passed, 10 xfailed**, 0 failed, 0 XPASS (strict xfails would fail the run), "Required test coverage of 96.0% reached. Total coverage: 98.51%" (branch coverage, 724 statements, 6 missed). `tests/test_cascade_properties.py` holds `@given` properties over generated forests with timestamp ties, shuffled arrival order and permuted ids (sorted permutation with parents first, idempotent and order independent, valid cascades accepted, a child moved before its parent rejected with `CascadeError`). `core/cascade.py` is real logic and `validate_cascade` is a hard gate on demo fixture load (`load_demo_fixture` in `api/analyze.py`, called from the lifespan in demo mode). The owner also ran the suite on native Windows: 533 passed, 10 xfailed in 21.38 s (owner). |
| 4 | `docker build` succeeds and the container answers `/health` 200; `/ready` returns 503 whenever a registered dependency check fails (proved by a test with an injected failing check) | VERIFIED (build and run via CI evidence; no Docker daemon here) | `/ready` 503: ran a TestClient probe that registers a check returning `False` and a check that raises `RuntimeError("postgres://u:SECRETPW@h/db")`: `/ready` 503 `application/problem+json`, detail "Not ready: database, secret_leaker.", neither `SECRETPW` nor `RuntimeError` appears in the body, `/health` stays 200, no checks gives 200 `{"status":"ready","checks":{}}`. Covered by `tests/test_health_ready.py` and `tests/test_readiness_registry.py` (pass). Real uvicorn from the fresh non-editable clone on loopback: `/health` 200, `/ready` 200, `/analyze?query=x` returns the labelled synthetic fixture; with no key and no `DEMO_MODE` the process exits with code 3 ("Application startup failed"). Docker, CI evidence: the `docker` job in run 39127140928 (and again in the HEAD run) succeeded on every step: build the image, start the container (`DEMO_MODE=true`, port 8000), probe `/health` (curl with retries), probe `/ready`, probe `/analyze` and grep `"synthetic":true`, assert `docker exec ... id -u` is not 0 and that `spread_simulator`, `users`, `risk_analyzer` and `pytest` are not importable inside the image. I read the Dockerfile myself: multi-stage, base `python:3.13-slim` pinned by sha256 digest, uv pinned by digest, `uv sync --frozen/--locked --no-dev --no-editable`, system user uid/gid 10001, `USER app`, no secrets, `CMD ... --no-proxy-headers`, `.dockerignore` excludes `legacy`, `tests`, `scripts`, `.planning`. |
| 5 | CORS accepts only configured origins, requests over the rate limit receive 429, repeated reads come from a TTL cache, and outbound HTTP uses timeouts and bounded retries (each proven by a test, including a mocked slow or failing upstream that stops after the retry bound) | VERIFIED | Ran an independent TestClient probe script (provider mocked with `responses`, fake key, the real GNews host never contacted): 38 of 39 checks passed; the single failing line was a wrong expectation in my own script (I asserted `source_status == "live"`; the schema's value is `"ok"`, `Literal["ok","empty","fixture"]`, and the observed value `ok` is correct), so all behaviours hold. Details are in the probe table below. The in-repo suites `test_cors.py`, `test_rate_limit.py`, `test_cache.py`, `test_retries.py` (469 lines, including the slow-upstream budget cases), `test_upstream_budget.py` and `test_v1_limits.py` all pass in the 533. |

The ROADMAP also states, in its goal, the `/v1` mount point extensible by Phases 3 and 4: **VERIFIED**. `api/v1.py` has `LimitedRouter(prefix="/v1")` and a `V1_REGISTRARS` list; my probe registered a route `/v1/probe/{item}` through a registrar with `RATE_LIMIT_V1=3/minute` and got `[200, 200, 200, 429, 429]` across five different path values (limited by route, not by URL). `register_default_checks` is the empty extension hook for the Phase 3 database and Phase 4 model checks.

**Score:** 5/5 success criteria verified, 0 behavior-unverified.

### What the CI docker job covers, and what it does not

Covers (CI evidence for criteria 2 and 4): the Dockerfile builds on a clean GitHub runner from the committed `uv.lock` and the digest-pinned base images (a failed pull of a pinned digest would fail the build); the container starts and the process inside it serves `/health` 200, `/ready` 200 and `/analyze` returning labelled synthetic data on the published port; the process runs as a non-zero uid; legacy, users, risk_analyzer and pytest are not importable in the image.

Does not cover (stated so nothing is overclaimed):
- The Dockerfile `HEALTHCHECK` instruction: the job probes with curl from the host and never reads `docker inspect ... State.Health.Status`, so the check reaching "healthy" is not observed. Its command is a `python -c urllib.request.urlopen('http://127.0.0.1:8000/health')` against an endpoint CI proves answers 200, so the risk is low, but it was not exercised.
- Image digest freshness or reproducibility: the job proves the pinned digests resolve and build, not that they are the latest or that a rebuild is byte-identical. Only the linux/amd64 runner platform was exercised.
- Live (non-demo) mode in the container: the job runs with `DEMO_MODE=true`; no real GNews call is made, by design.
- Image scanning and registry push: none exists in this phase.

None of these is a ROADMAP criterion wording ("`docker build` succeeds and the running container answers `/health` with 200"), so they are recorded as observations, not gaps.

### Owner-provided evidence (cited, not reproduced)

From `02-UAT.md` (status complete, 2/2 passed, 0 issues):
- Windows: the owner ran the README commands on native Windows PowerShell on 2026-10-18; pytest reported "533 passed, 10 xfailed in 21.38s" and `/health` answered `{"status":"ok"}`.
- Branch protection: the owner supplied a screenshot of the repository Branch rules: "Require status checks to pass" is not enabled (only restrict deletions and block force pushes are on), so no check name can go stale. Consequence worth knowing: with no required checks and no required pull request, CI is advisory by the owner's choice.

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| ENG-01 | `src/truthtrail` package; legacy modules off the live path | SATISFIED | Truth 1 |
| ENG-02 | uv lockfile, Python 3.13, training and serving split | SATISFIED | Truth 2 (`requires-python >=3.13,<3.14`, `.python-version` 3.13, `default-groups = ["dev"]`, `train` group not in serving closure or image) |
| ENG-03 | pytest + hypothesis suite, invariants, coverage | SATISFIED | Truth 3 |
| ENG-04 | CI runs ruff, mypy, pytest, pip-audit, secret scan on every push | SATISFIED | Truth 2: seven-job workflow on `push` and `pull_request`, green on the HEAD run; local equivalents all pass (table below). `REQUIREMENTS.md` still shows Pending: update it (advisory 2). |
| ENG-05 | Dockerfile builds and runs; `/health` liveness; `/ready` 503 when a dependency is unavailable | SATISFIED | Truth 4. The concrete database and model checks are deferred to Phases 3 and 4 by the ROADMAP's own criterion 4 wording; the registry that makes `/ready` fail closed exists and is tested. `REQUIREMENTS.md` still shows Pending: update it (advisory 2). |
| ENG-06 | CORS restricted, rate limited, TTL-cached, outbound timeouts and bounded retries | SATISFIED | Truth 5 |

No orphaned requirements: ENG-01 to ENG-06 are exactly the six mapped to Phase 2 in `REQUIREMENTS.md`, and the plans claim them.

### Tooling Gates (ran at HEAD)

| Gate | Command | Result |
|------|---------|--------|
| Tests plus coverage | `uv run --locked pytest --cov --hypothesis-profile=ci -q` (`GNEWS_API_KEY` unset) | 533 passed, 10 xfailed, no XPASS; coverage 98.51 percent against `fail_under = 96` |
| Lint | `ruff check .`, `ruff format --check .` | All checks passed; 60 files already formatted |
| Types | `mypy` (strict, `src/truthtrail`) | Success: no issues found in 22 source files |
| Lock | `uv lock --check` | Resolved 73 packages, no change |
| Dependency audit | `uv export --locked --no-emit-project --all-groups`, then `pip-audit -r <export> --require-hashes --disable-pip` | No known vulnerabilities found |
| Copy guard | `python scripts/copy_guard.py` | clean (160 OpenAPI strings) |
| Secret scan | `scripts/gitleaks_scan.sh /tmp/truthtrail-gitleaks/gitleaks a5dd8257e920923677c60e70611a6f36d87747b2 HEAD a5dd8257e920923677c60e70611a6f36d87747b2` | working tree (155 git-visible files) and range a5dd825..0e90b03 (119 commits): `gitleaks: clean`, exit 0; `gitleaks_selftest.sh`: all scenarios passed. Findings are redacted by the script; no key was printed |
| Installed-package smoke | clone at HEAD, `uv sync --locked --no-dev --no-editable`, `scripts/smoke_app.py` | health, ready, analyze demo (miss then hit), non-editable install with package data and legacy/dev/train not importable: all ok |
| Real server | `uvicorn truthtrail.main:app --no-proxy-headers` from that clone | `/health` 200, `/ready` 200, demo `/analyze` synthetic; no key and no demo: exit code 3 |
| Wheel contents | `uv build --wheel` | package modules and data only; no legacy, users or spread_sim |
| OpenAPI snapshot | worktree of `402d8c8`, regenerate and compare | equals `tests/golden/openapi_phase1.json` |

### Behavioural Probes (TestClient, provider mocked, fake key, no real network)

| Area | Observation |
|------|-------------|
| Health / ready | `/health` 200; `/ready` 200 with no checks; 503 problem+json with a failing and a raising check; no exception text or connection string leaked; `/health` unaffected |
| Rate limit | `/analyze` default 10 per minute: after ten 200s the next are 429 `application/problem+json` with `code: rate_limited`, `synthetic: false`, `source_status: rate_limited`, `data_as_of: null` and a `Retry-After`; 80 calls to `/health` and `/ready` all 200 (exempt) |
| Cache | miss then hit; `Parking`, ` parking ` share an entry; the provider was called once; a hit keeps the original `data_as_of`; the key never appears in a body. (Run-time TTL boundary, 600 s and 256 entries, is covered by `test_cache.py`, which passes.) |
| Retry bound | Upstream 500 and 503: exactly 3 attempts, then 502. Upstream 401, 404: 1 attempt, 502. Upstream 429: 1 attempt, 503. Read timeout: 3 attempts, 503. A 503 followed by a 200: success on attempt 2. No response body contained the key. |
| CORS | allowed origin echoed with no credentials header and `Retry-After` exposed; a disallowed origin gets no `Access-Control-Allow-Origin`; unset `CORS_ORIGINS` means no cross-origin access; `*`, a trailing-slash origin and `ftp://` are rejected at construction; a 404 carries CORS headers |
| Spoofed forwarding headers | 12 requests, each with a different `X-Forwarded-For` and `X-Real-IP`: requests 11 and 12 are 429 both with `TRUST_PROXY_HEADERS` unset and `true` (the spoof is not the rate-limit key) |
| DEMO_MODE gate | `true`: `synthetic: true`, `source_status: fixture`, zero provider calls, no key needed. `false`, `0`, `no`, empty: live path, `synthetic: false`. No key and no demo: `ConfigurationError` at startup (exit 3 with real uvicorn). Control character in the query: 422 |
| `/v1` mount | limited by route, not by URL (see the note under Observable Truths) |
| Per-app state | two `create_app()` calls do not share the limiter or the cache |

### Decision Spot-Check (D-01 to D-26)

| Decision | Status | Evidence |
|----------|--------|----------|
| D-01/D-02/D-21 legacy and baseline frozen | HELD | `legacy/spread_simulator.py`, `legacy/users.py` outside `src/`; `keyword_baseline.py` rules unchanged (10 strict xfails fail for the original reasons); sha pins enforced by `tests/test_legacy_frozen.py` (passes) |
| D-03/D-19 cascade functions | HELD | `order_events` and `validate_cascade` pure and property-tested; validation (not reordering) on demo load |
| D-04/D-05/D-06 layout, shim, `/v1` | HELD | `truthtrail.main:app`; root `main.py` is the compatibility shim (`from truthtrail.main import app`); `/analyze` stays at root; empty `/v1` mounted |
| D-07 readiness registry | HELD | proven above; 2 s per-check timeout (WR-03) |
| D-08/D-20 golden OpenAPI | HELD | regenerated from `402d8c8`; only permitted differences |
| D-09 CORS | HELD | proven above; methods GET, HEAD, OPTIONS; no credentials |
| D-10 rate limit | HELD | in-memory slowapi, peer-IP key, `TRUST_PROXY_HEADERS` default false, `--no-proxy-headers` in the Dockerfile CMD, 10/min and 60/min, 429 problem+json with `Retry-After` |
| D-11 cache | HELD | proven above; single-flight (WR-02) and a process-wide upstream budget (WR-05), both covered by passing tests |
| D-12/D-13 retries and folded items | HELD | proven above; `Retry-After: 0` clamps to 1 (test present); `Problem.synthetic` is `Literal[False]` (test present) |
| D-14/D-24 uv and pins | HELD | exact pins in `pyproject.toml` (fastapi 0.143.0, starlette 1.8.0, pydantic 2.14.0, pydantic-settings 2.15.0, uvicorn 0.54.0, requests 2.34.2, slowapi 0.1.10, cachetools 7.2.3), `uv.lock` committed |
| D-15/D-25 ruff, mypy, coverage | HELD | gates above; `fail_under = 96` |
| D-16 line endings | HELD | `.gitattributes`: `* text=auto eol=lf`, `*.sh text eol=lf` |
| D-17/D-26 CI | HELD | seven jobs, the original three names (`copy-guard`, `gitleaks`, `tests`) kept, actions SHA-pinned, `persist-credentials: false`, job timeouts, `permissions: contents: read` (`tests/test_ci_workflow.py` passes) |
| D-18/D-22 Dockerfile and fixture location | HELD | Dockerfile as described; fixture in `src/truthtrail/data/` and in the wheel; CI docker job proves the image serves it |
| D-23 per-app state | HELD | limiter, cache, readiness registry, upstream budget on `app.state`; two apps do not share state (probe) |

### Key Link / Wiring Check

| From | To | Status | Details |
|------|----|--------|---------|
| root `main.py` shim | `truthtrail.main:app` | WIRED | file read; `tests/test_main_shim.py` passes |
| `create_app()` | health, analyze and v1 routers; problem handlers; CORS; catch-all; optional proxy middleware | WIRED | read in `api/app.py`; every branch exercised by the probes |
| `/analyze` handler | limiter, cache, upstream budget, `fetch_news`, `analyze_risk` | WIRED | probes drive each branch |
| `ReadinessRegistry` | `/ready` | WIRED | injected checks change the answer |
| `validate_cascade` | demo fixture load and lifespan | WIRED | `load_demo_fixture` calls it per result; lifespan calls the loader in demo mode |
| `LimitedRouter` | `/v1` registrars | WIRED | a route added through a registrar is limited |

### Anti-Patterns Found

None blocking. A scan of `src`, `scripts`, `legacy`, `Dockerfile`, `.github`, `pyproject.toml` and `main.py` for `TBD`, `FIXME`, `XXX`, `TODO`, `HACK`, `PLACEHOLDER` found no matches; no hard-coded credential patterns in `src` or `scripts`; `.env.example` holds names only. Informational items already tracked in `02-REVIEW.md`: `HEAD /health` and `HEAD /ready` answer 405 although CORS lists HEAD (the Docker HEALTHCHECK and CI probes use GET, so unaffected); CORS preflight rejections are text/plain 400.

### Human Verification Required

None. Every item the earlier report listed is now closed by a CI run I read or by owner UAT that I cite as owner-provided. Nothing remains that only a human can close for the five ROADMAP criteria.

### Gaps Summary

No gaps. All five ROADMAP success criteria are met, backed by my own runs (tests, coverage, ruff, mypy, lock check, pip-audit, copy guard, gitleaks, installed-package smoke, real uvicorn, TestClient probes, Phase 1 OpenAPI regeneration), by GitHub Actions results (run 39127140928 on `33acd1b` and run 39127710210 on HEAD `0e90b03`, all seven jobs success) and by owner UAT. Two advisories (stale README sentence about Windows; `REQUIREMENTS.md` and `ROADMAP.md` still showing ENG-04, ENG-05 and Phase 2 as not complete) are bookkeeping, not goal failures.

Observation, not a gap: the owner's branch rules require no status checks and no pull request, so CI informs but does not gate merges. That is a deliberate owner setting and outside the Phase 2 criteria.

---

_Verified: 2026-10-18T12:36:00Z_
_Verifier: Claude (gsd-verifier)_
