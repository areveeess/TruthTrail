# Phase 1: Secure & Honest Foundation - Context

**Gathered:** 2026-10-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Make the existing hackathon service stop misleading its users, **without restructuring it**. Delivers: no secrets in the repo (env-only configuration), honest upstream errors (never a fabricated 200), provenance on every response (`synthetic`, `data_as_of`, `source_status`), demo data only behind `DEMO_MODE`, validated input and typed response models, characterization tests that pin current behaviour, a truthful README, and a minimal CI job (copy guard + secret scan).

Requirements: FND-01, FND-02, FND-03, FND-04, FND-05, FND-06.

**Not in this phase** (see ROADMAP.md): the `src/truthtrail` package layout, removal of `spread_simulator.py` / `users.py` from the live path, uv lockfile, ruff/mypy/pip-audit, Dockerfile, `/health` / `/ready`, CORS restriction, rate limiting, caching (all Phase 2); real propagation data (Phase 3); the trained classifier (Phase 4). Phase 1 keeps the flat root-level module layout.

</domain>

<decisions>
## Implementation Decisions

Decisions D-01..D-07 were made by the owner during the discussion. Decisions marked **(auto)** were made by Claude using the recommended option because the owner delegated remaining decisions ("take all the decisions urself on auto unless extremely necessary, im going afk"). The owner may revisit any **(auto)** decision.

### `/analyze` response shape
- **D-01:** Replace the bare JSON list with an envelope object: `{"results": [...], "meta": {"synthetic": bool, "data_as_of": <ISO-8601 UTC string>, "source_status": "ok" | "empty" | ...}}`. This is a deliberate breaking change; nothing in this repository consumes the old shape. — **Reversibility:** costly — every later `/v1` endpoint will copy this envelope, so changing it later touches all of them and any client.
- **D-02:** Demo data comes from a **static fixture JSON** committed to the repo, generated once from the existing simulator with a fixed seed and flagged `synthetic: true`. It is served only when `DEMO_MODE=true`. The simulator code itself is left untouched in Phase 1 (used only to generate the fixture), so Phase 2 can delete `spread_simulator.py` and `users.py` without changing demo behaviour.
- **D-03:** The `risk` value stays `High` / `Medium` / `Low`, and each result gains `risk_method: "keyword_baseline"` so no client mistakes it for a trained model.
- **D-04:** A query with zero articles returns **HTTP 200** with `{"results": [], "meta": {"source_status": "empty", "synthetic": false, ...}}`. The fabricated "unknown / 2025-01-01" fallback article is removed entirely.
- **D-05 (auto, derived from FND-03):** With `DEMO_MODE=false` (the default) a live result contains the headline, source, published time, `risk` and `risk_method` but **no `events` key at all** (omitted, not an empty list, so "no spread data" cannot be mistaken for "nothing spread"). With `DEMO_MODE=true`, the response is the fixture, `meta.synthetic` is `true`, and `events` is present.

### Error contract
- **D-06:** Errors are **RFC 9457 `application/problem+json`**: `type`, `title`, `status`, `detail`, plus extension members `code` (stable machine-readable string such as `upstream_unauthorized`, `upstream_bad_response`, `upstream_timeout`, `upstream_rate_limited`, `not_configured`) and `upstream` (e.g. `"gnews"`). Bodies and logs must never contain the upstream URL, query string or any key. **(auto)** Request-validation failures (422, FND-04) use the same problem+json shape with an `errors` extension, for one consistent error format.
- **D-07:** Status mapping: **502** when the upstream answered badly (HTTP 401/403, 5xx, non-JSON body, malformed or null-field records); **503 with a `Retry-After` header** when it cannot be reached or is throttling (timeout, connection error, HTTP 429). A test must prove a GNews 401 returns 502, not 200.
- **D-08 (auto):** If the news API key is absent at startup, the service **fails fast** with an explicit configuration error, unless `DEMO_MODE=true` (which needs no key). The always-false placeholder guard in `gnews_fetcher.py` is replaced by a real check on the settings value. The Bluesky app password and database URL are defined as optional settings now (documented in `.env.example`) but are not required until Phase 3.

### Secrets, scanning and history
- **D-09 (auto):** Secret scanner is **gitleaks**, run as a blocking CI job that scans (a) the working tree and (b) the commit range of each push/PR, so a key that is committed and later deleted still fails the build. Pre-rotation history is **not** scanned (the rotated key in commit `1fedcd2` is known and inert); no baseline file is needed. Researcher: verify the current gitleaks release and install method, and pin version and checksum. — **Reversibility:** reversible.
- **D-10 (auto):** Add `.gitignore` (Python, Node, virtualenvs, `.env*` except `.env.example`, data/model artifact dirs) and `.env.example` containing **names only**: `GNEWS_API_KEY`, `DEMO_MODE`, `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD`, `DATABASE_URL`. Test fixtures use obviously fake placeholder tokens that do not resemble real keys, to avoid scanner false positives.
- **D-11 (owner standing rule, from PROJECT.md):** The old rotated GNews key remains in git history. **Do not** rewrite history or force-push in this phase; that requires an explicit owner request.

### Tests and copy guard
- **D-12 (auto):** Characterization tests pin **stable** current behaviour with golden tables (e.g. `analyze_risk` on a fixed headline set; simulator event-count and linkage invariants under a fixed seed; the old `/analyze` endpoint with mocked `requests.get`). **Known defects are encoded as `xfail(strict=True)` tests that assert the desired behaviour** (substring false positives such as "secure"→High, "studies"→High, "couple"→High; hardcoded-name High risk; child timestamped before parent), so fixing them later flips a visible XPASS and no test asserts a bug as correct. Sequencing: the characterization tests are committed **before** any behavioural change; after the envelope change (D-01) the old-shape endpoint tests are deliberately replaced by contract tests, while the pure-function characterization suite persists.
- **D-13 (auto):** The copy guard is a script (also run as a pytest test) scanning `README.md`, `docs/**`, and FastAPI's OpenAPI strings (title / description / summaries), and any future UI string directory. Banned: truth- or fake-news-detection claims (e.g. "detects the truth", "fake news detector", "detects misinformation"), a `FAKE` verdict label/badge, and "AI-based" / "AI-powered" while no trained model exists. An inline `copy-guard: allow` marker permits quoting; `tests/` and `.planning/` are excluded. The README is rewritten now as a short, honest "prototype under reconstruction" note using "flag for human review" wording.
- **D-14 (auto):** Minimal CI in Phase 1: `.github/workflows/ci.yml` with the **copy guard** and **gitleaks** jobs required; a pytest job is included if installing dependencies is trivial. Phase 2 (ENG-04) extends this workflow with ruff, mypy, pip-audit and uv; it does not replace it.

### Claude's Discretion
- Settings mechanism (e.g. `pydantic-settings` vs plain `os.environ`), exact `code` string names, fixture seed and file location, test directory layout, GitHub Action versions/pins, exact README wording, and how `data_as_of` is derived (upstream article time vs fetch time; must be a UTC ISO-8601 string and documented).
- Whether the `Event` model in `models.py` is reused or replaced when building response models. Its fields differ slightly from the simulator output; it is currently unused.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and requirements
- `.planning/ROADMAP.md` — "Phase 1: Secure & Honest Foundation" goal and the five success criteria; Cross-Phase Notes (error contract and provenance must hold for all later endpoints; open question about retiring `/analyze` in Phase 3)
- `.planning/REQUIREMENTS.md` — FND-01..FND-06 (the six requirements this phase must satisfy)
- `.planning/PROJECT.md` — Core Value, Constraints (security, process/git, honesty) and Key Decisions

### Codebase map
- `.planning/codebase/ARCHITECTURE.md` — request flow, layers, anti-patterns (line references are accurate)
- `.planning/codebase/INTEGRATIONS.md` — GNews call details and the dead placeholder guard
- `.planning/codebase/CONCERNS.md` — defect inventory. **Warning:** several of its line-number references are wrong (it cites lines beyond the end of `main.py`, `spread_simulator.py` and `users.py`). Trust the content and verify against the source.
- `.planning/codebase/TESTING.md`, `.planning/codebase/CONVENTIONS.md` — current (absent) test practice and code style

### Research
- `.planning/research/PITFALLS.md` — silent fallbacks, provenance fields, stale data shown as live, overclaiming and the CI copy-grep idea, secret logging
- `.planning/research/SUMMARY.md` — roadmap implications for Phases 1-2
- `.planning/research/STACK.md` — tooling versions (ruff, mypy, pytest, hypothesis, pip-audit)

### Source files this phase changes or characterizes
- `main.py` — the `/analyze` handler, fallback article, CORS (CORS is Phase 2)
- `gnews_fetcher.py` — hardcoded key (line 3), dead guard (line 6), no timeout (line 17)
- `risk_analyzer.py` — keyword matcher (characterize, do not fix here)
- `spread_simulator.py`, `users.py` — used only to generate the demo fixture (D-02)
- `models.py` — unused Pydantic `Event`
- `requirements.txt`, `README.md`

### External standards
- RFC 9457, "Problem Details for HTTP APIs" (https://www.rfc-editor.org/rfc/rfc9457) — error body format (D-06)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `gnews_fetcher.fetch_news(query)`: the single provider seam; keep it as the adapter and make it raise typed errors instead of returning `[]` on failure.
- `risk_analyzer.analyze_risk(text)`: a pure function, ideal for golden-table characterization.
- `spread_simulator.create_root_event` / `simulate_spread`: used once, with a fixed seed, to generate the committed demo fixture (D-02); not called on the live path afterwards.
- `models.Event`: an unused Pydantic model that could seed the response models.

### Established Patterns
- Flat top-level modules imported by name from the repo root (`from gnews_fetcher import fetch_news`): the process must run from the repo root. Phase 1 keeps this; the package layout is Phase 2.
- Synchronous `def analyze` handler on FastAPI (runs in the threadpool); `requests.get` with no timeout.
- No tests, logging, config module, CI or `.gitignore` exist yet; Phase 1 introduces all of the minimum needed.

### Integration Points
- `main.py:16-41` (`/analyze`): response shape, error handlers and provenance wiring attach here.
- `gnews_fetcher.py:3,6,17`: where the key moves to settings, the guard is fixed and a timeout is added.
- `app = FastAPI()` (`main.py:7`): the title and description feed the OpenAPI strings the copy guard scans.

</code_context>

<specifics>
## Specific Ideas

Example success response (live mode):
```json
{"results": [{"headline": "…", "source": "…", "published_at": "2026-10-11T09:30:00Z", "risk": "Medium", "risk_method": "keyword_baseline"}],
 "meta": {"synthetic": false, "data_as_of": "2026-10-11T10:02:11Z", "source_status": "ok"}}
```
Example error response (GNews returned 401):
```json
{"type": "about:blank", "title": "Bad Gateway", "status": 502, "detail": "The news provider rejected our credentials.", "code": "upstream_unauthorized", "upstream": "gnews"}
```

</specifics>

<deferred>
## Deferred Ideas

- **Purging the old key from git history** — requires `git filter-repo` plus a force-push; only on an explicit owner request, never as part of a phase.
- **Retiring or reducing the query-driven `/analyze`** — DATA-06 forbids proxying arbitrary queries to the news API; this is an open scoping question for Phase 3 planning (see ROADMAP.md Cross-Phase Notes).
- **CORS restriction, rate limiting, caching, outbound retries** — Phase 2 (ENG-06).
- **Local pre-commit secret hook and enabling GitHub's native secret scanning / push protection** — worth doing but outside the roadmap; the owner can enable the GitHub settings in the repo's security settings.

</deferred>

---

*Phase: 01-secure-honest-foundation*
*Context gathered: 2026-10-11*
