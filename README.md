# TruthTrail

**Status: prototype under reconstruction.**

TruthTrail is being rebuilt into a misinformation early-warning tool. Its output is a flag for human review: it helps a reviewer decide what to look at first, and it never decides whether a claim is true. Nothing here is a verdict.

## What works today

`GET /analyze?query=...` fetches recent headlines from the GNews API and labels each with a keyword baseline:

- `risk` is `High`, `Medium` or `Low`, and every result carries `risk_method: keyword_baseline`.
- The baseline is substring keyword rules, not a trained model. It has known false positives, pinned by tests (for example "secure" matches "cure").
- Live results contain the headline, source, publication time and risk label. They contain no spread data at all.

## Honesty guarantees (Phase 1)

- Every response carries provenance: `synthetic`, `data_as_of` and `source_status` (under `meta` on success, at the top level on errors).
- If the news provider fails, the API answers 502 or 503 as `application/problem+json`. It never returns invented results. A query with no matches is an honest 200 with an empty `results` list.
- Demo data is served only when `DEMO_MODE=true`, from a committed fixture, and is labelled `synthetic: true`.

### What `data_as_of` means

- Live: the UTC instant this server received the provider response. It is not the article publication time (each result has its own `published_at`), and free-plan GNews articles can lag by about 12 hours.
- Demo: a fixed fixture generation instant, never "now", so demo data cannot pass for live data.

## Configuration

Copy `.env.example` to `.env` and fill in values. Never commit `.env`. Variables:

| Name | Purpose |
|---|---|
| `GNEWS_API_KEY` | News provider key. Required unless `DEMO_MODE=true`; the service refuses to start without it. |
| `DEMO_MODE` | `true` serves the synthetic fixture and needs no key. Default `false`. |
| `BLUESKY_HANDLE` | Optional until Phase 3. |
| `BLUESKY_APP_PASSWORD` | Optional until Phase 3. |
| `DATABASE_URL` | Optional until Phase 3. |

## Run and check

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
DEMO_MODE=true .venv/bin/uvicorn main:app      # demo data, no key needed
.venv/bin/python -m pytest -q                  # tests
.venv/bin/python scripts/copy_guard.py         # copy guard: README, docs and API strings
```

The secret scan uses a pinned, checksum-verified gitleaks binary:

```bash
bash scripts/install_gitleaks.sh "${TMPDIR:-/tmp}/truthtrail-gitleaks"
bash scripts/gitleaks_scan.sh "${TMPDIR:-/tmp}/truthtrail-gitleaks/gitleaks" <base> HEAD <floor>
bash scripts/gitleaks_selftest.sh "${TMPDIR:-/tmp}/truthtrail-gitleaks/gitleaks"
```

CI runs the copy guard, the secret scan and the tests on every push and pull request.

## Not here yet

- Real propagation data (Phase 3).
- A trained and evaluated classifier (Phase 4).
- The dashboard (Phase 5).

The old simulated spread now only generates the labelled demo fixture.
