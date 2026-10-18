---
phase: 02-engineering-baseline
reviewed: 2026-10-18
depth: deep
status: fixed
findings:
  confirmed: 8
  fixed: 8
  dismissed: 15
---

# Phase 2: Code Review Report

Review of the Phase 2 code (`src/truthtrail`, `tests`, `.github/workflows/ci.yml`, `Dockerfile`,
`pyproject.toml`). Candidates were reproduced by the reviewers; the confirmed ones are fixed
below (fix status is recorded in the Fix status section at the end). The two CORS candidates
(Retry-After only, and Retry-After plus X-Cache) are one defect and are fixed together as WR-01.

## Confirmed findings

### CR-01: Limiter keys buckets by request URL, so LimitedRouter does not rate limit path-parameter routes

**File:** `src/truthtrail/api/limits.py:25`
**Severity:** critical
**Issue:** slowapi 0.1.10 defaults `key_style` to `"url"`, so `build_limiter()` scopes every bucket
by the concrete request path, not by route function as the `LimitedRouter` docstring claims. A
`LimitedRouter` route `GET /items/{item_id}` with `RATE_LIMIT_V1=2/minute` gave `[200, 200, 429, 429]`
for one id, but fifty distinct ids from one IP all returned 200. Phase 3 and 4 routes such as
`/v1/claims/{id}` would be silently unlimited (the fail-open case D-23 exists to prevent). Latent
today because no `/v1` route exists yet.
**Fix:** pass `key_style="endpoint"` and add a probe test with a path parameter.

### WR-01: CORS exposes no response headers, so a browser frontend cannot read Retry-After or X-Cache

**File:** `src/truthtrail/api/app.py:91`
**Severity:** warning
**Issue:** `CORSMiddleware` is built without `expose_headers`, so a 429 or 503 carries
`Retry-After` and `Access-Control-Allow-Origin` but no `Access-Control-Expose-Headers`. Browsers
hide non-safelisted headers from cross-origin JavaScript, so the Vite dashboard sees `Retry-After`
(the documented 429/503 contract) and `X-Cache` as null. (Two candidates, one asking for
`Retry-After` and one for `Retry-After` plus `X-Cache`; merged.)
**Fix:** `expose_headers=["Retry-After", "X-Cache"]` plus a CORS test that asserts it.

### WR-02: No single-flight on cache miss: concurrent identical queries each hit the provider

**File:** `src/truthtrail/api/analyze.py:91`
**Severity:** warning
**Issue:** The handler does `cache.get`, then `_compute` outside the lock, then `cache.put`. Twenty
concurrent `GET /analyze?query=Bitcoin` requests from twenty IPs all returned `X-Cache: miss` and
the provider was called 20 times instead of once. The cache protects the roughly 100 requests per
day free quota (D-11); the per-IP limiter does not stop this.
**Fix:** per-key in-flight future so one caller fetches and the others wait for its result.

### WR-03: Readiness checks have no timeout, so one hung check starves all sync endpoints

**File:** `src/truthtrail/core/readiness.py:34`
**Severity:** warning
**Issue:** `run()` fails closed on exceptions and non-True results, but a check that blocks neither
fails nor times out. `/ready` is a sync `def` in the shared 40-thread pool and is not rate limited;
45 concurrent `/ready` requests against a blocking check made `/analyze` hang for more than 5 s.
**Fix:** run each check with a hard timeout; a check that is still running fails closed at once.

### WR-04: The 8 s retry budget can be overshot by the connect timeout (about 11 s)

**File:** `src/truthtrail/services/gnews.py:225`
**Severity:** warning
**Issue:** Each attempt passes `timeout=(min(3.05, remaining), min(10, remaining))`. urllib3 applies
connect and read timeouts separately, so one attempt can take about 3.05 + 8 s; `fetch_news`
raised `upstream_timeout` after 11.0 s in a reproduction. The README promises retries "inside an
overall 8 s budget".
**Fix:** cap the sum: connect gets at most half of the remaining budget, read gets the rest.

### WR-05: Per-IP limit does not bound total GNews usage; one client can exhaust the daily quota

**File:** `src/truthtrail/api/analyze.py:73`
**Severity:** warning
**Issue:** One client IP sending ten requests a minute with distinct queries makes ten upstream
calls a minute, because the 600 s cache only helps repeated queries. About ten minutes reach the
100 calls per day free-plan quota, after which every user gets 502 `upstream_forbidden`. There is
no global upstream budget, so the threat model's "10/min per IP, 600 s cache" mitigation does not
hold for unique queries.
**Fix:** a process-wide cap on upstream calls per window; when spent, answer 503 with Retry-After
before contacting the provider.

### WR-06: Cache-hit data_as_of replay is untested; a re-stamping hit passes the whole suite

**File:** `tests/test_cache.py:77`
**Severity:** warning
**Issue:** `test_hit_replays_the_original_data_as_of` only advances the injected cache clock;
`data_as_of` has one-second resolution, so a hit that re-stamped `data_as_of` with `now` still
passed (mutation reproduced: 512 passed).
**Fix:** store an `AnalyzeResponse` with an old `data_as_of` directly in the app cache and assert
the hit returns the old value.

### WR-07: docker job /health probe does not retry the connection reset Docker's port proxy returns

**File:** `.github/workflows/ci.yml:158`
**Severity:** warning
**Issue:** With Docker's default userland proxy, `127.0.0.1:8000` accepts the TCP connection and
drops it before uvicorn binds, so curl gets exit 56 or 52. `--retry-connrefused` only covers
refused connections; the probe makes one attempt and can fail on a healthy image.
**Fix:** add `--retry-all-errors` to the probe (and pin it in the static workflow test).

## Dismissed candidates (not confirmed; no change made)

These were raised as candidates but not confirmed for fixing in this pass. They stay open as
informational notes.

- IN-01 `src/truthtrail/core/boot.py:69`: `FORWARDED_ALLOW_IPS` entries are not validated; a hostname is silently never trusted.
- IN-02 `src/truthtrail/core/cascade.py:65`: `cascade_events_from` lets `OverflowError` escape for extreme timestamps.
- IN-03 `src/truthtrail/api/app.py:91`: CORS preflight rejections are `text/plain` 400, not problem+json (documented known limitation in `tests/test_cors.py`).
- IN-04 `src/truthtrail/api/app.py:33`: OpenAPI description says every response carries provenance, but `/health` and `/ready` 200 bodies do not.
- IN-05 `src/truthtrail/core/boot.py:49`: CORS origin validator accepts entries a browser never sends (fail closed).
- IN-06 `src/truthtrail/api/health.py:21`: `HEAD /health` and `HEAD /ready` return 405 although CORS advertises HEAD.
- IN-07 `pyproject.toml:64`: coverage ratchet is enforced by a comment only.
- IN-08 `tests/test_openapi_contract.py:118`: expected Phase 1 test edits table omits one real edit.
- IN-09 `tests/test_no_legacy_imports.py:21`: both legacy-isolation proofs miss computed dynamic imports.
- IN-10 `pyproject.toml:73`: frozen-file exclusions are not force-excluded.
- IN-11 `tests/test_container_files.py:162`: Dockerfile CR guard is vacuous, and nothing pins `.gitattributes`.
- IN-12 `Dockerfile:21`: HEALTHCHECK honours ambient proxy variables for the loopback probe.
- IN-13 `README.md:132`: `scripts/smoke_app.py` is presented as a check but nothing runs it.
- IN-14 `Dockerfile:1`: floating `# syntax=docker/dockerfile:1` frontend undermines digest pinning.
- IN-15 `pyproject.toml:82`: blanket `S` ignore for tests hides more than the assert rule.

## Fix status

All eight confirmed findings are fixed, one atomic commit each, on `claude/sleepy-lovelace-13aums`
(not pushed). The 15 dismissed candidates were deliberately left unchanged.

| ID | Status | Commit | What changed |
|----|--------|--------|--------------|
| CR-01 | fixed | `a60574b` | `build_limiter()` passes `key_style="endpoint"`; new probe test with a path-parameter route (six distinct ids give `[200, 200, 429, 429, 429, 429]`). |
| WR-01 | fixed | `d73326a` | `CORSMiddleware(expose_headers=["Retry-After", "X-Cache"])`; new CORS test asserts both on a 200 and a 429. |
| WR-02 | fixed | `b6c649e` | `AnalyzeCache.get_or_compute` single-flight (per-key future). One caller fetches; the others wait and report `X-Cache: hit`; a failure reaches every waiter and is never stored. Unit and HTTP tests (ten concurrent requests make one provider call). |
| WR-03 | fixed | `9a7ea8f` | Each readiness check runs in a daemon thread with a 2 s wait; a check still running fails closed at once and is never started twice; `KeyboardInterrupt` and `SystemExit` still propagate. Registry, `/ready` and shared-run tests. |
| WR-04 | fixed | `a7b7be1` | Per attempt, connect is at most half of the remaining budget and read is the rest, so connect plus read never exceeds the budget (first attempt `(3.05, 4.95)`). DNS time and slow-drip reads remain documented limitations. Two tests that encoded the old `(3.05, 8.0)` tuple were retargeted to the stronger sum invariant and the change is recorded as row 10 of the Phase 1 test edits table in `02-VALIDATION.md` (`test_upstream_errors.py`). |
| WR-05 | fixed (bounded, not eliminated) | `ec0ea31` | New `UpstreamBudget` (100 calls per rolling day, process-wide, in memory, constant `UPSTREAM_BUDGET`): a live cache miss spends one unit before the provider is contacted; once spent it answers 503 `upstream_budget_exhausted` with `Retry-After`. Cache hits and demo mode cost nothing. Residual risk: one client can still spend the shared budget (users then see 503 instead of 502 and the window slides instead of resetting at the provider's midnight); the cap guarantees the service never overruns the provider quota. It is a constant, not a setting, to keep the ten-name environment contract unchanged. A per-address bucket for IPv6 /64 clients is not addressed. |
| WR-06 | fixed | `0f58c1e` | New test stores an `AnalyzeResponse` stamped 2020 in the app cache and asserts the hit serves that exact `data_as_of` with no upstream call (mutation-checked: a re-stamping hit fails it). |
| WR-07 | fixed (static check only) | `f70b25d` | docker job `/health` probe uses `--retry-all-errors`; `test_docker_health_probe_retries_connection_resets` pins it. No Docker daemon or GitHub Actions run was available, so the job itself was not run. |

Verification ran in the main checkout (no worktree): full suite 533 passed, 10 xfailed (no XPASS),
`ruff check .`, `ruff format --check .`, `mypy`, `scripts/copy_guard.py` and the gitleaks scan
(`scripts/gitleaks_scan.sh`) all clean at the end of the pass.
