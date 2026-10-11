---
last_mapped_commit: 1fedcd29ba790edf42ebc1ffbffe62b9f643177f
last_mapped_at: 2026-10-11
---
# Codebase Concerns

**Analysis Date:** 2026-10-11

## Tech Debt

**Hardcoded API key and dead key-validation guard:**
- Issue: The GNews API key is written as a string literal instead of being read from the environment. The "is configured" guard is written incorrectly, so it never works: `if not "<key>" or "PUT_" in "<key>":` tests a non-empty string literal (always truthy, so `not` is always False) and checks a placeholder inside the key rather than the `GNEWS_API_KEY` variable. The function therefore always calls the external API, even when no real key is set.
- Files: `gnews_fetcher.py:3` (assignment), `gnews_fetcher.py:6` (guard)
- Impact: Secret is committed to the repository and is present in git history (tracked file, committed in the `Initial commit` / `Add files via upload` history). Anyone with read access to the repo can use the key. The guard that should prevent calls with a placeholder key does nothing.
- Fix approach: Read the key with `os.environ.get("GNEWS_API_KEY")` at `gnews_fetcher.py:3`, change the guard to `if not GNEWS_API_KEY: return []`, add the key name to a `.env.example` (no value), and add `.env` to a `.gitignore`. Rotate the key regardless of its status and purge it from history (for example with `git filter-repo`) before any public push.

**Synthetic spread data presented as analysis output:**
- Issue: `simulate_spread` generates every "spread" event with `random.choice` over hardcoded fake user IDs (`tw1`, `fb1`, `rd1`, etc.) and random timestamp offsets. The output has the same shape as real propagation data, but nothing in the API response marks it as simulated.
- Files: `spread_simulator.py:108-130`, `users.py:1-25`, `main.py:58-67`
- Impact: Consumers (the frontend, which is not in this repository) may display invented accounts and timelines as observed amplification. This undermines the stated purpose of "visualizing how it spreads across digital platforms".
- Fix approach: Add a `simulated: true` flag to each event and to the response, or document the simulation clearly in the API schema. Keep the mock data behind a clearly named module and make the simulator an explicit, opt-in path.

**Unseeded randomness makes results non-reproducible:**
- Issue: `random.choice` and `random.randint` are called without a seed, and `uuid.uuid4()` is used for IDs.
- Files: `spread_simulator.py:117`, `spread_simulator.py:124`
- Impact: The same headline produces a different graph on every request, which makes debugging, caching, and testing difficult.
- Fix approach: Accept an optional `random.Random(seed)` instance in `simulate_spread`, derive the seed from the headline hash, and pass it through from `main.py`.

**Chained events are not time-ordered:**
- Issue: Each child event's timestamp is `base + randint(5, 60)` minutes, computed from the root rather than from its parent. A child can therefore be timestamped earlier than its `parent_event_id`.
- Files: `spread_simulator.py:122-128`
- Impact: Any timeline view or causal analysis built on this data will show impossible orderings.
- Fix approach: Compute each child time as `parent_time + randint(...)` and carry the parent datetime forward inside the loop.

**Inconsistent timestamp formats:**
- Issue: The root event keeps the source string (e.g. `...Z`), while generated events are `datetime.isoformat()` output without a `Z` and, for timezone-aware input, with an offset. The code strips `Z` with `.replace("Z", "")` before parsing.
- Files: `spread_simulator.py:99-110`, `spread_simulator.py:124-125`
- Impact: Frontend date parsing may handle the two formats differently. Inputs with `+00:00` or fractional seconds may parse differently on Python versions before 3.11.
- Fix approach: Parse once with a helper that normalizes to UTC and emit every timestamp through the same formatter (for example `dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`).

**Unused and unvalidated data model:**
- Issue: `models.py` defines a pydantic `Event` model that nothing imports. `main.py` returns plain dicts and declares no `response_model`.
- Files: `models.py:1-11`, `main.py:44-69`
- Impact: The API contract exists in neither code nor docs. Field drift between the simulator and any client is undetected.
- Fix approach: Either use `Event` as `response_model` on `/analyze` (and build the response from it) or delete `models.py`.

**Unpinned and incomplete dependencies:**
- Issue: `requirements.txt` lists `fastapi`, `uvicorn`, and `requests` without versions. `models.py` imports `pydantic` directly, which is not listed and only arrives transitively through FastAPI. `package.json` declares `recharts` (`^3.7.0`) but no frontend code exists in the repository.
- Files: `requirements.txt:1-3`, `models.py:1`, `package.json:3`
- Impact: Builds are not reproducible, and a future major-version change can break the API silently.
- Fix approach: Pin exact versions (or generate a lock with `pip-compile`), add `pydantic` explicitly, and move the frontend's npm dependency into the frontend project once it is added.

**Missing project hygiene files:**
- Issue: No `.gitignore`, no tests directory, no CI configuration, no license, and no run instructions beyond a one-paragraph `README.md`. The `.planning/` directory is currently untracked.
- Files: `README.md`, repository root
- Impact: Caches, `.env` files, and virtualenvs could be committed by accident; no automated check runs on changes.
- Fix approach: Add a Python-appropriate `.gitignore` (including `.env`, `__pycache__/`, `.venv/`, `node_modules/`), a README section with install and run commands (`uvicorn main:app`), and a basic CI job.

## Known Bugs

**Guard against unset API key never triggers:**
- Symptoms: With no real key configured, `fetch_news` still sends requests to GNews and returns whatever the API responds with (typically an error object, which yields an empty list).
- Files: `gnews_fetcher.py:5-7`
- Trigger: Start the server without a valid key, or with a placeholder value.
- Workaround: None in code. The fallback in `main.py` masks the problem (see below).

**Non-JSON or error responses crash the request:**
- Symptoms: `r.json()` raises on an HTML or empty body (for example a rate-limit page or a 5xx from a proxy). The `/analyze` call returns HTTP 500 with no useful message.
- Files: `gnews_fetcher.py:17-18`
- Trigger: GNews quota exceeded, network issue, or upstream outage.
- Workaround: None. `r.raise_for_status()` plus a `try/except` around `r.json()` would contain it.

**Malformed article records raise KeyError:**
- Symptoms: If any article is missing `title`, `source`, or `publishedAt`, or `source` is null, the whole request fails with a KeyError.
- Files: `gnews_fetcher.py:21-26`
- Trigger: Incomplete upstream article data (GNews can return null fields).
- Workaround: None. Use `a.get(...)` and skip records without a title and timestamp.

**Fallback timestamp is fabricated:**
- Symptoms: When no article is found, the endpoint returns the user's query as a headline, source `unknown`, and a constant timestamp `2025-01-01T10:00:00Z`, and then runs the full simulation on it.
- Files: `main.py:48-54`
- Trigger: Any query that returns zero articles, including every request while the key guard is broken and the API is failing.
- Workaround: Clients can check `source == "unknown"`, but the response does not flag it.

**Timestamp parsing breaks on some valid ISO inputs:**
- Symptoms: `datetime.fromisoformat` raises on timestamps with fractional seconds of unusual precision or offset forms on Python versions earlier than 3.11, and `.replace("Z", "")` silently drops the zone, so an offset like `+05:30` is combined with the naive value and produces the wrong instant.
- Files: `spread_simulator.py:110`
- Trigger: Upstream timestamps with a non-UTC offset.
- Workaround: Upstream currently uses `Z`. Parse with `datetime.fromisoformat(ts.replace("Z", "+00:00"))` and normalize.

**Risk keyword matching uses substring search:**
- Symptoms: Keywords match inside unrelated words. Examples: `dead` matches "deadline", `cure` matches "secure" and "procure" (and both return High), `dies` matches "studies", `coup` matches "coupon", `leak` matches "bleak", `official` matches "unofficial", `claim` matches "disclaimer".
- Files: `risk_analyzer.py:32-89` (matching loops at `:79-89`)
- Trigger: Any headline containing those substrings. For example "Secure your deadline" is classified High.
- Workaround: None. Switch to word-boundary regex (`re.search(rf"\b{re.escape(word)}\b", text)`).

**Default risk is Medium for any unmatched text:**
- Symptoms: Neutral headlines with no keyword match are classified Medium, while only a narrow set of phrases can produce Low. Low risk is rarely returned.
- Files: `risk_analyzer.py:91-92`
- Trigger: Typical factual headlines without the listed phrases.
- Workaround: None. The default and the thresholds should be explicit and tested.

**High-risk list is dominated by named individuals:**
- Symptoms: Any headline naming a listed public figure (for example "elon musk", "joe biden", "donald trump") is classified High regardless of content, and the list is checked before the content-based categories.
- Files: `risk_analyzer.py:37-41`
- Trigger: Any headline containing those names.
- Workaround: None. Name-based rules introduce political and reputational bias and should be separated from content-based rules, or removed.

**Risk classification is title-only and first-match:**
- Symptoms: Only the headline is analyzed. The first matching high-risk term wins even if low-risk terms are also present (for example "official statement: person dead" is High, which is arguably correct, but "confirmed: market crash" is High with no context).
- Files: `risk_analyzer.py:79-92`, `main.py:59`
- Trigger: Any multi-signal headline.
- Workaround: None.

## Security Considerations

**Hardcoded credential committed to the repository:**
- Risk: The GNews key can be used by anyone with repo access, and it remains in history after deletion.
- Files: `gnews_fetcher.py:3`, `gnews_fetcher.py:6`
- Current mitigation: None in code. The key is believed to be rotated, but the committed value still needs to be replaced in the code and purged from history.
- Recommendations: Load from environment, rotate, purge history, and enable secret scanning on the repository.

**Wide-open CORS policy:**
- Risk: Any origin can call `/analyze` from a browser, and any method and header are accepted.
- Files: `main.py:37-42`
- Current mitigation: None. Credentials are not allowed, which limits cookie-based abuse, but the API is still fully open.
- Recommendations: Restrict `allow_origins` to the frontend origin(s) read from configuration, and limit `allow_methods` to `GET`.

**No input validation or rate limiting on the public endpoint:**
- Risk: `query` is an unbounded string sent upstream and used as a headline. Each call consumes GNews quota and runs the simulator. Anyone can exhaust the upstream quota or drive CPU use.
- Files: `main.py:44-46`, `gnews_fetcher.py:9-15`
- Current mitigation: None.
- Recommendations: Add `Query(..., min_length=1, max_length=200)`, add a per-client rate limit, and cache results per query for a short TTL.

**Outbound requests have no timeout:**
- Risk: A stalled connection to gnews.io holds a worker thread indefinitely.
- Files: `gnews_fetcher.py:17`
- Current mitigation: None.
- Recommendations: `requests.get(url, params=params, timeout=10)` and handle `requests.RequestException`.

**Upstream data reflected into the response without sanitization:**
- Risk: Article titles and source names are returned unchanged. If the frontend renders them as HTML, this is a stored-XSS vector via the upstream feed.
- Files: `gnews_fetcher.py:22-25`, `main.py:63-65`
- Current mitigation: None in the backend. The frontend is not in this repository, so its handling is unknown.
- Recommendations: Confirm the frontend escapes text (React escapes by default when using `{text}`, but not with `dangerouslySetInnerHTML`), and cap title length.

**API key sent as a query parameter:**
- Risk: The key appears in full URLs, which are often written to proxy, server, and client logs.
- Files: `gnews_fetcher.py:9-14`
- Current mitigation: Upstream requires this form. Do not log `params` or the full URL.
- Recommendations: Avoid logging the request URL, and make sure any error handler strips query strings before logging.

## Performance Bottlenecks

**Blocking upstream call on every request:**
- Problem: Each `/analyze` request performs a synchronous HTTP call to GNews with no caching.
- Files: `main.py:45-46`, `gnews_fetcher.py:17`
- Cause: `def analyze` (sync) calls `requests.get` directly. There is no cache, so repeat queries cost quota and latency.
- Improvement path: Add an in-process TTL cache keyed by the normalized query, and use `httpx.AsyncClient` in an `async def` endpoint if concurrency grows.

**Per-article loop does redundant work:**
- Problem: The loop computes `analyze_risk`, a root event, and a full simulation for each article.
- Files: `main.py:56-67`
- Cause: `max` is hardcoded to 1 in `gnews_fetcher.py:13`, so today the loop runs once, but the code is written for many articles without bounds.
- Improvement path: Keep the loop, but make `max` a parameter and cap total events returned.

**Simulation output size scales with risk:**
- Problem: A High result yields 1 root plus 18 events (6 per platform across 3 platforms), Medium yields 10. The count is fixed and not tied to real data.
- Files: `spread_simulator.py:112`, `spread_simulator.py:116`
- Cause: Magic numbers. `spread = 6 if risk == "High" else 3`.
- Improvement path: Move the spread counts into named constants and document them alongside the simulated-data caveat.

## Fragile Areas

**Risk analyzer keyword lists:**
- Files: `risk_analyzer.py:34-89`
- Why fragile: Classification depends on ordered substring lists. Adding a term can change results for unrelated headlines, and iteration order determines which category wins.
- Safe modification: Add tests with fixed headlines before changing any term; prefer word-boundary matching.
- Test coverage: No tests exist.

**Timestamp handling across the pipeline:**
- Files: `spread_simulator.py:99-110`, `spread_simulator.py:124-125`, `main.py:52-53`
- Why fragile: Input format is assumed to be a `Z`-suffixed UTC string. Any change in upstream format or any non-UTC input breaks parsing or mixes zones.
- Safe modification: Normalize at one boundary (`gnews_fetcher.py`) and test with `Z`, `+00:00`, and fractional-second inputs.
- Test coverage: None.

**Global mutable user table:**
- Files: `users.py:1-25`, `spread_simulator.py:95`, `spread_simulator.py:114`
- Why fragile: `USERS` is a module-level dict imported by reference. Any code that mutates it changes behavior for all requests in the process.
- Safe modification: Return copies, or freeze the structure (`types.MappingProxyType` and tuples).
- Test coverage: None.

**No frontend code in this repository:**
- Files: `package.json:1-5`, `README.md`
- Why fragile: The README and the `main.py` comment ("so frontend NEVER breaks") imply a consumer, but its contract with `/analyze` is undocumented and not tested here. Changing the response shape would break it silently.
- Safe modification: Document the response schema (see the `models.py` note above) before changing it.
- Test coverage: Not applicable in this repository.

## Scaling Limits

**Single-process, in-memory design:**
- Current capacity: One `uvicorn` process, no persistence, no shared cache.
- Limit: GNews free-tier quota (per-day request cap) and per-process throughput. Results are not shared across workers.
- Scaling path: Add a shared cache (Redis or similar) and a per-key quota budget before running multiple workers.

**Fallback masks upstream quota exhaustion:**
- Current capacity: Any upstream failure returns a plausible-looking result.
- Limit: Operators cannot tell from the response whether the data is real.
- Scaling path: Return an explicit `source_status` field (`ok`, `empty`, `upstream_error`) and log it.

## Dependencies at Risk

**GNews API (external, free tier):**
- Risk: Quota limits, no SLA, and the free tier restricts results. The code depends on the exact shape of `articles[].title`, `source.name`, and `publishedAt`.
- Impact: Requests fail or return empty results, and the fallback hides the failure.
- Migration plan: Isolate the provider behind `gnews_fetcher.fetch_news` (already a single function) and add a second provider adapter with the same return shape.

**`requests` (sync HTTP client):**
- Risk: Blocking I/O in a FastAPI service; no timeout set.
- Impact: Thread-pool exhaustion under load.
- Migration plan: Use `httpx` with explicit timeouts, or keep `requests` and set timeouts consistently.

## Missing Critical Features

**No automated tests:**
- Problem: No test files, test framework, or test configuration exist.
- Blocks: Safe refactoring of the risk rules, the simulator, and the API contract.

**No observability:**
- Problem: No logging, metrics, or health endpoint. Upstream failures are invisible.
- Blocks: Diagnosing quota exhaustion or the broken key guard in production.

**No documented API contract:**
- Problem: The `/analyze` response shape is implicit (see `main.py:63-67`), and the `Event` model is unused.
- Blocks: Frontend-backend work in parallel and any versioning.

## Test Coverage Gaps

**Risk classification:**
- What's not tested: Each keyword category, precedence between High, Medium, and Low, and the default.
- Files: `risk_analyzer.py:32-92`
- Risk: Substring false positives (see Known Bugs) go unnoticed; changes to lists change outputs silently.
- Priority: High

**GNews adapter:**
- What's not tested: Success response, empty `articles`, non-JSON body, HTTP error status, missing fields, and the key guard.
- Files: `gnews_fetcher.py:5-28`
- Risk: Crashes and the broken guard are only found in production.
- Priority: High

**Simulator invariants:**
- What's not tested: Event count per risk level, `parent_event_id` linkage, and the timestamp ordering that is currently violated.
- Files: `spread_simulator.py:97-130`
- Risk: Impossible timelines reach the frontend.
- Priority: Medium

**API endpoint:**
- What's not tested: `/analyze` with zero articles (fallback), with upstream errors, and with a blank or very long query.
- Files: `main.py:44-69`
- Risk: Fallback masking and unbounded input are not caught.
- Priority: Medium

---

*Concerns audit: 2026-10-11*
