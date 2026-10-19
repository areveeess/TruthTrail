---
phase: 3
document: source spike decision
ratified: false
ratified_by: ""
ratified_on: ""
ratification_source: ""
ratification_quote: ""
od1_retention: ""
od2_merge: ""
od3_tracking: ""
schema_via_uri: ""
dependencies_approved: ""
pseudonym_scheme: ""
windows_result: pending
recommended_parameters: {}
recommended_options: {}
ratified_parameters: {}
run_windows: []
---

# Phase 3 source spike: decision document

Plan 03-01, requirement DATA-01. CONTEXT calls this file 03-SPIKE-DECISION.md; this phase uses the
shorter name 03-SPIKE.md and no second copy exists. Every number is measured, with its window
label, from the real run recorded in the Run log. Every recommendation is PROVISIONAL until the owner
ratifies it. Nothing here is synthetic.

## How this document is used and the gate rule (D-02)

> D-02: Plan 03-01 ends at a `checkpoint:decision` for the owner. No Alembic revision, SQLAlchemy
> model, database dependency, collector, enrich, `/v1` or news-job code may be written or executed
> until this document carries a ratification block (`ratified: true`, `ratified_by: owner`,
> `ratified_on: <date>`, and the chosen options for OD-1, OD-2, OD-3 or the explicit instruction to
> take the recommended defaults). Ratification comes only from the owner's own message or the
> owner's own edit of this file; no agent, subagent or workflow output counts as ratification.

The machine gate is `python scripts/check_spike_ratified.py` (add `--json` for the effective
parameter values). It exits 0 only after the owner ratified; plans 03-02 to 03-12 run it first and
stop otherwise. The committed document has `ratified: false` because no agent may ratify. The owner
ratifies by replying at the checkpoint (see "Ratification block") or by editing the front matter
of this file.

## Run log

[[MEASURE: run log table from windows.json: label, host, dialect, exact bounds, UTC start and end, stop reason, measured stream span, frames, bytes, raw-log sha256 and size, tool git sha, ephemeral websockets install check]]

## Source terms (S-10)

[[MEASURE: dated quotes of the Bluesky terms of service, privacy policy, Developer Guidelines and the GNews Free-plan terms, with URL and the UTC date read; plain statement that the terms are silent on research and that this is not legal advice]]

## Reachability and environment (S-1, S-12)

[[MEASURE: four host rows and the flags needed through the container proxy]]

## Live-tail volume (S-2)

[[MEASURE: volume tables per window and combined]]

## Cursor lookback and catch-up (S-3)

[[MEASURE: cursor table, then the cadence and catch-up arithmetic of RESEARCH F-05 recomputed from the measured events per hour]]

## Time semantics (S-4)

[[MEASURE: inversions, seq monotonicity, createdAt skew, child-before-parent]]

## Edge semantics (S-6)

D-12 restated: `edge_kind` is `root`, `reply`, `quote` or `repost`, a fact of the record. A reply keeps
a quote target as the secondary `quoted_uri`. A repost is an inferred fan-out hanging off its subject
(the repost-star caveat): it has no depth, never chains and is never attached to another repost.
Reposts carry an optional `via` strong reference to another repost record (RESEARCH F-07).

[[MEASURE: shapes and ambiguity table, including the via share]]

## Cascade yield (S-5)

[[MEASURE: yield tables, outcome probabilities, cascade size distribution, cap fill and sampling shares]]

## Deletes and account events (S-7)

[[MEASURE: delete rates, time to delete with the censoring horizon, account statuses, sync rate]]

## Storage footprint (S-8)

[[MEASURE: bytes per row and the projection per candidate bound set]]

## Merge frequency (S-9)

[[MEASURE: cross-cascade children, shared canonical URLs, seed-eligible quotes]]

## Reconnect (S-11)

[[MEASURE: reconnect table]]

## Windows result (S-12)

Owner action, non-blocking: PENDING-OWNER (see the checkpoint). `windows_result` stays `pending`
until the owner pastes the summary of a 5-minute run on Windows.

## Coverage cross-check (S-13)

[[MEASURE: AppView cross-check table]]

## Draft allowlist

Path `src/truthtrail/data/seed_domains.txt`. [[MEASURE: entry count, category counts and the category rules]]

## Package legitimacy audit

| Package | Registry | Age (first upload) | Source repo | Seam verdict | Independent evidence | Owner verdict |
|---|---|---|---|---|---|---|
| sqlalchemy 2.1.5 | PyPI | 2006 | github.com/sqlalchemy/sqlalchemy | SUS (too-new, unknown-downloads) | named by CONTEXT and STACK.md; pip-audit clean | PENDING-OWNER |
| psycopg 3.3.6 with the binary extra (psycopg-binary 3.3.6) | PyPI | 2021 | github.com/psycopg | SUS (unknown-downloads) | official binary extra; exercised | PENDING-OWNER |
| alembic 1.20.0 | PyPI | 2011 | github.com/sqlalchemy/alembic | SUS (unknown-downloads) | same author organisation as SQLAlchemy | PENDING-OWNER |
| websockets 17.2 | PyPI | 2013 | github.com/python-websockets/websockets | SUS (too-new, unknown-downloads) | named in Bluesky's own Jetstream Python example; used here as an ephemeral install | PENDING-OWNER |
| mako, markupsafe, tzdata | PyPI | long-established | - | not checked individually | transitive via alembic and psycopg; present in the lock diff | PENDING-OWNER |

The seam answers SUS for every package because its download-statistics source is unreachable from
the container and because the latest release is recent; these are limits of the seam, not signals
about the packages. Adding the four direct dependencies (eight added packages in `uv.lock`) happens
in plan 03-02 only after the owner approves this table. [[MEASURE: the PyPI JSON check of websockets 17.2 done on the run date]]

## Schema hedges (`via_uri`)

[[MEASURE: the measured via share and the recommendation for the nullable via_uri column]]

## Pseudonymisation scheme (D-17, ONE-WAY DOOR)

This is a decision block, not a measurement. It is the one item of this document that cannot be
undone cheaply, so it needs its own explicit confirmation.

**The exact scheme.** Every stored identifier is a keyed hash, not a raw DID or URI.

- `accounts.pseudonym` is the lowercase base32 (no padding) of `HMAC-SHA256(PSEUDONYM_SECRET,
  "acct" NUL did)`, truncated to 16 characters (80 bits).
- Every `uri`, `parent_uri`, `reply_root_uri`, `quoted_uri` and `root_uri` column holds the URI key:
  the lowercase base32 (no padding) of `HMAC-SHA256(PSEUDONYM_SECRET, "uri" NUL canonical at:// URI)`,
  truncated to 20 characters (100 bits). The domain-separated prefixes `acct` and `uri` keep the two
  spaces from colliding.
- No DID, no handle, no `rkey`, no follower count, no display name, no avatar and no clear `at://`
  URI is ever stored. The API shows at most the first 8 characters of a pseudonym.
- `PSEUDONYM_SECRET` is at least 32 random bytes, read from the environment only by the processes
  that ingest or erase (collector, jobs); the API process never needs it. They refuse to start
  without it and error text never contains it.

**Why a keyed hash and not the raw DID.** An `at://` URI contains the author's DID, so a raw URI
column would defeat account pseudonymisation. A DID is a stable global identifier that joins to a
person's handle and full public history, which would make the database a ready-made index of who
engaged with which claim, a profiling asset beyond this tool's purpose (the tool analyses claims,
not people). No feature needs the raw value: unique-account counts, parent resolution and delete
matching all work on a deterministic key.

**Why HMAC with a server-side secret and not a plain, fixed-salt or per-row-salted hash.** The DID
space is enumerable from the public directory, so an unkeyed or publicly salted hash is reversible
by a dictionary attack. A random per-row salt would break the equality joins the cascade needs.
Only a single secret key keeps the joins and resists the dictionary.

**Rejected alternatives.** The raw DID or URI (profiling asset); a plain SHA-256 or a fixed public
salt (dictionary-reversible); a per-row salt (breaks joins); a token table mapping DIDs to random ids
(would store the DIDs it is meant to hide).

**What you give up.** There is no "open this post on Bluesky" link in v1 (the claim is the linked
article, which the UI shows). The secret is long-lived, so rotating it re-keys every identifier,
which is a rebuild.

**Honesty limits (to be stated in DOC-02).** This is pseudonymisation, not anonymisation: with
stored timestamps and, for the retention window, root text, a party holding a network archive can
still re-link a record, and a leaked secret plus a leaked database re-enables dictionary reversal.

**Cost of undoing it.** Raw identifiers are never kept, so past data cannot be recovered in clear
and stored rows cannot be re-keyed (the raw values do not exist). A different scheme later means
re-collecting from scratch, and a changed key re-keys every row. Plans 03-04 onward compute keyed
identifiers; the schema, the writer, the delete path and the API all depend on this choice.

**Measured fact the spike supplies.** [[MEASURE: bytes per event row from S-8, which already include the 20-character keyed identifiers]]

**Explicit confirmation required.** Only the token `pseudonym=d17` in the owner's reply (or the owner
setting `pseudonym_scheme: d17-hmac-v1` in the front matter by their own edit) confirms this scheme.
A blanket "ratify recommended" does not, and the gate stays closed without it. Choosing a
different scheme (`pseudonym_scheme: other`) stops the plans until the planner revises them.
Current value: PENDING-OWNER.

## OWNER DECISION OD-1: retention policy

**Question.** What is stored, for how long, and what is removed when.

**Options.** RT-1 Minimal: store no post text at all; the claim text of a root is the publisher's
link-card title; structure kept 30 days then deleted. RT-2 Short-TTL text: post text of a root is
kept 14 days from the root's `observed_at` and then NULLed; link-card title, canonical URL,
structure and counts are kept 90 days; the whole cascade is then hard-deleted; non-root events never
hold text; tombstones are purged 7 days after the delete. RT-3 Demo lifetime: root text kept for the
life of the cascade (up to the global cap).

**Trade-offs.** RT-1 has the least privacy exposure and the smallest database and fits a
headline-trained classifier, but reviewers see no author wording and Phase 4 cannot score
commentary. RT-2 gives reviewers wording during the triage window and bounds exposure, including
deletes missed during an ingest gap (a missed delete lives at most 14 days), at the cost of a purge
job and a 14-day window in which a post can be re-found by text search, which weakens the account
pseudonymisation of D-17 for roots. RT-3 gives the richest demo and the weakest privacy and terms
position.

**Facts the owner needs.** Text volume is not the binding storage constraint (a root's text is at
most 300 graphemes, about 1 KB; the events table dominates), privacy and terms are. Bluesky requires
deleting content on a user's request; the terms contain no research clause. Public posts are still
personal data; deletion propagation, minimisation and a purge job are the defence. An operator-run
erase command by DID is a small optional addition for a missed delete. The demo GIF and README
screenshots use pseudonymised data under every option.

**Measured.** [[MEASURE: S-5 roots per day and commentary share, S-8 bytes per root and runway, S-7 time to delete, S-10 terms wording]]

**Recommendation (PROVISIONAL).** [[MEASURE: recommendation with the numbers behind it]]

**What changes if you choose otherwise.** RT-1 sets `RETENTION_TEXT_DAYS` 0 (root text is never
written) and `RETENTION_CASCADE_DAYS` 30; RT-2 sets nothing and requires `0 < RETENTION_TEXT_DAYS <
RETENTION_CASCADE_DAYS`; RT-3 sets `RETENTION_TEXT_DAYS` equal to `RETENTION_CASCADE_DAYS`. The gate
derives these values from the option, so no numeric override is needed and a contradicting number
stops the gate (exit 2).

**Parameters that encode it.** `RETENTION_TEXT_DAYS`, `RETENTION_CASCADE_DAYS`,
`RETENTION_TOMBSTONE_DAYS`, `RETENTION_DORMANT_DAYS`.

## OWNER DECISION OD-2: how provisional and duplicate cascades merge

**Question.** When evidence shows two cascades overlap, do they merge.

**Situations.** (A) Re-rooting: events stored under cascade X are later shown to hang below another
tracked cascade Y; with edges stored as record facts and roots limited to top-level, non-reply,
non-quote posts this cannot happen under allowlist seeding, only if a policy promotes a reply or
quote to its own root (OD-3 option C). (B) Claim-level duplicates: several independent roots link
the same article. (C) Stream-order inversion where a child arrives before its root: handled by D-14
(dropped and counted), not by merging.

**Options.** M0 Never merge: a cascade's identity is fixed when its root is first stored; overlap is
recorded as a relation and shown. M1 Never merge, group by claim: M0 plus `cascades.claim_id` so the
API can filter and summarise all cascades that share a canonical article URL. M2 Derived full merge:
enrich derives membership from the parent graph and absorbs cascade X into Y, giving one tree per
story (outside the plans).

**Trade-offs.** M0 and M1 are order-independent by construction, keep cascade ids and "observed
since" stable and need no collector code; they leave duplicates visible. M2 gives one canonical tree
but churns ids and permalinks, changes orphan and "observed since" semantics retroactively, adds a
merge path that needs its own determinism tests and buys nothing under allowlist seeding.

**Facts the owner needs.** OD-2 is conditional on OD-3: with option A only situation (B) exists and
M1 settles it at no cost; with option C situation (A) appears and M2 becomes worth considering. The
UI feed (Phase 5) may want duplicates grouped; M1 gives it the key.

**Measured.** [[MEASURE: S-9 rates of situations A and B and the OD-3 interaction]]

**Recommendation (PROVISIONAL).** [[MEASURE: recommendation]]

**What changes if you choose otherwise.** M0 sets `CASCADE_MERGE_POLICY` none, which also switches
the claim_id filter of `GET /v1/cascades` off; M1 sets claim_group. Both are parameter changes the
gate derives itself. M2 is outside the plans and requires the planner to revise plans 03-04 to 03-07
before they run (the gate exits 3).

**Parameters that encode it.** `CASCADE_MERGE_POLICY` in none, claim_group, derived (only claim_group
and none are built).

## OWNER DECISION OD-3: tracked-root selection policy and its bounds

**Question.** Which top-level posts become tracked roots (everything else is dropped at the adapter
boundary), and how much may be stored.

**Options.** A Allowlist seed: a top-level post (not a reply, not a quote) becomes a root when its
external-embed or link-facet URL has a canonical host on a committed, reviewable allowlist of
English-language news organisations and fact-checkers (at most 60 domains, each entry commented with
its category), and passes the hygiene filters. B Claim-URL match (additive): also seed when the
canonical URL equals the URL of a stored news headline from the DATA-06 job; precise, cheap, low
yield; it is built and tested in plan 03-05 but seeds nothing until headlines exist. C Engagement
promotion: keep a bounded in-memory counter of reposts, replies and quotes per untracked subject
and promote a post to root when it crosses a threshold; finds viral content of any topic but buffers
every untracked reference, stores non-news content and creates the re-rooting situation of OD-2
(outside the plans). D Authenticated search seed: needs a credential, the public host load-sheds
that endpoint with 403 and backfilled events would carry fetch time instead of stream time; rejected
for v1.

**Bounds (apply to every option, PROVISIONAL).** At most 500 active roots, a root tracks for 48 hours
of stream time after its own `observed_at`, at most 5,000 stored events per cascade (events beyond the
cap are counted in `overflow_count`, not stored), at most 300,000 stored events in total, English
only, adult self-labelled posts excluded. When a cap is reached the collector stops promoting or
storing, counts the refusals and never evicts.

**Trade-offs and facts.** The allowlist is an editorial choice and a selection bias that must be
disclosed in the dashboard and the README limitations (DOC-02); entries are chosen by category rules
(wire services, public broadcasters, IFCN-listed fact-checkers), not political lean. Yield is unknown
until S-5; the heavy tail (a few viral cascades hold most events) is why the per-cascade cap exists.
Option A needs no credential, stores only link-bearing news posts and has the smallest privacy
footprint. A first-come cap is a window bias, not a sample (RESEARCH F-06): a deterministic sampling
parameter `TRACK_SAMPLE_PER_10K` makes the cap a safety valve instead of the selector.

**Measured.** [[MEASURE: S-5 yield, cap fill time, sampling shares, outcomes; S-9 duplicates]]

**Recommendation (PROVISIONAL).** [[MEASURE: recommendation including TRACK_SAMPLE_PER_10K and the bounds]]

**What changes if you choose otherwise.** A sets `TRACK_SEED_CLAIM_URL_MATCH` false; B sets it true.
Both are parameter changes the gate derives itself. C (and D) are outside the plans and require the
planner to revise plans 03-04 to 03-07 first (the gate exits 3 on C).

**Parameters that encode it.** `TRACK_ALLOWLIST_FILE`, `TRACK_MAX_ACTIVE_ROOTS`,
`TRACK_ROOT_TTL_HOURS`, `TRACK_MAX_EVENTS_PER_CASCADE`, `STORE_MAX_EVENTS_TOTAL`,
`TRACK_REQUIRE_LANG`, `TRACK_SEED_CLAIM_URL_MATCH`, `TRACK_SAMPLE_PER_10K`.

## Fixture manifest

[[MEASURE: the manifest of the cut fixture: files, sizes, sha256, counts by kind, coverage, selection policy, windows, tool git sha]]

## Risks

[[MEASURE: A5 runner reachability, A6 rate limiting of an unauthenticated tail, single-window bias, terms status, raw logs deleted by design]]

## Recommended parameter table

[[MEASURE: the table with the arithmetic of every formula and the JSON mirrored in recommended_parameters]]

## Ratification block

Visible copy of the front matter fields (all owner-only values are PENDING-OWNER until the owner
acts; an agent never sets them):

| Field | Value |
|---|---|
| ratified | false |
| ratified_by | PENDING-OWNER |
| ratified_on | PENDING-OWNER |
| ratification_source | PENDING-OWNER (owner-message or owner-edit) |
| od1_retention, od2_merge, od3_tracking | PENDING-OWNER |
| schema_via_uri | PENDING-OWNER |
| dependencies_approved | PENDING-OWNER |
| pseudonym_scheme | PENDING-OWNER (d17-hmac-v1 only with the explicit token) |

Reply formats (every one that ratifies must carry the token `pseudonym=d17`; without it the gate
stays closed):

- `ratify recommended pseudonym=d17`
- `ratify OD-1=RT-2 OD-2=M1 OD-3=A via_uri=true dependencies=approved pseudonym=d17` (change any
  value; add numeric overrides such as `TRACK_SAMPLE_PER_10K=1250`)
- `more data: {what you want}` (no ratification; the raw logs are deleted, so a new bounded window
  is recorded)
- `revise scope: {M2, C or pseudonym=other}` (exit 3; the planner revises plans 03-04 to 03-07)

Missing token: the reply `ratify recommended` alone does not confirm the one-way D-17 scheme, so
nothing is recorded until the owner answers one question: accept D-17 as written, yes or no.
