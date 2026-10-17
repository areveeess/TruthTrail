# TruthTrail

**Status: Phase 1 and Phase 2 are done; the project is still a prototype under reconstruction.**

TruthTrail is being rebuilt into a misinformation early-warning tool. Its output is a flag for human review: the aim is to help a reviewer decide what to look at first, and it never decides whether a claim is true. Nothing here is a verdict.

What is real today: a packaged FastAPI service with a typed, tested `GET /analyze` contract, health and readiness endpoints, rate limits, a response cache, bounded retries against the news provider, a locked dependency set, a container image definition and CI. What is still a keyword baseline: the risk label. There is no trained model and no real propagation data yet (see "Not built yet").

## What works today

### `GET /analyze?query=...`

Fetches the most recent matching headline from the GNews API (the provider is asked for one article per query, `max=1`) and labels it with a keyword baseline. The response contract is unchanged since Phase 1:

- The envelope holds `results` and `meta`. At most one result is returned. Nothing is ranked or sorted, so there is no prioritised list yet.
- `risk` is `High`, `Medium` or `Low`, and every result carries `risk_method: keyword_baseline`.
- The baseline is substring keyword rules, not a trained model. It has known false positives, pinned by tests (for example "secure" matches "cure").
- Live results contain the headline, source, publication time and risk label. They contain no spread data at all.
- Every response carries provenance: `synthetic`, `data_as_of` and `source_status` (under `meta` on success, at the top level on errors).
- Errors are `application/problem+json`. If the news provider fails, the API answers 502 or 503; it never returns invented results. A query with no matches is an honest 200 with an empty `results` list.
- Demo data is served only when `DEMO_MODE=true`, from a committed fixture, and is labelled `synthetic: true`.

What `data_as_of` means:

- Live: the UTC instant this server received the provider response. It is not the article publication time (each result has its own `published_at`), and free-plan GNews articles can lag by about 12 hours.
- Demo: a fixed fixture generation instant, never "now", so demo data cannot pass for live data.

### `GET /health` and `GET /ready`

- `GET /health` is liveness: `{"status":"ok"}` while the process runs. It does not check dependencies.
- `GET /ready` is readiness: `{"status":"ready","checks":{}}` when every registered check passes, otherwise 503 as `application/problem+json` naming the failed checks only. No checks are registered yet; the database check arrives in Phase 3 and the model check in Phase 4.

### The `/v1` mount point

An empty `/v1` router is mounted and rate limited, so Phases 3 and 4 add routes to it without changing the app wiring. It serves no data yet.

## Operational behaviour

- **Rate limits.** Per client IP: 10 per minute on `/analyze` and 60 per minute on every `/v1` route. Over the limit the API answers 429 with a `Retry-After` header. The limiter is in memory, so it is per process and meant for a single instance. The rate-limit library logs the client address in its warning line, so treat those logs as containing IP addresses.
- **Cache.** Successful `/analyze` responses are cached for 600 seconds (256 entries). The `X-Cache` header is `miss` or `hit`; a hit keeps the original `data_as_of`, so a cached answer never looks fresher than it is.
- **Provider retries.** GNews calls are retried at most twice, with 0.3 s and 0.6 s backoff (plus a little jitter), inside an overall 8 s budget. They are never retried on a 4xx response or on 429.
- **CORS.** Closed unless `CORS_ORIGINS` is set. For local development with the Vite dev server use `http://localhost:5173`.
- **Proxy headers.** The client address used for rate limiting is the peer address, unless `TRUST_PROXY_HEADERS=true`, in which case `X-Forwarded-For` is honoured for the proxies listed in `FORWARDED_ALLOW_IPS` (default: loopback). uvicorn has its own proxy-header handling, which is on by default and trusts loopback and `FORWARDED_ALLOW_IPS`. To keep one switch only, every documented start command and the image CMD pass `--no-proxy-headers`, and the application-level setting is the only one in effect. Do not remove the flag without re-reading the real-server test in `tests/test_proxy_headers_server.py`.

## Configuration

Copy `.env.example` to `.env` and fill in values. Never commit `.env`. Secrets are read from environment variables only. Variables:

| Name | Purpose |
|---|---|
| `GNEWS_API_KEY` | News provider key. Required unless `DEMO_MODE=true`; the service refuses to start without it. Sent only in the `X-Api-Key` request header. |
| `DEMO_MODE` | `true` serves the synthetic fixture and needs no key. Default `false`. |
| `BLUESKY_HANDLE` | Optional until Phase 3. |
| `BLUESKY_APP_PASSWORD` | Optional until Phase 3. |
| `DATABASE_URL` | Optional until Phase 3. |
| `CORS_ORIGINS` | Comma-separated browser origins (`scheme://host[:port]`, no trailing slash or wildcard). Unset means no cross-origin access. |
| `TRUST_PROXY_HEADERS` | `true` only behind a trusted reverse proxy. Default `false` (the forwarded header is ignored). |
| `FORWARDED_ALLOW_IPS` | Comma-separated proxy addresses whose forwarded header is trusted when `TRUST_PROXY_HEADERS=true`. Default `127.0.0.1` and `::1`. |
| `RATE_LIMIT_ANALYZE` | Per-IP limit for `/analyze`, format `N/minute`. Default `10/minute`. An invalid value stops startup. |
| `RATE_LIMIT_V1` | Per-IP limit for every `/v1` route, format `N/minute`. Default `60/minute`. An invalid value stops startup. |

## Setup with uv

Dependency versions are pinned by `uv.lock` (Python 3.13). Install [uv](https://docs.astral.sh/uv/), then, on Linux or macOS:

```bash
uv sync                                                              # serving + dev dependencies
DEMO_MODE=true uv run uvicorn truthtrail.main:app --no-proxy-headers  # synthetic demo data, no key needed
uv run pytest                                                         # tests
```

To use the live provider instead, export `GNEWS_API_KEY` in your shell (or put it in your own `.env`) and leave `DEMO_MODE` unset.

### Windows (native PowerShell)

```powershell
winget install --id=astral-sh.uv -e            # or: py -3.13 -m pip install uv
# delete an old pip-created .venv first: Remove-Item -Recurse -Force .venv
uv sync
$env:DEMO_MODE = "true"; uv run uvicorn truthtrail.main:app --no-proxy-headers
uv run pytest
```

Then open `http://127.0.0.1:8000/health`. An existing `.venv` created with pip must be deleted before running `uv sync`. The Windows commands are documented but have not been run by the maintainer on a Windows machine yet.

### Dependency groups

- Serving dependencies: the packages under `[project] dependencies`, installed in the image.
- `dev`: test and quality tools; installed by a plain `uv sync`.
- `train`: opt-in (`uv sync --group train`), unused until Phase 4 (model training). It is locked but never installed by default or into the image.

### The root `main.py` shim

The repository root keeps a small `main.py` so the Phase 1 command `uvicorn main:app --no-proxy-headers` still works. It re-exports `truthtrail.main:app` and will be removed when the dashboard phase lands; prefer `truthtrail.main:app`.

## Quality gates and CI

Run locally:

```bash
uv run pytest --cov --hypothesis-profile=ci -q       # tests, branch coverage gated by fail_under in pyproject.toml
uv run ruff check . && uv run ruff format --check .  # lint and formatting
uv run mypy                                          # strict type check of src/truthtrail
uv lock --check                                      # uv.lock matches pyproject.toml
uv export --locked --no-emit-project --all-groups --format requirements-txt -o audit.txt
uv run pip-audit -r audit.txt --require-hashes --disable-pip --progress-spinner off
uv run python scripts/copy_guard.py                  # wording guard for README, docs and API strings
uv run python scripts/generate_demo_fixture.py --check   # committed demo fixture is reproducible
```

The coverage gate is the measured total minus 2 points and may only be raised, never lowered. It is enforced by `--cov`, not by `addopts`, so running a single test file never trips it.

The secret scan uses a pinned, checksum-verified gitleaks binary:

```bash
bash scripts/install_gitleaks.sh "${TMPDIR:-/tmp}/truthtrail-gitleaks"
bash scripts/gitleaks_scan.sh "${TMPDIR:-/tmp}/truthtrail-gitleaks/gitleaks" <base> HEAD <floor>
bash scripts/gitleaks_selftest.sh "${TMPDIR:-/tmp}/truthtrail-gitleaks/gitleaks"
```

GitHub Actions runs seven jobs on every push and pull request: `copy-guard`, `gitleaks`, `tests`, `lint`, `typecheck`, `audit` and `docker`. Third-party actions are pinned by full commit SHA, the workflow has read-only permissions and references no secrets. The workflow structure is covered by a static test (`tests/test_ci_workflow.py`); the first real Actions run is confirmed by the maintainer, not assumed.

## Docker

```bash
docker build -t truthtrail .
docker run --rm -p 8000:8000 -e DEMO_MODE=true truthtrail    # keyless synthetic demo
docker run --rm -p 8000:8000 -e GNEWS_API_KEY truthtrail     # live provider; passes your exported variable through
curl -fsS http://127.0.0.1:8000/health
```

The image is multi-stage, installs only the locked serving dependencies, runs as a non-root user (uid 10001), has a `/health` HEALTHCHECK, and its CMD already carries `--no-proxy-headers`. Its properties are checked statically by `tests/test_container_files.py` and by the installed-package smoke script `scripts/smoke_app.py`; the `docker` CI job builds and probes it. A real build and run on a Docker host is still to be confirmed by the maintainer.

## Layout

- `src/truthtrail/{api,services,schemas,core,data}`: the installed package (routes, provider client and keyword baseline, response models, settings/errors/cascade/readiness, packaged demo fixture).
- `legacy/`: the frozen Phase 1 simulator and user pools. Not packaged, not in the image; used only by the fixture generator and the characterization tests.
- `tests/`: unit, contract, property and characterization tests.
- `scripts/`: copy guard, fixture generator, gitleaks scripts, installed-package smoke script.

## Not built yet

- Real propagation data and the database readiness check (Phase 3).
- A trained and evaluated classifier and the model readiness check (Phase 4).
- The dashboard (Phase 5).
- Deployment (Phase 6).

The old simulated spread now only generates the labelled demo fixture.
