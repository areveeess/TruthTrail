# Phase 2: Engineering Baseline - Research

**Researched:** 2026-10-17
**Domain:** Packaging (uv, src layout), refactor of a small FastAPI service into `src/truthtrail`, test/lint/type/CI/container tooling, and the operational guards ENG-06 (CORS, rate limit, TTL cache, bounded retries, readiness)
**Confidence:** HIGH for everything executed in a scratch clone of the repo (Python 3.13.16, uv 0.13.1, the exact pinned stack); MEDIUM for the Docker build and the GitHub Actions workflow YAML (no daemon and no runner here, see Assumptions A1-A4)

## Project Constraints (from CLAUDE.md)

Source: `/home/user/TruthTrail/.claude/CLAUDE.md`. No project skills exist.

- **Honesty:** user-facing copy says "flag for human review", never "detects the truth"; synthetic/demo data is labelled in API and UI. New OpenAPI strings (`/health`, `/ready`, 429 text) are scanned by the copy guard.
- **Security:** secrets only via environment variables; scan `.planning/` and code for key material before every commit. Never print or reproduce the old GNews key (it still exists in history at `1fedcd2`). Never call the real GNews API from the dev container.
- **Process / git:** all work on branch `claude/sleepy-lovelace-13aums`; no per-phase branches; no pull requests unless asked; push after each phase; no history rewrite or force-push. Commits end with the two attribution trailers from the session reminder.
- **Stack:** Python + FastAPI backend, React/TypeScript later, Postgres later. Free/open sources only.
- **Conventions:** 4-space indent, double quotes, `snake_case`, annotate all new signatures, `logging.getLogger(__name__)` (no `print`), triple-double-quoted docstrings, plain dicts/lists from pipeline functions, `[]`/typed errors per Phase 1 contracts.
- **Workflow enforcement:** repo edits go through a GSD command (`/gsd-execute-phase`).
- **Owner platform:** native Windows 11 (PowerShell, Python 3.13). Any subprocess-based test must pass `SYSTEMROOT` (Phase 1 lesson: without it asyncio cannot initialise Winsock, WinError 10106).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

The owner reviewed the gray areas and then delegated the answers ("do whatever you recommend"). Every decision below is therefore the recommended option, taken by Claude, and the owner may revisit any of them before planning.

#### Legacy modules and the "unreachable" criterion
- **D-01:** `spread_simulator.py` and `users.py` move **unchanged** (byte-identical content) to a top-level `legacy/` directory that is **outside** `src/`, not packaged and not copied into the Docker image. Only `scripts/generate_demo_fixture.py` and the strict-xfail characterization tests import them (their import lines change; every assertion stays identical). Nothing under `src/truthtrail` may import `legacy` (enforced by a test that walks the package's imports). — **Reversibility:** reversible — a directory move.
- **D-02:** `risk_analyzer.py` moves to `src/truthtrail/services/keyword_baseline.py` with **byte-identical rule logic** (only the module path changes). The 8 pinned keyword-defect xfails keep failing for the same reasons. Fixing word boundaries and the hardcoded names waits for Phase 4's "baseline 0 as shipped vs fixed" comparison. — **Reversibility:** reversible.
- **D-03:** The cascade-ordering invariants (events ordered by `observed_at`; a child never earlier than its parent) are implemented as pure functions `order_events()` and `validate_cascade()` in `src/truthtrail/core/cascade.py`, property-tested with hypothesis on arbitrary generated cascades, and **applied when the demo fixture is loaded**. Phase 3's real data reuses them. The legacy simulator's child-before-parent defect stays pinned (strict xfail) in `legacy/` and is not fixed. — **Reversibility:** costly — Phase 3 data code will depend on these signatures.

#### Package layout, entrypoint and routes
- **D-04:** Layout `src/truthtrail/{api,services,schemas,core}`: `api/` (app factory, routers, problem+json handlers, middleware), `services/` (GNews client, keyword baseline), `schemas/` (the Phase 1 pydantic models, `Event` JSON schema unchanged), `core/` (settings, errors, cascade, readiness registry). Canonical entrypoint `truthtrail.main:app` (`uvicorn truthtrail.main:app`). — **Reversibility:** costly — every later phase imports from these paths.
- **D-05:** Keep a two-line root `main.py` shim (`from truthtrail.main import app`) so `uvicorn main:app`, the README and existing run instructions keep working; document it as a compatibility shim, to be removed when the dashboard phase lands.
- **D-06:** `/analyze` keeps its exact Phase 1 contract and stays at the root (flagged for retirement or reduction in Phase 3 per the ROADMAP open scoping question). A new empty versioned `APIRouter(prefix="/v1")` is mounted as the extension point for Phases 3 and 4. `/health` (liveness, always 200 when the process serves) and `/ready` live at the root, unauthenticated.
- **D-07:** `/ready` uses a registry of named dependency checks (sync callables returning ok/failed). With no checks registered it returns 200 `{"status":"ready","checks":{}}`; if any check fails it returns **503 problem+json** (D-15 shape from Phase 1) naming only the failed check names, never exception text. Phase 3 and 4 register their checks; this phase proves the 503 path with an injected failing check.
- **D-08:** A golden OpenAPI snapshot test proves the refactor did not change the `/analyze` contract: the OpenAPI document is compared to a committed snapshot, and the only permitted differences are the new `/health`, `/ready` and 429 entries. The Phase 1 characterization and contract tests must pass with only import-path edits.

#### CORS, rate limiting, caching, retries
- **D-09:** CORS origins come from env `CORS_ORIGINS` (comma-separated). **Unset means no cross-origin access** (secure by default); `.env.example` documents the local Vite origin `http://localhost:5173`. Methods GET/HEAD/OPTIONS only, no credentials. `CORSMiddleware` is the outermost middleware so **error responses (including 500 and 429) carry CORS headers** (folds Phase 1 review item IN-02).
- **D-10:** Rate limiting is **in-memory, single-instance** (the demo deploys as one free-tier container; a shared store is deferred). Use `slowapi`, keyed by client IP. Proxy headers are trusted **only** when `TRUST_PROXY_HEADERS=true` (uvicorn `--proxy-headers` / forwarded-allow-ips), default false, so the limit cannot be bypassed by a spoofed header. Defaults: `/analyze` 10 per minute per IP (it spends scarce GNews quota), `/v1/*` 60 per minute, `/health` and `/ready` exempt. Limits are env-configurable. A limited request returns **429 problem+json** (code `rate_limited`) with `Retry-After` and the provenance members. — **Reversibility:** reversible.
- **D-11:** Repeated reads use an in-process TTL cache (`cachetools.TTLCache`, lock-guarded) for `/analyze`, keyed by the trimmed, casefolded query plus the demo-mode flag; **TTL 600 s, max 256 entries** (GNews' free tier allows ~100 requests/day, so a long TTL protects quota). Only successful responses (200, including the honest empty result) are cached; **errors are never cached**. A cache hit keeps the original `meta.data_as_of`, so staleness stays visible, and sets a `X-Cache: hit|miss` header. Rate limiting applies before the cache.
- **D-12:** Outbound GNews retries use an **explicit, small retry loop in our own code** (not urllib3 `Retry`), so it is testable with the `responses` mock: at most **2 retries (3 attempts)**, exponential backoff 0.3 s then 0.6 s plus jitter, only for connect errors, timeouts and HTTP 500/502/503/504 on this idempotent GET. **No retry on 4xx, including 429** (retrying wastes quota). A total time budget of 8 s caps the whole call. When the bound is exhausted the Phase 1 mapping (D-06/D-07 there) applies unchanged. A test with a mocked slow or failing upstream proves it stops at the bound.
- **D-13 (folded review items):** Clamp a provider `Retry-After: 0` to a minimum of 1 s (IN-03); make `Problem.synthetic` `Literal[False]` (IN-05, typing part).

#### Tooling, CI and container
- **D-14:** Dependency management is **uv** on Python 3.13 (`requires-python = ">=3.13,<3.14"`, `.python-version`), with a committed `uv.lock`. Groups: serving (the project dependencies), `dev` (pytest, pytest-cov, hypothesis, responses, httpx, ruff, mypy, pip-audit) and `train` (scikit-learn and numpy, documented as unused until Phase 4 and excluded from the image and the default CI sync). The Phase 1 `requirements*.txt` files are removed once `uv.lock` exists; the README setup becomes `uv sync` (with a Windows note). — **Reversibility:** costly — CI, Docker and README all depend on it.
- **D-15:** Ruff for lint and format (line length 100; rule families E, F, I, UP, B, S, SIM, C4, PT, RUF; `tests/` may relax `S`). mypy runs `strict = true` on `src/truthtrail` and a relaxed config on tests and scripts. Coverage via pytest-cov with a `fail_under` gate set to the **measured baseline minus 2 points** and only ever ratcheted upward. Hypothesis uses a pinned CI profile (derandomized, no example database) so CI is reproducible.
- **D-16:** Normalise line endings in one dedicated first commit: add `.gitattributes` (`* text=auto eol=lf`, `*.sh` forced LF) and renormalise the CRLF files (`main.py`, `gnews_fetcher.py`, and any other), so later diffs and the moves into `src/` are clean (folds review item IN-05).
- **D-17:** CI keeps the Phase 1 copy-guard, gitleaks (floor-bounded, with its selftest) and tests jobs and adds: `lint` (ruff check and format --check), `typecheck` (mypy), `audit` (pip-audit against the exported lock), and `docker` (build the image, run it with `DEMO_MODE=true`, and curl `/health`). Third-party actions stay SHA-pinned (add `astral-sh/setup-uv` pinned the same way), `persist-credentials: false`, job timeouts. The phase is done when CI is green on the final commit.
- **D-18:** The Dockerfile is multi-stage on `python:3.13-slim` (tag plus digest), installs with `uv sync --frozen --no-dev`, runs as a non-root user, contains no secrets (`DEMO_MODE` defaults false, so the image needs `GNEWS_API_KEY` at run time), has a `HEALTHCHECK` on `/health`, and starts `uvicorn truthtrail.main:app --host 0.0.0.0 --port 8000`. `legacy/`, `tests/`, `.planning/` and `scripts/` are excluded via `.dockerignore`.

### Claude's Discretion
Exact module and file names inside each package folder, hypothesis strategy details, how the OpenAPI snapshot is stored and refreshed, the structure of the readiness registry beyond its observable behaviour, and the precise ruff rule exceptions needed to pass on the existing code.

### Deferred Ideas (OUT OF SCOPE)
- Shared rate-limit and cache store (Redis) for multi-instance deployments: only if the Phase 6 deploy needs more than one instance.
- Pre-commit hooks, structured JSON logging, a metrics endpoint, API-key auth, a load test (all OPS2-01, v2).
- Removing the root `main.py` shim: when the dashboard phase lands.
- Retiring or reducing `/analyze`: Phase 3 (ROADMAP open scoping question).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ENG-01 | Code in `src/truthtrail` (api, services, schemas, core); legacy simulator and users removed from the live path | Pure `git mv` procedure with `--follow` history (verified); `legacy/` flat-import and `pythonpath` finding; OpenAPI byte-identical after the move; import-walker + subprocess `sys.modules` test; fixture moved into the package (wheel contents verified) |
| ENG-02 | uv lockfile on Python 3.13, training and serving split | Full `pyproject.toml` draft locked and synced; `train` excluded by default (verified); uv 0.11.32 and 0.13.1 both read the lock; `uv_build` backend verified |
| ENG-03 | pytest + hypothesis covering the API and the invariants, coverage reported | Cascade module + 4 property tests prototyped and mutation-checked; `ci` profile registration; measured coverage baseline 98% (line+branch) on moved code |
| ENG-04 | CI runs ruff, mypy, pytest, pip-audit, secret scan on every push | Measured ruff (81 findings, 24 manual) and mypy strict (11 errors, 3 files); exact `pip-audit` command verified; setup-uv v9.0.0 SHA; job layout |
| ENG-05 | Dockerfile builds and runs; `/health` liveness; `/ready` 503 on failed dependency | Readiness registry prototyped (503 problem+json, no exception text); Dockerfile pattern from uv docs; digests verified via registry API; Docker daemon unavailable here (build unverified) |
| ENG-06 | CORS restricted, rate limit, TTL cache, timeouts + bounded retries | slowapi compatibility matrix incl. a fail-open defect under FastAPI 0.143; CORS vs `ServerErrorMiddleware` experiment; TTLCache fake-clock + locking; retry loop vs `responses` |
</phase_requirements>

## Summary

The refactor itself is low risk: in a scratch clone the pure `git mv` into `src/truthtrail` and `legacy/` kept history (`git log --follow` works), the generated OpenAPI document stayed byte-identical to Phase 1, the demo fixture stayed byte-identical (sha256 `f47fc6926acf3ba976ef28db7d6382f1fcf2da28fad4f493e01fbdb7023f7ec2` before and after, and `generate_demo_fixture.py --check` passes), and the whole Phase 1 suite passed (274 passed, 10 xfailed) after only import-path and patch-target edits. uv 0.13.1, `uv_build`, the dependency groups, the lock (75 packages, identical to the Phase 1 pins for the stack), the editable install, a non-editable "production" install, `pip-audit` on an exported lock, `gitleaks` and the copy guard all work in this environment.

Eight findings change or sharpen locked decisions and must be settled before planning (details in Open Questions and Common Pitfalls):
1. **D-03 vs D-06/D-08:** the committed fixture's `events` arrays are NOT in `timestamp` order (platform chains are concatenated; 2 timestamp ties in cascade 1). Applying `order_events()` at load time reorders the served body, which breaks the Phase 1 test `body == committed` and the "contract frozen" rule. Recommended: apply `validate_cascade()` as a hard gate at fixture load, keep `order_events()` as the tested, reusable function for Phase 3, and leave the demo body order untouched (OR accept the reorder and edit that test). Also `Event` has `timestamp`, not `observed_at`.
2. **D-13 vs D-08:** `Problem.synthetic: Literal[False]` adds `"const": false` to the `Problem` schema in OpenAPI (verified), which is outside D-08's stated allowance (`/health`, `/ready`, 429). The snapshot test needs that one declared exception.
3. **D-10:** `slowapi` 0.1.10 works on FastAPI 0.143.0 / Starlette 1.8.0 only through its `@limiter.limit` decorator. `SlowAPIMiddleware` and `default_limits` **silently fail open** for every route added through `include_router` (FastAPI >= 0.137 returns `_IncludedRouter` objects without `.endpoint`; upstream issue laurents/slowapi#281, open since 2026-07-17, no maintainer reply). Since `/v1` is an included router, use decorators plus a small `LimitedRouter` so future `/v1` routes cannot be forgotten.
4. **D-01/D-02 vs D-16:** the three legacy files are CRLF. Renormalising (D-16) changes their bytes; "byte-identical" must be defined as identical after CRLF to LF normalisation (hashes recorded below), and the Phase 1 gate `git diff --quiet 9b5b085 -- ...` needs `--ignore-cr-at-eol`. Also `legacy/spread_simulator.py` does `from users import USERS`, so unchanged bytes force `legacy/` itself onto `sys.path`.
5. **D-09 / Phase 1 fail-fast:** reading `Settings` while building the app at import time (needed for CORS) turns the Phase 1 "uvicorn exits 3 with Application startup failed" behaviour into exit 1 "Error loading ASGI app" (verified), failing `test_uvicorn_exits_on_missing_key`. Construction-time values (CORS origins, trust-proxy flag) must come from a lenient, no-required-fields boot settings object.
6. **App-level state:** a module-level limiter and cache broke 57 of the existing tests in the prototype (429s and stale cache hits across tests). The limiter, cache and readiness registry must live on a per-app object built by `create_app()`.
7. **D-18 / smoke job:** the `DEMO_MODE=true` fixture must ship inside the package (non-editable image has no repo-relative `fixtures/`), and `readme = "README.md"` in `pyproject.toml` breaks the image build once `*.md` is dockerignored (reproduced).
8. **Tests are not literally unchanged:** 13 existing tests fail after the move until string patch targets (`"main.load_demo_fixture"`, `"main.FIXTURE_PATH"`, `"main.analyze_risk"`) and the logger-name assertion (`"gnews_fetcher"`) are retargeted. D-08 allows "import-path edits"; this is that class of edit, listed exactly below.

**Primary recommendation:** execute as ordered plans: (0) line-ending commit; (1) pure `git mv` commit; (2) import/patch-target fixes + `pyproject`/uv lock + pytest config + `create_app()`; (3) lint/format/type clean-up; (4) cascade module + hypothesis; (5) readiness, CORS + catch-all, rate limit, cache, retry; (6) Dockerfile + CI. Keep the OpenAPI "Phase 1 subset" test as the guard through every plan.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Dependency resolution, lock, groups | Build tooling (uv, `pyproject.toml`, `uv.lock`) | CI, Docker | One lock feeds dev, CI and the image |
| App construction, per-app state (limiter, cache, readiness) | API / Backend (`api/app.py` `create_app()`) | `core/` | State must be per app instance so tests and Phase 3/4 can build isolated apps |
| CORS and error-response CORS headers | API / Backend middleware | — | Browser frontend (Phase 5) depends on headers on 429/500 |
| Rate limiting (per IP) | API / Backend (decorators + `limits` engine) | Reverse proxy (client-IP trust) | Application enforces; the proxy must supply a trustworthy client IP |
| TTL cache for `/analyze` | API / Backend (in-process) | — | Single instance by decision; protects the GNews quota |
| Outbound HTTP timeouts + bounded retry | Service adapter (`services/gnews.py`) | — | Provider seam owns the retry/budget policy |
| Readiness registry and `/ready` | API / Backend | `core/` (registry) | Phase 3 (DB) and Phase 4 (model) register checks |
| Cascade ordering invariants | `core/cascade.py` (pure functions) | Fixture loader (API) | Shared by demo fixture now and real data in Phase 3 |
| Container image, HEALTHCHECK | Container build (Dockerfile) | CI `docker` job | Stateless image; secrets only at run time |
| Line endings, formatting, lint, types | Repo tooling (`.gitattributes`, ruff, mypy) | CI | Mechanical, enforced on every push |

## Standard Stack

### Core (serving group = `[project].dependencies`)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | 0.143.3 (Phase 1: 0.143.0) | HTTP API | Existing; suite passes on both [VERIFIED: pip index 2026-10-17; full suite run on 0.143.0 and 0.143.3] |
| starlette | 1.8.0 (transitive) | ASGI framework | Pulled by FastAPI [VERIFIED: uv.lock] |
| pydantic | 2.14.1 (Phase 1: 2.14.0) | Models, settings validation | Existing [VERIFIED: pip index; suite passes on both] |
| pydantic-settings | 2.16.0 (Phase 1: 2.15.0) | Env-only settings | Existing [VERIFIED: pip index; suite passes on both] |
| uvicorn | 0.54.0 | ASGI server | Existing [VERIFIED: pip index] |
| requests | 2.34.2 | GNews adapter | Existing; ships `py.typed` (no `types-requests` needed) [VERIFIED: site-packages/requests/py.typed; mypy strict run without stubs] |
| slowapi | 0.1.10 (released 2026-06-13) | Rate limiting (D-10) | Locked by D-10; use decorators only (see Pitfall 2) [VERIFIED: PyPI JSON; local FastAPI 0.143 experiments] |
| limits | 5.8.0 (transitive, 2026-02-05) | slowapi's engine; fallback if slowapi is dropped | [VERIFIED: PyPI JSON] |
| cachetools | 7.2.3 (uploaded 2026-10-17) | `TTLCache` (D-11) | Ships `py.typed`; `timer=` argument for fake clocks [VERIFIED: PyPI JSON; docs https://cachetools.readthedocs.io/en/latest/] |

### Dev group (`[dependency-groups].dev`, synced by default)
| Library | Version | Purpose |
|---------|---------|---------|
| pytest | 9.1.1 | Runner |
| pytest-cov / coverage | 7.1.0 / 7.16.2 | Coverage gate |
| hypothesis | 6.170.1 (2026-10-16) | Property tests |
| responses | 0.26.3 | Mock `requests` (sequences, callbacks, exceptions) |
| httpx | 0.28.1 | Starlette TestClient backend (warning filtered in pytest config, as in Phase 1) |
| ruff | 0.17.1 (2026-10-15) | Lint + format |
| mypy | 2.4.0 | Type check (use the pydantic plugin) |
| pip-audit | 2.10.1 | Dependency audit |

Do **not** add `types-requests` or `types-cachetools`: every runtime dependency above ships `py.typed` (checked for requests, cachetools, slowapi, limits, hypothesis, responses, pydantic-settings, uvicorn, fastapi, starlette), and mypy strict ran clean of import errors with both stub packages uninstalled [VERIFIED].

### Train group (`[dependency-groups].train`, NOT synced by default)
scikit-learn 1.9.1, numpy 2.5.4 [VERIFIED: pip index]. Present in `uv.lock`, absent from `uv sync` and from the image (verified: `uv sync --frozen --no-dev --no-editable` into a throwaway env contains no pytest, ruff, mypy, scikit-learn or numpy).

### Tools and pins
| Tool | Version / pin | Source |
|------|---------------|--------|
| uv | 0.13.1 (released 2026-10-14) | `pip index versions uv`, PyPI JSON, `git ls-remote` tag list [VERIFIED] |
| uv_build | `>=0.13.1,<0.14` (0.13.1 is latest) | PyPI JSON; config per https://docs.astral.sh/uv/concepts/build-backend/ [CITED] |
| astral-sh/setup-uv | v9.0.0 = `c771a70e6277c0a99b617c7a806ffedaca235ff9` | `git ls-remote --tags` (lightweight tag, so the commit SHA); release notes via GitHub release page [VERIFIED] |
| actions/checkout | v7.0.1 = `3d3c42e5aac5ba805825da76410c181273ba90b1` (unchanged) | `git ls-remote` [VERIFIED] |
| actions/setup-python | v7.0.0 = `5fda3b95a4ea91299a34e894583c3862153e4b97` (unchanged; optional once setup-uv installs Python) | `git ls-remote` [VERIFIED] |
| python:3.13-slim | `sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f` (multi-arch index; `3.13-slim`, `3.13-slim-trixie` and `3.13.16-slim` resolve to the same digest) | Docker Hub registry API through the proxy, 2026-10-17 [VERIFIED] |
| ghcr.io/astral-sh/uv:0.13.1 | `sha256:4a1f3666816dafadd20ceb71eac9a7d56d7ef30279f7d64048519ab901ada336` (same digest as `:0.13`) | ghcr.io registry API [VERIFIED] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `uv_build` | `hatchling` 1.32.4 | Works but needs `[tool.hatch.build.targets.wheel] packages = ["src/truthtrail"]`; one more third-party backend. `uv_build` needs zero config for `src/truthtrail` and ships package data (verified) |
| `uv_build` | `[tool.uv] package = false` | No build, but `truthtrail` is then importable only via `PYTHONPATH=src` (pytest `pythonpath`, Docker `ENV`, `uvicorn --app-dir`); `uvicorn truthtrail.main:app` stops working out of the box |
| slowapi decorators | `limits` behind a FastAPI dependency | ~25 lines, no signature pollution (`request`/`response` parameters), no module-name bucket keys, fully typed; verified working. Take this if the owner wants to drop slowapi; D-10 names slowapi, so it stays the recommendation |
| `cachetools.TTLCache` + explicit lock | `cachetools.cached(cache, lock=..., condition=...)` | The decorator cannot tell hit from miss (needed for `X-Cache`); explicit lock keeps it testable. `condition=` adds single-flight, optional |

**Installation (developer, Linux/macOS):**
```bash
uv sync                      # serving + dev (default groups); creates .venv
uv sync --group train        # opt-in, Phase 4 only
uv run pytest --hypothesis-profile=ci
```
**Windows (PowerShell), per https://docs.astral.sh/uv/getting-started/installation/ [CITED]:**
```powershell
winget install --id=astral-sh.uv -e      # or: py -3.13 -m pip install uv
uv sync
uv run pytest
$env:DEMO_MODE = "true"; uv run uvicorn truthtrail.main:app
```
uv adopts an existing pip-created `.venv` (verified: it removed an extraneous package and installed the project into it), but deleting the old `.venv` first is cleaner.

**This container:** `uv 0.11.32` is preinstalled at `/root/.local/bin/uv` and reads the generated lock (`uv lock --check` and `uv sync --frozen` succeed). The current release is obtained with `python3 -m venv <dir> && <dir>/bin/pip install uv` (installed uv 0.13.1; verified). `UV_NATIVE_TLS` is set in the environment and only produces a deprecation warning; `UV_SYSTEM_CERTS=true` silences it.

**Version verification:** `pip index versions <pkg>` and `https://pypi.org/pypi/<pkg>/json` on 2026-10-17 for every row above (fastapi 0.143.3, pydantic 2.14.1, starlette 1.8.0, pydantic-settings 2.16.0, uvicorn 0.54.0, requests 2.34.2, responses 0.26.3, httpx 0.28.1, pytest 9.1.1, slowapi 0.1.10, limits 5.8.0, cachetools 7.2.3, hypothesis 6.170.1, pytest-cov 7.1.0, coverage 7.16.2, mypy 2.4.0, ruff 0.17.1, pip-audit 2.10.1, scikit-learn 1.9.1, numpy 2.5.4, uv 0.13.1, uv-build 0.13.1, hatchling 1.32.4). Several tools shipped within the last 4 days (uv, ruff, hypothesis, cachetools): the lock pins them, `uv lock --upgrade` is deliberate.

**Recommended `pyproject.toml`** (locked and synced here; 75 packages resolved in about 1 s):
```toml
[build-system]
requires = ["uv_build>=0.13.1,<0.14"]
build-backend = "uv_build"

[project]
name = "truthtrail"
version = "0.1.0"
description = "Misinformation early-warning service: flag for human review."
# NO `readme = ...`: it makes the image build fail once *.md is dockerignored (Pitfall 7).
requires-python = ">=3.13,<3.14"
dependencies = [
    "fastapi>=0.143,<0.144",
    "pydantic>=2.14,<3",
    "pydantic-settings>=2.15,<3",
    "uvicorn>=0.54,<1",
    "requests>=2.34,<3",
    "slowapi>=0.1.10,<0.2",
    "cachetools>=7.2,<8",
]

[dependency-groups]
dev = [
    "pytest>=9.1,<10",
    "pytest-cov>=7.1,<8",
    "hypothesis>=6.170,<7",
    "responses>=0.26,<1",
    "httpx>=0.28,<0.29",
    "ruff>=0.17,<0.18",
    "mypy>=2.4,<3",
    "pip-audit>=2.10,<3",
]
train = [
    "scikit-learn>=1.9,<2",   # unused until Phase 4 (ML-03)
    "numpy>=2.5,<3",
]

[tool.uv]
default-groups = ["dev"]   # explicit; `train` stays opt-in (this is also uv's default)
```
`.python-version` contains `3.13`. The lock records `requires-python = "==3.13.*"` and `revision = 5`. With these ranges the lock resolved fastapi 0.143.3 / pydantic 2.14.1 / pydantic-settings 2.16.0 and the full suite passed (278 passed incl. the cascade prototype); with exact Phase 1 pins (`==0.143.0` etc.) the lock matched `requirements*.txt` package for package. Either policy works; ranges + lock is the usual uv convention. Do not set `[tool.uv] required-version` above `0.11` (a hard `>=0.13.1` made the container's preinstalled uv refuse to run: "Required uv version ... does not match the running version 0.11.32").

## Package Legitimacy Audit

`gsd-tools query package-legitimacy check --ecosystem pypi` returned **SUS for every package**, exactly as in Phase 1, for artefact reasons (`unknown-downloads`: PyPI exposes no counts; `too-new`: latest release within 30 days; `no-repository`: project URL is an issues/changelog link). Independent evidence from the PyPI JSON API (first upload, repository, release count):

| Package | Registry | First upload | Releases | Source Repo | Seam Verdict | Disposition |
|---------|----------|--------------|----------|-------------|--------------|-------------|
| slowapi | PyPI | 2020-02-21 | 11 | github.com/laurents/slowapi | SUS (unknown-downloads) | Approved with caveats: small maintainer base, one release in 2024-2026, open fail-open bug #281. Decorator-only use; `limits` fallback documented |
| limits | PyPI | 2015-01-08 | 98 | github.com/alisaifee/limits | SUS (unknown-downloads) | Approved (transitive) |
| cachetools | PyPI | 2014-03-22 | 80 | github.com/tkem/cachetools | SUS (too-new, unknown-downloads) | Approved; 7.2.3 uploaded the day of research, lock-pinned |
| hypothesis | PyPI | 2013-03-10 | 1580 | github.com/HypothesisWorks/hypothesis | SUS | Approved |
| pytest-cov | PyPI | 2010-04-25 | 54 | github.com/pytest-dev/pytest-cov | SUS | Approved |
| coverage | PyPI | 2009-05-16 | 197 | github.com/coveragepy/coveragepy | not run (transitive) | Approved |
| mypy | PyPI | 2009-09-09 | 142 | github.com/python/mypy | SUS (too-new) | Approved |
| ruff | PyPI | 2022-08-27 | 428 | github.com/astral-sh/ruff | SUS (too-new) | Approved |
| pip-audit | PyPI | 2021-09-16 | 63 | github.com/pypa/pip-audit | SUS | Approved |
| uv / uv-build | PyPI | 2024-02-15 / 2025-02-12 | 325 / 167 | github.com/astral-sh/uv | SUS (too-new) | Approved |
| scikit-learn, numpy | PyPI | long established | — | github.com/scikit-learn, github.com/numpy | SUS (artefacts) | Approved (train group only, never installed by default) |

**Packages removed due to SLOP verdict:** none. **Packages flagged SUS:** all, for the artefacts above. The Phase 1 owner decision D-18 waived the `checkpoint:human-verify` for the same artefact; the planner should either repeat that waiver explicitly for this set or insert one checkpoint reviewing the `pyproject.toml` dependency diff (the only genuinely low-adoption package is slowapi). No `postinstall` scripts apply (Python packages; pure-wheel installs).

## Architecture Patterns

### System Architecture Diagram

```
 browser (Vite dev origin / dashboard)            curl / docker HEALTHCHECK
        |                                                 |
        v                                                 v
 uvicorn truthtrail.main:app  --(optional TRUST_PROXY_HEADERS)--> ProxyHeadersMiddleware (trusted hosts only)
        |
        v
 ServerErrorMiddleware  (Starlette-internal; outermost; renders only what escapes everything below)
        |
        v
 CORSMiddleware  (allow_origins from boot settings; GET/HEAD/OPTIONS; no credentials)   <-- outermost USER middleware
        |
        v
 CatchAllMiddleware (pure ASGI, ours)  -- unhandled Exception --> problem+json 500, flows OUT through CORS (headers added)
        |
        v
 ExceptionMiddleware + routing
        |-- GET /health  (exempt) --------------------------------> {"status":"ok"}
        |-- GET /ready   (exempt) -- ReadinessRegistry.run() -----> 200 {"status":"ready","checks":{...}} | 503 problem+json (failed names in detail)
        |-- GET /analyze -- @limiter.limit(10/min, per IP)  [429 problem+json + Retry-After -> back out through CORS]
        |        |  param validation (422 problem+json, not counted)         \
        |        v                                                            > rate limit runs BEFORE the cache (decorator wraps the handler body)
        |     TTLCache lookup (lock) key=(casefold(query), demo_mode)
        |        | hit -> X-Cache: hit (original meta.data_as_of)
        |        | miss -> X-Cache: miss
        |        v
        |     demo_mode ? load_demo_fixture() [validate_cascade gate]  :  services.gnews.fetch_news()
        |                                                   retry loop: <=3 attempts, backoff 0.3/0.6 + jitter, 8 s budget,
        |                                                   retry only connect/timeout/500,502,503,504; never 4xx/429
        |                                                   -> UpstreamError -> problem+json (Phase 1 mapping unchanged)
        |-- /v1  (LimitedRouter, 60/min per route per IP, empty now) <- Phase 3 and Phase 4 add routes here
        v
 per-app state on app.state: limiter, analyze_cache (+lock), readiness registry   (created by create_app(), never module-level)
```

### Recommended Project Structure
```
.
├── main.py                       # two-line compatibility shim: from truthtrail.main import app (D-05)
├── pyproject.toml  uv.lock  .python-version  .gitattributes  .dockerignore  Dockerfile
├── legacy/                       # NOT packaged, NOT in the image (D-01); on pytest pythonpath
│   ├── spread_simulator.py       #   from users import USERS  (flat import: legacy/ itself must be on sys.path)
│   └── users.py
├── src/truthtrail/
│   ├── __init__.py  main.py      # main.py: app = create_app()   (canonical uvicorn target)
│   ├── api/    app.py (create_app, lifespan, middleware wiring) analyze.py (route, fixture loader) health.py
│   │           problems.py (handlers, PROBLEM_RESPONSES, 429 declaration) limits.py (LimitedRouter, 429 handler) catchall.py
│   ├── services/  gnews.py (retry loop) keyword_baseline.py   # byte-identical to risk_analyzer.py (LF-normalised)
│   ├── schemas/   models.py       # Event + envelope + Problem (Event schema unchanged)
│   ├── core/      config.py boot.py errors.py (UpstreamError) cascade.py readiness.py
│   └── data/      demo_analyze.json   # package data; moved with git mv, bytes unchanged
├── scripts/  copy_guard.py generate_demo_fixture.py gitleaks_*.sh install_gitleaks.sh
└── tests/    (conftest.py + existing files, + golden/openapi_phase1.json, test_cascade_properties.py, ...)
```
`UpstreamError` and `problem_body` should live in `core/errors.py`, not `api/problems.py`: in the scratch move, `services/gnews.py` had to import from `truthtrail.api.problems` (a service importing from the API layer). D-04 lists "errors" under `core/`.

### Pattern 1: Moves that keep history (verified)
1. Commit 1 (`chore: normalise line endings`): `.gitattributes` + `git add --renormalize .`. Verified diff is whitespace-only: `git diff --cached --ignore-cr-at-eol --stat` listed only `.gitattributes`. Exactly 6 files change (`main.py`, `models.py`, `gnews_fetcher.py`, `risk_analyzer.py`, `spread_simulator.py`, `users.py`; 544 insertions/542 deletions).
2. Commit 2 (`refactor: pure moves`): only `git mv` (no edits, no new `main.py` yet). Git reported all 8 renames at 100% and `git log --follow` walked past the move for `services/gnews.py` and `legacy/users.py`. Create the new root `main.py` shim in the NEXT commit; creating it in the same commit as `git mv main.py src/...` makes Git see a modified `main.py` plus a new file and `--follow` loses the history.
3. Commit 3: import rewrites, `create_app()`, config. Add the normalise commit SHA to `.git-blame-ignore-revs` (GitHub honours it) so blame stays useful.

`.gitattributes`:
```
* text=auto eol=lf
*.sh text eol=lf
```
**Owner pulling the commit** (simulated with a fast-forward in a clone): the 6 rewritten files arrive as LF in the working tree; other files may show `M` only if the Windows checkout had CRLF; `git add --renormalize .` then leaves nothing to commit. If the working tree must be refreshed: `git rm --cached -r -q . && git reset --hard -q` (only with a clean tree).

**Legacy identity (D-01/D-02):** after normalisation the legacy files are identical to the Phase 1 originals modulo CRLF. Record and test these hashes (computed from `git show 765b844:<file> | tr -d '\r' | sha256sum`; the moved files in the scratch clone matched):
```
risk_analyzer.py    (-> services/keyword_baseline.py)  7398c2cfd920b56d971324935956a1342159eef0b808da53b95ed91fab46f23a
spread_simulator.py (-> legacy/)                       e8e61cde19601bfe99311df21fc79ec95ce49ba0f62fdace663c4033a53e362c
users.py            (-> legacy/)                       e222249346536212bc1e3d2c7beab00202f647023f9ecbc28bb9797d7a0abfae
```
A `tests/test_legacy_frozen.py` that hashes `read_bytes().replace(b"\r\n", b"\n")` pins them. The Phase 1 gate `git diff --quiet 9b5b085 -- spread_simulator.py users.py risk_analyzer.py` returns exit 1 after the renormalise commit (verified) and 0 with `--ignore-cr-at-eol` (verified).

### Pattern 2: Import/patch-target edits needed in the existing tests (verified list)
After the move, 261 of 274 passed; the 13 failures were exactly: `tests/test_provenance_demo.py` lines 160, 178-179 (`"main.load_demo_fixture"`, `importlib.import_module("main")`, `"main.FIXTURE_PATH"`), `tests/test_request_validation.py` line 142 (`"main.analyze_risk"`), `tests/test_upstream_errors.py` line 316 (`r.name == "gnews_fetcher"`, the logger name becomes the module `__name__`, e.g. `truthtrail.services.gnews`). Other edits are plain imports (`from config import` etc.), `tests/conftest.py` (`import main` to `create_app()`), fixture path constants in `tests/test_demo_fixture.py` and `tests/test_provenance_demo.py`, the generator script, and `pytest.ini` to `pyproject.toml`. After these edits the suite was 274 passed, 10 xfailed, 0 XPASS. Centralise the patch targets (one `APP_MODULE` constant in `tests/conftest.py`) so Phases 3-4 do not repeat the edit.

`tests/test_char_simulator.py` keeps `from spread_simulator import ...` and `from users import USERS` unchanged because `legacy/` is on the pytest `pythonpath`.

### Pattern 3: pytest configuration, src layout and the shim
```toml
[tool.pytest.ini_options]
pythonpath = ["legacy", "."]          # "legacy": flat `from users import ...`; ".": the root main.py shim test
testpaths = ["tests"]
xfail_strict = true
addopts = "-ra"
filterwarnings = [
    "error",
    "ignore:Using .httpx. with .starlette.testclient. is deprecated",
]
```
- `truthtrail` itself needs no `pythonpath` entry: `uv sync` installs it editable (a `.pth` to `src`); the editable install was exercised by the whole suite.
- Delete `pytest.ini` in the same commit. With both present pytest prints `WARNING: ignoring pytest config in pyproject.toml!` and silently uses `pytest.ini` [VERIFIED: local run].
- Shim test: `import main; import truthtrail.main; assert main.app is truthtrail.main.app` (the shim is outside coverage `source`).
- `test_uvicorn_exits_on_missing_key` (`uvicorn main:app`, cwd `tmp_path`, `PYTHONPATH=repo_root`) passed unchanged against the shim.

### Pattern 4: Per-app state and the settings split
Build everything stateful in `create_app()` and store it on `app.state`; `tests/conftest.py::client_factory` calls `create_app()` per test. Evidence: with a module-level `Limiter` (10/min) and `TTLCache`, 57 of the existing 274 tests failed (429s and cross-test cache hits). Decorators must be applied inside the factory (or in a `build_*_router(limiter)` function) so each app has its own limiter.

Construction-time inputs (CORS origins, trust-proxy flag) must NOT come from the strict `Settings` object: reading it at import time makes a missing `GNEWS_API_KEY` fail during import, so uvicorn exits **1** ("Error loading ASGI app") instead of **3** ("Application startup failed"); both exit codes were reproduced with throwaway modules, and the existing test asserts 3 plus the message. Use a boot object with no required fields:
```python
# core/boot.py
class BootSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True, hide_input_in_errors=True)
    cors_origins: Annotated[list[str], NoDecode] = []          # NoDecode: plain list[str] REQUIRES JSON in env
    trust_proxy_headers: bool = False
    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split(cls, v: object) -> object:
        return [p.strip() for p in v.split(",") if p.strip()] if isinstance(v, str) else v
```
Verified: unset and empty give `[]`; `a, b` splits; a plain `list[str]` field raises `SettingsError` for a comma value. Validate each origin (scheme + host, no trailing slash, not `*`): `CORSMiddleware` compares exact strings, so `http://localhost:5173/` silently never matches. Rate-limit strings use slowapi callable limits read at request time (`@limiter.limit(lambda: get_settings().rate_limit_analyze)`; verified, no-arg callables work), so `create_app()` stays import-safe. Remember: `tests/conftest.py::ENV_NAMES` must list every new variable, and `.env.example` entries must stay `NAME=` (see Pitfall 12).

### Pattern 5: CORS ordering and CORS-aware 500s
Verified experiment (Starlette 1.8.0): a registered `Exception` handler renders inside `ServerErrorMiddleware`, outside every user middleware, so its 500 has **no** CORS headers; a 429 raised inside the route is handled by `ExceptionMiddleware` (inside CORS) and does carry `Access-Control-Allow-Origin`. The reliable fix is a small pure-ASGI catch-all placed just inside `CORSMiddleware` (add it BEFORE `CORSMiddleware`, since the last `add_middleware` is outermost among user middleware):
```python
class CatchAllMiddleware:
    def __init__(self, app: ASGIApp) -> None: self.app = app
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send); return
        started = False
        async def send_wrapper(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            logger.error("unexpected error: %s", type(exc).__name__)   # class name only, never str(exc)
            if started: raise
            await problem_response(500, problem_body(500, "Unexpected error.", "internal_error", source_status="error"))(scope, receive, send)

app.add_middleware(CatchAllMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=boot.cors_origins, allow_methods=["GET", "HEAD", "OPTIONS"], allow_credentials=False)
```
Results: 500 with `Origin` gives `ACAO: http://localhost:5173` and `Vary: Origin`; the `TestClient` no longer re-raises (default `raise_server_exceptions=True` returns the 500). Empty `allow_origins` gives no `ACAO` on any response; a disallowed preflight gets 400 with no `ACAO`; a preflight for `POST` gets 400 "Disallowed CORS method" as **plain text, not problem+json** (a CORSMiddleware limitation; document it). Keep the existing specific handlers (`ConfigurationError`, `UpstreamError`, ...): they run in `ExceptionMiddleware`, inside CORS. The fallback if a catch-all is unwanted: copy `Access-Control-Allow-Origin`/`Vary` manually in the `Exception` handler by checking `request.headers["origin"]` against the same list (not tested).

### Pattern 6: Rate limiting with slowapi (decorators only)
Verified on FastAPI 0.143.0 / Starlette 1.8.0 / `warnings.simplefilter("error")` and under pytest `filterwarnings=error` (30 apps built, no thread leaks, no warnings): sync and async handlers, `response_model` routes, 429 through a custom handler, `Origin` echo on the 429, exempt routes, `limiter.reset()`, per-IP keys, two apps with isolated storage, `mypy --strict` clean.
```python
limiter = Limiter(key_func=client_ip, storage_uri="memory://")      # headers_enabled stays False (see below)
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)          # registered ahead of the generic HTTPException handler: RateLimitExceeded IS an HTTPException subclass
async def _limited(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    item, args = request.state.view_rate_limit
    reset_at, _ = limiter.limiter.get_window_stats(item, *args)
    retry = max(1, math.ceil(reset_at - time.time()))
    return problem_response(429, problem_body(429, "Rate limit exceeded.", "rate_limited", source_status="rate_limited"),
                            {"Retry-After": str(retry)})

@router.get("/analyze", ...)
@limiter.limit(lambda: current_limits().analyze)    # "10/minute" default
def analyze(request: Request, response: Response, query: ...) -> AnalyzeResponse: ...
```
Facts and traps (each verified unless noted):
- The decorated function must have a parameter literally named `request` (slowapi raises at decoration time otherwise); add `response: Response` only if you set headers (`X-Cache`). Neither changes OpenAPI (the document stayed byte-identical to Phase 1).
- **`headers_enabled=True` puts `Retry-After` (and `X-RateLimit-*`) on EVERY response, including 200s** (observed `retry-after: 60` on a 200). Keep it off and compute `Retry-After` yourself in the 429 handler as above (observed `Retry-After: 60` on the first window).
- **`SlowAPIMiddleware` / `default_limits` do not apply to routes added through `include_router`** under FastAPI 0.143: `_find_route_handler` returns `None` for the `_IncludedRouter`, so the route is treated as exempt, silently (4 requests against a `3/minute` default all returned 200). Upstream: https://github.com/laurents/slowapi/issues/281 (open, opened 2026-07-17, confirmed on slowapi 0.1.10, no maintainer response). A decorator on a route inside an included router does work (`[200, 200, 429]`). Therefore never use the middleware or `default_limits`.
- Fail-closed `/v1` limits for Phases 3 and 4 (verified): 
```python
class LimitedRouter(APIRouter):
    def __init__(self, limiter: Limiter, limit: Callable[[], str], **kw: Any) -> None:
        super().__init__(**kw); self._limiter, self._limit = limiter, limit
    def add_api_route(self, path: str, endpoint: Callable[..., Any], **kw: Any) -> None:
        super().add_api_route(path, self._limiter.limit(self._limit)(endpoint), **kw)
```
Each route gets its own bucket (`module.function` key, so route function names must be unique within a module). Handlers on this router need a `request` parameter (fails loudly at import otherwise).
- FastAPI validates parameters before the wrapped function runs, so 422 requests do not consume quota (cheap, never reach GNews).
- Rate limiting before the cache (D-11) holds automatically: the decorator wraps the handler, the cache lookup is inside the body, so a cache hit still counts.
- slowapi logs a WARNING containing the limit key (the client IP) when a limit is hit; treat as personal data in logs (Security section).
- Client IP: `get_remote_address` uses `request.client.host`. The TestClient default client host is `"testclient"`; pass `TestClient(app, client=("203.0.113.9", 1))` to simulate IPs.
- Proxy trust (D-10): uvicorn's built-in default already trusts `X-Forwarded-*` only from loopback (`FORWARDED_ALLOW_IPS`, default `127.0.0.1,::1`); behind a platform proxy every client then shares the proxy's IP (the limit becomes global, fail-closed). Implement `TRUST_PROXY_HEADERS=true` in the app by adding `uvicorn.middleware.proxy_headers.ProxyHeadersMiddleware(app, trusted_hosts=...)` with hosts from `FORWARDED_ALLOW_IPS`, never `"*"` unless the container is reachable only through the proxy (with `"*"` a client can supply its own leftmost `X-Forwarded-For`). The Dockerfile CMD stays as D-18 specifies.
- Smallest alternative if slowapi must go (verified, typed): `limits.strategies.FixedWindowRateLimiter(MemoryStorage())` in `app.state.limiter` and a dependency `rate_limit("2/minute", "analyze")` raising a `RateLimited(retry_after)` exception handled into problem+json; `[200, 200, 429]`, `Retry-After: 60`.

### Pattern 7: TTL cache (D-11)
cachetools documents that its caches "are not thread-safe. Access to a shared cache from multiple threads must be properly synchronized" [CITED: cachetools docs]. The `analyze` handler is a sync `def`, so it runs in the threadpool: every access, including `get`, needs the lock (expiry is a mutation). Verified: 16 threads x 2000 mixed get/set on a tiny TTL with a `threading.Lock` raised nothing; fake clock check: entry present at +599 s, gone at +601 s, LRU bound 2 respected.
```python
class AnalyzeCache:
    def __init__(self, ttl: float = 600, maxsize: int = 256, timer: Callable[[], float] = time.monotonic) -> None:
        self._cache: TTLCache[tuple[str, bool], AnalyzeResponse] = TTLCache(maxsize=maxsize, ttl=ttl, timer=timer)
        self._lock = threading.Lock()
    def get(self, query: str, demo: bool) -> AnalyzeResponse | None:
        with self._lock: return self._cache.get((query.casefold(), demo))
    def put(self, query: str, demo: bool, value: AnalyzeResponse) -> None:
        with self._lock: self._cache[(query.casefold(), demo)] = value
```
- The query is already trimmed by `StringConstraints(strip_whitespace=True)`; add `casefold()` (and optionally collapse internal whitespace, not required by D-11).
- Fetch OUTSIDE the lock (blocking network); two simultaneous misses may both fetch (bounded by the 10/min limit). `cachetools.cached(..., condition=Condition())` adds single-flight if wanted [CITED].
- Store the validated `AnalyzeResponse` and never mutate it; FastAPI re-serialises per request. A hit returns the stored `meta.data_as_of` unchanged. Only 200s are stored (exceptions propagate before `put`); the honest empty result IS stored (D-11).
- `X-Cache` is set via a `response: Response` parameter. It is deliberately undocumented in OpenAPI (documenting it would add a diff outside D-08's allowance).
- Tests: inject `timer` through `create_app(cache_timer=...)`; assert upstream call count via `len(mock_gnews.calls)`; 599 s hit, 601 s miss; 401 then 200 for the same key proves errors are not cached; 11th identical request returns 429 even though it would be a hit.

### Pattern 8: Bounded retry loop vs the `responses` mock (D-12)
`responses` can simulate: ordered response sequences for one URL (registered in order, the last repeats), exceptions as `body=` (`ConnectTimeout`, `ConnectionError`), and callbacks that raise, inspect `request.req_kwargs["timeout"]`, and advance a fake clock. It cannot simulate real elapsed time, a slow body, or a read timeout caused by a drip-feeding server [VERIFIED: local]. Design (prototype executed, results below):
```python
BACKOFFS = (0.3, 0.6); BUDGET = 8.0; CONNECT, READ = 3.05, 10.0
RETRY_STATUSES = frozenset({500, 502, 503, 504})
# per attempt:  remaining = BUDGET - elapsed;  timeout = (min(CONNECT, remaining), min(READ, remaining))
# retry on: requests.Timeout, requests.ConnectionError EXCEPT SSLError (a certificate failure is not transient); status in RETRY_STATUSES
# never retry: 4xx (incl. 429), 3xx (allow_redirects=False stays), 200 with bad payload
# before sleeping: if elapsed + delay >= BUDGET: give up with the last mapped error; delay = BACKOFFS[i] + jitter
```
Executed against `responses` with an injected `Clock(monotonic, sleep, jitter)`: sequence `500, 502, 200` gives 200 after sleeps `[0.3, 0.6]`; always-503 stops after 3 calls with sleeps `[0.3, 0.6]`; 401 makes 1 call, no sleep; a callback burning the passed `timeout` advances the fake clock to about 8.0 s total and then stops. Test the bound by asserting the `timeout` tuples shrink (`(3.05, 8.0)`, `(3.05, 4.5)`, `(0.7, 0.7)`) and that no attempt starts with `remaining <= 0`; have the callback advance the clock by the timeout actually passed (otherwise the fake overshoots the budget, as my first run did at 10.5 s).
- No real sleeping in tests: inject `sleep`/`monotonic`/`jitter` (module-level callables the fixture monkeypatches, or keyword arguments defaulting to `time.sleep`, `time.monotonic`, `random.uniform`). Jitter uses `random`: needs `# noqa: S311` (not security).
- Exceptions: `SSLError` and `ProxyError` are subclasses of `ConnectionError`; `ConnectTimeout` is both a `ConnectionError` and a `Timeout`; `ReadTimeout` is only a `Timeout` (MRO verified). Keep `except Timeout` before `except ConnectionError` to retain the Phase 1 mapping (timeout 503 `upstream_timeout`, unreachable 503 `upstream_unreachable`).
- Limitation to document: `requests` read timeouts are per socket read, so a server that dribbles bytes can exceed the 8 s budget; GNews bodies are tiny (`max=1`), so accept. A hard wall-clock guard would need `stream=True` plus a deadline check while reading.
- Cost: retries spend GNews quota on 5xx attempts (Assumption A7); `Retry-After: 0` clamp is `max(1, min(int(value), MAX_RETRY_AFTER))` (D-13). The sync handler blocks a threadpool thread for at most about 8 s.
- Log one line per attempt with `attempt`, `code`, upstream status only (never URL, key or exception text), as `_fail` does today.

### Pattern 9: Readiness registry and `/health`, `/ready` (prototype executed)
```python
Check = Callable[[], bool]
class ReadinessRegistry:
    def __init__(self) -> None: self._checks: dict[str, Check] = {}
    def register(self, name: str, check: Check) -> None:        # reject duplicates
    def run(self) -> dict[str, bool]:                            # an exception counts as failed; log the class name only
```
`/health` returns `Health(status="ok")`. `/ready` is a sync `def` (blocking Phase 3 DB checks run in the threadpool): no failed check gives 200 `Ready(status="ready", checks={name: "ok"})`; a failed one gives 503 `application/problem+json` with `code: "not_ready"`, `source_status: "not_ready"`, and `detail: "Not ready: database, model."`. Verified: a check raising `RuntimeError("secret conn string")` yields a 503 whose body does not contain "secret". Put failed names in `detail` (a new `Problem.failed_checks` member would change an existing schema, see Open Question 4). Declare the `/ready` 503 in OpenAPI WITHOUT the `Retry-After` header that `PROBLEM_RESPONSES[503]` declares for the provider case (or send one). The registry lives on `app.state.readiness`. Inject a failure in a test with `app.state.readiness.register("database", lambda: False)` on the per-test app; Phase 3/4 register inside `create_app()` (or lifespan) via a `register_default_checks(registry, settings)` hook. An empty `APIRouter(prefix="/v1")` adds nothing to OpenAPI.

### Pattern 10: Cascade invariants (D-03), property tests (executed and mutation-checked)
`core/cascade.py` prototype (frozen dataclass `CascadeEvent(event_id, parent_event_id, observed_at: datetime)`, `order_events`, `validate_cascade`, `CascadeError`): sort key `(observed_at, depth, event_id)` where depth is the distance to the root along known parents, so equal timestamps put a parent before its child; `validate_cascade` rejects duplicate ids, cycles (in `_depths`) and a known parent later than its child, and tolerates a missing parent (Phase 3 orphans are an explicit state, never invented). `schemas.Event` has `timestamp: str`, not `observed_at`, so `core/cascade.py` takes its own typed view and an adapter parses `Event.timestamp` into an aware datetime (the fixture is all `...Z`).

Strategy that makes the invariants meaningful: build a forest incrementally (each event picks an EARLIER event as parent or none, and is observed `parent.observed_at + delta` with `delta` including 0 so ties occur), then `st.permutations` to shuffle arrival order; a separate property mutates one child to `parent.observed_at - 1 µs` and expects `CascadeError`. Properties: (1) output is a permutation, sorted by `observed_at`, and every parent precedes its child even on timestamp ties; (2) idempotent and independent of input order (`order_events(reversed(x)) == order_events(x)`); (3) valid cascades validate; (4) a broken child is rejected. Mutation check: dropping the depth tie-break fails (1) with `assert 1 < 0`; changing `<` to `<=` in `validate_cascade` fails (3). Four tests at 200 examples ran in about 4 s.

Registration (in `tests/conftest.py`, loaded before collection):
```python
settings.register_profile("ci", max_examples=200, derandomize=True, database=None, deadline=None,
                          suppress_health_check=[HealthCheck.too_slow])
settings.register_profile("dev", max_examples=50, deadline=None)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))
```
CI runs `pytest --hypothesis-profile=ci` (verified to select the registered profile). Add `.hypothesis/` to `.gitignore` (the `dev` profile writes an example database; `ci` writes none). `filterwarnings = error` is safe with hypothesis 6.170.1.

### Pattern 11: OpenAPI golden snapshot (D-08), verified concept
Dump the Phase 1 document from commit `765b844` (13,942 bytes, `sort_keys=True`) into `tests/golden/openapi_phase1.json`, and assert that the new document minus the declared additions equals it:
```python
ALLOWED_NEW_PATHS = {"/health", "/ready"}
ALLOWED_NEW_RESPONSES = {"429"}
def phase1_view(cur: dict, base: dict) -> dict:
    doc = copy.deepcopy(cur)
    doc["paths"] = {p: v for p, v in doc["paths"].items() if p in base["paths"]}
    for path, item in doc["paths"].items():
        for method, op in item.items():
            for code in list(op["responses"]):
                if code in ALLOWED_NEW_RESPONSES and code not in base["paths"][path][method]["responses"]:
                    del op["responses"][code]
    doc["components"]["schemas"] = {n: s for n, s in doc["components"]["schemas"].items() if n in base["components"]["schemas"]}
    return doc
# plus the ONE declared schema exception from D-13: base["components"]["schemas"]["Problem"]["properties"]["synthetic"]["const"] = False
```
Verified: after the move the document was byte-identical; adding the limiter, cache, `request`/`response` parameters and `X-Cache` left it identical; declaring a 429 changed only that response entry (the subset check passed). Also keep a refreshable "current" snapshot (`UPDATE_GOLDEN=1`) for Phases 3-5. A changed existing schema (for example a new `Problem` member) fails the test, which is the intent.

### Pattern 12: Dockerfile (verified in parts; full `docker build` unverified here, see A1)
The uv docs pattern [CITED: https://docs.astral.sh/uv/guides/integration/docker/] (intermediate layers, `--no-editable`, copy only the venv into the final stage, pin uv by version or digest). I verified each step with the same flags outside Docker: `uv sync --frozen --no-install-project --no-dev --no-editable`, then `uv sync --locked --no-dev --no-editable` into a throwaway environment; the resulting site-packages contained `truthtrail/data/demo_analyze.json`, no dev tools, and `python -I -m uvicorn truthtrail.main:app` run from `/` with a scrubbed environment and `DEMO_MODE=true` answered `/analyze` with 200, and a `urllib.request.urlopen(...)` probe (the HEALTHCHECK mechanism) returned 200.
```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.1@sha256:4a1f3666816dafadd20ceb71eac9a7d56d7ef30279f7d64048519ab901ada336 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev --no-editable
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-editable

FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
CMD ["uvicorn", "truthtrail.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
Notes: `UV_PYTHON_DOWNLOADS=0` makes uv use the image's Python (the venv's `python` symlink then resolves identically in the final stage, same base digest); `urlopen` raises `HTTPError` on non-2xx so the command exits non-zero without `curl` (slim has none); `DEMO_MODE` is deliberately not set (default false); the image needs `GNEWS_API_KEY` at run time. `.dockerignore` (D-18 plus the rest): `.git`, `.github`, `.venv`, `.env*`, `**/__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.hypothesis`, `.coverage*`, `htmlcov`, `legacy`, `tests`, `scripts`, `.planning`, `.claude`, `node_modules`, `package*.json`, `*.md`, `Dockerfile`, `.dockerignore`. Because the Dockerfile copies explicit paths, `.dockerignore` is a second line of defence.

### Pattern 13: CI workflow (script-level pieces executed; YAML not run, A2-A3)
Keep job names `copy-guard`, `gitleaks`, `tests` (a GitHub branch-protection rule may reference them) and add `lint`, `typecheck`, `audit`, `docker`. Setup block for uv jobs:
```yaml
- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
  with: { persist-credentials: false }
- uses: astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9 # v9.0.0
  with: { version: "0.13.1", python-version: "3.13", enable-cache: true }
- run: uv sync --locked          # --no-dev for copy-guard (serving deps only; verified: same "135 OpenAPI strings" result)
```
setup-uv v9.0.0 notes (from the README and release page): `version` pins uv, `python-version` sets `UV_PYTHON`, caching is automatic on hosted runners, and v9 changed `prune-cache` to default `false` (larger caches). Commands, all run here against the scratch clone:
```
lint:       uv run --locked ruff check .   &&   uv run --locked ruff format --check .
typecheck:  uv run --locked mypy
tests:      uv run --locked pytest --cov --hypothesis-profile=ci          # coverage settings in pyproject
audit:      uv export --locked --no-emit-project --all-groups --format requirements-txt -o "$RUNNER_TEMP/audit.txt"
            uv run --locked pip-audit -r "$RUNNER_TEMP/audit.txt" --require-hashes --disable-pip --progress-spinner off
lock:       uv lock --check               # fails if pyproject.toml and uv.lock disagree
docker:     docker build -t truthtrail:ci .
            cid=$(docker run -d -e DEMO_MODE=true -p 8000:8000 truthtrail:ci)
            curl -fsS --retry 15 --retry-connrefused --retry-delay 1 http://127.0.0.1:8000/health
            curl -fsS http://127.0.0.1:8000/ready ; test "$(docker exec "$cid" id -u)" != 0
            docker exec "$cid" python -c "import importlib.util as u,sys; sys.exit(u.find_spec('spread_simulator') is not None)"
            (always) docker logs "$cid"; docker stop "$cid"
```
The existing `gitleaks` job is untouched. With `uv.lock`, `pyproject.toml`, the moved sources and a Dockerfile committed, `scripts/gitleaks_scan.sh <bin> <floor> HEAD <floor>` stayed clean over 64 commits and 91 files [VERIFIED].

### Anti-Patterns to Avoid
- **Module-level limiter/cache/registry:** cross-test and cross-app leakage (57 failures reproduced).
- **`SlowAPIMiddleware` or `default_limits` with `include_router`:** silent fail-open.
- **`headers_enabled=True`:** Retry-After on 200s.
- **Reading strict `Settings` while constructing the app:** import-time failure (exit 1 instead of 3).
- **`app.add_exception_handler(X, handler)` with a handler narrowed to `X`:** mypy strict error (Starlette's handler type takes `Exception`); the decorator form `@app.exception_handler(X)` passes strict (verified).
- **`readme = ...` in an app `pyproject.toml`.**
- **`types-*` stub packages for libraries that already ship `py.typed`.**
- **Creating the root `main.py` shim in the same commit as the move.**

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Rate-limit counting windows | Own counters/timers | `limits` (via slowapi decorators or a thin dependency) | Window arithmetic, thread-safe memory storage, expiry timer |
| TTL + LRU cache | dict + timestamps | `cachetools.TTLCache` with a lock and `timer=` | Expiry, size bound, injectable clock |
| Env list parsing | manual `os.environ` splitting | pydantic-settings `Annotated[list[str], NoDecode]` + before-validator | Plain `list[str]` demands JSON in env (verified failure) |
| Proxy header trust | Parsing `X-Forwarded-For` | `uvicorn.middleware.proxy_headers.ProxyHeadersMiddleware` | Correct trusted-hop handling |
| CORS | Manual header setting | `CORSMiddleware` (+ our catch-all to keep 500s inside it) | Preflight, Vary, method checks |
| HTTP mocking | monkeypatching `requests.get` | `responses` (sequences, callbacks, exceptions) | Reproduces error classes and `req_kwargs["timeout"]` |
| Container install | `pip install` in Dockerfile | `uv sync --locked --no-dev --no-editable` from the lock | Same resolution as CI; wheel-installed package data |
| Dependency audit | Parsing lock yourself | `uv export` + `pip-audit --require-hashes` | Hash-pinned, no resolver |
| Cascade ordering property tests | Hand-picked examples | hypothesis composite strategy with ties and shuffles | Finds tie and ordering defects (mutants killed) |

Small custom code that IS appropriate: the retry loop (D-12 explicitly), the 25-line catch-all middleware, the readiness registry, `LimitedRouter`, and the OpenAPI subset check.

## Runtime State Inventory

This phase moves and renames modules and replaces the dependency manifest, so the categories were checked explicitly.

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | None. No database, cache or file store holds module paths. The fixture file moves but its bytes do not (sha256 unchanged). | Code edit only (path constants) |
| Live service config | GitHub Actions: the workflow's `pip` caches key on `requirements*.txt`; if branch protection requires the status checks `copy-guard`, `gitleaks`, `tests`, renaming a job would block merges (cannot be inspected from the repo; owner setting, per the Phase 1 handoff). | Keep job names; replace pip cache steps with setup-uv cache; owner confirms required checks after the first green run |
| OS-registered state | None in the repo. The owner's Windows machine has the old pip `.venv`. | Owner runs `uv sync` (adopts or replaces `.venv`); no re-registration |
| Secrets / env vars | New variable names: `CORS_ORIGINS`, `TRUST_PROXY_HEADERS`, rate-limit settings. `tests/test_no_hardcoded_credentials.py::EXPECTED_ENV_NAMES` and `tests/conftest.py::ENV_NAMES` hard-code the current five names, and `test_env_example_lists_names_only` requires every `.env.example` entry to match `NAME=` (blank value). | Update both constants; document the Vite origin as a COMMENT line, not a value (Pitfall 12) |
| Build artifacts / installed packages | `requirements.txt`, `requirements-dev.txt`, `pytest.ini` (replaced), stale `.pytest_cache`, `.venv` built with pip; `scripts/generate_demo_fixture.py` and `tests/test_demo_fixture.py` hold the `fixtures/` path; README setup text; `tests/test_no_hardcoded_credentials.py` parametrised ignore-check paths (`fixtures/demo_analyze.json`, `models.py`) are strings and still pass but should be updated to the new paths. | Delete manifests after `uv.lock` exists; update paths; rewrite README setup |

## Common Pitfalls

### Pitfall 1: Applying `order_events()` at fixture load changes the served demo body
**What goes wrong:** the committed fixture lists events as per-platform chains (`news, tw x6, fb x6, re x6`), so none of its three cascades is sorted by timestamp (cascade 1 also has 2 timestamp ties). `test_demo_mode_serves_labelled_fixture` asserts `body == committed`. Sorting at load makes that test (and the "frozen /analyze contract") fail.
**How to avoid:** see Open Question 3. Recommended: call `validate_cascade()` at load (hard gate, fails startup/500 on a corrupt fixture, which also folds review item IN-02) and keep `order_events()` as the tested pure function Phase 3 serves.
**Warning signs:** `assert body == committed` failing with identical event sets in a different order.

### Pitfall 2: slowapi middleware/default limits are inert under `include_router`
**What goes wrong:** with FastAPI 0.143 the route list holds an `_IncludedRouter` without `.endpoint`; slowapi treats the route as exempt, with no error. **How to avoid:** decorators or `LimitedRouter`; add a test that sends `limit + 1` requests to a `/v1` test route and expects 429 (this test would have caught the defect). **Source:** issue #281 and local reproduction.

### Pitfall 3: Import-time settings break the fail-fast contract
See Pattern 4. **Warning signs:** `test_uvicorn_exits_on_missing_key` returning code 1 and a traceback instead of "Application startup failed".

### Pitfall 4: Legacy flat imports and unchanged bytes
`spread_simulator.py` has `from users import USERS`. Moving both into `legacy/` unchanged means `import legacy.spread_simulator` raises `ModuleNotFoundError: users`. Put `legacy/` on pytest `pythonpath` and on `sys.path` in `scripts/generate_demo_fixture.py` (done in the scratch run; `--check` passed). Ruff/mypy must exclude `legacy` (`extend-exclude`), otherwise ruff would rewrite CRLF-era style and break the frozen hashes.

### Pitfall 5: `ruff format` rewrites the "byte-identical" keyword baseline
`ruff format --check` flags 20 files including `services/keyword_baseline.py` (one-line keyword lists, blank lines). Exclude it from the formatter only: `[tool.ruff.format] exclude = ["src/truthtrail/services/keyword_baseline.py"]` (verified untouched after `ruff format` + `ruff check --fix`). `ruff check` itself passes on it.

### Pitfall 6: Hypothesis/coverage artefacts and the `.gitignore`
`.hypothesis/` is not in `.gitignore`; add it. `.coverage`, `htmlcov/`, `.mypy_cache/`, `.ruff_cache/` already are.

### Pitfall 7: `readme = "README.md"` plus `.dockerignore` excluding `*.md`
`uv_build` opens the README at build time: `failed to open file .../README.md: No such file or directory` (reproduced twice). Omit `readme` (the package is not published).

### Pitfall 8: Demo fixture outside the package
The `DEMO_MODE=true` docker smoke needs the fixture in the image, and `Path(__file__).parents[3]` is wrong inside site-packages. Move it to `src/truthtrail/data/demo_analyze.json` (`git mv`; `.gitignore` has only an anchored `/data/`, so it is not ignored). `uv_build` includes it in the wheel (verified listing). Update `FIXTURE_PATH` (`Path(__file__).resolve().parents[1] / "data" / "demo_analyze.json"` from `api/`), the generator, and the two test constants.

### Pitfall 9: `Path.write_text` newline translation on Windows
`generate_demo_fixture.py` writes with `Path.write_text(rendered, encoding="utf-8")`; on Windows `\n` becomes `\r\n`. `--check` passes anyway (it reads in text mode) and Git normalises on add, but any byte-level hash check would differ. Use `write_text(..., newline="\n")` and rely on `.gitattributes`.

### Pitfall 10: `Literal[False]` changes the OpenAPI `Problem` schema
Verified: `{"default": false, ..., "type": "boolean"}` becomes `{"const": false, "default": false, ..., "type": "boolean"}`. Declare it in the golden test (Pattern 11).

### Pitfall 11: mypy `add_exception_handler` variance and other strict findings
11 strict errors in 3 files (see Validation/lint section). Use the decorator form for handlers.

### Pitfall 12: `.env.example` is machine-checked
`test_env_example_lists_names_only` requires every non-comment line to match `^[A-Z][A-Z0-9_]*=$`. D-09's "document `http://localhost:5173`" must be a comment (`# CORS_ORIGINS=http://localhost:5173 for the local Vite dev server`) followed by a blank `CORS_ORIGINS=` line, and `EXPECTED_ENV_NAMES` must gain the new names.

### Pitfall 13: pytest.ini silently overrides pyproject
See Pattern 3.

### Pitfall 14: Docker/uv version drift
Pin uv in CI (`version: "0.13.1"`) and in the image (digest). `uv.lock` here is `revision = 5`; uv 0.11.32 reads it, but run `uv lock --check` in CI so an accidental `uv lock` by a different uv version shows up as a diff. A very new tool set (uv, ruff, hypothesis, cachetools shipped this week) means the first lock is a moving target: lock once, commit, upgrade deliberately.

### Pitfall 15: The first full `docker build` happens in CI
No daemon here. Keep the `docker` job last in the plan and treat its first run as the verification gate (human-verify at end of phase, as the config requires).

## Code Examples

### Existing-test patch targets (exact edits)
```python
# tests/conftest.py  client_factory
import truthtrail.main as main            # was: import main        (then build via create_app() per test)
# tests/test_provenance_demo.py:160,178,179
monkeypatch.setattr("truthtrail.api.analyze.load_demo_fixture", stub)       # module that owns the function after the split
# tests/test_request_validation.py:142
monkeypatch.setattr("truthtrail.api.analyze.analyze_risk", boom)
# tests/test_upstream_errors.py:316
adapter_records = [r for r in caplog.records if r.name == "truthtrail.services.gnews"]
```

### Legacy-unreachable proof (D-01, success criterion 1)
```python
# tests/test_no_legacy_imports.py  (ast walk) + subprocess check
FORBIDDEN = {"legacy", "spread_simulator", "users", "risk_analyzer"}
def test_package_never_imports_legacy() -> None:
    for path in (REPO_ROOT / "src" / "truthtrail").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            assert not [n for n in names if n.split(".")[0] in FORBIDDEN], path

def test_importing_the_app_does_not_load_legacy() -> None:   # fresh interpreter: pytest's own sys.modules is polluted
    code = "import sys, truthtrail.main; sys.exit(any(m in sys.modules for m in ('spread_simulator','users','legacy')))"
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1", **windows_system_env()}   # SYSTEMROOT on Windows
    assert subprocess.run([sys.executable, "-c", code], env=env, cwd=tmp_path).returncode == 0
```
Move the duplicated `_windows_system_env()` helper into `tests/conftest.py` so every new subprocess test gets `SYSTEMROOT`.

### pip-audit (exact, executed)
```bash
uv export --locked --no-emit-project --all-groups --format requirements-txt -o /tmp/audit.txt
uv run --locked pip-audit -r /tmp/audit.txt --require-hashes --disable-pip --progress-spinner off
# -> "No known vulnerabilities found" (74 hashed pins; serving-only export: 26 pins), exit 0
```
Negative control (executed): `jinja2==2.11.2` gave 10 findings and exit 1; adding `--ignore-vuln <ID>` for each id gave "No known vulnerabilities found, 10 ignored" and exit 0.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `pip` + `requirements*.txt` | uv lock + dependency groups (PEP 735) | this phase | `train` excluded by default, one lock for CI and image |
| hatchling/setuptools for apps | `uv_build` (default src layout, no config) | uv 0.8+ | zero-config `src/truthtrail` |
| `FastAPI.include_router` copying routes | `_IncludedRouter` objects (FastAPI >= 0.137) | 2026 | slowapi middleware default limits break (issue #281) |
| `types-requests` stubs | `requests` ships `py.typed` (2.34.2) | verified here | drop the stubs |
| `gitleaks-action` | pinned binary scripts (Phase 1) | Phase 1 | unchanged |
| GitHub Actions `setup-python` + pip cache | `astral-sh/setup-uv` v9 (installs Python, caches uv) | v9.0.0 | fewer steps; `prune-cache` default now false |

**Deprecated/outdated:** `pytest.ini` once `pyproject.toml` carries pytest config; `requirements*.txt`; `UV_NATIVE_TLS` (use `UV_SYSTEM_CERTS`, container only).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The Dockerfile builds and the container passes the smoke test as written. Only the individual steps were executed (the Docker CLI 29.8.2 is present, `dockerd` binary exists, but the daemon is not running in this container). | Pattern 12 | First CI `docker` run fails; fix is local to the Dockerfile |
| A2 | `ubuntu-latest` has the Docker daemon, `curl` and `docker exec` available as used in the `docker` job | Pattern 13 | Job needs an extra setup step |
| A3 | `astral-sh/setup-uv@v9.0.0` with `version: "0.13.1"` and `python-version: "3.13"` installs and verifies uv and downloads CPython 3.13 on a hosted runner (README read, workflow not run; setup-uv's bundled known-checksums were last updated for 0.11.30) | Pattern 13 | Drop `python-version` and keep `actions/setup-python`, or use `version: latest`; no code impact |
| A4 | The CI workflow YAML is semantically right (not executed; no runner or GitHub API access for this repo from here) | Pattern 13 | One-line fixes after the first push; CI green is a human-verify item |
| A5 | Windows behaviours: `winget install --id=astral-sh.uv -e`, `uv sync` adopting the old `.venv`, uv downloading CPython 3.13 if absent, `write_text` newline translation | Installation, Pitfall 9 | Owner follows the PowerShell note and reports; commands are from the uv installation docs (CITED) but not run on Windows |
| A6 | GNews counts every HTTP attempt (including retried 5xx) against the 100 requests/day free quota | Pattern 8 | Retries cost more quota than assumed; the 10/min limit and the 600 s cache bound exposure |
| A7 | The recommended proxy-trust design (`ProxyHeadersMiddleware` with `FORWARDED_ALLOW_IPS`) matches the Phase 6 host's topology | Pattern 6 | Re-decide in Phase 6; mis-set trust either shares one bucket or allows spoofing |
| A8 | Coverage baseline: 98% line+branch was measured on the moved code plus the cascade prototype only (no new ENG-06 code). The `fail_under` value (D-15: baseline minus 2) must be re-measured on the final tree | Validation | A gate set too early is too loose or too tight |
| A9 | slowapi's in-memory storage growth under many distinct IPs is bounded by `limits`' expiry timer (observed no thread leaks over 30 apps; not stress-tested with high key cardinality) | Security | Memory growth under a distributed flood; acceptable for the single-instance demo, revisit with Redis (deferred) |
| A10 | `pytest` branch-protection required checks exist on the GitHub repo (owner setting, not visible from here) | Runtime State Inventory | Renaming jobs would block merges |
| A11 | The fixture ordering decision in Open Question 3 is the owner's call | Open Questions | Different served event order or a changed Phase 1 test |

## Open Questions

1. **Build backend and layout (RESOLVED)**
   - Recommendation: `uv_build` with default `src/` discovery; verified editable install, non-editable install, wheel contents.
2. **Where the demo fixture lives (RESOLVED)**
   - `src/truthtrail/data/demo_analyze.json` via `git mv` (bytes unchanged, sha256 recorded); needed so the image and the `DEMO_MODE=true` smoke job work.
3. **D-03: apply `order_events()` at fixture load? (OPEN, owner/planner decision)**
   - What we know: the fixture is not time-ordered; the Phase 1 test requires `body == committed`; `Event` has `timestamp`.
   - Options: (a) RECOMMENDED: `validate_cascade()` at load, `order_events()` tested and unused on the demo path (documented: demo events are grouped by platform chain); (b) apply both and edit `test_demo_mode_serves_labelled_fixture` to compare against the ordered fixture (the served body differs from the file, violating "frozen contract" unless the owner accepts it); (c) regenerate the fixture sorted (changes fixture bytes, rejected by the byte-identity requirement).
4. **`/ready` failed-check names and OpenAPI allowance (RESOLVED, with one exception)**
   - Names go in `detail` so no existing schema changes. The only declared schema exception is D-13's `Problem.synthetic` `const: false` (Pattern 11); the plan should state this as an amendment to D-08's allowance.
5. **Byte-identical legacy modules vs CRLF renormalisation (RESOLVED)**
   - Define identity modulo CRLF to LF; pin the three hashes above; use `--ignore-cr-at-eol` in the Phase 1 gate.
6. **Construction-time vs lifespan-time settings (RESOLVED)**
   - `BootSettings` (no required fields) at construction; strict `Settings` in lifespan (exit 3 preserved); callable rate limits.
7. **Proxy trust semantics for `TRUST_PROXY_HEADERS` (OPEN, low; decide in Phase 6 deploy)**
   - Implemented as an app-level `ProxyHeadersMiddleware` fed by `FORWARDED_ALLOW_IPS`; tests use `TestClient(client=...)` and a fake `X-Forwarded-For`. Phase 6 chooses the trusted address of the host's proxy.
8. **Dependency version policy (OPEN, low)**
   - Ranges + lock resolved to fastapi 0.143.3 / pydantic 2.14.1 / pydantic-settings 2.16.0 (suite green) versus exact Phase 1 pins (also green). Pick one in the plan; do not mix.
9. **Coverage gate (OPEN until the last code plan)**
   - Measure after ENG-06 code lands; set `fail_under = floor(measured) - 2`; ratchet.
10. **Docker and workflow verification (OPEN, human-verify at end of phase)**
    - Cannot be proven here; the first green CI run on the final commit is the gate (config `human_verify_mode: end-of-phase`).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.13 | everything | yes | 3.13.16 (`/usr/bin/python3.13`) | — |
| uv | lock, sync, CI parity | yes | 0.11.32 preinstalled; 0.13.1 via `pip install uv` in a venv | either works with the lock |
| git | moves, hooks of the scan scripts | yes | 2.43.0 | — |
| Docker CLI | Dockerfile | CLI yes (29.8.2), daemon NO (`/var/run/docker.sock` absent; `dockerd` binary present, not started) | — | CI `docker` job is the verification (A1) |
| Docker Hub / ghcr.io registry APIs | digests | yes through the proxy | — | — |
| PyPI (JSON API, simple index) | locking, pip-audit | yes | — | — |
| docs.astral.sh | docs | direct fetch blocked; read through Firecrawl | — | — |
| `gh` / GitHub API for this repo | CI status | NO (HTTP 403, repository access not enabled) | — | owner confirms CI green after push |
| gitleaks | secret scan | installed to a scratch dir by `scripts/install_gitleaks.sh` | 8.30.1 | — |
| pypistats.org | download counts | NO (proxy 403) | — | PyPI age/release evidence used |

**Missing dependencies with no fallback:** none for planning. A green Docker build and GitHub Actions run can only be confirmed after a push.
**Missing dependencies with fallback:** local Docker daemon (use CI), GitHub API (owner check).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1, pytest-cov 7.1.0, hypothesis 6.170.1, responses 0.26.3, Starlette TestClient (httpx 0.28.1) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (replaces `pytest.ini`) |
| Quick run command | `uv run pytest -x -q tests/<file>.py` |
| Full suite command | `uv run pytest --cov --hypothesis-profile=ci` |
| Non-pytest gates | `uv run ruff check . && uv run ruff format --check .`; `uv run mypy`; `uv run python scripts/copy_guard.py`; `uv run python scripts/generate_demo_fixture.py --check`; `uv lock --check`; pip-audit pair (Pattern 13); gitleaks scripts; docker job |

### Phase Requirements -> Test Map
| Req ID / SC | Behavior | Test Type | Automated Command | File Exists? |
|-------------|----------|-----------|-------------------|--------------|
| ENG-01 / SC1 | Phase 1 suite passes after retargeting (274 passed, 10 xfailed, 0 XPASS) | regression | `uv run pytest -q` | exists (edit imports) |
| ENG-01 / SC1 | package never imports legacy; app import loads no legacy module | unit + subprocess | `uv run pytest -q tests/test_no_legacy_imports.py` | Wave 0 |
| ENG-01 | legacy and keyword baseline frozen (LF-normalised sha256) | unit | `uv run pytest -q tests/test_legacy_frozen.py` | Wave 0 |
| ENG-01 / D-05 | root shim exposes the same app | unit | `uv run pytest -q tests/test_main_shim.py` | Wave 0 |
| D-08 | OpenAPI = Phase 1 subset + declared additions (429, `/health`, `/ready`, `Problem.synthetic` const) | contract | `uv run pytest -q tests/test_openapi_golden.py` | Wave 0 (`tests/golden/openapi_phase1.json` from `765b844`) |
| ENG-02 / SC2 | `pyproject` has `train` group outside default; lock current; image excludes train/dev | unit (tomllib) + CI | `uv run pytest -q tests/test_dependency_groups.py`; `uv lock --check` | Wave 0 |
| ENG-03 / SC3 | cascade ordering and parent-before-child properties | property | `uv run pytest -q tests/test_cascade_properties.py --hypothesis-profile=ci` | Wave 0 |
| ENG-03 / D-03 | fixture passes `validate_cascade`; hypothesis profile `ci` selected in CI | unit | `uv run pytest -q tests/test_demo_fixture.py` | exists + extend |
| ENG-03 | coverage reported and gated | CI | `uv run pytest --cov` (`fail_under` in `[tool.coverage.report]`) | Wave 0 config |
| ENG-04 / SC2 | lint, types, tests, audit, secret scan green on the final commit | CI | `gh`/Actions run for the pushed SHA | human-verify |
| ENG-05 / SC4 | `/health` 200; `/ready` 200 empty; 503 problem+json with an injected failing/raising check, no exception text | integration | `uv run pytest -q tests/test_health_ready.py` | Wave 0 |
| ENG-05 / SC4 | image builds, container answers `/health`, runs non-root | CI | docker job | human-verify (A1) |
| ENG-06 / SC5 | allowed origin gets ACAO, other origin none, unset env none; 429 and 500 carry ACAO; methods limited | integration | `uv run pytest -q tests/test_cors.py` | Wave 0 |
| ENG-06 / SC5 | `/analyze` 11th request 429 + `Retry-After >= 1` + provenance members; `/health`,`/ready` never limited; a `/v1` route is limited (fail-closed); per-IP isolation; trusted-proxy flag | integration | `uv run pytest -q tests/test_rate_limit.py` | Wave 0 |
| ENG-06 / SC5 | cache hit/miss with fake clock, `X-Cache`, `data_as_of` preserved, errors not cached, empty cached, limit-before-cache | integration | `uv run pytest -q tests/test_cache.py` | Wave 0 |
| ENG-06 / SC5 | retries: 500,502,200 succeeds; always-503 stops at 3 calls; 401/429 never retried; timeouts shrink within 8 s; no real sleep | integration (responses) | `uv run pytest -q tests/test_retries.py` | Wave 0 |
| D-13 | `Retry-After: 0` becomes 1; `Problem.synthetic` literal | unit | extend `tests/test_upstream_errors.py`, `tests/test_response_models.py` | exists + extend |
| FND carry-over | copy guard clean on README, OpenAPI strings of `/health`,`/ready`,429 | CI + unit | `uv run python scripts/copy_guard.py` | exists |

### Sampling Rate
- **Per task commit:** `uv run pytest -x -q <touched files>` plus `uv run ruff check <files>`.
- **Per wave merge:** `uv run pytest -q`, `uv run mypy`, `uv run ruff check . && uv run ruff format --check .`, copy guard, fixture `--check`.
- **Phase gate:** full suite with coverage and `--hypothesis-profile=ci`, `uv lock --check`, pip-audit pair, gitleaks scan from the floor, then a green Actions run on the pushed final commit before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/golden/openapi_phase1.json` (dump from `765b844`: `python -I` script importing the app with `DEMO_MODE=true`, `json.dump(app.openapi(), sort_keys=True, indent=2)`) and `tests/test_openapi_golden.py`
- [ ] `tests/test_legacy_frozen.py`, `tests/test_no_legacy_imports.py`, `tests/test_main_shim.py`, `tests/test_dependency_groups.py`
- [ ] `tests/test_cascade_properties.py` + `src/truthtrail/core/cascade.py`; Hypothesis profiles in `tests/conftest.py`
- [ ] `tests/test_health_ready.py`, `tests/test_cors.py`, `tests/test_rate_limit.py`, `tests/test_cache.py`, `tests/test_retries.py`
- [ ] `tests/conftest.py`: per-test `create_app()`, new env names in `ENV_NAMES`, shared `windows_system_env()`, fake `Clock` fixtures
- [ ] `pyproject.toml` tool sections (pytest, coverage, ruff, mypy), `.gitattributes`, `.gitignore` (`.hypothesis/`), `.dockerignore`, `Dockerfile`
- [ ] Framework install: `uv sync`

### Lint and type-check baseline (measured on a copy, read-only on the repo)
Ruff 0.17.1, D-15 families, `line-length = 100`, `extend-exclude = ["legacy"]`, `tests/**` ignoring `S`: **81 findings**, 33 auto-fixable (`UP045` Optional to `X | None` x16, `UP017` `datetime.UTC` x7, `I001` x7, `SIM117` x2, `F401` x1); `ruff format` reformats 19 of 69 files (not `keyword_baseline.py` once excluded); after format + `--fix`, **24 remain**: 21 `E501` (comments/docstrings/strings in `scripts/copy_guard.py` x3, `api/app.py` x2, `core/config.py`, `schemas/models.py` x4, several tests), `S311` (`scripts/generate_demo_fixture.py` `random.Random(SEED)`: `# noqa: S311`, deterministic fixture seed), `B905` + `RUF007` (`tests/test_char_simulator.py:60` `zip` over pairs: use `itertools.pairwise`), `PT018` x2 (split compound asserts). Exceptions needed: `extend-exclude = ["legacy"]`, formatter exclude for `keyword_baseline.py`, one `noqa: S311`, and optionally `E501` for `tests/**`. No `S` finding fires in `src/truthtrail` (the `0.0.0.0` bind lives only in the Dockerfile).
mypy 2.4.0 `strict = true` with `plugins = ["pydantic.mypy"]` (13 errors without the plugin, 11 with): **11 errors in 3 files** after the move: bare `dict`/`list[dict]` generics x4 (`api/problems.py` x3, `services/gnews.py`), `Mapping[str, str] | None` passed where `dict` is declared (`problems.py`), four `add_exception_handler` variance errors (use `@app.exception_handler(...)` decorators), `requests.get(params=...)` typed `dict[str, object]` (annotate `dict[str, str | int]`), and the untyped `lifespan` (`-> AsyncIterator[None]`). `services/keyword_baseline.py` passes strict as is. A relaxed run over `tests` and `scripts` (`check_untyped_defs`, `ignore_missing_imports`) reports 10 errors (`DemoResult | LiveResult` has no `events` x7: assert `isinstance`; `importlib` spec `Optional` x3): recommend either fixing them or running mypy on `src/truthtrail` only in CI (D-15 allows a relaxed config; decide in the plan).
No `pydantic-settings`-specific plugin is needed.

## Security Domain

Config: `security_enforcement` true, ASVS level 1, block on high.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V1 Architecture / V14 Configuration | yes | env-only config, lock-pinned dependencies, digest-pinned base images and SHA-pinned actions, non-root container, `permissions: contents: read`, `persist-credentials: false` |
| V2 / V3 Authentication, sessions | no | unauthenticated public read API; no cookies (CORS `allow_credentials=False`) |
| V4 Access Control | yes (limited) | CORS allow-list; `/ready` and `/health` unauthenticated by decision |
| V5 Input Validation | yes | unchanged `StringConstraints` query rule (422 not counted against the limit); origin list validated at boot |
| V7 Error Handling and Logging | yes | problem+json for 429/503/500; class names only in logs; slowapi's WARNING contains the client IP |
| V8 Data Protection | yes | `SecretStr`, header-only key, `from None`; no secret in image layers (`DEMO_MODE` unset by default) |
| V12/V13 API and Web Service | yes | typed models, golden OpenAPI, rate limiting, bounded outbound calls |
| V10 Malicious Code / supply chain | yes | `uv.lock` hashes, `pip-audit --require-hashes`, gitleaks, `--locked` installs |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Rate-limit bypass by spoofed `X-Forwarded-For` | Spoofing / DoS | Trust proxy headers only when `TRUST_PROXY_HEADERS=true`, with explicit trusted hosts; default uses the socket peer |
| Silent loss of limits on new `/v1` routes (slowapi fail-open) | Elevation / DoS | Decorators + `LimitedRouter`; test that a `/v1` route returns 429 |
| Wildcard or malformed CORS origin | Information disclosure | Unset means none; reject `*` and trailing-slash origins; methods GET/HEAD/OPTIONS; no credentials |
| 500/429 without CORS headers hides problem+json from the dashboard | Availability (UX) | Catch-all inside CORS; 429 raised inside the route |
| Retry amplification burns GNews quota or hammers a failing provider | DoS (quota) | max 3 attempts, no retry on 4xx/429, 8 s budget, 10/min per IP, 600 s cache |
| Cache poisoning / unbounded growth | Tampering / DoS | key = (casefolded validated query, demo flag); LRU `maxsize=256`; only 200s stored; stored object never mutated |
| Client IP kept in logs (slowapi WARNING) | Information disclosure (privacy) | Accept for a demo; set the `slowapi` logger level to ERROR in `create_app()` if IPs must not be logged |
| Key or URL leaking through retry logging | Information disclosure | Log attempt number, code and upstream status only (Phase 1 `_fail` pattern) |
| `/ready` reveals dependency names | Information disclosure | Names only (no exception text), accepted by D-07 |
| Compromised/typosquatted dependency | Tampering | Lock + hashes, `pip-audit`, legitimacy audit above; slowapi flagged as low-adoption |
| Image runs as root / bloated attack surface | Elevation | Non-root uid 10001, slim base by digest, no dev/train groups, no curl |
| Vulnerability disclosure turns CI red without code change | Availability (process) | `--ignore-vuln <ID>` with a dated comment; optional scheduled audit |

## Sources

### Primary (HIGH confidence)
- Local executions this session (Python 3.13.16; uv 0.13.1 and 0.11.32; scratch clones of the repo at `765b844`): `git mv`/`--follow`, renormalisation, `uv lock`/`sync`/`export`/`build`, wheel contents, pytest suite (274 passed, 10 xfailed), coverage (98%), ruff 0.17.1 and mypy 2.4.0 reports, slowapi/limits experiments, CORS/ServerErrorMiddleware experiment, retry prototype against `responses`, hypothesis strategies with mutation checks, OpenAPI diffs, pip-audit runs, gitleaks scan, uvicorn exit codes.
- `pip index versions` and `https://pypi.org/pypi/<pkg>/json` (versions, first-upload dates, repositories), 2026-10-17.
- `git ls-remote --tags` for astral-sh/setup-uv, actions/checkout, actions/setup-python, astral-sh/uv.
- Docker Hub registry API (`python:3.13-slim` digest) and ghcr.io registry API (`astral-sh/uv:0.13.1` digest).
- Installed source: `slowapi/extension.py`, `slowapi/middleware.py`, `uvicorn/middleware/proxy_headers.py`, `uvicorn/config.py`, `cachetools/__init__.py`, `limits/storage/memory.py`.
- In-repo files read this session: `main.py`, `config.py`, `problems.py`, `models.py`, `gnews_fetcher.py`, `scripts/generate_demo_fixture.py`, `tests/conftest.py`, `tests/test_network_guard.py`, `tests/test_demo_fixture.py`, `tests/test_provenance_demo.py` (88-142), `tests/test_settings.py` (100-255), `tests/test_no_hardcoded_credentials.py` (60-106), `pytest.ini`, `requirements*.txt`, `.github/workflows/ci.yml`, `.gitignore`, `.env.example`, `README.md`, the Phase 1 CONTEXT/RESEARCH/REVIEW/VERIFICATION/SECURITY and `.planning/HANDOFF.md`.

### Secondary (MEDIUM confidence)
- https://docs.astral.sh/uv/guides/integration/docker/ (multi-stage pattern, `--no-editable`, pinning; read via Firecrawl)
- https://docs.astral.sh/uv/concepts/projects/dependencies/ (dependency groups; dev synced by default)
- https://docs.astral.sh/uv/concepts/build-backend/ (`uv_build` config, default `src/` module root)
- https://docs.astral.sh/uv/getting-started/installation/ (Windows commands)
- https://cachetools.readthedocs.io/en/latest/ (not thread-safe; `timer`; `cached(lock, condition)`)
- https://github.com/astral-sh/setup-uv README at v9.0.0 and its v9.0.0 release page (inputs; `prune-cache` default change)
- https://github.com/laurents/slowapi/issues/281 (fail-open under FastAPI >= 0.137; open) and https://github.com/laurents/slowapi/releases (0.1.10 notes)

### Tertiary (LOW confidence)
- None relied upon.

## Metadata

**Confidence breakdown:**
- Standard stack and versions: HIGH - read from the index today and resolved/installed together on 3.13.
- Architecture and move procedure: HIGH - executed end to end in a scratch clone, suite green.
- ENG-06 guards (CORS, rate limit, cache, retry): HIGH - each prototyped against the pinned FastAPI/Starlette; slowapi fail-open reproduced and matched to an upstream issue.
- Docker and the GitHub Actions workflow: MEDIUM - steps executed individually; daemon and runner unavailable (A1-A4).
- Windows behaviour: MEDIUM - from documentation and the Phase 1 lesson; not run on Windows (A5).

**Research date:** 2026-10-17
**Valid until:** 2026-10-24 for tool versions (uv, ruff, hypothesis and cachetools shipped within the last four days; re-run `pip index versions` and `git ls-remote` at execution time); 2026-11-17 for the architectural findings.
