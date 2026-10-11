---
last_mapped_commit: 1fedcd29ba790edf42ebc1ffbffe62b9f643177f
last_mapped_at: 2026-10-11
---
# Technology Stack

**Analysis Date:** 2026-10-11

## Languages

**Primary:**
- Python 3 - All backend code: `main.py`, `gnews_fetcher.py`, `risk_analyzer.py`, `spread_simulator.py`, `users.py`, `models.py`

**Secondary:**
- JavaScript (npm ecosystem) - Only a dependency manifest is present (`package.json`, `package-lock.json`). No `.js`, `.jsx`, `.ts`, or `.tsx` source files exist in the repository, so the frontend is either absent or lives outside this repo.

## Runtime

**Environment:**
- Python 3 (exact version not pinned; no `.python-version`, `runtime.txt`, or `pyproject.toml` present)
- Node.js (version not pinned; no `.nvmrc` or `engines` field in `package.json`)

**Package Managers:**
- pip - Python dependencies from `requirements.txt` (unpinned)
  - Lockfile: missing (no `requirements.lock`, `poetry.lock`, or `Pipfile.lock`)
- npm - JavaScript dependencies from `package.json`
  - Lockfile: present (`package-lock.json`, lockfileVersion 3)

## Frameworks

**Core (backend):**
- FastAPI (unpinned) - HTTP API framework; single app object `app = FastAPI()` in `main.py`
- Uvicorn (unpinned) - ASGI server listed in `requirements.txt`. No launch command or config file is in the repo; it is presumably run as `uvicorn main:app`.
- Pydantic - Used for the `Event` model in `models.py` (`BaseModel`). Not declared in `requirements.txt`; it is available only as a transitive dependency of FastAPI.

**Core (frontend manifest):**
- Recharts `^3.7.0` (lockfile resolves to 3.7.0) - React charting library declared in `package.json`. No code in this repo imports it.

**Testing:**
- Not detected. No test framework, test files, or test config are present.

**Build/Dev:**
- Not detected. No bundler, linter, formatter, or type-checker config is present.

## Key Dependencies

**Critical (Python, from `requirements.txt`):**
- `fastapi` (unpinned) - API routing, query parameter validation, CORS middleware (`main.py`)
- `uvicorn` (unpinned) - ASGI server
- `requests` (unpinned) - Outbound HTTP to the GNews API in `gnews_fetcher.py`

**Standard library (Python) in use:**
- `uuid`, `random`, `datetime` (incl. `timedelta`) - Event IDs and spread simulation in `spread_simulator.py`
- `typing.Optional` - `models.py`

**Critical (npm, from `package.json`):**
- `recharts` `^3.7.0` - Declared dependency; no consuming code in repo

**Transitive npm packages present in `package-lock.json` but NOT declared in `package.json`:**
- `react` 19.2.4, `react-dom` 19.2.4, `react-redux` 9.2.0, `@reduxjs/toolkit` 2.11.2, `redux` 5.0.1
- Recharts' own dependencies (`d3-*`, `victory-vendor`, `immer`, `es-toolkit`, etc.)
- Note: the lockfile root entry (`""`) lists only `recharts`, so `@reduxjs/toolkit`, `react-redux`, and `react-dom` appear to be leftovers from an earlier `npm install` and are not used by any source file. Treat them as undeclared.

## Configuration

**Environment:**
- No `.env` file is present in the repository. Reads of configuration are not implemented through environment variables; the GNews key is hardcoded (see `gnews_fetcher.py:3`). See INTEGRATIONS.md for the security implications.
- No `config/` directory or settings module exists.

**Build:**
- No build configuration (`tsconfig.json`, `vite.config.*`, `webpack.config.*`, `Dockerfile`, `Makefile`, CI workflows) detected.

## Platform Requirements

**Development:**
- Python 3 with `pip install -r requirements.txt`
- Node.js with npm to install `package.json` dependencies (only needed for the Recharts dependency)
- Run backend: `uvicorn main:app --reload` (inferred from the `app` object in `main.py`; not documented in `README.md`)

**Production:**
- Not configured. No deployment target, container image, or process manager is defined. The FastAPI app permits all CORS origins (`main.py:9-14`), which is only appropriate for local development.

---

*Stack analysis: 2026-10-11*
