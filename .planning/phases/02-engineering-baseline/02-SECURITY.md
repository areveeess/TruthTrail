---
phase: 02-engineering-baseline
status: secured
threats_open: 0
threats_total: 53
asvs_level: 1
block_on: high
audited: 2026-10-18
head: 65aabff
---

# Phase 2 Security Verification

Verdict: **SECURED** (53/53 threats closed: 48 mitigate, 5 accept; no open IDs). The threat register was verified directly against code, tests and config at HEAD `65aabff`, which already contains the fixes for all eight confirmed code-review findings (`02-REVIEW.md`). Threat IDs are T-02-01 to T-02-42 (41 numbered threats: 36 mitigate, 5 accept) plus one T-02-SC supply-chain row for each of the 12 plans (12 mitigate). T-02-23 is not declared in any plan; it is a numbering gap, not a threat. The T-02-SC rows are reported below as three groups. ASVS level 1, `block_on: high`: no high-severity threat is open.

## Verification performed

No repo files were edited by the audit and the working tree stayed clean.

- Full pytest with coverage: 533 passed, 10 xfailed. The xfails are the Phase 1 legacy-defect characterisation tests. Total coverage 98.51% against the `fail_under = 96` gate; a `--fail-under=100` negative control exited 2.
- `ruff check`, `ruff format --check` and `mypy --strict` are clean.
- `uv lock --check --offline` resolved without changes.
- `pip-audit` over the exported lock with `--require-hashes` reported no known vulnerabilities.
- The two pinned image digests (python and uv) both resolve at their registries (HTTP 200).
- Secret scans, counts only, no key printed: the old key does not occur in the HEAD tree; no commit after the rotation floor `a5dd825` adds a line containing it; there are no 32-hex strings in any tracked file at HEAD, and none in added lines after the floor.

## Threat register

Evidence paths are relative to the repo root. "Disposition" `accept` marks the five accepted risks.

| ID | Sev | Disposition | Evidence | Status |
|---|---|---|---|---|
| T-02-01 | med | mitigate | Commit 0e9f90b touches 7 files; `git show --ignore-cr-at-eol --stat` lists only `.gitattributes`. The three legacy files are identical to 9b5b085 modulo CR, and their sha256 values match the pins in `tests/test_legacy_frozen.py:25-32`. | CLOSED |
| T-02-02 | med | mitigate | `tests/golden/openapi_phase1.json` has one commit (ce80365) and its sha256 is pinned at `tests/test_openapi_golden.py:20`. Only the declared additions are stripped in `phase1_view`, and `test_only_declared_additions_exist` guards the rest. | CLOSED |
| T-02-03 | high | mitigate | `tests/test_no_hardcoded_credentials.py` passes. No key material appears in HEAD, and no post-floor commit adds any 32-hex line. | CLOSED |
| T-02-04 | high | mitigate | `tests/test_no_legacy_imports.py`: AST walk with a negative control (`test_walker_flags_forbidden_imports`), fresh-interpreter `sys.modules` test, and a serving-path `find_spec` test. `main.py` re-exports only `truthtrail.main`. | CLOSED |
| T-02-05 | high | mitigate | Commit 1473d89 is 9 pure renames at 100% similarity (`git show -M100%`). The fixture sha256 is pinned at `tests/test_legacy_frozen.py:34`, and the fixture and legacy hashes were recomputed. `test_check_detects_hand_edit` covers the generator `--check`. | CLOSED |
| T-02-06 | med | mitigate | `tests/test_upstream_errors.py:337-361` targets logger `truthtrail.services.gnews` and asserts a WARNING record exists (`has_warning`, so it cannot pass vacuously), with no key or URL in logs. | CLOSED |
| T-02-07 | high | mitigate | `pyproject.toml:11-19` has exact `==` pins. `uv.lock` has 388 sha256 hashes, all 72 packages come from the pypi.org registry, and the lock is unchanged since 1c8cfe2. `tests/test_dependency_groups.py` asserts the pins, and CI and the Dockerfile use `--locked` or `--frozen`. | CLOSED |
| T-02-08 | med | mitigate | CI pins uv 0.13.1 in all 5 uv jobs (`ci.yml:28,85,...`). `required-version` is unset (`test_uv_required_version_is_not_set`). `uv lock --check` is in the lint job (`ci.yml:105`) and passed locally with uv 0.11.32. | CLOSED |
| T-02-09 | high | mitigate | `ci.yml:26` pins setup-uv by 40-hex SHA with a `# v9.0.0` comment. Permissions are `contents: read` (`ci.yml:11-12`), every checkout sets `persist-credentials: false`, and there is no `secrets.`. `tests/test_ci_workflow.py` enforces all of it. | CLOSED |
| T-02-10 | high | mitigate | `pyproject.toml:73` has `extend-exclude = ["legacy"]` and `:86` excludes `keyword_baseline.py` from the formatter. The hash pins hold at HEAD. | CLOSED |
| T-02-11 | med | mitigate | Handler registration order is preserved at `problems.py:172-178`. The golden test and the full suite pass. | CLOSED |
| T-02-12 | high | mitigate | `core/boot.py:27-51` rejects wildcard, path, trailing slash, credentials and bad scheme or port. `cors_origins` defaults to `[]` (`boot.py:65`). `app.py:92-100` allows only GET, HEAD and OPTIONS with `allow_credentials=False`. `tests/test_cors.py` covers denied origins, unset or empty values and invalid origins. | CLOSED |
| T-02-13 | med | mitigate | `app.py:88-92` adds `CatchAllMiddleware` before CORS, so it sits inside it. `test_cors.py` shows ACAO on 404, 422 and 500 for an allowed origin. | CLOSED |
| T-02-14 | high | mitigate | `api/catchall.py:40` logs `type(exc).__name__` only, and the body is the fixed generic 500. `test_500_for_allowed_origin_is_problem_json_with_cors_headers` asserts the marker string is absent from body and caplog. | CLOSED |
| T-02-15 | med | mitigate | `app.py:87` uses `get_boot_settings()` (no required fields). The key check is only in the lifespan (`app.py:41`). `tests/test_settings.py:127` `test_uvicorn_exits_on_missing_key` asserts exit code 3 and "Application startup failed". | CLOSED |
| T-02-16 | high | mitigate | `api/health.py:39-46` puts only check names in `detail`. `core/readiness.py:49,87,92` logs the name and class name only. `test_raising_check_is_503_and_leaks_nothing` and `test_raising_check_logs_class_name_only` assert the secret is absent. | CLOSED |
| T-02-17 | low | accept | `/health` returns a constant body (`health.py:26-28`). `/ready` runs only registered checks, with a 2 s timeout (`readiness.py:29`). Neither endpoint is rate limited, per `test_health_and_ready_are_never_limited`. The acceptance is documented in the plan and the module docstring. | CLOSED (accepted) |
| T-02-18 | med | mitigate | `readiness.py:46` treats a non-True result as failed, and `:47-49` treats a raised exception as failed, logging the name. `readiness.py:67-68` rejects duplicate names, and `:86-88` fails closed on timeout. Tests cover each. | CLOSED |
| T-02-19 | high | mitigate | `analyze.py:74` applies `@limiter.limit(... rate_limit_analyze)`, default 10/minute, validated in `config.py:52-61`. `problems.py:96-107` returns a 429 problem+json with `Retry-After`. `test_cache.py::test_rate_limit_applies_before_the_cache` and `test_rate_limit.py::test_eleventh_default_request_is_429_problem` pass. WR-05 added the process-wide `UpstreamBudget` (`limits.py:68-90`, 100/day). | CLOSED (residual, see below) |
| T-02-20 | high | mitigate | `limits.py:47-65` `LimitedRouter.add_api_route` wraps every route. Limiting is decorator-only (`app.py:80`), and `key_style="endpoint"` is set at `limits.py:44` (fix CR-01). `test_v1_limits.py` has the probe-route 429, a path-parameter shared bucket, and a handler-without-`request` failure. `test_rate_limit.py:217` is an AST guard against `SlowAPIMiddleware` and `default_limits`. | CLOSED |
| T-02-21 | high | mitigate | `app.py:101-108` adds the proxy middleware only if `TRUST_PROXY_HEADERS`, and only for the `FORWARDED_ALLOW_IPS` peers. `Dockerfile:23` CMD carries `--no-proxy-headers`, and the README start commands do too. `tests/test_proxy_headers_server.py` runs a real uvicorn subprocess with a default-flags negative control (spoof gets 200,200,200 versus 200,200,429). | CLOSED |
| T-02-22 | low | accept | slowapi logs `ratelimit %s (%s) exceeded` with the client key at WARNING (`.venv/.../slowapi/extension.py:515-520`). The 429 body excludes the address (`test_rate_limit.py:60-66`). `README.md:39` documents it: "treat those logs as containing IP addresses". | CLOSED (accepted, documented) |
| T-02-24 | high | mitigate | `Dockerfile:15` creates uid 10001 and `:19` sets `USER app` (final stage). `test_runs_as_exactly_one_non_root_user_with_uid_10001` passes. The CI docker job asserts `id -u != 0` (`ci.yml:171-173`). | CLOSED |
| T-02-25 | high | mitigate | `Dockerfile:10-11` copies only `pyproject.toml`, `uv.lock` and `src`. `.dockerignore` excludes legacy, tests, scripts, `.planning`, `.claude`, `.env*` and `*.md`. There is no ENV or ARG holding a key and DEMO_MODE is not set. `test_container_files.py` enforces these, and `ci.yml:174` checks that legacy modules and pytest are not importable. | CLOSED |
| T-02-26 | med | mitigate | `Dockerfile:2,3,14` pin the python (twice) and uv images by tag and sha256. `test_every_from_and_the_uv_image_are_pinned_by_tag_and_digest` asserts it. Both digests resolve at their registries. | CLOSED |
| T-02-27 | low | accept | `Dockerfile:21-22` HEALTHCHECK probes `/health` with Python and a 2 s timeout. The CI docker job probes `/health` and `/ready` (`ci.yml:159-162`). | CLOSED (accepted) |
| T-02-28 | high | mitigate | `cache.py:24-25` keys on the stripped, casefolded query plus the demo flag. The query regex is at `analyze.py:28-36`. A value is stored only after `compute()` returns (`cache.py:90-98`), and exceptions are never stored. `test_errors_are_never_cached` and the unit tests pass. | CLOSED |
| T-02-29 | med | mitigate | `cache.py:33,39-41` sets `maxsize=256` with a 600 s TTL. `test_defaults_are_ttl_600_and_256_entries` and `test_bound_evicts_the_least_recently_used_entry` pass. | CLOSED |
| T-02-30 | med | mitigate | A hit returns the stored object (`cache.py:80-82`). `test_put_then_get_returns_the_very_same_object`, `test_hit_replays_the_original_data_as_of` and `test_hit_does_not_restamp_an_old_data_as_of` pass. `analyze.py:99` sets the `X-Cache` header. | CLOSED |
| T-02-31 | med | mitigate | One `threading.Lock` guards every access (`cache.py:42,58,63,79`). `compute()` runs outside the lock (`:90`). `test_concurrent_mixed_access_raises_nothing`, `test_get_and_put_both_take_the_lock` and the single-flight tests pass. | CLOSED |
| T-02-32 | high | mitigate | `gnews.py:38-43` sets 3 attempts, an 8 s budget and retries only on 500/502/503/504 and timeout or connect errors. 4xx, 429, 3xx and a bad 200 payload are not retried. `tests/test_retries.py` asserts exact call counts, and the WR-05 budget and the 600 s cache bound exposure further. | CLOSED |
| T-02-33 | high | mitigate | `gnews.py:109` logs code and upstream status only, `:244-249` logs attempt, code and status, and `:110` raises `from None`. `test_retry_logs_carry_the_attempt_number_and_no_key_or_url`, `test_exhausted_retries_raise_from_none_without_key_or_url` and `test_no_key_or_url_in_logs` pass. | CLOSED |
| T-02-34 | high | mitigate | `gnews.py:133` sets `allow_redirects=False`, and a 3xx maps to a non-retryable 502 (`:189-195`). `test_redirect_is_not_followed_and_maps_to_502` and `test_a_redirect_is_never_followed_or_retried_through_the_endpoint` pass. The key is sent only in the `X-Api-Key` header (`:129`). | CLOSED |
| T-02-35 | low | accept | The slow-drip limitation is documented in the code comment at `gnews.py:214-218`, which cites T-02-35. | CLOSED (accepted, documented) |
| T-02-36 | high | mitigate | `analyze.py:55-57` makes `validate_cascade` gate `load_demo_fixture`. The label check is at `:53`. `app.py:42-46` loads the fixture at startup in demo mode. `test_cascade_gate.py` covers the loader error, the generic 500, and startup failure. The sha256 pin and the generator `--check` still pass. | CLOSED |
| T-02-37 | low | accept | `core/cascade.py:14-16` and `analyze.py:49-51` document that the fixture is validated and never reordered (D-19). `test_sorting_the_committed_fixture_would_change_at_least_one_cascade` records it. | CLOSED (accepted, documented) |
| T-02-38 | med | mitigate | `cascade.py:82-111` uses an `on_path` set and raises `CascadeError` on cycles. `_index` (`:70-79`) rejects duplicates. The unit and Hypothesis property tests pass (cycle, self-parent, duplicate). | CLOSED |
| T-02-39 | high | mitigate | All 12 `uses:` lines are pinned by 40-hex SHA with a `# vX` comment. Permissions are read-only, every job has `timeout-minutes`, and every checkout has `persist-credentials: false`. `tests/test_ci_workflow.py` enforces these. | CLOSED |
| T-02-40 | high | mitigate | There is no `secrets.` anywhere in the workflow. The docker job runs with `DEMO_MODE=true` and no key (`ci.yml:156`), and `test_docker_job_needs_no_uv_and_no_secret_environment` asserts it. The gitleaks job and the three gitleaks scripts are byte-identical to the end of Phase 1 (402d8c8). The installer verifies a pinned sha256 (`install_gitleaks.sh:17,53`). | CLOSED |
| T-02-41 | low | mitigate | The audit job (`ci.yml:124-143`) uses `uv export --locked` and `pip-audit --require-hashes`. There is no `--ignore-vuln`, and `test_no_job_skips_failures` requires a dated comment if one is added. A local run of the same commands found no known vulnerabilities. | CLOSED |
| T-02-42 | med | mitigate | `pyproject.toml:61-64` has `fail_under = 96` with a "may only be raised" comment (measured 98.342 minus 2). `tests/test_coverage_config.py` checks it. The negative control confirmed the gate fires (exit 2). | CLOSED |
| T-02-SC (plans 01, 02) | high | mitigate | These plans predate the uv adoption. The requirements files were only deleted in 1c8cfe2, and nothing new was installed. | CLOSED |
| T-02-SC (plan 03) | high | mitigate | The legitimacy audit is at `02-RESEARCH.md:219-237` (no SLOP verdicts), and the owner waiver is D-26. All 72 packages in `uv.lock` come from the pypi.org registry with hashes, and `pip-audit` is clean. | CLOSED |
| T-02-SC (plans 04-12) | high | mitigate | `uv.lock` has not changed since 1c8cfe2, and pyproject changes since then are tool config only. `package.json` is untouched. The Dockerfile installs with `--frozen` or `--locked --no-dev --no-editable`. | CLOSED |

## Accepted risks

- **T-02-17 (low):** `/health` and `/ready` are unauthenticated and not rate limited, so orchestrators can probe them. `/health` returns a constant body; `/ready` runs only registered checks under a 2 s timeout and exposes no data. Documented in the plan and the module docstring.
- **T-02-22 (low):** slowapi's own WARNING line (`ratelimit ... exceeded`) carries the client address. The 429 body never contains it. Documented at `README.md:39` ("treat those logs as containing IP addresses"); revisit with Phase 6 hosting.
- **T-02-27 (low):** the container HEALTHCHECK is a liveness probe of `/health` only (Python, 2 s timeout); readiness is `/ready`, exercised by the CI docker job.
- **T-02-35 (low):** a sync handler can hold one threadpool thread for about 8 s while retrying, and a drip-fed upstream body can exceed the budget because `requests` timeouts are per read. Documented in the code comment at `gnews.py:214-218`; accepted because GNews bodies are tiny.
- **T-02-37 (low):** `order_events` is not applied to the served body; the fixture is validated and never reordered (D-19). Documented in `core/cascade.py:14-16` and `analyze.py:49-51`.
- **Pre-rotation GNews key in git history (owner decision, carried from Phase 1 T-01-11):** the key is in history at `1fedcd2`, which is before the scan floor `a5dd825`. It also appears as removed lines only in `51dea4b`, the Phase 1 commit that removed it. There are zero occurrences in the HEAD tree and zero added lines after the floor. The owner rotated the key and chose no history rewrite. No key value is recorded in this file.

## Review findings that overlapped a threat

This section maps `02-REVIEW.md` findings onto the register above (the mapping is by control and file, not a re-audit). The review ran before this audit: all eight confirmed findings were fixed in atomic commits and HEAD `65aabff` already contains them, so the auditor closed the threats below against the post-fix code. None of these findings reopened a threat, and no `Threat Flags` were raised by any SUMMARY (unregistered flags: none).

### Confirmed findings (all fixed)

| Finding | Commit | Overlapping threat(s) | Effect on the threat |
|---|---|---|---|
| CR-01 (critical): limiter keyed buckets by request URL, so path-parameter `LimitedRouter` routes were unlimited | `a60574b` | T-02-20 | The mitigation as first shipped would have failed open for routes like `/v1/claims/{id}` (latent: no `/v1` route exists yet). T-02-20 is closed only on the fix: `key_style="endpoint"` at `limits.py:44` plus the path-parameter probe test in `test_v1_limits.py`. |
| WR-01: CORS exposed no response headers, so a browser could not read `Retry-After` or `X-Cache` | `d73326a` | T-02-12, T-02-13, T-02-19 | Not a security gap in the CORS allow-list (T-02-12 and T-02-13 hold). It made the documented 429/503 `Retry-After` contract of T-02-19 readable by the cross-origin frontend; pinned by a CORS test. |
| WR-02: no single-flight on cache miss, so concurrent identical queries each hit the provider | `b6c649e` | T-02-19, T-02-28, T-02-31, T-02-32 | Tightens the quota-exposure bound that T-02-19 and T-02-32 rely on; the single-flight tests are cited as T-02-31 evidence, and failures are still never cached (T-02-28). |
| WR-03: readiness checks had no timeout, so one hung check starved the sync thread pool | `9a7ea8f` | T-02-18, T-02-17 | The fail-closed-on-timeout evidence for T-02-18 (`readiness.py:86-88`) comes from this fix. The accepted-risk rationale of T-02-17 (a bounded `/ready`, 2 s timeout) depends on it. |
| WR-04: the 8 s retry budget could be overshot by the connect timeout (about 11 s) | `a7b7be1` | T-02-32, T-02-35 | Restores the 8 s total budget that T-02-32 states (connect at most half the remaining budget). DNS time and slow-drip reads remain the documented limitation accepted as T-02-35. Two Phase 1 tests were retargeted to the stronger sum invariant (recorded as row 10 of the Phase 1 test edits table in `02-VALIDATION.md`). |
| WR-05: the per-IP limit did not bound total GNews usage; one client could exhaust the daily quota | `ec0ea31` | T-02-19, T-02-32 | Added the process-wide `UpstreamBudget` (100 calls per rolling day, 503 `upstream_budget_exhausted` with `Retry-After`). Bounded, not eliminated; see the T-02-19 residual below. |
| WR-06: a cache hit re-stamping `data_as_of` passed the whole suite | `0f58c1e` | T-02-30 | Closes a test gap in the evidence for T-02-30 (mutation-checked); `test_hit_does_not_restamp_an_old_data_as_of` is cited as evidence. |
| WR-07: the docker job `/health` probe did not retry connection resets | `f70b25d` | T-02-27, T-02-40 | The probe is part of the CI docker job evidenced by T-02-27 (accepted) and T-02-40. Static check only: the job itself has not been run (no Docker daemon, no Actions run). |

### Dismissed candidates that touch a registered control

The 15 dismissed candidates were deliberately left unchanged and stay as informational notes in `02-REVIEW.md`. These ten sit next to a register row; none was raised by the auditor as a gap in that row's mitigation.

- IN-01 (`FORWARDED_ALLOW_IPS` entries not validated; a hostname is silently never trusted): T-02-21. Fails closed.
- IN-02 (`cascade_events_from` lets `OverflowError` escape for extreme timestamps): T-02-38, same module as the cycle and duplicate guards.
- IN-03 (CORS preflight rejections are `text/plain` 400, not problem+json; a documented known limitation in `tests/test_cors.py`): T-02-12.
- IN-05 (CORS origin validator accepts entries a browser never sends): T-02-12. Fails closed.
- IN-07 (coverage ratchet enforced by a comment only): T-02-42.
- IN-09 (both legacy-isolation proofs miss computed dynamic imports): T-02-04.
- IN-10 (frozen-file exclusions are not force-excluded): T-02-10.
- IN-11 (Dockerfile CR guard is vacuous and nothing pins `.gitattributes`): T-02-01, T-02-25.
- IN-12 (HEALTHCHECK honours ambient proxy variables for the loopback probe): T-02-27 (accepted).
- IN-14 (floating `# syntax=docker/dockerfile:1` frontend undermines digest pinning): T-02-26. The auditor verified the pinned python and uv image digests; the BuildKit frontend is outside that check.

The other five (IN-04, IN-06, IN-08, IN-13, IN-15) do not map to a registered threat. IN-13 (`scripts/smoke_app.py` is presented as a check but nothing runs it) is worth noting: the plan for T-02-25 cites the smoke script, but the audit's T-02-25 evidence rests on `test_container_files.py` and `ci.yml:174` instead.

## Residual observations (informational, none open)

- **T-02-19 residual (from WR-05):** one client can still drain the shared 100/day provider budget and cause 503 for other users. The service never overruns the provider quota, but the exposure is bounded, not eliminated. A per-address bucket for IPv6 /64 clients is not addressed.
- **Catch-all edge case:** `CatchAllMiddleware` (`catchall.py:41-42`) re-raises when the response has already started, so a server-level traceback could log exception text. This edge case is outside the declared T-02-14 mitigation. As in Phase 1, uvicorn's server log is operator-side only.
- **`LimitedRouter` coverage:** it wraps `add_api_route` only. Routes added through `add_route`, `mount` or websockets would bypass the limit. No `/v1` routes exist yet; Phase 3 registrars should avoid those registration paths.
- **Carried from Phase 1:** whether the CI jobs are required for merging is a GitHub branch-protection setting, not verifiable from the repo.
- **Phase 1 residuals closed here:** transitive dependencies are now hash-pinned (`uv.lock`, T-02-07) and `pip-audit` runs in CI (T-02-41); CORS is a configured allow-list (T-02-12) and `/analyze` is rate limited (T-02-19), where Phase 1 had `allow_origins=["*"]` and no limiting; 500 responses now carry CORS headers for an allowed origin (T-02-13), where Phase 1 had none.

### Not verified in this audit

- The GitHub Actions SHA-to-tag mapping, because GitHub API access was disabled in the audit session.
- The gitleaks scan was not re-run by the auditor, because no binary was installed. The gitleaks job and its three scripts are unchanged from the end of Phase 1, and the auditor's own key-count and 32-hex scans were clean. The review pass ran `scripts/gitleaks_scan.sh` clean at the end of its fixes.
- The CI docker job and a real image build, because there is no Docker daemon in the container. This matches the recorded D-26 human follow-up. No docker build or GitHub Actions run is claimed to have passed.
- Follow-up: confirm CI green on GitHub after the push (the Actions run itself has not been observed from this container).
