---
last_mapped_commit: 1fedcd29ba790edf42ebc1ffbffe62b9f643177f
last_mapped_at: 2026-10-11
---
# External Integrations

**Analysis Date:** 2026-10-11

## APIs & External Services

**News search:**
- GNews API (`https://gnews.io/api/v4/search`) - Fetches news articles matching a user query, used as the source of root events for spread simulation
  - SDK/Client: `requests` (direct HTTP GET) in `gnews_fetcher.py`, function `fetch_news`
  - Auth: API key passed as the `apikey` query parameter. The value is hardcoded as the module constant `GNEWS_API_KEY` at `gnews_fetcher.py:3`. No environment variable is read.
  - Request parameters: `q` (user query), `lang=en`, `max=1`
  - Response fields consumed: `articles[].title`, `articles[].source.name`, `articles[].publishedAt`

**Social platforms (simulated, not integrated):**
- Twitter, Facebook, and Reddit appear only as keys of the in-memory dictionary `USERS` in `users.py`. The application makes no API calls to these platforms; the "spread" events are generated locally with `random` in `spread_simulator.py`.

## Data Storage

**Databases:**
- None. No database driver, ORM, or connection string is present. All state is in memory and per request.

**File Storage:**
- Local filesystem only for source code. The application does not read or write data files.

**Caching:**
- None detected.

## Authentication & Identity

**Auth Provider:**
- None. The `/analyze` endpoint in `main.py` (line 16-17) has no authentication or authorization.
  - Implementation: Not applicable. Any client can call the endpoint.

## Monitoring & Observability

**Error Tracking:**
- None detected.

**Logs:**
- No logging configured. There are no `logging` imports or print statements in the Python modules. Uvicorn default access logs are the only output.

## CI/CD & Deployment

**Hosting:**
- Not configured. No Dockerfile, Procfile, cloud config, or deployment manifest.

**CI Pipeline:**
- None detected. No `.github/workflows/`, `.gitlab-ci.yml`, or similar.

## Environment Configuration

**Required env vars:**
- None read by the code. No `os.environ` or `os.getenv` usage exists in the repository.

**Secrets location:**
- The GNews API key is stored in source code at `gnews_fetcher.py:3`. This is a committed secret and should be moved to an environment variable or secret manager, and the key should be rotated, since it is present in git history (commits `1c0ca0e` and `1fedcd2`).
- Placeholder guard in `gnews_fetcher.py:6` is ineffective: `if not "<key literal>" or "PUT_" in "<key literal>":` tests a non-empty string literal rather than `GNEWS_API_KEY`, so the early `return []` never triggers. The intended check is `if not GNEWS_API_KEY or "PUT_" in GNEWS_API_KEY:`.

## Webhooks & Callbacks

**Incoming:**
- None. The only HTTP route is `GET /analyze` (`main.py:16`), which takes a `query` string parameter and returns a JSON list of `{headline, risk, events}` objects. It is a request/response endpoint, not a webhook.

**Outgoing:**
- None beyond the GNews request in `gnews_fetcher.py:17`.

## Network Behavior Notes

- `fetch_news` has no timeout on `requests.get` (`gnews_fetcher.py:17`) and no HTTP status check before `r.json()` (`gnews_fetcher.py:18`). A GNews error response that lacks `articles` yields an empty list, which triggers the fallback in `main.py:21-26`.
- CORS is open to all origins (`main.py:9-14`: `allow_origins=["*"]`), so any web page can call `/analyze`.

---

*Integration audit: 2026-10-11*
