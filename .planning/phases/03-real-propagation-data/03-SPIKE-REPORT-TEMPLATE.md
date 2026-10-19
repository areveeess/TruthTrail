# Phase 3 source spike: measurement report template (plan 03-01)

This template is the shape of one measurement report S-1 to S-13 (CONTEXT D-01). The executor of plan
03-01 fills it from the real run into 03-SPIKE.md; the owner pastes the printed `analyze --summary`
output of a Windows run into the "Windows result (S-12)" block. Every fill-in spot below is a
double-bracket MEASURE marker; a finished report has none left. Numbers are counts, rates,
percentiles and domain names only: no account, post text or link may appear (D-18).

The `### S-2`, `### S-4`, `### S-5`, `### S-6`, `### S-7` and `### S-9` headings mirror the headings
that `scripts/bluesky_spike.py analyze --summary` prints (a test keeps the two in step).

## Windows recorded

One row per recorded window (from `windows.json`, pasted unchanged into the `run_windows` front
matter key of 03-SPIKE.md).

| Label | Host | Dialect | UTC start | UTC end | Bound (s) | Measured stream span (s) | Frames | Bytes | Stop reason | Raw log sha256 |
|---|---|---|---|---|---|---|---|---|---|---|
| [[MEASURE: label]] | [[MEASURE: host]] | [[MEASURE: dialect]] | [[MEASURE: start]] | [[MEASURE: end]] | [[MEASURE: bound]] | [[MEASURE: span]] | [[MEASURE: frames]] | [[MEASURE: bytes]] | [[MEASURE: stop]] | [[MEASURE: sha256]] |

Combined: [[MEASURE: total measured stream span in seconds]] (the floor of the gate is 3600 s of measured
stream span, the sum over windows of last minus first frame time).

### S-1 Reachability and dialect

| Host | Dialect | HTTPS status | Upgrade | Subprotocol | Handshake (s) | First frame | `kinds` honoured |
|---|---|---|---|---|---|---|---|
| [[MEASURE: host]] | [[MEASURE: dialect]] | [[MEASURE: status]] | [[MEASURE: upgrade]] | [[MEASURE: subprotocol]] | [[MEASURE: handshake]] | [[MEASURE: first frame]] | [[MEASURE: kinds]] |

Flags needed through the container proxy: [[MEASURE: flags]].

### S-2 Volume

| Measure | Value |
|---|---|
| Events per second (mean) | [[MEASURE: events/s]] |
| Per collection and operation (events/s) | [[MEASURE: by kind]] |
| Control events (account, identity, sync) per hour | [[MEASURE: control per hour]] |
| Bytes per second (uncompressed) | [[MEASURE: bytes/s]] |
| Frame size P50 / P95 / P99 / max (bytes) | [[MEASURE: frame sizes]] |
| Events per second P50 / P95 / max (per second) | [[MEASURE: per second]] |
| Events per minute P50 / P95 / max | [[MEASURE: per minute]] |
| Post creates: top-level / reply / quote / reply+quote (share) | [[MEASURE: post shares]] |

### S-3 Cursor lookback and catch-up

| Cursor | Result | First event minus cursor (s) | Replay rate (events/s) | Info frame | HTTP |
|---|---|---|---|---|---|
| [[MEASURE: cursor]] | [[MEASURE: result]] | [[MEASURE: delta]] | [[MEASURE: rate]] | [[MEASURE: info]] | [[MEASURE: http]] |

### S-4 Time

| Measure | Value |
|---|---|
| Arrival-order stream-time inversions (count, largest in seconds) | [[MEASURE: inversions]] |
| Sequence number going backwards (per host) | [[MEASURE: seq]] |
| Record createdAt minus stream time: P1 / P50 / P99 (s) | [[MEASURE: skew]] |
| createdAt more than 60 s in the future / more than 1 h old / absurd | [[MEASURE: skew counts]] |
| Child frames before their parent frame (pairs both in the log) | [[MEASURE: child before parent]] |

### S-5 Seed yield and cascades

| Measure | Value |
|---|---|
| Eligible roots per hour (draft allowlist) | [[MEASURE: roots/h]] |
| Seed decisions by reason | [[MEASURE: reasons]] |
| English share / commentary share / adult-label share of allowlisted-link roots | [[MEASURE: shares]] |
| Distinct domains and top domains (roots, distinct authors) | [[MEASURE: domains]] |
| Seconds until a 500-root cap is full | [[MEASURE: cap fill]] |
| Share of eligible roots accepted under hash sampling 10000 / 5000 / 2500 / 1250 / 625 per 10000 | [[MEASURE: sampling]] |
| P(at least one reply, quote or repost) within 15 min / 1 h / 6 h / observed horizon (n) | [[MEASURE: outcomes]] |
| Cascade children: median / P90 / P99 / max | [[MEASURE: cascade size]] |
| Reply depth distribution and orphan rate | [[MEASURE: depth]] |
| Share of tracked events held by the top 1 percent of cascades | [[MEASURE: top 1 percent]] |
| Option C counters: subjects with at least 10 / 25 / 100 references per hour | [[MEASURE: option C]] |

### S-6 Shapes and ambiguity

| Measure | Value |
|---|---|
| Reply+quote posts | [[MEASURE: reply+quote]] |
| Embed type distribution | [[MEASURE: embeds]] |
| Link source on top-level posts: card only / facet only / both / neither | [[MEASURE: link sources]] |
| Shortener links | [[MEASURE: shorteners]] |
| Reposts: subject a tracked root versus not; `via` share; `via` target seen | [[MEASURE: reposts]] |
| Quote targets that are not posts; did:web authorities; unknown embed types | [[MEASURE: odd shapes]] |

### S-7 Deletes and account events

| Measure | Value |
|---|---|
| Deletes per collection (per hour, share of creates) | [[MEASURE: deletes]] |
| Time to delete: all posts / tracked roots / tracked children (n, P50, P90, max s) and the censoring horizon | [[MEASURE: latency]] |
| Account events by status (including unknown) | [[MEASURE: accounts]] |
| Sync events per hour | [[MEASURE: sync]] |

### S-8 Storage footprint

| Table | Rows | Total bytes | Bytes per row |
|---|---|---|---|
| [[MEASURE: table]] | [[MEASURE: rows]] | [[MEASURE: bytes]] | [[MEASURE: per row]] |

Projection per candidate bound set: [[MEASURE: bound sets, steady-state MB, days to fill the budget]].

### S-9 Merge frequency

| Measure | Value |
|---|---|
| Children whose parent lies in another tracked cascade | [[MEASURE: cross cascade]] |
| Distinct roots sharing one canonical article URL (share of roots in shared groups, largest group) | [[MEASURE: url groups]] |
| Quote posts that are themselves seed-eligible | [[MEASURE: quote seeds]] |

### S-10 Terms

| Source and date read | Dated quote | Consequence |
|---|---|---|
| [[MEASURE: source]] | [[MEASURE: quote]] | [[MEASURE: consequence]] |

### S-11 Reconnect

| Measure | Value |
|---|---|
| Server-initiated closes seen during the recorded windows | [[MEASURE: closes]] |
| Deliberate disconnect and resume at last time minus 30 s: duplicates versus expected overlap | [[MEASURE: duplicates]] |
| Idle hold on a sparse filter (seconds, closed by the server, close code) | [[MEASURE: hold]] |

### S-12 Environments

Container flags: [[MEASURE: flags]]. GitHub-hosted runner reachability is a Phase 6 verification item.

#### Windows result (S-12)

How to produce it (owner, native Windows 11, PowerShell, Python 3.13, uv; about 6 minutes). From the
repository root run `uv run --no-project --python 3.13 --with websockets==17.2 python scripts\bluesky_spike.py probe`,
then `... record --seconds 300 --out spike-output`, then
`uv run --no-project --python 3.13 python scripts\bluesky_spike.py analyze --in spike-output --summary`.
Behind a corporate proxy set `HTTPS_PROXY` and `SSL_CERT_FILE` first (verification stays on). Paste
the printed summary (counts and rates only) below; the ratification does not wait for it.

[[MEASURE: pasted Windows summary]]

### S-13 Coverage cross-check against the public AppView

| Measure | Value |
|---|---|
| Roots selected (observed at least 10 min) and hydrated | [[MEASURE: roots]] |
| Replies: stream equals AppView / stream at most AppView | [[MEASURE: replies]] |
| Reposts: stream equals AppView / stream at most AppView | [[MEASURE: reposts]] |
| Quotes: stream equals AppView / stream at most AppView | [[MEASURE: quotes]] |
