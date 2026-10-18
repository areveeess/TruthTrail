---
phase: 02-engineering-baseline
verified: 2026-10-18T12:00:00Z
status: human_needed
score: 5/5 roadmap success criteria verified in-container (criteria 2 and 4 each carry a human-only residual); 0 failed
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
human_verification:
  - test: "Build the image and run it: `docker build -t truthtrail:verify .` then `docker run -d -e DEMO_MODE=true -p 8000:8000 truthtrail:verify`; `curl -fsS http://127.0.0.1:8000/health`, `/ready`, `/analyze?query=x`; `docker exec <c> id -u`; `docker inspect --format '{{.State.Health.Status}}' <c>`."
    expected: "Build succeeds; /health returns 200 {\"status\":\"ok\"}; /ready returns 200; /analyze returns synthetic:true fixture data; uid is not 0; the HEALTHCHECK reaches healthy; spread_simulator, users, risk_analyzer and pytest are not importable inside the image."
    why_human: "No Docker daemon in this container. ROADMAP criterion 4 (docker build succeeds and the running container answers /health) and ENG-05 cannot be proven here. The installed-package smoke (scripts/smoke_app.py, run here, passed) and a green CI docker job on 65aabff are strong indirect evidence only."
  - test: "Push HEAD (fc59504, currently one unpushed commit ahead of origin/claude/sleepy-lovelace-13aums) and confirm the `ci` workflow run on that exact SHA is green on all seven jobs."
    expected: "copy-guard, gitleaks, tests, lint, typecheck, audit and docker all conclude success for fc59504."
    why_human: "ROADMAP criterion 2 says CI is green on the phase's final commit. GitHub reports no check runs for fc59504 because it was never pushed (API: 'No commit found for SHA'). The latest remote tip 65aabff is green on all seven jobs; fc59504 differs from it only by adding .planning/phases/02-engineering-baseline/02-SECURITY.md (git diff --stat: 1 file, 134 insertions), so risk is very low, but the criterion is literally about the final commit."
  - test: "On native Windows PowerShell run the README commands: `winget install --id=astral-sh.uv -e`, `uv sync`, the DEMO_MODE start command, open http://127.0.0.1:8000/health, and `uv run pytest`."
    expected: "uv installs, sync succeeds on Python 3.13 from uv.lock, the service starts, /health answers, and the suite passes (tests that spawn subprocesses pass SYSTEMROOT)."
    why_human: "Linux container only. The README itself states the Windows commands have not been run by the maintainer on Windows. CONTEXT 'Specifics' makes the Windows path an owner requirement."
  - test: "In the GitHub repository settings (Settings, Branches, branch protection / rulesets) check which status checks are marked required, if any."
    expected: "Any required check names are among the unchanged `copy-guard`, `gitleaks`, `tests` or the new `lint`, `typecheck`, `audit`, `docker`; no stale name (e.g. an old job id) is required, which would block merges forever."
    why_human: "Repository settings are not visible from the container or the checked-in files. D-26 kept the three original job names precisely because a protection rule may require them; the live rule can only be read in the GitHub UI or with admin API access."
---

# Phase 2: Engineering Baseline Verification Report

**Phase Goal:** The service is a properly packaged, tested, containerised and CI-guarded FastAPI app, with a versioned `/v1` router mount point that Phases 3 and 4 can extend independently, so data and ML code land on a solid base.
**Verified:** 2026-10-18 against HEAD `fc595044cedf3589c04e5cb1e1137697bcfea624` (branch `claude/sleepy-lovelace-13aums`, clean working tree)
**Status:** human_needed
**Re-verification:** No - initial verification

Everything that can be proven inside this container was proven by running it, not by reading SUMMARY.md. No code gap was found. Status is `human_needed` and not `passed` because four criteria fragments (docker build and run, GitHub Actions on the exact final commit, a Windows run, branch-protection check names) cannot be verified here, as the task requires.

## Goal Achievement

### Observable Truths (ROADMAP success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Code lives in `src/truthtrail` (api, services, schemas, core), serves the same endpoints, Phase 1 characterization tests still pass unchanged, `spread_simulator.py` and `users.py` unreachable from any route or import | VERIFIED | Package tree present (22 mypy source files). Golden OpenAPI snapshot regenerated by me from the Phase 1 commit `402d8c8` equals `tests/golden/openapi_phase1.json` (True); the live document differs only by `/health`, `/ready`, 429 entries and `Problem.synthetic` const (test_openapi_golden passes). The 10 Phase 1 xfails (8 keyword defects plus 2 simulator defects) still xfail with strict mode, no XPASS. Phase 1 test edits beyond import paths are exactly two assertion edits (timeout tuple and a cache-avoiding query string), both tabulated in 02-VALIDATION.md with the decision that forced them (D-12, D-11). Legacy modules sit in `legacy/` outside `src/`; the built wheel contains no `legacy`, `users` or `spread_simulator`; `tests/test_no_legacy_imports.py` (AST walk, fresh-interpreter `sys.modules` check, serving-only path) passes. Fresh-clone `--no-dev` environment: `find_spec` for spread_simulator, users, risk_analyzer, pytest, sklearn, numpy all absent. |
| 2 | Fresh clone installs from the uv lockfile on Python 3.13 with training and serving sets split; GitHub Actions runs ruff, mypy, pytest, pip-audit and the secret scan on every push and is green on the final commit | VERIFIED in-container; CI on exact final commit is a HUMAN item | Cloned the repo at HEAD to a scratch dir and ran `uv sync --locked --no-dev --no-editable`: Python 3.13.16, installs cleanly, `scripts/smoke_app.py` passes all four checks. Serving closure (exported with `--no-dev`) has 27 packages and none of scikit-learn, numpy, pytest, hypothesis, ruff, mypy, responses; the `train` group (scikit-learn, numpy, scipy, joblib, ...) is in `uv.lock` only. `uv lock --check` clean. `requirements*.txt` and `pytest.ini` are gone. `ci.yml` has the seven jobs (copy-guard, gitleaks, tests with `--cov --hypothesis-profile=ci`, lint, typecheck, audit, docker); GitHub check runs for `65aabff` (remote tip) are all `success`: lint, copy-guard, tests, typecheck, gitleaks, audit, docker. HEAD `fc59504` is unpushed, so no run exists for it (see human item 2). A prior run on `0541300` failed (the WR-07 docker probe race), later fixed by `f70b25d`. |
| 3 | pytest + hypothesis suite covers the API and reports coverage; property tests prove events come back ordered by `observed_at` and a child is never earlier than its parent | VERIFIED | `pytest --cov --hypothesis-profile=ci -q`: 533 passed, 10 xfailed, 0 failed. Coverage 98.51 percent (branch) against `fail_under = 96` ("Required test coverage of 96.0% reached"). `tests/test_cascade_properties.py` has four `@given` properties over generated forests with timestamp ties, shuffled arrival order and permuted ids: sorted permutation with parents first, idempotent and arrival-order independent, valid cascades accepted, a child moved one microsecond before its parent rejected with `CascadeError`. `core/cascade.py` is real logic (depth-aware total ordering, cycle and duplicate detection), and `validate_cascade` is a hard gate on demo fixture load (`load_demo_fixture`, lifespan). |
| 4 | `docker build` succeeds and the container answers `/health` 200; `/ready` returns 503 whenever a registered dependency check fails (proved by a test with an injected failing check) | /ready 503 VERIFIED; docker build and run is a HUMAN item | I injected a `False`-returning check and a raising check through `app.state.readiness.register`: `/ready` 503, `application/problem+json`, detail "Not ready: database, secret_leaker." with no exception text (an injected connection string with a fake password never appears), provenance members present, `/health` stays 200 meanwhile; with no checks `/ready` is 200 `{"status":"ready","checks":{}}`. Real uvicorn on loopback: `/health` 200, `/ready` 200. Dockerfile reviewed: multi-stage, python:3.13-slim pinned by digest, `uv sync --frozen --no-dev`, non-root uid 10001, HEALTHCHECK on `/health`, CMD with `--no-proxy-headers`, no secrets, `.dockerignore` excludes legacy, tests, scripts, .planning. No Docker daemon here, so the build and the running container are not proven by me (the CI docker job on `65aabff` succeeded). |
| 5 | (Phase boundary, from CONTEXT) a versioned `/v1` router mount point that Phases 3 and 4 can extend independently | VERIFIED | `api/v1.py`: `LimitedRouter(prefix="/v1")` plus a `V1_REGISTRARS` list that later phases append to. Probe: a registrar adding `/v1/probe/{item}` with `RATE_LIMIT_V1=3/minute` gives `[200,200,200,429,429]` across five different path-parameter values (proves the CR-01 `key_style="endpoint"` fix, which a URL-keyed bucket would have failed), 429 is problem+json with `Retry-After`. `register_default_checks` is the empty extension hook for the Phase 3 database and Phase 4 model checks. |

**Score:** 5/5 truths verified in the container; two of them (2, 4) have a remainder that only a human can close (items 1 and 2 below). 0 behavior-unverified.

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| ENG-01 | `src/truthtrail` package; legacy modules off the live path | SATISFIED | Truth 1 |
| ENG-02 | uv lockfile, Python 3.13, training and serving split | SATISFIED | Truth 2 (`requires-python >=3.13,<3.14`, `.python-version` 3.13, `default-groups=["dev"]`, `train` group excluded from default sync and image) |
| ENG-03 | pytest + hypothesis suite, invariants, coverage | SATISFIED | Truth 3 |
| ENG-04 | CI runs ruff, mypy, pytest, pip-audit, secret scan on every push | SATISFIED for definition and for `65aabff`; NEEDS HUMAN for final commit `fc59504` | Local equivalents all pass (below). `REQUIREMENTS.md` still shows ENG-04 Pending, which is correct until item 2 is closed. |
| ENG-05 | Dockerfile builds and runs; `/health` liveness; `/ready` 503 on unavailable dependency | PARTIAL, NEEDS HUMAN | `/health` and `/ready` behaviour proven; Dockerfile build and run not provable here (item 1). `REQUIREMENTS.md` shows Pending, which is correct. The database and model checks are deferred to Phases 3 and 4 by design. |
| ENG-06 | CORS restricted, rate limited, TTL-cached, outbound timeouts and bounded retries | SATISFIED | Probes below |

No orphaned requirements: ENG-01 to ENG-06 are exactly the six mapped to Phase 2.

### Tooling Gates (run by me in this container)

| Gate | Command | Result |
|------|---------|--------|
| Tests plus coverage | `uv run --locked pytest --cov --hypothesis-profile=ci -q` (GNEWS_API_KEY unset) | 533 passed, 10 xfailed; coverage 98.51 percent >= `fail_under` 96 |
| Lint | `ruff check .` and `ruff format --check .` | All checks passed; 60 files already formatted |
| Types | `mypy` (strict, `src/truthtrail`) | Success: no issues in 22 source files |
| Lock | `uv lock --check` | Resolved 73 packages, no change |
| Dependency audit | `uv export --locked --no-emit-project --all-groups` then `pip-audit -r ... --require-hashes --disable-pip` | "No known vulnerabilities found" (exit 0) |
| Copy guard | `scripts/copy_guard.py` | clean (160 OpenAPI strings) |
| Secret scan | `/tmp/truthtrail-gitleaks/gitleaks` via `scripts/gitleaks_scan.sh <bin> a5dd8257e920923677c60e70611a6f36d87747b2 HEAD a5dd8257e920923677c60e70611a6f36d87747b2` | working tree 153 files plus range a5dd825..fc59504 (116 commits): clean, exit 0. Selftest: all scenarios passed. No key printed. |
| Hypothesis | included in the pytest run under the `ci` profile (200 examples, derandomized, no database) | passed |
| OpenAPI snapshot | `tests/test_openapi_golden.py` plus my own regeneration from commit `402d8c8` | pass; golden equals regenerated Phase 1 document |
| Installed-package smoke | clone at HEAD, `uv sync --locked --no-dev --no-editable`, `scripts/smoke_app.py` | health, ready, analyze demo (miss then hit), non-editable install with package data and no legacy/dev/train modules: all ok |
| Real server | `uvicorn truthtrail.main:app --no-proxy-headers` on loopback | `/health` 200, `/ready` 200; with no key and no DEMO_MODE the process exits with code 3 ("Application startup failed") |
| Wheel contents | `uv build --wheel` | contains the 22 package modules and `data/demo_analyze.json`; no legacy |

### Behavioural Probes (TestClient, provider fully mocked with `responses`; fake key; no real network)

Independent script run: 67 of 67 checks passed. Highlights:

| Area | Observation |
|------|-------------|
| Health / ready | `/health` 200; `/ready` 200 with no checks; 503 problem+json with an injected failing and a raising check; no exception text leaked |
| Rate limit | Default `/analyze` limit: ten 200s then 429 on the 11th. 429 is `application/problem+json`, `code: rate_limited`, `status: 429`, `synthetic: false`, `source_status: rate_limited`, `data_as_of: null`, `Retry-After: 60`. `/health` and `/ready` exempt (80 calls all 200). A fresh app has fresh limiter state |
| CORS | Allowed origin echoed; disallowed origin gets no `Access-Control-Allow-Origin`; no credentials header; preflight GET ok, preflight POST 400; unset `CORS_ORIGINS` means no cross-origin access; `*`, trailing-slash and `ftp://` origins are rejected at construction. CORS headers present on 429, 422, 404, upstream 502 and an unexpected 500 (500 is problem+json and does not leak the exception text). `Retry-After` and `X-Cache` are exposed to browsers |
| Cache | miss, hit, hit for `Parking`, `parking`, ` PARKING `; the provider was called once; a hit keeps the original `data_as_of`; a different query misses; TTL boundary: hit at 599 s, miss at 601 s; defaults TTL 600 and 256 entries. Upstream 401 is not cached (provider called on every request) and the first success after recovery is a fresh miss with no `X-Cache` on the error responses |
| Retry bound | Upstream 500/502/503/504: exactly 3 attempts then 502. Upstream 401/403/404/429: exactly 1 attempt. Connect timeout and read timeout: 3 attempts then 503. TLS error: 1 attempt. A 503 followed by a 200 succeeds on attempt 2 |
| Slow upstream | With a fake clock where each call burns its whole timeout: first attempt gets timeout (3.05, 4.95) = the 8 s budget, 1 attempt, elapsed 8.00 s, 503 with `Retry-After`. With calls that take 3 s each: 3 attempts, each timeout shrunk to fit the remainder (3.05+4.95, 2.33+2.33, 0.53+0.53), total elapsed 8.00 s, never above the 8 s budget |
| Spoofed X-Forwarded-For | TestClient with a fixed peer, a different `X-Forwarded-For`, `X-Real-IP` and `Forwarded` on each of 12 requests, with and without `TRUST_PROXY_HEADERS=true`: requests 11 and 12 are 429 in both cases (the spoof is not the key; with trust on, an untrusted peer is ignored). Real uvicorn (`--no-proxy-headers`) on loopback with a different `X-Forwarded-For` per request: ten 200s then two 429s |
| DEMO_MODE gate | `true`: synthetic fixture, `synthetic: true`, `source_status: fixture`, zero provider calls, no key needed. Unset, `false`, `0`, `no`, empty: live path, `synthetic: false`. No key and no demo: startup fails fast with `ConfigurationError` (uvicorn exit code 3 confirmed above). Control characters in the query: 422 |
| `/v1` mount | Limited by route, not by URL (see truth 5) |

### Decision Spot-Check (D-01 to D-26)

| Decision | Status | Evidence |
|----------|--------|----------|
| D-01/D-02/D-21 legacy and baseline frozen | HELD | `legacy/spread_simulator.py` and `legacy/users.py` present outside `src/`; `keyword_baseline.py` rule logic unchanged (10 strict xfails fail for the original reasons); sha pins enforced by `tests/test_legacy_frozen.py` (passes); ruff excludes `legacy` and the formatter excludes `keyword_baseline.py` |
| D-03/D-19 cascade functions | HELD | `order_events`, `validate_cascade` pure and property-tested; validation (not reordering) on demo load |
| D-04/D-05/D-06 layout, shim, `/v1` | HELD | `truthtrail.main:app`; root `main.py` is the two-line shim; `/analyze` unchanged at root; empty `/v1` mounted |
| D-07 readiness registry | HELD | proven above; WR-03 adds a 2 s per-check timeout |
| D-09 CORS | HELD | proven above; CORSMiddleware outermost of the non-proxy middlewares |
| D-10 rate limit | HELD | in-memory slowapi, peer-IP key, `TRUST_PROXY_HEADERS` default false, `--no-proxy-headers` in the Dockerfile CMD, 10/min and 60/min, 429 problem+json with `Retry-After` |
| D-11 cache | HELD | proven above, plus single-flight (WR-02) and a process-wide upstream budget of 100/day (WR-05, 503 `upstream_budget_exhausted`) |
| D-12/D-13 retries and folded items | HELD | proven above; `Retry-After: 0` clamps to 1; `Problem.synthetic` is `Literal[False]` |
| D-14/D-24 uv and pins | HELD | exact pins in `pyproject.toml`, `uv.lock` committed |
| D-15/D-25 ruff, mypy, coverage | HELD | gates above |
| D-16 line endings | HELD | `.gitattributes` present (`* text=auto eol=lf`, `*.sh` LF) |
| D-17/D-26 CI | HELD | seven jobs, original three names kept, actions SHA-pinned with version comments, `persist-credentials: false`, job timeouts, read-only permissions (`tests/test_ci_workflow.py`) |
| D-18/D-22 Dockerfile and fixture location | HELD (build not runnable here) | Dockerfile as described; fixture lives in `src/truthtrail/data/` and ships in the wheel |
| D-23 per-app state | HELD | limiter, cache, readiness registry and upstream budget on `app.state`; two apps never share state (probe) |

### Key Link / Wiring Check

| From | To | Status | Details |
|------|----|--------|---------|
| `main.py` shim | `truthtrail.main:app` | WIRED | `tests/test_main_shim.py`; `uvicorn main:app` still works |
| `create_app()` | health, analyze, v1 routers; problem handlers; CORS; catch-all; optional proxy middleware | WIRED | read in `api/app.py` and exercised by the probes |
| `/analyze` handler | limiter, cache (`get_or_compute`), upstream budget, `fetch_news`, `analyze_risk` | WIRED | the probes drive every branch |
| `ReadinessRegistry` | `/ready` | WIRED | injected checks change the answer |
| `validate_cascade` | demo fixture load and lifespan | WIRED | `load_demo_fixture` calls it per result; lifespan calls the loader in demo mode |
| `LimitedRouter` | `/v1` registrars | WIRED | route registered through a registrar is limited |

### Anti-Patterns Found

None blocking. Scan of files changed since Phase 1 for `TBD`, `FIXME`, `XXX`, `TODO`, `HACK`, `PLACEHOLDER`: no matches. No hard-coded credentials in `src` or `scripts`. `.env.example` has names only. Informational, already tracked in `02-REVIEW.md` as dismissed or open-low: IN-06 `HEAD /health` and `HEAD /ready` answer 405 although CORS lists HEAD (the Docker HEALTHCHECK and CI probes use GET, so unaffected); IN-03 CORS preflight rejections are text/plain 400.

### Observations Worth Knowing (not gaps)

- Phase 1 tests were not literally byte-unchanged: besides import paths and ruff formatting, two assertions changed, the first-attempt timeout tuple (necessary because the 8 s retry budget caps the read timeout, D-12 and review WR-04) and one query string changed to avoid the new TTL cache (D-11). Both are recorded in `02-VALIDATION.md` "Expected Phase 1 test edits". I treat criterion 1's "unchanged" as satisfied in spirit; the owner may want to look at the table.
- My own probe for "no key and no demo fails fast" asserts only that `ConfigurationError` is raised; the exit code 3 was confirmed separately with a real uvicorn process.
- `02-REVIEW.md` reports 8 confirmed findings, all fixed, and `02-SECURITY.md` reports 53 of 53 threats closed at `65aabff`. I did not re-audit every threat; I confirmed the behaviours that matter most (CR-01, WR-01, WR-02, WR-03 symptoms) through the probes above.

### Human Verification Required

See the `human_verification` list in the frontmatter (four items): docker build and run; GitHub Actions on the exact final commit `fc59504` (unpushed); a Windows run of the README commands; branch-protection required-check names.

### Gaps Summary

No gaps: every roadmap success criterion that can be exercised in this container is met by running code, and nothing was found missing, stubbed or unwired. The phase cannot be marked `passed` only because docker, the Actions run on the very last commit, Windows and branch-protection settings are outside what this environment can prove. After human items 1 and 2 are closed, ENG-04 and ENG-05 can be flipped to Complete and Phase 2 checked off in `ROADMAP.md`.

---

_Verified: 2026-10-18T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
