---
phase: "1"
slug: "secure-honest-foundation"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-11"
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Seeded from `01-RESEARCH.md` § Validation Architecture; the per-task rows are filled in by the planner/checker once PLAN.md files exist. Test client dependency is `httpx==0.28.1` (CONTEXT D-18), not `httpx2`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 + responses 0.26.3 + httpx 0.28.1 (Starlette `TestClient`) |
| **Config file** | `pytest.ini` — Wave 0 creates it (none exists today); `xfail_strict = true` |
| **Quick run command** | `python -m pytest -q -x tests/<affected file>.py` |
| **Full suite command** | `python -m pytest -q` |
| **Non-pytest gates** | `python scripts/copy_guard.py`; `bash scripts/gitleaks_scan.sh <gitleaks-bin> <base> HEAD <floor>` |
| **Estimated runtime** | ~20 seconds (no real network; all upstream calls mocked) |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest -q -x tests/<affected file>.py`
- **Before every task commit, from plan 01-02 onward (CLAUDE.md Security: scan `.planning/` and code for key material before every commit):** a cheap secret check over every git-visible file outside `tests/`, `.planning/` and `.claude/` included. 01-02 Tasks 1-2 (before the backstop exists): `git grep -I -i -l -E --untracked "<backstop regex>" -- . ':(exclude)tests'; test $? -eq 1` (file names only; exact command in 01-02-PLAN.md). From 01-02 Task 3 on: `.venv/bin/python -m pytest -q tests/test_no_hardcoded_credentials.py`. From 01-06 Task 2 on, additionally `bash scripts/gitleaks_scan.sh "${TMPDIR:-/tmp}/truthtrail-gitleaks/gitleaks" a5dd8257e920923677c60e70611a6f36d87747b2 HEAD a5dd8257e920923677c60e70611a6f36d87747b2`. Every task's `<verify>` in 01-02..01-06 carries the applicable check.
- **After every plan wave:** Run `python -m pytest -q` plus `python scripts/copy_guard.py`
- **Before `/gsd-verify-work`:** Full suite green; `copy_guard.py` exit 0; local gitleaks script exit 0 against `FLOOR..HEAD`. The post-push CI run is a non-gating follow-up (see Manual-Only Verifications), not a verify-work gate.
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

Commands assume cwd = repo root and the dev virtualenv `.venv` created by 01-01 Task 1 (`.venv/bin/python`); any plan run in a fresh worktree recreates it first. Threat refs point at the `<threat_model>` tables in the PLAN files.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01-01 | 1 | FND-05 | T-01-01, T-01-SC | first commit of the phase: unmocked network blocked; five env names scrubbed; only the fake key travels on outbound test requests; pinned test tools incl. `httpx==0.28.1` (D-18) on the prototype's still-unpinned `requirements.txt` | unit + integration | `.venv/bin/python -m pytest -q tests/test_network_guard.py` and `git diff --quiet 9b5b085 -- requirements.txt` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01-01 | 1 | FND-05 | T-01-03 | `analyze_risk` golden table + 8 strict-xfail defects; simulator invariants + strict-xfail child-before-parent and mixed formats | unit | `.venv/bin/python -m pytest -q tests/test_char_risk_analyzer.py tests/test_char_simulator.py` | ❌ W0 | ⬜ pending |
| 01-01-03 | 01-01 | 1 | FND-05 | T-01-03, T-01-04, T-01-SC | legacy `/analyze` shape pinned; fabricated-200 / 500 / no-validation defects as strict xfails; committed BEFORE any behavioural change (no production module differs from 9b5b085); then, as the plan's last commit, `requirements.txt` exact pins with per-test outcomes identical under the unpinned prototype runtime and the pinned set | integration | `.venv/bin/python -m pytest -q -rx tests/test_char_analyze_legacy.py` (file retired in 01-05-01) and `diff "${TMPDIR:-/tmp}/truthtrail-char-unpinned.txt" "${TMPDIR:-/tmp}/truthtrail-char-pinned.txt"` | ❌ W0 | ⬜ pending |
| 01-02-01 | 01-02 | 2 | FND-01 | T-01-05, T-01-06, T-01-09 | key read only from env and sent only in `X-Api-Key`; missing key raises ConfigurationError at startup with zero upstream calls | integration | `.venv/bin/python -m pytest -q tests/test_settings.py` | ❌ W0 | ⬜ pending |
| 01-02-02 | 01-02 | 2 | FND-01 | T-01-07, T-01-08 | DEMO_MODE parsing; blank key = missing; no secret in startup errors or repr; real `uvicorn main:app` exits 3 | unit + subprocess | `.venv/bin/python -m pytest -q tests/test_settings.py` | ❌ W0 | ⬜ pending |
| 01-02-03 | 01-02 | 2 | FND-01 | T-01-05, T-01-10 | no credential literal in tracked/unignored files outside `tests/`, `.planning/` and `.claude/` included (scope asserted); `.env.example` names only; `.gitignore` semantics | unit | `.venv/bin/python -m pytest -q tests/test_no_hardcoded_credentials.py` | ❌ W0 | ⬜ pending |
| 01-03-01 | 01-03 | 3 | FND-03 | T-01-12 | committed fixture validates as `AnalyzeResponse` and is labelled synthetic; fixture not git-ignored (needs 01-02 `.gitignore`) | unit | `.venv/bin/python -m pytest -q tests/test_demo_fixture.py` | ❌ W0 | ⬜ pending |
| 01-03-02 | 01-03 | 3 | FND-03 | T-01-12, T-01-14, T-01-16 | three risk labels; monotone UTC `Z` timelines; LiveResult cannot carry `events`; Problem model shape | unit | `.venv/bin/python -m pytest -q tests/test_demo_fixture.py tests/test_response_models.py` | ❌ W0 | ⬜ pending |
| 01-03-03 | 01-03 | 3 | FND-03 | T-01-13, T-01-15 | byte-for-byte regeneration; a hand edit (e.g. synthetic flipped) fails `--check` | unit | `.venv/bin/python scripts/generate_demo_fixture.py --check` and `.venv/bin/python -m pytest -q tests/test_demo_fixture.py` | ❌ W0 | ⬜ pending |
| 01-04-01 | 01-04 | 3 | FND-02 | T-01-17, T-01-18 | GNews 401 returns 502 problem+json, not 200; no key, host or URL in body, logs or exception | integration | `.venv/bin/python -m pytest -q tests/test_upstream_errors.py::test_gnews_401_returns_502_not_200` | ❌ W0 | ⬜ pending |
| 01-04-02 | 01-04 | 3 | FND-02 | T-01-17, T-01-18, T-01-20, T-01-21 | 403/400/5xx/non-JSON/null-field/naive-date -> 502; timeout/unreachable/429 -> 503 + Retry-After (cap 3600); `totalArticles: 0` valid empty; raised `from None`; timeout (3.05, 10) | integration | `.venv/bin/python -m pytest -q tests/test_upstream_errors.py` | ❌ W0 | ⬜ pending |
| 01-04-03 | 01-04 | 3 | FND-04 | T-01-19, T-01-22, T-01-23 | empty / whitespace / 201-char / control-char / missing query -> 422 problem+json (title asserted via `HTTPStatus(422).phrase`) without echoing input; 404/405/not_configured/500 share the shape | integration | `.venv/bin/python -m pytest -q tests/test_request_validation.py` | ❌ W0 | ⬜ pending |
| 01-05-01 | 01-05 | 4 | FND-03 | T-01-25, T-01-26 | envelope `{results, meta}` with provenance; live results have no `events`; fabricated fallback gone; legacy list tests retired with replacement map | integration | `.venv/bin/python -m pytest -q tests/test_provenance_demo.py` | ❌ W0 | ⬜ pending |
| 01-05-02 | 01-05 | 4 | FND-03 | T-01-24, T-01-27, T-01-28 | fixture served only under `DEMO_MODE=true` and only if labelled synthetic; empty -> honest 200; provenance on every response incl. errors (D-15) | integration | `.venv/bin/python -m pytest -q tests/test_provenance_demo.py` | ❌ W0 | ⬜ pending |
| 01-05-03 | 01-05 | 4 | FND-04 | T-01-29 | OpenAPI: typed 2xx schema for every operation; 422/500/502/503 problem+json; real bodies match declared models; honest metadata copy | contract | `.venv/bin/python -m pytest -q tests/test_openapi_contract.py` | ❌ W0 | ⬜ pending |
| 01-06-01 | 01-06 | 5 | FND-06 | T-01-34 | banned phrases fail, allow marker works, README contains the required phrase, OpenAPI strings clean | unit | `.venv/bin/python -m pytest -q tests/test_copy_guard.py` and `.venv/bin/python scripts/copy_guard.py` | ❌ W0 | ⬜ pending |
| 01-06-02 | 01-06 | 5 | FND-01 | T-01-30, T-01-31, T-01-32, T-01-36, T-01-37 | gitleaks (sha256-pinned) clean on git-visible working tree and `a5dd825..HEAD`; only the 40-zero new-branch sentinel base falls back to the floor (exit 0 on the clean range); a non-sentinel unresolvable base (`not-a-commit`), a bogus floor behind the sentinel, a bogus head or a non-ancestor base each exit 2 | CI script, local | `bash scripts/install_gitleaks.sh "${TMPDIR:-/tmp}/truthtrail-gitleaks" && bash scripts/gitleaks_scan.sh "${TMPDIR:-/tmp}/truthtrail-gitleaks/gitleaks" a5dd8257e920923677c60e70611a6f36d87747b2 HEAD a5dd8257e920923677c60e70611a6f36d87747b2` | ❌ W0 | ⬜ pending |
| 01-06-03 | 01-06 | 5 | FND-06, FND-01 | T-01-32, T-01-33, T-01-SC | CI runs copy-guard, gitleaks and tests jobs; SHA-pinned actions; `permissions: contents: read`; no secrets referenced; backstop and gitleaks scan clean before the commit (post-push Actions run is a non-gating follow-up, not in verify) | config contract | `.venv/bin/python -c "import yaml; d = yaml.safe_load(open('.github/workflows/ci.yml')); assert set(d['jobs']) == {'copy-guard', 'gitleaks', 'tests'}"` and `.venv/bin/python -m pytest -q` and the gitleaks scan command from 01-06-02 | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pytest.ini`, `requirements-dev.txt` (test-tool pins only) (01-01-01); pinned `requirements.txt` (adds `pydantic`, `pydantic-settings`) is the LAST commit of 01-01 (01-01-03), after per-test outcomes are shown identical under the unpinned prototype runtime and the pinned set
- [ ] `tests/conftest.py` — autouse network guard, env scrub, `client_factory`, `mock_gnews` (**first commit of the phase**, together with `pytest.ini`, before any pin change, 01-01-01; the real key is still live in source until 01-02 lands) plus `tests/test_network_guard.py`
- [ ] `tests/test_char_risk_analyzer.py`, `tests/test_char_simulator.py`, `tests/test_char_analyze_legacy.py` — committed before any behavioural change (01-01-02, 01-01-03)
- [ ] `tests/test_settings.py`, `tests/test_no_hardcoded_credentials.py` (regex backstop for the entropy gap in gitleaks) (01-02)
- [ ] `tests/test_demo_fixture.py`, `tests/test_response_models.py` (01-03)
- [ ] `tests/test_upstream_errors.py`, `tests/test_request_validation.py` (01-04); `tests/test_provenance_demo.py`, `tests/test_openapi_contract.py` (01-05); `tests/test_copy_guard.py` (01-06) — the seeded name `test_validation_openapi.py` was split into `test_request_validation.py` and `test_openapi_contract.py`
- [ ] `scripts/generate_demo_fixture.py` (01-03), `scripts/copy_guard.py`, `scripts/install_gitleaks.sh`, `scripts/gitleaks_scan.sh` (01-06)
- [ ] Framework install: `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt` (01-01-01)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| CI workflow is green on the pushed branch (**non-gating follow-up**: does not block 01-06, the phase or `/gsd-verify-work`; recorded as an open item in 01-06-SUMMARY.md "Non-gating follow-ups") | FND-06 | The workflow YAML cannot be executed in the dev container (GitHub API and `gh` are blocked); it can only be confirmed by a real Actions run after the push | After push, open the Actions run for the head commit; confirm copy-guard, gitleaks and pytest jobs pass |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
