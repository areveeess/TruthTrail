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
- **After every plan wave:** Run `python -m pytest -q` plus `python scripts/copy_guard.py`
- **Before `/gsd-verify-work`:** Full suite green; `copy_guard.py` exit 0; local gitleaks script exit 0 against `FLOOR..HEAD`; CI run green after push
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (filled by planner) | | | FND-01 | credential disclosure | no credential literal in tracked source; missing key fails fast; `.env.example` names only | unit | `python -m pytest -q tests/test_no_hardcoded_credentials.py tests/test_settings.py` | ❌ W0 | ⬜ pending |
| (filled by planner) | | | FND-01 | credential disclosure | gitleaks working tree and new-commit range clean | CI + local | `bash scripts/gitleaks_scan.sh ...` (exit 0) | ❌ W0 | ⬜ pending |
| (filled by planner) | | | FND-02 | fabricated-success / key leak via exception text | GNews 401 returns 502 problem+json, not 200; 403/429/5xx/timeout/ConnectionError/non-JSON/null-field mapped; key/URL absent from body and logs | integration | `python -m pytest -q tests/test_upstream_errors.py` (incl. `::test_gnews_401_returns_502_not_200`) | ❌ W0 | ⬜ pending |
| (filled by planner) | | | FND-03 | unlabelled synthetic data | every response carries `synthetic` / `data_as_of` / `source_status`; live has no `events`; fixture only under `DEMO_MODE=true`; error bodies carry provenance too (D-15) | integration | `python -m pytest -q tests/test_provenance_demo.py` | ❌ W0 | ⬜ pending |
| (filled by planner) | | | FND-04 | input abuse | empty / whitespace / 201-char / control-char / missing query returns 422 problem+json without echoing input; OpenAPI has a typed 2xx schema for every operation | contract | `python -m pytest -q tests/test_validation_openapi.py` | ❌ W0 | ⬜ pending |
| (filled by planner) | | | FND-05 | regression risk | `analyze_risk` golden table + strict-xfail defects; simulator invariants + strict-xfail child-before-parent; legacy `/analyze` shape; unmocked network blocked — committed BEFORE any behavioural change | unit | `python -m pytest -q tests/test_char_risk_analyzer.py tests/test_char_simulator.py tests/test_char_analyze_legacy.py` | ❌ W0 | ⬜ pending |
| (filled by planner) | | | FND-06 | overclaiming | banned phrases fail, allow marker works, README contains the required phrase, OpenAPI strings clean | unit | `python -m pytest -q tests/test_copy_guard.py` and `python scripts/copy_guard.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pytest.ini`, pinned `requirements.txt` (adds `pydantic`, `pydantic-settings`), `requirements-dev.txt`
- [ ] `tests/conftest.py` — autouse network guard, env scrub, `client_factory`, `mock_gnews` (**first commit of the phase**; the real key is still live in source until the removal plan lands)
- [ ] `tests/test_char_risk_analyzer.py`, `tests/test_char_simulator.py`, `tests/test_char_analyze_legacy.py` — committed before any behavioural change
- [ ] `tests/test_no_hardcoded_credentials.py` (regex backstop for the entropy gap in gitleaks), `tests/test_settings.py`, `tests/test_upstream_errors.py`, `tests/test_provenance_demo.py`, `tests/test_validation_openapi.py`, `tests/test_copy_guard.py`
- [ ] `scripts/copy_guard.py`, `scripts/gitleaks_scan.sh`, `scripts/generate_demo_fixture.py`
- [ ] Framework install: `python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| CI workflow is green on the pushed branch | FND-06 | The workflow YAML cannot be executed in the dev container (GitHub API and `gh` are blocked); it can only be confirmed by a real Actions run | After push, open the Actions run for the head commit; confirm copy-guard, gitleaks and pytest jobs pass |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
