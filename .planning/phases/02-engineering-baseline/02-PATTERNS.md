# Phase 2: Engineering Baseline - Pattern Map

**Mapped:** 2026-10-17
**Files analyzed:** 50 (11 moved, 9 modified in place, 30 new)
**Analogs found:** 46 in-repo analogs / 50. Unlike Phase 1, the repo now has Phase 1 code, tests, scripts and CI to copy from. Only 4 files have no in-repo analog: `pyproject.toml`/`uv.lock`, `Dockerfile`/`.dockerignore`, `core/cascade.py`, the slowapi `LimitedRouter`. For those the source is the cited 02-RESEARCH.md Pattern.

All analog paths below are git-TRACKED at HEAD `01dfac5` (`git ls-files` confirmed for every root module, `tests/*`, `scripts/*`, `fixtures/demo_analyze.json`, `.github/workflows/ci.yml`, `.env.example`, `pytest.ini`, `requirements*.txt`). Line numbers refer to the pre-move files. Nothing in `src/`, `legacy/` or `pyproject.toml` exists yet.

**Secret handling:** never reproduce the old GNews key (history `1fedcd2`). Tests use the word token `FAKE_TEST_KEY` only. `gnews_fetcher.py` no longer contains a key literal.

## File Classification

### Moved (pure `git mv`, commit 2; no content edits)

| New location | Role | Data Flow | Old file | Edits needed in LATER commit |
|---|---|---|---|---|
| `src/truthtrail/services/gnews.py` | service/adapter | request-response (outbound) | `gnews_fetcher.py` | imports, retry loop, `Retry-After` clamp |
| `src/truthtrail/services/keyword_baseline.py` | service | transform | `risk_analyzer.py` | NONE (frozen, sha256 `7398c2cf...`) |
| `src/truthtrail/core/config.py` | config | startup | `config.py` | add CORS/proxy/rate-limit fields |
| `src/truthtrail/core/errors.py` | utility (error type + builder) | request-response | `problems.py` (`UpstreamError`, `problem_body`, `problem_response`) | split out of `problems.py` |
| `src/truthtrail/api/problems.py` | handler registration | request-response | `problems.py` (handlers, `PROBLEM_RESPONSES`) | imports, decorator-form handlers, 429 declaration |
| `src/truthtrail/schemas/models.py` | model | transform | `models.py` | `Problem.synthetic: Literal[False]`, `Optional` to `X \| None` (ruff UP045) |
| `src/truthtrail/api/analyze.py` + `app.py` | controller + app wiring | request-response | `main.py` | split into `create_app()`, route, fixture loader |
| `src/truthtrail/data/demo_analyze.json` | fixture data | static | `fixtures/demo_analyze.json` | none (same bytes, sha256 `f47fc692...`) |
| `legacy/spread_simulator.py` | legacy | transform | `spread_simulator.py` | none (sha256 `e8e61cde...`) |
| `legacy/users.py` | legacy data | static | `users.py` | none (sha256 `e2222493...`) |

### New / modified

| File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `src/truthtrail/main.py` | entrypoint | startup | `main.py:48-60` (`app = FastAPI(...)` + `register_problem_handlers`) | role-match |
| `main.py` (root shim, 2 lines) | shim | startup | none; spec D-05 | no analog |
| `src/truthtrail/api/health.py` (`/health`, `/ready`) | controller | request-response | `main.py:63-108` route style + `problems.py:112-124` builder | role-match |
| `src/truthtrail/core/readiness.py` | utility (registry) | request-response | RESEARCH Pattern 9; style of `config.py` | partial |
| `src/truthtrail/core/boot.py` (`BootSettings`) | config | startup | `config.py` (`Settings`, `SettingsConfigDict`) | exact |
| `src/truthtrail/api/limits.py` (`LimitedRouter`, 429 handler) | middleware/handler | request-response | `problems.py:127-137` (`_upstream_error_handler` with `Retry-After`) | role-match |
| `src/truthtrail/api/catchall.py` | middleware | request-response | `problems.py:191-197` (`_unexpected_error_handler`) | role-match |
| `src/truthtrail/core/cascade.py` | utility (pure functions) | transform | none; RESEARCH Pattern 10 | no analog |
| `pyproject.toml`, `uv.lock`, `.python-version` | config | n/a | `pytest.ini` (settings move), `requirements.txt` (pins) | partial |
| `.gitattributes` | config | n/a | `.gitignore` (sibling, same style) | partial |
| `Dockerfile`, `.dockerignore` | config | n/a | none; RESEARCH Pattern 12 | no analog |
| `.github/workflows/ci.yml` (modify) | CI | batch | itself (`ci.yml:20-88`) | self |
| `.env.example` (modify) | config | n/a | itself | self |
| `README.md` (modify) | docs | n/a | itself | self |
| `scripts/generate_demo_fixture.py` (modify) | utility script | batch | itself (`:28-37`, `:128-165`) | self |
| `tests/conftest.py` (modify) | test infra | request-response | itself | self |
| `tests/test_health_ready.py` | test | request-response | `tests/test_upstream_errors.py:16-50` | role-match |
| `tests/test_rate_limit.py` | test | request-response | `tests/test_upstream_errors.py` + `client_factory` | role-match |
| `tests/test_cache.py` | test | request-response | `tests/test_provenance_demo.py:150-165` (call-count stub) + `mock_gnews` | role-match |
| `tests/test_retries.py` | test | request-response | `tests/test_upstream_errors.py:277-340` | exact role |
| `tests/test_cors.py` | test | request-response | `tests/test_upstream_errors.py:16-50` | role-match |
| `tests/test_cascade_properties.py` | test | transform | `tests/test_char_simulator.py` (structure asserts, `seeded_random`) | partial |
| `tests/test_openapi_golden.py` + `tests/golden/openapi_phase1.json` | test | transform | `tests/test_openapi_contract.py` | exact role |
| `tests/test_no_legacy_imports.py` | test | file-I/O + subprocess | `tests/test_settings.py:119-146` + `tests/test_no_hardcoded_credentials.py:28-40` | role-match |
| `tests/test_legacy_frozen.py`, `test_main_shim.py`, `test_dependency_groups.py` | test | file-I/O | `tests/test_demo_fixture.py:109-125` | partial |
| `tests/test_no_hardcoded_credentials.py` (modify) | test | file-I/O | itself | self |

## Pattern Assignments

### `src/truthtrail/core/errors.py` + `api/problems.py` (problem+json builder) - MOVE + SPLIT

**Analog:** `problems.py` (204 lines). `UpstreamError`, `problem_body`, `problem_response` go to `core/errors.py` so `services/gnews.py` never imports from `api/` (RESEARCH Architecture note). Handlers and `PROBLEM_RESPONSES` stay in `api/problems.py`.

**Builder, copy unchanged** (`problems.py:100-124`):
```python
def problem_body(status: int, detail: str, code: str, *, source_status: str, **extensions: Any) -> dict:
    return {
        "type": "about:blank", "title": HTTPStatus(status).phrase, "status": status,
        "detail": detail, "code": code, **extensions,
        "synthetic": False, "source_status": source_status, "data_as_of": None,
    }

def problem_response(status: int, body: dict, headers: Optional[dict] = None) -> JSONResponse:
    return JSONResponse(body, status_code=status, media_type=PROBLEM_MEDIA_TYPE, headers=headers)
```
mypy strict: annotate `dict[str, Any]`, `Mapping[str, str] | None` for headers (RESEARCH mypy list).

**Every new error path uses this builder (D-07, D-10):**
- 429: `problem_response(429, problem_body(429, "Rate limit exceeded.", "rate_limited", source_status="rate_limited"), {"Retry-After": str(retry)})`
- `/ready` 503: `problem_body(503, "Not ready: database, model.", "not_ready", source_status="not_ready")` (names in `detail`, never exception text)
- catch-all 500: `problem_body(500, "Unexpected error.", "internal_error", source_status="error")`

**Handler registration: switch to decorator form** (mypy variance). Current form to replace (`problems.py:198-204`):
```python
app.add_exception_handler(UpstreamError, _upstream_error_handler)
app.add_exception_handler(RequestValidationError, _validation_error_handler)
app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
app.add_exception_handler(ConfigurationError, _configuration_error_handler)
app.add_exception_handler(Exception, _unexpected_error_handler)
```
New form: `@app.exception_handler(UpstreamError)` inside `register_problem_handlers(app)`. Register `RateLimitExceeded` BEFORE the Starlette `HTTPException` handler (it subclasses it).

**OpenAPI declaration:** extend `PROBLEM_RESPONSES` (`problems.py:44-58`, `_problem_declaration` at `:34-41`) with a `429` entry using `_problem_declaration(...)` plus a `Retry-After` header, copying the 503 header block. Add `"429"` to the set in `_problem_only_openapi` (`problems.py:178`: `{"422", "500", "502", "503"}`). `/ready` 503 gets its OWN declaration WITHOUT the `Retry-After` header.

**D-13 clamp** (`gnews_fetcher.py:75-80`): change `return min(int(value), MAX_RETRY_AFTER)` to `max(1, min(int(value), MAX_RETRY_AFTER))`.

---

### `src/truthtrail/services/gnews.py` (service, request-response outbound) - MOVE then MODIFY

**Analog:** itself (`gnews_fetcher.py:1-204`). Keep `GNEWS_URL`, `TIMEOUT = (3.05, 10)`, the pydantic `_Payload/_Article` validation, the header-only key, `allow_redirects=False`, `_fail(...)` (logs code + upstream status only, `raise ... from None`), `logger = logging.getLogger(__name__)` (`:25`).

**Imports to retarget** (`gnews_fetcher.py:22-23`): `from config import ConfigurationError, is_header_safe_key` -> `from truthtrail.core.config import ...`; `from problems import UpstreamError` -> `from truthtrail.core.errors import UpstreamError`.

**Retry loop wraps the existing single call** (`gnews_fetcher.py:98-125`). Keep the exception order exactly, `Timeout` before `ConnectionError` before `RequestException`:
```python
try:
    resp = requests.get(GNEWS_URL, params={"q": query, "lang": "en", "max": 1},
                        headers={"X-Api-Key": api_key}, timeout=TIMEOUT, allow_redirects=False)
except requests.exceptions.Timeout:
    _fail(503, "upstream_timeout", "The news provider timed out.", retry_after=DEFAULT_RETRY_AFTER)
except requests.exceptions.ConnectionError:
    _fail(503, "upstream_unreachable", "The news provider could not be reached.", retry_after=DEFAULT_RETRY_AFTER)
```
New (RESEARCH Pattern 8): `BACKOFFS = (0.3, 0.6)`, `BUDGET = 8.0`, `RETRY_STATUSES = frozenset({500, 502, 503, 504})`; per-attempt `timeout = (min(3.05, remaining), min(10, remaining))`; retry on `Timeout`, `ConnectionError` except `SSLError`, and those statuses; never 4xx/429/3xx. When the bound is exhausted call the existing `_fail` mappings unchanged. Inject `sleep`, `monotonic`, `jitter` as keyword args defaulting to `time.sleep`, `time.monotonic`, `random.uniform` (`# noqa: S311`). Log per attempt: `attempt`, `code`, upstream status only, in the `_fail` style (`logger.warning("gnews request failed: code=%s upstream_status=%s", ...)`).

---

### `src/truthtrail/api/analyze.py`, `api/app.py`, `src/truthtrail/main.py` - SPLIT of `main.py`

**Analog:** `main.py` (109 lines).

**Route + validation to preserve verbatim** (`main.py:25-27`, `:68-90`): `SearchQuery` (`StringConstraints(strip_whitespace=True, min_length=1, max_length=200, pattern=r"^[^\x00-\x1f\x7f-\x9f\u2028\u2029]+$")`), the `Query(description=...)`, `response_model=AnalyzeResponse`, `responses=PROBLEM_RESPONSES`, summary string, `settings: Annotated[Settings, Depends(get_settings)]`. These strings are in the golden OpenAPI snapshot: do not edit them.

**Lifespan fail-fast to keep** (`main.py:15-18`), with return type `-> AsyncIterator[None]` for mypy:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()  # fail fast: a missing key stops startup before any upstream call
    yield
```
`create_app()` must NOT call `get_settings()` (use `BootSettings` for CORS), or `test_uvicorn_exits_on_missing_key` (`tests/test_settings.py:119-146`, asserts `returncode == 3`) breaks with exit 1.

**Fixture loader to move** (`main.py:29-45`): `FIXTURE_PATH` becomes `Path(__file__).resolve().parents[1] / "data" / "demo_analyze.json"` (from `api/`). Keep `@lru_cache(maxsize=1) load_demo_fixture()` and the `RuntimeError("demo fixture is not labelled synthetic")` guard. Add `validate_cascade()` as a hard gate here (D-19); do NOT call `order_events()` on the served body.

**CORS block to replace** (`main.py:62-67`, wildcards) with CatchAll + CORS, added in this order (last added = outermost):
```python
app.add_middleware(CatchAllMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=boot.cors_origins,
                   allow_methods=["GET", "HEAD", "OPTIONS"], allow_credentials=False)
```

**Handler body to cache/limit** (`main.py:91-108`): live branch stays: `data_as_of = datetime.now(timezone.utc).replace(microsecond=0)` (use `datetime.UTC`, ruff UP017), `LiveResult(...)`, `Meta(synthetic=False, ..., source_status="ok" if results else "empty")`. Wrap: `@limiter.limit(lambda: ...)` above the function, add `request: Request` and `response: Response` params, cache lookup inside the body, set `response.headers["X-Cache"]`.

**Per-app state (D-23):** `create_app()` builds `app.state.limiter`, `app.state.analyze_cache`, `app.state.readiness`. Module-level `app = create_app()` lives only in `truthtrail/main.py`. Run `register_problem_handlers(app)` from `create_app()` (as `main.py:60` does at module level today).

---

### `main.py` root shim - NEW (2 lines)

No analog. `from truthtrail.main import app` plus `__all__ = ["app"]` is acceptable. Commit it AFTER the `git mv` commit (otherwise git loses the rename). Test: `import main; import truthtrail.main; assert main.app is truthtrail.main.app`; `test_uvicorn_exits_on_missing_key` must pass unchanged against `uvicorn main:app`.

---

### `src/truthtrail/core/config.py` + `core/boot.py`

**Analog:** `config.py` (88 lines): `Settings(BaseSettings)` with `env_ignore_empty=True`, `hide_input_in_errors=True`, `SecretStr`, `ConfigurationError` re-raised `from None`, `@lru_cache get_settings`. Move unchanged; add rate-limit string fields (`rate_limit_analyze="10/minute"`, `rate_limit_v1="60/minute"`).

`BootSettings` copies the same `model_config` shape with NO required fields (RESEARCH Pattern 4): `cors_origins: Annotated[list[str], NoDecode] = []` with a `mode="before"` comma splitter, `trust_proxy_headers: bool = False`. Validate each origin (scheme + host, no trailing slash, not `*`).

---

### `src/truthtrail/api/health.py` (controller, request-response)

**Analog:** the route declaration style at `main.py:63-82` (`responses=PROBLEM_RESPONSES`, `response_model=`, summary text). `/health` returns `{"status": "ok"}` (pydantic `Health`), `/ready` is a sync `def` returning `Ready(status="ready", checks={name: "ok"})` or `problem_response(503, ...)`. Both unauthenticated, no `@limiter.limit`. Copy-guard scans their OpenAPI strings: no "detects", "AI-based", "verified true" wording (see `scripts/copy_guard.py` `BANNED`).

---

### `src/truthtrail/core/cascade.py` (utility, transform) - NO ANALOG

Use RESEARCH Pattern 10: frozen dataclass `CascadeEvent(event_id, parent_event_id, observed_at)`, `order_events`, `validate_cascade`, `CascadeError`; adapter from `Event.timestamp` (`models.py:4-11`, `timestamp: str`). Sort key `(observed_at, depth, event_id)`. The legacy defect it guards is characterised at `tests/test_char_simulator.py:104,122` (strict xfails); those stay failing.

---

### Test patterns (copy from existing tests)

**Client and mock** (`tests/conftest.py:60-96`): `client_factory(gnews_api_key=..., demo_mode=..., raise_server_exceptions=False)` and `mock_gnews`. Change ONLY `import main` / `main.app` (`conftest.py:78,87`) to build `create_app()` per test; add `client=("203.0.113.9", 1)` pass-through for per-IP tests; add `cache_timer` pass-through for cache tests.

**Problem+json assertion block, copy for 429 / 503 / 500 tests** (`tests/test_upstream_errors.py:25-48`):
```python
response = client.get("/analyze", params={"query": "x"})
body = response.json()
assert response.status_code == 502
assert response.headers["content-type"].startswith("application/problem+json")
assert body["type"] == "about:blank"
assert body["code"] == "upstream_unauthorized"
assert body["synthetic"] is False
assert body["source_status"] == "upstream_error"
assert body["data_as_of"] is None
assert "results" not in body
assert fake_key not in response.text and "gnews.io" not in response.text
assert fake_key not in caplog.text
```
Use for `test_rate_limit.py` (11th request: 429, `Retry-After >= 1`, `code == "rate_limited"`, provenance members, `Origin` echo), `test_health_ready.py` (injected `app.state.readiness.register("database", lambda: False)` and a raising check whose text must not appear in body or `caplog`), `test_cors.py` (500 and 429 carry `Access-Control-Allow-Origin`; unset env gives none).

**Mocking upstream sequences** (`mock_gnews.get(gnews_url, json={...}, status=401)` at `test_upstream_errors.py:18-20`; adapter-direct call at `:277-287`, `gnews_fetcher.fetch_news("x", fake_key)`): `test_retries.py` registers `500, 502, 200` in order on the same URL, counts `len(mock_gnews.calls)`, uses callbacks that read `request.req_kwargs["timeout"]`, and injects `sleep`/`monotonic` fakes (no real sleeping). Build payloads with the `gnews_payload(gnews_article())` fixtures (`conftest.py:106-132`).

**Call-count stub style** (`tests/test_provenance_demo.py:150-165`): `calls: list[str] = []` stub that raises if reached. Reuse for `test_cache.py` (assert upstream not reached on a hit; 401 then 200 proves errors are not cached).

**Golden OpenAPI** (`tests/test_openapi_contract.py`, already walks `app.openapi()`): new `tests/test_openapi_golden.py` per RESEARCH Pattern 11 with `ALLOWED_NEW_PATHS = {"/health", "/ready"}`, `ALLOWED_NEW_RESPONSES = {"429"}` and the single declared schema exception `Problem.properties.synthetic.const = False` (D-20). Golden file dumped from commit `765b844`.

**Hypothesis profiles** in `tests/conftest.py` (RESEARCH Pattern 10): register `ci` (`max_examples=200, derandomize=True, database=None, deadline=None`) and `dev`; `.hypothesis/` into `.gitignore`.

**Subprocess tests: SYSTEMROOT.** Existing duplicates: `tests/test_demo_fixture.py:109-112` (`_windows_system_env()`) and `tests/test_settings.py:129-131` (inline `if "SYSTEMROOT" in os.environ`). Hoist ONE helper into `tests/conftest.py` and use it in `test_no_legacy_imports.py` (fresh-interpreter `sys.modules` check, `python -I`-style minimal env: `PATH`, `PYTHONDONTWRITEBYTECODE`, plus helper).

**Import-boundary test:** `ast.walk` over `src/truthtrail/**/*.py` with `FORBIDDEN = {"legacy", "spread_simulator", "users", "risk_analyzer"}` (RESEARCH "Legacy-unreachable proof"); file listing style from `tests/test_no_hardcoded_credentials.py:28-37` (`git ls-files -z`).

---

### Retargeting list: EXACT existing lines to edit after the move

| File:line | Current | New |
|---|---|---|
| `tests/conftest.py:17` | `from config import Settings, get_settings` | `from truthtrail.core.config import Settings, get_settings` |
| `tests/conftest.py:78,87` | `import main` / `main.app` | `create_app()` per call (central `APP_MODULE = "truthtrail.api.analyze"` constant) |
| `tests/conftest.py:21-27` | `ENV_NAMES` 5 names | add `CORS_ORIGINS`, `TRUST_PROXY_HEADERS`, rate-limit names |
| `tests/test_provenance_demo.py:160` | `"main.load_demo_fixture"` | `"truthtrail.api.analyze.load_demo_fixture"` |
| `tests/test_provenance_demo.py:178` | `importlib.import_module("main")` | `importlib.import_module("truthtrail.api.analyze")` |
| `tests/test_provenance_demo.py:179` | `"main.FIXTURE_PATH"` | `"truthtrail.api.analyze.FIXTURE_PATH"` |
| `tests/test_provenance_demo.py:17` | `.../"fixtures"/"demo_analyze.json"` | `.../"src"/"truthtrail"/"data"/"demo_analyze.json"` |
| `tests/test_request_validation.py:142` | `"main.analyze_risk"` | `"truthtrail.api.analyze.analyze_risk"` |
| `tests/test_upstream_errors.py:316` | `r.name == "gnews_fetcher"` | `r.name == "truthtrail.services.gnews"` |
| `tests/test_upstream_errors.py:12-13` | `import gnews_fetcher`, `from problems import UpstreamError` | `from truthtrail.services import gnews as gnews_fetcher` (keeps `:52,277,287,314,340` calls unchanged), `from truthtrail.core.errors import UpstreamError` |
| `tests/test_demo_fixture.py:17,20` | `from models import ...`, `"fixtures"` path | `from truthtrail.schemas.models import ...`, `data/` path |
| `tests/test_response_models.py:8`, `tests/test_openapi_contract.py:10`, `tests/test_char_simulator.py:13` | `from models import` / `import models` | `truthtrail.schemas.models` |
| `tests/test_settings.py:11` | `from config import ...` | `from truthtrail.core.config import ...` |
| `tests/test_char_risk_analyzer.py:10` | `from risk_analyzer import analyze_risk` | `from truthtrail.services.keyword_baseline import analyze_risk` |
| `tests/test_char_simulator.py:14-15` | `from spread_simulator ...`, `from users ...` | UNCHANGED (`legacy/` on pytest `pythonpath`) |
| `tests/test_no_hardcoded_credentials.py:92,97` | `"fixtures/demo_analyze.json"`, `"models.py"` | `"src/truthtrail/data/demo_analyze.json"`, `"src/truthtrail/schemas/models.py"` |
| `tests/test_no_hardcoded_credentials.py:19-25` | `EXPECTED_ENV_NAMES` 5 names | add the new names |
| `scripts/generate_demo_fixture.py:28-34,37` | root-path imports, `REPO_ROOT / "fixtures"` | `sys.path.insert(0, REPO_ROOT / "legacy")`; `from truthtrail.schemas.models import AnalyzeResponse`; `from truthtrail.services.keyword_baseline import analyze_risk`; `FIXTURE_PATH = REPO_ROOT / "src/truthtrail/data/demo_analyze.json"` |
| `scripts/generate_demo_fixture.py:157` | `args.path.write_text(rendered, encoding="utf-8")` | add `newline="\n"` (Pitfall 9) |
| `pytest.ini` | whole file | delete; move to `[tool.pytest.ini_options]` (`pythonpath = ["legacy", "."]`, `xfail_strict`, `addopts = "-ra"`, same two `filterwarnings`) |

---

### Credential backstop test (`tests/test_no_hardcoded_credentials.py`)

**Analog:** itself. Pattern to extend: `EXPECTED_ENV_NAMES` is a `set` compared by equality at `:80` against every non-comment `.env.example` line, and each line must satisfy `re.fullmatch(r"[A-Z][A-Z0-9_]*=", ln)` (`:77-79`). So new variables go in BOTH places as blank `NAME=` lines, and `http://localhost:5173` goes in a `#` comment only. Scan scope (`SCANNED_SUFFIXES` at `:17` includes `.toml`; `.planning/` and `.claude/CLAUDE.md` asserted at `:63-64`) automatically covers `pyproject.toml`. `uv.lock` has `.lock` suffix (not scanned, hash text would false-positive); do not add it to the suffix set. Also add `.hypothesis/` and `uv.lock` handling to `.gitignore` semantic cases if parametrised (`:84-98`).

---

### `.env.example` - MODIFY

**Analog:** itself (17 lines): comment line + blank `NAME=` per variable. Add:
```
# Comma-separated allowed browser origins. Unset means no cross-origin access.
# Local Vite dev server: http://localhost:5173
CORS_ORIGINS=

# true only behind a trusted reverse proxy. Default false.
TRUST_PROXY_HEADERS=
```
plus the rate-limit names.

---

### `scripts/generate_demo_fixture.py` - MODIFY

**Analog:** itself. Keep `main(argv) -> int` with `argparse` (`--check`, `--path`), `render()` (`json.dumps(..., indent=2, ensure_ascii=False) + "\n"`), `raise SystemExit(main())` (`:128-165`). Suppress `random.Random(SEED)` S311 with `# noqa: S311`. Sibling script style for any new script (`copy_guard.py:200-219`): `main(argv: list[str] | None = None) -> int`, `sys.stdout.write(...)`, return exit code.

---

### `.github/workflows/ci.yml` - MODIFY

**Analog:** itself. Keep verbatim: header comment style, `on:`, `permissions: contents: read`, `concurrency`, the `gitleaks` job in full (`:33-70`, untouched incl. `RANGE_FLOOR`, selftest, `fetch-depth: 0`), job names `copy-guard`, `gitleaks`, `tests`, `timeout-minutes: 10`, SHA-pinned actions with version comments, `persist-credentials: false`.

**Job skeleton to copy for each new job** (`ci.yml:20-34`, `:72-88`):
```yaml
  lint:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9 # v9.0.0
        with:
          version: "0.13.1"
          python-version: "3.13"
          enable-cache: true
      - run: uv sync --locked
      - run: uv run --locked ruff check . && uv run --locked ruff format --check .
```
Replace the `actions/setup-python` + `pip install -r requirements*.txt` pairs in `copy-guard` (`:25-32`, use `uv sync --locked --no-dev`, then `uv run python scripts/copy_guard.py`) and `tests` (`:77-87`, `uv run --locked pytest --cov --hypothesis-profile=ci`). New jobs: `lint`, `typecheck` (`uv run --locked mypy`), `audit` (RESEARCH "pip-audit (exact)": `uv export ... -o "$RUNNER_TEMP/audit.txt"` then `pip-audit -r ... --require-hashes --disable-pip`), `docker` (RESEARCH Pattern 13 commands; add `docker logs` in an `if: always()` step). Add `uv lock --check`. Update the header comment lines 1-2, which still say Phase 2 "extends" it.

---

### `pyproject.toml`, `uv.lock`, `.python-version`, `.gitattributes`

`pyproject.toml`: no in-repo analog; use RESEARCH "Recommended pyproject.toml" with D-24 exact pins (fastapi 0.143.0, pydantic 2.14.0, pydantic-settings 2.15.0, uvicorn 0.54.0, requests 2.34.2; starlette comes via lock at 1.8.0), `uv_build>=0.13.1,<0.14`, NO `readme`, `default-groups = ["dev"]`, no `required-version` above 0.11. Port settings from `pytest.ini` (above); add `[tool.coverage.*]`, `[tool.ruff]` (`line-length = 100`, `extend-exclude = ["legacy"]`, format `exclude` for `keyword_baseline.py`), `[tool.mypy]` (`strict`, `plugins = ["pydantic.mypy"]`, files `src/truthtrail`). Pins currently live in `requirements.txt` (26 lines) and `requirements-dev.txt` (13 lines); read them for the transitive versions to expect in `uv.lock`, then delete both files.

`.gitattributes` (D-16, from RESEARCH Pattern 1): `* text=auto eol=lf` / `*.sh text eol=lf`. Own commit first. Sibling style: `.gitignore` (one rule per line, comments above).

---

### `Dockerfile`, `.dockerignore` - NO ANALOG

Copy RESEARCH Pattern 12 verbatim (digests recorded there; re-verify with the registry API at execution time). `.dockerignore` list in the same section; excludes `legacy`, `tests`, `scripts`, `.planning`, `*.md`. Smoke job asserts `spread_simulator` is NOT importable in the image and `id -u != 0`.

---

### `README.md` - MODIFY

**Analog:** itself (65 lines, Phase 1 rewrite). Keep the "flag ... for human review" phrase (copy guard requires it) and the DEMO_MODE / env-var documentation; replace the pip setup with `uv sync`, add the Windows block (`winget install --id=astral-sh.uv -e`, `uv sync`, `$env:DEMO_MODE = "true"; uv run uvicorn truthtrail.main:app`), document the root `main.py` shim, `CORS_ORIGINS`, `TRUST_PROXY_HEADERS`, `/health`, `/ready`, 429 and `X-Cache`. Run `python scripts/copy_guard.py` after editing.

## Shared Patterns

### Problem+json for every new error path
**Source:** `problems.py:100-124` (`problem_body`, `problem_response`), consumed from `core/errors.py` after the split.
**Apply to:** 429 handler, `/ready` 503, catch-all 500, readiness-check failure, any new `LimitedRouter` rejection. Media type `application/problem+json`; never a bare `JSONResponse` or `HTTPException(detail=...)`. Plain-text CORS preflight 400s are a documented CORSMiddleware limitation.

### Provenance members
**Source:** `problems.py:119-122`: `"synthetic": False, "source_status": ..., "data_as_of": None` always last, always present on errors. Success responses use `Meta(synthetic, data_as_of, source_status)` (`main.py:104-108`). Cache hits keep the original `meta.data_as_of`.
**Apply to:** all new error bodies; `/health` and `/ready` 200 bodies are operational, not data, and carry no `meta`.

### Key-free, URL-free logging
**Source:** `gnews_fetcher.py:56-72` (`_fail`) and `problems.py:191-197`: log `type(exc).__name__` or codes only, `raise ... from None`, `logger = logging.getLogger(__name__)`.
**Apply to:** retry loop (attempt, code, status only), catch-all middleware, readiness registry (class name of a raising check only), limits handler. slowapi's own WARNING contains the client IP (accepted; optionally raise the `slowapi` logger to ERROR in `create_app()`). Tests assert `fake_key not in caplog.text`.

### SYSTEMROOT in subprocess tests
**Source:** `tests/test_demo_fixture.py:109-125`, `tests/test_settings.py:129-131` (comment: without it asyncio cannot initialise Winsock, WinError 10106).
**Apply to:** `test_no_legacy_imports.py`, `test_main_shim.py` (if subprocess), generator `--check` runs, any uvicorn subprocess. One shared `windows_system_env()` in `tests/conftest.py`.

### CRLF handling
**Source:** D-16 / D-21 / RESEARCH Pattern 1. The six CRLF files (`main.py`, `models.py`, `gnews_fetcher.py`, `risk_analyzer.py`, `spread_simulator.py`, `users.py`) are renormalised in commit 1 BEFORE any move. "Unchanged" means identical after `.replace(b"\r\n", b"\n")`; pin with `tests/test_legacy_frozen.py` using the three recorded sha256 values. The Phase 1 gate becomes `git diff --quiet --ignore-cr-at-eol 9b5b085 -- <files>`. Generator writes with `newline="\n"`. Add the normalise commit SHA to `.git-blame-ignore-revs`.

### Network guard and env scrub
**Source:** `tests/conftest.py:37-49` (autouse `responses.RequestsMock(assert_all_requests_are_fired=False)`, `monkeypatch.delenv` over `ENV_NAMES`, `Settings.model_config["env_file"] = None`, `get_settings.cache_clear()`). Add `BootSettings.model_config["env_file"] = None` in the same fixture so a developer `.env` cannot leak CORS values. Never call live GNews.

### Conventions (CLAUDE.md)
4-space indent, double quotes, `snake_case`, annotate all new signatures (mypy strict on `src/truthtrail`), `logging.getLogger(__name__)` never `print`, triple-double-quoted docstrings, no emoji comments (the `risk_analyzer.py` emoji comments stay because that file is frozen). User-facing strings say "flag for human review", never "detects".

## No Analog Found

| File | Role | Data Flow | Reason / source instead |
|------|------|-----------|-------------------------|
| `pyproject.toml`, `uv.lock` | config | n/a | No packaging exists; RESEARCH "Recommended pyproject.toml" |
| `Dockerfile`, `.dockerignore` | config | n/a | No container files; RESEARCH Pattern 12 |
| `src/truthtrail/core/cascade.py` | utility | transform | New invariants; RESEARCH Pattern 10 |
| `LimitedRouter` in `api/limits.py` | router | request-response | slowapi-specific; RESEARCH Pattern 6 |
| `main.py` root shim | shim | n/a | Two lines per D-05 |

## Metadata

**Analog search scope:** repo root modules, `tests/`, `scripts/`, `.github/workflows/`, `fixtures/`, config files (80 tracked files via `git ls-files`).
**Files read:** `main.py`, `problems.py`, `gnews_fetcher.py` (1-125), `tests/conftest.py`, `.github/workflows/ci.yml`, `.env.example`, `pytest.ini`, `scripts/generate_demo_fixture.py` (1-60, 125-165), `scripts/copy_guard.py` (195-219), `scripts/gitleaks_scan.sh` (1-25), targeted excerpts of `tests/test_no_hardcoded_credentials.py`, `test_settings.py`, `test_upstream_errors.py`, `test_demo_fixture.py`, `test_provenance_demo.py`. Retarget lines found by grep over `tests/` and `scripts/`.
**Notes:** line numbers are for the pre-move HEAD `01dfac5`; 02-RESEARCH.md numbers (261 passed after move, 13 failures) match the retarget table above. `config.py`, `models.py` were not re-read; their shape is taken from 02-RESEARCH.md and the Phase 1 pattern map.
**Pattern extraction date:** 2026-10-17
