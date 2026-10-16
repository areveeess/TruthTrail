---
phase: 01-secure-honest-foundation
status: secured
threats_open: 0
threats_total: 39
asvs_level: 1
block_on: high
audited: 2026-10-16
head: 8b52703
post_audit_fixes: 403e05e
---

# Phase 1 Security Verification

Verdict: **SECURED** (39/39 threats closed: 37 mitigate, 2 accept). Audited by `gsd-security-auditor` against code, tests, scripts and workflow at HEAD `8b52703`; the register with per-threat evidence (T-01-01 .. T-01-38, T-01-SC) is in the auditor's report and each plan's `<threat_model>`.

## Accepted risks
- **T-01-11:** the pre-rotation GNews key remains in git history (commit `1fedcd2`). Owner rotated the key and chose no history rewrite. The scan floor `a5dd825` excludes that history by design (D-09, D-20).
- **T-01-29:** the OpenAPI document is public and exposes no secret, host, path or environment detail (verified: one path, seven schemas).

## Audit gap found afterwards, now fixed
The auditor closed T-01-30/T-01-31 (blocking secret scan) on HEAD `8b52703`. The independent code review (`01-REVIEW.md`) then found **CR-01**: with `cancel-in-progress: true`, a push-range scan (`before..sha`) could leave a cancelled run's commits unscanned (key added in push 1, deleted in push 2). Fixed in `480d334`: push events now scan `floor..sha`, covered by the selftest scenario `deleted-key-from-floor`. Related hardening in the same pass: no redirect following with the key header (WR-01), malformed keys rejected before any upstream call (WR-02), fail-closed working-tree export (WR-06), full transitive pins (WR-05), `persist-credentials: false` and job timeouts (IN-04). Post-fix state: 271 passed / 10 strict xfails, gitleaks scan of `floor..HEAD` clean, selftest 11/11.

## Residual observations (informational, none open)
- Transitive dependencies are now version-pinned but not hash-pinned; uv lockfile and pip-audit arrive in Phase 2 (ENG-02, ENG-04).
- Uvicorn's server log can carry a traceback for unhandled errors (operator side only; client body and app logs are clean).
- 500 responses carry no CORS headers; a provider `Retry-After: 0` is passed through (IN-02, IN-03 deferred).
- CORS is `allow_origins=["*"]` and `/analyze` has no rate limiting: Phase 2 (ENG-06).
- Whether the CI jobs are *required* for merging is a GitHub branch-protection setting, not verifiable from the repo.
- The GitHub Actions run itself has not been observed from this container (follow-up: confirm CI green after the push).
