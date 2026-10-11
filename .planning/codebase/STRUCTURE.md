---
last_mapped_commit: 1fedcd29ba790edf42ebc1ffbffe62b9f643177f
last_mapped_at: 2026-10-11
---
# Codebase Structure

**Analysis Date:** 2026-10-11

## Directory Layout

```
TruthTrail/                       # Repository root (git)
├── .git/                         # Git metadata (2 commits)
├── .planning/                    # GSD planning and codebase maps
│   └── codebase/                 # Output of codebase mapping (this document lives here)
├── README.md                     # Project description
├── main.py                       # FastAPI app entry point and /analyze route
├── gnews_fetcher.py              # GNews API client
├── risk_analyzer.py              # Keyword-based misinformation risk classifier
├── spread_simulator.py           # Root-event and propagation-event generator
├── users.py                      # Static simulated user pools per platform
├── models.py                     # Pydantic Event model (not yet used)
├── requirements.txt              # Python dependencies
├── package.json                  # npm manifest (recharts only)
└── package-lock.json             # npm lockfile
```

No subdirectories exist for source code. All application modules sit at the repository root, flat.

## Directory Purposes

**`/` (repository root):**
- Purpose: Holds every Python module, the app entry point, and dependency manifests.
- Contains: `*.py` modules, `requirements.txt`, `package.json`, `package-lock.json`, `README.md`.
- Key files: `main.py`, `gnews_fetcher.py`, `risk_analyzer.py`, `spread_simulator.py`, `users.py`, `models.py`

**`.planning/`:**
- Purpose: GSD workflow artifacts.
- Contains: `codebase/` subdirectory only.
- Key files: `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STRUCTURE.md`

**`.planning/codebase/`:**
- Purpose: Analysis documents consumed by planning and execution commands.
- Contains: Markdown analysis files in UPPERCASE.md naming.
- Key files: Written by the mapper; other focus areas (tech, quality, concerns) add STACK.md, INTEGRATIONS.md, CONVENTIONS.md, TESTING.md, CONCERNS.md.

**`.git/`:**
- Purpose: Version control.
- Contains: Two commits on the current branch: "Initial commit" and "Add files via upload".
- Committed: Not applicable (metadata).

## Key File Locations

**Entry Points:**
- `main.py`: FastAPI `app` object and `GET /analyze` route. Start from repository root with an ASGI server.

**Configuration:**
- `requirements.txt`: Python packages `fastapi`, `uvicorn`, `requests` (unpinned).
- `package.json`: Declares `recharts` `^3.7.0` as the only npm dependency.
- `gnews_fetcher.py:3`: GNews API key constant. Contains a secret; do not copy its value into other files. Move to an environment variable.
- `main.py:9-14`: CORS policy (allow all origins, methods, headers).

**Core Logic:**
- `risk_analyzer.py`: `analyze_risk` and the three keyword lists (High, Medium, Low).
- `spread_simulator.py`: `create_root_event`, `simulate_spread`.
- `gnews_fetcher.py`: `fetch_news`.
- `users.py`: `USERS` reference data.

**Data Models:**
- `models.py`: `Event` Pydantic model.

**Testing:**
- None. No test files, test directory, or test configuration exist.

**Frontend:**
- None present. `package.json` implies a React/Recharts UI that is not in this repository.

## Naming Conventions

**Files:**
- Python modules: `snake_case.py`, named by responsibility with a noun or verb suffix: `gnews_fetcher.py`, `risk_analyzer.py`, `spread_simulator.py`.
- Single-word modules for data and models: `users.py`, `models.py`, `main.py`.
- Planning documents: `UPPERCASE.md` under `.planning/codebase/`.

**Directories:**
- Only `.planning/codebase/` uses a multi-level path. Directory names are lowercase, hyphen-free.

**Identifiers:**
- Functions: `snake_case` (`fetch_news`, `analyze_risk`, `simulate_spread`, `create_root_event`).
- Constants: `UPPER_SNAKE_CASE` (`GNEWS_API_KEY`, `USERS`).
- Pydantic model: `PascalCase` (`Event`).
- Dict keys and API fields: `snake_case` in simulator output (`event_id`, `parent_event_id`, `user_influence`) but `camelCase` in the news payload (`publishedAt`) and the response (`headline`). Keep both conventions when extending each area.

## Where to Add New Code

**New API route:**
- Primary code: `main.py` (add a decorated function on `app`).
- Tests: No test location exists. Create `tests/` at the root if adding tests.

**New data source or external client:**
- Implementation: New top-level module modelled on `gnews_fetcher.py`, returning `{title, source, publishedAt}` dicts so `main.py` can consume it unchanged.

**New risk rule or keyword category:**
- Implementation: `risk_analyzer.py`. Add terms to the appropriate list. Keep High → Medium → Low check order in `analyze_risk`.

**New simulated platform or user pool:**
- Implementation: Add a key with `{id, influence}` records to `USERS` in `users.py`. `simulate_spread` iterates over all keys automatically.

**New event field or schema:**
- Implementation: Update `models.py` `Event` and the dict construction in `spread_simulator.py` together.

**Shared utilities:**
- No shared utility module exists. If helpers are needed by more than one module, create a top-level `utils.py` to match the flat layout.

**Frontend (if added):**
- Create a dedicated directory such as `frontend/` or `web/` so it does not mix with the Python modules. The existing `package.json` is at the root and would need to move or be reconciled.

## Special Directories

**`.planning/`:**
- Purpose: GSD planning and codebase analysis.
- Generated: Yes (by GSD mapper and planning commands).
- Committed: Not verified in this analysis; check `.gitignore` before committing.

**`.git/`:**
- Purpose: Git object store.
- Generated: Yes (by git).
- Committed: Not applicable.

**`node_modules/`:**
- Not present. `package-lock.json` exists but no install has been performed in this checkout.

---

*Structure analysis: 2026-10-11*
