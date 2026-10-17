---
phase: 01-secure-honest-foundation
verified: 2026-10-17T16:00:00Z
status: passed
score: 5/5 roadmap success criteria verified (6/6 requirements verified for Phase 1 scope)
covered_files:
  - .env.example
  - .github/workflows/ci.yml
  - .gitignore
  - .planning/phases/01-secure-honest-foundation/01-01-PLAN.md
  - .planning/phases/01-secure-honest-foundation/01-01-SUMMARY.md
  - .planning/phases/01-secure-honest-foundation/01-02-PLAN.md
  - .planning/phases/01-secure-honest-foundation/01-02-SUMMARY.md
  - .planning/phases/01-secure-honest-foundation/01-03-PLAN.md
  - .planning/phases/01-secure-honest-foundation/01-03-SUMMARY.md
  - .planning/phases/01-secure-honest-foundation/01-04-PLAN.md
  - .planning/phases/01-secure-honest-foundation/01-04-SUMMARY.md
  - .planning/phases/01-secure-honest-foundation/01-05-PLAN.md
  - .planning/phases/01-secure-honest-foundation/01-05-SUMMARY.md
  - .planning/phases/01-secure-honest-foundation/01-06-PLAN.md
  - .planning/phases/01-secure-honest-foundation/01-06-SUMMARY.md
  - README.md
  - config.py
  - fixtures/demo_analyze.json
  - gnews_fetcher.py
  - main.py
  - models.py
  - problems.py
  - pytest.ini
  - requirements-dev.txt
  - requirements.txt
  - scripts/copy_guard.py
  - scripts/generate_demo_fixture.py
  - scripts/gitleaks_scan.sh
  - scripts/gitleaks_selftest.sh
  - scripts/install_gitleaks.sh
  - tests/test_demo_fixture.py
  - tests/test_settings.py
covered_digest: "v3:sha256:3ff76ece766bf4bb7cb040b589d1bbb1d0d013b181502e1b4a59e00598fa78e6"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: stale (report predated source changes; its status line had been hand-edited)
  previous_score: 5/5
  gaps_closed: []
  gaps_remaining: []
  regressions: []
gaps: []
deferred:
  - truth: "FND-02 wording also covers Bluesky and database failures returning 502/503"
    addressed_in: "Phase 3"
    evidence: "Phase 3 SC5: 'honours the Phase 1 provenance and error contract (a database outage returns 503 with the machine-readable body and /ready reports not ready)'. No Bluesky or database code exists in Phase 1, and Phase 1 SC2 scopes the criterion to the news API."
---

# Phase 1: Secure & Honest Foundation Verification Report

**Phase Goal:** The existing service stops misleading its users: no secrets in the repo, upstream failures surface as honest errors, any demo data is explicitly labelled, input is validated, and the prototype's current behaviour is pinned by tests before anything is refactored.
**Verified:** 2026-10-17T16:00:00Z (HEAD 2fa531bcdc5ff15c988932ad71be26f5fef87d45, equal to origin/claude/sleepy-lovelace-13aums)
**Status:** passed
**Re-verification:** Yes. This is a full regeneration. The earlier report (HEAD 8dd679e) was stale and its frontmatter status had been edited by hand, so nothing in it was trusted. Every item below was re-checked against HEAD.

All five roadmap success criteria hold in the code. There are no gaps. The three owner-side items from the earlier report are now resolved. The resolution is owner-attested evidence in `01-UAT.md`, which this verification could not reproduce (see "Owner-provided evidence"). Everything else was verified directly.

Changes since the last verification, in `git diff 8dd679e HEAD` outside `.planning/`: `config.py`, `tests/test_demo_fixture.py` and `tests/test_settings.py` only. The first is the owner-chosen key trimming. The two test files now pass `SYSTEMROOT` to child processes, for Windows.

## Commands Run

| Check | Command | Result |
|---|---|---|
| Test suite | `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q` | `274 passed, 10 xfailed in 3.58s`. No XPASS (a grep for "xpass" over the output found 0 matches). `pytest.ini` sets `xfail_strict = true` and `filterwarnings = error`. |
| Copy guard | `.venv/bin/python scripts/copy_guard.py` | `copy-guard: clean (1 files, 135 OpenAPI strings)`, exit 0 |
| Fixture drift | `.venv/bin/python scripts/generate_demo_fixture.py --check` | `demo fixture is up to date`, exit 0 |
| Secret scan | `bash scripts/gitleaks_scan.sh /tmp/truthtrail-gitleaks/gitleaks a5dd8257... HEAD a5dd8257...` | Working tree: 76 git-visible files. Range a5dd825..2fa531b (floor excluded): 56 commits. `gitleaks: clean`, exit 0. The binary was already installed. |
| CI for HEAD | `gh run list/view` (the MCP `actions_list` tool was not available here) | Run 39046801559, headSha 2fa531b (HEAD), workflow `ci`, conclusion **success**. Jobs `copy-guard`, `gitleaks` and `tests` are all success. Earlier runs for aa7c721 and f04a612 are also green. Commit 64731a7 has no run in the list (the list returned four runs only), which does not affect HEAD. |
| Debt markers | grep for `TBD\|FIXME\|XXX\|TODO\|HACK` over `*.py`, `*.yml`, `*.sh`, `*.md` outside `.planning`, `.venv` and `node_modules` | None |
| Startup, no key | `uvicorn.run('main:app')` with `GNEWS_API_KEY` and `DEMO_MODE` unset | `ConfigurationError: Invalid configuration (settings: Value error, GNEWS_API_KEY is required unless DEMO_MODE=true)`, "Application startup failed", exit 3 |
| Pinned code untouched | `git diff --stat 9b5b085 HEAD -- risk_analyzer.py spread_simulator.py users.py` | Empty. All three are byte-identical to the pre-phase baseline. |

## Mocked-Network Exercise of the App

`TestClient` with `responses` as the transport mock, a fake 32-character key, no real GNews call, no real key used or printed. Script: `/tmp/claude-0/-home-user-TruthTrail/92aa1a2e-0a51-57d6-846d-a61e78cb81bd/scratchpad/exercise.py`.

| Scenario | Observed | Expected met |
|---|---|---|
| No key, no DEMO_MODE | Startup raised `ConfigurationError ... GNEWS_API_KEY is required unless DEMO_MODE=true`. No upstream call. | yes |
| Key with an interior space (`"abc def123"`) | Startup raised `ConfigurationError ... must be printable ASCII without spaces or line breaks inside the key`. The value is not echoed. | yes |
| Key with a non-ASCII character | The same `ConfigurationError` at startup | yes |
| Key `"\n<key> \r\n"` (and `"  <key>\t"`) | Startup succeeded. The `X-Api-Key` header of the outgoing request equalled the trimmed key. The URL was `...search?q=vaccine&lang=en&max=1` with no key in it. 200 envelope: `meta {synthetic:false, data_as_of, source_status:"ok"}`, the result has `risk_method: keyword_baseline`, and the fake key is absent from the response. | yes |
| Upstream 401 | **502** `application/problem+json`, `code: upstream_unauthorized`, `upstream: gnews`, `synthetic:false`, `source_status:"upstream_error"`, `data_as_of:null`. The key is absent from the body. | yes |
| Upstream 400 | 502 `upstream_bad_response` (matches the owner's real-API observation for a malformed key) | yes |
| Upstream 429 with `Retry-After: 7` | 503 `upstream_rate_limited`, `Retry-After: 7` | yes |
| Connection timeout (its message embeds the key) | 503 `upstream_timeout`, `Retry-After: 30`, key absent from the body | yes |
| Upstream `{"totalArticles":0}` | Honest **200**, `results: []`, `meta.source_status:"empty"`, `synthetic:false`. No fabricated article. | yes |
| `DEMO_MODE=true`, no key | App starts, 0 upstream calls, 200 with `meta {synthetic:true, data_as_of:"2026-10-11T12:00:00Z", source_status:"fixture"}`, 3 results, every headline labelled "(synthetic demo)", every result has `events` | yes |
| `DEMO_MODE` unset, empty or `false`, upstream 401 | 502 `upstream_unauthorized` in all three cases. No fixture served. | yes |
| Missing, empty, whitespace-only, 201-character, NUL and U+2028 queries | 422 `application/problem+json`, `source_status: invalid_request`, `synthetic:false`. The 201-character input is not echoed. 0 upstream calls. | yes |
| Unknown route and wrong method | 404 `application/problem+json`; POST `/analyze` gives 405 | yes |
| Log capture across the whole run | The fake key never appears in captured logs | yes |
| `/openapi.json` | One operation, `GET /analyze`, with responses 200, 422, 500, 502 and 503. Schemas: `AnalyzeResponse`, `DemoResult`, `Event`, `FieldIssue`, `LiveResult`, `Meta`, `Problem`. | yes |

## Goal Achievement: Roadmap Success Criteria

| # | Success Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Clean checkout holds no credential values; env-only settings documented in `.env.example`; tree secret scan passes; starting without the news key gives an explicit configuration error | VERIFIED | `config.py` `Settings` uses `SecretStr`, `hide_input_in_errors=True` and `env_ignore_empty=True`, and has no import-time env read. `get_settings()` is called in `main.py`'s `lifespan`, so startup fails before any request (exit 3 observed under real uvicorn). `.env.example` lists `GNEWS_API_KEY`, `DEMO_MODE`, `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD` and `DATABASE_URL`, all blank. `.env` is git-ignored (`.gitignore:22`) and not tracked. Gitleaks is clean over the tree and the range. `gnews_fetcher.py` sends the key only in `X-Api-Key`, never in the URL. No placeholder call is possible: `fetch_news` raises `ConfigurationError` for a blank or header-unsafe key before any request. The old key remains in history (1fedcd2) by owner decision D-11; the owner reports it deleted (see owner-provided evidence). |
| 2 | Upstream 401/403/timeout/other gives 502/503 with a machine-readable body (code, message, upstream) and never a fabricated article; a test proves 401 gives 502 | VERIFIED | Exercised above: 401 gives 502, 400 gives 502, 429 gives 503 with Retry-After, timeout gives 503. By code review of `gnews_fetcher.py`: 403, other non-200, non-JSON, malformed or null-field payloads and a missing `articles` key without `totalArticles==0` map to 502, connection errors to 503, and redirects are not followed. The named test `tests/test_upstream_errors.py::test_gnews_401_returns_502_not_200` exists and passes in the full run. |
| 3 | Every response carries `synthetic`, `data_as_of`, `source_status`; DEMO_MODE unset/false can never serve fixture data; DEMO_MODE=true flags `synthetic: true` | VERIFIED | Success bodies carry them in `meta`. Error bodies carry them at top level (`data_as_of: null`) via `problem_body`. `main.py` calls `load_demo_fixture()` only under `if settings.demo_mode`, and `load_demo_fixture` refuses a fixture whose meta is not `synthetic: true` / `source_status: fixture`. Exercised for unset, empty and false (502, no fixture) and for true (labelled synthetic fixture, 0 upstream calls). `generate_demo_fixture.py --check` passes. |
| 4 | Empty, oversize or malformed query gives 422; `/openapi.json` shows a Pydantic response model for every endpoint (schema-walking test) | VERIFIED | Six invalid-query cases all gave 422 problem+json with no upstream call. OpenAPI shows `GET /analyze` -> `AnalyzeResponse` plus `Problem` for 422/500/502/503. The walker test `tests/test_openapi_contract.py::test_every_operation_has_typed_2xx_response` exists and passes. |
| 5 | Characterization tests pin current `/analyze` behaviour including known keyword defects, committed before any behavioural change; CI fails on banned phrases; README says "flag for human review" | VERIFIED | `risk_analyzer.py`, `spread_simulator.py` and `users.py` are byte-identical to 9b5b085. The 10 known defects run as strict xfails with 0 XPASS (secure/cure, studies/dies, couple/coup, deadline, Dead heat, Musk, Trump, negated "market crash", child-before-parent, mixed timestamp formats). Ordering (per the earlier verification of git history, whose commits are unchanged): test commits 7d9e4ac and f7a5040 precede the first production change, 51dea4b. `copy_guard.py` is clean over the repo and the OpenAPI strings, and `ci.yml` runs it as a job; CI is green on HEAD. README.md opens with "Its output is a flag for human review ... it never decides whether a claim is true". |

## Requirements Coverage

| Requirement | Status | Evidence |
|---|---|---|
| FND-01 (credentials from env, `.env.example`, no secret in tree) | VERIFIED | See SC1. `tests/test_no_hardcoded_credentials.py` and `tests/test_settings.py` pass. |
| FND-02 (upstream failure gives 502/503 machine-readable, never a fabricated 200) | VERIFIED for the news-API scope. The Bluesky and database clauses are deferred to Phase 3. | See SC2. No Bluesky or database code exists until Phase 3, whose SC5 carries the database-outage 503. **Bookkeeping:** `.planning/REQUIREMENTS.md` still shows FND-02 as `[ ]` / `Pending` while FND-01 and FND-03..06 are Complete. This is a decision for the orchestrator (mark it Complete for Phase 1, or leave it Pending until Phase 3 lands). It is not a code gap, and ROADMAP.md still shows the Phase 1 checkbox unchecked. |
| FND-03 (provenance on every response; fixture only under DEMO_MODE, flagged synthetic) | VERIFIED | See SC3. |
| FND-04 (422 on bad input; Pydantic response model in OpenAPI for every endpoint) | VERIFIED | See SC4. |
| FND-05 (characterization tests pin current behaviour incl. defects, before refactor) | VERIFIED | See SC5. |
| FND-06 (copy says "flag for human review"; CI fails on banned phrases) | VERIFIED | See SC5. |
| Orphaned requirements | None | REQUIREMENTS.md maps only FND-01..06 to Phase 1, and all six are in plan frontmatter. |

## Decisions D-01..D-20 (Spot-Checks Against Code)

| Decision area | Status | Evidence |
|---|---|---|
| D-01 envelope, D-03 `risk_method`, D-04 empty gives 200 `source_status: empty`, fabricated "unknown"/2025-01-01 article removed | VERIFIED | Exercised (empty response above). `main.py` builds `AnalyzeResponse(results, meta)` and contains no fabricated article. |
| D-02/D-17 fixture static, deterministic, committed; simulator unmodified and unreachable from routes | VERIFIED | The `--check` passes. `main.py` does not import `spread_simulator` or `users`, which are unchanged from the baseline. |
| D-05 live results carry no `events`, demo results do | VERIFIED | Observed in the live 200 body (no `events`) and the demo body (`events` on all 3). |
| D-06/D-15 RFC 9457 shape with provenance on every error | VERIFIED | 502, 503, 422, 404 and 500 handlers all go through `problem_body`; 405 was observed as problem+json status. |
| D-07 bad answer is 502, unreachable or throttled is 503 | VERIFIED | `gnews_fetcher.py` classification, exercised above. |
| D-08 fail-fast without key unless DEMO_MODE | VERIFIED | Observed ConfigurationError and uvicorn exit 3; startup succeeds under `DEMO_MODE=true`. |
| D-09/D-20 pinned, checksum-verified gitleaks; range scan fails closed; floor skips pre-rotation history | VERIFIED | Scan passes locally and in CI. The earlier verification confirmed the selftest and the SHA-pinned `ci.yml`; neither file changed since (the diff from 8dd679e touches only `config.py` and two test files). |
| D-11 history not rewritten | VERIFIED | Commit 1fedcd2 remains in history by decision; the gitleaks floor is a5dd825. |
| D-14 CI with copy-guard, gitleaks and tests | VERIFIED | Run 39046801559 on HEAD: three jobs, all success. |
| D-16 key in header only, `from None` re-raises, no URL or key in bodies, logs or exceptions | VERIFIED | Header-only send confirmed from the outgoing request (`key_in_url: False`). The timeout whose message embeds the key produced a body and logs without it. |
| D-12 legacy list-shape endpoint tests retired; pure-function suites persist | VERIFIED | The suite shows the pure-function characterization tests passing. |
| D-10/D-13/D-18/D-19 | VERIFIED (by suite) | The 274-test run exercises the settings, envelope and adapter contracts these decisions cover. D-19's response-shape assumptions are additionally corroborated by the owner's real-API check (refined A1: malformed key gives 400, well-formed wrong key gives 401). |

## Owner-Provided Evidence (Not Independently Reproduced)

`01-UAT.md` is `status: complete`, 3 tests, 3 passed, 0 issues. This verification **did not and must not** call the real GNews API, so the following are owner attestations, accepted as the resolution of the earlier human items:

1. **Live smoke test (owner, Windows, 2026-10-17):** a real key gave a 200 envelope with `synthetic: false`, `source_status: ok` and a real headline. A well-formed wrong key (32 characters) gave GNews 401 and our 502 `upstream_unauthorized`. A malformed short key gave GNews 400 and our 502 `upstream_bad_response`. The mocked behaviour above matches these observations code-path for code-path (401 and 400 both reproduce the owner's results).
2. **Old key (commit 1fedcd2):** owner reports it changed and deleted. Nothing in the repo can prove it, because history below the floor is intentionally unscanned.
3. **Key policy:** the owner chose trimming. `config.py` now trims surrounding whitespace (including `\n`, `\r\n`, space and tab) and still rejects interior whitespace and non-ASCII. I verified this behaviourally above. `fetch_news` stays strict and rejects any key with whitespace if called directly.

## Anti-Patterns Found

None blocking. There are no TBD/FIXME/XXX/TODO/HACK markers. There are no stubs: the fixture data flows from the committed JSON through the validated `AnalyzeResponse`, and the live path flows from the adapter response to `LiveResult`.

Items left deliberately open, none of them Phase 1 gaps:
- `main.py` still uses `allow_origins=["*"]`; restricting it is Phase 2 (ENG-06). Per 01-REVIEW.md IN-02, 500 responses carry no CORS headers.
- 01-REVIEW.md IN-03 (`Retry-After: 0` passes through) and IN-05 (loose model typing, line endings) remain informational.
- The new trimming logic lives in a `mode="before"` validator, so a trimmed key is stored as the trimmed value, which is what the outgoing header test confirmed.

## Human Verification Required

None outstanding. The three earlier items are resolved by owner-attested UAT (above). If the owner wants machine-checkable proof that the old key is dead, that can only come from GNews, not from this repository.

## Gaps Summary

No gaps. Phase 1 achieves its goal in the code. No credential is in the tree, upstream failures surface as problem+json 502/503, every response carries provenance, fixture data is reachable only through `DEMO_MODE=true` and labelled synthetic, input is validated, OpenAPI is typed, and the keyword defects are pinned as strict xfails. The suite is 274 passed with 10 xfailed and no XPASS, and the copy guard, fixture check and secret scan are clean. CI is green on HEAD 2fa531b. The one open bookkeeping point is the FND-02 checkbox in REQUIREMENTS.md, plus the unchecked Phase 1 box in ROADMAP.md.

---

_Verified: 2026-10-17T16:00:00Z_
_Verifier: Claude (gsd-verifier)_
