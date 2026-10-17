---
status: complete
phase: 01-secure-honest-foundation
source: 01-01-SUMMARY.md, 01-02-SUMMARY.md, 01-03-SUMMARY.md, 01-04-SUMMARY.md, 01-05-SUMMARY.md, 01-06-SUMMARY.md
started: 2026-10-16T11:09:01Z
updated: 2026-10-17T15:49:59Z
---

## Current Test

[testing complete]

## Tests

### 1. Live smoke test with a real GNews key
expected: Real key gives 200 envelope with meta.synthetic false; wrong key gives 502 problem+json upstream_unauthorized. The assistant does not call the real API; the user runs it locally and reports status codes.
result: pass
reported: "Real key: 200 envelope, meta.synthetic false, source_status ok, real headline (run on Windows 2026-10-17). Well-formed wrong key (32 chars): 502 upstream_unauthorized, log upstream_status=401. Malformed key ('wrong'): 502 upstream_bad_response, log upstream_status=400."
note: "Assumption A1 refined: GNews answers a malformed key with 400, a well-formed wrong key with 401. Both surface as honest 502 problem+json. 400 deliberately stays upstream_bad_response because a 400 can also mean a bad query."

### 2. Old key revoked
expected: The key that was in commit 1fedcd2 is revoked or deleted at GNews, not merely replaced.
result: pass
reported: "the key is changed and deleted"


### 3. Key-policy acceptance
expected: A malformed key (whitespace or non-ASCII) is rejected at startup instead of being trimmed. User accepts this, or asks for trimming.
result: pass
reported: "trim it"
note: "Owner chose to trim rather than reject surrounding whitespace. Implemented in config.py: Settings trims leading/trailing whitespace (newline, CRLF, space, tab); whitespace inside the key and non-ASCII characters are still rejected at startup. fetch_news stays strict. Tests: TRIMMABLE_KEYS and the trim tests in tests/test_settings.py."

## Summary

total: 3
passed: 3
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]
