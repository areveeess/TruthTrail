---
phase: 01-secure-honest-foundation
verified: 2026-10-16T11:30:00Z
status: human_needed
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
covered_digest: "v3:sha256:14a0e97c4e18e10ef214afc1fdeab073b5817a981947c0b5e1401d1dd714b15a"
behavior_unverified: 0
overrides_applied: 0
gaps: []
deferred:
  - truth: "FND-02 wording also covers Bluesky and database failures returning 502/503"
    addressed_in: "Phase 3"
    evidence: "Phase 3 SC5: 'honours the Phase 1 provenance and error contract (a database outage returns 503 with the machine-readable body and /ready reports not ready)'. No Bluesky or database code exists in Phase 1, and Phase 1 SC2 scopes the criterion to the news API."
human_verification:
  - test: "Live smoke test with a real GNews key (owner-held, never committed): run `GNEWS_API_KEY=... uvicorn main:app`, then `curl 'localhost:8000/analyze?query=vaccine'`; then repeat with a deliberately wrong key."
    expected: "Real key: 200 envelope with meta.synthetic=false, source_status ok or empty. Wrong key: 502 problem+json code upstream_unauthorized. Confirms GNews accepts the X-Api-Key header, a 400 maps to 502, and a no-articles-key body is totalArticles 0 (research assumptions A1-A2 in D-19)."
    why_human: "Every GNews interaction in this verification was mocked (the network is blocked by design and the real API must not be called here). Header acceptance and the A1-A2 response shapes are assumptions that only a real call can confirm."
  - test: "Confirm the old GNews key committed in 1fedcd2 has actually been rotated/revoked in the GNews dashboard."
    expected: "The old key is rejected by GNews."
    why_human: "D-09/D-11 assume the key is rotated and inert, and history was intentionally not rewritten. The gitleaks scan deliberately skips history up to the floor a5dd825, so nothing in the repo can prove the key is dead. SC1 only covers a clean checkout."
  - test: "Accept or revise the WR-02 policy choice: a key with whitespace, line breaks or non-ASCII characters is rejected at startup (ConfigurationError) rather than stripped."
    expected: "Owner agrees that rejecting is preferable to silently stripping a pasted key."
    why_human: "01-REVIEW.md flags this fix as a policy decision requiring human verification. It is a design preference, not a code defect."
---

# Phase 1: Secure & Honest Foundation Verification Report

**Phase Goal:** The existing service stops misleading its users: no secrets in the repo, upstream failures surface as honest errors, any demo data is explicitly labelled, input is validated, and the prototype's current behaviour is pinned by tests before anything is refactored.
**Verified:** 2026-10-16T11:30:00Z (HEAD 8dd679e689a8aaa2c22fe92fd148899c9ccb87be, equal to origin/claude/sleepy-lovelace-13aums)
**Status:** human_needed
**Re-verification:** No, initial verification

All five roadmap success criteria are verified against the code. Three owner-side items remain, so the phase is `human_needed`. There are no gaps. Verification used the code, the tests and live exercise of the app with the network mocked, not the SUMMARY.md claims.

## Commands Run

| Check | Command | Result |
|---|---|---|
| Test suite | `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q` | `271 passed, 10 xfailed in 3.07s`, no XPASS, no failures. `xfail_strict = true` and `filterwarnings = error` are set in `pytest.ini`. |
| Copy guard | `python scripts/copy_guard.py` | The system `python` has no `fastapi`, so it exited 1 with `ModuleNotFoundError` (an environment issue; CI and the README use a venv). With `.venv/bin/python`: `copy-guard: clean (1 files, 135 OpenAPI strings)`, exit 0. |
| Fixture drift | `python scripts/generate_demo_fixture.py --check` | `demo fixture is up to date`, exit 0 |
| Secret scan | `bash scripts/gitleaks_scan.sh /tmp/truthtrail-gitleaks/gitleaks a5dd825... HEAD a5dd825...` | Working tree 74 git-visible files, range a5dd825..8dd679e 50 commits: `gitleaks: clean`, exit 0. The binary was already installed. |
| Scan selftest | `bash scripts/gitleaks_selftest.sh /tmp/truthtrail-gitleaks/gitleaks` | `all scenarios passed` (including deleted-key-from-floor, ls-files-failure, empty-working-tree and the zero-sentinel cases) |
| CI on HEAD | `gh run view 38890735635` (read-only) | headSha 8dd679e (HEAD); conclusion success; jobs copy-guard, gitleaks and tests all success |
| Debt markers | grep for `TBD\|FIXME\|XXX\|TODO\|HACK` over production code, scripts and workflow | None |

## Goal Achievement: Roadmap Success Criteria

| # | Success Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Clean checkout holds no credential values; env-only settings documented in `.env.example`; tree secret scan passes; starting without the news key gives an explicit configuration error | VERIFIED | `config.py` has `Settings` (`SecretStr`, `hide_input_in_errors`, `env_ignore_empty`) and `get_settings()`. `main.py` runs it in `lifespan`, so startup fails before any request. `.env.example` lists exactly `GNEWS_API_KEY`, `DEMO_MODE`, `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD`, `DATABASE_URL`, all with blank values. `.env` is git-ignored (`git check-ignore` hit `.gitignore:22`). Gitleaks over the tree and the range is clean. Exercised: with no key and no DEMO_MODE, `TestClient` startup raised `ConfigurationError: ... GNEWS_API_KEY is required unless DEMO_MODE=true`, and real `uvicorn.run('main:app')` exited with code 3. No upstream call was made and the key was not echoed. The key goes only in the `X-Api-Key` header (the URL carried `q=vaccine&lang=en&max=1` only). The old rotated key stays in history (1fedcd2) by owner decision D-11, so see human item 2. |
| 2 | Upstream 401/403/timeout/other gives 502 or 503 with a machine-readable body (code, message, upstream) and never a fabricated article; a test proves 401 gives 502 | VERIFIED | Exercised via `TestClient` with `responses` mocking the network. 401 gave **502** `application/problem+json` with `code: upstream_unauthorized`, `upstream: gnews`, `detail` and `title`. 429 gave 503 with `Retry-After: 7`. A `ConnectTimeout` gave 503 `upstream_timeout` with `Retry-After: 30`. The fake key was absent from every body and log. Code review of `gnews_fetcher.py`: 403, 400, other non-200, non-JSON, malformed or null-field records and naive timestamps map to 502; redirects are not followed (WR-01). The named test `tests/test_upstream_errors.py::test_gnews_401_returns_502_not_200` exists and passes in the full run. |
| 3 | Every response carries `synthetic`, `data_as_of`, `source_status`; DEMO_MODE unset/false can never serve fixture data; DEMO_MODE=true flags `synthetic: true` | VERIFIED | Success: `meta` was `{synthetic:false, data_as_of:"2026-10-16T10:59:54Z", source_status:"ok"/"empty"}`. Errors (401, 429, timeout, 422, 404, 405): the same three members at top level with `data_as_of: null`. With `DEMO_MODE` unset, `false` or empty and an upstream 401, the response was 502 and not the fixture. `main.py` calls `load_demo_fixture()` only under `if settings.demo_mode`. With `DEMO_MODE=true` and no key, the app started, made 0 upstream calls, and returned 200 with `meta {synthetic:true, data_as_of:"2026-10-11T12:00:00Z", source_status:"fixture"}`, 3 results all with `events`, and every headline labelled "(synthetic demo)". A fixture not labelled synthetic is refused by `load_demo_fixture` (RuntimeError, rendered as a generic 500). Live results have no `events` key (D-05, confirmed in the "ok" response). |
| 4 | Empty, oversize or malformed query gives 422; `/openapi.json` shows a Pydantic response model for every endpoint | VERIFIED | Whitespace-only, missing, 201-character and NUL-containing queries all gave 422 problem+json with an `errors` list of `{loc, msg, type}` that does not echo the input, and 0 upstream calls were made. Demo mode also validates the query. The `SearchQuery` pattern also rejects C1 controls and U+2028/U+2029 (IN-06). OpenAPI has `GET /analyze` 200 -> `AnalyzeResponse`, and 422/500/502/503 -> `Problem` as `application/problem+json`. Schemas: `AnalyzeResponse`, `DemoResult`, `Event`, `FieldIssue`, `LiveResult`, `Meta`, `Problem`. `/analyze` is the only API operation; FastAPI's built-in docs routes are excluded from the schema by design. The walker test `tests/test_openapi_contract.py::test_every_operation_has_typed_2xx_response` exists in the passing suite. |
| 5 | Characterization tests committed before any behavioural change, known keyword defects included; CI fails on banned phrases; README says "flag for human review" | VERIFIED | Git order: test commits 7d9e4ac and f7a5040 (10:04) precede the first production change, 51dea4b (10:08). `risk_analyzer.py`, `spread_simulator.py` and `users.py` are byte-identical to 9b5b085. All 10 defects run as strict xfails asserting the desired behaviour: "secure"/cure, "studies"/dies, "couple"/coup, "deadline", "Dead heat", Musk, Trump, negated "market crash", child-before-parent, and mixed timestamp formats. The suite shows 10 xfailed and 0 XPASS. The legacy list-shape endpoint tests were deliberately retired in 01-05 as D-12 planned, and the pure-function suites persist. `scripts/copy_guard.py` has rules for truth claims, fake-news and misinformation detectors, lie detector, an all-caps FAKE badge and AI-powered wording, and it also scans OpenAPI strings. It is clean on the repo, and `ci.yml` has a copy-guard job that runs it. README.md opens with "Its output is a flag for human review ... it never decides whether a claim is true", and the OpenAPI title, description and summary use the same wording. |

## Requirements Coverage

| Requirement | Status | Evidence |
|---|---|---|
| FND-01 (credentials from env, `.env.example`, no secret in tree) | VERIFIED | See SC1. Gitleaks working-tree and range scans are clean, and the credential backstop tests `tests/test_no_hardcoded_credentials.py` and `tests/test_settings.py` pass. The remaining caveat is human item 2: the old key's revocation is unverifiable from the repo. |
| FND-02 (upstream failure gives 502/503 machine-readable, never a fabricated 200) | VERIFIED for Phase 1 scope (news API). The Bluesky and database clauses are deferred. | The news API path is fully exercised (SC2). Bluesky and database dependencies do not exist until Phase 3, where Phase 3 SC5 carries the database-outage 503 check. **Bookkeeping:** `.planning/REQUIREMENTS.md` still shows FND-02 as `[ ]` / `Pending`, whereas the other five requirements are checked. The orchestrator should decide whether to mark it Complete for Phase 1 or leave it Pending until the Bluesky/database clauses land. This is not a code gap. |
| FND-03 (provenance on every response; fixture only under DEMO_MODE, flagged synthetic) | VERIFIED | See SC3. |
| FND-04 (422 on bad input; Pydantic response model in OpenAPI for every endpoint) | VERIFIED | See SC4. |
| FND-05 (characterization tests pin current behaviour including defects, before refactor) | VERIFIED | See SC5. |
| FND-06 (copy says "flag for human review"; CI fails on banned phrases) | VERIFIED | See SC5. The guard also fails if README lacks the "flag ... for human review" phrase. `ci.yml` has a blocking `copy-guard` job. |
| Orphaned requirements | None | REQUIREMENTS.md maps only FND-01..06 to Phase 1, and all six appear in plan frontmatter. |

## Plan must_haves Spot-Checks (against code, not SUMMARYs)

| Item | Status | Evidence |
|---|---|---|
| D-01 envelope, D-03 `risk_method`, D-04 empty gives 200 `source_status: empty`, fabricated "unknown"/2025-01-01 article removed | VERIFIED | `main.py` builds `AnalyzeResponse(results, meta)`, and the empty mock returned `{"results":[],"meta":{"synthetic":false,...,"source_status":"empty"}}`. Neither "unknown" nor "2025-01-01" appears in `main.py`. |
| D-06/D-15 RFC 9457 shape with provenance on every error | VERIFIED | 502, 503, 422, 404 and 405 bodies all have `type: about:blank`, `title`, `status`, `detail`, `code`, `synthetic: false`, `source_status` and `data_as_of: null`. 404 and 405 are also problem+json. |
| D-08 fail-fast without a key unless DEMO_MODE | VERIFIED | Observed: `ConfigurationError` at startup and uvicorn exit 3 with no key; startup succeeds with `DEMO_MODE=true` and no key. |
| D-16 key in header only, `from None` re-raises, no URL or key in bodies, logs or exceptions | VERIFIED | `gnews_fetcher.py` uses `headers={"X-Api-Key": api_key}`, `allow_redirects=False` and `_fail(...)` with `raise ... from None`. Log lines contain only `code=... upstream_status=...`. The key was absent from the response and logs in the exercised cases. |
| D-02/D-17 fixture is static, deterministic and committed, simulator unmodified | VERIFIED | `generate_demo_fixture.py --check` passed. `spread_simulator.py` and `users.py` are unchanged and no longer imported by `main.py`. |
| D-09/D-20 pinned, checksum-verified gitleaks; range scan fails closed; floor skips pre-rotation history | VERIFIED | The scan and the selftest passed locally. `ci.yml` pins every action by full SHA with a version comment, uses `fetch-depth: 0`, runs the selftest, and pushes scan the cumulative floor..sha range (CR-01 fix). |
| D-14 CI workflow with copy-guard, gitleaks and tests | VERIFIED | `.github/workflows/ci.yml` has three jobs. `gh` showed the run for HEAD 8dd679e concluded success on all three. |

## Anti-Patterns Found

None blocking. There are no TBD/FIXME/XXX/TODO/HACK markers in phase-modified production code. There are no stubs: the fixture is real data flowing from the committed JSON through the validated model. The live path flows from the adapter response to `LiveResult`.

Review items left deliberately deferred in `01-REVIEW.md` (informational, not Phase 1 gaps):
- **IN-02:** 500 responses have no CORS headers, and a broken fixture is not caught at startup (CORS work is Phase 2, ENG-06).
- **IN-03:** `Retry-After: 0` passes through from the provider.
- **IN-05:** inconsistent line endings and loose typing in the models.

`main.py` still uses `allow_origins=["*"]`; restricting it is explicitly Phase 2 (ENG-06).

## Behavioral Spot-Checks

All of the exercises above ran through `TestClient` with the network mocked (`responses`), using a fake key and no real GNews call. The summary table is in the Commands Run and Success Criteria sections. Behavior-dependent truths (fail-fast, 401 to 502, the DEMO_MODE gate) were exercised behaviourally and also have named passing tests, so `behavior_unverified` is 0.

## Human Verification Required

1. **Live smoke test with a real GNews key.** Run the service with a real key, call `/analyze?query=vaccine`, then repeat with a wrong key. Expected: 200 envelope with a real key and 502 `upstream_unauthorized` with a wrong key. Why human: all upstream behaviour here was mocked, and the `X-Api-Key` header acceptance and the response-shape assumptions A1-A2 (D-19) need one real call.
2. **Confirm the old key from commit 1fedcd2 is revoked.** Nothing in the repo can prove it, because history is intentionally unscanned below the floor and not rewritten (D-09, D-11).
3. **Accept the WR-02 policy:** a malformed key is rejected at startup rather than stripped.

(The GitHub Actions run, which the request listed as a human item, was observable from this container through `gh`. It was green for HEAD, so it is recorded as verified above and not as a human item.)

## Gaps Summary

No gaps. Phase 1 achieves its goal in the code: no credential in the tree, upstream failures surface as honest problem+json 502/503, provenance is on every response, fixture data is reachable only through `DEMO_MODE=true` and is labelled synthetic, input is validated, OpenAPI is typed, and the defects are pinned as strict xfails before any behavioural change. The status is `human_needed` only because of the three owner-side items above. The one bookkeeping point is that FND-02 is still unchecked in REQUIREMENTS.md.

---

_Verified: 2026-10-16T11:30:00Z_
_Verifier: Claude (gsd-verifier)_
