---
phase: 02-engineering-baseline
plan: 08
subsystem: api
tags: [cache, cachetools, ttl, x-cache, fastapi]

requires:
  - phase: 02-engineering-baseline
    provides: plan 02-07 create_app() with limiter on app.state.limiter, decorator-limited /analyze, client_factory(app_kwargs=...)
provides:
  - "AnalyzeCache (api/cache.py): lock-guarded cachetools TTLCache, key (trimmed casefolded query, demo flag), ttl 600 s, 256 entries, injectable timer"
  - "GET /analyze served from app.state.analyze_cache with X-Cache hit or miss on every 200; successes only; limit applies before the cache"
  - "create_app(cache_timer=...) so tests use a fake clock and never sleep"
affects: [02-09, 02-11, 02-12, 03]

actuals:
  tokens: 9000
  tasks: 2
  commits: 2
plan_head_before: 6ce1f40822b7fc48c0291efca49c8c5fc430d2a3
plan_head_after: db493a99629c430401f365380c876d113cf0e8d6

tech-stack:
  added: []
  patterns:
    - "Every cache access (get included) takes one threading.Lock because cachetools caches are not thread safe and expiry mutates; the network fetch runs outside the lock"
    - "Cache lives on app.state, built per app by create_app(); the clock is injected, never patched"
    - "Handler order: validation, rate limit (decorator wrapper), cache lookup, compute, store, header; an exception propagates before the store so errors are never cached"

key-files:
  created:
    - src/truthtrail/api/cache.py
    - tests/test_cache_unit.py
    - tests/test_cache.py
  modified:
    - src/truthtrail/api/analyze.py
    - src/truthtrail/api/app.py
    - tests/test_openapi_contract.py

key-decisions:
  - "The miss path (demo fixture branch or live fetch and mapping) moved unchanged into a module-level _compute(query, settings) helper so the handler reads lookup, compute, store, header"
  - "AnalyzeCache exposes read-only ttl and maxsize properties so the defaults (600 s, 256) are testable without reaching into cachetools"

requirements-completed: []

status: complete
completed: 2026-10-17
---

# Phase 2 Plan 08: TTL Cache for /analyze Summary

**Repeated `/analyze` reads inside 600 seconds are answered from an in-process lock-guarded TTL cache (256 entries, key = trimmed casefolded query plus demo flag): one upstream call, `X-Cache: hit`, the originally stored `meta.data_as_of` replayed, errors never stored, the honest empty result stored, and the rate limit still answering 429 before any hit.**

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | 1341891 | feat(cache): AnalyzeCache - lock-guarded TTL/LRU cache with normalised keys and injectable clock |
| 2 | db493a9 | feat(cache): serve repeated /analyze reads from the TTL cache (X-Cache, successes only, limit before cache) |

## What was built

- **AnalyzeCache (Task 1).** `api/cache.py`, free of FastAPI imports. `TTLCache[tuple[str, bool], AnalyzeResponse]` plus a `threading.Lock`; `get` and `put` hold the lock for the whole operation. The stored object is returned by identity (no copy, no mutation). Key is `(query.strip().casefold(), demo)`. Defaults `ttl=600.0`, `maxsize=256`, `timer=time.monotonic`.
- **Wiring (Task 2).** `create_app(*, cache_timer=None, v1_registrars=None)` builds `AnalyzeCache(timer=cache_timer or time.monotonic)` on `app.state.analyze_cache` (never module-level). The `/analyze` handler gained `response: Response`; after validation and the limiter wrapper it looks up the cache, on a hit sets `X-Cache: hit` and returns the stored object, on a miss computes, stores and sets `X-Cache: miss`. The header is not declared in OpenAPI; the golden test passes unchanged.

## Tests

- `tests/test_cache_unit.py` (14 collected): defaults, empty miss, identity on put/get, trim and casefold normalisation (`STRASSE` collides with `strasse` and with the sharp-s spelling), demo flag and query separation, expiry present at +599 s and absent at +601 s with a fake clock, LRU bound at maxsize 2 (a get refreshes recency), a spy lock proving both `get` and `put` acquire it, and an 8-thread x 500-operation smoke test.
- `tests/test_cache.py` (14 collected): miss then hit with one upstream call and equal bodies; hit replays the original `meta.data_as_of` while the injected clock advances 599 s (single upstream call, no patching of `datetime`); 599 s hit and 601 s miss with a second upstream call; errors not cached for upstream 401 (502), upstream 503 (502) and a connect timeout (503), each followed by a 200 `miss` and two upstream calls; honest empty result cached; `" Vaccine "`, `vaccine` and `VACCINE` share an entry; different queries are separate; demo mode second request is a hit equal to the committed fixture with zero upstream calls; a 422 carries no `X-Cache` and leaves the cache untouched; with `RATE_LIMIT_ANALYZE=2/minute` the third identical request (which would be a hit) is a 429 without `X-Cache`; two apps own independent caches; OpenAPI never mentions `X-Cache`.

## Verification

- `pytest -q`: 418 passed, 10 xfailed, no XPASS (390 passed at the start; 404 after Task 1, +14; 418 after Task 2, +14).
- `tests/test_openapi_golden.py`, `tests/test_rate_limit.py`, `tests/test_provenance_demo.py`, `tests/test_upstream_errors.py`: 91 passed unchanged.
- `ruff check`, `ruff format --check`, `mypy` (21 source files) and `scripts/copy_guard.py` (160 OpenAPI strings) clean. `tests/test_no_hardcoded_credentials.py`: 13 passed before each commit; the added-lines scan for 32-hex strings found nothing.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Existing contract test replayed a cached success instead of the upstream error**
- **Found during:** Task 2 full-suite run
- **Issue:** `tests/test_openapi_contract.py::test_actual_bodies_match_declared_models` sent a live 200 for query `mayor`, swapped the mock to a 401, and repeated the identical query on the same app expecting 502. With the cache the repeat is (correctly) a hit.
- **Fix:** The 401 request now uses a different query (`mayor resigns`) with a comment citing D-11. The assertions (502, problem+json, `Problem` validation) are unchanged; nothing was weakened or skipped.
- **Files modified:** tests/test_openapi_contract.py
- **Commit:** db493a9

### Other notes

- The miss-path logic was moved verbatim into a `_compute` helper rather than left inline (plan: "run the existing logic unchanged"). Behaviour is identical and tests that patch `load_demo_fixture` / `analyze_risk` on the module still work.
- Test counts exceed the plan's floors (7 and 11 collected) because the casefold parametrisation and the error-type parametrisation expand to several cases.
- No Docker daemon is involved in this plan; nothing here claims a docker build or a CI run passed.

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model. T-02-28 (only HTTP 200 stored, normalised key, errors tested), T-02-29 (maxsize 256, LRU, TTL, bound tested), T-02-30 (original `data_as_of` replayed, `X-Cache` states hit or miss, identity tested) and T-02-31 (one lock for every access, fetch outside the lock, thread smoke test) are implemented and tested. ENG-06 stays Pending: bounded retries and timeouts land in plan 02-09.

## Self-Check: PASSED

- Files src/truthtrail/api/cache.py, tests/test_cache_unit.py, tests/test_cache.py: FOUND
- Commits 1341891 and db493a9 are ancestors of HEAD: FOUND
