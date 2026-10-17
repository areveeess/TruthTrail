---
phase: 02-engineering-baseline
plan: 11
subsystem: infra
tags: [docker, container, uv, smoke-test, static-contract, non-root, healthcheck]

requires:
  - phase: 02-engineering-baseline
    provides: plan 02-10 cascade gate; src/truthtrail package with packaged demo fixture, uv.lock, /health and /ready, --no-proxy-headers design (02-07)
provides:
  - "Dockerfile: multi-stage, tag+digest pinned (python:3.13-slim, uv 0.13.1), uv sync --frozen/--locked --no-dev --no-editable, uid 10001, urllib HEALTHCHECK, CMD with --no-proxy-headers"
  - ".dockerignore second line of defence (legacy, tests, scripts, .planning, .claude, markdown, env files, caches)"
  - "tests/test_container_files.py: static contract for both files (12 tests)"
  - "scripts/smoke_app.py: installed-package smoke test used locally and mirrored by the CI docker job in plan 02-12"
affects: [02-12]

actuals:
  tokens: 14000
  tasks: 2
  commits: 2
plan_head_before: a51a51fd1292c2d60bff0189edf1b7c820ab8902
plan_head_after: 7edaf805dcb65fd74967e5cd804bba410714996c

tech-stack:
  added: []
  patterns:
    - "Container security properties asserted by parsing Dockerfile logical lines (continuations joined) instead of building"
    - "Image-equivalent local proof: UV_PROJECT_ENVIRONMENT throwaway dir, uv sync --locked --no-dev --no-editable, run from a temp cwd with a scrubbed environment"

key-files:
  created:
    - Dockerfile
    - .dockerignore
    - tests/test_container_files.py
    - scripts/smoke_app.py
  modified: []

key-decisions:
  - "ENG-05 is left Pending in REQUIREMENTS.md: no docker build or container run has happened (no daemon); plan 02-12 also lists ENG-05 and adds the CI docker job, and the build stays a recorded non-gating human-verify item (D-26)"
  - "The smoke script uses a proxy-free urllib opener so ambient HTTP(S)_PROXY variables cannot intercept loopback requests, and an absolute but not symlink-resolved interpreter path (a venv interpreter locates site-packages through its own path)"

requirements-completed: []

duration: 15min
completed: 2026-10-17
status: complete
---

# Phase 2 Plan 11: Dockerfile, Static Container Contract and Installed-Package Smoke Test Summary

**Digest-pinned multi-stage non-root Dockerfile (uid 10001, urllib HEALTHCHECK, CMD with `--no-proxy-headers`) whose properties are machine-checked by a 12-test static contract, plus a stdlib smoke script proving a non-editable `--no-dev` install serves /health, /ready and the labelled demo /analyze with legacy, dev and train modules absent. The real `docker build` is NOT verified here.**

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | 20fc33b | build(docker): multi-stage digest-pinned non-root image with /health HEALTHCHECK; static container contract test |
| 2 | 7edaf80 | test(docker): installed-package smoke script - non-editable no-dev install serves health, ready and demo analyze |

## What was built

- **Dockerfile and .dockerignore (Task 1).** Written exactly as the research reference with its one deliberate deviation, `--no-proxy-headers` on the CMD (D-10). Builder stage: uv 0.13.1 copied from ghcr.io by tag and digest, dependency layer with `uv sync --frozen --no-install-project --no-dev --no-editable`, then `COPY pyproject.toml uv.lock ./`, `COPY src ./src`, `uv sync --locked --no-dev --no-editable`. Final stage: same python digest, `groupadd/useradd` uid/gid 10001, only `/app/.venv` copied, `USER app`, no ENV/ARG secret, DEMO_MODE not set. `.dockerignore` carries the 21 listed entries plus a comment.
- **tests/test_container_files.py (12 tests).** Parses logical Dockerfile lines. Covers: both FROM lines and the uv COPY pinned `@sha256:` + 64 lowercase hex, uv tag 0.13.1; two stages with identical base reference; two `uv sync` runs each with `--no-dev --no-editable`, one `--frozen` and one `--locked`; no `train`/`--all-groups`/`--group`/`--extra` in installs; COPY sources exactly `pyproject.toml`, `uv.lock`, `src`, `builder:/app/.venv` and no ADD; exactly one non-root USER in the final stage with `useradd --uid 10001`; HEALTHCHECK targets /health via python urllib (no curl/wget, not /ready); CMD equals the exact exec-form list, last element `--no-proxy-headers`; no ENV/ARG mentions KEY, SECRET, TOKEN, PASSWORD, GNEWS or DEMO_MODE; no tabs, CR or 32-hex string; `.dockerignore` required entries and an env-file pattern; `pyproject.toml` has no `readme` key.
- **scripts/smoke_app.py (Task 2).** Free port on 127.0.0.1; starts `python -m uvicorn truthtrail.main:app ... --no-proxy-headers` from a fresh temp directory with an environment of only PATH, PYTHONDONTWRITEBYTECODE=1, DEMO_MODE=true (and SYSTEMROOT when present); polls /health; then four checks; a second `python -I -c` child asserts `find_spec` is None for spread_simulator, users, risk_analyzer, pytest, ruff, sklearn, that `truthtrail.__file__` is under site-packages and that `data/demo_analyze.json` is package data. The server is always terminated (then killed after 10 s) in `finally`. Failures print the check name and a short message, never a body.

## Smoke result (fresh `UV_PROJECT_ENVIRONMENT=... uv sync --locked --no-dev --no-editable`, uv 0.11.32 building truthtrail 0.1.0 from file:///home/user/TruthTrail)

```
ok: health
ok: ready
ok: analyze demo (X-Cache miss then hit)
ok: installed non-editable, package data present, legacy/dev/train not importable
```

Negative control (not committed): running the same script against the editable dev `.venv` served the first three checks and then failed with `importable but must not be: pytest, ruff`, so the install check does discriminate.

## Base-image digest re-verification

Re-checked on 2026-10-17 against the Docker Hub and ghcr.io registry APIs (manifest-list `Docker-Content-Digest`): `python:3.13-slim` resolves to `sha256:70729b46...5678c2f` and `ghcr.io/astral-sh/uv:0.13.1` to `sha256:4a1f3666...ada336`. Both equal the research values committed in the Dockerfile.

## Mutation check (not committed)

With `USER app` replaced by `USER root` and `--no-proxy-headers` removed from the CMD, `test_runs_as_exactly_one_non_root_user_with_uid_10001` and `test_cmd_is_the_exact_exec_form_with_the_proxy_header_flag` failed (2 failed, 10 passed); the Dockerfile was restored byte-identically (`cmp`).

## Verification

- `pytest -q`: 497 passed, 10 xfailed, no XPASS (485 passed at the start, +12). The 10 strict xfails are unchanged.
- `ruff check`, `ruff format --check` (57 files), `mypy` (22 source files, scripts not type-checked) and `scripts/copy_guard.py` clean. `tests/test_no_hardcoded_credentials.py`: 13 passed before each commit; the added-lines 32-hex scan found nothing (the 64-hex digests do not match the word-boundary pattern).
- Not verified here (no Docker daemon, no CI run): `docker build`, the running container's `/health`, `id -u` of 10001, the HEALTHCHECK itself, `RUN --mount` cache/bind behaviour under BuildKit. Nothing in this plan claims a docker build or GitHub Actions run passed.

## Non-gating human follow-up (D-26, research assumption A1)

On a machine with a Docker daemon: `docker build -t truthtrail:ci .`, `docker run --rm -d -p 8000:8000 -e DEMO_MODE=true truthtrail:ci`, `curl -fsS http://127.0.0.1:8000/health` (expect 200 `{"status":"ok"}`) and `docker exec {container} id -u` (expect 10001). Or read the CI `docker` job added by plan 02-12 on the pushed commit.

## Deviations from Plan

- **No `# noqa: S310` comments.** The plan asked for them on the urlopen calls. The script uses `opener.open(...)` on a proxy-free opener (so ambient proxy variables cannot intercept loopback), which ruff's S310 does not flag; RUF100 rejected the unused directives, so they were omitted. The `# noqa: S603` on the two subprocess calls stays.
- **ENG-05 not marked complete.** The plan frontmatter lists ENG-05, but the requirement says the Dockerfile "builds and runs the service", which has not been demonstrated; plan 02-12 also lists ENG-05. REQUIREMENTS.md keeps ENG-05 Pending.
- Additions beyond the plan text, kept inside the scope of the smoke script: a proxy-free opener, an absolute-path check for `--python` (`FAIL: startup` message instead of a traceback on a missing interpreter) and a test that the Dockerfile contains no tabs, CR or 32-hex string.
- Test count (12) exceeds the plan's floor of 9.

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model. T-02-24 (non-root user, asserted statically; `id -u` check is plan 02-12), T-02-25 (explicit COPY list, .dockerignore, no ENV/ARG secret, legacy not importable in the smoke test), T-02-26 (tag plus digest pins asserted, digests re-verified) are implemented; T-02-27 accepted; T-02-SC: no packages added.

## Self-Check: PASSED

- Files Dockerfile, .dockerignore, tests/test_container_files.py, scripts/smoke_app.py: FOUND
- Commits 20fc33b and 7edaf80 are ancestors of HEAD: FOUND
