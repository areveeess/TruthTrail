# TruthTrail

## What This Is

TruthTrail is a misinformation early-warning system: it ingests news and social-propagation data, scores how likely a claim is to be misleading using a trained and evaluated classifier, and visualizes how the claim spreads (cascade graph, timeline, risk with confidence) so a human reviewer can prioritize what to look at first. It began as a hackathon prototype (keyword rules plus a random "spread" generator) and is being rebuilt into a credible, deployed, portfolio-grade project aimed at hiring reviewers (SWE / ML / full-stack). Results are always framed as "flag for human review", never "truth detection".

## Core Value

Every risk score and every cascade the system shows is backed by real data and a measured, reproducible evaluation. Nothing fabricated is ever presented as analysis.

## Requirements

### Validated

<!-- Inferred from the existing code (see .planning/codebase/). These exist but are prototype-grade; see Context for their known defects. -->

- ✓ `GET /analyze?query=` endpoint returns `[{headline, risk, events}]` as JSON — existing (`main.py`)
- ✓ Fetch one English news headline per query from the GNews API — existing (`gnews_fetcher.py`)
- ✓ Three-level (High/Medium/Low) rule-based headline risk label — existing, accuracy never measured (`risk_analyzer.py`); to be retained only as the documented "baseline 0" in evaluation
- ✓ Event-record data model for a propagation cascade (`event_id`, `parent_event_id`, `platform`, `user_id`, `timestamp`, `user_influence`) — existing (`spread_simulator.py`; unused Pydantic `Event` in `models.py`)

### Active

<!-- Milestone v1 "Lean MVP" scope (~4-6 weeks). Milestone v2 "Showcase" items are tracked as v2 in REQUIREMENTS.md. -->

- [ ] No secrets in the repo; configuration comes from the environment (the previously committed GNews key has been rotated)
- [ ] Upstream failures surface as honest HTTP errors (502/503), never as fabricated 200 responses; any demo data is behind an explicit `DEMO_MODE` and flagged `synthetic: true`
- [ ] Input validation and typed (Pydantic) response models; truthful README
- [ ] Proper package layout, pinned dependencies, pytest suite (characterization tests first, then simulator invariants), CI (lint, types, tests, dependency audit), Dockerfile, `/health`, restricted CORS, rate limiting, caching
- [ ] Real propagation data ingested from one open source (Bluesky or Mastodon, chosen in a Phase 3 spike) and stored in Postgres; no fabricated users on the live path
- [ ] A text classifier trained and evaluated on a labelled dataset (macro-F1, PR-AUC, calibration), with the old keyword rules reported as baseline 0; API returns a score with confidence
- [ ] React + TypeScript dashboard: cascade graph, timeline, risk badge with confidence, loading/error/empty states
- [ ] Deployed live demo, docker-compose from a clean clone, README with architecture diagram, demo GIF, results table, and limitations/ethics section

### Out of Scope

- Declaring claims "true" or "false" (truth adjudication) — the system flags for human review only; overclaiming is both inaccurate and an ethics risk
- Content-moderation actions (takedowns, user bans, appeal flows) — out of the product's remit; this is an analysis tool
- User accounts and per-user auth in v1 — a single-tenant demo; API-key auth is deferred to v2
- Paid X/Twitter API ingestion — cost and access barriers; open sources (Bluesky/Mastodon) and public research datasets instead
- Non-English content in v1 — the prototype and candidate datasets are English; multilingual is a later extension
- Committing trained model weights — train offline, commit metrics and a model card only
- Mobile app — web dashboard only

## Context

- **Origin:** built in a short hackathon; ~200 lines of Python in 7 flat modules (`main.py`, `gnews_fetcher.py`, `risk_analyzer.py`, `spread_simulator.py`, `users.py`, `models.py`) on FastAPI. No tests, CI, `.gitignore`, pinned dependencies, Dockerfile or frontend source (`package.json` lists only `recharts`).
- **Known defects (verified by running the code and by the codebase map):** the "risk" label is substring keyword matching (e.g. `"cure"` matches `"secure"`, `"dies"` matches `"studies"`, `"coup"` matches `"couple"`; 9 of 10 plainly benign probe headlines scored High; named public figures are hardcoded as High risk); the "spread" is `random.choice` over 7 hardcoded users, ~40% of simulated events precede their own parent, `user_influence` is unused, and nothing marks the data as synthetic; a GNews 401/403 returns HTTP 200 with a fabricated article while other upstream failures return a bare 500; `requests.get` has no timeout; CORS is `*`; a placeholder-key guard in `gnews_fetcher.py` can never fire.
- **Secret history:** a GNews API key was committed in `1fedcd2` and has since been rotated by the owner. The old value still exists in git history; purging it requires a history rewrite and force-push and is deliberately not part of any phase unless the owner explicitly asks.
- **Audience and purpose:** a portfolio piece to be reviewed by hiring engineers. Credibility comes from honest framing, reproducible evaluation numbers, tests/CI, and a live demo, not from breadth.
- **Codebase map:** `.planning/codebase/` (STACK, INTEGRATIONS, ARCHITECTURE, STRUCTURE, CONVENTIONS, TESTING, CONCERNS), generated 2026-10-11.
- **Prior planning:** a review and an approved two-milestone roadmap exist (v1 Lean MVP, v2 Showcase); this project definition carries that plan into GSD.

## Constraints

- **Tech stack**: Keep Python + FastAPI for the backend; React + TypeScript (Vite) for the frontend; Postgres for storage — a coherent, mainstream stack that reviewers recognize and that reuses the existing service.
- **Timeline**: v1 targeted at ~4-6 weeks part-time; v2 (~6 more weeks) is optional — v1 must stand alone as a shippable portfolio piece.
- **Data access**: Free and open sources only (Bluesky Jetstream / Mastodon, public research datasets) — paid APIs are out of reach; verify each source's terms and rate limits in a spike before building on it.
- **Compute**: No GPU in the dev environment — model fine-tuning (v2) is trained offline (Colab/Kaggle); the repo ships code, metrics and a model card, never weights.
- **Security**: Secrets only via environment variables, never committed; scan `.planning/` and code for key material before every commit.
- **Process / git**: All work on branch `claude/sleepy-lovelace-13aums`; no per-phase branches; no pull requests unless the owner explicitly asks; push after each phase (the dev container is ephemeral).
- **Honesty**: User-facing copy must say "flag for human review", never "detects the truth"; synthetic or demo data is always labelled as such in both API and UI.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Two milestones: v1 Lean MVP, then v2 Showcase | v1 alone is a shippable portfolio piece; v2 deepens ML and simulation if time allows | — Pending |
| Horizontal-layers roadmap (foundation, engineering, data, detection, dashboard, deploy) | Matches the approved plan; each layer is independently verifiable | — Pending |
| Keep the keyword rules only as "baseline 0" in the evaluation table | Shows measured improvement over the prototype instead of silently discarding it | — Pending |
| Open propagation data (Bluesky/Mastodon) instead of paid X API | Cost and access; supports reposts/quotes/replies needed for cascades | — Pending |
| Rotate the leaked GNews key; do not rewrite git history by default | Rotation neutralizes the risk; a force-push on a shared repo is destructive and needs explicit owner approval | ✓ Good (key rotated) |
| GSD installed globally; `.planning/` committed | Cloud container is ephemeral, so planning state must live in the repo; global install keeps GSD command files out of the portfolio repo | — Pending |
| Interactive workflow mode, Standard granularity, project-level research first | Owner's choices at initialization | — Pending |
| Bluesky Jetstream v2 as the propagation source; Mastodon deferred to v2 | Free, unauthenticated, per-record timestamps and explicit parent/subject URIs; Mastodon `reblogged_by` has no boost time and sees only a federated slice (research, 2026-10-11; confirm in the Phase 3 spike) | — Pending |
| Primary experience is a triage feed of tracked cascades ranked by risk x velocity, plus a "score this text" playground; query-driven `/analyze` is no longer the core flow | Jetstream filters only by collection and DID, and Replay is metered, so "any claim, any time" is not deliverable on free tiers | — Pending |
| Collector is a bounded scheduled batch job (GitHub Actions), not a 24/7 worker, in the deployed demo | Render free cannot run workers and sleeps after 15 min; free Render Postgres expires after 30 days, so use Neon | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-10-11 after initialization*
