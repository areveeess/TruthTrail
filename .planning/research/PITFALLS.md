# Pitfalls Research

**Domain:** Misinformation early-warning system (news + social-propagation ingest, text classifier, cascade features / early detection, cascade simulator, deployed dashboard), built as a hiring-reviewer portfolio piece on top of a hackathon prototype
**Researched:** 2026-10-11
**Confidence:** MEDIUM-HIGH. Platform facts (Bluesky/Mastodon limits, Render free tier, ISOT confound, FakeNewsNet redistribution limits) were verified against current docs or papers. ML-methodology pitfalls (leakage, calibration, prevalence shift, early-detection protocol) are well-established practice from training knowledge and are tagged MEDIUM where not independently re-verified in this session.

**Phase numbering used below** (the roadmap owns the real numbers; map by name if they differ):
P1 Foundation (secrets, honesty, hygiene) / P2 Engineering baseline (layout, tests, CI, Docker) / P3 Real data ingest (incl. source spike) / P4 Detection + evaluation / P5 Dashboard / P6 Deploy / v2: P7 Cascade features + early detection / P8 Simulator / P9 Polish.

---

## Critical Pitfalls

### Pitfall 1: The classifier learns the outlet, not the claim (source / style / boilerplate leakage)

**What goes wrong:**
Reported accuracy is 95-100%, and it collapses on any news that did not come from the training outlets. The model keys on publisher fingerprints: a "(Reuters)" dateline, bylines, boilerplate footers, URL slugs, capitalization and punctuation habits, "Share this" text, or the outlet name itself. A 2025-26 paper, "Diagnosing Source Confounds in Fake-News Benchmarks," shows exactly this on ISOT, where "real" = Reuters and "fake" = a set of unreliable sites, and ranked shortcuts by class-conditional document frequency with "Reuters" at the top. Papers in the same literature report ISOT accuracy of 100% for XGBoost and 96-97% on FakeNewsNet/LIAR; those numbers measure outlet recognition, not misinformation detection (and one such paper in the results was retracted).

**Why it happens:**
Datasets built by "crawl trusted outlets for real, crawl junk sites for fake" make label and source perfectly correlated. TF-IDF + logistic regression finds the cheapest separating feature. Nothing in a random train/test split punishes this.

**How to avoid:**
- Prefer claim-level, fact-checker-labelled data (LIAR-style PolitiFact statements, ClaimReview-derived sets, PHEME rumours) over outlet-labelled article dumps. Decide in P4 and write down in the model card what the label means (claim rated false by fact-checkers vs. article from unreliable outlet).
- Never use ISOT, Kaggle "Fake and real news", or WELFake as the headline benchmark. If used at all, use only as a documented *negative example* ("here is why 99% means nothing") with the leakage canaries below.
- Run the leakage canary suite (see "Evaluation Integrity Protocol") before any number goes in the README: strip/mask outlet names, datelines, bylines, URLs, and speaker/party metadata; train a **source-only baseline** (outlet name as the sole feature); run a **cross-source holdout** (train on outlets A, test on outlets B); run a **shuffled-label** sanity check.
- Inspect the top-weighted features of the linear baseline and commit that table to the model card. If an outlet name, a person name, or punctuation is in the top 20, you have a shortcut.

**Warning signs:**
- Macro-F1 above ~0.90 on a claim-level task (published text-only results on LIAR-type data are far lower; treat 95%+ as a bug until proven otherwise). [MEDIUM]
- Source-only baseline is within a few points of the full model.
- Performance drops >15 points under cross-source or time-based holdout.
- Top features are proper nouns, "reuters", "via", "photo", "click".

**Phase to address:** P4 (dataset choice, preprocessing, canaries). The dataset *decision* belongs in the P3 spike so P4 does not start with a leaky corpus.

---

### Pitfall 2: Train/test contamination through near-duplicates, shared claims, and tuning on the test set

**What goes wrong:**
The same claim (or the same story re-published by 20 outlets, or the same PolitiFact statement quoted in several rows) lands in both train and test. A random split then rewards memorization. Separately, thresholds, regularization, and model choice are tuned on the test set, so the reported number is optimistically biased.

**Why it happens:**
`train_test_split(shuffle=True)` is the default, merged Kaggle datasets contain duplicates (WELFake merges four sources specifically and is known to carry duplicates/label noise [MEDIUM]), and hackathon-style notebooks tune "until the number looks good."

**How to avoid:**
- Deduplicate first (exact hash, then near-duplicate with MinHash/Jaccard or normalized-title match) and *then* split.
- Split by **group** (claim id / story cluster / event) and by **time** (train on older, test on newer). For rumour data (PHEME), use leave-one-event-out.
- Three-way split: train / validation (model selection, threshold, calibration) / test (touched once, at the end). Record the split seed and a hash of the split in `metrics.json`.
- Report bootstrap 95% confidence intervals. LIAR-sized test sets (~1.3k rows) give roughly +/-3 points of noise on macro-F1, so a "1-point improvement" is meaningless. [MEDIUM]
- Add a CI test that asserts zero ID/near-duplicate overlap between split files.

**Warning signs:**
- Train/validation/test scores all within 1 point of each other on a small, repetitive corpus.
- A new feature "helps" by 0.5 points and the README gets updated.
- The test set was loaded in more than one notebook cell/script before the final evaluation.

**Phase to address:** P4.

---

### Pitfall 3: Task and domain mismatch between the training data and what the live system scores

**What goes wrong:**
The classifier is trained on fact-checked political statements or fake-vs-real article bodies, but the product feeds it GNews headlines from mainstream outlets and Bluesky posts. These are different distributions (length, register, topic, prevalence of falsehood). The model returns confident, meaningless scores; nearly everything from reputable outlets looks "low", or the model flags every sensational headline regardless of truth. The prototype's "Medium by default" behaviour is reborn as a learned prior.

**Why it happens:**
Only labelled data exists for one distribution, and the demo needs another. Nobody measures out-of-domain behaviour because there is no label for it.

**How to avoid:**
- State the intended input type in the model card (e.g. "short English claim/headline text"). Train and evaluate on text of the same form as serving input: headline-length text, not full articles, if headlines are what the API scores.
- Build a small **out-of-domain probe set** (50-100 hand-labelled live headlines/posts, including obviously benign ones, since the prototype scored 9/10 benign probes High) and report the false-flag rate on it as a separate row in the results table. Label it honestly as small and non-representative.
- Give the API an **abstain / low-confidence** state: very short text, non-English, empty, or out-of-distribution input returns `risk: null, reason: "insufficient_signal"`, not Medium.
- Do not present a score on content the model was never evaluated for (non-English is out of scope in v1: detect language and refuse).

**Warning signs:**
- Score distribution on live headlines is a spike at one value, or its mean differs wildly from the validation distribution.
- Benign headlines from major outlets score above the review threshold.
- Everything scores identically for short inputs.

**Phase to address:** P4 (probe set, abstention), P5 (UI must render the abstain state).

---

### Pitfall 4: Misleading metrics, balanced test sets, and prevalence shift

**What goes wrong:**
Accuracy on a 50/50 corpus is reported as if it described deployment, where misleading content is a small minority. At 5% prevalence even a classifier with 90% sensitivity and 90% specificity has under 33% precision: two of three flags would be false alarms. Reviewers (the project's stated user) get flooded. Conversely, a majority-class predictor on an imbalanced set shows high "accuracy."

**Why it happens:**
Accuracy is the default metric, benchmark datasets are class-balanced by construction, and nobody recomputes precision at a realistic base rate.

**How to avoid:**
- Headline metrics: macro-F1, PR-AUC (against the positive-class base rate, shown as the no-skill line), and per-class precision/recall. Never lead with accuracy. (PROJECT.md already commits to macro-F1 and PR-AUC; enforce it.)
- Because the product is a **prioritization tool for human reviewers**, add ranking metrics: precision@k and recall@k at a fixed review budget, and a **"most-shared-first" popularity baseline**. If the model does not beat "sort by cascade size," it adds nothing; say so honestly if so.
- Report precision at 1%, 5%, 20% assumed prevalence (simple Bayes re-weighting of the validation confusion matrix), clearly labelled as an assumption.
- Include the baselines in one table: majority class, keyword rules (baseline 0, after fixing the substring bug so the baseline is not a straw man), TF-IDF + LR, then any transformer. Choose the threshold on validation, never on test.
- Class weighting or resampling is applied to *train only*; never resample before the split.

**Warning signs:**
- README's first metric is "Accuracy".
- Only one threshold (0.5) ever evaluated.
- Majority-class baseline not in the table.
- Resampling code appears above the split in the notebook.

**Phase to address:** P4 (metrics, baselines, threshold). Ranking/popularity baseline again in P7.

---

### Pitfall 5: "Confidence" that is not calibrated

**What goes wrong:**
The API returns `risk: 0.93` or "confidence 87%" straight from `predict_proba` or a softmax. Transformer softmax outputs are over-confident, LR trained with class weights is shifted, and neither reflects the prevalence at serving time. The dashboard's "risk with confidence" badge conveys false precision, which is exactly the overclaiming the project says it avoids.

**Why it happens:**
`predict_proba` looks like a probability; calibration is an extra step; ECE with too few samples or bins looks fine by accident.

**How to avoid:**
- Calibrate on the **validation** split (Platt/sigmoid or isotonic; temperature scaling for transformers), evaluate calibration on test: reliability diagram plus Brier score, ECE with a stated bin count and counts-per-bin shown. Do not calibrate on the test set.
- Separate two ideas in the API: `score` (calibrated probability under the training prevalence) and `band` (Low / Review / High, defined by thresholds chosen against reviewer budget). Never show a bare percentage to a user without the band and the "flag for review" framing.
- Where data are too few for stable isotonic regression (<~1k validation rows), use sigmoid, and show a confidence interval or coarse bands rather than decimals.
- Commit the reliability diagram image generated by the eval script into `docs/`.

**Warning signs:**
- Reliability curve hugs 0 and 1 (over-confidence) or sits far from the diagonal.
- Percentages displayed to 2 decimals.
- Calibration fit and calibration evaluation use the same split.

**Phase to address:** P4 (calibration + reliability diagram), P5 (how it is displayed).

---

### Pitfall 6: Overclaiming ("detects fake news") and implying ground truth

**What goes wrong:**
README, UI copy, or the interview pitch says the system "detects fake news" or shows a red "FAKE" badge. A hiring reviewer with ML background immediately discounts the project, and a non-expert user could treat a score as a verdict about a named person or outlet. The prototype already shipped hardcoded "High" risk for named public figures.

**Why it happens:**
Compelling narratives sell portfolios; classifier outputs are easy to over-interpret; "risk" can mean misleading, viral, or harmful, and these blur.

**How to avoid:**
- One glossary, used verbatim everywhere: the system flags text "similar to claims fact-checkers have rated false/misleading" **for human review**. It does not assess truth. Put the exact sentence in README, API docs (`description`), and dashboard footer.
- Distinguish three different quantities in the data model and UI: *content risk* (classifier), *propagation signal* (cascade stats), *synthetic/simulated* (never mixed with the first two).
- Ban list in review: "detects", "verifies", "truth", "fake" as a badge label, "AI-powered fact-checking". Add a grep check to CI over `README.md` and frontend strings (cheap, effective).
- Put the limitations section above the fold, with three concrete numbers: out-of-domain false-flag rate, precision at realistic prevalence, and the test-set size with CI.
- A "what this cannot do" list: cannot judge novel claims, satire, non-English, images, or context; can be evaded trivially; reflects annotator and dataset bias.

**Warning signs:**
- The word "detect" next to a truth word anywhere in the repo.
- A single large number (e.g. "94% accurate") in the README without dataset, split, and CI.
- UI colors that use pure red/green semantics for true/false.

**Phase to address:** P1 (copy rules + CI grep), P4 (results framing), P5/P6 (UI copy and README).

---

### Pitfall 7: Assuming social platforms give you a clean cascade tree (and recreating the prototype's impossible timelines)

**What goes wrong:**
The dashboard draws a deep, branching cascade, but the underlying platform data does not contain it:
- **Bluesky:** a repost is a record with a subject reference to the *original* post; it carries no parent chain, so reposts form a flat star around the root. Real depth is only recoverable from **reply** threads (strong parent/root references) and **quote** posts (an embedded strong reference). Drawing "who reposted from whom" requires inference, which must be labelled as inferred or not drawn. [MEDIUM: structure from atproto docs for replies/quotes; repost structure from protocol knowledge]
- **`createdAt` is client-supplied** in the post record ("each post requires text and createdAt"), so it can be wrong, backdated, or in the future. Using it to order events can yield children before parents: the same defect found in the prototype (about 40% of simulated events precede their parent). Use the stream's own receipt time (Jetstream `time_us`) as the ordering key and keep `createdAt` as a separate, untrusted field.
- **Mastodon:** federation means each instance only sees the slice of the network its users interact with; boost counts on a status are instance-local views, and the public timeline may require an app token if the instance disabled public preview. [HIGH: Mastodon docs]
- Whatever you ingest is an **observed subset** of the true cascade, and it is right-censored at ingest time.

**Why it happens:**
Tutorials and papers assume Twitter retweet trees (which had a parent per retweet). Authors draw a tree because the library makes it easy.

**How to avoid:**
- Define the cascade data model in P3 from what the platform actually emits: nodes = posts/reposts/quotes/replies; edges only where the protocol provides an explicit reference; edge `kind` in {reply, quote, repost-of-root}; `inferred: bool` for anything else.
- Store both `observed_at` (ingest time) and `claimed_at` (record timestamp). Add a DB constraint or ingest-time assertion: an edge target must exist and `observed_at(child) >= observed_at(parent)`; log and quarantine violations rather than "fixing" them silently.
- UI caption on every cascade view: "Observed subset of public posts on <platform>, as of <time>."
- Pick the P3 platform with the structure you need in mind: Bluesky gives a complete public firehose (no instance sampling bias) but flat reposts; Mastodon gives per-instance partial views. The Bluesky choice is the better default for completeness; Mastodon only if you can name the instances and accept the bias.

**Warning signs:**
- Graph has any edge whose child timestamp precedes the parent.
- A tree deeper than 2-3 levels from a platform with flat reposts.
- Cascade sizes in the live demo look suspiciously smooth or uniform.

**Phase to address:** P3 (data model, ordering key, invariants), P5 (caption and honest rendering).

---

### Pitfall 8: Temporal leakage in cascade features and "early detection"

**What goes wrong:**
An "early detection" result is reported that actually uses information from after the detection time: features computed on the full cascade (final size, final depth, total unique users) while claiming detection at 1 hour; labels derived from cascade outcome (e.g., "viral" = size > N) so the model predicts its own label; train/test split that is random across time so future-era topics inform the past; or the fact-check verdict timing ignored, so the "early warning" arrives after the debunk. The headline "AUC 0.93 within 30 minutes" is then unreproducible in real time.

**Why it happens:**
Cascade datasets ship complete cascades; it is easy to compute features on everything and truncate afterward (or forget to). Virality prediction and misinformation detection are conflated, but virality is a different label.

**How to avoid:**
- Implement features as a pure function `features(cascade_events, t0, horizon)` that *physically filters* events with `t - t0 <= horizon` before computing anything, and unit-test it with a property test: appending later events must not change features at that horizon.
- Evaluate on a **horizon curve** (e.g., 5 min / 30 min / 1 h / 6 h / 24 h): metric versus the information available. "Early" is a claim about the left side of the curve and about lead time versus the fact-check publication time.
- Labels must come from an **external** source (fact-check verdict), never from cascade size or engagement.
- Time-based split, and for rumour datasets leave-one-event-out (standard practice for PHEME).
- Include a **volume-only baseline** (event count in the first N minutes). Many cascade "detectors" are volume detectors in disguise; a structural-feature model has to beat it.
- Handle right-censoring: cascades that are still growing at ingest time must be flagged, not treated as finished.

**Warning signs:**
- Feature code computes `len(cascade)` or `max(depth)` without a time cutoff argument.
- Performance is nearly flat across horizons (suggests leakage from outcome features).
- Label-related columns (counts) appear in the feature importance top 5.

**Phase to address:** P7 (primary), with the `features(t0, horizon)` interface contract decided in P3's data model.

---

### Pitfall 9: No ground-truth labels on the live cascades, and unusable legacy datasets

**What goes wrong:**
The team ingests live Bluesky/Mastodon cascades and then cannot say whether any of them are misinformation: there are no labels, so a cascade classifier cannot be trained or evaluated on the data the demo shows. The fallback is to train on the classic Twitter-era datasets, but FakeNewsNet states that the complete dataset cannot be distributed because of Twitter privacy policies and publisher copyright, so you must rehydrate tweets through a downloader. Rehydration is now effectively unavailable on the free tier, and deleted tweets and suspended accounts are unrecoverable, which is non-random: deleted/suspended content skews toward the interesting class, biasing whatever remains. Also, train-on-Twitter / demo-on-Bluesky is a platform domain shift.

**Why it happens:**
Datasets are advertised by their label counts, not by what can be downloaded today; live data and labelled data come from different worlds.

**How to avoid:**
- Be explicit about two separate evidence streams in the architecture and results table: (a) **text classifier** evaluated on a labelled text dataset (P4); (b) **cascade features** evaluated on a labelled propagation dataset whose structure ships *without* rehydration (e.g., Twitter15/16 and PHEME ship usable propagation structure; verify license and what is actually in the download before committing to one) (P7). Live Bluesky cascades are shown *descriptively* with the classifier score; do not claim the cascade model was validated on them.
- Spike item for P3/P7: write down for each candidate dataset: what is in the download today, file sizes, license, whether tweet text is present, whether user IDs are pseudonymized, whether the number of retrievable items matches the paper.
- Report coverage honestly ("N of M items retrievable").
- Optional, only if time: a small hand-labelled set of live cascades linked to existing fact-checks (match by URL/claim), clearly marked as a demonstration, not an evaluation.

**Warning signs:**
- A plan that says "train the cascade model on Bluesky" with no label source.
- Dataset download script depends on an API tier you do not have.
- Dataset item count in the paper differs from what loads.

**Phase to address:** P3 (spike decides sources), P7 (cascade evaluation).

---

### Pitfall 10: A simulator that looks real but is not validated

**What goes wrong:**
The "cascade simulator" produces plausible-looking graphs, but its parameters were picked by eye, its output distribution has never been compared to real cascades, and it may be used to generate training features (then the detector is evaluated on the generator's own assumptions: circular validation). In the worst case it leaks into the live path again, as the prototype's `simulate_spread` did, with fabricated users shown as analysis.

**Why it happens:**
Simulators are fun and visual; validation is dull. The prototype provides a template for "random events that look like data."

**How to avoid:**
- Pick a documented generative model (branching process / Galton-Watson with heavy-tailed offspring, or a Hawkes-style process) and cite the form; fit parameters to the cascades you actually ingested in P3.
- Validate by **comparing distributions to real cascades**, not by eyeballing: cascade size (heavy-tail, log-log plot), depth, structural virality or branching factor, inter-event time distribution. Show simulated vs. real overlaid in the README and put the comparison script in CI-runnable form (small seeded sample). State where it fails.
- Invariants as property tests (seeded RNG, Hypothesis): child time >= parent time, acyclic, single root, event count within bounds, deterministic given seed. These directly close the prototype defects (unseeded randomness, children before parents).
- **Hard separation:** simulator lives in its own module/package, outputs carry `synthetic: true` at the event and response level, rendered with a persistent "SIMULATION" banner and a different visual style; no code path from simulator output to the risk score or to the live cascade view.
- Never train or evaluate the detector on simulator output and report it as a result. Use the simulator for what-if exploration (change branching rate -> see effect) and show parameter uncertainty.
- If the simulator cannot be validated within the v2 time budget, cut it or ship it labelled "illustrative, unvalidated" rather than as analysis.

**Warning signs:**
- Simulator output has no seed parameter or no `synthetic` field.
- No figure compares simulated to real cascades.
- Same module imported by both the live endpoint and the simulation endpoint.

**Phase to address:** P8 (primary); P2 (seed/invariant test pattern established when fixing the prototype simulator); P1 (`DEMO_MODE` + `synthetic: true`).

---

### Pitfall 11: Platform terms, rate limits, data redistribution, and deletions

**What goes wrong:**
- Committing or publishing a scraped corpus of social posts (as a repo file, Kaggle dataset, or demo fixture) violates terms, privacy expectations, or both. A 1M-Bluesky-posts dataset released on Hugging Face in 2024 was pulled after backlash from users, even though the posts were public (the follow-up academic release removed usernames and post URIs, coarsened timestamps to the minute, and offered GDPR opt-out). [HIGH: 404 Media report, arXiv 2404.18984, Zenodo record]
- Ignoring **deletions**: if a user deletes a post, the stream emits a delete; your DB keeps displaying it.
- Hitting rate limits and getting blocked: Mastodon default is 300 requests per 5 minutes per account and per IP, varies by instance [HIGH]; Bluesky's hosted PDS applies 3000 per 5 minutes per IP overall, and `createSession` is limited to 30 per 5 minutes and 300 per day per account, so logging in on every request or every container restart will lock you out [HIGH: bsky.network rate-limit docs]. Bluesky's unauthenticated `public.api.bsky.app` is cached and intended for "public web" use; the firehose/Jetstream is the right tool for streaming, not polling.
- Treating FakeNewsNet-style "dataset available" as redistributable.
- Storing and republishing news article **bodies** (publisher copyright) instead of headline + URL + your derived scores.

**Why it happens:**
"It's public, so it's fine." Rate limits are only discovered when blocked. Deletion handling is invisible in a demo.

**How to avoid:**
- P3 spike deliverable (one page, in `docs/`): for the chosen source, ToS URL and date read, rate limits, what may be stored, whether redistribution is allowed, retention policy, and an explicit "we do not redistribute raw posts" decision. Re-read at P6 before going public.
- Store the minimum: post URI/ID, hashed author ID (salted), timestamps, edge kind, counts, and a language/URL-domain summary. Keep post text only transiently or with a short TTL if the classifier needs it; do not commit any raw data. `data/` is `.gitignore`d; ship a **synthetic-free tiny fixture** hand-written for tests, and a script to fetch data.
- Process delete events: remove or tombstone the record and its text; run a purge job.
- Use the stream, not polling; honor `429` and `Retry-After`/rate-limit headers with exponential backoff and jitter; persist a stream cursor so reconnects do not re-read or lose events; reuse a Bluesky session token instead of calling `createSession` repeatedly; use an app password, never the main password, and keep it in the environment only.
- Link news -> social by **URL** (canonicalize: strip UTM, resolve known shorteners, normalize host/path) and a domain allowlist; do not store the whole firehose (storage on a free Postgres tier is small).
- Headline + URL + source + timestamp only for news; no article body storage.

**Warning signs:**
- A `data/` or `*.jsonl` of real posts in the diff.
- 429s in logs, or a login call per request.
- Ingest worker has no cursor persisted; every restart replays or skips.
- Deleted posts still render.

**Phase to address:** P3 (terms spike, minimal schema, cursor, backoff, deletions), P6 (re-check before public deploy), P9 (data statement).

---

### Pitfall 12: Entity, topic, and political bias (the prototype's name-based rules, learned instead of hardcoded)

**What goes wrong:**
Hardcoded "High" for named public figures was a known prototype defect. A trained model reproduces it implicitly: fact-checker datasets over-represent certain politicians and topics (a handful of names dominate PolitiFact-style corpora), so "mentions Politician X" becomes a feature for "false." The tool then systematically flags one side's speakers, and a displayed cascade can attach the label to real, named accounts, enabling harassment.

**Why it happens:**
Label sources sample what fact-checkers choose to check; names are strongly predictive in-sample and nobody slices metrics by entity.

**How to avoid:**
- Delete all name-based rules; do not add the old list to baseline 0 either (baseline 0 = word-boundary keyword content rules only; document the removal).
- Evaluate **slices**: per topic, per frequently-named entity or party where available: report macro-F1 and false-flag rate per slice and the gap.
- **Counterfactual swap test:** replace named entities with placeholders or swap equivalent names ("Candidate A said...") in the test set and measure score change; commit the result. Consider training with entity masking (spaCy NER or a name list) and compare.
- Pseudonymize accounts in the UI and screenshots (short hashed IDs; never real handles in the README GIF). Do not label accounts "bot," "troll," or "spreader." The tool analyzes claims and propagation, not people.
- Put a bias/limitations section in the model card with the slice table and its caveats (small slices => wide CIs).

**Warning signs:**
- Top LR features include politician names.
- Score changes more than a few points under name swapping.
- Demo screenshot shows a real, identifiable handle next to a "High" badge.

**Phase to address:** P4 (slices, swap test, masking), P5 (pseudonymized display), P9 (model card polish).

---

### Pitfall 13: Prototype defects reborn as silent fallbacks, stale data shown as live, and fabricated "Medium" defaults

**What goes wrong:**
New pipeline code copies the prototype's habits: upstream failure returns 200 with a plausible placeholder; the ingest worker dies and the dashboard shows hours-old data as "live"; the classifier returns "Medium" for short or odd text because nothing forces an abstain; a cache serves stale results with no timestamp; `DEMO_MODE` is on in production because a default was left `true`.

**Why it happens:**
Hackathon error handling optimizes for "the demo never breaks." It's the same instinct that produced the 200-with-fake-article fallback (CONCERNS: "Fallback timestamp is fabricated," "Fallback masks upstream quota exhaustion").

**How to avoid:**
- Every response carries provenance: `data_as_of`, `source_status` in {ok, empty, upstream_error, stale}, `synthetic: bool`. UI shows a visible "last event ingested N min ago" and goes to an explicit stale/offline state past a threshold.
- Honest status codes (502/503) for upstream failure; contract tests for each (these are already P2 targets: write them before refactoring).
- `DEMO_MODE` defaults to false, is read from the environment, and when true stamps every event `synthetic: true` and renders a banner; add a startup log line and a CI test that production config has it off.
- Provide a **recorded replay mode**: a small stored set of *real, previously ingested* cascades (not fabricated) behind `REPLAY_MODE`, labelled "recorded on <date>." This keeps the demo alive when upstream is down without lying. Keep it distinct from synthetic data.
- Abstain explicitly in the classifier (Pitfall 3); no default class.
- Seed all randomness used anywhere (tests, sampling, simulator) and record seeds.

**Warning signs:**
- A `try/except` that returns a non-error response.
- Any code path producing a user or timestamp that did not come from a source.
- Demo looks fine while the ingest process is down.

**Phase to address:** P1 (DEMO_MODE, honest errors), P2 (tests for failure paths), P3 (freshness), P5 (stale/empty/error UI states).

---

### Pitfall 14: Portfolio-specific traps: dead demo, no eval numbers, unreproducible results

**What goes wrong:**
A hiring reviewer clicks the demo link and gets a one-minute cold start, a 500, or an expired database; or finds a README with no results table; or tries `docker compose up` and it fails; or the numbers in the README cannot be regenerated. Specific hazards for free hosting: Render free web services spin down after 15 minutes idle and take about a minute to wake, and **free Render Postgres expires 30 days after creation** with a 14-day grace before deletion and no backups [HIGH: Render docs, accessed this session]. Other free tiers have analogous sleep/expiry limits; verify at P6 time.

**Why it happens:**
Deploy is left to last; results live in a notebook; README numbers are typed by hand; the dev container is ephemeral so unsaved state disappears (PROJECT.md notes this).

**How to avoid:**
- Treat "deployed and working from a clean clone" as a P6 acceptance test run by someone (or a fresh container) other than the author's warm environment: `git clone` -> `docker compose up` -> dashboard shows data.
- Pick hosting that matches the data lifecycle: use a Postgres with no 30-day expiry (verify current terms of the provider at P6), or make the DB rebuildable from a script plus the replay snapshot. Add a keep-warm or a "waking up" UI state; document cold-start behaviour in the README so it reads as a known tradeoff.
- Results table in README is **generated** from `reports/metrics.json` by a script (`make eval` -> `reports/metrics.json` + figures); CI fails if the README table and the JSON disagree. Record in the JSON: git SHA, dataset name+version+hash, split seed, library versions, date.
- Pin everything (`requirements.txt` or lock file; prototype had none), fixed seeds, deterministic splits; a `make eval` that runs in under ~15 minutes on CPU for the baseline model.
- Always include: architecture diagram, demo GIF (with pseudonymized data), results table with CIs, model card, limitations/ethics. Reviewers skim for these.
- Add an uptime check (cron/GitHub Action pinging `/health` weekly) and a README line: "last verified <date>".
- Keep a fallback: a recorded video/GIF of the working demo in the README so the project is still credible if hosting dies.

**Warning signs:**
- README has screenshots but no metrics or no command to reproduce them.
- "Works on my machine" Docker image that only builds with cached layers.
- Hosting credentials expiring within the interview season.

**Phase to address:** P2 (pinning, Docker, `make` targets), P4 (metrics.json generation), P6 (clean-clone acceptance, hosting choice, health check), P9 (polish).

---

### Pitfall 15: ML artifacts and data in the repo (weights, datasets, notebooks, pickles, image bloat)

**What goes wrong:**
Multi-hundred-MB model weights or dataset files are committed (permanent repo bloat, license trouble, clones become slow); notebooks with embedded outputs, tokens, or sample raw posts get committed; `pickle`/`joblib` models are loaded without version pinning (breaks on sklearn upgrade, and unpickling untrusted files executes code); the serving image pulls in `torch` and balloons to multiple GB and exceeds free-tier memory.

**Why it happens:**
The prototype had no `.gitignore`; ML habit is to checkpoint everything; "just add the model so the demo works."

**How to avoid:**
- `.gitignore` for `data/`, `models/`, `*.pkl`, `*.pt`, `*.onnx`, `.env`, `__pycache__`, `.ipynb_checkpoints` in P1 (PROJECT.md already says no weights in the repo; keep to it).
- Commit: training/eval code, `metrics.json`, model card, confusion matrix and reliability images, dataset fetch script with checksum.
- For serving, prefer a small artifact (TF-IDF + LR as a pinned `joblib` pipeline or exported coefficients, <~50 MB) generated by a documented `make train` step and fetched at container build or from a release asset, not git. Record sklearn version in the artifact metadata and fail loudly on mismatch.
- If a transformer is added in v2: train offline (Colab/Kaggle, per PROJECT.md), export to ONNX or distil; check the free-tier RAM budget before promising it; keep the TF-IDF model as the always-works fallback and say which one the live demo runs.
- Strip notebook outputs (`nbstripout`) and scan for secrets before commit; do not paste API keys or Colab tokens into notebooks.
- Separate `requirements-train.txt` and `requirements-serve.txt` (or optional extras) so CI and Docker do not install training stacks.

**Warning signs:**
- `git count-objects -vH` growing by >10 MB on a commit.
- Dockerfile `pip install torch` for an LR model.
- `.ipynb` diffs with huge base64 blobs.

**Phase to address:** P1 (`.gitignore`, secret scan), P2 (requirement split), P4 (artifact handling), P6 (image size/RAM).

---

## Moderate Pitfalls

### Pitfall 16: Treating label noise and label semantics as ground truth
**What goes wrong:** Six-level PolitiFact-style labels ("barely true", "half true") are collapsed to binary with an undocumented cut, or fact-checker verdicts are time- and annotator-dependent; scores are then reported with false precision.
**Prevention:** Document the label mapping in the model card; report both the original multi-class and the collapsed binary result; treat borderline classes as ambiguous (report ablation dropping them). Check label agreement on a small sample by hand and report it.
**Phase:** P4.

### Pitfall 17: Evaluating with an LLM or pretrained model that has seen the benchmark
**What goes wrong:** A pretrained transformer or an LLM zero-shot baseline has memorized popular fact-check datasets; its test score is contaminated.
**Prevention:** Say so in the results table ("possible pretraining contamination"); prefer a held-out, post-training-cutoff probe set for any LLM/transformer comparison; keep the TF-IDF baseline as the interpretable reference.
**Phase:** P4 (v2 model fine-tune section).

### Pitfall 18: Linking news to social posts by keyword or headline text
**What goes wrong:** Matching a headline to posts by shared words yields unrelated cascades; "cascade" then means "posts about the same topic," not "propagation of the same item." Attribution errors multiply across shorteners, UTM variants, and quote posts.
**Prevention:** Anchor cascades on a **canonical URL** (or on an explicit reply/quote/repost reference), canonicalize URLs, and record the link method on each cascade (`anchor: url|quote|reply`). Report the fraction of posts linked by each method.
**Phase:** P3.

### Pitfall 19: Ingest volume and storage sizing
**What goes wrong:** Subscribing to the whole firehose (Jetstream) and writing every event overflows a free-tier database (1 GB on Render's free Postgres) and saturates a small worker within days.
**Prevention:** Server-side filter by collection (Jetstream `wantedCollections`), then filter in-process by a domain allowlist before writing; batch inserts; idempotent upserts keyed by AT-URI/status ID; retention (e.g., 7-14 days) with a purge job; monitor row counts.
**Phase:** P3, P6.

### Pitfall 20: Free GNews tier quotas and delayed/limited results
**What goes wrong:** The free tier's request cap and result limits (prototype fetches `max=1`) make "real news ingest" thin; bursts from the dashboard exhaust the quota; the free tier may delay articles (verify current plan terms before depending on it). [LOW until verified against current GNews plan page]
**Prevention:** Server-side TTL cache and a scheduled fetch rather than per-request calls; per-day quota budget in config; second provider adapter behind the existing `fetch_news` seam; store headline + URL only.
**Phase:** P2 (cache, timeouts), P3.

### Pitfall 21: Bots, spam, duplicates, and NSFW/abusive content in live social data
**What goes wrong:** Coordinated posts, repost farms, and slurs/NSFW content show up in the cascade view; the demo GIF captures something unfit for a portfolio.
**Prevention:** Skip posts with moderation labels or adult self-labels; language filter (English only in v1); dedupe by text hash within window; cap displayed text length; don't autoplay media. Do not claim to detect bots (see Pitfall 12).
**Phase:** P3 (filters), P5 (render).

### Pitfall 22: Rendering user-generated text unsafely
**What goes wrong:** Post text and link previews from the social platform flow into the dashboard; `dangerouslySetInnerHTML`, un-sanitized links, or server-side URL fetching (SSRF) opens XSS/SSRF. (Carries over CONCERNS "Upstream data reflected without sanitization.")
**Prevention:** Render as text only; if links are shown, `rel="noopener noreferrer"` and scheme allowlist (http/https); never fetch URLs found in posts from your server except via an allowlisted, timeout-bounded fetcher; cap field lengths in Pydantic models.
**Phase:** P2 (response models), P5.

### Pitfall 23: Graph visualization scale and wrong library
**What goes wrong:** Recharts (already in `package.json`) is a chart library, not a graph layout engine; trying to draw a few-thousand-node cascade in SVG freezes the browser.
**Prevention:** Use a graph/network lib (d3-force, Cytoscape, or Sigma/graphology) for the cascade and keep Recharts for the timeline; cap rendered nodes (aggregate leaves beyond N), paginate; test with a worst-case cascade fixture.
**Phase:** P5.

### Pitfall 24: Tests that pin model outputs, or CI that downloads datasets
**What goes wrong:** Unit tests assert exact scores from a trained model (flaky across retrains); CI pulls the dataset and takes 20 minutes or fails on a network blip.
**Prevention:** Tests use a tiny fixture model and hand-written fixtures; evaluation is a separate manual/scheduled job (`make eval`) with an artifact; CI asserts invariants (schema, ranges, determinism with seed, no overlap between splits) not exact scores.
**Phase:** P2, P4.

### Pitfall 25: Keyword baseline as a straw man (or as an unfixed bug)
**What goes wrong:** "Baseline 0" is the buggy substring matcher (9/10 benign probes scored High), so any model looks great. A reviewer sees through this.
**Prevention:** Characterization tests first (pin the buggy behaviour as documented), then report **both** "prototype as shipped" and "prototype with word-boundary fix" in the results table. Beat the stronger one.
**Phase:** P2 (characterization tests), P4 (baseline rows).

---

## Minor Pitfalls

### Pitfall 26: Timestamps and timezones
**What goes wrong:** Mixed `Z`, offsets, naive datetimes, and microsecond epochs (`time_us`) across sources produce off-by-hours cascades.
**Prevention:** One parsing helper at the ingest boundary; store UTC `timestamptz`; emit one format in the API; unit tests with `Z`, `+00:00`, `+05:30`, fractional seconds.
**Phase:** P2/P3.

### Pitfall 27: Logging secrets and URLs
**What goes wrong:** GNews key travels as a query parameter and lands in logs; Bluesky app password or Mastodon token in error messages.
**Prevention:** Never log full URLs or `params`; redact in error handlers; secret scan (gitleaks-style) in CI and pre-commit; `.env.example` with names only.
**Phase:** P1/P2.

### Pitfall 28: Hype dependencies and over-scoping v2
**What goes wrong:** Time is spent on GNN cascade models, LLM explainers, or Kubernetes instead of finishing evaluation and deployment. v1 must stand alone.
**Prevention:** Gate v2 on a v1 "done" checklist; one method per v2 feature, with the simplest baseline first (hand-crafted cascade features + gradient boosting before any GNN).
**Phase:** roadmap level.

### Pitfall 29: Unrealistic expectations for text-only accuracy
**What goes wrong:** Disappointment or a rewrite when honest, leak-free metrics come out modest.
**Prevention:** Plan the README story around *measured improvement over baseline 0 with CIs and honest limits*; modest honest numbers plus a rigorous protocol read better to ML reviewers than 99% claims.
**Phase:** P4 framing.

---

## Evaluation Integrity Protocol (gate for P4, reused in P7)

All must pass before any metric appears in the README:

1. **Dedupe then split** (exact + near-duplicate); group split by claim/story/event; time split where timestamps exist. Test: zero ID overlap and near-duplicate overlap below a stated threshold, asserted in CI.
2. **Three sets** (train / val / test); model selection, threshold, calibration only on val; test evaluated once; split seed and split hash stored.
3. **Leakage canaries:** (a) source-only baseline, (b) metadata-stripped input (outlet, byline, dateline, URL, speaker, party), (c) cross-source/outlet holdout, (d) shuffled-label run should land at chance, (e) top-feature inspection committed to the model card.
4. **Metrics:** macro-F1, PR-AUC with base-rate line, per-class P/R, bootstrap 95% CI, precision@k, precision at assumed 1/5/20% prevalence, Brier + reliability diagram. Baselines: majority, keyword rules (as shipped and word-boundary-fixed), popularity ("most-shared first") where cascade data exist, TF-IDF+LR, then any larger model.
5. **Slices and robustness:** entity/topic slices, name-swap counterfactual, out-of-domain probe set false-flag rate, short/non-English/empty-input behaviour (abstain).
6. **Reproducibility:** `make eval` regenerates `reports/metrics.json` and figures; README table generated from it; versions, seed, dataset hash, git SHA recorded.
7. **Honest framing:** model card states data, label definition, intended use ("flag for human review"), out-of-scope uses, known biases, and limitations.

For P7 add: `features(events, t0, horizon)` leakage property test; horizon curve; volume-only baseline; external-label requirement; leave-one-event-out.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Random train/test split | One line of code | Inflated metrics via duplicates/shared claims; reviewer-visible flaw | Never for reported numbers |
| Tuning threshold on test set | Better-looking number | Biased result, not reproducible in deployment | Never |
| Using `predict_proba` as "confidence" | No extra work | False precision; undermines core value | Only as an internal feature before P4 calibration lands |
| Hardcoding a small fixture of "real-looking" cascades for the demo | Demo never breaks | Reintroduces fabricated data | Only if clearly labelled `synthetic: true`/"recorded replay" and never default |
| Saving model as `.pkl` in repo | Demo works after clone | Repo bloat, unpickle risk, version breakage | Never; build via `make train` or release asset |
| README numbers typed by hand | Fast | Drift; unverifiable | Never after first metrics.json exists |
| Storing raw post text indefinitely | Easy re-processing | Privacy/ToS risk, DB bloat | Only with TTL and delete handling |
| Single process ingest + API | Simple deploy | Ingest crash takes down API; restarts lose cursor | Acceptable in v1 if cursor persisted and health shows ingest freshness |
| Skipping Postgres for SQLite/in-memory | Fast start | Deviates from the declared stack; no persistence on ephemeral hosts | Only for unit tests |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Bluesky Jetstream / API | Polling REST for new posts; logging in per request; trusting `createdAt` for ordering; ignoring deletes | Subscribe to the stream with `wantedCollections`; persist cursor; reuse session (createSession limited to 30/5 min, 300/day); order by stream receipt time; handle delete events |
| Bluesky reposts/quotes | Assuming a repost tree | Reposts reference the root only; depth comes from replies/quotes; mark inferred edges |
| Mastodon | Assuming a global view and unauthenticated public timeline | Public timeline may require an app token; per-instance limits (default 300/5 min); partial federated view; document chosen instances |
| GNews | Per-request calls, `max=1`, no timeout, 200-on-failure | Scheduled fetch + TTL cache, timeout, honest 502/503, quota budget, headline+URL only |
| Twitter-era datasets (FakeNewsNet, Twitter15/16) | Expecting a full download; rehydrating tweets | Check what ships today; use processed structure; report retrievable fraction; do not redistribute |
| Fact-check datasets (LIAR, PolitiFact-derived) | Using speaker/party/context columns as features | Drop metadata that leaks the label; report with and without |
| Postgres on free hosting | Assuming permanence | Check expiry and size limits (Render free: 1 GB, expires after 30 days); make DB rebuildable |
| Colab/Kaggle training | Secrets/tokens in notebooks, no seeds, ad hoc data copies | Pull training code from the repo, fixed seeds, export only metrics + small artifact |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Writing every firehose event to Postgres | DB fills, ingest lags | Filter at stream and by URL-domain allowlist; batch upserts; retention purge | Within days on a 1 GB free DB |
| Per-request transformer inference in a sync FastAPI route | Latency spikes, worker starvation | Small model, load once at startup, batch/async or `run_in_threadpool`; cache by text hash | A handful of concurrent users |
| Model loaded lazily on first request | First request after cold start times out | Load at startup; readiness probe separate from `/health` liveness | Every cold start on free tiers (~1 min wake) |
| SVG graph with thousands of nodes | Browser freezes | Graph lib with canvas/WebGL, node cap, aggregation | Roughly >1-2k nodes |
| N+1 queries when assembling a cascade | Slow dashboard | Single recursive CTE or adjacency fetch, index on `parent_id`, `anchor_url`, `observed_at` | Cascades with hundreds of events |
| Unbounded `/analyze` input and no cache | Quota burn, CPU abuse | Pydantic length limits, rate limit, TTL cache | First public link share |
| Eval job in CI | Slow/flaky CI | Separate scheduled/manual eval; CI runs tiny fixtures | Any dataset download |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Real credentials in notebooks, scripts, or `.planning/` | Key leak (already happened once: GNews key in `1fedcd2`) | Env-only config, secret scan before every commit (orchestrator rule), `nbstripout`; history purge only if owner asks |
| Unpickling untrusted/unpinned model files | Arbitrary code execution or breakage | Build artifacts yourself in CI/release, pin sklearn, verify checksum; never load user-supplied pickles |
| Rendering post text as HTML | Stored XSS via social content | Text-only rendering, scheme-allowlisted links, length caps |
| Server-side fetching of URLs from posts | SSRF to internal addresses | Don't fetch; or allowlist + block private ranges + timeout |
| Open CORS and no rate limit on public deploy | Quota exhaustion, abuse | Restrict origins to the frontend URL; per-IP rate limit; caching |
| Storing identifiable user data from social platforms | Privacy/GDPR exposure, takedown | Hash author IDs with a secret salt, honor deletes, retention TTL, no raw dataset publication |
| Using main account credentials for Bluesky | Account compromise | App password via env, least privilege; read-only use needs no login for public endpoints |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Red "FAKE"/green "TRUE" badges | Reads as verdict; harms named parties | Neutral band labels ("Review suggested", "Low signal", "Not enough information") with calibrated score and CI |
| Bare percentage | False precision | Band + range + short explanation of what it means |
| No abstain state | Garbage-in confident output | Explicit "insufficient signal" UI |
| Cascade graph without provenance caption | Looks like complete ground truth | "Observed subset, <platform>, as of <time>"; edge type legend; inferred edges dashed |
| Synthetic data visually identical to real | Fabrication | Persistent banner, distinct styling, `synthetic` badge on every simulated node |
| Real handles in screenshots | Doxxing/harassment risk | Pseudonymized IDs everywhere including the GIF |
| No loading/stale/error states | Looks broken on cold start | Skeletons, "waking server" message, "last updated" and stale indicator |
| Risk and virality shown as one signal | Conflates "popular" with "misleading" | Two separate, labelled encodings |

## "Looks Done But Isn't" Checklist

- [ ] **Classifier:** Often missing a leakage check -- verify source-only baseline, cross-source holdout, and top features are in the model card.
- [ ] **Evaluation:** Often missing CIs and a popularity/majority baseline -- verify `metrics.json` has bootstrap intervals and baseline rows.
- [ ] **Calibration:** Often fitted and evaluated on the same data -- verify a reliability diagram from test, calibration fit on val.
- [ ] **Early detection:** Often features use full cascade -- verify the `features(events, t0, horizon)` property test and a horizon curve.
- [ ] **Cascade view:** Often has edges the platform never provided -- verify every edge has `kind` and `inferred` flag, and no child precedes its parent.
- [ ] **Ingest:** Often missing cursor persistence, backoff, and delete handling -- verify by killing the worker mid-stream and restarting, and by deleting a test post.
- [ ] **Simulator:** Often unvalidated -- verify a real-vs-simulated comparison figure and the `synthetic: true` flag end to end.
- [ ] **Honesty:** Often a leftover "detects" string -- verify the CI grep over README and frontend copy.
- [ ] **Demo:** Often works only warm -- verify clean clone -> `docker compose up` -> data visible, and the live URL after 30+ minutes idle.
- [ ] **Hosting:** Often a free DB that expires -- verify provider expiry terms and the rebuild script.
- [ ] **README numbers:** Often hand-typed -- verify they are generated from `reports/metrics.json`.
- [ ] **Repo hygiene:** Often weights/data/notebook outputs committed -- verify `git ls-files` for `*.pkl|*.pt|*.csv|*.jsonl` and run a secret scan.
- [ ] **Ethics section:** Often generic -- verify it names bias findings from the slice table, data retention, and the no-redistribution decision.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Source leakage discovered late | MEDIUM | Re-split by source/time, strip metadata, retrain, regenerate all figures; keep the leaky run in the README as a documented lesson |
| Test set contaminated by tuning | MEDIUM | Obtain a fresh holdout (time-later data or a new dataset split); never reuse; note in model card |
| Temporal leakage in features | MEDIUM-HIGH | Rewrite feature function with horizon filter and property test; rerun all cascade results |
| Fabricated or impossible cascades shown | LOW-MEDIUM | Add DB constraints and ingest assertions; purge bad rows; add `synthetic`/`inferred` flags |
| Posted raw data or secret to the repo | HIGH | Remove file; rotate credentials; history rewrite only with explicit owner approval (PROJECT.md policy); add pre-commit scan |
| Hosting DB expired / demo dead | MEDIUM | Re-run bootstrap script plus replay snapshot; switch provider; keep GIF/video in README as fallback |
| Overclaiming wording shipped | LOW | Global copy edit, CI grep, update model card |
| Simulator found invalid | LOW-MEDIUM | Relabel "illustrative", remove from analysis claims, or cut |
| Platform blocks/rate-limits ingest | LOW-MEDIUM | Back off, persist cursor, switch to stream, reduce scope; use recorded replay while recovering |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1 Source/outlet leakage | P3 (dataset decision), P4 | Canary suite results + top-features table in model card |
| 2 Contamination / tuning on test | P4 | CI asserts split non-overlap; split hash in metrics.json |
| 3 Domain mismatch | P4, P5 | OOD probe set row in results; abstain state rendered |
| 4 Metrics / prevalence | P4 (P7 for ranking) | Results table has macro-F1, PR-AUC, CIs, precision at assumed prevalence, baselines |
| 5 Calibration | P4, P5 | Reliability diagram committed; test-set Brier/ECE reported |
| 6 Overclaiming | P1, P4, P5, P6 | CI copy grep passes; limitations above the fold |
| 7 Cascade structure / ordering | P3, P5 | DB/ingest invariants; UI caption; zero child-before-parent violations |
| 8 Temporal leakage | P7 (contract in P3) | Horizon property test; horizon curve; volume-only baseline |
| 9 No labels / legacy datasets | P3 spike, P7 | Dataset audit doc; retrievable-fraction reported |
| 10 Unvalidated simulator | P8 (P1/P2 patterns) | Real-vs-sim comparison figure; seeded invariant tests; banner e2e test |
| 11 ToS / rate limits / redistribution / deletions | P3, P6, P9 | Terms note in `docs/`; delete-event test; no raw data in `git ls-files` |
| 12 Entity / political bias | P4, P5, P9 | Slice table, name-swap test, pseudonymized UI |
| 13 Silent fallbacks / stale-as-live | P1, P2, P3, P5 | Failure-path tests (502/503); freshness indicator; `DEMO_MODE` default false test |
| 14 Portfolio traps (dead demo, no numbers) | P2, P4, P6, P9 | Clean-clone acceptance; generated README table; weekly health check |
| 15 Weights/data/notebook hygiene | P1, P2, P4, P6 | `.gitignore`, repo size check, split requirements, image size |
| 16 Label semantics/noise | P4 | Model card label mapping |
| 17 Pretraining contamination | P4 (v2 models) | Table footnote + post-cutoff probe set |
| 18 News-to-post linking | P3 | `anchor` field and link-method breakdown |
| 19 Ingest volume/storage | P3, P6 | Row-count monitor, retention job |
| 20 GNews quota | P2, P3 | Cache + quota budget in config |
| 21 Bots / NSFW content | P3, P5 | Label-filter test; reviewed demo GIF |
| 22 Unsafe rendering | P2, P5 | Pydantic length caps; no `dangerouslySetInnerHTML` lint rule |
| 23 Graph scale | P5 | Worst-case fixture renders under target time |
| 24 Flaky model-output tests | P2, P4 | CI uses fixtures; eval separate |
| 25 Straw-man baseline | P2, P4 | Both baseline-0 variants in table |

## Sources

- Bluesky rate limits (HIGH, fetched this session): https://bsky.network/docs/rate-limits/ (3000/5 min per IP; createSession 30/5 min and 300/day per account; public.api.bsky.app cached for public web use)
- Bluesky ToS, updated 14 Aug 2025 (HIGH, must be read in full during P3 spike): https://bsky.social/about/support/tos
- atproto post structure, replies and quotes use strong references, `createdAt` is a required client-supplied field (HIGH): https://atproto.com/blog/create-post and https://bsky.network/docs/bluesky-api/creating-a-post/
- Mastodon rate limits, 300 per 5 min per account and per IP (HIGH): https://docs.joinmastodon.org/api/rate-limits/
- Mastodon timelines, public timeline requires app token if instance disabled public preview (HIGH): https://docs.joinmastodon.org/methods/timelines/
- Bluesky dataset ethics and release practice: https://arxiv.org/html/2404.18984v1 ; Zenodo record https://zenodo.org/records/14258401 ; 404 Media report on the 1M-post dataset: https://www.404media.co/someone-made-a-dataset-of-one-million-bluesky-posts-for-machine-learning-research/ (MEDIUM-HIGH)
- FakeNewsNet repository note on non-distribution due to Twitter privacy policy and publisher copyright; deleted tweets and temporal drift limit reproducibility (HIGH for the non-distribution statement): https://github.com/KaiDMML/FakeNewsNet ; overview of limitations: https://www.emergentmind.com/topics/fakenewsnet-dataset (MEDIUM)
- Source-confound evidence for ISOT, "Diagnosing Source Confounds in Fake-News Benchmarks" (MEDIUM, preprint): https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6904799 ; ISOT collection description (Reuters for real): https://www.kaggle.com/datasets/emineyetm/fake-news-detection-datasets ; example of near-100% reported accuracy: https://rsisinternational.org/journals/ijrsi/view/a-comparison-of-machine-learning-classifiers-for-fake-news-identification-using-the-isot-dataset-xgboost-and-random-forest-achieve-100-accuracy
- Leave-one-event-out as the standard rumour evaluation on PHEME (MEDIUM): https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0320333
- Render free-tier behaviour (HIGH, fetched this session): https://render.com/docs/free
- Prototype defects: `/home/user/TruthTrail/.planning/codebase/CONCERNS.md`; project constraints: `/home/user/TruthTrail/.planning/PROJECT.md`
- Training knowledge, not independently re-verified this session (MEDIUM/LOW): prevalence/precision arithmetic, calibration practice (Platt/isotonic/temperature), early-detection protocol, WELFake duplicate issue, Twitter15/16 and PHEME download contents and licenses, GNews free-tier limits, expected ceiling of text-only LIAR-type results. Treat as items to confirm in the relevant phase's research.

---
*Pitfalls research for: misinformation early-warning system (news + social propagation, classifier, cascade features, simulator, portfolio deployment)*
*Researched: 2026-10-11*
