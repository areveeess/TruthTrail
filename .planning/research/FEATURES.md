# Feature Research

**Domain:** Misinformation early-warning / claim-triage / cascade-analysis tools (research demos and fact-checker tooling), built as a hiring-reviewer-facing portfolio project
**Researched:** 2026-10-11
**Confidence:** MEDIUM-HIGH (feature landscape of Hoaxy / CoVaxxy / Full Fact / Fact Check Tools is well sourced; current live status of Botometer, ClaimBuster API and Meedan clustering internals is MEDIUM; Bluesky repost-edge semantics need a spike)

## How the reference tools actually work (what "expected behaviour" means)

| Tool | What it does | Features worth learning from | Status / caveat |
|------|--------------|------------------------------|-----------------|
| Hoaxy (OSoMe, Indiana Univ.) | Search a claim, see how claim articles and fact-check articles spread on Twitter | (1) Timeline of cumulative post counts, claims vs fact-checks on one axis; (2) interactive diffusion network, nodes = accounts, edges = retweet/reply/mention/quote with direction; (3) click edge to see the post and linked story, click node to see what that account shared; (4) node colour = Botometer score | Twitter only, public posts only; tool is explicitly "observe, not adjudicate". Built on a curated list of low-credibility and fact-check source domains, tracked by shared URL |
| CoVaxxy dashboard (OSoMe + PoliMi) | Public dashboard linking vaccine-conversation data to uptake/hesitancy | State-level maps, correlation plots against survey/uptake data, weekly counts of low-credibility vs mainstream sources, hashtag/domain trends, downloadable plots and data | Source credibility comes from a public list (Iffy+) compiled from fact-checkers, not from a per-post model. Aggregate-level, no per-user labelling |
| Botometer / Botometer X | Per-account bot-likelihood score | Score + colour scale, used inside Hoaxy | Original service went offline when free Twitter/X research API access ended; Botometer X now serves archival pre-computed scores (pre-June 2023) only. Treat as cautionary tale (platform dependency, per-account labelling) not as a feature to copy |
| Google Fact Check Explorer / Fact Check Tools API | Search existing fact-checks (ClaimReview markup) by text or image | `claims:search` with language filter, `maxAgeDays`, publisher filter, pagination; returns reviewed claim, publisher, rating, URL | Free with API key. It retrieves existing human verdicts; it does not generate them. This is the right way for a triage tool to surface "has this already been checked" |
| ClaimBuster | Scores sentences for check-worthiness | Score per sentence, trained on human-labelled debate-transcript claims; public API, datasets, demos | Scores "worth checking", explicitly not "true/false". This is the framing TruthTrail should copy |
| Full Fact AI | Internal tooling for professional fact-checkers | Claim detection (BERT-style claim-type classifier), topic filter, check-worthiness ranking, claim matching against previously checked claims (semantic similarity plus entity overlap), daily digest of top claims by topic, searchable archive of monitored media | Not publicly usable; value is the triage workflow: filter, rank, match to known, hand to human |
| Meedan Check | Fact-check workspace and WhatsApp tipline platform | Tip intake, text-similarity / claim matching to cluster duplicate submissions and surface existing fact-checks, assignment and status workflow for reporters | Workflow and accounts are the product; out of scope for a single-tenant demo. Clustering internals not publicly documented in what I found |
| Community Notes (ex-Birdwatch) | Crowd-written context notes, shown only if raters who normally disagree both rate them helpful | Open-source bridging-based ranking (matrix factorisation of rater x note ratings, polarity + helpfulness factors), public data and code | Needs a user community; a different problem from automated triage. Not buildable honestly in a portfolio demo |

**Cross-tool pattern (HIGH confidence):** every credible tool is (a) a search/ingest layer over a curated or public source, (b) a ranking/triage layer that says "look here first", (c) a visual of spread over time and across accounts, and (d) explicit that a human or an existing fact-check decides truth. None of them output a bare "FAKE" verdict.

**Research-side expectations for the classifier and early detection (MEDIUM-HIGH):** standard benchmarks are Twitter15/16 (four-class, ~1.5k and ~0.8k claims, with propagation trees), PHEME (per-event; evaluate leave-one-event-out because random splits across threads leak), FakeNewsNet (PolitiFact/GossipCop, news-centric; UPFD adds propagation graphs). Early detection is reported as macro-F1 at fixed checkpoints (elapsed time or post count), and text is the strongest signal at the very start while structure helps more as posts accumulate. Reviewers who know this literature will look for: macro-F1, split design, a text-only baseline, and checkpoint curves.

**A structural trap specific to this project (HIGH on the problem, MEDIUM on Bluesky specifics):** most platforms attribute every reshare to the original poster, so true "who reshared from whom" trees are not directly observable (DeVerna et al., 2024, shows reconstruction assumptions materially distort influence and cascade metrics). For Bluesky/Mastodon expect: replies carry a true parent, quote posts embed the quoted post (true edge), reposts/boosts point at the original (star-shaped, not a tree). The dashboard must label which edges are observed vs inferred, and cascade "depth" must be reported with that caveat. Confirm repost record semantics in the Phase 3 spike.

## Feature Landscape

Tags: **[v1]** = Lean MVP (4-6 weeks part-time), **[v1.x]** = add if v1 finishes early, **[v2]** = Showcase milestone, **[defer]** = not planned. Complexity: LOW (< 1 day), MEDIUM (1-4 days), HIGH (> 4 days or research risk).

### Table Stakes (Reviewers and users expect these)

Missing any of these makes the project read as a hackathon demo, which is the exact thing being fixed.

| Feature | Why Expected | Complexity | Tag | Notes |
|---------|--------------|------------|-----|-------|
| Honest failure modes: upstream error -> 502/503, never a fabricated 200; `DEMO_MODE` data flagged `synthetic: true` in API and UI | First thing a reviewer probes; the prototype's worst defect | LOW | v1 | Also: request timeouts, no secrets in repo, env-only config |
| Typed request/response models (Pydantic), input validation, `/health` | Baseline engineering credibility | LOW | v1 | OpenAPI docs come free from FastAPI; link them in README |
| Multi-result news/claim search with provenance (title, source domain, URL, published time) | Every tool shows what it analysed and links to it; prototype returns one headline | LOW | v1 | GNews returns multiple articles; cache per query (rate limits) |
| Real propagation ingest from one open source (Bluesky or Mastodon) persisted in Postgres | Core value: "no fabricated data on the live path". Hoaxy's whole premise is real observed diffusion | HIGH | v1 | Spike first (terms, rate limits, edge semantics). Link news to posts by shared URL (Hoaxy approach) or keyword search; store raw ids + edge type |
| Cascade graph view with edge-type legend and observed-vs-inferred labelling | Hoaxy's headline feature; reviewers expect a graph | MEDIUM | v1 | Force-directed or tree layout; click node/edge for the underlying post link. Keep to a few hundred nodes, cap and say so |
| Timeline of cumulative posts (and per-interval rate) | Hoaxy's second headline visual; cheap and legible | LOW | v1 | Recharts already in `package.json` |
| Basic cascade stats: size, unique accounts, duration, max depth, max breadth | Standard cascade descriptors in the literature | LOW | v1 | Report depth with the star-shape caveat |
| Text classifier producing a score plus confidence, framed as "flag for human review" | The project's reason to exist; ClaimBuster/Full Fact both output a ranking score, not a verdict | MEDIUM | v1 | Start TF-IDF + logistic regression (fast, explainable, no GPU); transformer fine-tune is v2 |
| Reproducible evaluation: macro-F1, PR-AUC, calibration (reliability curve, ECE/Brier), confusion matrix, one command to re-run | The single biggest credibility lever for ML reviewers | MEDIUM | v1 | Fixed seeds, committed metrics JSON + model card; source-disjoint or event-disjoint split (random splits leak) |
| Baseline-0 comparison: old keyword rules vs the trained model on the same test set | Shows measured improvement; turns the prototype's shame into a result | LOW | v1 | Plus a majority-class and a simple-lexicon baseline so the numbers are interpretable |
| Risk badge with confidence, an "uncertain / needs review" band, and plain-language caveat | Prevents false precision; ClaimBuster-style "worth checking" wording | LOW | v1 | Never "True/False/Fake"; copy reviewed for this |
| Loading / error / empty states in the UI | Expected of any dashboard; the honest-errors story must reach the UI | LOW | v1 | Distinguish "no posts found" from "upstream failed" from "demo data" |
| Visible synthetic/demo banner anywhere simulated data appears | Core Value | LOW | v1 | Driven by the API `synthetic` flag, not hand-set in the UI |
| Tests, CI (lint, types, tests, dependency audit), Dockerfile, docker-compose from clean clone, pinned deps | Hiring-engineer checklist | MEDIUM | v1 | Characterization tests of the prototype first, then invariants (child timestamp >= parent timestamp) |
| Rate limiting, restricted CORS, response caching | Protects a public demo and the upstream quota | LOW | v1 | In-memory or Postgres-backed cache is enough |
| Deployed live demo with seeded, real, stored cascades so it works without live API keys on a cold start | Reviewers will not clone and run; a dead demo is worse than none | MEDIUM | v1 | Serve from the DB snapshot; live-refresh is optional |
| README: architecture diagram, demo GIF, results table, limitations and ethics section | The artifact reviewers actually read | MEDIUM | v1 | Limitations must include domain shift (trained on claims/headlines, applied to social posts) and the edge-inference caveat |

### Differentiators (Competitive Advantage)

Align with Core Value: measured, reproducible, nothing fabricated. Pick a few and do them well; do not chase breadth.

| Feature | Value Proposition | Complexity | Tag | Notes |
|---------|-------------------|------------|-----|-------|
| Per-prediction explanation (top contributing tokens/features) | Triage tools are only useful if a reviewer can see why something was flagged; near-free with a linear model | LOW-MEDIUM | v1 | Highlight terms in the headline; be careful that "style artifacts" (source, punctuation) are not read as evidence |
| Calibration shown in UI/README (reliability diagram, "when it says 0.8, it is right ~X%") | Rare in portfolio projects, impressive to ML reviewers, directly supports "score with confidence" | LOW | v1 | Isotonic or Platt on a held-out set; report ECE before/after |
| Out-of-domain check on a small hand-labelled sample of the ingested social posts | Honestly quantifies domain shift, which is the project's biggest validity risk | MEDIUM | v1.x | 100-200 posts, labelled by the owner with a written rubric; report agreement caveats. Skip if time is short, but keep the limitation in the README |
| Existing fact-check lookup via Google Fact Check Tools API (`claims:search`) shown next to the score | Mirrors how real triage works ("already checked?"); surfaces human verdicts instead of inventing one | LOW-MEDIUM | v1.x | Needs a free API key (env var); degrade gracefully when absent. Strong fit for "flag for human review" framing |
| Source-domain credibility signal from a public list (Iffy+ style) | CoVaxxy and Hoaxy both rely on source lists; cheap, interpretable feature and baseline | MEDIUM | v1.x | Verify the list's licence/terms; this is per-domain, not per-user. Also a leakage risk if the labels came from the same lists |
| Triage queue: items ranked by risk x spread velocity, with filters | The "early-warning" in the name; Full Fact's daily-digest pattern | MEDIUM | v1.x (simple sortable list in v1), v2 (composite priority score) | Do not invent a composite score until it can be evaluated |
| Cascade feature extraction (growth rate, early-window counts, structural virality, reply/quote ratio, account-age mix) | Foundation for early detection; hand-crafted + gradient boosting is a respected baseline before any GNN | MEDIUM | v2 | Depends on real stored cascades (v1) and enough labelled cascades; see risk below |
| Early-detection evaluation: macro-F1 at checkpoints (e.g. first 10/30/60 min or 5/20/50 posts), text-only vs text+structure | The standard way the literature reports "early"; shows rigour and a real finding even if the answer is "structure adds little" | HIGH | v2 | Needs labelled cascades with timestamps (Twitter15/16, PHEME are the public sets; Bluesky cascades are unlabelled). Report negative results honestly |
| Transformer fine-tune (offline, Colab/Kaggle) with metrics + model card, no weights committed | Moves macro-F1 up and shows modern ML skills | HIGH | v2 | Must beat the TF-IDF baseline on the same split or be reported as not beating it |
| What-if intervention simulator (e.g. "remove top-k amplifiers / add a label at time t") | Visually compelling; ties cascades to decisions | HIGH | v2 | Only credible if fitted to real cascades (branching/Hawkes/IC with estimated parameters), clearly labelled "model-based simulation, not a prediction", with sensitivity ranges. Unfitted parameters = fabrication |
| Claim clustering / near-duplicate grouping (embeddings) | Full Fact and Meedan's core triage move; collapses repeats so reviewers see distinct claims | MEDIUM-HIGH | v2 | Sentence-embedding + threshold, evaluate cluster purity on a small labelled set |
| Data export (CSV/JSON of a cascade) and public API docs | CoVaxxy offers downloads; reproducibility signal | LOW | v1.x | Include `synthetic` and provenance fields |
| API-key auth, usage quotas | Production polish | MEDIUM | v2 | |
| Monitoring/observability (structured logs, metrics endpoint) and load test numbers | "Production polish" talking point | MEDIUM | v2 | Only after the demo is stable |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Output "True / False / Fake / Real" verdicts or "detects the truth" copy | Simple, demo-friendly | A text classifier learns style and source artifacts, not truth; overclaiming is inaccurate and an ethics red flag; no reference tool does it | "Flag for human review" with calibrated score, confidence band, explanation, and link to existing fact-checks |
| Per-user blacklists, "bad actor" lists, or per-account bot/misinformation scores | Looks like actionable insight, Botometer precedent | Labels real individuals on weak evidence; Botometer's own scores became unavailable and contested; harassment and defamation risk; also out of scope (no moderation) | Aggregate views: cascade-level stats, top-amplifier counts shown as neutral facts, domain-level (not person-level) credibility |
| Unlabelled synthetic / simulated data presented as analysis (the prototype's `random.choice` spread) | Makes the demo look alive when ingest fails | Directly violates Core Value; ~40% of simulated events preceded their parent | Real stored cascades; `DEMO_MODE` + `synthetic: true` everywhere, banner in UI |
| Reporting accuracy from a random train/test split, or a single headline number | Easy and flattering | Leakage inflates results (PHEME-style threads, same-source articles); accuracy hides class imbalance | Macro-F1 + PR-AUC + calibration on source- or event-disjoint splits, baselines alongside, confidence intervals if feasible |
| Graph neural network / transformer-on-everything for its own sake | Resume keywords | No GPU, small labelled cascade sets, hard to beat tuned text + hand-crafted features; adds risk to v1 | TF-IDF + LR in v1; GBM on cascade features and an offline fine-tune in v2, each compared to the simpler baseline |
| LLM-as-judge verdicts on claim truth | Impressive in demos | Hallucinated "facts", non-reproducible, cost, and it is truth adjudication by another name | Optional later: LLM for summarising or explaining the cascade, never for scoring truth |
| Paid X/Twitter ingestion or scraping | It is where the research data lives | Cost, terms violations, fragile (Botometer's fate) | Bluesky/Mastodon live data; public research datasets (Twitter15/16, PHEME, FakeNewsNet) for labelled evaluation |
| Presenting repost fan-out as a true reshare tree | Makes prettier, deeper graphs | Platform data attributes reshares to the original; inferred depth is an assumption that distorts metrics | Show edge types, mark inferred edges, report depth with caveat; compute metrics robust to this (size, rate, unique accounts) |
| Real-time everything (websocket live graph, streaming inference) | "Early warning" sounds real-time | Operational complexity, quota burn, harder to test, no evaluation benefit | Scheduled/batched ingest into Postgres plus on-demand refresh; near-real-time labelled "minutes-level" |
| User accounts, roles, review/assignment workflows (Meedan Check clone) | Looks like a product | Large scope, no hiring-signal gain over the analysis itself | Single-tenant demo; API key in v2 |
| Content-moderation actions (takedown, ban, appeal) | Seems like the logical end of "early warning" | Out of remit, ethics and liability | Prioritisation for human review only |
| Crowd-notes / bridging-rating system (Community Notes clone) | Famous, interesting | Requires a real rater community; a simulated one would be fabricated data | Cite it in README as related work |
| Multilingual support in v1 | Misinformation is global | Datasets, labels and evaluation all English; quality claims would be unsupported | Document as a limitation; v2+ extension |
| Committing model weights or raw scraped user data | Convenience | Repo bloat, licensing, privacy | Commit metrics, model card, training script, and a small licensed sample |
| Hardcoded named public figures as high-risk (prototype behaviour) | Quick demo win | Targets specific people; unjustifiable bias | Remove; model features must be general and explainable |

## Feature Dependencies

```
[Honest errors + DEMO_MODE/synthetic flag]
    └──required by──> [Every UI state: banner, empty/error states]
    └──required by──> [Deployed demo credibility]

[Package layout + typed models + tests/CI]
    └──required by──> [Everything below; characterization tests protect refactor]

[Source spike: terms, rate limits, edge semantics]
    └──required by──> [Real propagation ingest]
                          └──required by──> [Postgres cascade store]
                                                └──required by──> [Cascade graph + timeline + basic stats]
                                                └──required by──> [Seeded snapshot for deployed demo]
                                                └──required by──> [Cascade features (v2)]
                                                                      └──required by──> [Early-detection eval (v2)]
                                                                      └──required by──> [What-if simulator (v2): fit params to real cascades]

[Labelled text dataset (LIAR / FakeNewsNet / PHEME text)]
    └──required by──> [Train + evaluate classifier (score + confidence)]
                          └──required by──> [Calibration] ──required by──> [Risk badge w/ confidence band]
                          └──required by──> [Baseline-0 comparison table]
                          └──enhances──> [Explanations]
                          └──required by──> [Transformer fine-tune (v2)]

[Multi-result news search w/ provenance] ──enhances──> [Link article URL to social posts (cascade seed)]
[Fact Check Tools lookup] ──enhances──> [Risk badge / triage view]   (independent of classifier)
[Triage queue] ──requires──> [classifier score] + [cascade stats]
[Claim clustering (v2)] ──enhances──> [Triage queue]

[Labelled cascades (Twitter15/16, PHEME)] ──required by──> [Early-detection eval]
[Bluesky cascades are unlabelled] ──conflicts──> [claiming cascade-model accuracy on live Bluesky data]
[Unfitted simulator parameters] ──conflicts──> [Core Value: no fabricated analysis]
[Classifier trained on headlines] ──domain shift──> [Scoring social posts]  (document; optional hand-labelled check)
```

### Dependency Notes

- **Cascade store requires the source spike:** edge semantics (repost = star to original, quote and reply = true edges) decide the schema (`edge_type`, `inferred` flag) and what "depth" means. Decide this before the DB migration.
- **Classifier and propagation ingest are independent tracks:** the classifier can train on public labelled text while ingest is still being spiked. Parallelise them in the roadmap; the dashboard is where they meet.
- **Risk score applies to headlines/claims, cascades are about posts:** the join is via shared URL or query. Be explicit in the UI that the score is for the article/claim text, and cascade stats are descriptive, until v2 adds a cascade-based signal.
- **Early detection and the simulator need labelled or fitted cascades:** live Bluesky data has no truth labels. Do v2 early-detection on the public labelled datasets (Twitter15/16, PHEME) and use live Bluesky only for the descriptive dashboard and simulator parameter fitting; say so.
- **Calibration requires a held-out set separate from training and the final test set:** plan three splits.
- **Fact-check lookup is independent of the classifier:** it can ship at any time and adds value even if the classifier underperforms.

## MVP Definition

### Launch With (v1, Lean MVP)

- [ ] Honest error handling + `DEMO_MODE` / `synthetic` flag end to end (API and UI)
- [ ] Typed API, validation, `/health`, caching, rate limiting, restricted CORS, no secrets
- [ ] Package layout, pinned deps, tests, CI, Docker/docker-compose
- [ ] Multi-result news search with provenance
- [ ] One open propagation source ingested into Postgres, edge types preserved, inferred edges flagged
- [ ] Text classifier (TF-IDF + LR first) with calibrated score, confidence band, and per-prediction explanation
- [ ] Reproducible evaluation: macro-F1, PR-AUC, calibration, source/event-disjoint split, baseline-0 + trivial baselines, model card
- [ ] React + TS dashboard: cascade graph, timeline, basic cascade stats, risk badge + confidence, loading/error/empty states
- [ ] Deployed demo from a seeded snapshot; README with architecture, GIF, results table, limitations and ethics

### Add After Validation (v1.x)

- [ ] Google Fact Check Tools lookup next to the score (trigger: v1 deployed, key available)
- [ ] Source-domain credibility signal from a public list (trigger: licence checked, leakage analysis done)
- [ ] Out-of-domain hand-labelled check on ingested posts (trigger: time remains, rubric written)
- [ ] CSV/JSON export of a cascade
- [ ] Simple sortable/filterable triage list

### Future Consideration (v2, Showcase)

- [ ] Cascade feature extraction + GBM; early-detection macro-F1 at checkpoints, text-only vs text+structure
- [ ] Offline transformer fine-tune, reported against the v1 baseline
- [ ] What-if intervention simulator fitted to real cascades, clearly labelled as a model
- [ ] Claim clustering, composite triage priority (only if evaluable)
- [ ] API-key auth, observability, load test

### Deferred / not planned

Truth verdicts, per-user scoring, moderation actions, accounts and review workflows, Community Notes clone, multilingual, mobile, paid X ingestion, committed weights.

## Feature Prioritization Matrix

| Feature | User/Reviewer Value | Implementation Cost | Priority |
|---------|---------------------|---------------------|----------|
| Honest errors + synthetic flag | HIGH | LOW | P1 |
| Tests + CI + Docker + typed API | HIGH | MEDIUM | P1 |
| Real propagation ingest + Postgres | HIGH | HIGH | P1 |
| Classifier with score + confidence | HIGH | MEDIUM | P1 |
| Reproducible evaluation + baseline-0 + model card | HIGH | MEDIUM | P1 |
| Cascade graph + timeline + stats | HIGH | MEDIUM | P1 |
| Risk badge, uncertain band, caveat copy | HIGH | LOW | P1 |
| Deployed demo + README (results, limitations) | HIGH | MEDIUM | P1 |
| Calibration plot | MEDIUM-HIGH | LOW | P1 |
| Explanations (top tokens) | MEDIUM | LOW-MEDIUM | P2 (lean P1 if linear model) |
| Fact Check Tools lookup | MEDIUM-HIGH | LOW-MEDIUM | P2 |
| Out-of-domain hand-labelled check | MEDIUM | MEDIUM | P2 |
| Source-domain credibility signal | MEDIUM | MEDIUM | P2 |
| Triage queue | MEDIUM | MEDIUM | P2 |
| Data export | LOW-MEDIUM | LOW | P2 |
| Cascade features + early-detection eval | HIGH | HIGH | P2 (v2) |
| Transformer fine-tune | MEDIUM | HIGH | P3 (v2) |
| What-if simulator | MEDIUM-HIGH (visual appeal) | HIGH | P3 (v2) |
| Claim clustering | MEDIUM | MEDIUM-HIGH | P3 (v2) |
| API-key auth, observability | LOW-MEDIUM | MEDIUM | P3 (v2) |

**Priority key:** P1 must have for launch; P2 add when possible; P3 future consideration.

## Competitor Feature Analysis

| Feature | Hoaxy | CoVaxxy | Full Fact AI / ClaimBuster | Fact Check Explorer | Our Approach |
|---------|-------|---------|----------------------------|---------------------|--------------|
| Claim search | By keyword over tracked low-credibility + fact-check sources | Fixed topic (vaccines) | Monitored media stream | Search existing fact-checks | News search (GNews) with provenance; optional Fact Check lookup (v1.x) |
| Spread timeline | Cumulative tweets, claims vs fact-checks | Weekly counts by source type | n/a | n/a | Cumulative + rate timeline per cascade |
| Cascade / diffusion graph | Yes, account network with directed edges | No | n/a | n/a | Yes, with edge-type legend and inferred-edge labelling |
| Risk / check-worthiness score | No (bot score per account) | No (source-list based) | Yes, check-worthiness ranking | No | Calibrated risk score + confidence band, "flag for review" |
| Source credibility | Curated domain lists | Iffy+ list | Not public | Publisher shown | Optional domain-list feature (v1.x), per-domain only |
| Per-account labelling | Botometer colour | No | No | No | Deliberately none |
| Evaluation transparency | Research paper | Dataset paper | Papers with benchmarks | n/a | Metrics table, model card, one-command repro; baseline-0 |
| Claim matching / clustering | No | No | Yes | Image/text search of reviewed claims | v2 |
| Early detection | No | No | Partly (triage) | No | v2, evaluated at checkpoints |
| Intervention what-if | No | No | No | No | v2, fitted and labelled as model |
| Humans decide truth | Explicit | Explicit | Explicit | Verdicts come from publishers | Explicit in UI copy and README |

## Sources

- Hoaxy visualisation and Botometer colouring: Shao et al., "Anatomy of an online misinformation network" (arXiv 1801.06122, https://arxiv.org/pdf/1801.06122); Hoaxy launch coverage (Indiana University, https://archive.news.indiana.edu/releases/iu/2016/12/iu-hoaxy.shtml) (MEDIUM; 2016-2018 vintage, current UI may differ)
- CoVaxxy dashboard and dataset: https://osome.iu.edu/research/blog/introducing-the-covaxxy-dashboard ; https://ojs.aaai.org/index.php/ICWSM/article/view/18122 (MEDIUM-HIGH; maintenance status unclear)
- Botometer X / loss of original service: https://osome.iu.edu/research/blog/introducing-botometer-x (MEDIUM; Feb 2024)
- Google Fact Check Tools API (`claims:search`): https://developers.google.com/fact-check/tools/api/reference/rest ; https://googleapis.github.io/google-api-python-client/docs/dyn/factchecktools_v1alpha1.claims.html (HIGH for endpoint existence and parameters; re-check current quota/terms before building)
- ClaimBuster: Hassan et al., KDD 2017 (https://ranger.uta.edu/~cli/pubs/2017/claimbuster-kdd17-hassan.pdf); claimbuster.org (MEDIUM; API details unverified)
- Full Fact AI: https://fullfact.org/ai/ ; https://fullfact.org/blog/2025/feb/how-ai-can-help-fact-checkers/ (MEDIUM-HIGH)
- Meedan Check / tiplines: https://arxiv.org/abs/2106.04726 ; https://meedan.com (MEDIUM; clustering internals unconfirmed)
- Community Notes bridging algorithm: https://asteriskmag.com/issues/08/the-making-of-community-notes ; https://arxiv.org/pdf/2510.09585v1 (MEDIUM; secondary sources)
- Datasets and early-detection protocol: "A Survey of Datasets for Information Diffusion Tasks" (https://arxiv.org/pdf/2407.05161); Twitter15/16/PHEME overview (https://ieee-dataport.org/node/14857); Zero-shot rumor detection with propagation structure (https://arxiv.org/pdf/2212.01117); PHEME event-leakage warning in https://arxiv.org/pdf/2112.00245 (MEDIUM; from search snippets, LIAR dataset details are from background knowledge, verify during the classifier phase)
- Cascade inference problem: DeVerna et al., arXiv 2410.21554 (https://arxiv.org/abs/2410.21554) (HIGH for the claim that platforms attribute reshares to the original poster; Bluesky repost-record semantics LOW-MEDIUM, confirm against AT Protocol docs in the Phase 3 spike)
- Bluesky cascade data precedent: same paper's Bluesky case study (4,710 cascades from firehose, first week); Bluesky MurkySky (arXiv 2501.10557, summary-level only, LOW)

---
*Feature research for: misinformation early-warning / claim-triage / cascade-analysis tools (portfolio-grade)*
*Researched: 2026-10-11*
