# TruthTrail — session handoff (read this first in a fresh session)

**Written:** 2026-10-17, end of Phase 1. **Branch:** `claude/sleepy-lovelace-13aums` (all work pushed; HEAD at time of writing `402d8c8`).
**State:** Phase 1 COMPLETE. Next step: **plan Phase 2 (Engineering Baseline)**. Nothing of Phase 2 exists yet.

To continue: start a new session on this branch, then run `/gsd-next` (or `/gsd-discuss-phase 2` then `/gsd-plan-phase 2` then `/gsd-execute-phase 2`). `.planning/STATE.md` already says "Phase 1 complete, ready to plan Phase 2".

## What this project is

TruthTrail is a misinformation early-warning system: ingest news and social-propagation data, score how likely a claim is misleading with a trained and evaluated classifier, and visualize how it spreads, so a human reviewer can prioritize. It started as a hackathon prototype (keyword rules plus a random "spread" generator) and is being rebuilt into a credible portfolio project. Core value: every score and cascade shown is backed by real data and a measured evaluation; nothing fabricated is presented as analysis. Copy always says "flag for human review", never "detects the truth".

Planning artifacts live in `.planning/`: `PROJECT.md`, `REQUIREMENTS.md` (33 v1 requirements), `ROADMAP.md` (6 v1 phases + deferred v2), `STATE.md`, `research/*`, `codebase/*`, and `phases/01-secure-honest-foundation/` (CONTEXT with decisions D-01..D-20, RESEARCH, PATTERNS, VALIDATION, six PLAN/SUMMARY pairs, REVIEW, SECURITY, VERIFICATION, UAT). `.claude/CLAUDE.md` holds the project guide (its "Architecture/Conventions" text describes the ORIGINAL prototype and is partly outdated).

## Roadmap (v1 "Lean MVP")

1. Secure & Honest Foundation — **done**
2. Engineering Baseline — **next** (ENG-01..06)
3. Real Propagation Data (Bluesky Jetstream v2 → Postgres, `/v1` read API)
4. Baseline Detection & Evaluation (LIAR/PHEME, TF-IDF + logistic regression, calibration, metrics)
5. Dashboard (React + TypeScript + Vite; triage feed of tracked cascades is the primary UX)
6. Deploy & Package (docker compose, live demo, README with results table)

Phases 3 and 4 both depend only on Phase 2 and may run in parallel. v2 "Showcase" is deferred. Product decision: the primary UX is a triage feed of tracked cascades, not the query-driven `/analyze`. Open scoping question for Phase 3: DATA-06 forbids proxying arbitrary user queries to the news API, so legacy `/analyze` must be retired or reduced; its Phase 1 tests are then retired deliberately, not silently.

## Standing owner constraints (still in force)

- Work only on branch `claude/sleepy-lovelace-13aums`. **No pull requests** unless the owner explicitly asks. **No history rewrite, force-push or key purge** unless explicitly asked.
- Push after each phase/plan (the container is ephemeral). Every commit message ends with exactly:
  `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01RrbnqswEy1t46d655GHDjC`
- Secrets only via environment variables. The old GNews key still exists in git history (commit `1fedcd2`); the owner confirmed it was changed and deleted at GNews. **Never print or reproduce any key.** Before every commit scan added lines for key material (32-hex with word boundaries; 40-char git SHAs are fine; derive the old key from `git show 9b5b085:gnews_fetcher.py` inside a script and print only counts). `tests/test_no_hardcoded_credentials.py` is the backstop (scans the repo incl. `.planning/` and `.claude/`).
- Never call the real GNews API from the dev container (the test network guard enforces it in tests). The owner runs live checks on their own machine.
- The owner delegated decisions ("take all the decisions urself on auto unless extremely necessary"). Plan mode has been re-imposed by the harness several times; when it is active, plan and call ExitPlanMode instead of editing.
- Honesty: synthetic/demo data is always labelled `synthetic: true` in API and UI; fixture data is served only when `DEMO_MODE=true`.

## What Phase 1 delivered (verified: 274 passed, 10 strict xfailed, 0 XPASS; CI green)

- `config.py`: lazy pydantic-settings `Settings` (`GNEWS_API_KEY`, `DEMO_MODE` default false, `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD`, `DATABASE_URL`), `SecretStr`, fail-fast at startup via lifespan unless `DEMO_MODE=true`. The key is trimmed of surrounding whitespace (owner decision); whitespace inside or non-ASCII is rejected at startup.
- `gnews_fetcher.py`: `fetch_news(query, api_key)`; key only in the `X-Api-Key` header; no redirects followed; typed upstream errors. **CRLF file** — preserve CRLF when editing (also `main.py`).
- `problems.py` + `models.py`: RFC 9457 `application/problem+json` for every error with provenance members; success envelope `{results, meta:{synthetic,data_as_of,source_status}}`; `risk_method:"keyword_baseline"`. Error map: 401→502 `upstream_unauthorized`, 403→502 `upstream_forbidden`, other unexpected statuses (incl. GNews 400 for a malformed key)→502 `upstream_bad_response`, 429/timeout/unreachable→503 + Retry-After, bad input→422, unconfigured→500 `not_configured`. Empty upstream result → honest 200 with `results: []`, `source_status: empty`.
- `fixtures/demo_analyze.json` + `scripts/generate_demo_fixture.py` (seeded, `--check`): the only source of demo data, served only under `DEMO_MODE=true`.
- Legacy `risk_analyzer.py`, `spread_simulator.py`, `users.py` are **byte-identical to the original commit `9b5b085`**; their known defects (substring matches like "secure"→"cure", hardcoded celebrity names, negation ignored, child-before-parent timestamps, mixed timestamp formats) are pinned as 10 **strict xfail** tests (`tests/test_char_*.py`). The simulator is now only used by the fixture generator; `/analyze` no longer simulates events.
- Guards: `scripts/copy_guard.py` (banned truth-claim wording in README, docs, OpenAPI strings; README must contain "flag ... for human review"), pinned+checksummed gitleaks 8.30.1 (`scripts/install_gitleaks.sh`, `gitleaks_scan.sh` with range floor `a5dd8257e920923677c60e70611a6f36d87747b2`, `gitleaks_selftest.sh` with 11 scenarios), `.github/workflows/ci.yml` (copy-guard, gitleaks, tests; actions pinned by SHA; push events scan floor..HEAD so cancelled runs cannot skip a range).
- Exact-pinned dependencies including the transitive closure (`requirements.txt`, `requirements-dev.txt`; Starlette 1.8.0; `httpx==0.28.1`). `pytest.ini`: `xfail_strict`, `filterwarnings=error` with a documented Starlette httpx ignore.
- Real-API facts the owner observed on 2026-10-17: valid key → 200; well-formed wrong key → GNews 401; malformed short key → GNews 400.

## Deferred / known items (not blocking)

- Review items left open: 500 responses carry no CORS headers (IN-02); provider `Retry-After: 0` is passed through (IN-03); mixed CRLF/LF line endings with no `.gitattributes`, `models.py` loosely formatted, `Problem.synthetic` could be `Literal[False]` (IN-05).
- CORS is still `allow_origins=["*"]` and `/analyze` has no rate limiting — **Phase 2 scope (ENG-06)**.
- Transitive deps are version-pinned but not hash-pinned — uv lockfile and pip-audit are **Phase 2 (ENG-02, ENG-04)**.
- Whether CI jobs are *required* for merging is a GitHub branch-protection setting, not in the repo.
- FND-02 is complete for the news API only; its Bluesky and database failure paths are verified in Phase 3 (SC5).
- Phase 1 summaries mention retired file `tests/test_char_analyze_legacy.py` (deliberately retired in plan 01-05 with a replacement map in 01-05-SUMMARY).

## Phase 2 starting notes (Engineering Baseline)

Goal: a packaged, tested, containerised, CI-guarded FastAPI app with a versioned `/v1` router mount point that Phases 3 and 4 can extend independently. Success criteria (ROADMAP.md): `src/truthtrail` package (api, services, schemas, core) serving the same endpoints with the Phase 1 characterization tests still passing **unchanged**; `spread_simulator.py`/`users.py` unreachable from routes and imports (the demo-fixture generator needs a plan: keep the fixture committed and either move the generator to a script-only location or generate from a frozen copy); uv lockfile on Python 3.13 with training/serving dependency split; CI with ruff, mypy, pytest, pip-audit and the secret scan, green on the final commit; pytest + hypothesis suite with coverage and property tests (events ordered by `observed_at`, child never earlier than parent); Dockerfile with `/health` and `/ready` (503 when a registered check fails, via an injected-failure test); CORS limited to configured origins, rate limiting (429), TTL cache, outbound timeouts and bounded retries. Keep the Phase 1 CI jobs; Phase 2 extends the workflow, it does not replace it (D-14).

## How work was run (reuse this pattern)

- GSD Core 1.16.0 is installed globally in `~/.claude` (72 `gsd-*` skills; CLI `~/.claude/gsd-core/bin/gsd_run query <cmd>`). Config: interactive mode, standard granularity, `workflow.use_worktrees=false`, `git.branching_strategy=none`. Node 22 works.
- Per plan: spawn `gsd-executor` (sequential, main tree, **plain `git commit` with the two trailers**, explicit staging, no push). Then the orchestrator verifies independently before pushing: `git log` trailers per commit, `git diff --quiet 9b5b085 -- spread_simulator.py users.py risk_analyzer.py`, full pytest, `copy_guard.py`, gitleaks scan, key-material scans, clean tree, no stray `__pycache__` (the Stop hook demands a clean tree and pushed commits). Phase gates after the last wave: code review (`gsd-code-reviewer`, then `gsd-code-fixer`), security audit (`gsd-security-auditor`; the orchestrator writes `NN-SECURITY.md`), `gsd-verifier` (writes VERIFICATION.md; it must be re-run if covered source files change after it — hand edits are not accepted), UAT via `/gsd-verify-work`, then `gsd_run query phase.complete N`.
- Independent review caught real defects the executors and the auditor missed (CI cancel gap, redirect key leak, flaky selftest); keep doing review plus independent verification. The gitleaks selftest was made deterministic with an AWS-shaped runtime-generated value.
- Windows: the owner runs on Windows 11 (PowerShell, Python 3.13 via `py -3.13`); subprocess-based tests must pass `SYSTEMROOT` through.

## Environment gotchas (fresh container)

- Rebuild the venv: `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`. Use `PYTHONDONTWRITEBYTECODE=1` and delete stray `__pycache__` before finishing a turn.
- The gitleaks binary lived in `/tmp/truthtrail-gitleaks` (ephemeral): reinstall with `bash scripts/install_gitleaks.sh /tmp/truthtrail-gitleaks`.
- Scratchpad helper scripts (e.g. a root-pin guard) were ephemeral and are gone; they are not needed.
- `gh` may be absent; use the GitHub MCP tools (`mcp__github__actions_list` etc.) to check CI.
- A PreToolUse hook blocks Bash commands that mention `.env` file names; avoid grepping for them.
