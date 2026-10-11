# Phase 1: Secure & Honest Foundation - Research

**Researched:** 2026-10-11
**Domain:** Hardening and honesty retrofit of a flat-module FastAPI service (secrets/config, upstream error contract, provenance envelope, typed responses, characterization tests, copy guard, minimal CI)
**Confidence:** HIGH (nearly every recommendation below was executed in a scratch venv on Python 3.13.16 with the pinned versions; items that could not be executed are tagged)

## Project Constraints (from CLAUDE.md)

Source: `/home/user/TruthTrail/.claude/CLAUDE.md` (config key `claude_md_path` points there). No project skills exist (`.claude/skills/`, `.agents/skills/` absent).

- **Honesty:** user-facing copy must say "flag for human review", never "detects the truth"; synthetic/demo data is labelled as such in API and UI.
- **Security:** secrets only via environment variables, never committed; scan `.planning/` and code for key material before every commit. **Never write the old GNews key into any file or output** (it still sits in the working tree at `gnews_fetcher.py` lines 3 and 6, and in git history at `1fedcd2`).
- **Process/git:** all work on branch `claude/sleepy-lovelace-13aums`; no per-phase branches; no PRs unless the owner asks; push after each phase; no history rewrite / force-push (D-11).
- **Stack:** keep Python + FastAPI (React/Postgres come later); flat root-level modules stay until Phase 2.
- **Conventions (`CONVENTIONS.md` block):** 4-space indent, double quotes, `snake_case`, annotate new signatures, `logging.getLogger(__name__)` (no `print`), triple-double-quoted docstrings. The existing `publishedAt` camelCase is replaced by `published_at` in the new envelope (D-01 example).
- **Workflow enforcement:** repo edits go through a GSD command (this phase is executed via `/gsd-execute-phase`).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### `/analyze` response shape
- **D-01:** Replace the bare JSON list with an envelope object: `{"results": [...], "meta": {"synthetic": bool, "data_as_of": <ISO-8601 UTC string>, "source_status": "ok" | "empty" | ...}}`. This is a deliberate breaking change; nothing in this repository consumes the old shape. — **Reversibility:** costly — every later `/v1` endpoint will copy this envelope, so changing it later touches all of them and any client.
- **D-02:** Demo data comes from a **static fixture JSON** committed to the repo, generated once from the existing simulator with a fixed seed and flagged `synthetic: true`. It is served only when `DEMO_MODE=true`. The simulator code itself is left untouched in Phase 1 (used only to generate the fixture), so Phase 2 can delete `spread_simulator.py` and `users.py` without changing demo behaviour.
- **D-03:** The `risk` value stays `High` / `Medium` / `Low`, and each result gains `risk_method: "keyword_baseline"` so no client mistakes it for a trained model.
- **D-04:** A query with zero articles returns **HTTP 200** with `{"results": [], "meta": {"source_status": "empty", "synthetic": false, ...}}`. The fabricated "unknown / 2025-01-01" fallback article is removed entirely.
- **D-05 (auto, derived from FND-03):** With `DEMO_MODE=false` (the default) a live result contains the headline, source, published time, `risk` and `risk_method` but **no `events` key at all** (omitted, not an empty list, so "no spread data" cannot be mistaken for "nothing spread"). With `DEMO_MODE=true`, the response is the fixture, `meta.synthetic` is `true`, and `events` is present.

#### Error contract
- **D-06:** Errors are **RFC 9457 `application/problem+json`**: `type`, `title`, `status`, `detail`, plus extension members `code` (stable machine-readable string such as `upstream_unauthorized`, `upstream_bad_response`, `upstream_timeout`, `upstream_rate_limited`, `not_configured`) and `upstream` (e.g. `"gnews"`). Bodies and logs must never contain the upstream URL, query string or any key. **(auto)** Request-validation failures (422, FND-04) use the same problem+json shape with an `errors` extension, for one consistent error format.
- **D-07:** Status mapping: **502** when the upstream answered badly (HTTP 401/403, 5xx, non-JSON body, malformed or null-field records); **503 with a `Retry-After` header** when it cannot be reached or is throttling (timeout, connection error, HTTP 429). A test must prove a GNews 401 returns 502, not 200.
- **D-08 (auto):** If the news API key is absent at startup, the service **fails fast** with an explicit configuration error, unless `DEMO_MODE=true` (which needs no key). The always-false placeholder guard in `gnews_fetcher.py` is replaced by a real check on the settings value. The Bluesky app password and database URL are defined as optional settings now (documented in `.env.example`) but are not required until Phase 3.

#### Secrets, scanning and history
- **D-09 (auto):** Secret scanner is **gitleaks**, run as a blocking CI job that scans (a) the working tree and (b) the commit range of each push/PR, so a key that is committed and later deleted still fails the build. Pre-rotation history is **not** scanned (the rotated key in commit `1fedcd2` is known and inert); no baseline file is needed. Researcher: verify the current gitleaks release and install method, and pin version and checksum. — **Reversibility:** reversible.
- **D-10 (auto):** Add `.gitignore` (Python, Node, virtualenvs, `.env*` except `.env.example`, data/model artifact dirs) and `.env.example` containing **names only**: `GNEWS_API_KEY`, `DEMO_MODE`, `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD`, `DATABASE_URL`. Test fixtures use obviously fake placeholder tokens that do not resemble real keys, to avoid scanner false positives.
- **D-11 (owner standing rule, from PROJECT.md):** The old rotated GNews key remains in git history. **Do not** rewrite history or force-push in this phase; that requires an explicit owner request.

#### Tests and copy guard
- **D-12 (auto):** Characterization tests pin **stable** current behaviour with golden tables (e.g. `analyze_risk` on a fixed headline set; simulator event-count and linkage invariants under a fixed seed; the old `/analyze` endpoint with mocked `requests.get`). **Known defects are encoded as `xfail(strict=True)` tests that assert the desired behaviour** (substring false positives such as "secure"→High, "studies"→High, "couple"→High; hardcoded-name High risk; child timestamped before parent), so fixing them later flips a visible XPASS and no test asserts a bug as correct. Sequencing: the characterization tests are committed **before** any behavioural change; after the envelope change (D-01) the old-shape endpoint tests are deliberately replaced by contract tests, while the pure-function characterization suite persists.
- **D-13 (auto):** The copy guard is a script (also run as a pytest test) scanning `README.md`, `docs/**`, and FastAPI's OpenAPI strings (title / description / summaries), and any future UI string directory. Banned: truth- or fake-news-detection claims (e.g. "detects the truth", "fake news detector", "detects misinformation"), a `FAKE` verdict label/badge, and "AI-based" / "AI-powered" while no trained model exists. An inline `copy-guard: allow` marker permits quoting; `tests/` and `.planning/` are excluded. The README is rewritten now as a short, honest "prototype under reconstruction" note using "flag for human review" wording.
- **D-14 (auto):** Minimal CI in Phase 1: `.github/workflows/ci.yml` with the **copy guard** and **gitleaks** jobs required; a pytest job is included if installing dependencies is trivial. Phase 2 (ENG-04) extends this workflow with ruff, mypy, pip-audit and uv; it does not replace it.

### Claude's Discretion
- Settings mechanism (e.g. `pydantic-settings` vs plain `os.environ`), exact `code` string names, fixture seed and file location, test directory layout, GitHub Action versions/pins, exact README wording, and how `data_as_of` is derived (upstream article time vs fetch time; must be a UTC ISO-8601 string and documented).
- Whether the `Event` model in `models.py` is reused or replaced when building response models. Its fields differ slightly from the simulator output; it is currently unused.

### Deferred Ideas (OUT OF SCOPE)
- **Purging the old key from git history** — requires `git filter-repo` plus a force-push; only on an explicit owner request, never as part of a phase.
- **Retiring or reducing the query-driven `/analyze`** — DATA-06 forbids proxying arbitrary queries to the news API; this is an open scoping question for Phase 3 planning (see ROADMAP.md Cross-Phase Notes).
- **CORS restriction, rate limiting, caching, outbound retries** — Phase 2 (ENG-06).
- **Local pre-commit secret hook and enabling GitHub's native secret scanning / push protection** — worth doing but outside the roadmap; the owner can enable the GitHub settings in the repo's security settings.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FND-01 | All credentials read from env vars; `.env.example` documents them; no secret in the tree | pydantic-settings with `SecretStr`, `env_ignore_empty`, `hide_input_in_errors`; fail-fast lifespan (verified, uvicorn exit code 3); `.gitignore` semantics verified; gitleaks working-tree scan verified (detects the current literal, exit 1); regex backstop test |
| FND-02 | Upstream failure -> 502/503 machine-readable body, never fabricated 200 | Adapter table (23 scenarios executed against `responses`); RFC 9457 handlers; header-based key removes the URL-leak vector of `raise_for_status()`; Retry-After |
| FND-03 | Every response carries `synthetic`, `data_as_of`, `source_status`; fixtures only under `DEMO_MODE=true` (default false) | Envelope models (union of `LiveResult`/`DemoResult`, `extra="forbid"`) verified; deterministic fixture generator needs `uuid4` patching; error bodies need provenance extension (Open Question 1) |
| FND-04 | Invalid/oversize input -> 422; every endpoint has a Pydantic response model in OpenAPI | `Annotated[str, StringConstraints(...)]` verified (strip, 1..200, control-char pattern); 422 problem+json override with `input` echo stripped; OpenAPI walker test verified (flags an untyped `{}` schema) |
| FND-05 | Characterization tests pin current `/analyze` behaviour incl. known defects before refactor | Current behaviour captured empirically (see Pitfall 1 table); golden values; `xfail(strict=True, raises=AssertionError)` verified to fail the build on XPASS; mandatory network guard |
| FND-06 | Copy says "flag for human review"; CI fails on banned phrases | Copy-guard script prototype executed against README/OpenAPI/samples; regex set, allow marker, exclusions, false-positive list |
</phase_requirements>

## Summary

The phase is a retrofit on 5 small flat modules (204 lines in total). The mechanics are all standard, and nearly all of them were executed here, so the plan can be prescriptive. The hard part is not any single technique but five traps in the current code that make the locked decisions harder than they look: (1) the real, rotated key is still the live default in the working tree, so the characterization tests (which must be committed first) will call the real GNews API unless a hard network guard exists from the very first commit; (2) `requests.raise_for_status()` and several `requests` exception strings embed the full URL including `apikey=...`, which would violate D-06 unless the key moves to the `X-Api-Key` header (which GNews documents) and exceptions are raised `from None`; (3) `uuid.uuid4()` is not seeded by `random.seed()`, so "fixed seed" fixture generation is only deterministic if the generator patches `uuid4`; (4) the simulator puts a child before its parent in ~41% of links (1479 of 3600 across 200 seeds), so a "demo cascade" fixture would visibly lie about time unless the generator post-processes timestamps; (5) gitleaks 8.30.1 **fails open** (exit code 0) when `--log-opts` contains an unresolvable revision, so the CI script must validate the range itself.

For tooling: FastAPI 0.143.0 / Pydantic 2.14.0 / Starlette 1.7.0 / pydantic-settings 2.15.0 / pytest 9.1.1 / `responses` 0.26.3 all resolve together on Python 3.13. Starlette 1.7's `TestClient` now prefers `httpx2` (pydantic/httpx2) and emits a `StarletteDeprecationWarning` when only `httpx` is present, so use `httpx2==2.13.1` as the test dependency. gitleaks is at 8.30.1 (2026-03-21); use the checksum-verified binary download in CI (not `gitleaks-action`, which only scans history and adds licence/token coupling). Pin `actions/checkout` v7.0.1 and `actions/setup-python` v7.0.0 by commit SHA.

**Primary recommendation:** Land the work in four ordered plans: (A) test infrastructure + characterization tests against the unmodified code, with an autouse network guard; (B) settings/secret removal + typed-error adapter; (C) envelope, problem+json, validation, fixture, OpenAPI test; (D) README, copy guard, gitleaks script, CI workflow last (the secret scan can only be green after plan B removes the literal).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Credential/config loading and fail-fast | API / Backend (`config.py`, lifespan) | CI (secret scan) | Process must refuse to start misconfigured; env is the only source |
| Upstream error classification (401/403/429/5xx/timeout/malformed) | API / Backend (adapter `gnews_fetcher.py`) | — | The adapter owns the provider seam and must raise typed errors; handlers only render them |
| Problem+json rendering, Retry-After, 422 shape | API / Backend (exception handlers in `main.py`) | — | One place formats every error so all later routers inherit it |
| Provenance (`synthetic`, `data_as_of`, `source_status`) | API / Backend (response models + route) | Fixture file (static) | Computed per response; demo values come from the committed fixture, never computed |
| Demo fixture generation | Build/dev script (`scripts/generate_demo_fixture.py`) | Static storage (committed JSON) | Run offline once; runtime only reads JSON |
| Input validation | API / Backend (Pydantic `Query` constraints) | — | Validation at the boundary, before any upstream call |
| Secret scanning, copy guard | CI / repo tooling | Local script/pytest | Enforced on every push; also runnable locally |
| Copy (README, OpenAPI strings) | Docs + API metadata | CI copy guard | Honest wording is a repo artifact, verified mechanically |

## Standard Stack

### Core (runtime, pinned in `requirements.txt`)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | 0.143.0 | HTTP API | Existing backend; `pip index versions` shows 0.143.0 as latest [VERIFIED: pip index, 2026-10-11] |
| pydantic | 2.14.0 | Response models, upstream-payload validation | Already imported by `models.py`; currently only a transitive dependency, so declare it [VERIFIED: pip index] |
| pydantic-settings | 2.15.0 | Env-only settings, `SecretStr`, fail-fast validation | Official Pydantic companion; behaviours below executed [VERIFIED: pip index + local experiments] |
| uvicorn | 0.54.0 | ASGI server | Existing; startup-failure exit code 3 verified [VERIFIED: pip index + local run] |
| requests | 2.34.2 | GNews adapter (kept in Phase 1; no restructuring) | Existing adapter library [VERIFIED: pip index] |
| starlette | 1.7.0 (transitive) | Underlying framework | Pulled by fastapi 0.143.0 (`starlette>=0.46.0`) [VERIFIED: venv resolve] |

### Supporting (dev, pinned in `requirements-dev.txt` = `-r requirements.txt` + below)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.1.1 | Test runner | All tests [VERIFIED: pip index] |
| responses | 0.26.3 | Mock the `requests` transport; blocks unregistered URLs | Adapter + endpoint tests [VERIFIED: pip index + local experiments] |
| httpx2 | 2.13.1 | Backend of `fastapi.testclient.TestClient` | Starlette 1.7 imports `httpx2` first and warns on `httpx` [VERIFIED: starlette/testclient.py lines 31-48 in the installed package] |

Verbatim from the installed `starlette/testclient.py` (lines 31-48): `import httpx2 as httpx` is tried first; on `ModuleNotFoundError` it falls back to `import httpx` and calls `warnings.warn("Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.", StarletteDeprecationWarning, ...)`. Starlette's own `full` extra lists `httpx2>=2.0.0` and `httpx<0.29.0,>=0.27.0`. With `httpx2`, `python -W error -c "from fastapi.testclient import TestClient"` succeeds [VERIFIED: local run]. This supersedes the `httpx 0.28.1` note in `.planning/research/STACK.md` for the test client; Phase 2 should re-decide the outbound client (`httpx` vs `httpx2`).

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `httpx2` | `httpx==0.28.1` | Works, but every test run emits `StarletteDeprecationWarning`; then `filterwarnings = error` needs an ignore entry. Fallback if the human-verify checkpoint on `httpx2` is declined |
| `responses` | `unittest.mock.patch("requests.get")` | Mock patching cannot reproduce `raise_for_status()` text, `Retry-After` headers, `ConnectTimeout` MRO, or block unregistered URLs; `responses` does all of it (see Code Examples) |
| `pydantic-settings` | plain `os.environ` | `os.environ` cannot give typed bools, `SecretStr` masking, `.env` loading for local dev only, or a single validated object; hand-rolling these is error-prone (see Don't Hand-Roll) |
| gitleaks binary | `gitleaks/gitleaks-action@v3` | Action: no licence needed for user accounts [CITED: github.com/gitleaks/gitleaks-action README], but it scans history/PR commits not the working tree, hides the exact flags, and adds a token/licence coupling; the binary gives both scans, a pinned checksum and the fail-open guard below |

**Installation:**
```bash
# requirements.txt (runtime)
fastapi==0.143.0
pydantic==2.14.0
pydantic-settings==2.15.0
uvicorn==0.54.0
requests==2.34.2

# requirements-dev.txt
-r requirements.txt
pytest==9.1.1
responses==0.26.3
httpx2==2.13.1
```
The whole set resolved and ran together in a clean Python 3.13.16 venv created with `uv venv` [VERIFIED: local]. Note the sandbox's global site-packages differ (pydantic 2.13.5, starlette 1.6.0); always test in a clean venv.

**Version verification:** `pip index versions <pkg>` on 2026-10-11 returned fastapi 0.143.0, pydantic 2.14.0, pydantic-settings 2.15.0, starlette 1.7.0, httpx 0.28.1, httpx2 2.13.1 (installed index says latest 2.13.1), pytest 9.1.1, responses 0.26.3, requests 2.34.2, uvicorn 0.54.0.

## Package Legitimacy Audit

The `gsd-tools query package-legitimacy check --ecosystem pypi ...` seam returned **SUS for every package** — an artefact, not a finding: PyPI's API exposes no download counts (`weeklyDownloads: null` -> reason `unknown-downloads`), and the `too-new` reason fires because the seam only sees the latest-release timestamp (fastapi/pydantic/uvicorn all shipped within the last 30 days). Independent evidence is in the table.

| Package | Registry | Age (first upload) | Downloads | Source Repo | Seam Verdict | Disposition |
|---------|----------|--------------------|-----------|-------------|--------------|-------------|
| fastapi | PyPI | years (project predates 2019) | n/a (PyPI) | github.com/fastapi/fastapi | SUS (too-new, unknown-downloads) | Approved after the single checkpoint below |
| pydantic | PyPI | years | n/a | github.com/pydantic/pydantic | SUS (too-new, unknown-downloads) | Approved after checkpoint |
| pydantic-settings | PyPI | 2019-08-19, 45 releases [VERIFIED: pypi.org JSON] | n/a | github.com/pydantic/pydantic-settings | SUS (unknown-downloads) | Approved after checkpoint |
| uvicorn | PyPI | years | n/a | github.com/Kludex/uvicorn | SUS (too-new, unknown-downloads) | Approved after checkpoint |
| requests | PyPI | years | n/a | github.com/psf/requests | SUS (unknown-downloads) | Approved after checkpoint |
| pytest | PyPI | years | n/a | github.com/pytest-dev/pytest | SUS (unknown-downloads) | Approved after checkpoint |
| responses | PyPI | 2013-11-25, 65 releases [VERIFIED: pypi.org JSON] | n/a | github.com/getsentry/responses | SUS (unknown-downloads) | Approved after checkpoint |
| httpx2 | PyPI | **2026-05-11**, 18 releases [VERIFIED: pypi.org JSON] | n/a | github.com/pydantic/httpx2 (Pydantic org stewardship of the HTTPX lineage; README) | SUS (too-new, unknown-downloads) | **Flagged** - newest dependency; required by Starlette 1.7 TestClient preference. Fallback: `httpx==0.28.1` |

**Packages removed due to SLOP verdict:** none.
**Packages flagged SUS:** all eight, for the artefact reasons above. **Planner: insert ONE `checkpoint:human-verify` task covering the pinned requirement set** (compare the names/versions in the two requirements files against this table, with particular attention to `httpx2`) before the first `pip install`. No `postinstall` scripts apply (all are Python packages).

## Architecture Patterns

### System Architecture Diagram

```
                    process start (uvicorn main:app, cwd = repo root)
                                   |
                     lifespan: load_settings()  -- missing GNEWS_API_KEY & DEMO_MODE!=true
                                   |                    --> ConfigurationError, exit code 3 (fail fast)
                                   v
 HTTP GET /analyze?query=...  --> [CORSMiddleware (unchanged; Phase 2)]
                                   |
                       FastAPI param validation (Query: strip, 1..200 chars, no control chars)
                         | invalid                                 | valid
                         v                                         v
          RequestValidationError handler                   analyze(query, settings via Depends)
          -> 422 application/problem+json                          |
             (errors[] without `input`/`ctx`)          settings.demo_mode ?
                                                        |yes                 |no
                                                        v                    v
                                      load fixtures/demo_analyze.json   gnews_fetcher.fetch_news(query, api_key)
                                      validate as AnalyzeResponse        requests.get(timeout, X-Api-Key header)
                                      (synthetic=true, source_status=         |
                                       "fixture", events present)     classify: Timeout->503 / ConnErr->503 /
                                                                      401,403,5xx,other->502 / 429->503+Retry-After /
                                                                      non-JSON, schema violation, null fields -> 502
                                                                             | raises UpstreamError(status, code, detail)
                                                                             v
                                                        UpstreamError handler -> problem+json (+Retry-After on 503)
                                                                             |ok
                                                                             v
                                                       for each article: analyze_risk(title) -> LiveResult
                                                       (no `events` key; risk_method="keyword_baseline")
                                                       meta: synthetic=false, data_as_of=now(UTC),
                                                             source_status = "ok" | "empty"
                                   |
        every other error (404/405 via Starlette HTTPException, uncaught Exception) -> same problem+json shape
```

### Recommended Project Structure (flat layout preserved)
```
.
├── main.py                  # app, lifespan, handlers, /analyze  (edited)
├── config.py                # NEW: Settings, ConfigurationError, get_settings
├── gnews_fetcher.py         # adapter: typed errors, timeout, header key  (edited; key literal removed)
├── models.py                # Event (reused as-is) + Meta, LiveResult, DemoResult, AnalyzeResponse, Problem
├── problems.py              # NEW (optional): UpstreamError, problem body builder, PROBLEM_RESPONSES
├── risk_analyzer.py, spread_simulator.py, users.py   # UNCHANGED in Phase 1
├── fixtures/demo_analyze.json         # NEW committed demo response (NOT under data/, which .gitignore ignores)
├── scripts/
│   ├── generate_demo_fixture.py       # offline, seeded; patches uuid4
│   ├── copy_guard.py                  # CI + pytest
│   └── gitleaks_scan.sh               # CI + local
├── tests/
│   ├── conftest.py                    # env scrub, env_file off, network guard, client factory
│   ├── test_char_risk_analyzer.py     # golden + xfail(strict) defects (persist)
│   ├── test_char_simulator.py         # invariants + xfail(strict) defects (persist while simulator exists)
│   ├── test_char_analyze_legacy.py    # old list-shape endpoint tests (DELETED when D-01 lands)
│   ├── test_settings.py, test_upstream_errors.py, test_provenance_demo.py,
│   ├── test_validation_openapi.py, test_copy_guard.py, test_no_hardcoded_credentials.py
│   └── fixtures/                      # HTTP payload samples with obviously fake tokens
├── .github/workflows/ci.yml
├── .gitignore, .env.example, pytest.ini, requirements.txt, requirements-dev.txt, README.md
```

`pytest.ini` (rather than a pyproject, which Phase 2 creates with uv):
```ini
[pytest]
pythonpath = .
testpaths = tests
xfail_strict = true
addopts = -ra
filterwarnings =
    error
```
`pythonpath = .` is needed because the modules are imported by bare name. `filterwarnings = error` is safe with `httpx2` [VERIFIED: `-W error` run passed]; with plain `httpx` it fails on the deprecation warning.

### Pattern 1: Settings (pydantic-settings, lazy, fail-fast)
**What:** one `Settings` class; read lazily (never at import); validated in the app lifespan; `SecretStr` for secrets; masked errors.
**Why each option:** `env_ignore_empty=True` makes `GNEWS_API_KEY=` (the blank lines users copy from `.env.example`) count as unset, and `DEMO_MODE=` as unset instead of a parse error; `hide_input_in_errors=True` stops Pydantic from echoing the raw input dict (which would include `DATABASE_URL` with its password) in the startup error [VERIFIED: with it off the error text contained `input_value={...}`; with it on a password set in `DATABASE_URL` was absent from the whole uvicorn output, grep count 0].
```python
# config.py  -- executed in scratch (see Sources); every behaviour below was observed
from functools import lru_cache
from typing import Optional
from pydantic import SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class ConfigurationError(RuntimeError):
    """Raised at startup when required configuration is missing or invalid."""

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", env_ignore_empty=True, hide_input_in_errors=True)
    gnews_api_key: Optional[SecretStr] = None
    demo_mode: bool = False                      # default false (FND-03)
    bluesky_handle: Optional[str] = None         # optional until Phase 3 (D-08)
    bluesky_app_password: Optional[SecretStr] = None
    database_url: Optional[SecretStr] = None

    @model_validator(mode="after")
    def _key_required_unless_demo(self) -> "Settings":
        if not self.demo_mode and self.gnews_api_key is None:
            raise ValueError("GNEWS_API_KEY is required unless DEMO_MODE=true")
        return self

@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'settings'}: {e['msg']}" for e in exc.errors())
        raise ConfigurationError(f"Invalid configuration ({problems}). See .env.example.") from None
```
Observed: `DEMO_MODE` accepts `true/TRUE/1/yes` -> True; `maybe` raises (fail-fast); `.env` loads; a real environment variable beats `.env`; `repr(settings)` shows `SecretStr('**********')`; a whitespace-only key `"   "` is NOT treated as missing unless you add `.strip()` logic (my first prototype did; the lean version above does not - add a `field_validator` that strips and maps `""` to `None` if wanted).

Lifespan (fail fast, verified exit code 3 and a clean message with no password in output):
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()          # raises ConfigurationError -> uvicorn "Application startup failed. Exiting."
    yield
app = FastAPI(title="TruthTrail API", description="...", lifespan=lifespan)
```
Handler obtains settings through `Depends(get_settings)`, so tests override with `app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, gnews_api_key="FAKE_TEST_KEY", demo_mode=False)`. **A plain `TestClient(app)` does not run the lifespan** (a request returned 200 with no key in my experiment); the fail-fast test must use `with TestClient(app):` inside `pytest.raises(ConfigurationError)`. Tests must also neutralise a developer's real `.env`: `monkeypatch.setitem(Settings.model_config, "env_file", None)` (verified) plus `monkeypatch.delenv` for the five names, then `get_settings.cache_clear()`.

A runtime `not_configured` problem (D-06 lists the code) is only reachable when the lifespan was bypassed; render `ConfigurationError` as HTTP 500 `code: not_configured` (Assumption A8).

### Pattern 2: Adapter raising typed errors (replaces `return []`)
`fetch_news(query, api_key)` takes the key as an argument (no module-level constant), sends it in the **`X-Api-Key` header** (GNews documents two auth ways: the `apikey` query parameter or the `X-Api-Key` header [CITED: docs.gnews.io/authentication]), uses `timeout=(3.05, 10)`, validates the payload with a Pydantic model, and raises `UpstreamError(status, code, detail, retry_after)`.

Why the header: `requests.HTTPError` text from `raise_for_status()` is `"401 Client Error: Unauthorized for url: https://gnews.io/api/v4/search?q=x&apikey=<KEY>"` and a `ConnectTimeout` message can carry the URL [VERIFIED: local `responses` experiment, `leaks_key=True` for 401/403/429/500 and for a timeout carrying a URL]. With the header, the same `HTTPError` text is `...for url: https://gnews.io/api/v4/search?q=x` (key absent) [VERIFIED]. Do both: header **and** never interpolate `str(exc)` into a body/log, and raise `from None`.

Executed against 23 scenarios; observed mapping (this is the table the tests encode):

| Scenario | Result | `code` |
|---|---|---|
| 200 + `{"articles":[...]}` (extra fields like description/image ignored) | OK | - |
| 200 + `{"totalArticles":0,"articles":[]}` | OK, 0 articles -> envelope `source_status:"empty"` | - |
| 401 | 502 | `upstream_unauthorized` |
| 403 | 502 | `upstream_forbidden` |
| 400, any other non-200 4xx, 500, 503 | 502 | `upstream_bad_response` |
| 429 (numeric `Retry-After` honoured, capped 3600; absent or HTTP-date -> 30) | 503 + `Retry-After` | `upstream_rate_limited` |
| `ConnectTimeout`, `ReadTimeout` | 503 + `Retry-After: 30` | `upstream_timeout` |
| `ConnectionError`, `SSLError`, other `RequestException` | 503 + `Retry-After: 30` | `upstream_unreachable` |
| 200 non-JSON, JSON list, missing `articles`, null/empty `title`, missing `source`, null `source.name`, unparseable or **naive** `publishedAt` | 502 | `upstream_bad_response` |

Ordering traps found: `requests.exceptions.ConnectTimeout` is a subclass of **both** `ConnectionError` and `Timeout` (MRO verified), so `except Timeout` must come before `except RequestException`; `requests.exceptions.JSONDecodeError` is itself a `RequestException`, so call `resp.json()` **outside** the transport `try` and catch `ValueError` separately (otherwise non-JSON becomes a 503 instead of the 502 D-07 requires).

GNews facts that shape the table [CITED: docs.gnews.io/error-handling, /authentication, /endpoints/search-endpoint, scraped 2026-10-11]: 400 = malformed request **including a missing/malformed key** ("You did not provide an API key"); 401 = well-formed key that matches no account; 403 = daily quota reached (reset 00:00 UTC) or subscription expired; 429 = rate limit (free plan 1 request/second); 500/503 = server/maintenance; error body is `{"errors": [...]}` or `{"errors": {"attr": "msg"}}`; `q` maximum is 200 characters (so the 200-character cap in FND-04 matches the provider); free plan = 100 requests/day, 12-hour data delay, truncated content; `nullable` parameter implies description/content/image can be null (title/publishedAt/source are the fields the code needs). D-07 locks 403 to 502 even though it usually means quota: keep 502 but use the distinct code `upstream_forbidden` and a detail that mentions "credentials, subscription or daily quota".

### Pattern 3: RFC 9457 problem+json for every error
`application/problem+json` with `type: "about:blank"` and `title` = the HTTP status phrase (RFC 9457 4.2.1: "When 'about:blank' is used, the title SHOULD be the same as the recommended HTTP status phrase for that code" [CITED: rfc-editor.org/rfc/rfc9457.html]; Python 3.13 `http.HTTPStatus(422).phrase` is `"Unprocessable Content"`, 502 `"Bad Gateway"`, 503 `"Service Unavailable"` [VERIFIED: local]). RFC also says a member whose value type does not match the spec MUST be ignored, so keep `status` an integer. `detail` is for humans; clients branch on `code`.

Handlers to register (all executed):
1. `UpstreamError` -> status/code/detail from the exception, `upstream: "gnews"`, `Retry-After` header when set.
2. `RequestValidationError` -> 422, `code: "invalid_request"`, `errors` = list of `{loc, msg, type}` only. **Strip `input`, `ctx`, `url`**: FastAPI's default 422 body echoes the offending input, so a 5,000-character query comes back at 5,000+ characters and control characters are reflected; stripped, the oversize case returned a 242-byte body [VERIFIED].
3. `starlette.exceptions.HTTPException` (not FastAPI's subclass - FastAPI docs say to register on Starlette's [CITED: fastapi.tiangolo.com/tutorial/handling-errors/]) -> covers 404 and 405 so *every* error has one shape. **Forward `exc.headers`**, otherwise a 405 loses its `Allow` header (my first handler did; verified).
4. `Exception` -> 500 `code: "internal_error"`, generic detail (never `str(exc)`). Notes: the response is built by `ServerErrorMiddleware`, which sits outside `CORSMiddleware`, so these 500s carry no CORS headers (Phase 2 concern); and `TestClient` re-raises server exceptions by default - tests of this handler need `TestClient(app, raise_server_exceptions=False)`.

OpenAPI declaration of error responses - `responses={...}` with `"model": Problem` **plus** an explicit `content` for `application/problem+json` produced both media types referencing the one `Problem` component schema (bare `"content": {PROBLEM: {}}` produced an *empty* schema for problem+json, the trap) [VERIFIED]. Declare 422/502/503 (and `Retry-After` header on 503) on the route:
```python
PROBLEM = "application/problem+json"
_REF = {"schema": {"$ref": "#/components/schemas/Problem"}}
PROBLEM_RESPONSES = {
    422: {"model": Problem, "description": "Invalid request", "content": {PROBLEM: _REF}},
    502: {"model": Problem, "description": "Upstream answered badly", "content": {PROBLEM: _REF}},
    503: {"model": Problem, "description": "Upstream unreachable or throttling",
          "headers": {"Retry-After": {"description": "Seconds to wait", "schema": {"type": "integer"}}},
          "content": {PROBLEM: _REF}},
}
```
FastAPI keeps `HTTPValidationError`/`ValidationError` in `components.schemas` even after the 422 override [VERIFIED]; harmless (the copy guard sees only neutral strings).

### Pattern 4: Envelope and models (reuse `Event`)
`models.Event` has exactly the seven keys the simulator emits (`event_id, platform, content_id, parent_event_id, user_id, timestamp, user_influence`); `Event(**e)` validated all 19 events of a High-risk run, and `set(Event.model_fields) == set(root_event.keys())` is true [VERIFIED: local, models.py:4-11]. CONTEXT's "fields differ slightly" is **not** the case; reuse `Event` unchanged (note `parent_event_id: Optional[str]` has no default, so it must be passed explicitly, `None` for the root).

Verbatim source, `models.py:4-11`:
```
class Event(BaseModel):
    event_id: str
    platform: str
    content_id: str
    parent_event_id: Optional[str]
    user_id: str
    timestamp: str
    user_influence: int
```
Recommended models (executed; `extra="forbid"` makes the union unambiguous; returning model instances **or** a dict loaded from the fixture both serialise correctly - events present only on `DemoResult`):
```python
class _Result(BaseModel):
    model_config = ConfigDict(extra="forbid")
    headline: str; source: str; published_at: AwareDatetime
    risk: Literal["High", "Medium", "Low"]
    risk_method: Literal["keyword_baseline"]
class LiveResult(_Result): ...                       # NO events field at all (D-05)
class DemoResult(_Result):
    events: list[Event]
class Meta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    synthetic: bool
    data_as_of: AwareDatetime
    source_status: Literal["ok", "empty", "fixture"]
class AnalyzeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    results: list[DemoResult | LiveResult]
    meta: Meta
class Problem(BaseModel):
    type: str = "about:blank"; title: str; status: int; detail: str; code: str
    upstream: str | None = None
    errors: list[dict] | None = None
    synthetic: bool = False; source_status: str | None = None; data_as_of: None = None   # see Open Question 1
```
The generated OpenAPI shows `results.items.anyOf [DemoResult, LiveResult]` with no `null` branch; the alternative `events: list[Event] | None` + `response_model_exclude_unset=True` also omits the key correctly [VERIFIED], but advertises a nullable `events` that is never `null` (dishonest schema); `response_model_exclude_none=True` is wrong because it would drop any legitimately null field. `datetime.now(timezone.utc)` serialises with microseconds (`...33.595986Z`); use `.replace(microsecond=0)` for a stable `...Z` string. An `AwareDatetime` field rejects naive inputs and serialises UTC as `Z` [VERIFIED].

`data_as_of` semantics (discretion): live = the UTC instant the upstream response was received by this server (not the article time; each result carries its own `published_at`); demo = a constant stored in the fixture (generation instant), never "now" (otherwise a demo looks live). Document in the OpenAPI field description and README. GNews free plan articles lag ~12 h [CITED: docs.gnews.io], so `data_as_of` must not be described as "news is current as of".

### Pattern 5: Deterministic fixture generation
`random.seed(SEED)` fixes users and minute offsets but **not** `event_id`: `uuid.uuid4()` uses `os.urandom` (two runs with the same seed gave equal non-id fields and different `event_id`s) [VERIFIED]. A generator that patches `spread_simulator.uuid.uuid4` with a seeded `random.Random(...).getrandbits(128)` produced fully identical output across runs [VERIFIED]. The generator should (1) use fixed neutral synthetic headlines and sources ("Example Town Council approves ...", "Example News (synthetic)"), (2) compute `risk` via the real `analyze_risk`, (3) call the real simulator, (4) **post-process timestamps to a monotone parent<=child UTC `Z` form** (recommended; see Pitfall 4) and (5) write `meta = {synthetic: true, data_as_of: <constant>, source_status: "fixture"}` plus `risk_method`. Event counts: High -> 19 events (1 + 3 platforms x 6), Medium/Low -> 10 (1 + 3 x 3) [VERIFIED]. Keep it out of `data/` (D-10's ignore rule would drop it; `git check-ignore` verified `data/x.json` ignored, `fixtures/demo.json` tracked). Load the file with `Path(__file__).parent / "fixtures" / ...`, not a CWD-relative path, and validate it through `AnalyzeResponse` at load time.

### Pattern 6: Copy guard (script + pytest + OpenAPI walk)
See Code Examples. Design decisions, all executed: match against the *whole file text* with `\s+` between words so hard-wrapped Markdown can't dodge it; report the line from the match offset; allow marker `copy-guard: allow` honoured on any line of the match span **or the line immediately before**; walk every string leaf of `app.openapi()` (skipping `$ref`, `operationId`, `pattern`, `format`, `type`) so an enum value `FAKE`, a route docstring or a description is caught; require the literal positive phrase "flag ... for human review" in README.md; `FAKE` is matched case-sensitively with `\b` so `FAKE_TEST_KEY` (underscore is a word char) and prose "fake" do not trigger.

Executed result on the *current* README: two hits on line 2 - `ai-claim` ("AI-based") and `detects-misleading` ("detects potentially misleading content"). The latter is NOT in D-13's literal list; the "detects potentially misleading" rule is an addition (documented as such).

### Pattern 7: gitleaks scan script (working tree + validated range)
See Code Examples. Verified behaviour of gitleaks 8.30.1 (binary downloaded, sha256 matched the release `checksums.txt`):
- `gitleaks dir . --redact --no-banner --exit-code 1` scans the working tree; on a clone of this repo it reports exactly one finding (rule `generic-api-key`, `gnews_fetcher.py` line 3, secret shown as `REDACTED`) and exits 1; nothing in `.planning/` or `package-lock.json` is flagged.
- `gitleaks git . --log-opts="BASE..HEAD"` scans only commits in the range. Scanning `1fedcd2^..1fedcd2` -> exit 1; `1fedcd2..HEAD` -> exit 0; full history -> exit 1. So range scanning from any commit after `1fedcd2` implements D-09 ("pre-rotation history is not scanned") with **no baseline file**.
- A commit that only **removes** a secret does not trigger (removed lines are not scanned): scanning just the removal commit exit 0, whereas a range including the add commit exit 1 [VERIFIED with a throwaway high-entropy fake key]. So Phase 1's own "delete the literal" commit will not fail the build.
- **Fail-open:** `--log-opts` with an unknown revision or flag (`deadbeef..HEAD`, `HEAD~5..HEAD` in a 1-commit shallow clone, `--no-such-flag`) prints `ERR ... fatal: ambiguous argument` and **exits 0** [VERIFIED]. Therefore the script validates both endpoints with `git cat-file -e` and `git merge-base --is-ancestor` first, and CI must checkout with `fetch-depth: 0`.
- Entropy caveat: a random 32-hex assigned to `GNEWS_API_KEY` whose Shannon entropy was low (~3.4) was **not** flagged by `generic-api-key`, while a higher-entropy one was [VERIFIED]. gitleaks is a net, not a proof; keep the regex backstop test and `.env.example` names-only discipline.
- `# gitleaks:allow` inline suppression works [VERIFIED]. Fake placeholders: `"test-key-not-real"`, `"FAKE_GNEWS_KEY_FOR_TESTS_ONLY"`, `"dummy-key-for-tests"` were NOT flagged; a "realistic" `"<realistic-looking 32-hex placeholder, omitted here>"` assigned to `GNEWS_API_KEY` **was** flagged - so test tokens must be words like `FAKE_TEST_KEY`, never hex-looking strings (matches D-10). `.env.example` with names only (and a placeholder `DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/truthtrail`) produced no finding.
- Release: v8.30.1 published 2026-03-21 is "Latest" (13 assets) [CITED: github.com/gitleaks/gitleaks/releases]. The README states the tool is "feature complete", future releases are security patches only, and the author's focus is shifting to Betterleaks [CITED: github.com/gitleaks/gitleaks README] - low risk for this phase; note for Phase 2 review.
- `gitleaks detect`/`protect` are deprecated since v8.19.0 (hidden but present); use `dir` and `git` [CITED: README]. Flags used: `--redact` (default 100%), `--no-banner`, `--exit-code`, `-l`, `--log-opts` [VERIFIED via `--help`].
- Linux x64 asset sha256 (from the release's `gitleaks_8.30.1_checksums.txt`, matched by `sha256sum -c`): `551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb` for `gitleaks_8.30.1_linux_x64.tar.gz`.

`gitleaks-action@v3` (current major per its README example): no licence key is required for user accounts, only for organizations [CITED]; the repo remote is `https://github.com/areveeess/TruthTrail` (looks like a user account - Assumption A1, moot because the binary route is recommended).

### Pattern 8: Test infrastructure and network guard
```python
# tests/conftest.py (sketch; pieces executed)
import pytest, responses
from config import Settings, get_settings

FAKE_KEY = "FAKE_TEST_KEY"                       # words, not hex: gitleaks-safe (D-10)

@pytest.fixture(autouse=True)
def _no_real_network_and_clean_env(monkeypatch):
    # 1) hard network guard: any unmocked requests call raises ConnectionError
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rs:
        monkeypatch.setenv("TT_TEST_GUARD", "1")
        # 2) never read a developer's real .env or inherited secrets
        for name in ("GNEWS_API_KEY", "DEMO_MODE", "BLUESKY_HANDLE", "BLUESKY_APP_PASSWORD", "DATABASE_URL"):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setitem(Settings.model_config, "env_file", None)
        get_settings.cache_clear()
        yield rs
        get_settings.cache_clear()
```
`responses` registers GNews URLs on the same `rs` mock the fixture yields (expose it as `mock_gnews`). Unregistered URLs raise `ConnectionError("Connection refused by Responses - the call doesn't match any registered mock.")` [VERIFIED]. Put app construction and the GNews mocking in **one** fixture (`client_factory`, `mock_gnews`) so that Phase 2's package move and a possible `requests`->`httpx` switch touch one file (the Phase 2 success criterion says the characterization tests must pass "unchanged" - keep imports of `main`/`gnews_fetcher` out of test bodies).

### Anti-Patterns to Avoid
- **Module-level `GNEWS_API_KEY = os.environ[...]`:** import-time failure breaks test collection and defeats `DEMO_MODE`. Read settings lazily.
- **`str(exc)` / `exc.response.url` in any body or log line:** carries `apikey=` when the key is a query param.
- **`response_model=dict` / untyped return:** OpenAPI emits `schema: {}` (verified), which the walker test must reject.
- **`except requests.RequestException` around `.json()`:** misclassifies non-JSON as 503.
- **Using `exclude_none` to omit `events`:** drops any legitimately-null future field.
- **Putting the fixture under `data/`:** gitignored by D-10.
- **Adding the CI secret scan before the key literal is removed:** the working-tree scan fails until plan B lands.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Env parsing, bool coercion, `.env` loading, secret masking | `os.environ.get` + manual `"true"` compare | `pydantic-settings` | Typed bools (rejects `maybe`), `SecretStr` repr, `.env` precedence verified |
| Mocking HTTP for `requests` | monkeypatching `requests.get` with fakes | `responses` | Reproduces real exception text, headers, MRO, blocks unregistered URLs |
| Secret scanning | A bespoke regex scanner as the primary control | gitleaks (binary, pinned) | 100+ maintained rules, entropy, git-history range support; keep only a tiny regex backstop test |
| RFC 9457 body type | a new ad-hoc error dict per call site | One `Problem` model + one builder function used by all handlers | Single shape across upstream, validation, 404/405, 500 |
| Query validation | `if not query or len(query) > 200` in the handler | `Annotated[str, StringConstraints(...)]` on `Query` | Produces the 422 path and the OpenAPI `minLength/maxLength/pattern` for free |
| OpenAPI walking | Parsing FastAPI internals | `TestClient(app).get("/openapi.json").json()` | Tests the contract clients see |
| Datetime formatting | `strftime` + manual `Z` | `AwareDatetime` + `.replace(microsecond=0)` | Rejects naive inputs, serialises UTC as `Z` |

**Key insight:** every item here fails in subtle, security-relevant ways when hand-rolled (URL leakage in exception text, echoing input in 422 bodies, secrets in startup errors); each library behaviour above was checked by running it.

## Common Pitfalls

### Pitfall 1: Characterization tests call the real API with the real key
**What goes wrong:** the tests must be committed *before* the key is removed; `gnews_fetcher.py` still hard-wires the live key and its guard never fires (lines 3 and 6; the guard compares a string literal, so it is always "present"). Any unmocked request goes to `gnews.io`. **It happened once during this research:** an unmocked `/analyze` call was issued from a scratch script; the egress proxy rejected the CONNECT to `gnews.io:443` (proxy status shows `connect_rejected` for that host), so it never reached GNews - but in CI or on a developer laptop it would. **How to avoid:** the autouse `responses` guard above is the *first* file of the first plan; add a test `test_unmocked_request_is_blocked` asserting `requests.get("https://example.org")` raises `ConnectionError`. **Warning signs:** a test passes without registering a mock.

Current `/analyze` behaviour pinned by the executed experiment (mocked via `responses`, `TestClient(raise_server_exceptions=False)`):

| Upstream | Current result |
|---|---|
| 200 + one article | 200 list `[{"headline","risk","events"}]` with 19 (High) or 10 events |
| 200 + `articles: []` | **200 with a fabricated "unknown"/`2025-01-01T10:00:00Z` article** (headline = the query, `risk` "Medium") |
| 401, 403, 429 (JSON `errors` body) | **200 with the same fabricated article** (the headline defect) |
| 500 html, 200 non-JSON, null title, missing source, bad date, timeout | 500 `Internal Server Error` (plain text) |
| empty `query=` | reaches upstream (no validation) |

### Pitfall 2: Pydantic/pydantic-settings errors leak secrets
Default `ValidationError` text includes `input_value={...}` of the whole settings input; a missing news key plus a set `DATABASE_URL` would print the DB password to the startup log. Use `hide_input_in_errors=True` *and* re-raise a `ConfigurationError` built from `loc`/`msg` only (both verified).

### Pitfall 3: `uuid4` ignores `random.seed`
Golden/regeneration tests cannot compare `event_id`s. Characterization tests assert structure (counts, parent linkage, platforms, field set) and compare the non-id fields under a seed; only the generator patches `uuid4`. Use `monkeypatch.setattr(spread_simulator.uuid, "uuid4", ...)` (this patches the shared `uuid` module attribute; monkeypatch restores it). Also seed/restore the *global* `random` state in a fixture (`random.seed(n)`; `random.setstate(old)`).

### Pitfall 4: The simulator's timestamps are wrong in a way a demo will display
Child time = `base + randint(5,60)` minutes, independent of its parent: a child precedes its parent in 1479/3600 links (41%) over 200 seeds [VERIFIED]. Root timestamp keeps the upstream `Z` form; children are naive `isoformat()` strings (`...T09:42:00`) - mixed formats in one list. D-12 pins this as an `xfail(strict)` defect. For the *fixture* the generator should enforce monotone, UTC-`Z` timestamps (post-process; the simulator stays untouched) and a persistent fixture test should assert "no child earlier than its parent" and "all timestamps parse as UTC". `fromisoformat` also raises on garbage (`ValueError`) and `KeyError` on a missing key - irrelevant after D-05 removes the simulator from the live path, which is why the adapter, not the simulator, must validate `publishedAt`.

### Pitfall 5: Known-defect inventory for the golden table and xfail tests
Executed against the current `analyze_risk` (values copied from the run):

| Headline | Actual | Why |
|---|---|---|
| "Council approves new secure parking scheme" | High | "secure" contains "cure" |
| "New studies show coffee is healthy" | High | "studies" contains "dies" |
| "Couple wins lottery" | High | "couple" contains "coup" |
| "Officials say deadline extended" | High | "deadline" contains "dead" |
| "Dead heat in the polls" | High | idiom matched as death |
| "Elon Musk opens a bakery", "Donald Trump signs bill" | High | hardcoded names (`risk_analyzer.py:14`) |
| "Trump to visit India" | Medium | only the full name "donald trump" is listed - inconsistent |
| "Official statement confirms budget", "Study finds walking is good" | Low | stable |
| "Police confirm death of suspect", "Mayor dies after long illness", "Doctors cure patient with new treatment", "Prediction: market crash unlikely, analysts say" | High | stable keyword hits (the last one is semantically negated - a defect, but pin as stable current behaviour or as xfail per D-12 discretion) |
| "Breaking: storm approaching coast", "Leaked memo shows plan", "Local bakery wins award", "", "Weather forecast for Tuesday" | Medium | medium keyword / default |
| `analyze_risk(None)` | `AttributeError` | null title crash (relevant to the 502 on null fields) |

High wins over Medium and Low (first match, order High -> Medium -> Low), so "Official statement confirms the death of ..." is High. Use `pytest.param(..., marks=pytest.mark.xfail(strict=True, raises=AssertionError, reason=...))` so only the assertion failure is excused (an `ImportError` would still fail). `xfail_strict = true` in `pytest.ini` and an XPASS then **fails** the run [VERIFIED: "[XPASS(strict)] would XPASS"] - which means the fix commit must remove the marker in the same commit (CONTEXT says "visible XPASS"; with strict it is a red build, by design).

### Pitfall 6: gitleaks range scan fails open (see Pattern 7)
Validate both ends of the range yourself; always `fetch-depth: 0`; script exits 2 on an invalid range [VERIFIED across 5 scenarios].

### Pitfall 7: Docstrings and route metadata become OpenAPI copy
FastAPI turns a route function's docstring into the operation `description`; the copy guard (which walks all OpenAPI strings) will see them. Write the app `title`/`description`/route `summary` deliberately and keep "flag for human review" wording there.

### Pitfall 8: `.gitignore` can swallow what you need
`.env.*` ignores `.env.example` unless `!.env.example` follows; `data/` ignores a fixture placed there. Both verified with `git check-ignore`. Also add `__pycache__/` immediately (a stray `__pycache__/` appeared in the repo root while researching and was removed).

### Pitfall 9: Query "malformed" needs a definition
`?query=a&query=b` is accepted (last value wins: `{'q': 'b'}`) [VERIFIED]. Define the 422 matrix explicitly: missing param, empty, whitespace-only (after strip), > 200 characters (200 Unicode characters accepted, 201 rejected), and control characters (`\x00`, `\n`, `\t` rejected by `pattern=r"^[^\x00-\x1f\x7f]+$"`). The control-character rule also prevents log injection.

## Code Examples

### Problem handlers (executed)
```python
# main.py excerpt
from http import HTTPStatus
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM = "application/problem+json"

def problem_body(status: int, detail: str, code: str, **ext) -> dict:
    return {"type": "about:blank", "title": HTTPStatus(status).phrase, "status": status,
            "detail": detail, "code": code, **ext}

@app.exception_handler(UpstreamError)
async def _upstream(request: Request, exc: UpstreamError):
    headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
    return JSONResponse(problem_body(exc.status, exc.detail, exc.code, upstream="gnews",
                                     synthetic=False, source_status="upstream_error", data_as_of=None),
                        status_code=exc.status, media_type=PROBLEM, headers=headers)

@app.exception_handler(RequestValidationError)
async def _invalid(request: Request, exc: RequestValidationError):
    errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]   # no input/ctx/url
    return JSONResponse(problem_body(422, "Request validation failed.", "invalid_request", errors=errors,
                                     synthetic=False, source_status="invalid_request", data_as_of=None),
                        status_code=422, media_type=PROBLEM)

@app.exception_handler(StarletteHTTPException)
async def _http(request: Request, exc: StarletteHTTPException):
    return JSONResponse(problem_body(exc.status_code, str(exc.detail), "http_error",
                                     synthetic=False, source_status="error", data_as_of=None),
                        status_code=exc.status_code, media_type=PROBLEM, headers=exc.headers)   # keep Allow on 405

@app.exception_handler(Exception)
async def _unexpected(request: Request, exc: Exception):
    return JSONResponse(problem_body(500, "Unexpected error.", "internal_error",
                                     synthetic=False, source_status="error", data_as_of=None),
                        status_code=500, media_type=PROBLEM)
```
Observed bodies: 401 -> `502 application/problem+json {"type":"about:blank","title":"Bad Gateway","status":502,"detail":"The news provider rejected our credentials.","code":"upstream_unauthorized","upstream":"gnews"}`; 503 carried `Retry-After: 30`; empty/whitespace/missing/oversize/malformed query -> 422 with `errors:[{"loc":["query","query"],"msg":"String should have at least 1 character","type":"string_too_short"}]`; 404/405 -> problem+json.

### Query constraint (executed)
```python
from typing import Annotated
from fastapi import Query
from pydantic import StringConstraints
SearchQuery = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200,
                                               pattern=r"^[^\x00-\x1f\x7f]+$")]

@app.get("/analyze", response_model=AnalyzeResponse, responses=PROBLEM_RESPONSES,
         summary="Keyword-baseline risk flags for recent headlines (flag for human review)")
def analyze(query: Annotated[SearchQuery, Query(description="Search keywords, 1-200 characters.")],
            settings: Annotated[Settings, Depends(get_settings)]) -> AnalyzeResponse: ...
```
OpenAPI parameter rendered as `{"type":"string","minLength":1,"maxLength":200,"pattern":"^[^\\x00-\\x1f\\x7f]+$"}`.

### Adapter core (executed against 23 scenarios)
```python
# gnews_fetcher.py
GNEWS_URL = "https://gnews.io/api/v4/search"
TIMEOUT = (3.05, 10)                 # (connect, read) seconds; read timeout is per socket read, not a total deadline
DEFAULT_RETRY_AFTER = 30

def fetch_news(query: str, api_key: str) -> list[dict]:
    try:
        resp = requests.get(GNEWS_URL, params={"q": query, "lang": "en", "max": 1},
                            headers={"X-Api-Key": api_key}, timeout=TIMEOUT)
    except requests.exceptions.Timeout:          # BEFORE RequestException: ConnectTimeout is both Timeout and ConnectionError
        raise UpstreamError(503, "upstream_timeout", "The news provider timed out.", DEFAULT_RETRY_AFTER) from None
    except requests.exceptions.RequestException:
        raise UpstreamError(503, "upstream_unreachable", "The news provider could not be reached.", DEFAULT_RETRY_AFTER) from None
    s = resp.status_code
    if s == 401: raise UpstreamError(502, "upstream_unauthorized", "The news provider rejected our credentials.")
    if s == 403: raise UpstreamError(502, "upstream_forbidden", "The news provider refused the request (credentials, subscription or daily quota).")
    if s == 429: raise UpstreamError(503, "upstream_rate_limited", "The news provider is rate limiting us.", _retry_after(resp))
    if s != 200: raise UpstreamError(502, "upstream_bad_response", "The news provider returned an unexpected status.")
    try:
        payload = _Payload.model_validate(resp.json())      # outside the transport try; ValueError = non-JSON
    except (ValueError, ValidationError):
        raise UpstreamError(502, "upstream_bad_response", "The news provider returned an unreadable response.") from None
    return [{"title": a.title, "source": a.source.name, "published_at": a.publishedAt} for a in payload.articles]
```
with `_Article(title: str(strip,min 1), source: _Source(name: str min 1), publishedAt: AwareDatetime)`, `extra="ignore"`, and `_retry_after` = numeric header capped at 3600 else 30. Key stays in the header; query goes through `params=` (URL-encoded; the user cannot inject extra parameters).

### Mocking an upstream scenario (executed)
```python
@pytest.mark.parametrize("kw,status,code", [
    (dict(status=401, json={"errors": ["Invalid API Key provided."]}), 502, "upstream_unauthorized"),
    (dict(status=403, json={"errors": ["quota"]}), 502, "upstream_forbidden"),
    (dict(status=429, json={}, headers={"Retry-After": "7"}), 503, "upstream_rate_limited"),
    (dict(status=500, body="oops"), 502, "upstream_bad_response"),
    (dict(status=200, body="<html>"), 502, "upstream_bad_response"),
    (dict(body=requests.exceptions.ConnectTimeout("t")), 503, "upstream_timeout"),
    (dict(body=requests.exceptions.ConnectionError("c")), 503, "upstream_unreachable"),
])
def test_upstream_failures_are_honest(client, mock_gnews, caplog, kw, status, code):
    mock_gnews.add(responses.GET, GNEWS_URL, **kw)
    r = client.get("/analyze", params={"query": "x"})
    assert r.status_code == status and r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["code"] == code and "results" not in r.json()
    assert FAKE_KEY not in r.text and FAKE_KEY not in caplog.text and "gnews.io" not in r.text
def test_gnews_401_returns_502_not_200(...): ...    # the named test required by D-07 / success criterion 2
```

### OpenAPI walker (executed; passes on a typed app, flags `{}` and `dict` schemas)
```python
HTTP_METHODS = {"get", "put", "post", "delete", "patch", "options", "head"}
def _resolve(spec, node):
    while isinstance(node, dict) and "$ref" in node:
        node = spec["components"]["schemas"][node["$ref"].rsplit("/", 1)[-1]]
    return node

def test_every_operation_has_typed_2xx_response(spec):
    ops = [(p, m, o) for p, item in spec["paths"].items() for m, o in item.items() if m in HTTP_METHODS]
    assert ops
    for path, method, op in ops:
        twoxx = {c: r for c, r in op["responses"].items() if c.startswith("2")}
        assert twoxx, f"{method.upper()} {path}: no 2xx response"
        for code, resp in twoxx.items():
            if code == "204": continue
            schema = _resolve(spec, resp["content"]["application/json"]["schema"])
            assert schema.get("properties") or schema.get("items") or schema.get("anyOf") or schema.get("oneOf") or schema.get("allOf"), \
                f"{method.upper()} {path} {code}: untyped schema"

def test_error_responses_are_problem_json(spec):
    for code in ("422", "502", "503"):
        assert "application/problem+json" in spec["paths"]["/analyze"]["get"]["responses"][code]["content"]
```
(An unannotated route returns `schema: {}`; `response_model=dict` returns `{"type":"object","additionalProperties":true}` - both rejected by the check [VERIFIED].)

### Copy guard core (executed; full prototype in scratchpad `cg/scripts/copy_guard.py`)
```python
BANNED = [
  ("truth-claim",           re.compile(r"\bdetect(s|ing|ion|or|ors)?\s+(of\s+)?(the\s+)?truth\b", re.I)),
  ("fake-news-detector",    re.compile(r"\bfake[\s-]+news\s+(detect\w*|classif\w*|identif\w*)\b", re.I)),
  ("detects-misinformation",re.compile(r"\b(detect(s|ing)?|identif(y|ies|ying))\s+(and\s+\w+\s+)?(fake\s+news|misinformation|disinformation|fake\s+content|false\s+(claims?|information))\b", re.I)),
  ("detects-misleading",    re.compile(r"\bdetect(s|ing)?\s+(potentially\s+|possibly\s+)?(misleading|false|fake|fraudulent)\s+(content|claims?|posts?|news|information|stories)\b", re.I)),
  ("misinformation-detector",re.compile(r"\b(mis|dis)information\s+detect(or|ors|ion)\b", re.I)),
  ("ai-claim",              re.compile(r"\bAI[\s-]*(based|powered|driven|enabled)\b", re.I)),
  ("fake-verdict-label",    re.compile(r"\bFAKE\b")),          # case-sensitive: the badge, not the word
]
```
Sample results (executed): hard-wrapped "detects the\ntruth" flagged; "FAKE badge" flagged; prose "fake news are common" clean; `FAKE_TEST_KEY` clean; "This is not a fake news detector." flagged unless `<!-- copy-guard: allow -->` on the line or the line above; "AI-assisted" clean; "a misinformation early-warning system" and "Baseline Detection & Evaluation" clean; "prior work on misinformation detection" flagged (needs the marker - a Phase 4/6 README risk).

### gitleaks scan script (executed in 5 scenarios)
```bash
#!/usr/bin/env bash
# scripts/gitleaks_scan.sh <gitleaks-binary> <base_sha> <head_sha> <floor_sha>
set -euo pipefail
GL="$1"; BASE="$2"; HEAD_SHA="$3"; FLOOR="$4"
ZERO=0000000000000000000000000000000000000000
echo "== (a) working tree"
"$GL" dir . --redact --no-banner --exit-code 1 -l warn
if [ "$BASE" = "$ZERO" ] || ! git cat-file -e "${BASE}^{commit}" 2>/dev/null; then
  echo "base unusable (new branch / force-push); falling back to floor ${FLOOR}"; BASE="$FLOOR"
fi
git cat-file -e "${BASE}^{commit}"     || { echo "ERROR: range base not found"; exit 2; }
git cat-file -e "${HEAD_SHA}^{commit}" || { echo "ERROR: range head not found"; exit 2; }
git merge-base --is-ancestor "$BASE" "$HEAD_SHA" || { echo "ERROR: base is not an ancestor of head"; exit 2; }
echo "== (b) commit range ${BASE:0:7}..${HEAD_SHA:0:7} ($(git rev-list --count "${BASE}..${HEAD_SHA}") commits)"
"$GL" git . --redact --no-banner --exit-code 1 -l warn --log-opts="${BASE}..${HEAD_SHA}"
echo "gitleaks: clean"
```
Observed: removal-only range -> clean (exit 0); range including the add -> exit 1; zero/bogus `before` -> falls back to the floor; missing floor -> exit 2. **Floor value:** `a5dd8257e920923677c60e70611a6f36d87747b2` (current HEAD; every commit after it is scanned on new-branch/force-push pushes; `1fedcd2` is an ancestor of it and therefore never scanned, satisfying D-09 without a baseline file). If the owner ever purges history (deferred, D-11) the floor SHA vanishes and the script exits 2 loudly - update the constant then. The binary must live outside the workspace (`$RUNNER_TEMP`), otherwise `dir .` scans the downloaded archive.

### Workflow (script-level pieces executed; the YAML itself was not run - no runner access, Assumption A6)
```yaml
name: ci
on:
  push:
  pull_request:
permissions:
  contents: read
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
jobs:
  copy-guard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version: "3.13"
          cache: pip
          cache-dependency-path: requirements.txt
      - run: pip install -r requirements.txt
      - run: python scripts/copy_guard.py
  gitleaks:
    runs-on: ubuntu-latest
    env:
      GITLEAKS_VERSION: "8.30.1"
      GITLEAKS_SHA256: "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"
      RANGE_FLOOR: "a5dd8257e920923677c60e70611a6f36d87747b2"
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 0
      - name: Install gitleaks (pinned + checksum verified)
        run: |
          set -euo pipefail
          url="https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz"
          curl -sSfL -o "$RUNNER_TEMP/gl.tgz" "$url"
          echo "${GITLEAKS_SHA256}  $RUNNER_TEMP/gl.tgz" | sha256sum -c -
          mkdir -p "$RUNNER_TEMP/gl" && tar -xzf "$RUNNER_TEMP/gl.tgz" -C "$RUNNER_TEMP/gl" gitleaks
      - name: Scan working tree + commit range
        env:
          EVENT_NAME: ${{ github.event_name }}
          PUSH_BEFORE: ${{ github.event.before }}
          PUSH_AFTER: ${{ github.sha }}
          PR_BASE: ${{ github.event.pull_request.base.sha }}
          PR_HEAD: ${{ github.event.pull_request.head.sha }}
        run: |
          if [ "$EVENT_NAME" = "pull_request" ]; then BASE="$PR_BASE"; HEAD_SHA="$PR_HEAD"; else BASE="$PUSH_BEFORE"; HEAD_SHA="$PUSH_AFTER"; fi
          bash scripts/gitleaks_scan.sh "$RUNNER_TEMP/gl/gitleaks" "$BASE" "$HEAD_SHA" "$RANGE_FLOOR"
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version: "3.13"
          cache: pip
          cache-dependency-path: requirements-dev.txt
      - run: pip install -r requirements-dev.txt
      - run: python -m pytest -q
```
Action pins: `actions/checkout` v7.0.1 (commit `3d3c42e5aac5ba805825da76410c181273ba90b1`, released 20 Jul) and `actions/setup-python` v7.0.0 (commit `5fda3b95a4ea91299a34e894583c3862153e4b97`, released 20 Jul) [CITED: github.com/actions/checkout/releases/tag/v7.0.1, github.com/actions/setup-python/releases/tag/v7.0.0; the SHAs were read from the release pages, not cross-checked with `git ls-remote`]. setup-python v7 notes: ESM migration, removed the `pip-install` input (unused here); v6 required runner >= v2.327.1 (hosted runners satisfy it). The repo's gitleaks-action README example also uses `actions/checkout@v6` with `fetch-depth: 0`. Using `@v7` tags instead of SHAs is acceptable but SHAs are the supply-chain-safe pin.

### Credential backstop test (executed: matches only `gnews_fetcher.py:3`)
```python
rx = re.compile(r'''(?i)(api[_-]?key|passw(or)?d|secret|token)\s*[:=]\s*["'][A-Za-z0-9_\-./+]{16,}["']''')
# iterate `git ls-files`, skip tests/ and .planning/, *.py/*.md/*.json/*.yml/*.toml/*.txt/*.ini, skip package-lock.json
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| RFC 7807 problem details | RFC 9457 (obsoletes 7807); same `application/problem+json` | 2023 | Same shape; cite 9457 |
| `httpx` as TestClient backend | Starlette 1.7 prefers `httpx2` (Pydantic org), warns on `httpx` | Starlette 1.7 / httpx2 first upload 2026-05-11 | Use `httpx2` in dev deps |
| `gitleaks detect` / `protect` | `gitleaks git` / `gitleaks dir` (old verbs hidden, deprecated v8.19.0) | 2024 | Use `dir` + `git` |
| `gitleaks-action` for everything | Binary + explicit `dir` and `git --log-opts` scans | - | Working-tree scan + checksum pin |
| 422 "Unprocessable Entity" | "Unprocessable Content" (RFC 9110; Python 3.13 phrase) | Python 3.13 | Title text follows `HTTPStatus` |

**Deprecated/outdated:** `pydantic.BaseSettings` (moved to the `pydantic-settings` package); relying on `httpx` for the Starlette test client; module-level secret constants.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The repo owner `areveeess` is a personal (non-org) account, so `gitleaks-action` would need no licence (moot - binary route recommended) | Pattern 7 | None for the recommended design; matters only if someone switches to the action |
| A2 | GNews returns `"articles": []` (not a missing key) for zero matches, so a missing `articles` key can be treated as malformed (502). The docs sample responses were not seen; the old code used `data.get("articles", [])` | Pattern 2 | A zero-result query would 502. Mitigation: accept a missing `articles` only when `totalArticles == 0`, and keep the test table explicit; confirm with owner when a real key is available |
| A3 | `data_as_of` for live responses = server receive time (UTC, second precision); for demo = the fixture's constant | Pattern 4 | Wording/semantic change only; documented in README + OpenAPI |
| A4 | Error (problem+json) bodies also carry `synthetic: false`, `source_status`, `data_as_of: null` so that "every response" in FND-03 is satisfied literally | Pattern 3 / Open Question 1 | If the owner wants problem bodies pure RFC-9457, drop three keys; the test and model change is trivial |
| A5 | `DEMO_MODE=true` ignores the query and returns the entire fixture (query is still validated) | Pattern 5 | Demo UX only |
| A6 | The GitHub Actions workflow YAML is syntactically/semantically right but was **not executed** (no runner; the GitHub API/`gh` is blocked in this sandbox); only the scripts and commands inside it were executed locally | Code Examples | First push may need a one-line fix; plan a "CI green" human-verify at the end of the phase |
| A7 | Seed value and the fixture's `data_as_of` constant are arbitrary (any fixed values work) | Pattern 5 | None |
| A8 | A runtime `ConfigurationError` (lifespan bypassed) renders as HTTP 500 `code: not_configured` | Pattern 1 | Could instead be 503; D-06 lists the code but no D-07 status |
| A9 | The 20 Jul releases of `actions/checkout` v7.0.1 / `setup-python` v7.0.0 are still the latest majors and their commit SHAs are as printed on the release pages | Code Examples | A wrong SHA fails the workflow loudly at start; re-read the release pages at execution time |
| A10 | Free-plan GNews 12-hour data delay and 100 requests/day limits are current | Pattern 4 | Wording in README/OpenAPI only |

## Open Questions

1. **Do error responses carry the provenance trio (FND-03 says "every API response")?**
   - What we know: D-06 defines the problem body as `type/title/status/detail/code/upstream`; ROADMAP criterion 3 says "Every API response carries `synthetic`, `data_as_of` and `source_status`".
   - What's unclear: whether errors are in scope of that sentence.
   - Recommendation: add `synthetic: false`, `source_status` (`upstream_error` / `invalid_request` / `error`) and `data_as_of: null` as RFC-9457 extension members (cheap, compatible). If the owner prefers pure problem bodies, restrict the FND-03 test to 2xx responses and say so in the plan.

2. **GNews 400 for a user-supplied query syntax error** (unbalanced quotes/operators, `q` syntax error) is mapped to 502 `upstream_bad_response` (D-07 only lists 401/403/5xx/non-JSON/malformed). Recommendation: keep 502 in Phase 1; revisit when `/analyze` is retired or reduced in Phase 3.

3. **Does the live `/analyze` keep `max=1`?** Current code requests one article (free plan allows up to 10). Recommendation: keep `max=1` (behaviour-preserving, minimises quota use); the envelope already supports a list.

4. **Pin style for GitHub Actions:** SHA pins (recommended) vs `@v7` tags. SHA pins need a refresh routine; Phase 2 can add Dependabot for `github-actions`.

5. **Phase 2 coupling:** `responses` only mocks `requests`; if Phase 2 swaps the adapter to `httpx`/`httpx2`, the single `mock_gnews` fixture is the only place to change - provided Phase 1 keeps all mocking behind it.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | everything | yes | 3.13.16 | - |
| pip | installs | yes | 24.0 | uv |
| uv | clean venvs | yes | 0.11.32 | pip + venv |
| git | scan scripts | yes | 2.43.0 | - |
| Node | not needed in Phase 1 | yes | v22.22.0 | - |
| Docker | not needed in Phase 1 | yes | 29.8.2 | - |
| gitleaks | local secret scan | **no (not installed)**; release binary downloadable here | 8.30.1 | `scripts/gitleaks_scan.sh` with the same checksum-verified download into a temp dir |
| GitHub API / `gh` for this repo | verifying CI runs | **no** (403 "GitHub access to this repository is not enabled for this session") | - | CI is verified after the owner's push (human-verify) |
| Outbound to `gnews.io`, `docs.gnews.io`, `rfc-editor.org`, `fastapi.tiangolo.com` | docs/live API | blocked by the egress proxy for direct fetch (docs read via Firecrawl) | - | Tests never call GNews; docs already captured |

**Missing dependencies with no fallback:** none for planning/execution; a green GitHub Actions run can only be confirmed after a push.
**Missing dependencies with fallback:** local gitleaks (download in a temp dir or use the script).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 + responses 0.26.3 + httpx2 2.13.1 (TestClient) |
| Config file | `pytest.ini` (Wave 0 creates it; none exists today) |
| Quick run command | `python -m pytest -q -x tests/<file>.py` |
| Full suite command | `python -m pytest -q` (all tests, `xfail_strict`, `filterwarnings=error`) |
| Non-pytest gates | `python scripts/copy_guard.py` ; `bash scripts/gitleaks_scan.sh <gitleaks-bin> <base> HEAD <floor>` |

### Phase Requirements -> Test Map
| Req ID / Success criterion | Behavior | Test Type | Automated Command | File Exists? |
|---|---|---|---|---|
| FND-01 / SC1 | no credential literal in tracked source | unit (regex backstop) | `python -m pytest -q tests/test_no_hardcoded_credentials.py` | Wave 0 |
| FND-01 / SC1 | gitleaks working tree clean | CI + local | `bash scripts/gitleaks_scan.sh ...` (exit 0) | Wave 0 |
| FND-01 / SC1 | missing key -> explicit config error at startup; `DEMO_MODE=true` starts without key; bad `DEMO_MODE` value fails | unit | `python -m pytest -q tests/test_settings.py` (uses `with TestClient(app)` + `pytest.raises(ConfigurationError)`) | Wave 0 |
| FND-01 | `.env.example` lists exactly the five names, no values; `.env.example` is tracked, `.env` ignored | unit | `tests/test_settings.py::test_env_example_names_only` (parse file; `git check-ignore`) | Wave 0 |
| FND-02 / SC2 | **GNews 401 -> 502 problem+json, not 200** (named test) | integration | `python -m pytest -q tests/test_upstream_errors.py::test_gnews_401_returns_502_not_200` | Wave 0 |
| FND-02 | 403/429(+Retry-After)/500/timeout/ConnectionError/non-JSON/null-field -> mapped status+code; never `results`; key/URL absent from body and `caplog` | integration (parametrized, `responses`) | `python -m pytest -q tests/test_upstream_errors.py` | Wave 0 |
| FND-03 / SC3 | every 2xx carries `synthetic`,`data_as_of` (UTC `Z`),`source_status`; live has no `events` key; empty -> 200 `source_status:"empty"` | integration | `python -m pytest -q tests/test_provenance_demo.py` | Wave 0 |
| FND-03 | `DEMO_MODE` unset/false: fixture loader is never called (monkeypatch it to raise) even when upstream fails | integration | same file | Wave 0 |
| FND-03 | `DEMO_MODE=true`: `synthetic: true`, `source_status:"fixture"`, `events` present, no network call (unmocked guard stays silent) | integration | same file | Wave 0 |
| FND-03 | committed fixture validates through `AnalyzeResponse`; child never earlier than parent; timestamps UTC; regenerating with the seed reproduces it byte-for-byte | unit | `tests/test_provenance_demo.py::test_fixture_*` (regeneration test uses `pytest.importorskip("spread_simulator")` - Phase 2 deletes it) | Wave 0 |
| FND-04 / SC4 | empty, whitespace-only, 201 chars, control chars, missing -> 422 problem+json with `errors`, body size bounded (no input echo) | integration | `python -m pytest -q tests/test_validation_openapi.py` | Wave 0 |
| FND-04 / SC4 | OpenAPI walker: every operation has a typed 2xx schema; 422/502/503 declared as problem+json | contract | same file | Wave 0 |
| FND-05 / SC5 | `analyze_risk` golden table (stable rows) + `xfail(strict)` defect rows; simulator invariants (counts 19/10, linkage, platforms, seed-determinism of non-id fields) + `xfail(strict)` child-before-parent | unit | `python -m pytest -q tests/test_char_risk_analyzer.py tests/test_char_simulator.py` | Wave 0 (committed FIRST) |
| FND-05 | legacy list-shape `/analyze` (incl. the 200-with-fabricated-article defects as `xfail(strict)` desired-behaviour tests) | integration | `python -m pytest -q tests/test_char_analyze_legacy.py` | Wave 0; deleted/replaced when D-01 lands |
| FND-05 | unmocked `requests` call is blocked | unit | `tests/test_char_analyze_legacy.py::test_unmocked_request_is_blocked` (or conftest self-test) | Wave 0 |
| FND-06 / SC5 | banned phrases fail; allow marker works; README contains the required phrase; OpenAPI strings clean; self-test fixtures prove each rule fires | unit | `python -m pytest -q tests/test_copy_guard.py` and `python scripts/copy_guard.py` | Wave 0 |
| FND-06 / SC5 | CI workflow runs copy guard + gitleaks + pytest green on the pushed branch | manual (post-push) | open the Actions run for the pushed commit | n/a (human-verify at end of phase) |

### Sampling Rate
- **Per task commit:** `python -m pytest -q -x tests/<affected file>`
- **Per wave merge:** `python -m pytest -q` plus `python scripts/copy_guard.py`
- **Phase gate:** full suite green, `copy_guard.py` exit 0, local gitleaks script exit 0 against `FLOOR..HEAD`, then CI run green after push, before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `pytest.ini`, `requirements.txt` (pinned + `pydantic`, `pydantic-settings`), `requirements-dev.txt`
- [ ] `tests/conftest.py` (network guard, env scrub, `client_factory`, `mock_gnews`) - **first commit of the phase**
- [ ] `tests/test_char_risk_analyzer.py`, `tests/test_char_simulator.py`, `tests/test_char_analyze_legacy.py` (committed before any behavioural change)
- [ ] All other test files listed above, `scripts/copy_guard.py`, `scripts/gitleaks_scan.sh`, `scripts/generate_demo_fixture.py`
- [ ] Framework install: `python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt` (or `uv venv` + `uv pip install -r requirements-dev.txt`)

## Security Domain

Config: `security_enforcement` true, ASVS level 1, block on high.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (no user auth in this service) | - |
| V3 Session Management | no | - |
| V4 Access Control | no (public read endpoint; CORS `*` is Phase 2/ENG-06) | - |
| V5 Input Validation | yes | Pydantic `StringConstraints` (strip, 1..200, control-char pattern) -> 422 before any upstream call; strict upstream-payload model |
| V6 Cryptography | no hand-rolled crypto | `requests` default TLS verification (never `verify=False`) |
| V7 Error Handling and Logging | yes | problem+json with generic `detail`; `from None`; never `str(exc)`/URL/key in bodies or logs; `caplog` assertion |
| V8 Data Protection | yes | `SecretStr`; key sent in `X-Api-Key` header, not in URLs; `hide_input_in_errors=True` |
| V10 Malicious Code / V14 Configuration | yes | env-only secrets, `.env*` ignored, gitleaks (pinned + checksum), pinned requirements, SHA-pinned actions, `permissions: contents: read` |
| V12/V13 API | yes | typed response models; no unversioned untyped dicts |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| API key in outbound URL echoed via exception text (`HTTPError`, `ConnectTimeout`) | Information disclosure | Header auth + generic messages + `from None` (verified leak, verified fix) |
| 422 body reflects attacker-controlled input (size + log injection) | Tampering / Info disclosure | Strip `input`/`ctx` from errors; control-char pattern; 200-char cap |
| Secrets printed in startup validation errors | Information disclosure | `hide_input_in_errors=True`; `ConfigurationError` from `loc`/`msg` only (verified) |
| Unmocked tests call the live provider with a live key | Information disclosure / Denial of service (quota) | Autouse `responses` guard; key removed in plan B |
| Committed secret later deleted | Information disclosure | gitleaks range scan (add commit detected even after removal); regex backstop |
| gitleaks silently skipped on bad range | Tampering (control bypass) | Validate range endpoints; exit 2; `fetch-depth: 0` |
| Compromised CI download/action | Tampering (supply chain) | Checksum-verified binary; SHA-pinned actions; least-privilege `permissions` |
| Request without timeout hangs workers | Denial of service | `timeout=(3.05, 10)` |
| Query injection into the provider URL | Tampering | Query passed via `params=` (URL-encoded); fixed URL (no SSRF) |
| Demo data mistaken for live | Spoofing (of provenance) | `synthetic: true` + `source_status: "fixture"` + `DEMO_MODE` default false, tested |

## Sources

### Primary (HIGH confidence)
- Local executions this session (Python 3.13.16, clean uv venvs): FastAPI 0.143.0 / Starlette 1.7.0 / pydantic 2.14.0 / pydantic-settings 2.15.0 / responses 0.26.3 / pytest 9.1.1 / requests 2.34.2 / uvicorn 0.54.0 / httpx2 2.13.1 - handler, OpenAPI, settings, adapter, copy-guard and gitleaks experiments quoted above.
- gitleaks 8.30.1 binary: SHA-256 checked against `gitleaks_8.30.1_checksums.txt` downloaded from the GitHub release; `--help` output for `dir` and `git`.
- Starlette installed source `starlette/testclient.py` lines 31-48 (httpx2 preference).
- `pip index versions` and `pypi.org/pypi/<pkg>/json` (first upload dates).
- In-repo files read this session with the Read tool: `main.py` (1-41), `gnews_fetcher.py` (7-28; lines 3 and 6 deliberately not quoted), `risk_analyzer.py` (1-30, remainder executed), `spread_simulator.py` (1-39), `models.py` (1-11), `users.py` (1-15), `requirements.txt` (1-3), `README.md` (1-2).
- https://docs.gnews.io/error-handling, /authentication, /endpoints/search-endpoint, / (Firecrawl scrape, 2026-10-11).
- https://www.rfc-editor.org/rfc/rfc9457.html (title / `about:blank` rule; type-mismatch members MUST be ignored).
- https://fastapi.tiangolo.com/tutorial/handling-errors/ (register on Starlette's `HTTPException`; `RequestValidationError` override).
- https://github.com/gitleaks/gitleaks and /releases (v8.30.1, 2026-03-21; deprecations; "feature complete" note).

### Secondary (MEDIUM confidence)
- https://github.com/gitleaks/gitleaks-action README (licence only for organizations; v3; example with `fetch-depth: 0`).
- https://github.com/actions/checkout/releases/tag/v7.0.1 and https://github.com/actions/setup-python/releases/tag/v7.0.0 (commit SHAs, notes).
- https://github.com/pydantic/httpx2 README (stewardship statement).

### Tertiary (LOW confidence)
- None relied upon.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - versions read from the index today and the set installed/ran together on 3.13.
- Architecture/patterns: HIGH - each pattern executed in scratch code; only the workflow YAML is unexecuted (Assumption A6).
- Pitfalls: HIGH - each was reproduced (URL-leak, fail-open gitleaks, uuid4 seeding, 41% child-before-parent, 200-with-fabricated-article, ConnectTimeout MRO).
- GNews behaviour: MEDIUM-HIGH - docs read; zero-result payload shape unseen (A2); no live calls were (or may be) made.

**Research date:** 2026-10-11
**Valid until:** 2026-11-10 (fast-moving: FastAPI/Starlette/httpx2/GitHub Actions majors; re-check action SHAs and gitleaks release at execution time)
