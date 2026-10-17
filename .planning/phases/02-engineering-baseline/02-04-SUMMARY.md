---
phase: 02-engineering-baseline
plan: 04
subsystem: tooling
tags: [ruff, ruff-format, mypy, strict, pydantic-plugin, git-blame-ignore-revs, lint]

requires:
  - phase: 02-engineering-baseline
    provides: plan 02-03 pyproject.toml, uv.lock and the installed ruff 0.17.1 and mypy 2.4.0
provides:
  - "[tool.ruff], [tool.ruff.lint], [tool.ruff.format] and [tool.mypy] configuration in pyproject.toml"
  - a repository that is clean under ruff check, ruff format --check and mypy strict
  - the mechanical formatter commit recorded in .git-blame-ignore-revs
affects: [02-05, 02-06, 02-07, 02-08, 02-09, 02-10, 02-11, 02-12]

actuals:
  tokens: 30000
  tasks: 3
  commits: 3
plan_head_before: 089f781dc53997b49d77ea2880abb805cb90511e
plan_head_after: 79cb23fa25cf2b6223a908768a8c4666152ef798

tech-stack:
  added: []
  patterns:
    - "Mechanical format/autofix commit is separate from hand fixes and listed in .git-blame-ignore-revs"
    - "Docstrings that reach the OpenAPI document are set through __doc__ = (adjacent literals) so wrapping cannot change the text"
    - "Exception handlers registered through app.exception_handler(X)(handler) (typed for subclasses), order unchanged"

key-files:
  created: []
  modified:
    - pyproject.toml
    - .git-blame-ignore-revs
    - src/truthtrail/api/problems.py
    - src/truthtrail/core/config.py
    - src/truthtrail/core/errors.py
    - src/truthtrail/main.py
    - src/truthtrail/schemas/models.py
    - src/truthtrail/services/gnews.py
    - scripts/copy_guard.py
    - scripts/generate_demo_fixture.py
    - tests/ (mechanical format in 14 files; hand edits in 7, see below)
    - .planning/phases/02-engineering-baseline/02-VALIDATION.md

key-decisions:
  - "Markdown is excluded from ruff (extend-exclude gains *.md): ruff 0.17 lints and formats Python code blocks in Markdown and rewrote seven planning notes on the first run"

requirements-completed: []

status: complete
completed: 2026-10-17
---

# Phase 2 Plan 04: Ruff and Mypy Strict to Green Summary

**Ruff (E, F, I, UP, B, S, SIM, C4, PT, RUF at line length 100) and mypy strict with the pydantic plugin are configured and clean over the whole repository, in three commits: a mechanical autofix and format commit recorded for blame, a hand-fix commit, and a typing commit. No behaviour changed: 303 passed, 10 xfailed, no XPASS, the golden OpenAPI and frozen-hash tests unchanged.**

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | a530756 | style: ruff autofixes and ruff format (mechanical, no behaviour change) |
| 2 | 591bb69 | style: fix remaining ruff findings; record formatter commit for blame |
| 3 | 79cb23f | refactor(types): make src/truthtrail pass mypy strict (generics, Mapping headers, decorator-form handlers, lifespan type) |

## Statistics

**Ruff, before (first run with the new configuration, Markdown not yet excluded):** 86 findings, 31 autofixable (E501 50, UP045 16, UP017 7, I001 5, SIM117 2, PT018 2, S311 1, F401 1, RUF007 1, B905 1). Markdown code blocks accounted for a share of the E501 count and were then excluded (see Deviations).

**Ruff, after the Task 1 safe autofix and format:** 25 files reformatted, 27 findings left for hand fixing (22 E501, 2 PT018, 1 S311, 1 RUF007, 1 B905). The plan estimated 24; the difference is E501 lines in 7 test and script docstrings or comments that the formatter does not wrap.

**Ruff, after Task 2:** `All checks passed!`; `ruff format --check .` reports 33 files already formatted.

**Mypy, before:** 11 errors in 4 files (the plan expected 3; `core/errors.py` also had two bare `dict` generics).

| Location | Error | Fix |
|----------|-------|-----|
| core/errors.py `problem_body` | bare `dict` return | `dict[str, Any]` |
| core/errors.py `problem_response` | bare `dict` body and headers | `body: dict[str, Any]`, `headers: Mapping[str, str] | None` |
| services/gnews.py `fetch_news` | bare `dict` in return | `list[dict[str, str]]` |
| services/gnews.py `requests.get(params=...)` | `dict[str, object]` not accepted | a local `params: dict[str, str | int]` |
| api/problems.py `_problem_declaration` | bare `dict` return | `dict[str, Any]` |
| api/problems.py `_http_exception_handler` | `Mapping[str, str] | None` headers passed to a `dict` parameter | resolved by the `Mapping` parameter in `problem_response` |
| api/problems.py (4 calls) | `add_exception_handler` variance errors | `app.exception_handler(X)(handler)` for the same handlers, same order |
| main.py `lifespan` | missing return type | `AsyncIterator[None]` from `collections.abc` |

**Mypy, after:** `Success: no issues found in 12 source files`. The configuration has no `ignore_errors` and no per-module overrides. The existing `# type: ignore[method-assign]` on `app.openapi` is still needed (strict reports it as unused otherwise, and it did not), so it stays. No `types-*` package was added; `uv lock --check` still passes and `uv.lock` is unchanged.

## Hand fixes (Task 2)

- OpenAPI-visible strings wrapped with adjacent literals: the `analyze` summary and the `q` description in `main.py`, the `source_status` Field description in `schemas/models.py`.
- The three model docstrings in `schemas/models.py` that pydantic copies into the OpenAPI schema (`LiveResult`, `DemoResult`, `Problem`) could not be wrapped as docstrings without inserting a newline into the schema text, so they are set with `__doc__ = ("..." "...")` inside the class body; `tests/test_openapi_golden.py` proves the document is byte-identical.
- S311: the seeded `random.Random(SEED)` is moved to its own line `rng = ...  # noqa: S311 - deterministic fixture seed, not security`. No `noqa: E501` was added anywhere.
- B905 and RUF007: `zip(chain, chain[1:])` became `itertools.pairwise(chain)` (VALIDATION row 6).
- PT018: the two compound asserts were split into consecutive asserts in the same order (VALIDATION rows 2 and 3).
- `.git-blame-ignore-revs` now lists two 40-character SHAs: the line-ending commit and a5307569be224b3c0dd878bb740ca14af1ee90a1.
- 02-VALIDATION.md "Expected Phase 1 test edits" gained row 9 for the wrapped docstrings, comments, the xfail `reason` string and the two sha256 pins (values byte-identical).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Ruff 0.17 formatted and linted Markdown files**
- **Found during:** Task 1, first `ruff check . --fix` and `ruff format .`
- **Issue:** ruff 0.17.1 treats Python code blocks inside `*.md` files as in scope and rewrote seven planning notes under `.planning/` (and produced extra E501 findings). The plan's configuration only excludes `legacy`, and the plan says nothing about Markdown.
- **Fix:** reverted those seven files with `git checkout -- .planning` (they carried only the tool's changes) and set `extend-exclude = ["legacy", "*.md"]` with a comment explaining why. Prose documents and the README are not source.
- **Files modified:** pyproject.toml
- **Commit:** a530756

**2. [Deviation - form] Plan said "decorator form" for exception handlers**
- **Found during:** Task 3
- **Issue:** the handlers are module-level functions; moving them inside `register_problem_handlers` to use `@app.exception_handler(X)` syntax would reshape the module for no gain.
- **Fix:** used `app.exception_handler(X)(handler)` (the decorator factory applied to the same functions). It is typed for subclass handlers (no variance error) and registers in the identical order: UpstreamError, RequestValidationError, StarletteHTTPException, ConfigurationError, Exception.
- **Files modified:** src/truthtrail/api/problems.py
- **Commit:** 79cb23f

**3. Method notes (no behaviour effect):** `[tool.mypy]` was appended to pyproject.toml with a shell append rather than the Edit tool, and the mypy cache was directed to a scratch directory outside the repository so no `.mypy_cache` was created. The ruff formatter joined the wrapped hash and summary literals back into single lines where they fit in 100 columns, which is the intended formatter output.

## Verification

- `ruff check .`: All checks passed. `ruff format --check .`: 33 files already formatted. `mypy`: no issues in 12 source files.
- `pytest -q`: 303 passed, 10 xfailed (no XPASS), unchanged from the start of the plan. `tests/test_openapi_golden.py` and `tests/test_legacy_frozen.py`: 7 passed. `tests/test_no_hardcoded_credentials.py`: 13 passed.
- `scripts/copy_guard.py`: clean (135 OpenAPI strings). `scripts/generate_demo_fixture.py --check`: up to date.
- `git diff 089f781 HEAD` shows no change under `legacy/` or `src/truthtrail/services/keyword_baseline.py`.
- From this plan on, every plan's verification includes `ruff check`, `ruff format --check` and `mypy`.

## Known Stubs

None.

## Threat Flags

None. No network, auth, file-access or schema surface was added.

## Self-Check: PASSED

- pyproject.toml has `[tool.ruff]`, `[tool.ruff.lint]`, `[tool.ruff.lint.isort]`, `[tool.ruff.lint.per-file-ignores]`, `[tool.ruff.format]` and `[tool.mypy]`: FOUND
- Commits a530756, 591bb69, 79cb23f are ancestors of HEAD: FOUND
