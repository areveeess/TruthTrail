---
phase: 01-secure-honest-foundation
plan: 06
subsystem: ci
tags: [copy-guard, gitleaks, github-actions, readme, secret-scan, honesty]

requires:
  - phase: 01-secure-honest-foundation
    provides: key literal removed from the working tree (01-02), honest OpenAPI copy (01-05), pinned requirements and test harness (01-01)
provides:
  - scripts/copy_guard.py (seven banned-copy rules, required "flag for human review" phrase, allow marker, OpenAPI string walk) plus tests/test_copy_guard.py
  - README.md rewritten as an honest "prototype under reconstruction" note
  - scripts/install_gitleaks.sh (pinned 8.30.1, sha256-verified on both the download and GITLEAKS_TARBALL routes)
  - scripts/gitleaks_scan.sh (git-visible working-tree scan plus a validated, floor-bounded, fail-closed commit-range scan)
  - scripts/gitleaks_selftest.sh (throwaway-repository proof of the range rules and redacted detection)
  - .github/workflows/ci.yml (copy-guard, gitleaks, tests jobs; contents: read; SHA-pinned actions)
affects: [phase-02]

actuals:
  tokens: 8300
  tasks: 3
  commits: 3
plan_head_before: 0c1d6fd462308398d0dee1f07e13a69d181e7211
plan_head_after: 88281c5e915ba7ca72fd9d74309b6961bc1ce5b5

tech-stack:
  added: [gitleaks 8.30.1 (CI and local binary, not a Python dependency), pyyaml 6.0.3 (dev pin)]
  patterns:
    - "Guard scripts live in scripts/ (never scanned by the copy guard) and are exercised by pytest through importlib plus a subprocess CLI test"
    - "Range scan: validate every ref, normalise to full SHAs, merge-base for a non-ancestor base, clamp to the floor, bound with ^floor, announce an empty range"

key-files:
  created:
    - scripts/copy_guard.py
    - tests/test_copy_guard.py
    - scripts/install_gitleaks.sh
    - scripts/gitleaks_scan.sh
    - scripts/gitleaks_selftest.sh
    - .github/workflows/ci.yml
  modified:
    - README.md
    - requirements-dev.txt

key-decisions:
  - "The range scan is bounded with ^FLOOR in addition to the BASE clamp (01-VALIDATION.md 'Known Issues Accepted at the Plan-Check Cap'), so a branch that forked before the rotated-key commit and later merged newer history cannot pull pre-floor commits back into the range"
  - "OpenAPI skip keys ($ref, operationId, pattern, format, type) are skipped only when their value is a string leaf, so a schema property named 'type' cannot hide its description from the guard"

patterns-established:
  - "Every commit of this plan ran tests/test_no_hardcoded_credentials.py and a 32-hex scan over the added lines first; from Task 2 on also the gitleaks scan script"

requirements-completed: [FND-06, FND-01]

coverage:
  - id: D1
    description: "Banned overclaiming copy (truth-detection, fake-news-detector, detects-misinformation, detects-misleading, misinformation-detector, AI-based/AI-powered, all-caps verdict label) in README, docs, UI dirs or any OpenAPI string fails the guard; the README must contain 'flag ... for human review'; tests/ and .planning/ are excluded; the allow marker works on the line and the line before"
    requirement: FND-06
    verification:
      - kind: unit
        ref: "tests/test_copy_guard.py (rules, clean samples, allow marker, readme phrase, exclusions, OpenAPI walk, CLI exit codes)"
        status: pass
    human_judgment: false
  - id: D2
    description: "The rewritten README and the live OpenAPI document pass the guard (python scripts/copy_guard.py prints 'copy-guard: clean (1 files, 135 OpenAPI strings)'); the previous README produced exactly the three expected findings (ai-claim, detects-misleading, missing-required-phrase)"
    requirement: FND-06
    verification:
      - kind: unit
        ref: "tests/test_copy_guard.py#test_repository_copy_is_clean"
        status: pass
      - kind: other
        ref: ".venv/bin/python scripts/copy_guard.py exits 0"
        status: pass
    human_judgment: false
  - id: D3
    description: "A checksum-pinned gitleaks 8.30.1 scans the git-visible working tree and the range a5dd825..HEAD with no baseline and exits 0 (clean) locally"
    requirement: FND-01
    verification:
      - kind: other
        ref: "bash scripts/gitleaks_scan.sh /tmp/truthtrail-gitleaks/gitleaks a5dd825 HEAD a5dd825 -> 'gitleaks: clean' (exit 0), run before each of the Task 2 and Task 3 commits"
        status: pass
    human_judgment: false
  - id: D4
    description: "Range rules: sentinel->floor (exit 0), sentinel with a bogus floor / bogus base / bogus head / bogus floor (exit 2), HEAD as base over the floor (exit 0 via merge-base, empty range announced), pre-rotation initial commit as base (exit 0 via floor clamp)"
    requirement: FND-01
    verification:
      - kind: other
        ref: "eight in-repo cases of 01-06-PLAN.md Task 2 verify, all matched"
        status: pass
    human_judgment: false
  - id: D5
    description: "Self-test in throwaway repositories: advanced PR base scanned from the merge-base (exit 0 clean, exit 1 with a planted value, redacted), unrelated history exit 2, working-tree detection exit 1 redacted, merged pre-floor branch exit 0 with a control scan of the same range exit 1"
    requirement: FND-01
    verification:
      - kind: other
        ref: "bash scripts/gitleaks_selftest.sh /tmp/truthtrail-gitleaks/gitleaks -> 'selftest: all scenarios passed'"
        status: pass
    human_judgment: false
  - id: D6
    description: ".github/workflows/ci.yml has exactly the jobs copy-guard, gitleaks, tests; permissions contents: read; five action references all pinned by 40-hex SHA with a version comment; no secrets context; push and pull_request triggers only"
    requirement: FND-06
    verification:
      - kind: other
        ref: "yaml contract check prints 'workflow ok'; uses-pin grep passes; grep 'secrets\\.' prints nothing"
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-10-16
status: complete
---

# Phase 1 Plan 06: Copy Guard, Secret Scan and CI Summary

**An honest README, a copy guard that fails on overclaiming wording (README, docs, UI dirs, every OpenAPI string), a checksum-pinned and fail-closed gitleaks working-tree plus commit-range scan proven in throwaway repositories, and a three-job SHA-pinned CI workflow.**

## Performance

- **Duration:** about 6 min (2026-10-16T10:29:46Z to about 10:36Z)
- **Tasks:** 3
- **Files modified:** 8 (6 created, 2 modified)

## Accomplishments

- `scripts/copy_guard.py` implements the seven rules (truth-claim, fake-news-detector, detects-misinformation, detects-misleading, misinformation-detector, ai-claim, fake-verdict-label), the required `flag ... for human review` README phrase, the `copy-guard: allow` marker (same line, any line of a wrapped match, or the line before), the excluded prefixes and the OpenAPI string walk. It passes on the repo (`copy-guard: clean (1 files, 135 OpenAPI strings)`) and failed the previous README with exactly three findings.
- `README.md` states "prototype under reconstruction", frames the output as a flag for human review, documents the five variable names, `DEMO_MODE`, `data_as_of` semantics and the run, test and guard commands, and lists what is not here yet (Phases 3-5).
- `scripts/gitleaks_scan.sh` scans every git-visible working-tree file (via an exported copy, so a local `.venv/` or `.env` is never scanned or printed) and a validated commit range. It exits 2 on any unresolvable base, head or floor, scans a non-ancestor base from the merge-base, clamps a pre-floor base to the floor, bounds the range with `^FLOOR` and announces an empty range.
- `scripts/install_gitleaks.sh` verifies the pinned sha256 before extraction on both routes and refuses a destination inside the repository.
- `.github/workflows/ci.yml` runs `copy-guard`, `gitleaks` (fetch-depth 0, binary in `$RUNNER_TEMP`) and `tests`.
- Full suite: 183 passed, 10 xfailed, no XPASS (163 passed before this plan plus 20 new copy-guard test cases). Credential backstop: 13 passed.

## Task Commits

1. **Task 1: Copy guard end to end, README rewrite (tracer)** - `af86d9d` (feat)
2. **Task 2: Pinned gitleaks install, fail-closed range scan, self-test** - `03af4e8` (feat)
3. **Task 3: CI workflow (plus pyyaml pin)** - `88281c5` (chore)

**Plan metadata:** committed separately after this file (docs commit).

Tracer gate: `workflow.human_verify_mode` is `end-of-phase` and the Task 1 verify is automated-only, so it was re-run after the commit (guard clean, full suite 183 passed / 10 xfailed) and the plan expanded: `Tracer verified end-to-end`.

## gitleaks install route and evidence

- **Install route:** release download (`gitleaks: downloaded release archive`), sha256 `551f6fc8...70eb` matched the pin. The `GITLEAKS_TARBALL` route was also exercised with the downloaded archive (verified, installed) and with a junk file (exit 1, "refusing to extract", archive removed), a missing file (exit 2) and an in-repo destination (exit 2).
- **In-repo cases (all matched the plan):**

| Case | Exit | Key output |
|---|---|---|
| floor..HEAD | 0 | `gitleaks: clean` |
| sentinel + real floor | 0 | `new-branch sentinel base, scanning from the floor`, `gitleaks: clean` |
| sentinel + bogus floor | 2 | `unusable range: base not found` |
| `not-a-commit` base | 2 | `unusable range: base not found` (no floor fallback) |
| `not-a-commit` head | 2 | `unusable range: head not found` |
| bogus floor, valid base/head | 2 | `unusable range: floor not found` |
| HEAD as base, floor as head | 0 | `not an ancestor`, `merge-base`, `commit range is empty`, `gitleaks: clean` |
| initial commit 1c0ca0e as base | 0 | `at or behind the floor`, `gitleaks: clean` |

- **Control:** the unbounded scan `1c0ca0e..HEAD` exits 1 (it reaches the inert rotated key); the same range with `^a5dd825` exits 0.
- **Self-test case lines:**

```
selftest: advanced-pr-base: ok
selftest: advanced-pr-base-leak: ok
selftest: unrelated-history: ok
selftest: working-tree-leak: ok
selftest: merged-prefloor-branch: ok
selftest: merged-prefloor-control: ok
selftest: all scenarios passed
```

The generated values were never echoed, written to the repository or placed in a commit message. No `.gitleaksignore` was needed: the clean scan produced no findings.

## Plan-check cap fix applied (01-VALIDATION.md "Known Issues Accepted at the Plan-Check Cap")

The accepted warning said the floor clamp only applies when the base is an ancestor of the floor, so a branch that forked before `1fedcd2` and later merged `main` would leave `BASE..HEAD` containing the rotated-key commit. **The prescribed fix was applied in Task 2:**

- `scripts/gitleaks_scan.sh` bounds the range by the floor: `--log-opts="${BASE}..${HEAD_SHA} ^${FLOOR}"` (and the commit count uses the same `^FLOOR` exclusion), so everything reachable from the floor is excluded.
- `scripts/gitleaks_selftest.sh` gained the "merged pre-floor branch" scenario: an old feature branch (base X) merged post-floor history (head Z) while the pre-floor history holds a planted value; the scan exits 0 with the value absent from the output. A control scan of the same range without the bound exits 1, proving the scenario would otherwise be red. The self-test now has five scenarios plus the control (six case lines) instead of the plan's four.
- Advisories followed: `pyyaml==6.0.3` is pinned in `requirements-dev.txt` (the workflow contract check imports it; the venv already had 6.0.3 transitively through `responses`); the `fails_when` lines were not touched in this plan (no exact-count lines exist in 01-06, and test gating here is by named tests). T-01-38 wording is narrowed as stated under Threat notes.

## Deviations from Plan

**1. [Rule 2 - Missing critical functionality] Floor bound for merged pre-floor branches**
- **Found during:** Task 2 (instructed by the orchestrator from 01-VALIDATION.md)
- **Issue:** the floor clamp alone leaves pre-floor commits in the range for a branch that is neither an ancestor nor a descendant of the floor.
- **Fix:** `^FLOOR` bound plus self-test scenario and control, described above.
- **Files modified:** `scripts/gitleaks_scan.sh`, `scripts/gitleaks_selftest.sh`
- **Commit:** `03af4e8`

**2. [Rule 2] OpenAPI walk descends into dict values under skip keys**
- **Found during:** Task 1 design
- **Issue:** the plan skips values under the keys `$ref`, `operationId`, `pattern`, `format` and `type`; applied literally, a schema property named `type` (the `Problem` model has one) would hide its whole subtree, including its description, from the guard.
- **Fix:** the skip applies to string leaves only; `test_openapi_strings_are_walked` covers the case.
- **Files modified:** `scripts/copy_guard.py`, `tests/test_copy_guard.py`
- **Commit:** `af86d9d`

**3. [Rule 3] `pyyaml==6.0.3` added to `requirements-dev.txt`** (file outside the plan's `files_modified`), per the VALIDATION advisory, because the Task 3 verify imports `yaml`. Commit `88281c5`.

**4. Minor wording differences:** the range line reads `== (b) commit range <b7>..<h7> excluding history up to the floor (<n> commits)` (the plan listed `(<n> commits)` without the middle phrase); `install_gitleaks.sh` prints a `sha256 verified` line in addition to the route line.

**Total deviations:** 3 auto-fixed/added, 1 wording note. No architectural change.

**Post-plan orchestrator fix (commit after aca5205):** the selftest's planted value was a random urlsafe token that gitleaks' generic-api-key rule sometimes drops (stopwords/entropy), so the selftest failed intermittently (3 of 11 runs observed). It now builds an AWS-shaped value from 16 distinct symbols at run time; 40 consecutive runs passed.

## Issues Encountered

None. The release download was reachable through the proxy on the first attempt, so no checksum pin was loosened and no tarball route was needed.

## Action SHA re-verification

Re-verified with `git ls-remote` (network was reachable): `actions/checkout` `refs/tags/v7.0.1` = `3d3c42e5aac5ba805825da76410c181273ba90b1` and `actions/setup-python` `refs/tags/v7.0.0` = `5fda3b95a4ea91299a34e894583c3862153e4b97`. Both are lightweight tags (no peeled entry); both match the research pins, so no SHA changed.

## Threat notes

- T-01-38 (narrowed): the workflow installs only the exact-pinned `requirements.txt` / `requirements-dev.txt` entries from 01-01 (plus the `pyyaml` pin added here). The transitive dependencies of those packages are not hash-pinned; that is Phase 2 work (uv lockfile, pip-audit). The statement "never installs an unpinned package" covers direct requirements only.
- T-01-32: gitleaks installed only after sha256 match; actions pinned by SHA.
- T-01-33: `permissions: contents: read`, push and pull_request triggers only, no `secrets.` reference.
- Gap to remember: gitleaks is a net (a low-entropy value assigned to a key name can pass); `tests/test_no_hardcoded_credentials.py` stays in the tests job as the backstop.

## Known Stubs

None.

## Threat Flags

None. No new endpoint or runtime trust boundary; the CI workflow and the downloaded scanner binary are the plan's own threat-model items.

## Constraints verified

- `spread_simulator.py`, `users.py`, `risk_analyzer.py` untouched by this plan (the diff since the plan start lists none of them); `models.py` and `main.py` untouched.
- No push, force-push, history rewrite, branch, worktree or pull request. The real GNews API was never called.

## Non-gating follow-ups

Not blocking plan or phase completion:

- **Post-push CI confirmation (FND-06; mirrors 01-VALIDATION.md Manual-Only Verifications):** after the phase is pushed to branch `claude/sleepy-lovelace-13aums`, open the GitHub Actions run for the head commit and confirm the copy-guard, gitleaks and tests jobs finish green, with `gitleaks: clean` for both the working tree and the commit range. Why it cannot run here: the GitHub API and `gh` are blocked in the dev container, so the workflow itself cannot be executed or observed (Assumption A6). The action SHAs were re-verified with `git ls-remote` (see above), so a wrong-SHA start failure is not expected.
- First push of a branch sends `github.event.before` as the 40-zero sentinel, which exercises the sentinel path in CI; the first push after that exercises a normal range. Both are covered locally by the scan cases above.

## Self-Check: PASSED

- Created and modified files exist: scripts/copy_guard.py, tests/test_copy_guard.py, README.md, scripts/install_gitleaks.sh, scripts/gitleaks_scan.sh, scripts/gitleaks_selftest.sh, .github/workflows/ci.yml, requirements-dev.txt (all FOUND).
- Commits are ancestors of HEAD: af86d9d, 03af4e8, 88281c5 (all FOUND).
- Plan verification: `.venv/bin/python -m pytest -q` reports 183 passed, 10 xfailed, 0 XPASS; `python scripts/copy_guard.py` exits 0; the local gitleaks scan, all eight in-repo cases and the self-test passed.
