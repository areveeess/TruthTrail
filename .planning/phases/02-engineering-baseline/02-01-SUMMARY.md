---
phase: 02-engineering-baseline
plan: 01
subsystem: testing
tags: [line-endings, gitattributes, openapi-golden, content-pins, conftest]

requires:
  - phase: 01-secure-honest-foundation
    provides: characterization suite (274 passed, 10 strict xfail), OpenAPI contract tests, legacy files at 9b5b085
provides:
  - .gitattributes LF policy and a standalone line-ending commit (D-16, folds review item IN-05)
  - tests/golden/openapi_phase1.json, the frozen Phase 1 OpenAPI document, and tests/test_openapi_golden.py (allowed-additions-only contract test)
  - tests/test_legacy_frozen.py, LF-normalised sha256 pins for risk_analyzer.py, spread_simulator.py, users.py and the raw pin of the demo fixture
  - conftest APP_MODULE constant plus app_module and subprocess_env fixtures (D-25)
  - .git-blame-ignore-revs listing the line-ending commit
affects: [02-02, 02-04, 02-05, 02-07]

actuals:
  tokens: 6200
  tasks: 3
  commits: 3
plan_head_before: a7be47b062c1b3bd504f6e9b7cc71564da9688a7
plan_head_after: 2fd84d791b3a9d570f104ae5ca7ed007b1ac24aa

tech-stack:
  added: []
  patterns:
    - "Immutable golden contract: pinned sha256 inside the test, live document compared after removing only declared additions"
    - "String patch targets built from the app_module fixture so a module move changes one conftest line"

key-files:
  created:
    - .gitattributes
    - .git-blame-ignore-revs
    - tests/golden/openapi_phase1.json
    - tests/test_openapi_golden.py
    - tests/test_legacy_frozen.py
  modified:
    - main.py
    - models.py
    - gnews_fetcher.py
    - risk_analyzer.py
    - spread_simulator.py
    - users.py
    - tests/conftest.py
    - tests/test_provenance_demo.py
    - tests/test_request_validation.py

key-decisions:
  - "ENG-01 stays Pending in REQUIREMENTS.md: this plan only freezes what the move must not change; the package move that satisfies ENG-01 is plan 02-02"
  - "client_factory in conftest still does 'import main' (the plan only centralises string patch targets); plan 02-02 / 02-05 change that import together with APP_MODULE"

requirements-completed: []

status: complete
completed: 2026-10-17
---

# Phase 2 Plan 01: Freeze What the Refactor Must Not Change Summary

**Line endings normalised to LF in one standalone commit, the Phase 1 OpenAPI document frozen as a sha256-pinned golden snapshot enforced as "Phase 1 plus declared additions only", and the content of the files that will move pinned by hash.**

## Performance

- **Tasks:** 3
- **Files:** 14 changed (5 created, 9 modified), 3 commits

## Accomplishments

- `.gitattributes` (`* text=auto eol=lf`, `*.sh text eol=lf`) and `git add --renormalize .` produced a commit with exactly seven paths: `.gitattributes` plus main.py, models.py, gnews_fetcher.py, risk_analyzer.py, spread_simulator.py, users.py. Its `--ignore-cr-at-eol --stat` listed only `.gitattributes`, proving the six files differ by line endings alone. After converting the working-tree copies, `git ls-files --eol` shows 99 entries, all `i/lf` (95 at the time of Task 1, 99 now with the new files), and the tree is clean.
- Legacy files are identical to Phase 1 modulo line endings: `git diff --quiet --ignore-cr-at-eol 9b5b085 -- risk_analyzer.py spread_simulator.py users.py` exits 0. The raw (non-ignoring) form of that Phase 1 gate now returns 1 by design (D-21).
- `tests/golden/openapi_phase1.json` was dumped from the unmoved code (`DEMO_MODE=true`, `sort_keys=True`, `indent=2`), 13943 bytes, paths exactly `/analyze`, schemas exactly AnalyzeResponse, DemoResult, Event, FieldIssue, LiveResult, Meta, Problem; a second dump was byte-identical (`cmp`). `tests/test_openapi_golden.py` pins its sha256, compares the live document after removing only `/health`, `/ready`, `429` response entries, extra schemas and the `Problem.synthetic` `const` keyword (D-20), and its messages name sections or codes only, never whole documents.
- conftest gained `APP_MODULE = "main"`, fixture `app_module` and fixture `subprocess_env` (fresh dict, PATH, `PYTHONDONTWRITEBYTECODE=1`, SYSTEMROOT when present). The three string patch targets in test_provenance_demo.py and test_request_validation.py now use `f"{app_module}...."`; `importlib.import_module(app_module)` replaces the literal import. No assertion text changed, and no string literal beginning `"main.` remains in those two files.
- `tests/test_legacy_frozen.py` pins the three legacy files (LF-normalised) and the raw demo fixture.

## Recorded values

| Item | Value |
|------|-------|
| Line-ending commit | `0e9f90bcda102eed833e5f44ee7c646c7f7da957` (`0e9f90b`) |
| risk_analyzer.py (LF) sha256 | `7398c2cfd920b56d971324935956a1342159eef0b808da53b95ed91fab46f23a` |
| spread_simulator.py (LF) sha256 | `e8e61cde19601bfe99311df21fc79ec95ce49ba0f62fdace663c4033a53e362c` |
| users.py (LF) sha256 | `e222249346536212bc1e3d2c7beab00202f647023f9ecbc28bb9797d7a0abfae` |
| Golden file sha256 (`GOLDEN_SHA256`) | `dcd039653878201b74e6a49d3f033d556548ea8612912c2b6da6360683d7dad7` |
| Demo fixture sha256 | `f47fc6926acf3ba976ef28db7d6382f1fcf2da28fad4f493e01fbdb7023f7ec2` |

All three legacy hashes equal the values recorded in 02-RESEARCH.md.

## Task Commits

1. **Task 1: Normalise line endings** - `0e9f90b` (chore)
2. **Task 2: Freeze the Phase 1 OpenAPI contract** - `ce80365` (test)
3. **Task 3: Centralise app module and subprocess env; pin moved files** - `2fd84d7` (test)

**Plan metadata:** committed separately after this file (docs commit).

## Test counts

| Point | Result |
|-------|--------|
| Start of plan | 274 passed, 10 xfailed |
| After Task 1 | 274 passed, 10 xfailed |
| After Task 2 | 277 passed, 10 xfailed (+3 golden tests) |
| After Task 3 | 281 passed, 10 xfailed (+4 frozen tests) |

No XPASS at any point; the 10 strict xfails are untouched. `tests/test_no_hardcoded_credentials.py` (13 passed) and the word-bounded 32-hex added-lines scan ran clean before each commit.

## Deviations from Plan

**1. [Rule 3 - Blocking] Stale index stat data after the working-tree LF conversion**
- **Found during:** Task 1 step 5
- **Issue:** after `sed -i 's/\r$//'` the six files showed ` M` in `git status` with an empty diff (stat-dirty entries left by the renormalise; `git update-index --refresh` reported "needs update").
- **Fix:** `git add` of the same six explicit paths refreshed the index; nothing was staged (`git diff --cached` empty) and no commit was needed.
- **Commit:** none.

**2. [Note] Golden file is 13943 bytes**, one byte over the 13,942 quoted in the research, because the dump ends with the trailing newline the plan's command prescribes. The sha256 is pinned on the file as written.

**3. [Note] ENG-01 not marked complete.** The plan frontmatter lists ENG-01, but the requirement (package layout, legacy removed from the live path) is delivered by plan 02-02; marking it here would be inaccurate.

Total: 1 blocking fix without code impact, 2 notes. No architectural change.

## Known Stubs

None.

## Threat Flags

None. The plan adds tests and a JSON snapshot only; no endpoint, auth path or schema changed.

## Verification notes

- Docker and GitHub Actions are not touched by this plan; nothing about them is claimed.
- No key material was read, printed or written; the credential backstop and the 32-hex scan were clean for all three commits.

## Self-Check: PASSED

All created files exist (`.gitattributes`, `.git-blame-ignore-revs`, golden JSON, the two new test modules) and commits `0e9f90b`, `ce80365`, `2fd84d7` are ancestors of HEAD.
