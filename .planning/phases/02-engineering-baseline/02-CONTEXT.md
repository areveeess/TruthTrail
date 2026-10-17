# Phase 2: Engineering Baseline - Context

**Gathered:** 2026-10-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Turn the honest-but-flat Phase 1 service into a properly packaged, tested, containerised and CI-guarded FastAPI app, with a versioned `/v1` router mount point that Phases 3 and 4 can extend independently. Delivers: a `src/truthtrail` package (api, services, schemas, core); a uv lockfile on Python 3.13 with serving / training / dev dependency groups; a pytest + hypothesis suite with coverage and cascade-ordering property tests; CI with ruff, mypy, pytest, pip-audit, the existing copy guard and secret scan, plus a Docker build-and-smoke job; a Dockerfile; `/health` and `/ready`; configured-origin CORS, rate limiting (429), a TTL cache for repeated reads, and outbound HTTP with timeouts and a bounded retry.

Requirements: ENG-01, ENG-02, ENG-03, ENG-04, ENG-05, ENG-06.

**Not in this phase:** the database and its `/ready` check (Phase 3), the model artifact and its `/ready` check (Phase 4), any real propagation data, any new `/v1` data endpoint, the dashboard, deployment. The `/analyze` contract (envelope, problem+json, provenance) is frozen: this phase changes where the code lives and how it is guarded, not what `/analyze` returns, except the explicitly listed folded fixes below.

</domain>

<decisions>
## Implementation Decisions

The owner reviewed the gray areas and then delegated the answers ("do whatever you recommend"). Every decision below is therefore the recommended option, taken by Claude, and the owner may revisit any of them before planning.

### Legacy modules and the "unreachable" criterion
- **D-01:** `spread_simulator.py` and `users.py` move **unchanged** (byte-identical content) to a top-level `legacy/` directory that is **outside** `src/`, not packaged and not copied into the Docker image. Only `scripts/generate_demo_fixture.py` and the strict-xfail characterization tests import them (their import lines change; every assertion stays identical). Nothing under `src/truthtrail` may import `legacy` (enforced by a test that walks the package's imports). — **Reversibility:** reversible — a directory move.
- **D-02:** `risk_analyzer.py` moves to `src/truthtrail/services/keyword_baseline.py` with **byte-identical rule logic** (only the module path changes). The 8 pinned keyword-defect xfails keep failing for the same reasons. Fixing word boundaries and the hardcoded names waits for Phase 4's "baseline 0 as shipped vs fixed" comparison. — **Reversibility:** reversible.
- **D-03:** The cascade-ordering invariants (events ordered by `observed_at`; a child never earlier than its parent) are implemented as pure functions `order_events()` and `validate_cascade()` in `src/truthtrail/core/cascade.py`, property-tested with hypothesis on arbitrary generated cascades, and **applied when the demo fixture is loaded**. Phase 3's real data reuses them. The legacy simulator's child-before-parent defect stays pinned (strict xfail) in `legacy/` and is not fixed. — **Reversibility:** costly — Phase 3 data code will depend on these signatures.

### Package layout, entrypoint and routes
- **D-04:** Layout `src/truthtrail/{api,services,schemas,core}`: `api/` (app factory, routers, problem+json handlers, middleware), `services/` (GNews client, keyword baseline), `schemas/` (the Phase 1 pydantic models, `Event` JSON schema unchanged), `core/` (settings, errors, cascade, readiness registry). Canonical entrypoint `truthtrail.main:app` (`uvicorn truthtrail.main:app`). — **Reversibility:** costly — every later phase imports from these paths.
- **D-05:** Keep a two-line root `main.py` shim (`from truthtrail.main import app`) so `uvicorn main:app`, the README and existing run instructions keep working; document it as a compatibility shim, to be removed when the dashboard phase lands.
- **D-06:** `/analyze` keeps its exact Phase 1 contract and stays at the root (flagged for retirement or reduction in Phase 3 per the ROADMAP open scoping question). A new empty versioned `APIRouter(prefix="/v1")` is mounted as the extension point for Phases 3 and 4. `/health` (liveness, always 200 when the process serves) and `/ready` live at the root, unauthenticated.
- **D-07:** `/ready` uses a registry of named dependency checks (sync callables returning ok/failed). With no checks registered it returns 200 `{"status":"ready","checks":{}}`; if any check fails it returns **503 problem+json** (D-15 shape from Phase 1) naming only the failed check names, never exception text. Phase 3 and 4 register their checks; this phase proves the 503 path with an injected failing check.
- **D-08:** A golden OpenAPI snapshot test proves the refactor did not change the `/analyze` contract: the OpenAPI document is compared to a committed snapshot, and the only permitted differences are the new `/health`, `/ready` and 429 entries. The Phase 1 characterization and contract tests must pass with only import-path edits.

### CORS, rate limiting, caching, retries
- **D-09:** CORS origins come from env `CORS_ORIGINS` (comma-separated). **Unset means no cross-origin access** (secure by default); `.env.example` documents the local Vite origin `http://localhost:5173`. Methods GET/HEAD/OPTIONS only, no credentials. `CORSMiddleware` is the outermost middleware so **error responses (including 500 and 429) carry CORS headers** (folds Phase 1 review item IN-02).
- **D-10:** Rate limiting is **in-memory, single-instance** (the demo deploys as one free-tier container; a shared store is deferred). Use `slowapi`, keyed by client IP. Proxy headers are trusted **only** when `TRUST_PROXY_HEADERS=true` (uvicorn `--proxy-headers` / forwarded-allow-ips), default false, so the limit cannot be bypassed by a spoofed header. Defaults: `/analyze` 10 per minute per IP (it spends scarce GNews quota), `/v1/*` 60 per minute, `/health` and `/ready` exempt. Limits are env-configurable. A limited request returns **429 problem+json** (code `rate_limited`) with `Retry-After` and the provenance members. — **Reversibility:** reversible.
- **D-11:** Repeated reads use an in-process TTL cache (`cachetools.TTLCache`, lock-guarded) for `/analyze`, keyed by the trimmed, casefolded query plus the demo-mode flag; **TTL 600 s, max 256 entries** (GNews' free tier allows ~100 requests/day, so a long TTL protects quota). Only successful responses (200, including the honest empty result) are cached; **errors are never cached**. A cache hit keeps the original `meta.data_as_of`, so staleness stays visible, and sets a `X-Cache: hit|miss` header. Rate limiting applies before the cache.
- **D-12:** Outbound GNews retries use an **explicit, small retry loop in our own code** (not urllib3 `Retry`), so it is testable with the `responses` mock: at most **2 retries (3 attempts)**, exponential backoff 0.3 s then 0.6 s plus jitter, only for connect errors, timeouts and HTTP 500/502/503/504 on this idempotent GET. **No retry on 4xx, including 429** (retrying wastes quota). A total time budget of 8 s caps the whole call. When the bound is exhausted the Phase 1 mapping (D-06/D-07 there) applies unchanged. A test with a mocked slow or failing upstream proves it stops at the bound.
- **D-13 (folded review items):** Clamp a provider `Retry-After: 0` to a minimum of 1 s (IN-03); make `Problem.synthetic` `Literal[False]` (IN-05, typing part).

### Tooling, CI and container
- **D-14:** Dependency management is **uv** on Python 3.13 (`requires-python = ">=3.13,<3.14"`, `.python-version`), with a committed `uv.lock`. Groups: serving (the project dependencies), `dev` (pytest, pytest-cov, hypothesis, responses, httpx, ruff, mypy, pip-audit) and `train` (scikit-learn and numpy, documented as unused until Phase 4 and excluded from the image and the default CI sync). The Phase 1 `requirements*.txt` files are removed once `uv.lock` exists; the README setup becomes `uv sync` (with a Windows note). — **Reversibility:** costly — CI, Docker and README all depend on it.
- **D-15:** Ruff for lint and format (line length 100; rule families E, F, I, UP, B, S, SIM, C4, PT, RUF; `tests/` may relax `S`). mypy runs `strict = true` on `src/truthtrail` and a relaxed config on tests and scripts. Coverage via pytest-cov with a `fail_under` gate set to the **measured baseline minus 2 points** and only ever ratcheted upward. Hypothesis uses a pinned CI profile (derandomized, no example database) so CI is reproducible.
- **D-16:** Normalise line endings in one dedicated first commit: add `.gitattributes` (`* text=auto eol=lf`, `*.sh` forced LF) and renormalise the CRLF files (`main.py`, `gnews_fetcher.py`, and any other), so later diffs and the moves into `src/` are clean (folds review item IN-05).
- **D-17:** CI keeps the Phase 1 copy-guard, gitleaks (floor-bounded, with its selftest) and tests jobs and adds: `lint` (ruff check and format --check), `typecheck` (mypy), `audit` (pip-audit against the exported lock), and `docker` (build the image, run it with `DEMO_MODE=true`, and curl `/health`). Third-party actions stay SHA-pinned (add `astral-sh/setup-uv` pinned the same way), `persist-credentials: false`, job timeouts. The phase is done when CI is green on the final commit.
- **D-18:** The Dockerfile is multi-stage on `python:3.13-slim` (tag plus digest), installs with `uv sync --frozen --no-dev`, runs as a non-root user, contains no secrets (`DEMO_MODE` defaults false, so the image needs `GNEWS_API_KEY` at run time), has a `HEALTHCHECK` on `/health`, and starts `uvicorn truthtrail.main:app --host 0.0.0.0 --port 8000`. `legacy/`, `tests/`, `.planning/` and `scripts/` are excluded via `.dockerignore`.

### Claude's Discretion
Exact module and file names inside each package folder, hypothesis strategy details, how the OpenAPI snapshot is stored and refreshed, the structure of the readiness registry beyond its observable behaviour, and the precise ruff rule exceptions needed to pass on the existing code.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and requirements
- `.planning/ROADMAP.md` — Phase 2 goal, success criteria 1-5, the cross-cutting contracts note, and the Phase 3 open scoping question about `/analyze`
- `.planning/REQUIREMENTS.md` — ENG-01 to ENG-06
- `.planning/PROJECT.md` — core value, constraints (stack, honesty, git/process rules)

### Contracts that must not change
- `.planning/phases/01-secure-honest-foundation/01-CONTEXT.md` — D-01..D-20 (envelope, problem+json, provenance, status mapping, secret handling); note the mapping of D-06/D-07/D-15 there is what retries and 429 must respect
- `.planning/phases/01-secure-honest-foundation/01-VERIFICATION.md` — what Phase 1 proved and how
- `.planning/phases/01-secure-honest-foundation/01-REVIEW.md` — deferred items IN-02, IN-03, IN-05 folded into D-09, D-13, D-16
- `.planning/phases/01-secure-honest-foundation/01-SECURITY.md` — accepted risks and residual observations (CORS wildcard, no rate limit) this phase closes

### Code being moved or extended
- `main.py`, `config.py`, `problems.py`, `models.py`, `gnews_fetcher.py` — the Phase 1 modules that become `src/truthtrail`
- `risk_analyzer.py`, `spread_simulator.py`, `users.py` — legacy modules (D-01, D-02)
- `scripts/generate_demo_fixture.py`, `fixtures/demo_analyze.json` — the only non-test consumers of the legacy simulator
- `tests/conftest.py`, `pytest.ini` — network guard and strict-xfail configuration that must survive the refactor
- `.github/workflows/ci.yml`, `scripts/gitleaks_scan.sh`, `scripts/gitleaks_selftest.sh`, `scripts/copy_guard.py` — existing CI and guards to extend, not replace

### Research
- `.planning/research/STACK.md`, `.planning/research/ARCHITECTURE.md`, `.planning/research/PITFALLS.md` — stack and structure guidance for this phase
- `.planning/codebase/STRUCTURE.md`, `.planning/codebase/CONVENTIONS.md`, `.planning/codebase/TESTING.md` — pre-Phase-1 codebase maps (line numbers unreliable, trust content)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `config.py` (`get_settings`, `ConfigurationError`, `is_header_safe_key`): becomes `core/config.py`; add `CORS_ORIGINS`, `TRUST_PROXY_HEADERS` and rate-limit settings here.
- `problems.py` (`problem_response`, `register_problem_handlers`, `UpstreamError`): the single problem+json builder, reused for 429 and `/ready` 503.
- `models.py` (`AnalyzeResponse`, `Meta`, `Problem`, `Event`): moves to `schemas/` unchanged.
- `tests/conftest.py` (`client_factory`, `mock_gnews`, autouse network guard): reused as is; the retry and cache tests build on `mock_gnews`.
- `scripts/gitleaks_scan.sh` / `gitleaks_selftest.sh` and `scripts/copy_guard.py`: reused untouched.

### Established Patterns
- Characterization-first: strict xfails encode known defects; any refactor must keep them failing for the same reasons (XPASS is a visible signal).
- Errors are a single RFC 9457 shape with provenance members; every new error path (429, `/ready` 503) uses the same builder.
- Secrets only via environment; tests use obviously fake tokens; a credential backstop test scans the tree, `.planning/` and `.claude/`.
- Commits end with the attribution trailers; key-material scan before every commit.

### Integration Points
- The live route imports only `gnews_fetcher`, `models`, `problems`, `risk_analyzer`; the legacy simulator is reached only by the fixture generator and tests, so moving it breaks nothing in the live path.
- `uvicorn main:app` is used by the README, the owner's Windows run steps and tests; the shim (D-05) keeps all three working.
- CI currently installs from `requirements-dev.txt`; switching to uv changes every job's setup step.

</code_context>

<specifics>
## Specific Ideas

- The owner runs the project on native Windows (PowerShell); Phase 2 setup instructions must include a Windows path (uv install via winget or pip, `uv sync`, `uv run`), and any new subprocess-based test must pass `SYSTEMROOT` as the Phase 1 fix did.
- The owner wants to review each stage; this phase's plan, execution and verification are each presented for review before the next begins.

</specifics>

<deferred>
## Deferred Ideas

- Shared rate-limit and cache store (Redis) for multi-instance deployments: only if the Phase 6 deploy needs more than one instance.
- Pre-commit hooks, structured JSON logging, a metrics endpoint, API-key auth, a load test (all OPS2-01, v2).
- Removing the root `main.py` shim: when the dashboard phase lands.
- Retiring or reducing `/analyze`: Phase 3 (ROADMAP open scoping question).

</deferred>

---

*Phase: 02-engineering-baseline*
*Context gathered: 2026-10-17*
