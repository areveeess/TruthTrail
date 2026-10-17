---
status: partial
phase: 01-secure-honest-foundation
source: 01-01-SUMMARY.md, 01-02-SUMMARY.md, 01-03-SUMMARY.md, 01-04-SUMMARY.md, 01-05-SUMMARY.md, 01-06-SUMMARY.md
started: 2026-10-16T11:09:01Z
updated: 2026-10-17T15:47:21Z
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

number: 2
name: Old key revoked
expected: |
  The key that was in commit 1fedcd2 is revoked or deleted at GNews, not merely replaced.
awaiting: user response

## Tests

### 1. Live smoke test with a real GNews key
expected: Real key gives 200 envelope with meta.synthetic false; wrong key gives 502 problem+json upstream_unauthorized. The assistant does not call the real API; the user runs it locally and reports status codes.
result: pass
reported: "Real key: 200 envelope, meta.synthetic false, source_status ok, real headline (run on Windows 2026-10-17). Well-formed wrong key (32 chars): 502 upstream_unauthorized, log upstream_status=401. Malformed key ('wrong'): 502 upstream_bad_response, log upstream_status=400."
note: "Assumption A1 refined: GNews answers a malformed key with 400, a well-formed wrong key with 401. Both surface as honest 502 problem+json. 400 deliberately stays upstream_bad_response because a 400 can also mean a bad query."

### 2. Old key revoked
expected: The key that was in commit 1fedcd2 is revoked or deleted at GNews, not merely replaced.
result: [pending]

### 3. Key-policy acceptance
expected: A malformed key (whitespace or non-ASCII) is rejected at startup instead of being trimmed. User accepts this, or asks for trimming.
result: [pending]

## Summary

total: 3
passed: 1
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps

[none yet]
