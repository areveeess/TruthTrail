---
phase: 02-engineering-baseline
plan: 09
subsystem: api
tags: [retry, backoff, timeout, budget, requests, responses, fake-clock]

requires:
  - phase: 02-engineering-baseline
    provides: plan 02-08 TTL cache and limiter in front of the GNews adapter; create_app() and client_factory
provides:
  - "Bounded retry loop in services/gnews.py: 3 attempts, backoff 0.3 s then 0.6 s plus jitter in [0, 0.1], 8 s total budget, per-attempt (connect, read) timeout capped by the remaining budget"
  - "Injectable module seams _monotonic, _sleep and _jitter; autouse no_real_sleep fixture so no test sleeps"
  - "Retry-After clamp max(1, min(int(value), 3600)) closing review item IN-03 (D-13)"
affects: [02-10, 02-11, 02-12, 03]

actuals:
  tokens: 14000
  tasks: 2
  commits: 2
plan_head_before: 9bcf5d0652d61ff6918052afd63d56161873bc8c
plan_head_after: 5b8833c99e689a388c3cb65dc34a0fce0d85554e

tech-stack:
  added: []
  patterns:
    - "Explicit retry loop in our own code (not urllib3 Retry) so the policy, the budget and the Phase 1 error mapping stay in one reviewable place"
    - "Time is injected through module-level seams called via module globals at call time; tests patch them with a FakeClock, never real sleeping"
    - "Each attempt is classified into a frozen _Failure (status, code, detail, retryable, retry_after, upstream_status); the last failure is mapped through _fail exactly as in Phase 1"

key-files:
  created:
    - tests/test_retries.py
  modified:
    - src/truthtrail/services/gnews.py
    - tests/conftest.py
    - tests/test_upstream_errors.py
    - tests/test_cache.py

key-decisions:
  - "fetch_news was split into _request_once (transport, returns a response or a _Failure), _classify_status (non-200 mapping) and the loop; the Phase 1 mappings were moved verbatim"
  - "The fallback failure used when the budget is exhausted before any attempt can start is upstream_timeout 503 with Retry-After 30"

requirements-completed: [ENG-06]

status: complete
completed: 2026-10-17
---

# Phase 2 Plan 09: Bounded Retries and Time Budget for the GNews Call Summary

**The GNews adapter retries only transient failures (timeouts, non-TLS connect errors, HTTP 500/502/503/504) at most three attempts in total inside an 8 second budget, never retries 4xx/429/3xx/bad payloads, maps the final failure exactly as Phase 1 did, and clamps a provider `Retry-After: 0` to 1 second; every claim is proven with an injected fake clock and no test sleeps.**

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | 9374d5d | feat(retry): bounded retry loop with 8 s budget and injected clock seams; autouse no-sleep fixture |
| 2 | 5b8833c | test(retry): prove the retry bound end to end; clamp provider Retry-After 0 to 1 (D-12, D-13) |

## What was built

- **Retry loop (Task 1).** Constants `BACKOFFS = (0.3, 0.6)`, `MAX_ATTEMPTS = 3`, `BUDGET = 8.0`, `CONNECT_TIMEOUT = 3.05`, `READ_TIMEOUT = 10.0`, `RETRY_STATUSES = frozenset({500, 502, 503, 504})`; the old `TIMEOUT` tuple is gone. Per attempt `remaining = BUDGET - elapsed`, no attempt starts at `remaining <= 0`, and the request timeout is `(min(3.05, remaining), min(10, remaining))`. A retry is skipped when `elapsed + delay >= BUDGET`. One INFO line per retry carries only the attempt number, the code and the upstream status. `except Timeout` stays before `except ConnectionError`; `SSLError` keeps 503 `upstream_unreachable` without a retry, any other `RequestException` keeps 502 `upstream_bad_response` without a retry. The known limitation (per-read timeouts let a drip-feeding server exceed the budget) is documented in a code comment.
- **Seams and fixture.** `_monotonic`, `_sleep`, `_jitter` (the last with `# noqa: S311 - backoff jitter, not security`) are module functions called through module globals. `tests/conftest.py` has an autouse `no_real_sleep` fixture that makes `_sleep` a no-op; `tests/test_retries.py` overrides it with its own `fake_clock`.
- **Tests (`tests/test_retries.py`, 35 collected).** Constants and real jitter bounds; the 500, 502, 200 sequence (sleeps 0.3 and 0.6, jitter 0.05 adds to each); always 500/502/503/504 stop at exactly 3 calls with 502 `upstream_bad_response` and the status logged; always ConnectTimeout/ReadTimeout (503 `upstream_timeout`, Retry-After 30, 3 calls); always ConnectionError/ProxyError (503 `upstream_unreachable`, 3 calls); SSLError, 400, 401, 403, 404, 429 (Retry-After 7 kept), 301, 302 and 200 with bad payloads make exactly 1 call and no sleep; the exact first-attempt timeout `(3.05, 8.0)`; slow upstream stopped by the budget (1 call when each attempt burns its full read timeout, 2 calls when it burns 4.0 s, retry skipped when the delay would reach 8 s); recorded read timeouts shrink, stay positive and never exceed the caps with total fake time at most 8.0; every attempt sends the same `X-Api-Key` with `allow_redirects=False` (observed with a spy on `requests.get`, because `responses` does not record that argument); through `GET /analyze`: always-503 gives 502 and 3 calls, always-ConnectTimeout gives 503 with `Retry-After: 30` and 3 calls, a slow upstream gives 503 with fewer than 3 calls, real elapsed time under 2 s in each, a 302 is neither followed nor retried; logging across retries has INFO lines with `attempt=1` and `attempt=2`, a final WARNING, no key and no URL in any adapter message, and the raised error has `__cause__` None and `__suppress_context__` True with a leaky exception text that carries the key and URL.
- **Retry-After clamp (Task 2, D-13 / IN-03).** `_retry_after` returns `max(1, min(int(value), MAX_RETRY_AFTER))` for numeric ASCII values; non-numeric and HTTP-date values still give 30 and 99999 still caps at 3600. Two FAILURE_CASES rows (`Retry-After: 0` and `00`, expecting header `1`) were added and seen failing before the change.

## Verification

- `pytest -q`: 455 passed, 10 xfailed, no XPASS (418 passed at the start; 447 after Task 1, +29; 455 after Task 2, +8: 6 new retry tests, 2 new FAILURE_CASES rows). Full suite time about 10 s, unchanged.
- `ruff check`, `ruff format --check`, `mypy` (21 source files) and `scripts/copy_guard.py` clean. `tests/test_no_hardcoded_credentials.py`: 13 passed before each commit; the added-lines scan for 32-hex strings found nothing.
- No Docker daemon or GitHub Actions run is involved; nothing here claims a docker build or a CI run passed.

## Deviations from Plan

### The one deliberately edited Phase 1 assertion

`tests/test_upstream_errors.py::test_request_uses_timeout_header_and_fixed_params`: the whole-tuple equality `timeout == (3.05, 10)` became two conditions (connect timeout equals 3.05; read timeout greater than 7.9 and at most 8.0) with a comment citing the 8 s budget (D-12). This is row 1 of "Expected Phase 1 test edits" in 02-VALIDATION.md. The exact `(3.05, 8.0)` is asserted with a fake clock in `tests/test_retries.py`. Apart from the two added FAILURE_CASES rows (additions, not edits) no other assertion in that file changed.

### Auto-fixed Issues

**1. [Rule 1 - Bug] Phase 2 cache test counted outbound calls that retries now multiply**
- **Found during:** Task 1 full-suite run
- **Issue:** `tests/test_cache.py::test_errors_are_never_cached` (a plan 02-08 test, not a Phase 1 test) ended with `len(mock_gnews.calls) == 2`. With D-12 the failing 503 and ConnectTimeout cases make 3 attempts before the error is reported, so the total is 4; the 401 case stays at 2.
- **Fix:** Added a `failed_attempts` parameter (1 for the 401, 3 for the 503 and the timeout, with a comment citing D-12) and assert `len(calls) == failed_attempts + 1`. The meaning is unchanged: the error is not cached, the next request goes upstream once and succeeds; the assertion is now exact rather than loosened.
- **Files modified:** tests/test_cache.py (not listed in the plan's `files_modified`)
- **Commit:** 9374d5d

### Other notes

- `responses` does not record `allow_redirects` in `req_kwargs`, so the "never follows redirects on any attempt" claim is checked by a spy around `requests.get` rather than by reading the recorded request.
- Test counts exceed the plan's floors (14 and 18 collected) because of parametrisation.
- ENG-06 is now marked complete: CORS (02-05), rate limit (02-07), TTL cache (02-08) and timeouts with bounded retries (this plan) are all implemented and tested.

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model. T-02-32 (at most 3 attempts, no retry of 4xx/429/3xx/bad payload, 8 s budget, exact call counts asserted), T-02-33 (attempt number, code and upstream status only; `from None`; key, host and URL absence asserted across attempts), T-02-34 (`allow_redirects=False` on every attempt, a 3xx is called once) are implemented and tested. T-02-35 is accepted and documented in a code comment. No packages were added (T-02-SC).

## Self-Check: PASSED

- Files src/truthtrail/services/gnews.py, tests/test_retries.py, tests/conftest.py, tests/test_upstream_errors.py, tests/test_cache.py: FOUND
- Commits 9374d5d and 5b8833c are ancestors of HEAD: FOUND
