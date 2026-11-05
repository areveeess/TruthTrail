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
eligible_roots_per_day: 15199
bytes_per_root: 1426
recommended_parameters: {"CASCADE_MERGE_POLICY": "claim_group", "DB_BUDGET_BYTES": 300000000, "INGEST_BATCH_ROWS": 500, "INGEST_BATCH_SECONDS": 2, "INGEST_MAX_EVENTS": 500000, "INGEST_MAX_RESUME_AGE_HOURS": 30, "INGEST_MAX_SECONDS": 300, "INGEST_MAX_STORED": 20000, "INGEST_REWIND_SECONDS": 30, "INGEST_STALE_AFTER_SECONDS": 21600, "RETENTION_CASCADE_DAYS": 90, "RETENTION_DORMANT_DAYS": 0, "RETENTION_NEWS_DAYS": 30, "RETENTION_TEXT_DAYS": 14, "RETENTION_TOMBSTONE_DAYS": 7, "STORE_MAX_EVENTS_TOTAL": 300000, "TRACK_ALLOWLIST_FILE": "src/truthtrail/data/seed_domains.txt", "TRACK_MAX_ACTIVE_ROOTS": 2850, "TRACK_MAX_EVENTS_PER_CASCADE": 5000, "TRACK_REQUIRE_LANG": "en", "TRACK_ROOT_TTL_HOURS": 48, "TRACK_SAMPLE_PER_10K": 625, "TRACK_SEED_CLAIM_URL_MATCH": false}
recommended_options: {"od1": "RT-2", "od2": "M1", "od3": "A"}
ratified_parameters: {}
run_windows: [{"bound_seconds": 3660.0, "bytes": 176504321, "dialect": "v2", "first_us": 1792395708073504, "frames": 207687, "host": "jetstream.us-east.bsky.network", "label": "w1", "last_us": 1792399367472878, "max_bytes": 800000000, "raw_bytes": 55291809, "raw_sha256": "0729f7fb54615c8c0265f47819338450951df4d36fb02b7b1f68579a0db0adf0", "stop_reason": "seconds", "stream_seconds": 3659.399374}, {"bound_seconds": 1800.0, "bytes": 169320963, "dialect": "v2", "first_us": 1792411841972337, "frames": 190019, "host": "jetstream.us-east.bsky.network", "label": "w2", "last_us": 1792413642775519, "max_bytes": 400000000, "raw_bytes": 51277198, "raw_sha256": "1eff7899fa238df1eb7e6514c861e04e0a9ff27a51e79d34bc0ad9a4df7556e5", "stop_reason": "seconds", "stream_seconds": 1800.803182}, {"bound_seconds": 1800.0, "bytes": 151047689, "dialect": "v2", "first_us": 1792416428173653, "frames": 185778, "host": "jetstream.us-east.bsky.network", "label": "w3", "last_us": 1792418227510055, "max_bytes": 400000000, "raw_bytes": 47254527, "raw_sha256": "6365bdac31472a7e584f2ac6e4f94693994b8ec7ebdb56f288cb509ed0981d2c", "stop_reason": "seconds", "stream_seconds": 1799.336402}]
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
parameter values). It exits 0 only after the owner ratified with the explicit tokens and the
effective parameters pass the storage coupling (Recommended parameter table); plans 03-02 to 03-12 run it first and
stop otherwise. The committed document has `ratified: false` because no agent may ratify. The owner
ratifies by replying at the checkpoint (see "Ratification block") or by editing the front matter
of this file.

## Run log

All windows were recorded inside this container against the live public Jetstream v2 host `jetstream.us-east.bsky.network`
(path `/xrpc/network.bsky.jetstream.subscribeEvents`, subprotocol `xrpc.v1.json`, collections post and repost,
`kinds=commit,account,sync`, `maxMessageSizeBytes=1048576`, no cursor, no credential), one connection at a time,
with the ephemeral install `uv run --no-project --python 3.13 --with websockets==17.2` (Python 3.13.16, websockets 17.2).
The same table, parsed as JSON, is the `run_windows` front matter key (pasted unchanged from `analyze`'s `windows.json`).

| Window | Host | Dialect | Exact bounds (--seconds, --max-bytes) | UTC start | UTC end | Stop reason | Measured stream span (s) | Frames | Frame bytes | Raw log gzip bytes | Raw log sha256 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| w1 | jetstream.us-east.bsky.network | v2 | 3660 s, 800,000,000 B | 2026-10-19T07:41:47Z | 2026-10-19T08:42:47Z | seconds | 3,659.4 | 207,687 | 176,504,321 | 55,291,809 | 0729f7fb54615c8c0265f47819338450951df4d36fb02b7b1f68579a0db0adf0 |
| w2 | jetstream.us-east.bsky.network | v2 | 1800 s, 400,000,000 B | 2026-10-19T12:10:42Z | 2026-10-19T12:40:42Z | seconds | 1,800.8 | 190,019 | 169,320,963 | 51,277,198 | 1eff7899fa238df1eb7e6514c861e04e0a9ff27a51e79d34bc0ad9a4df7556e5 |
| w3 | jetstream.us-east.bsky.network | v2 | 1800 s, 400,000,000 B | 2026-10-19T13:27:07Z | 2026-10-19T13:57:07Z | seconds | 1,799.3 | 185,778 | 151,047,689 | 47,254,527 | 6365bdac31472a7e584f2ac6e4f94693994b8ec7ebdb56f288cb509ed0981d2c |

- **Total measured stream span: 7,259.5 s** (sum over windows of last minus first frame stream time; the floor of the gate is 3,600 s, so the run is 2.02 times the floor and W1 alone clears it). A test (`tests/test_recorded_fixture.py`) checks that the manifest windows, this table and the stream times inside the fixture agree.
- **Stop reasons.** All three windows ended on the time bound (`seconds`), with 0 reconnects, no close code, no `ConsumerTooSlow` and no server-initiated close.
- **Schedule.** Monday 2026-10-19 UTC: W1 07:41 to 08:42 (European morning, US night), W2 12:10 to 12:40 (European midday, US early morning), W3 13:27 to 13:57 (US morning). The executor session was paused by a usage limit between W1 and W2, so the W1 to W2 gap is 3 h 28 min and the W2 to W3 gap is 46 min 25 s (both at least the required 45 minutes). No window covers a US evening, a night or a weekend (see Risks).
- **Tool provenance.** The recorder (`scripts/bluesky_spike.py`) is unchanged since commit b0c29c3; the working-tree HEAD when the windows ended was c6fe9be704ff4c3b8d880d62ee6f7070b871be15 (recorded in each meta file). Scrubber version of the fixture: scrub-1 at the cut, scrub-2 after the verification fix round of 2026-11-05 (a pure pass over the committed files, see Fixture manifest).
- **Package check before first use (T-03-SC).** PyPI JSON for websockets 17.2 fetched on 2026-10-19: the release exists, `Homepage` is https://github.com/python-websockets/websockets, files uploaded 2026-10-03 (14:52 to 14:56 UTC); the cp313 manylinux x86_64 wheel (uploaded 2026-10-03T14:54:00Z) has sha256 d87091c4347daadbcc0833b65812ff38d7350c67339625d4e4a512cf38e3e8ef and the sdist 36c2fb94c990cc2545143b12690e2de6c16300f9dbe5b4f33fa300cf57dc8792. Nothing differed from the RESEARCH audit.
- **Raw logs.** The transient raw logs live only under the git-ignored `spike-output/raw` and are deleted after the fixture cut (D-01); their sha256 and sizes above keep the run attributable. A re-analysis needs a new run.
- **Other steps.** The probe (S-1) ran at 07:37Z, the cursor test (S-3) at 07:37 to 07:39Z and the reconnect test (S-11) at 07:39 to 07:41Z, all before any long window.

## Source terms (S-10)

All pages below were fetched with `curl` through the container proxy, public pages only, no account
and no API call of any kind: the Bluesky pages on 2026-10-19 (UTC); the Jetstream Replay page, the
GNews pricing page, the GNews error-handling page and the GNews terms again on 2026-11-05 in the
verification fix round, because the earlier rows held paraphrases. Text in quotation marks is
verbatim from the page on the stated retrieval date; "unchanged" means the page's own "Last Updated"
date and the quoted sentence match the 2026-10-18 research reading (03-RESEARCH.md "Terms, privacy
and acceptable use").

| Source (URL), page date, read 2026-10-19 | Dated quote | Consequence for this phase |
|---|---|---|
| Bluesky Terms of Service, https://bsky.social/about/support/tos , Last Updated: 14 August, 2025 (unchanged) | "These Terms only apply to social networking that happens on Bluesky. If you're using another social networking application on the AT Protocol that isn't Bluesky Social (a "Developer Application"), the terms and conditions of that Developer Application will govern your experience." | The terms bind Bluesky users and the Bluesky app, not a reader of public network data. They contain no scraping, research or machine-learning clause. |
| same, section on Content | "Due to the decentralized nature of the AT Protocol, we cannot control or force other services and Developer Applications on the AT Protocol to treat your Content in a particular way and some posts may continue to exist on these services that are outside our control. That means that complete deletion across the network may not always be possible." | Honouring deletes is our responsibility as a downstream copy (D-16). |
| AT Protocol Network Services Privacy Notice, https://bsky.social/about/support/network-services-privacy-policy , Last Updated: May 22, 2024 (unchanged) | "User Content is Public." and "we may share your public personal information such as your public posts and profile with third-party actors that operate on the AT Protocol. We are not responsible for the processing of personal information by third-party actors that operate on the AT Protocol." | Public posts are personal data that we process as an independent party; minimisation, deletion propagation and retention are our defence. |
| Bluesky Privacy Policy, https://bsky.social/about/support/privacy-policy , Last Updated: August 14, 2025 | "Bluesky is a decentralized microblogging service where most user activity is public by design." and "Your posts and comments are public, so exercise care when deciding what to share." | Same. |
| Developer Guidelines, https://bsky.network/docs/developer-guidelines/ (no date shown) | "All services must have a method for deleting content a user has requested to be deleted." / "Developers must maintain updated contact information accessible to the public including an email address that is regularly monitored." / "Developers should maintain reasonable security measures to protect against unauthorized access or disclosure of any end-user information or app data." / apps with user-generated content "must include: A method to report illegal content; A method for blocking forbidden content from being shared in the app; A method for blocking abusive users from the app" / failure to respond to known violations "may result in suspension of access to services or features run on Bluesky's infrastructure." | The guidelines are addressed to "Developers who federate their apps or services on the AT Protocol"; whether a read-only analysis dashboard is covered is unclear, so they are treated as binding: deletion path (D-16), a public contact (README and the `COLLECTOR_CONTACT` part of the User-Agent), a documented report path and an operator erase command. |
| Community Guidelines, https://bsky.social/about/support/community-guidelines | No scraping or data-collection clause found (the only occurrence of "research" is an exception for "academic research" content). | Read-only consumption is not spam; keep the User-Agent honest. |
| Jetstream documentation, https://bsky.network/docs/jetstream/ | "No authentication is required for the live tail; these instances serve the full network." and "The cursor is inclusive ... and delivery is at-least-once, so an event may arrive more than once across a reconnect. Make your handlers idempotent." | No credential in this phase; idempotent writes (D-15). The research reading's "not metered" statement is not on this page; it is on the Replay page (next row, verbatim). |
| Jetstream Replay documentation, https://bsky.network/docs/jetstream-replay/ , retrieved 2026-11-05, section "Authentication and metering" | "On Bluesky-hosted instances, the replay HTTP endpoints are metered." / "The live WebSocket needs no key and is not metered." / elsewhere on the page: "an account-level deletion (an account event with active: false and status: "deleted") or a sync divergence marker removes all of that account's records" / "36 hours on Bluesky-hosted instances" | The live tail used by the collector needs no key and is not metered; the Replay HTTP API is metered and keyed, so it is out of scope for v1; the account-wide delete rule of D-16 and the 36 h lookback are confirmed. |
| Bluesky rate limits, https://bsky.network/docs/rate-limits/ | "These API services have generous rate-limits. Please contact us if you encounter rate-limiting." | The live tail has no published limit; see Risks (A6). |
| GNews Terms of Service, https://gnews.io/legal/terms-of-service , Last Updated: October 18, 2026 (read 2026-10-19 and again 2026-11-05, quotes verbatim on 2026-11-05). The research reading recorded "October 16, 2026"; what changed between the two versions is unverified (no copy of the earlier text was kept) | "If you do not hold an active paid subscription (including while on the Free plan ...), your license to use the API is limited to personal, academic, evaluation, and other non-commercial use." / prohibited: "Redistribute, resell, or sublicense access to the API without our express written consent" and "To create a database by systematically downloading and storing all or substantial portions of API content for the purpose of creating a competing service, redistributing the data, or avoiding API usage limits. Reasonable caching of API responses for application performance is permitted." | Storing a small topic set of headlines for the news context (DATA-06) is caching, not a competing database. A public portfolio demo on the Free plan must be non-commercial: the owner reads section 3 before the Phase 6 deploy. |
| GNews pricing, https://gnews.io/pricing , retrieved 2026-11-05 | Free plan, verbatim list items: "For development, testing, and non-commercial projects" / "Non-commercial use" / "100 requests per day" / "Up to 10 articles per request" / "12-hour delay" / "Last 30 days of historical data" / "Content cut to 250 characters" / "CORS for localhost only". | `NEWS_DAILY_BUDGET` 60 stays under the 100 requests per day; `max_results` 10. Headlines are at least 12 hours old, so the news context is never "breaking". The 250-character cut does not matter (D-18 stores no article body). CORS for localhost only means the browser never calls GNews: only the server-side news job does. |
| GNews error handling, https://docs.gnews.io/error-handling , retrieved 2026-11-05 | Status table: "403" "Forbidden" "The account's email address isn't verified, or the daily quota is used up." / "429" "Too many requests" "Too many requests per second: 1 on the Free plan, 10 on paid plans." Example 403 bodies: "Verify your email address to use the API: enter the code we emailed you, or request a new one, at https://gnews.io/verify-email" and "You've used all 100 requests of today's quota. The quota resets at 00:00 UTC. For more requests per day, see the plans: https://gnews.io/pricing" | A 403 is ambiguous: unverified email OR daily quota. The news job must classify a 403 by its body: the quota message stops the run until the 00:00 UTC reset; the unverified-email message (or any other 403 body) is a configuration error reported once and never retried (RESEARCH F-13). |

No research, machine-learning or scraping clause was found in any Bluesky page; absence is not a
licence. This is not legal advice; the owner is the controller of the processed data. The terms are
read again before the Phase 6 public deploy. Public pages only: no GNews API call was made in this
phase.

## Reachability and environment (S-1, S-12)

Probe on 2026-10-19 at about 07:37 UTC, 15 s per host, one host at a time (one sample frame per dialect was kept in the git-ignored `spike-output/samples.jsonl` and is scrubbed into the fixture samples file):

| host | dialect | https | upgrade | subprotocol | handshake_s | frames | commit | identity | account | first_frame | kinds_honoured |
|---|---|---|---|---|---|---|---|---|---|---|---|
| jetstream.us-east.bsky.network | v2 | 200 | ok | xrpc.v1.json | 0.48 | 795 | 791 | 0 | 4 | commit | yes |
| jetstream.us-west.bsky.network | v2 | 200 | ok | xrpc.v1.json | 0.41 | 808 | 805 | 0 | 3 | commit | yes |
| jetstream2.us-east.bsky.network | v1 | 200 | ok | - | 0.41 | 762 | 752 | 4 | 6 | commit | no |
| jetstream1.us-west.bsky.network | v1 | 200 | ok | - | 0.48 | 784 | 779 | 2 | 3 | commit | no |

- All four hosts answer HTTPS 200 and upgrade to a WebSocket through the container proxy. The v2 hosts negotiate `xrpc.v1.json` and honour `kinds` (0 identity frames in 795 and 808 frames); the v1 hosts negotiate no subprotocol and ignore `kinds=commit` (identity and account frames still arrive), as RESEARCH F-02 and Source Facts found.
- **Flags needed through the container proxy (S-12): none.** `HTTPS_PROXY` and `SSL_CERT_FILE` are already set; `websockets` 17.2 defaults (`proxy=True`) and the default SSL context connect with TLS verification on. The tool exposes an optional `--proxy` for odd networks and never disables verification (RESEARCH F-20).
- Transient failures through the proxy are real: a first connect attempt of a 20-second smoke recording ended in `ConnectionResetError` before the first frame and was retried by the tool; the three recorded windows needed no reconnect.

## Live-tail volume (S-2)

Measured per window (w1 07:41, w2 12:10, w3 13:27 UTC on 2026-10-19; "combined" sums counts and weights rates by the measured stream seconds). Collections post and repost, `kinds=commit,account,sync`.

#### S-2 volume

| Measure | w1 | w2 | w3 | combined |
|---|---|---|---|---|
| measured stream span (s) | 3,659.4 | 1,800.8 | 1,799.3 | 7,259.5 |
| frames | 207,687 | 190,019 | 185,778 | 583,484 |
| events per second | 56.75 | 105.5 | 103.2 | 80.37 |
| bytes per second (uncompressed) | 48,233.1 | 94,025.2 | 83,946.3 | 68,444.1 |
| post creates per second | 28.74 | 59.84 | 48.48 | 41.35 |
| repost creates per second | 23.8 | 41.59 | 47.47 | 34.08 |
| post deletes per second | 1.882 | 2.358 | 4.836 | 2.732 |
| repost deletes per second | 2.013 | 1.377 | 2.06 | 1.867 |
| post updates (count) | 121 | 45 | 73 | 239 |
| account events (count) | 1,042 | 582 | 664 | 2,288 |
| sync events (count) | 11 | 14 | 2 | 27 |
| frame bytes P50 | 773.0 | 794.0 | 746.0 | 794.0 |
| frame bytes P95 | 1,541.0 | 1,494.0 | 1,434.0 | 1,493.0 |
| frame bytes P99 | 2,354.0 | 2,150.0 | 2,123.0 | 2,216.0 |
| frame bytes max | 343,765.0 | 50,417.0 | 57,118.0 | 343,765.0 |
| events/s per-second P50 | 54 | 88 | 100.0 | 75 |
| events/s per-second P95 | 83 | 113.0 | 131.0 | 115.0 |
| events/s per-second max | 1,243.0 | 21,031.0 | 691.0 | 21,031.0 |
| events per minute P50 | 3,267.0 | 5,360.0 | 5,983.0 | 5,055.0 |
| events per minute P95 | 4,538.0 | 9,768.0 | 6,680.0 | 6,652.0 |
| events per minute max | 5,488.0 | 26,139.0 | 10,656.0 | 26,139.0 |
| post creates: top-level share | 0.5546 | 0.6058 | 0.4932 | 0.5552 |
| post creates: reply share | 0.3928 | 0.343 | 0.4339 | 0.3869 |
| post creates: quote share | 0.0486 | 0.0489 | 0.0689 | 0.0546 |
| post creates: reply+quote share | 0.004 | 0.0023 | 0.004 | 0.0034 |


- Mean combined volume is **80.4 events/s** (about 289,000 events per hour, 68.4 KB/s uncompressed, 851 bytes per frame on average); the quiet W1 (European morning) ran at 56.8 events/s and the W2 and W3 windows at 103 to 106 events/s, i.e. the load varied by a factor of 1.9 within about six hours of one day (W1 07:41 to W3 13:57 UTC; no night, evening or weekend was measured).
- Frame size P50 / P95 / P99 / max: 794 / 1,493 / 2,216 / 343,765 bytes (the largest frame, in W1, is far below the 1 MiB `maxMessageSizeBytes` sent to the server and the 2 MiB client bound).
- **Burst.** One upstream burst stamped 21,031 events within one stream second at +490 s into W2 (arrival over about 4 s of wall clock, 26,139 events in that minute); nothing was lost and no `ConsumerTooSlow` followed, but a reader must keep draining while a batch is written (the 500 rows or 2 s batching of D-21). Excluding that single second (derived): W2 93.8 events/s instead of 105.5, combined about 77.5 events/s instead of 80.4; the rates above include it.
- Post updates are rare (239 in 2.0 hours, none for reposts) and are ignored and counted (D-15).

## Cursor lookback and catch-up (S-3)

| cursor | result | first_event_minus_cursor_s | replay_events_per_s | info_frames | http |
|---|---|---|---|---|---|
| now-10min | accepted | 0.006 | 2126 (backlog exhausted) | - | - |
| now-2h | accepted | 0.006 | 8205 | - | - |
| now-24h | accepted | 0.016 | 7946 | - | - |
| now-35h | accepted | 0.010 | 8282 | - | - |
| now-37h | accepted | 1382.674 | 8536 | OutdatedCursor | - |
| now-48h | accepted | 40982.674 | 8278 | OutdatedCursor | - |
| seq=1 | CursorTooOld |  |  | - | 400 |
| seq=900000000000000 | accepted |  | 48 | FutureCursor | - |

- Timestamp cursors of now-10 min, 2 h, 24 h and 35 h are accepted without a key; the first event arrives 6 to 16 ms after the requested instant.
- Replay rates are **receive-path lower bounds on what the server can deliver**, not server capability: the longer cursors gave 7,900 to 8,500 events/s and every one of those reads stopped at the 100 MiB read cap of the 15-second probe, so the client (through the container proxy) was the limit; the 10-minute cursor (2,126 events/s) ran out of backlog (it caught up to the live tip inside the read), so it is not a speed figure and is not used below. 7,900 to 8,500 events/s is about three to four times the 1,900 to 2,800 events/s of the research reading and about 100 times the live rate of about 80 events/s.
- A timestamp cursor older than the floor (37 h and 48 h) is **accepted and clamped**: the first frame is an in-band `#info OutdatedCursor` and the stream begins 1,382.7 s and 40,982.7 s after the requested instant, i.e. about 36.6 h before the test (RESEARCH F-02). A sequence cursor of 1 is refused with HTTP 400 `CursorTooOld`; a sequence cursor far beyond the tip yields `#info FutureCursor` and the live tip.

**Cadence and catch-up arithmetic (RESEARCH F-05, recomputed from the measured rate).** The live tail delivers 80.4 events/s on average (289,000 per hour; 204,000 per hour in W1 up to 380,000 per hour in W2). `INGEST_MAX_EVENTS` 500,000 therefore covers 1.73 hours of stream at the mean rate (2.45 h at the W1 rate, 1.32 h at the W2 rate); `INGEST_MAX_SECONDS` 300 is not binding because 500,000 events replay in about 63 s at the measured receive rate of 8,000 events/s (a lower bound on the server, see above; a slower network than this container's makes it longer). Catching up a gap costs runs, not events (everything inside the 36-hour lookback is replayed):

| Gap since the last checkpoint | Events to replay at the mean rate (derived) | Runs of the default bounds (500,000 events) | Time at 8,000 events/s (measured receive rate) | Uncompressed bytes at 851 B/frame |
|---|---|---|---|---|
| 1 h | 289,000 | 1 | 36 s | 0.25 GB |
| 6 h | 1.74 M | 4 | 3.6 min | 1.48 GB |
| 12 h | 3.47 M | 7 | 7.2 min | 2.95 GB |
| 24 h | 6.94 M | 14 | 14.5 min | 5.90 GB |
| 30 h (`INGEST_MAX_RESUME_AGE_HOURS`) | 8.68 M | 18 | 18.1 min | 7.38 GB |

An hourly job with the defaults keeps up at the measured daytime rates (an extrapolation: the rates are from about two daytime hours of one Monday, and the per-hour W2 peak of 380,000 events is still under the 500,000 bound); a six-hourly job needs `--max-events` 2,500,000 (or several runs per gap); a gap over 36 hours is clamped by the server and recorded as an explicit gap (`resume_gap`). Phase 6 chooses the cadence and bounds together; no Phase 3 plan builds a scheduler. The default `INGEST_MAX_EVENTS`, `INGEST_MAX_SECONDS` and `INGEST_MAX_STORED` are unchanged.

## Time semantics (S-4)

#### S-4 time

| Measure | w1 | w2 | w3 | combined |
|---|---|---|---|---|
| arrival-order inversions | 0 | 0 | 0 | 0 |
| largest inversion (s) | 0 | 0 | 0 | 0 |
| seq going backwards | 0 | 0 | 0 | 0 |
| createdAt minus stream time P1 (s) | -46,691,374.4 | -52,132,728.4 | -109.7 | -48,862,124.0 |
| createdAt minus stream time P50 (s) | -1.08 | -1.498 | -0.8996 | -1.114 |
| createdAt minus stream time P99 (s) | 5.449 | 3.229 | 5.516 | 4.578 |
| createdAt minus stream time max (s) | 82,784.0 | 41,398.0 | 35,929.6 | 82,784.0 |
| createdAt more than 60 s in the future (count) | 464 | 379 | 376 | 1,219 |
| createdAt more than 1 h old (count) | 3,622 | 27,627 | 271 | 31,520 |
| createdAt absurd or unparseable (count) | 0 | 0 | 0 | 0 |
| child/parent pairs with the parent seen first | 33,287 | 24,800 | 27,866 | 85,953 |
| child before parent | not measured | not measured | not measured | not measured (analyzer defect, see below) |


- Stream time never goes backwards in arrival order on a single instance: **0 inversions in 583,484 frames** (largest 0 s) and the sequence number never decreases, so `INGEST_REWIND_SECONDS` stays at its floor of 30 s (the cross-instance witnessed-at offset of RESEARCH F-03, at most 2.02 s, was not re-measured because only one host was recorded).
- The record `createdAt` is untrustworthy, as D-08 assumes: median -1.1 s against the stream time, but 1,219 posts (0.41 percent of post creates) claim more than 60 s in the future, 31,520 (10.5 percent; 27,627 of them in W2) are over an hour old (backdated or imported), and the first percentile of createdAt minus stream time is already -46.7 million s (1.5 years) in W1 and -52.1 million s in W2 (bulk imports or backdating). `createdAt` is never used for ordering.
- **Child before parent: not measured in the spike windows** (analyzer defect, fixed after): the spike's pair counter only counted a pair when the parent had already been seen, so a child that arrived first could never be counted and the 85,953 pairs above are parent-first by construction. The analyzer now keeps a pending-target set and counts a child whose target arrives later (commit cf9a646, with a constructed positive test); the raw logs are deleted, so the windows cannot be re-analysed. An independent live re-measure on 2026-11-05 found 0 of 1,545 parent-in-log pairs arriving child-first (95% upper bound about 0.2%), on a different day. That is under the D-14 1 percent threshold, so D-14 stays as written (no pending buffer); the collector's drop-and-count `order_violation_count` remains the safeguard and the RESEARCH F-16 "tree prefix closed under ancestors" property holds only as far as that count stays near zero.

## Edge semantics (S-6)

D-12 restated: `edge_kind` is `root`, `reply`, `quote` or `repost`, a fact of the record. A reply keeps
a quote target as the secondary `quoted_uri`. A repost is an inferred fan-out hanging off its subject
(the repost-star caveat): it has no depth, never chains and is never attached to another repost.
Reposts carry an optional `via` strong reference to another repost record (RESEARCH F-07).

#### S-6 shapes

| Measure | w1 | w2 | w3 | combined |
|---|---|---|---|---|
| reply+quote posts | 419 | 243 | 348 | 1,010 |
| embed: none | 63,277 | 54,162 | 53,105 | 170,544 |
| embed: images | 16,322 | 12,823 | 12,709 | 41,854 |
| embed: external (link card) | 16,836 | 33,424 | 13,139 | 63,399 |
| embed: record (quote) | 4,657 | 4,745 | 5,510 | 14,912 |
| embed: recordWithMedia | 881 | 769 | 859 | 2,509 |
| embed: video | 2,920 | 1,612 | 1,700 | 6,232 |
| embed: gallery | 276 | 217 | 200 | 693 |
| embed: other (unknown) | 3 | 1 | 2 | 6 |
| unknown embed types (distinct) | 2 | 1 | 2 | 5 |
| top-level link: card only | 6,929 | 25,645 | 4,708 | 37,282 |
| top-level link: facet only | 8,372 | 5,337 | 4,378 | 18,087 |
| top-level link: both | 7,824 | 6,023 | 6,431 | 20,278 |
| top-level link: neither | 35,208 | 28,275 | 27,503 | 90,986 |
| top-level posts with a shortener | 954 | 663 | 759 | 2,376 |
| reposts total | 87,088 | 74,898 | 85,408 | 247,394 |
| reposts of a tracked root | 240 | 104 | 126 | 470 |
| reposts of a tracked event (any) | 270 | 106 | 135 | 511 |
| reposts of an untracked subject | 86,818 | 74,792 | 85,259 | 246,869 |
| reposts of a non-post record | 0 | 0 | 14 | 14 |
| repost via share | 0.2527 | 0.2601 | 0.255 | 0.2557 |
| via target is a repost seen in the log | 0.422 | 0.3549 | 0.4181 | 0.4 |
| via with the same subject (of seen) | 9,288 | 6,915 | 9,105 | 25,308 |
| quote targets that are not posts | 11 | 4 | 14 | 29 |
| did:web authors | 121 | 1 | 4 | 126 |
| did:web targets | 39 | 2 | 2 | 43 |


- Edge sources (D-13): of the 75,647 top-level posts that carry a link, the link card appears in 76.1 percent (card only 49.3, both 26.8) and a link facet in 50.7 percent (facet only 23.9); using only one source would miss a quarter to a half of the links, so the union is required.
- Reply+quote posts are 0.34 percent of post creates (1,010); reply wins and the quote target stays the secondary `quoted_uri`. `recordWithMedia` quotes number 2,509 and are treated as quotes.
- **Repost `via`.** 63,268 of 247,394 reposts (25.6%) carry a `via` reference to another repost record. Where the `via` repost is also in the window (25,309), the same subject matches in 25,308 cases. This confirms RESEARCH F-07 on three windows (24.2 percent there).
- Reposts of a tracked root are rare (470 of 247,394); 14 reposts name a non-post record and 29 quotes name a non-post record (both dropped). `did:web` authors appear in 126 events and as 43 reference targets (accepted); 6 posts carry an unknown embed type (5 distinct type names, not printed).

## Cascade yield (S-5)

#### S-5 yield

| Measure | w1 | w2 | w3 | combined |
|---|---|---|---|---|
| eligible roots | 449 | 413 | 415 | 1,277 |
| eligible roots per hour | 441.7 | 825.6 | 830.3 | 633.3 |
| allowlisted-link top-level posts | 635 | 508 | 518 | 1,661 |
| English share of those | 0.7071 | 0.813 | 0.8012 | 0.7688 |
| commentary-text share | 0.8646 | 0.7756 | 0.8282 | 0.826 |
| adult-label share | 0 | 0 | 0 | 0 |
| distinct domains (eligible) | 33 | 32 | 38 | 46 |
| distinct authors (eligible) | 319 | 291 | 291 | 855 |
| seeds refused: no_link | 35,208 | 28,275 | 27,503 | 90,986 |
| seeds refused: not_allowlisted | 21,536 | 35,835 | 14,240 | 71,611 |
| seeds refused: shortener | 954 | 662 | 759 | 2,375 |
| seeds refused: lang | 186 | 95 | 103 | 384 |
| seeds refused: adult_label | 0 | 0 | 0 | 0 |
| seeds refused: no_unauthenticated_label | 0 | 0 | 0 | 0 |
| share accepted by a 500-root cap | 1 | 1 | 1 | 1 |
| sampling 5000/10000: share | 0.441 | 0.4891 | 0.5157 | 0.4808 |
| sampling 2500/10000: share | 0.2361 | 0.2373 | 0.2458 | 0.2396 |
| sampling 1250/10000: share | 0.1158 | 0.1186 | 0.1253 | 0.1198 |
| sampling 625/10000: share | 0.049 | 0.0533 | 0.0651 | 0.0556 |
| P(any child) within 15 min (n) | 355 | 189 | 190 | 734 |
| P(any child) within 15 min | 0.2197 | 0.2011 | 0.1684 | 0.2016 |
| P(reply) within 15 min | 0.1352 | 0.1111 | 0.0737 | 0.1131 |
| P(quote) within 15 min | 0.0535 | 0.0159 | 0.0158 | 0.0341 |
| P(repost) within 15 min | 0.1324 | 0.1164 | 0.1211 | 0.1253 |
| P(any child) within 1 h (n) | 9 | 0 | 0 | 9 |
| P(any child) within 1 h | n/a (n = 9) | n/a | n/a | n/a (2 of 9; 95% interval 6 to 55 percent) |
| P(reply) within 1 h | n/a (n = 9) | n/a | n/a | n/a |
| P(quote) within 1 h | n/a (n = 9) | n/a | n/a | n/a |
| P(repost) within 1 h | n/a (n = 9) | n/a | n/a | n/a |
| P(any child) within 6 h (n) | 0 | 0 | 0 | 0 |
| P(any child) over the observed horizon (n) | 449 | 413 | 415 | 1,277 |
| P(any child) observed horizon | 0.2227 | 0.2131 | 0.1928 | 0.2099 |
| P(reply) observed horizon | 0.1448 | 0.0969 | 0.0747 | 0.1065 |
| P(quote) observed horizon | 0.0535 | 0.0097 | 0.0265 | 0.0305 |
| P(repost) observed horizon | 0.1425 | 0.1429 | 0.1422 | 0.1425 |
| cascade children median | 0 | 0 | 0 | 0 |
| cascade children P90 | 3 | 1 | 1 | 2 |
| cascade children P99 | 16 | 6 | 8 | 10 |
| cascade children max | 60 | 9 | 23 | 60 |
| cascades with at least one child | 100 | 88 | 80 | 268 |
| orphan rate (replies) | 0 | 0.0179 | 0 | 0.0032 |
| top 1 percent of cascades: share of tracked events | 0.1807 | 0.069 | 0.1195 | 0.1325 |
| option C: subjects with >= 10 refs per bucket | 1,278.0 | 1,080.0 | 1,335.0 | 1,231.0 |
| option C: subjects with >= 25 refs per bucket | 315.0 | 275.0 | 363.0 | 317.7 |
| option C: subjects with >= 100 refs per bucket | 17 | 26 | 45 | 29.3 |
| option C: distinct referenced subjects per bucket | 73,011.0 | 65,160.0 | 65,043.0 | 67,738.0 |
| option C: bucket length (s) | 3,600.0 | 1,800.0 | 1,799.0 | 2,400.0 |
| dropped by TTL / overflow | 0 | 0 | 0 | 0 |


- **Yield.** With the draft 54-domain allowlist the policy accepts **1,277 eligible roots in 7,259.5 s = 633 roots per hour** (442 in the W1 morning, 826 and 830 in W2 and W3), from 855 distinct authors and 46 of the 54 domains; 15,199 per day (derived: the measured hourly rate times 24, assuming the daytime mean held for 24 hours; it is measured over 2.0 daytime hours only). Top domains by eligible roots (distinct authors): theguardian.com 389 (282), nytimes.com 208 (142), bbc.co.uk 126 (93), apnews.com 75 (65), abc.net.au 51 (36), reuters.com 40 (38), independent.co.uk 36 (30), wsj.com 36 (30), bbc.com 33 (28), npr.org 29 (26), cbc.ca 27 (26), bloomberg.com 25 (16), ft.com 24 (23), smh.com.au 20 (7), washingtonpost.com 17 (17).
- Of the 1,661 top-level posts with an allowlisted link, 76.9 percent are English (384 refused for language), 82.6 percent carry commentary text besides the link and none carried an adult self-label; 2,375 posts used a shortener and 71,611 linked a non-allowlisted domain (these are counted by reason).
- **The 500-root cap is a window bias, not a sample (RESEARCH F-06).** At the combined rate it fills in 47 minutes (36 minutes at the W2 and W3 rate; no single window reached 500: 449, 413, 415). With 500 active roots and a 48-hour TTL the steady state admits at most 250 new roots a day, **1.6 percent of the 15,199 eligible**, first-come after each slot frees. Deterministic hash sampling at 625 per 10,000 accepted 5.6 percent of eligible roots in the log (the table above); the share is stable across windows.
- **Outcomes.** Among the 734 roots with a full 15-minute horizon, P(at least one reply, quote or repost within 15 minutes) = 20.2 percent (reply 11.3, quote 3.4, repost 12.5). These are **upper bounds on engagement by others**: they include self-engagement (the root author replying under their own post, e.g. a thread continuation), and 44 percent of the replies in the fixture's tracked cascades (109 of 245) are by the root author; the spike did not separate self-replies in the windows. Within 1 hour only 9 roots (W1) have the full horizon (2 of 9 have a child; too few for a rate, reported as n/a); **6 hours cannot be measured: n = 0, because every window is at most 61 minutes**. Over the observed horizon (0 to 61 minutes) 21.0 percent of the 1,277 roots have a child (reply 10.7, quote 3.1, repost 14.3).
- **Cascade size** (stored children, window-truncated lower bounds): median 0, P90 2, P99 10, max 60; 268 of 1,277 cascades (21.0 percent) have at least one child. Reply depth: 187 at depth 1, 65 at 2, 30 at 3, 34 at 4 or more, 1 orphan (0.3 percent of 317 stored replies). The top 1 percent of cascades (13) hold 13.3 percent of tracked events. No cascade approaches the 5,000-event cap (nothing dropped for TTL or overflow).
- **Option C counters** (per bucket; W1 bucket 3,600 s, W2 and W3 buckets 1,800 s, so the mean mixes widths): subjects with at least 10 / 25 / 100 references per bucket: W1 (per hour) 1,278 / 315 / 17, W2 1,080 / 275 / 26, W3 1,335 / 363 / 45 (per 30 minutes); a promotion rule would lose the first T-1 references of each promoted subject (W1 per hour: 11,502 / 7,560 / 1,683 references) and the in-memory counter must hold about 73,000 distinct subjects per hour in W1 (65,000 per half hour in W2 and W3).

## Deletes and account events (S-7)

#### S-7 deletes and accounts

| Measure | w1 | w2 | w3 | combined |
|---|---|---|---|---|
| post deletes | 6,886 | 4,247 | 8,701 | 19,834 |
| repost deletes | 7,367 | 2,480 | 3,706 | 13,553 |
| post deletes per hour | 6,774.2 | 8,490.2 | 17,408.4 | 9,835.7 |
| repost deletes per hour | 7,247.4 | 4,957.8 | 7,414.7 | 6,720.9 |
| post deletes / post creates | 0.0655 | 0.0394 | 0.0998 | 0.0661 |
| repost deletes / repost creates | 0.0846 | 0.0331 | 0.0434 | 0.0548 |
| deleted in window: posts created in window (n) | 1,531 | 1,067 | 1,302 | 3,900 |
| time to delete, all posts: P50 (s) | 55.4 | 39.3 | 36.4 | 43.7 |
| time to delete, all posts: P90 (s) | 783.7 | 423.8 | 439.0 | 567.3 |
| time to delete, all posts: max (s) | 3,278.6 | 1,559.1 | 1,786.2 | 3,278.6 |
| tracked roots deleted in window | 5 | 2 | 2 | 9 |
| time to delete, tracked roots: P50 (s) | n/a (n = 5) | n/a (n = 2) | n/a (n = 2) | n/a (n = 9) |
| tracked children deleted (n) | 4 | 4 | 2 | 10 |
| time to delete, tracked children: P50 (s) | n/a (n = 4) | n/a (n = 4) | n/a (n = 2) | n/a (n = 10) |
| censoring horizon (s) | 3,659.0 | 1,801.0 | 1,799.0 | 7,260.0 |
| account events: active | 800 | 448 | 477 | 1,725 |
| account events: deleted | 85 | 58 | 61 | 204 |
| account events: takendown | 79 | 34 | 72 | 185 |
| account events: deactivated | 78 | 41 | 53 | 172 |
| account events: throttled | 0 | 1 | 1 | 2 |
| account events: suspended | 0 | 0 | 0 | 0 |
| account events: desynchronized | 0 | 0 | 0 | 0 |
| account events: other (unknown) | 0 | 0 | 0 | 0 |
| sync events | 11 | 14 | 2 | 27 |
| sync events per hour | 10.82 | 27.99 | 4 | 13.39 |
| info frames (any) | 0 | 0 | 0 | 0 |


- **Deletes.** Posts are deleted at 9,836 per hour (6.6 percent of post creates counted in the same time) and reposts at 6,721 per hour (5.5 percent). Most deletes retract older content: only 3,900 deletes hit a post created inside the window, 80 percent target older posts. **1.3 percent of the 300,149 post creates deleted in-window is a lower bound** on the share that is ever deleted: a post created near the end of a window had only seconds to be deleted (right-censored). The time-to-delete figures are **conditional on a delete inside the window** and censored at the window length: for those 3,900 posts P50 44 s, P90 567 s, max 3,279 s; they say nothing about deletes after hours or days. Tracked roots: 9 of 1,277 (0.7 percent, 95% interval 0.4 to 1.3 percent, a lower bound for the same reason) were deleted within the window; 10 tracked children were deleted. With n = 9 and n = 10 their median delay is not reported (n/a). A short text TTL therefore cannot replace the delete path (D-16).
- **Account events** over 7,260 s: 1,725 active, 204 deleted, 185 takendown, 172 deactivated, 2 throttled, 0 suspended, 0 desynchronized, 0 unknown; the deletion statuses (`deleted`, `takendown`) arrive at about 190 per hour. Counting `takendown` as deletion-type (the collector removes the account's records) is a conservative choice: a takedown can be reversed, and a reversed account's records are then gone from our copy until they are seen again. **Sync events** arrive at 13.4 per hour (27 in all), so D-16's account-wide rule is cheap. No `#info` or error frame occurred in the recorded windows (control shapes are in the probe samples).

## Storage footprint (S-8)

Measured on a throwaway local PostgreSQL 16.15 cluster (private temp directory, unix socket only, started as the `postgres` user, stopped with `pg_ctl -m immediate` and deleted; no postgres process or `tt-pg-*` directory remained). Scratch tables shaped like D-20 with the same index set were loaded with the 2,151 recorded tracked rows (1,277 roots and 874 children) replicated 93 times with re-keyed identifiers so that index and page overhead are at steady state (the scale is a measurement device; nothing here is a schema or data). Root text and link-card title lengths are the real lengths, padded with a filler character. **Scope of the figures:** a fresh bulk load into scratch tables only. They exclude table and index bloat from deletes and purges (dead tuples until vacuum), WAL and the free-space map, the nullable `via_uri` column if ratified (one more 20-character key on about a quarter of repost rows) and the stored news headlines of DATA-06 (about 10 MB, an estimate); real usage is higher than the projections below.

| table | rows | total_bytes | bytes_per_row |
|---|---|---|---|
| accounts | 129549 | 18841600 | 145.4 |
| claims | 87699 | 47243264 | 538.7 |
| cascades | 118761 | 27697152 | 233.2 |
| events | 200043 | 72810496 | 364.0 |
measurement scale: recorded tracked rows (2151) replicated 93x, identifiers re-keyed
all-in bytes per root (events x (1 + 0.68 children) + cascade + claim + account): 1426 (derived)
eligible roots per day (window-measured rate x 24): 15199 (derived)
| bound set | roots/day | retention_days | steady_state_MB | share_of_budget | days_to_fill_budget | days_to_fill_80pct |
|---|---|---|---|---|---|---|
| cap 500 active / 48 h | 250 | 90 | 32.1 | 0.11 | 841.3 | 673.0 |
| all eligible, 7 d | 15199 | 7 | 151.8 | 0.51 | 13.8 | 11.1 |
| all eligible, 14 d | 15199 | 14 | 303.5 | 1.01 | 13.8 | 11.1 |
| all eligible, 30 d | 15199 | 30 | 650.4 | 2.17 | 13.8 | 11.1 |
| 1-in-2, 30 d | 7600 | 30 | 325.2 | 1.08 | 27.7 | 22.1 |
| 1-in-2, 90 d | 7600 | 90 | 975.6 | 3.25 | 27.7 | 22.1 |
| 1-in-4, 30 d | 3800 | 30 | 162.6 | 0.54 | 55.3 | 44.3 |
| 1-in-4, 90 d | 3800 | 90 | 487.8 | 1.63 | 55.3 | 44.3 |
| 1-in-8, 30 d | 1900 | 30 | 81.3 | 0.27 | 110.7 | 88.6 |
| 1-in-8, 90 d | 1900 | 90 | 243.9 | 0.81 | 110.7 | 88.6 |
| 1-in-16, 30 d | 950 | 30 | 40.7 | 0.14 | 221.4 | 177.1 |
| 1-in-16, 90 d | 950 | 90 | 122.0 | 0.41 | 221.4 | 177.1 |

- **Bytes per row including indexes: events 364.0, cascades 233.2, claims 538.7, accounts 145.4** (the events figure already includes the two 20-character keyed identifiers per row and the three indexes of D-20). All-in bytes per root: events x (1 + 0.684 children) + cascade + claim x (1 - 0.193 shared-URL discount) + account = 613 + 233 + 435 + 145 = **1,426 bytes**. The 0.684 children per root is window-truncated (a lower bound; cascades live up to 90 days), so the per-root figure and every projection below are optimistic for long-lived cascades.
- Rows are measured against the 300 MB budget (`DB_BUDGET_BYTES`), stop threshold 80 percent. The roots-per-day column uses the combined mean of 15,199 eligible roots a day.
- **Break-evens of the recommended setting** (625 per 10,000, 950 roots a day, 90 days, about 85,500 roots held; derived). The 300,000 `STORE_MAX_EVENTS_TOTAL` cap binds at 2.51 children per root (measured 0.684, window-truncated, so the true lifetime figure is higher). The 60 percent design line (180 MB) is crossed at 2.55 children per root and the 80 percent stop (240 MB) at 4.48. At the measured 0.684 children per root, the eligible-roots-per-day figure has headroom of 1.47 times to the 60 percent line and 1.97 times to the 80 percent stop. Any multiplier on the daily mean (a busier evening, a news day) is an assumption, not a measurement.

## Merge frequency (S-9)

#### S-9 merge

| Measure | w1 | w2 | w3 | combined |
|---|---|---|---|---|
| children whose parent is in another cascade | 0 | 0 | 0 | 0 |
| stored children | 486 | 167 | 221 | 874 |
| roots | 449 | 413 | 415 | 1,277 |
| distinct canonical URLs | 331 | 345 | 363 | 943 |
| roots in shared-URL groups | 173 | 112 | 81 | 493 |
| share of roots in shared-URL groups | 0.3853 | 0.2712 | 0.1952 | 0.3861 |
| largest URL group | 12 | 5 | 10 | 15 |
| URL groups of 2 or more | 55 | 44 | 29 | 159 |
| quote posts that are seed-eligible | 11 | 4 | 0 | 15 |


- **Situation A (re-rooting)** is absent: 0 of 874 stored children has a parent in another cascade, as expected under allowlist seeding. **Situation B (claim-level duplicates)** is visible: 943 distinct canonical article URLs for 1,277 roots; 493 roots (38.6 percent; 19.5 to 38.5 percent inside a single window) share a URL with another root, in 159 groups, the largest with 15 roots. The combined figure counts groups across windows, so a URL repeated in different windows is one group.
- 15 quote posts (1.2 percent of roots) are themselves seed-eligible (an allowlisted link in a quote); they are not roots under the top-level rule.

## Reconnect (S-11)

| measure | value |
|---|---|
| first read frames | 1070 |
| resume cursor | last stream time minus 30 s |
| second read frames | 2132 |
| duplicates (seq seen in the first read) | 1070 |
| expected overlap (first-read frames with stream time >= cursor) | 1070 |
| idle hold requested (s) | 90.0 |
| idle hold elapsed (s) | 90.4 |
| idle hold frames (sparse filter) | 0 |
| closed by the server before the hold ended | no |
| close code / error | - / - |

- A deliberate disconnect followed by a resume at the last stream time minus 30 s re-delivers exactly the expected overlap: **1,070 duplicates against an expected overlap of 1,070** frames (every frame of the 20-second first read lies within 30 s of the cursor), and idempotent writes absorb them (D-15).
- **Server-initiated closes: none** in 7,260 s of recording (0 close codes, 0 reconnects, 0 `ConsumerTooSlow`) and none during a 90-second idle hold on a sparse filter that delivered 0 frames (the default 20 s keepalive of `websockets` was enough). Silence of 60 s as a dead connection is safe for the dense post and repost filter; a sparse filter can be silent indefinitely and must not reuse that rule (RESEARCH, time and cursor semantics).

## Windows result (S-12)

Owner action, non-blocking: PENDING-OWNER (see the checkpoint). `windows_result` stays `pending`
until the owner pastes the summary of a 5-minute run on Windows.

## Coverage cross-check (S-13)

AppView `app.bsky.feed.getPosts` (25 URIs per call, spaced at least 1.1 s, 4 calls per check, unauthenticated) against child counts reconstructed from the stream, up to 100 roots with at least 10 minutes of observation per window. W1 was checked 3 h 28 min after its window ended (stale: the AppView counts include events after the recording), W2 and W3 within 25 seconds of theirs.

| Window | Roots selected / hydrated | Replies: stream equals AppView / stream at most AppView | Reposts: equals / at most | Quotes: equals / at most |
|---|---|---|---|---|
| w1 (stale by 3 h 28 min) | 100 / 100 | 0.920 / 1.000 | 0.830 / 1.000 | 0.950 / 1.000 |
| w2 (fresh) | 100 / 99 | 0.980 / 0.990 | 0.980 / 0.990 | 1.000 / 1.000 |
| w3 (fresh) | 100 / 100 | 1.000 / 1.000 | 0.980 / 0.990 | 1.000 / 1.000 |

The check is small: 100 roots per window, about 79 percent of them childless (for those, equality is trivially expected), and it compares direct children only (reply, repost and quote counts on the root), not deeper replies. Within that scope it shows **no evidence of loss in a small sample**, with three shortfall cells (W2 replies 1, W2 reposts 1, W3 reposts 1): in each, one root had a stream count below the AppView ("equals" is one root lower than "at most"), explainable by a child created in the up to 25 seconds between the window end and the check, though a missed event cannot be excluded; in the same cells one root had a stream count above the AppView ("at most" below 1), consistent with a child deleted after it was observed. In the two fresh windows the reconstruction equals the AppView count for 98 to 100 percent of the hydrated roots. W1 is stale (checked 3 h 28 min after the window, so the AppView includes later events) and shows the expected drift (83 to 95 percent exact); it supports nothing beyond "the stream never exceeded the AppView". This is not a completeness proof for deeper cascades or other days. The thread view of the AppView is not a completeness oracle and is not used.

## Draft allowlist

Path `src/truthtrail/data/seed_domains.txt`. 54 entries (8 fact-checker, 25 newspaper-of-record, 10 public-broadcaster, 6 science-news, 5 wire-service), each commented with its category, chosen by the category rules in the file header and never by political lean; 46 of the 54 had at least one eligible root in the run. The list is a DRAFT for the owner's review. Disclosed selection bias: by the same category rules it leaves out cable and broadcast television networks, digital-native outlets and magazines that were among the frequently linked news-like domains in the log (for example propublica.org, theatlantic.com, theconversation.com, apple.news, rawstory.com) and non-English outlets (eldiario.es, spiegel.de, news.yahoo.co.jp); the IFCN and published-corrections criteria were not re-verified entry by entry. Adding a domain is a one-line edit; the fixture keeps the allowlist it was cut with in its manifest, so an edit at the checkpoint cannot change what the fixture means.

- **In-sample yield.** The list was reviewed against the domain counts of all three windows, so the yield (633 roots an hour, 46 of 54 domains used) is an in-sample figure; the out-of-sample yield (other days, a revised list) is unmeasured.
- **Concentration.** theguardian.com supplies 30.5 percent of eligible roots (389 of 1,277); The Guardian and The New York Times together 46.8 percent; the top five domains 66.5 percent. The feed therefore reflects a few publishers' Bluesky audiences, which the dashboard and DOC-02 must disclose.
- **Redundant entry.** `factcheck.afp.com` is also matched by `afp.com` (a domain matches its subdomains), so it adds no host; it is kept only so that AFP's fact-check desk carries the fact-checker category (the longest match wins). The list therefore has 54 entries and 53 distinct coverage scopes.

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
in plan 03-02 only after the owner approves this table. The PyPI JSON check of websockets 17.2 was repeated on 2026-10-19 (release, project URL, file hashes: see the Run log) and nothing differed. Each row's Owner verdict is left for the owner; plan 03-02 runs only after the owner approves (`dependencies_approved`), which a reply confirms only with the explicit token `dependencies=approved`.

## Schema hedges (`via_uri`)

**Measured via share: 25.6% of reposts carry a `via` reference** (63,268 of 247,394), stable at 25.3 to 26.0 percent in each window; where the `via` repost is also in the window, the subject matches in 25,308 of 25,309 cases. **Recommendation (PROVISIONAL): `schema_via_uri` true** - add a nullable `via_uri` (keyed, a secondary relation, never an edge in v1, exactly like `quoted_uri`) to the baseline migration. D-12's star semantics stay: reposts remain an inferred fan-out and nothing draws who saw the post from whom. Adding the column later is a migration plus a re-ingest. The owner confirms this field only with the explicit token `via_uri=true` (or `via_uri=false`) in the reply.

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

**Alternative the owner may prefer: deterministic encryption** (for example AES-SIV with a
server-side key) instead of HMAC. It keeps the equality joins, and because it is reversible with the
key it would allow a "view on Bluesky" link for roots and a key rotation without re-collecting
(decrypt and re-encrypt every row). It loses the strongest property of D-17: with HMAC the raw
identifiers are never kept anywhere, while with encryption they are kept (encrypted) and a leaked key
plus a leaked database reveals every DID directly, without a dictionary attack. It is not
recommended; it is listed so the one-way choice is made knowingly.

**What you give up.** There is no "open this post on Bluesky" link in v1 (the claim is the linked
article, which the UI shows). The secret is long-lived, so rotating it re-keys every identifier,
which is a rebuild.

**Honesty limits (to be stated in DOC-02).** This is pseudonymisation, not anonymisation: with
stored timestamps and, for the retention window, root text, a party holding a network archive can
still re-link a record, and a leaked secret plus a leaked database re-enables dictionary reversal.

**Cost of undoing it.** Raw identifiers are never kept, so past data cannot be recovered in clear
and stored rows cannot be re-keyed (the raw values do not exist). A different scheme later means
re-collecting from scratch, and a changed key re-keys every row. Plans 03-03 onward compute keyed
identifiers; the schema, the writer, the delete path and the API all depend on this choice.

**Measured fact the spike supplies.** An events row costs **364.0 bytes including its indexes** (S-8), and that figure already contains the two 20-character keyed identifiers (`uri` and `parent_uri`) per row; the 16-character account pseudonym adds 145.4 bytes per account row. The keyed scheme therefore costs no more than the raw identifiers it replaces would have.

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

**Measured.** S-5 (combined, 7,259.5 s): 633 eligible roots per hour (15,199 a day if the mean held), 82.6 percent with commentary text; S-8: 1,426 bytes per root all-in and 364 per event row; S-7: 1.3 percent of posts are deleted within the window (a lower bound, censored) and 80 percent of deletes retract older posts, tracked roots deleted in-window 0.7 percent (n = 9, a lower bound); S-10: no research clause in the Bluesky terms, the Developer Guidelines require a deletion method.

**Recommendation (PROVISIONAL).** **RT-2 (14 / 90 / 7 days) stays the recommendation, but the measurements contradict CONTEXT's premise that it fits as written.** RT-2's 90-day cascade window at full yield (15,199 roots a day) needs about 1.95 GB, 6.5 times the 300 MB budget; even 14 days of every eligible root is 303 MB (1.01 of the budget). RT-2 fits only together with the OD-3 sampling parameter: at `TRACK_SAMPLE_PER_10K` 625 the steady state is 122 MB (41 percent of the budget, under the 60 percent design line) with `RETENTION_CASCADE_DAYS` 90 unchanged, so RT-2 is recommended **together with OD-3's sampling**, not alone. Alternatives, each flagged: RT-1 (text 0, structure 30 days) changes the storage picture through its shorter cascade retention, not through text (root text is a small part of 1,426 bytes per root): 30 days instead of 90 allows four times the sampling (2,500 per 10,000) in a similar footprint; RT-3 (text for the life of the cascade) has the weakest privacy position and no storage benefit. The real trade between the options is **yield versus retention** (see the table below); every option fits the budget at some sampling rate. A rule that drops cascades with no child early (`RETENTION_DORMANT_DAYS` 7, not in CONTEXT's RT options) would, because 79 percent of cascades had no child in the window, cut the storage per accepted root to about 27 percent (0.79 x 7 + 0.21 x 90 = 24.4 root-days instead of 90) and would allow sampling 2,500 per 10,000 (about 133 MB, 44 percent) instead of 625; this is an indicative extrapolation from window-truncated child shares and is not recommended until measured over days. Deletes: the TTL bounds a missed delete to 14 days, and because 80 percent of deletes retract older content (S-7) the purge and the delete path matter more than the TTL.

**Per-option storage at the measured rates** (derived: 15,199 eligible roots a day, 1,426 bytes per root, 48-hour TTL, budget 300 MB, 60 percent line 180 MB; sampling values from the analysed ladder 10000 / 5000 / 2500 / 1250 / 625 / 312; the required cap is ceil(1.5 x 48 / 24 x roots a day x sampling / 10000)):

| Option | Cascade retention (days) | Largest ladder sampling at or below 60 percent (exact maximum) | Roots a day | Required `TRACK_MAX_ACTIVE_ROOTS` | Steady state MB (share) |
|---|---|---|---|---|---|
| RT-1 | 30 | 2,500 (2,768) | 3,800 | 11,400 | 162.6 (54 percent) |
| RT-2 (recommended) | 90 | 625 (922) | 950 | 2,850 | 121.9 (41 percent) |
| RT-3 | 90 (life of the cascade) | 625 (922) | 950 | 2,850 | 121.9 (41 percent) |
| RT-2 with CONTEXT's 500 cap and no sampling | 90 | none (first-come) | at most 250 | 500 | 32.1 (11 percent) |

RT-2 with CONTEXT's 500 cap also fits, at 11 percent; what it costs is yield and representativeness (a first-come window bias, 1.6 percent of eligible roots a day), not storage. The gate enforces the coupling (see the Recommended parameter table).

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

**Measured.** **Situation measurements (S-9).** Situation A: 0 of 874 stored children has its parent in another tracked cascade. Situation B: 493 of 1,277 roots (38.6 percent) share a canonical article URL, 159 groups, largest 15. Situation C (child before root): not measured in the spike windows (analyzer defect, fixed after); an independent live re-measure on 2026-11-05 found 0 of 1,545 parent-in-log pairs arriving child-first (95% upper bound about 0.2%), different day; the collector's drop-and-count `order_violation_count` remains the safeguard. OD-3 interaction: under option A only B exists; option C would create A.

**Recommendation (PROVISIONAL).** **M1 (never merge, group by claim), `CASCADE_MERGE_POLICY` claim_group.** Situation A (re-rooting) was 0 of 874 stored children (0 percent, under the 1 percent threshold) and situation B is a visible share of the feed (38.6 percent of roots share an article URL with another root across the run, 19.5 to 38.5 percent inside one window, groups of up to 15), which is exactly the rule CONTEXT sets for ratifying M1. After sampling at 625 per 10,000 a root's URL siblings are mostly sampled out too, so the share of stored roots that share a URL with another stored root is expected to be about 8 to 10 percent (an estimate, not measured); M1 still costs nothing and groups those. Revisit only if the owner picks OD-3 option C.

**What changes if you choose otherwise.** M0 sets `CASCADE_MERGE_POLICY` none, which also switches
the claim_id filter of `GET /v1/cascades` off; M1 sets claim_group. Both are parameter changes the
gate derives itself. M2 is outside the plans and requires the planner to revise plans 03-03 to 03-07, plus 03-02 (OD-3 C)
and 03-10 (docs), before they run (the gate exits 3).

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

**Measured.** **S-5 measured (per window above):** 633 eligible roots an hour combined, cap 500 fills in 47 minutes (36 at the afternoon rate), sampling shares 48.1 / 24.0 / 12.0 / 5.6 percent at 5000 / 2500 / 1250 / 625 per 10,000, P(any child within 15 minutes) 20.2 percent (n = 734; an upper bound on engagement by others, it includes self-replies), P99 10 children, max 60. **S-9:** 0 re-rooted children, 38.6 percent of roots share a URL. The option C counters (1,231 subjects with at least 10 references per bucket, 29 with at least 100; 73,000 distinct subjects an hour held in memory) show option C is feasible only with a large always-on counter and loses the first references of every promoted subject. Option B yields near zero until headlines are stored.

**Recommendation (PROVISIONAL).** **Option A (allowlist seed), `TRACK_SEED_CLAIM_URL_MATCH` false, with `TRACK_SAMPLE_PER_10K` 625 and the bounds in the table below.** The yield (633 eligible roots an hour) populates a feed without option B, so B stays off (built and tested later; it seeds nothing until headlines exist). The sampling parameter is the answer to the finding that the first-come cap is a window bias (47 minutes to fill 500, 1.6 percent of eligible roots a day, first-come): 625 per 10,000 keeps 950 roots a day chosen by a deterministic hash of the raw URI, so the cap (`TRACK_MAX_ACTIVE_ROOTS` 2,850 = 1.5 x the 1,900 roots active over the 48-hour TTL) is a safety valve, not the selector. The sampled rate must be disclosed in the dashboard and DOC-02 (about 6 percent of eligible allowlisted roots, all hours). Cascades are small (P99 10 children, max 60), so `TRACK_MAX_EVENTS_PER_CASCADE` stays 5,000. C and D stay deferred.

**What changes if you choose otherwise.** A sets `TRACK_SEED_CLAIM_URL_MATCH` false; B sets it true.
Both are parameter changes the gate derives itself. C (and D) are outside the plans and require the
planner to revise plans 03-03 to 03-07, plus 03-02 (OD-3 C) and 03-10 (docs), first (the gate exits 3
on C).

**Parameters that encode it.** `TRACK_ALLOWLIST_FILE`, `TRACK_MAX_ACTIVE_ROOTS`,
`TRACK_ROOT_TTL_HOURS`, `TRACK_MAX_EVENTS_PER_CASCADE`, `STORE_MAX_EVENTS_TOTAL`,
`TRACK_REQUIRE_LANG`, `TRACK_SEED_CLAIM_URL_MATCH`, `TRACK_SAMPLE_PER_10K`.

## Fixture manifest

Produced by `scripts/bluesky_spike.py cut-fixture` from the raw logs above (`--check` re-cut from the raw logs gave byte-identical files before they were deleted), then rewritten once by `scripts/bluesky_spike.py rescrub-fixture` (scrub-2, 2026-11-05, verification fix round): a pure, deterministic pass over the committed files that needs no raw log. Nothing in it is written by hand. `source_mode` is `recorded-real`, scrubber version `scrub-2`, cut at tool git sha 8e37d757ddaa4f7fd32621110e8ee117d435449f, trimmed false, frames dropped by the scrubbers 3 (the scrub-2 adult-label drop), `did:web` DIDs mapped to did:plc tokens 1. Total 681,821 bytes of the 1,500,000 budget.

| File (src/truthtrail/data/recorded/) | Bytes | Lines | sha256 (scrub-2) | sha256 before the scrub-2 pass (scrub-1) |
|---|---|---|---|---|
| bluesky-2026-10-19.jsonl | 678,985 | 1,180 | 4ef9bd30a8d67a361488186822ad4193348f42f4fd3ddd483fd08c3dbe3ad91d | 6e39a1f9a460a15a2ccdcc8d8830d624d60d3f511738a999653fc943018a1d7e |
| bluesky-2026-10-19.samples.jsonl | 2,836 | 7 | 59a2ab8c5054f46328d336136fbfb810fb0a8d1ae1e074d63ddcb1f370878015 | a0beaefb1c39b9bba3d520ec98c7a9cdf617c28329522caafbdb2ffb9a388b3c |
| bluesky-2026-10-19.manifest.json | (see file) | - | (the manifest cannot hold its own hash) | - |

- **scrub-2 (host-aware URLs).** Allowlisted publisher URLs keep scheme, host and path (selection needs them), with UUID-shaped segments and hex runs of 20 or more characters mapped to `id0001`-style counters; gift links (`giftarticle.*` hosts) keep only the publisher's registrable domain and `/redeem/` paths are dropped. Shortener URLs keep the host only. Every other URL, and always `bsky.app`, `bsky.social`, `*.bsky.social`, `*.bsky.network`, `substack.com`, `note.com`, `t.me`, `x.com`, `twitter.com`, `instagram.com`, `facebook.com`, `tiktok.com`, `linktr.ee`, `*.bandcamp.com` and `*.blogspot.com`, becomes `https://nonlisted-<n>.invalid/`, numbered **per distinct URL** in first-seen order (two links to the same page share a number; two pages on one host do not), one numbering universe per file. Main file: 285 allowlisted URLs kept (13 ids mapped, 2 gift links reduced), 4 shortener URLs reduced to the host, 113 URLs replaced by 78 distinct placeholders; samples file: 1 URL replaced. Seed decisions are unchanged by construction (tests check it): tracked roots stay 149.
- **Adult self-labels (D-13).** The 3 frames carrying an adult self-label (`porn`, `sexual`, `nudity`; none were tracked roots, nothing referenced them) are dropped. scrub-1's coverage counter missed them (it counted a label only when the label was the refusal reason, and all three were refused earlier, for no link, not allowlisted and not top-level); the fixed counter counts labels on every negative control and gave 3 before the drop, 0 after.
- **Pseudonymised, not anonymised.** DIDs, rkeys and revs are sequential counter tokens and non-listed links are placeholders, but stream times, sequence numbers and `createdAt` are kept, so a party holding a third-party archive of the public network can join a frame back to the original record (the manifest's `privacy` block says so).
- **Not for rates.** The fixture is stratified and enriched for cascades (every recorded cascade with at least 3 children, a hash-ordered sample of the smaller ones, chosen negative controls and shapes); its counts are not rates of the network and must not be used to estimate shares. The measured rates are in this document.
- **Samples file.** One row per real probe frame: the v1 legacy-wire frames, the v2 envelopes and the cursor-test control shapes (`#info` `OutdatedCursor` and `FutureCursor`). It is scrubbed with its own token and placeholder universe, so its tokens never join to the main file.
- **Removal requests.** Anyone may ask for a record to be removed from the fixture by opening an issue at https://github.com/areveeess/TruthTrail/issues (asking for a private contact rather than posting the handle or link in public); the manifest records the same contact.
- `counts_by_kind` (main file): {"account": 22, "info": 0, "post_create": 605, "post_delete": 15, "repost_create": 525, "repost_delete": 10, "sync": 3}.
- `coverage` (the data contract plans 03-04 and 03-05 read by exact key, recomputed from the fixture by `test_manifest_coverage_matches_fixture`): tracked_roots 149; children_by_kind {"quote": 29, "reply": 245, "repost": 382}; cascades_with_replies 75, cascades_with_quotes 22, cascades_with_reposts 75, cascades_with_depth2_replies 38; orphan_replies 1; deletes {"post": 5, "repost": 5}; account_events_by_status {"active": 5, "deactivated": 5, "deleted": 5, "takendown": 5, "throttled": 2}; sync_events 3; negative_controls {"adult_labelled": 0, "near_miss_non_allowlisted": 40, "non_english_allowlisted": 10, "reply_with_link": 7, "shortener": 3, "total": 325}.
- `selection_policy`: require_lang en, sample_per_10k 10000 (the cutter never samples, because the sampling hash is over the RAW at-URI which the scrubbed fixture does not hold), no active-root cap, root TTL 48 h, per-cascade cap 5,000, and the 54 allowlist domains as used; later fixture-driven tests build their policy from this block, never from the editable allowlist file.
- `windows`: the three rows of the Run log (label, host, dialect, first and last stream time, stream seconds, frames, bytes, bounds, stop reason, raw sha256); the stream span adds up to 7,259.5 s.
- **First cut rejected.** The first cut contained real 32-hex article ids in link paths (key-lookalikes for the repo scans); the scrubber now maps hex runs of 32 or more characters to letters (commit d145e40) and the fixture was re-cut from the same raw logs. The scrub-1 hashes above are those of the second cut. The scrub-1 files remain in the branch history (commit 193daea); removing them from history is an owner decision (no history rewrite without an explicit instruction).
- **Shapes absent from the data (recorded as 0, never invented):** no adult-labelled allowlisted post and no `!no-unauthenticated` post occurred among the candidate roots in 7,260 s, and the three adult-labelled frames the cut did contain are dropped (`negative_controls.adult_labelled` 0); no `#info`/error frame is in the main file (the two real control shapes `OutdatedCursor` and `FutureCursor` and the real v1-dialect frames are in the samples file), and the fixture holds no post text or link-card title, so tests of those build `constructed_*` frames from the nearest real frame. The fixture holds 1 orphan reply, 3 sync events and 5 real delete frames of included posts and 5 of reposts.

## Risks

- **A5 runner reachability: not testable from this container.** Whether GitHub-hosted runners can reach the public Jetstream hosts is a Phase 6 verification item; no Phase 3 test depends on it.
- **A6 rate limiting of an unauthenticated tail: not observed, not excluded.** Seven thousand and some seconds of recording and about thirty short reads produced no throttling, no `ConsumerTooSlow`, no server-initiated close and no HTTP 401 or 403; the Jetstream RFD warns the unauthenticated v2 stream may be rate limited more strictly than the firehose, and no short test can exercise sustained limits.
- **Single-day bias.** All three windows fall on one Monday (2026-10-19 UTC, 07:41 to 13:57), none in a US evening, a night or a weekend. Volume and yield varied by a factor of 1.9 within those six hours (events per second 56.8 versus 103 to 106; eligible roots per hour 442 versus 826 to 830; share of posts deleted 3.9 to 10.0 percent). The daily extrapolation (x 24) is therefore indicative. At the recommended sampling the steady state is 41 percent of the budget: a true daily mean up to 1.47 times the measured one stays under the 60 percent design line and up to 1.97 times under the 80 percent stop (break-evens in S-8); a busier true mean is an assumption either way, and the collector's `capacity_reached` stop is the backstop.
- **Window truncation.** Windows are at most 61 minutes: 6-hour outcomes are unmeasured (n = 0), cascade sizes and per-root storage are lower bounds, and time-to-delete is censored at the window length.
- **Allowlist bias.** The list is an editorial, category-based choice (see Draft allowlist) and a disclosed selection bias; the sampling rate of whatever is ratified must also be disclosed.
- **Terms.** No research or machine-learning clause in the Bluesky pages (absence is not a licence). The GNews terms carry "Last Updated: October 18, 2026" (the research reading recorded October 16; what changed is unverified) and restrict the Free plan to non-commercial use; both are read again before the Phase 6 deploy; this is not legal advice.
- **GNews limits.** The Free plan gives 100 requests a day, at most 1 request a second, headlines with a 12-hour delay and non-commercial use only; a 403 means either an unverified email or the daily quota, so the news job classifies it by the body (S-10). The news context in the dashboard is therefore at least 12 hours old, and a public demo must stay non-commercial.
- **Budget source.** CONTEXT D-21 assumed a free-tier Postgres of about 0.5 GB and set `DB_BUDGET_BYTES` to 300 MB. Neon's pricing page (https://neon.com/pricing , "Last updated: 2026-10-31", retrieved 2026-11-05) lists the Free plan's storage as "1 GB/project, 20 GB account total". The 300 MB design budget stays (the smaller assumption wins, D-21), and the provider and its limit are re-checked in Phase 6.
- **Bloat from deletes and purges.** S-8 measured a fresh load. Deletes, tombstone purges and the text purge leave dead tuples and index bloat until vacuum reclaims them, so the real footprint is above the projection; the collector measures `pg_total_relation_size` (which includes bloat), so the 80 percent stop still holds, but it can be reached earlier than projected.
- **`capacity_reached` freezes ingestion.** When the stop at 80 percent of the budget fires, the collector stops storing new events (it never evicts), so cascades stop growing and new claims are not tracked until the purge job frees space; the dashboard must show this state rather than a silent gap.
- **Allowlist concentration.** One publisher supplies 30.5 percent of eligible roots and the top five 66.5 percent (Draft allowlist); the feed mirrors a few publishers' Bluesky audiences.
- **Stale and small cross-check.** The W1 AppView check ran 3 h 28 min after its window (a usage-limit pause); the W2 and W3 checks are fresh, but cover 100 roots per window, mostly childless, and direct children only (S-13).
- **Child-before-parent rate.** Not measured in the spike windows (analyzer defect, fixed after); an independent live re-measure on 2026-11-05 found 0 of 1,545 (95% upper bound about 0.2%), on a different day (S-4).
- **Raw logs deleted by design (D-01).** A different analysis means a new bounded run; the hashes above keep this run attributable.
- **Windows run pending (S-12).** The owner's 5-minute run on native Windows is requested at the checkpoint and does not block ratification.

## Recommended parameter table

Formulas from the plan, applied to the combined measurements (7,259.5 s, three windows). All values are PROVISIONAL until ratified. Derived inputs (not direct measurements): 15,199 eligible roots a day (hourly rate x 24) and 1,426 bytes per root (S-8); both are front-matter keys (`eligible_roots_per_day`, `bytes_per_root`) that the gate uses.

**Coupling enforced by the gate** (`check_spike_ratified.py` exits 2 when broken and warns above the 60 percent line):

    TRACK_SAMPLE_PER_10K / 10000 x eligible_roots_per_day x RETENTION_CASCADE_DAYS x bytes_per_root <= 0.8 x DB_BUDGET_BYTES
    TRACK_MAX_ACTIVE_ROOTS >= ceil(1.5 x TRACK_ROOT_TTL_HOURS / 24 x eligible_roots_per_day x TRACK_SAMPLE_PER_10K / 10000)

The effective cascade days are `RETENTION_CASCADE_DAYS` (the dormant rule's saving is not credited). A ratified override must name a parameter of `recommended_parameters`, keep its type and stay in range, or the gate exits 2.

| Parameter | Recommended | Arithmetic |
|---|---|---|
| `INGEST_REWIND_SECONDS` | 30 | max(30, ceil(2 x largest same-host stream-time inversion)) = max(30, ceil(2 x 0 s)) = 30 |
| `STORE_MAX_EVENTS_TOTAL` | 300,000 | min(300,000, floor(0.6 x 300,000,000 / 364.0 B per event row)) = min(300,000, 494,505) = 300,000 |
| `TRACK_SAMPLE_PER_10K` | 625 | per-root all-in 1,426 B; eligible 15,199 a day; steady state at 90 days = accepted roots a day x 1,426 x 90: 10000 -> 1,951 MB, 5000 -> 976, 2500 -> 488, 1250 -> 244 (81 percent, over the 80 percent stop: the gate rejects it), **625 -> 950 roots a day -> 122 MB (41 percent)**, 312 -> 61 MB; largest value at or below 180 MB is 625 |
| `TRACK_MAX_ACTIVE_ROOTS` | 2,850 | ceil(1.5 x 950 roots a day x 48 h / 24 h) = ceil(1.5 x 1,900) = 2,850 (CONTEXT's 500 would be the selector at any rate above 250 roots a day) |
| `TRACK_ROOT_TTL_HOURS` | 48 | unchanged |
| `RETENTION_CASCADE_DAYS` | 90 | fits at 625 (122 MB, 41 percent), so the 90-day default holds; `RETENTION_DORMANT_DAYS` stays 0 (a value of 7 would instead allow sampling 2,500, see OD-1) |
| `RETENTION_TEXT_DAYS` / `RETENTION_TOMBSTONE_DAYS` / `RETENTION_NEWS_DAYS` | 14 / 7 / 30 | unchanged (S-7 does not contradict them) |
| `TRACK_MAX_EVENTS_PER_CASCADE` | 5,000 | unchanged: max cascade 60 children, P99 10 (below the 2,000 trigger) |
| `CASCADE_MERGE_POLICY` | claim_group | S-9 does not contradict it (0 re-rooted children, 38.6 percent shared URLs) |
| `TRACK_SEED_CLAIM_URL_MATCH` | false | OD-3 recommendation is A |
| `TRACK_REQUIRE_LANG` | en | unchanged |
| `INGEST_MAX_SECONDS` / `INGEST_MAX_EVENTS` / `INGEST_MAX_STORED` | 300 / 500,000 / 20,000 | unchanged; catch-up table in the cursor section |
| `INGEST_MAX_RESUME_AGE_HOURS` | 30 | unchanged (under the measured 36.6-hour floor) |

Cross-check of the event count: steady state at 625 is 950 roots a day x 90 days x 1.684 events per root = about 144,000 stored events, under `STORE_MAX_EVENTS_TOTAL` 300,000 (the cap binds at 2.51 children per root, S-8 break-evens). The same JSON is the `recommended_parameters` front matter key and the options of the three Recommendation paragraphs are the `recommended_options` key (RT-2, M1, A).

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

Reply formats. Every reply that ratifies must carry three explicit confirmations, `pseudonym=d17` (the
one-way D-17 scheme), `dependencies=approved` (the package table) and `via_uri=true` or
`via_uri=false` (the schema hedge). Without them the gate stays closed (exit 1), even under
"recommended":

- `ratify recommended via_uri=true dependencies=approved pseudonym=d17`
- `ratify OD-1=RT-2 OD-2=M1 OD-3=A via_uri=true dependencies=approved pseudonym=d17` (change any
  value; add numeric overrides such as `TRACK_SAMPLE_PER_10K=312`; overrides must respect the
  coupling above, e.g. RT-1 with more sampling is the pair `TRACK_SAMPLE_PER_10K=2500
  TRACK_MAX_ACTIVE_ROOTS=11400`, 162.6 MB at 30 days)
- `more data: {what you want}` (no ratification; the raw logs are deleted, so a new bounded window
  is recorded)
- `revise scope: {M2, C or pseudonym=other}` (exit 3; the planner revises plans 03-03 to 03-07,
  plus 03-02 (OD-3 C) and 03-10 (docs))

Missing token: a reply such as `ratify recommended` without the tokens records nothing (it
does not confirm the one-way D-17 scheme, the dependencies or the schema hedge). The agent
then asks for the missing tokens only, and the owner replies exactly `pseudonym=d17` (and, if they
were also missing, `dependencies=approved` and `via_uri=true` or `via_uri=false`), never a yes or no.
`ratification_quote` then holds every owner message of the exchange verbatim, joined with ` / `.
