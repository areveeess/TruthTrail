---
phase: 01-secure-honest-foundation
plan: 04
subsystem: api
tags: [rfc9457, problem-json, error-handling, pydantic, requests, input-validation, fastapi]

requires:
  - phase: 01-secure-honest-foundation
    provides: env-driven fetch_news(query, api_key) and Settings (01-02), Problem model and provenance members (01-03), mock_gnews/client_factory fixtures (01-01)
provides:
  - problems.py with PROBLEM_MEDIA_TYPE, UpstreamError, problem_body, problem_response and register_problem_handlers (five handlers)
  - GNews adapter that classifies every upstream outcome into a typed 502/503 error and validates the payload before use
  - SearchQuery validation on /analyze (trimmed, 1-200 characters, no control characters) answered with a bounded 422 problem+json
  - One RFC 9457 shape (plus synthetic/source_status/data_as_of) for upstream errors, 422, 404/405, not_configured and internal_error
affects: [01-05, 01-06, phase-02]

actuals:
  tokens: 7991
  tasks: 3
  commits: 3
plan_head_before: 77c10e3e6bfdd7fe20663a2951e003e129040a57
plan_head_after: 8cbf5c9afdeee5d49ae0f87d5181d11dcb533f5c

tech-stack:
  added: []
  patterns:
    - "Adapter raises UpstreamError(status, code, detail, retry_after) from None via a single _fail helper that logs only code and upstream status"
    - "Timeout handled before RequestException (ConnectTimeout is both); resp.json() called outside the transport try so non-JSON is 502, not 503"
    - "Pydantic private models (extra=ignore, AwareDatetime) validate the provider payload; publishedAt normalised to UTC Z"
    - "Handlers registered on Starlette's HTTPException so router 404/405 share the problem shape and keep Allow"
    - "Failure-table tests built from case factories receiving the article/payload builders and the fake key"

key-files:
  created:
    - problems.py
    - tests/test_upstream_errors.py
    - tests/test_request_validation.py
  modified:
    - gnews_fetcher.py
    - main.py
    - tests/test_char_analyze_legacy.py

key-decisions:
  - "403 stays 502 (D-07) with the distinct code upstream_forbidden and a detail naming credentials, subscription or daily quota"
  - "A response with articles null or absent is the valid empty result only when totalArticles == 0; anything else is 502 upstream_bad_response (D-19)"
  - "ConfigurationError at request time (lifespan bypassed) is answered 500 not_configured; the lifespan remains the real fail-fast path"
  - "Retry-After is honoured only for all-ASCII-digit values and capped at 3600, otherwise 30"

patterns-established:
  - "Every error body carries synthetic false, source_status and data_as_of null so errors cannot be mistaken for data"
  - "Error handlers never format an exception message: 500 logs only type(exc).__name__, adapter logs only code and upstream status"
  - "Legacy xfail rows lose their marker in the commit that fixes them (strict XPASS is a red build)"

requirements-completed: [FND-02, FND-04]

coverage:
  - id: D1
    description: "A GNews 401 makes /analyze answer 502 application/problem+json (upstream_unauthorized, upstream gnews), never 200, with no key, host or URL in body or logs"
    requirement: FND-02
    verification:
      - kind: integration
        ref: "tests/test_upstream_errors.py#test_gnews_401_returns_502_not_200"
        status: pass
      - kind: unit
        ref: "tests/test_upstream_errors.py#test_adapter_error_carries_no_key_or_url"
        status: pass
    human_judgment: false
  - id: D2
    description: "Full D-07/D-19 mapping: 401/403/400/404/500/503 and malformed payloads give 502; timeouts, connection errors and 429 give 503 with Retry-After (numeric honoured, capped 3600, otherwise 30); empty result with totalArticles 0 is valid"
    requirement: FND-02
    verification:
      - kind: integration
        ref: "tests/test_upstream_errors.py#test_upstream_failures_are_honest (24 rows)"
        status: pass
      - kind: unit
        ref: "tests/test_upstream_errors.py#test_adapter_success_shapes"
        status: pass
    human_judgment: false
  - id: D3
    description: "Outbound request uses timeout (3.05, 10), the X-Api-Key header and exactly q, lang, max=1; no log record or exception from the adapter contains the key, host or URL; every exception is raised from None"
    requirement: FND-02
    verification:
      - kind: unit
        ref: "tests/test_upstream_errors.py#test_request_uses_timeout_header_and_fixed_params"
        status: pass
      - kind: unit
        ref: "tests/test_upstream_errors.py#test_no_key_or_url_in_logs"
        status: pass
      - kind: unit
        ref: "tests/test_upstream_errors.py#test_adapter_exceptions_are_raised_from_none"
        status: pass
    human_judgment: false
  - id: D4
    description: "Missing, empty, whitespace-only, over-200 and control-character queries are rejected with a 422 problem+json carrying only loc/msg/type, never echoing input, with no upstream call; 200-character and trimmed queries are accepted"
    requirement: FND-04
    verification:
      - kind: integration
        ref: "tests/test_request_validation.py#test_invalid_query_is_422_problem (8 rows)"
        status: pass
      - kind: integration
        ref: "tests/test_request_validation.py#test_oversize_query_is_not_echoed"
        status: pass
      - kind: integration
        ref: "tests/test_request_validation.py#test_query_boundaries_accepted"
        status: pass
    human_judgment: false
  - id: D5
    description: "404, 405 (Allow header kept), not_configured and unexpected exceptions (generic detail, message never echoed) share the same problem+json shape and provenance members"
    requirement: FND-02
    verification:
      - kind: integration
        ref: "tests/test_request_validation.py#test_unknown_path_is_problem_json"
        status: pass
      - kind: integration
        ref: "tests/test_request_validation.py#test_wrong_method_keeps_allow_header"
        status: pass
      - kind: integration
        ref: "tests/test_request_validation.py#test_missing_configuration_is_not_configured"
        status: pass
      - kind: integration
        ref: "tests/test_request_validation.py#test_unexpected_error_is_generic_500"
        status: pass
    human_judgment: false
  - id: D6
    description: "Legacy characterization rows fixed by this plan lost their xfail markers in the same commits; only the empty-result row stays xfail for 01-05"
    requirement: FND-02
    verification:
      - kind: integration
        ref: "tests/test_char_analyze_legacy.py (11 passed, 1 xfailed: test_empty_result_is_not_fabricated)"
        status: pass
    human_judgment: false

duration: 3min
completed: 2026-10-16
status: complete
---

# Phase 1 Plan 04: Honest, Uniform Error Handling Summary

**A typed GNews adapter (timeouts, status/payload classification, key-free `from None` errors) plus one RFC 9457 problem+json renderer carrying provenance members for upstream 502/503, 422 validation, 404/405, not_configured and internal errors, with `/analyze` queries validated before any upstream call.**

## Performance

- **Duration:** about 3 min (start 2026-10-16T10:18:08Z, end 2026-10-16T10:21:11Z)
- **Tasks:** 3
- **Files modified:** 6 (3 created, 3 modified)

## Accomplishments

- A GNews 401 now yields `502 application/problem+json` with `code: upstream_unauthorized`, `upstream: gnews`, `synthetic: false`, `source_status: upstream_error`, `data_as_of: null` and no `results`; the named test `test_gnews_401_returns_502_not_200` proves it, and also that the fake key and `gnews.io` are absent from the body and from DEBUG logs.
- The adapter classifies every outcome in the D-07/D-19 table: 401/403/400/404/500/503 and non-JSON, list, `{}`, missing `articles` (unless `totalArticles == 0`), null/blank titles, missing or null source, unparseable and naive `publishedAt` all give 502; timeouts, connection/SSL errors and 429 give 503 with `Retry-After`. The request uses `timeout=(3.05, 10)`, the `X-Api-Key` header and exactly `q`, `lang`, `max=1`.
- Payloads are validated with private pydantic models before use; titles are stripped and `publishedAt` is converted to UTC `Z`; the adapter's return keys (`title`, `source`, `publishedAt`) are unchanged for 01-05.
- `/analyze` rejects missing, empty, whitespace, over-200-character and control-character queries with a 422 problem+json whose `errors` items hold only `loc`, `msg`, `type`; a 5000-character query returns a body under 1000 bytes and nothing is forwarded upstream.
- 404, 405 (with `Allow`), `not_configured` and unexpected exceptions (generic detail, only the class name logged) use the same shape.
- Full suite: 144 passed, 11 xfailed, no XPASS. The credential backstop passes.

## Task Commits

1. **Task 1: A GNews 401 travels adapter -> handler -> client as a key-free 502 problem+json (tracer)** - `d94393d` (feat)
2. **Task 2: Complete the D-07 / D-19 mapping table, payload validation and leak-proofing** - `92168f7` (feat)
3. **Task 3: Input validation and one problem+json shape for 422, 404/405, not_configured and 500** - `8cbf5c9` (feat)

**Plan metadata:** committed separately after this file (docs commit).

Tracer gate: after the Task 1 commit the verify was re-run (2 passed, full suite 85 passed / 18 xfailed with no XPASS, credential backstop 13 passed) and the plan expanded with `Tracer verified end-to-end`.

## Files Created/Modified

- `problems.py` - `PROBLEM_MEDIA_TYPE`, `UpstreamError`, `problem_body`, `problem_response`, `_upstream_error_handler`, `_validation_error_handler`, `_http_exception_handler`, `_configuration_error_handler`, `_unexpected_error_handler`, `register_problem_handlers`, `logger`
- `gnews_fetcher.py` - `TIMEOUT`, `DEFAULT_RETRY_AFTER`, `MAX_RETRY_AFTER`, `_Source`/`_Article`/`_Payload`, `_fail`, `_retry_after`; `fetch_news` raises `UpstreamError` (CRLF kept)
- `main.py` - `SearchQuery`, validated `query` parameter, `register_problem_handlers(app)` (CRLF kept)
- `tests/test_upstream_errors.py` - 38 test cases across seven test functions (24-row failure table)
- `tests/test_request_validation.py` - 16 test cases across seven test functions
- `tests/test_char_analyze_legacy.py` - xfail markers removed from the 401, 403, 429, http-500, non-JSON, null-title, timeout and empty-query rows

## Decisions Made

- 403 keeps status 502 as locked by D-07, but with its own code and a detail that names credentials, subscription or daily quota, so clients and humans can tell a quota exhaustion from a rejected key.
- `ConfigurationError` raised during a request (only possible when the lifespan was bypassed, Assumption A8) is answered 500 `not_configured` without logging its text.
- `SearchQuery` is defined on one line so the plan's literal acceptance grep matches; the regex rejects control characters (also blocks log injection).

## Deviations from Plan

None - plan executed exactly as written. Notes that are not deviations:

- Tasks 2 and 3 are marked `tdd="true"`, but `workflow.tdd_mode` is not enabled and Task 1 already created the handler and adapter skeleton, so a separate RED commit was not produced (same situation as 01-02 Task 2 and 01-03). As a sensitivity check, I mutated `gnews_fetcher.py` in a scratch edit (swapped the `Timeout` except clause for `ConnectionError`) and `test_upstream_failures_are_honest[read-timeout]`, `[connection-error]` and `[ssl-error]` failed; the file was restored from a saved copy before committing.
- `main.py` and `gnews_fetcher.py` are CRLF in the repository; CRLF was kept so diffs show only real changes. New files are LF.
- The two xfailed rows the plan expected to remain after Task 2 (empty-result and empty-query) were reduced to one after Task 3, as the plan specifies.

**Total deviations:** 0.

## Issues Encountered

None.

## Known Stubs

None. The legacy fallback article in `main.py` (fabricated 200 on an empty result) is intentionally untouched; plan 01-05 replaces it and owns the `test_empty_result_is_not_fabricated` row that stays xfail.

## Threat Flags

None. No new endpoint or trust boundary beyond the plan's threat model; T-01-17 to T-01-23 are mitigated as specified. One known Phase 2 concern from RESEARCH: 500 responses built by Starlette's `ServerErrorMiddleware` sit outside `CORSMiddleware` and carry no CORS headers.

## Authentication Gates

None. The real GNews API was never called; the autouse network guard blocked any unmocked request.

## Next Phase Readiness

- Plan 01-05 can reuse `problems.problem_body`/`problem_response` and the error codes, change the success shape to the envelope, replace the fabricated fallback and delete `tests/test_char_analyze_legacy.py` (its last xfail row, `test_empty_result_is_not_fabricated`, is that plan's to resolve).
- `fetch_news` returns `[]` only for a valid empty result (`totalArticles == 0` or an empty `articles` list), so 01-05 can map `[]` to `source_status: "empty"` without ambiguity.
- Plan 01-06 can document the error codes and the 502 vs 503 contract; the OpenAPI `responses=` declaration for 422/502/503 (RESEARCH Pattern 3) is not part of this plan and is left to 01-05/01-06.

## Self-Check: PASSED

- Created and modified files exist: problems.py, gnews_fetcher.py, main.py, tests/test_upstream_errors.py, tests/test_request_validation.py, tests/test_char_analyze_legacy.py (all FOUND).
- Commits are ancestors of HEAD: d94393d, 92168f7, 8cbf5c9 (all FOUND); `git rev-list --count` from the recorded base gives 3.
- Plan verification: `.venv/bin/python -m pytest -q` reports 144 passed, 11 xfailed, no XPASS; `test_gnews_401_returns_502_not_200` passes; `-rx` on the legacy module lists only `test_empty_result_is_not_fabricated`; `grep -nE "str\(exc|resp\.url|resp\.text" gnews_fetcher.py` prints nothing; `except requests.exceptions.Timeout` (line 101) precedes `except requests.exceptions.RequestException` (line 109); the credential backstop passes (13 tests).
