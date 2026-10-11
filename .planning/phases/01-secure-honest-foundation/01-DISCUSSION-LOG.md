# Phase 1: Secure & Honest Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-11
**Phase:** 1-Secure & Honest Foundation
**Areas discussed:** `/analyze` response shape; Error contract; Secret scan & history; Tests & copy guard

**Process note:** The owner selected all four areas. Area 1 and the first two questions of Area 2 were answered by the owner. On the third Area 2 question the owner replied, instead of choosing an option: "after this take all the decisions urself on auto unless extremely necessary im going afk". All remaining questions (Area 2 Q3, all of Area 3, all of Area 4) were therefore resolved by Claude using the recommended option, were **not** reviewed by the owner, and are marked "(auto)" in CONTEXT.md.

---

## `/analyze` response shape (owner-answered)

| Option | Description | Selected |
|--------|-------------|----------|
| Envelope object (Recommended) | `{results, meta:{synthetic,data_as_of,source_status}}`; breaks the old bare list, provenance explicit | ✓ |
| Keep list + headers | Provenance in X-* headers; non-breaking but easy to drop | |
| Keep list + per-item fields | Provenance repeated on every item; empty results carry none | |

**User's choice:** Envelope object

| Option | Description | Selected |
|--------|-------------|----------|
| Static fixture JSON (Recommended) | Generated once from the simulator with a fixed seed, committed, flagged synthetic | ✓ |
| Live simulator, seeded | Keep calling simulate_spread behind DEMO_MODE | |

**User's choice:** Static fixture JSON

| Option | Description | Selected |
|--------|-------------|----------|
| Label the method (Recommended) | Add `risk_method: 'keyword_baseline'` | ✓ |
| Leave as-is | No extra field | |

**User's choice:** Label the method

| Option | Description | Selected |
|--------|-------------|----------|
| 200 with empty results (Recommended) | `{results: [], meta:{source_status:'empty'}}` | ✓ |
| 404 Not Found | Treat no articles as not found | |

**User's choice:** 200 with empty results

---

## Error contract (first two questions owner-answered)

| Option | Description | Selected |
|--------|-------------|----------|
| RFC 9457 problem+json (Recommended) | Standard fields plus `code` and `upstream` extensions | ✓ |
| Simple custom envelope | `{error:{code,message,upstream}}` | |

**User's choice:** RFC 9457 problem+json

| Option | Description | Selected |
|--------|-------------|----------|
| Split 502 vs 503 (Recommended) | 502 for bad upstream answers; 503 + Retry-After for unreachable/throttled | ✓ |
| Always 502 | Simpler; no retry signal | |
| Always 503 | Hides permanent faults behind a retry hint | |

**User's choice:** Split 502 vs 503

| Option | Description | Selected |
|--------|-------------|----------|
| Fail fast unless DEMO_MODE (Recommended) | Refuse to start without a key unless DEMO_MODE=true | ✓ (auto) |
| Boot degraded, 503 on use | Start anyway; 503 `not_configured`; /ready false | |

**User's choice:** Not chosen — the owner delegated this to Claude ("take all the decisions urself on auto").
**Notes:** Resolved to the recommended option (D-08).

---

## Secret scan & history (resolved on auto; options not shown to owner)

| Option considered | Selected |
|-------------------|----------|
| Working tree + new-commit range, no baseline, gitleaks | ✓ (auto) |
| Full-history scan with a baseline ignoring the rotated key's finding | |
| Custom in-repo regex script | |

**Notes:** A full-history blocking scan would fail permanently on the rotated key in commit `1fedcd2`; scanning the working tree and each push's new commit range keeps CI green while still failing any new leak, including a commit-then-delete. No history rewrite (owner standing rule). Exact gitleaks version and install method to be verified by the researcher.

---

## Tests & copy guard (resolved on auto; options not shown to owner)

| Option considered | Selected |
|-------------------|----------|
| Golden tables for stable behaviour + strict xfail for known defects | ✓ (auto) |
| Pin everything as-is, bugs included, delete tests when fixed | |

| Option considered | Selected |
|-------------------|----------|
| Moderately strict copy guard (README, docs, OpenAPI strings; truth/fake-news-detection claims, FAKE badge, AI-based/AI-powered until a model exists; inline allow marker; tests/ and .planning/ excluded) | ✓ (auto) |
| Narrow guard ("detects the truth" and a FAKE badge only) | |

---

## Claude's Discretion

Settings mechanism, exact error `code` names, fixture seed/location, test layout, GitHub Action pins, README wording, definition of `data_as_of`, and whether `models.Event` is reused.

## Deferred Ideas

- Purge the old key from git history (explicit owner request only)
- Retire or reduce `/analyze` (Phase 3 scoping question)
- CORS, rate limiting, caching, retries (Phase 2)
- Local pre-commit secret hook; GitHub native secret scanning / push protection (owner repo setting)
