---
phase: 02-engineering-baseline
plan: 03
subsystem: packaging
tags: [uv, uv-lock, pyproject, dependency-groups, ci, setup-uv, static-ci-test]

requires:
  - phase: 02-engineering-baseline
    provides: plan 02-02 src/truthtrail package, legacy/ directory, root main.py shim
provides:
  - pyproject.toml (exact-pinned serving dependencies, dev and train groups, pytest configuration)
  - uv.lock generated with uv 0.13.1 (revision 5, 73 packages, train group included)
  - .python-version (3.13)
  - copy-guard and tests CI jobs on SHA-pinned astral-sh/setup-uv v9.0.0 with uv sync --locked
  - README uv setup block and Windows (PowerShell) subsection
  - tests/test_dependency_groups.py and tests/test_ci_workflow.py (machine-checked dependency policy and CI contract)
affects: [02-04, 02-05, 02-06, 02-07, 02-08, 02-09, 02-10, 02-11, 02-12]

actuals:
  tokens: 17000
  tasks: 2
  commits: 2
plan_head_before: c90bc45f8cd5717737d67dd6d73653e53ab80538
plan_head_after: 1def85b0c03746d2bd6754c55cd11609810cba1c

tech-stack:
  added: [uv 0.13.1 (lock), uv_build, slowapi 0.1.10, limits 5.8.0, cachetools 7.2.3, pytest-cov, hypothesis, ruff, mypy, pip-audit, scikit-learn and numpy (train group only)]
  patterns:
    - "One lock for serving, dev and train; train is locked but never synced by default"
    - "Static CI contract test parses the workflow YAML so configuration drift is caught without a runner"

key-files:
  created:
    - pyproject.toml
    - uv.lock
    - .python-version
    - tests/test_dependency_groups.py
    - tests/test_ci_workflow.py
  modified:
    - .gitignore
    - .github/workflows/ci.yml
    - README.md
  deleted:
    - requirements.txt
    - requirements-dev.txt
    - pytest.ini

key-decisions:
  - "Followed the plan as written; implements D-14, D-17, D-22, D-24, D-25, D-26 with no new decisions"

requirements-completed: [ENG-02]

status: complete
completed: 2026-10-17
---

# Phase 2 Plan 03: uv Project, Lock and CI on uv Summary

**The pip manifests and pytest.ini are replaced by a uv project: `pyproject.toml` with exact-pinned serving dependencies and a dev/train split, a committed `uv.lock` (uv 0.13.1, 73 packages) that the container's uv 0.11.32 also accepts, and CI `copy-guard` and `tests` jobs that install with SHA-pinned setup-uv and `uv sync --locked`.**

## Commits

| Task | Commit | Notes |
|------|--------|-------|
| 1. uv project, lock, groups, pytest config; retire pip manifests | `1c8cfe2` | Green: 294 passed, 10 xfailed |
| 2. CI and README on uv, static CI contract test | `1def85b` | Green: 303 passed, 10 xfailed |

## What was built

- `pyproject.toml`: build backend `uv_build>=0.13.1,<0.14`; `requires-python = ">=3.13,<3.14"`; no `readme` key; no `required-version`; `[dependency-groups]` `dev` (default through `[tool.uv] default-groups = ["dev"]`) and `train` (scikit-learn, numpy; unused until Phase 4); `[tool.pytest.ini_options]` with `pythonpath = ["legacy", "."]`, `xfail_strict = true`, `addopts = "-ra"` (no `--cov`) and `filterwarnings = ["error", "ignore:Using .httpx. with .starlette.testclient. is deprecated"]`.
- `uv.lock` header: `version = 1`, `revision = 5`, `requires-python = "==3.13.*"`. The root `truthtrail` entry lists the nine serving packages as runtime dependencies and `train` as a dev-dependency group naming only numpy and scikit-learn.
- `requirements.txt`, `requirements-dev.txt` and `pytest.ini` deleted (`git rm`) in the same commit that adds `pyproject.toml`, after the suite was green under uv. `.hypothesis/` added to `.gitignore`.
- `.github/workflows/ci.yml`: `copy-guard` runs `uv sync --locked --no-dev` then `uv run --locked --no-dev python scripts/copy_guard.py`; `tests` runs `uv sync --locked` then `uv run --locked pytest -q`; both use `astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9 # v9.0.0` with `version: "0.13.1"`, `python-version: "3.13"`, `enable-cache: true`. The `gitleaks` job is textually unchanged (the staged diff had hunks only at lines 1-2, 25-28 and 82-85, none inside that job). Job names, `permissions: contents: read`, concurrency, timeouts and `persist-credentials: false` are unchanged.
- README "Run and check" uses `uv sync`, `DEMO_MODE=true uv run uvicorn main:app`, `uv run pytest -q`, `uv run python scripts/copy_guard.py`, a Windows (PowerShell) subsection, and states that `uv.lock` pins versions and the `train` group is not installed by default. "flag for human review" and all other sections are unchanged.
- `tests/test_dependency_groups.py` (8 tests) and `tests/test_ci_workflow.py` (9 tests).

## uv versions and lock acceptance

| Check | uv 0.13.1 | uv 0.11.32 |
|-------|-----------|-----------|
| Generated the lock | yes (`uv lock`, 73 packages) | no |
| `uv lock --check` | passes | passes |
| `uv sync --locked` | passes (scratch environment) | passes (project `.venv`, serving-only environment and a fresh clone of the committed state) |

The lock kept `version = 1` / `revision = 5` under both versions and neither rewrote it. The scratch uv 0.13.1 was installed with pip into a virtualenv outside the repository; PyPI was reachable and no TLS workaround was needed. `UV_SYSTEM_CERTS=true` was set to silence the `UV_NATIVE_TLS` deprecation warning.

## Verification

| Check | Result |
|-------|--------|
| Full suite after Task 1 (pyproject.toml, pytest.ini deleted) | 294 passed, 10 xfailed, no XPASS (was 286 + 8 new) |
| Full suite after Task 2 | 303 passed, 10 xfailed, no XPASS (+9 new) |
| Serving-only sync (`--no-dev`) | fastapi, slowapi, cachetools importable; pytest, sklearn, numpy, ruff absent |
| Fresh `git clone` of the Task 1 commit | `uv sync --locked` succeeds; `test_dependency_groups.py` and `test_main_shim.py`: 9 passed |
| gitleaks (floor to HEAD plus working tree) before Task 1 commit | clean |
| `tests/test_no_hardcoded_credentials.py` and 32-hex added-lines scan | 13 passed, 0 hits before each commit |
| `scripts/copy_guard.py` | clean (1 file, 135 OpenAPI strings) |
| `ci.yml` grep for `pip install`, `requirements`, `setup-python` | no matches |

No Docker daemon and no GitHub Actions run were involved; neither is claimed.

## Dependency review (D-26)

Owner review in place of a checkpoint (D-26 repeats the Phase 1 D-18 waiver). `gsd-tools` marks every PyPI package suspicious only because PyPI exposes no download counts; no SLOP verdict exists for any package. First-upload years come from 02-RESEARCH.md "Package Legitimacy Audit". `grep -c '^\[\[package\]\]' uv.lock` = **73**.

| Package | Pinned | Group | Purpose | First upload |
|---------|--------|-------|---------|--------------|
| fastapi | 0.143.0 | serving | HTTP API framework | Phase 1 dependency (pre-existing) |
| starlette | 1.8.0 | serving | ASGI toolkit under FastAPI (pinned directly for the warnings-as-errors suite) | Phase 1 dependency (pre-existing) |
| pydantic | 2.14.0 | serving | Response models and validation | Phase 1 dependency (pre-existing) |
| pydantic-settings | 2.15.0 | serving | Environment-based settings | Phase 1 dependency (pre-existing) |
| uvicorn | 0.54.0 | serving | ASGI server | Phase 1 dependency (pre-existing) |
| requests | 2.34.2 | serving | Outbound HTTP to the news provider | Phase 1 dependency (pre-existing) |
| slowapi | 0.1.10 | serving | Rate limiting (plan 02-07); **low adoption**: small maintainer base, one release in 2024-2026, open upstream issue 281 (fail-open); used through decorators only | 2020 |
| limits | 5.8.0 | serving | slowapi's engine, imported directly to validate rate-limit settings at startup | 2015 |
| cachetools | 7.2.3 | serving | TTL cache (plan 02-08); 7.2.3 was uploaded the day of research, lock-pinned | 2014 |
| pytest | 9.1.1 | dev | Test runner | Phase 1 dependency (pre-existing) |
| pytest-cov | 7.1.0 | dev | Coverage reporting (ENG-03) | 2010 |
| hypothesis | 6.170.1 | dev | Property-based tests (ENG-03) | 2013 |
| responses | 0.26.3 | dev | HTTP mocking for the network guard | Phase 1 dependency (pre-existing) |
| httpx | 0.28.1 | dev | FastAPI TestClient transport | Phase 1 dependency (pre-existing) |
| pyyaml | 6.0.3 | dev | Parses the CI workflow in tests | Phase 1 dependency (pre-existing) |
| ruff | 0.17.1 | dev | Lint and format (plan 02-04) | 2022 |
| mypy | 2.4.0 | dev | Type checking | 2009 |
| pip-audit | 2.10.1 | dev | Vulnerability audit in CI (plan 02-12) | 2021 |
| scikit-learn | 1.9.1 | train | Classifier (Phase 4); locked, never installed by default | long established |
| numpy | 2.5.4 | train | Numerics (Phase 4); locked, never installed by default | long established |
| uv_build | >=0.13.1,<0.14 | build | Build backend | 2025 |

The Phase 1 pins match the retired requirements files exactly. Transitive packages (53 more in the lock) are fixed by `uv.lock` with sha256 hashes.

## Deviations from Plan

None - plan executed exactly as written. Minor notes:

- The `plan_head_before` value is the HEAD at start of the plan (`c90bc45`), measured with `git rev-list --count c90bc45..HEAD` = 2 before this docs commit.
- `tests/test_dependency_groups.py` wraps one long tuple into two statements for line length; no behaviour difference.

## Open follow-up (non-gating)

After the orchestrator pushes, open the GitHub Actions run for the pushed commit and confirm that `copy-guard`, `gitleaks` and `tests` are green, that setup-uv reports uv 0.13.1 and CPython 3.13, and that `uv sync --locked` succeeds. This cannot be executed in this container (no runner). If setup-uv v9.0.0 rejects `version: "0.13.1"` or `python-version`, apply the fallback in 02-RESEARCH.md assumption A3. Harvested into the phase UAT.

## Known Stubs

None.

## Threat Flags

None. T-02-07 (exact pins, hashed lock, `--locked` everywhere, pin tests), T-02-08 (lock generated by 0.13.1 and accepted by 0.11.32, `required-version` unset) and T-02-09 (SHA-pinned setup-uv, read-only permissions, `persist-credentials: false`, no secrets, enforced by `test_ci_workflow.py`) mitigations are in place as planned.

## Self-Check: PASSED

Created files exist (`pyproject.toml`, `uv.lock`, `.python-version`, `tests/test_dependency_groups.py`, `tests/test_ci_workflow.py`); `requirements.txt`, `requirements-dev.txt` and `pytest.ini` are absent; commits `1c8cfe2` and `1def85b` are ancestors of HEAD.
