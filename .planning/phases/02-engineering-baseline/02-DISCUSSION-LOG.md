# Phase 2: Engineering Baseline - Discussion Log

> Human reference only (audits, retrospectives). Not consumed by downstream agents.

**Date:** 2026-10-17
**Areas discussed (all four selected by the owner):** Legacy modules vs "unreachable"; Package layout and entrypoint; Rate limit, cache and retries; Tooling strictness and CI shape.

## Legacy modules vs "unreachable"
Questions asked: where the legacy simulator and user pool live; what happens to the keyword scorer; what the cascade-ordering property tests target.
Options offered: legacy/ outside the package vs repo root vs tests/scripts; move risk rules untouched vs fix now; new core.cascade functions vs fixture-only properties.
Owner response: skipped the questions and replied "ok you know what do whatever you reccomend".
Outcome: recommended options taken (D-01, D-02, D-03).

## Package layout and entrypoint; Rate limit, cache and retries; Tooling strictness and CI shape
Not asked one by one after the owner's reply. Claude took the recommended option for each choice and wrote them as D-04..D-18, folding the deferred Phase 1 review items IN-02, IN-03 and IN-05 where Phase 2 naturally covers them.

## Review gate
The owner asked to review each stage, so CONTEXT.md is presented for review before research and planning start.
