---
phase: 01-secure-honest-foundation
plan: 02
subsystem: config
tags: [pydantic-settings, secretstr, fail-fast, fastapi-lifespan, gitignore, secret-hygiene]

requires:
  - phase: 01-secure-honest-foundation
    provides: autouse network guard, client_factory and fixtures from plan 01-01
provides:
  - config.Settings and get_settings (lazy, cached, fail-fast) with ConfigurationError that never echoes a value
  - fetch_news(query, api_key) sending the credential only in the X-Api-Key header
  - App lifespan that stops startup (uvicorn exit code 3) when the news key is missing and DEMO_MODE is not true
  - Names-only .env.example and a .gitignore that keeps .env.example, fixtures/, scripts/ and tests/
  - Regex credential backstop test over every git-visible file outside tests/ (including .planning/ and .claude/)
affects: [01-03, 01-04, 01-05, 01-06]

actuals:
  tokens: 4500
  tasks: 3
  commits: 3
plan_head_before: 897d7a26e8ea22757ad9ef83a234654d130cb381
plan_head_after: e04761458aacf8319c81e9b022bbadc8eeae947d

tech-stack:
  added: []
  patterns:
    - "Settings read lazily via lru_cache get_settings; errors built from loc and msg only and raised from None"
    - "Settings injected into the route with Depends(get_settings); lifespan calls get_settings for fail-fast"
    - "Test env is driven through monkeypatch.setenv plus Settings.model_config env_file disabled and cache_clear before and after"
    - "Credential backstop reports path:line only so a failure cannot print a secret"

key-files:
  created:
    - config.py
    - .env.example
    - .gitignore
    - tests/test_settings.py
    - tests/test_no_hardcoded_credentials.py
  modified:
    - gnews_fetcher.py
    - main.py
    - tests/conftest.py

key-decisions:
  - "gnews_fetcher.py was deleted and rewritten from the redacted excerpt rather than read, so the rotated key literal never entered tool output"
  - "Legacy CRLF line endings of main.py and gnews_fetcher.py were preserved to keep the diff to the real changes"
  - "Invalid DEMO_MODE value is covered by its own test (test_invalid_demo_mode_fails_startup) beside the parametrized parsing rows"

patterns-established:
  - "Every task commit from here on runs the credential check first (git grep in Tasks 1-2, tests/test_no_hardcoded_credentials.py from Task 3 on)"
  - "Fake secret markers are low-entropy hyphenated words, never hex-looking strings"

requirements-completed: [FND-01]

coverage:
  - id: D1
    description: "The rotated key literal and the always-true placeholder guard are gone from gnews_fetcher.py; no credential literal exists in any git-visible file outside tests/"
    requirement: FND-01
    verification:
      - kind: unit
        ref: "tests/test_no_hardcoded_credentials.py#test_no_credential_literals_in_repo"
        status: pass
      - kind: other
        ref: "grep -cE '^GNEWS_API_KEY *=|PUT_|apikey' gnews_fetcher.py prints 0"
        status: pass
    human_judgment: false
  - id: D2
    description: "The key travels only in the X-Api-Key header; the query string carries exactly q, lang and max"
    requirement: FND-01
    verification:
      - kind: integration
        ref: "tests/test_settings.py#test_key_sent_only_in_header"
        status: pass
    human_judgment: false
  - id: D3
    description: "Starting without GNEWS_API_KEY and without DEMO_MODE=true raises ConfigurationError before any upstream call; uvicorn exits with code 3; DEMO_MODE=true starts without a key"
    requirement: FND-01
    verification:
      - kind: integration
        ref: "tests/test_settings.py#test_missing_key_fails_fast_at_startup"
        status: pass
      - kind: integration
        ref: "tests/test_settings.py#test_uvicorn_exits_on_missing_key"
        status: pass
      - kind: integration
        ref: "tests/test_settings.py#test_demo_mode_starts_without_key"
        status: pass
    human_judgment: false
  - id: D4
    description: "Blank or whitespace key counts as missing, invalid DEMO_MODE fails startup, and neither startup errors nor repr(settings) contain a secret value"
    requirement: FND-01
    verification:
      - kind: unit
        ref: "tests/test_settings.py#test_blank_key_is_missing"
        status: pass
      - kind: unit
        ref: "tests/test_settings.py#test_demo_mode_parsing"
        status: pass
      - kind: unit
        ref: "tests/test_settings.py#test_startup_error_never_echoes_secrets"
        status: pass
      - kind: unit
        ref: "tests/test_settings.py#test_settings_repr_masks_secrets"
        status: pass
    human_judgment: false
  - id: D5
    description: ".env.example lists exactly the five names with no values; .env and .env.* are ignored while .env.example, fixtures/, scripts/ and tests/ are not"
    requirement: FND-01
    verification:
      - kind: unit
        ref: "tests/test_no_hardcoded_credentials.py#test_env_example_lists_names_only"
        status: pass
      - kind: unit
        ref: "tests/test_no_hardcoded_credentials.py#test_gitignore_semantics"
        status: pass
    human_judgment: false
  - id: D6
    description: "Behaviour on upstream errors and the legacy list shape are unchanged: the legacy characterization still passes with its 9 xfail rows still xfail"
    requirement: FND-01
    verification:
      - kind: integration
        ref: "tests/test_char_analyze_legacy.py (3 passed, 9 xfailed, no XPASS)"
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-10-16
status: complete
---

# Phase 1 Plan 02: Environment-Only Configuration Summary

**Pydantic-settings `Settings` with `SecretStr` secrets, an app lifespan that exits uvicorn with code 3 when the news key is missing, the GNews key moved to the `X-Api-Key` header, and a regex backstop test proving no credential literal remains in any git-visible file.**

## Performance

- **Duration:** about 5 min (start time was not captured at launch; approximate)
- **Started:** 2026-10-16T10:06:00Z (approximate)
- **Completed:** 2026-10-16T10:12:00Z
- **Tasks:** 3
- **Files modified:** 8 (5 created, 3 modified)

## Accomplishments

- The hardcoded key constant and the placeholder guard that never fired are removed from `gnews_fetcher.py`. `fetch_news(query, api_key)` now raises `ConfigurationError` on a blank key and sends the credential only in the `X-Api-Key` header; the outbound query string is exactly `q`, `lang`, `max`.
- `config.py` defines `ConfigurationError`, `Settings` (key, app password and database URL are `SecretStr`; Bluesky and database settings optional until Phase 3) and a cached `get_settings()`. The error message is built from `loc` and `msg` only and raised `from None`, so no value is echoed.
- Startup fails fast: a real `python -m uvicorn main:app --port 0` with none of the variables set exits with code 3, names `GNEWS_API_KEY` and prints no marker secret. `DEMO_MODE=true` starts without a key.
- `.env.example` (five names, no values) and `.gitignore` (env files, caches, virtualenvs, Node, data and model artifacts; `.env.example`, `fixtures/`, `scripts/`, `tests/` stay visible). `git status` shows no stray caches.
- `tests/test_no_hardcoded_credentials.py` scans tracked and untracked-unignored files including `.planning/` and `.claude/` (asserting the scope cannot shrink) and reports `path:line` only. A probe with a synthetic 20-character assignment in an untracked file made it fail as intended.
- Full suite: 58 passed, 19 xfailed, no XPASS. The legacy characterization is unchanged (3 passed, 9 xfailed).

## Task Commits

1. **Task 1: Key from the environment reaches GNews only via the X-Api-Key header, and a missing key stops startup (tracer)** - `51dea4b` (feat)
2. **Task 2: Fail-fast and secret-masking edge cases, including a real uvicorn start** - `2a4156a` (test)
3. **Task 3: Names-only .env.example, .gitignore, regex credential backstop** - `e047614` (chore)

**Plan metadata:** committed separately after this file (docs commit).

Tracer gate: after the Task 1 commit the verify was re-run (8 passed, 9 xfailed across the three named files) and the plan expanded with `Tracer verified end-to-end`.

## Files Created/Modified

- `config.py` - `ConfigurationError`, `Settings` with `_blank_key_is_missing` and `_key_required_unless_demo`, cached `get_settings()`
- `gnews_fetcher.py` - `GNEWS_URL`, `fetch_news(query, api_key)` with the header-only credential
- `main.py` - `lifespan` calling `get_settings()`, `analyze(query, settings)` via `Depends(get_settings)`; CORS, fallback article, simulator calls and list response untouched
- `tests/conftest.py` - env scrub, `env_file` disabled, `get_settings.cache_clear()` before and after, env-driven `client_factory(gnews_api_key=, demo_mode=, raise_server_exceptions=)`
- `tests/test_settings.py` - 16 tests including the real uvicorn process
- `.env.example`, `.gitignore` - repo hygiene
- `tests/test_no_hardcoded_credentials.py` - 13 tests (1 scan, 1 regex self-check, 1 `.env.example`, 10 ignore rows)

## Decisions Made

- `gnews_fetcher.py` was removed and rewritten from the redacted excerpt in 01-PATTERNS.md instead of being read, so the rotated key never appeared in tool output. The key stays in history at `1fedcd2` by owner decision (D-11); no history rewrite or force-push was run.
- `main.py` and `gnews_fetcher.py` were CRLF in the original; CRLF was kept so the diffs show only real changes. New files are LF.

## Deviations from Plan

None - plan executed exactly as written. Notes that are not deviations:

- Task 2 is marked `tdd="true"`, but `_blank_key_is_missing` and the loc/msg-only `ConfigurationError` were already specified in Task 1's `config.py`, so every Task 2 test passed on first run and no separate RED commit was possible (the plan itself says to adjust `config.py` only if a behavior fails; `workflow.tdd_mode` is not enabled). In place of RED evidence, two mutation checks proved the tests are sensitive: disabling the blank-key validator failed `test_blank_key_is_missing[   ]`, and removing the lifespan `get_settings()` call failed `test_missing_key_fails_fast_at_startup` and `test_uvicorn_exits_on_missing_key`. Both mutations were reverted with `git checkout -- <file>` before committing.
- The invalid `DEMO_MODE=maybe` row lives in its own test, `test_invalid_demo_mode_fails_startup`, instead of a parametrization row; behavior is as specified. The subprocess test env also sets `PYTHONDONTWRITEBYTECODE=1` so it cannot write bytecode into the repo root.
- Acceptance count for `tests/test_settings.py` is 16 (plan asked for 15 or more).
- FND-01 was not marked complete in REQUIREMENTS.md: plan 01-06 also declares it and has no SUMMARY yet, so the shared-ID gate (`requirements.ready-ids`) reported it blocked. It becomes ready when 01-06 finishes.

**Total deviations:** 0.

## Issues Encountered

None. The tracer plan wording "Before this task [the git grep] matches gnews_fetcher.py" was honoured: after Task 1 it exits 1 (no matches).

## Known Stubs

None.

## Threat Flags

None. No new endpoint or trust boundary beyond the plan's threat model; T-01-05 through T-01-10 are mitigated as specified and T-01-11 (key in history) is accepted per D-11.

## Authentication Gates

None. The real GNews API was never called; the autouse network guard blocked any unmocked request.

## User Setup Required

None - no external service configuration required. To run the service locally, copy `.env.example` to `.env` and set `GNEWS_API_KEY` (or set `DEMO_MODE=true` once the demo fixture lands in a later plan). The previously committed key is rotated and inert.

## Next Phase Readiness

- Plan 01-03 onward can rely on `get_settings()`, `fetch_news(query, api_key)` and the env-driven `client_factory`; `tests/test_no_hardcoded_credentials.py` runs with the full suite before each later commit.
- Plan 01-04 owns timeouts, typed upstream errors and payload validation; they are deliberately untouched here. Plan 01-05 replaces `tests/test_char_analyze_legacy.py` and the fallback article.
- Plan 01-06's gitleaks working-tree scan can now be green because the key literal is gone from the working tree.

## Self-Check: PASSED

- Created and modified files exist: config.py, gnews_fetcher.py, main.py, tests/conftest.py, tests/test_settings.py, .env.example, .gitignore, tests/test_no_hardcoded_credentials.py (all FOUND).
- Commits are ancestors of HEAD: 51dea4b, 2a4156a, e047614 (all FOUND).
- Plan verification: `.venv/bin/python -m pytest -q` reports 58 passed, 19 xfailed, 0 XPASS; `grep -cE "^GNEWS_API_KEY *=|PUT_|apikey" gnews_fetcher.py` prints 0; `test_uvicorn_exits_on_missing_key` passes (exit code 3); no force-push, filter-repo or rebase was run.
