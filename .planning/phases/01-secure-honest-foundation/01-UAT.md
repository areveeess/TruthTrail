---
status: testing
phase: 01-secure-honest-foundation
source: 01-01-SUMMARY.md, 01-02-SUMMARY.md, 01-03-SUMMARY.md, 01-04-SUMMARY.md, 01-05-SUMMARY.md, 01-06-SUMMARY.md
started: 2026-10-16T11:09:01Z
updated: 2026-10-16T11:09:01Z
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

number: 1
name: Live smoke test with a real GNews key
expected: |
  With a real key in GNEWS_API_KEY, GET /analyze?query=vaccine returns 200 with a
  {results, meta} envelope and meta.synthetic false. With a deliberately wrong key it
  returns 502 application/problem+json with code upstream_unauthorized (never a 200).
awaiting: user response

## Tests

### 1. Live smoke test with a real GNews key
expected: Real key gives 200 envelope with meta.synthetic false; wrong key gives 502 problem+json upstream_unauthorized. The assistant does not call the real API; the user runs it locally and reports status codes.
result: [pending]

### 2. Old key revoked
expected: The key that was in commit 1fedcd2 is revoked or deleted at GNews, not merely replaced.
result: [pending]

### 3. Key-policy acceptance
expected: A malformed key (whitespace or non-ASCII) is rejected at startup instead of being trimmed. User accepts this, or asks for trimming.
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps

[none yet]
