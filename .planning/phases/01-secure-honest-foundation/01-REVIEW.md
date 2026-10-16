---
phase: 01-secure-honest-foundation
reviewed: 2026-10-16T11:00:00Z
depth: standard
files_reviewed: 27
files_reviewed_list:
  - config.py
  - gnews_fetcher.py
  - main.py
  - models.py
  - problems.py
  - requirements.txt
  - requirements-dev.txt
  - pytest.ini
  - README.md
  - .gitignore
  - .env.example
  - scripts/copy_guard.py
  - scripts/generate_demo_fixture.py
  - scripts/gitleaks_scan.sh
  - scripts/gitleaks_selftest.sh
  - scripts/install_gitleaks.sh
  - .github/workflows/ci.yml
  - tests/conftest.py
  - tests/test_copy_guard.py
  - tests/test_demo_fixture.py
  - tests/test_no_hardcoded_credentials.py
  - tests/test_openapi_contract.py
  - tests/test_provenance_demo.py
  - tests/test_request_validation.py
  - tests/test_settings.py
  - tests/test_upstream_errors.py
  - fixtures/demo_analyze.json
findings:
  critical: 1
  warning: 6
  info: 6
  total: 13
status: issues_found
fix_pass:
  fixed: [CR-01, WR-01, WR-02, WR-03, WR-04, WR-05, WR-06, IN-01, IN-04, IN-06]
  deferred: [IN-02, IN-03, IN-05]
---

# Phase 1: Code Review Report

**Reviewed:** 2026-10-16
**Depth:** standard (diff 9b5b085..HEAD; scripts and the CI workflow were also executed)
**Files Reviewed:** 27
**Status:** issues_found

## Summary

The core of the phase holds up. The 183 tests pass (10 strict xfails). `copy_guard.py` and `generate_demo_fixture.py --check` are clean. The gitleaks selftest passes all six scenarios with a binary whose sha256 I re-derived and which matches the pin. A real range scan from the floor to HEAD is clean. The Actions SHAs `checkout v7.0.1` and `setup-python v7.0.0` match the upstream tags, and the old key literal no longer exists in the HEAD tree. The D-06/D-07/D-15/D-16/D-19 error mapping is implemented as decided. The key travels only in the `X-Api-Key` header, and exceptions are raised `from None`.

The defects are in the edges around these controls.
- **Secret-scan control (one Critical):** the CI concurrency setting can silently skip the scan of a push range, which defeats the stated purpose of D-09.
- **Key handling (WR-01, WR-02):** the key can still be forwarded on a redirect, and a malformed key is reported as a transient provider outage.
- **Honesty guard (WR-03, WR-04):** the copy guard misses the most obvious overclaim phrasing ("truth detection"), and the API description says "Ranks" although nothing is ranked.

No API key value was printed or used. No real GNews call was made. The redirect and bad-key experiments ran against two throwaway localhost servers with fake key strings.

## Critical Issues

### CR-01: `cancel-in-progress` can skip the secret scan of a pushed commit range, so a committed-then-deleted key passes CI (D-09 bypass)

**Fix status:** fixed in 480d334. Push runs now scan floor..sha (cumulative), so a cancelled earlier run cannot leave commits unscanned; PR handling unchanged. The 40-zero sentinel and the committed-then-deleted-key case are covered by new selftest scenarios (deleted-key-from-floor, zero-sentinel-clean, zero-sentinel-leak).

**File:** `.github/workflows/ci.yml:13-15` (with `:58-61`)
**Issue:** The workflow uses `concurrency: group: ci-${{ github.ref }}` with `cancel-in-progress: true`. For `push` events the gitleaks job scans only `github.event.before..github.sha` (lines 58-61). The failure scenario:
1. Push 1 adds commit A, which contains a key.
2. Within the run time of push 1 (minutes), push 2 adds commit B, which deletes the key.
3. The run for push 1 is cancelled. A cancelled run is not a failure.
4. The run for push 2 scans `A..B`, where `before` is A. A is never inside any scanned range.
5. The working-tree scan sees only B's clean tree.
6. The branch tip is green, and the key stays in remote history unscanned.

This is exactly the "a key that is committed and later deleted still fails the build" guarantee in D-09. The project pushes after every phase from an ephemeral container, so rapid successive pushes are the normal case. Pull-request runs are not affected, because they scan base..head each time.
**Fix:** Do not cancel the secret scan. Either disable cancellation for the whole workflow or scope it to the cheap jobs:
```yaml
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: false   # a cancelled gitleaks run leaves its push range permanently unscanned
```
Alternatively, give the gitleaks job no `concurrency` block at all (scoping the group to the other jobs is not possible at workflow level, so use `cancel-in-progress: ${{ github.event_name == 'pull_request' }}`). A second line of defence is to make push scans cumulative by always scanning from the floor (`BASE=$RANGE_FLOOR` on push, as the new-branch sentinel already does), so each run covers the whole post-floor history and no push range can be skipped.

## Warnings

### WR-01: `X-Api-Key` is forwarded on redirects, including to another host or to plain http (D-16 leak path)

**Fix status:** fixed in 2eb1f85. allow_redirects=False; a 3xx maps to 502 upstream_bad_response; test asserts exactly one outbound call.

**File:** `gnews_fetcher.py:95-100`
**Issue:** `requests.get` follows redirects by default. `requests` strips only the `Authorization` header when a redirect changes host. A custom `X-Api-Key` header is re-sent unchanged. I verified this against two localhost servers (127.0.0.1 and localhost on different ports). The first server answered 302, and the second received `X-Api-Key` with the full key value. A redirect to an `http://` URL would send the key in cleartext. Reaching this needs the provider (or something in front of it) to emit a redirect. That is unlikely, but D-16 states the key must never leave the intended request. No test covers it.
**Fix:**
```python
resp = requests.get(
    GNEWS_URL,
    params={"q": query, "lang": "en", "max": 1},
    headers={"X-Api-Key": api_key},
    timeout=TIMEOUT,
    allow_redirects=False,
)
```
A 3xx then falls into the existing `status != 200` branch and becomes a 502 `upstream_bad_response`. Add a test that registers a 302 and asserts a 502 and exactly one outbound call.

### WR-02: A malformed key is reported as a transient provider outage (503 `upstream_unreachable` with Retry-After), or as a bare 500

**Fix status:** fixed in 5835f54 (requires human verification of the policy choice: the key is rejected, not stripped). Keys with whitespace, line breaks or non-ASCII characters raise ConfigurationError at startup (and again in the fetcher); connection/SSL/proxy errors and timeouts stay 503 + Retry-After; other requests errors map to 502 upstream_bad_response.

**File:** `gnews_fetcher.py:91-115` and `config.py:35-41`
**Issue:** The blank-key check strips only for the emptiness test, and the unstripped value is stored and sent. I ran these cases through `fetch_news` against a localhost server:
- A key with a leading space or an embedded newline makes `requests` raise `InvalidHeader`. The blanket `except requests.exceptions.RequestException` turns it into 503 `upstream_unreachable` with `Retry-After: 30`. The operator is told to retry a provider that was never contacted, while the real problem is local misconfiguration (D-08 intends misconfiguration to surface as `not_configured`).
- A key containing a non-latin-1 character raises `UnicodeEncodeError` at send time. It is not a `RequestException`, so it falls through to the generic 500 `internal_error`, with a traceback in the server log.

The same blanket mapping also sends `ChunkedEncodingError`, `ContentDecodingError`, `TooManyRedirects` and `InvalidURL` to 503. D-07 says a bad upstream answer is a 502.
**Fix:** Normalise the key once in the settings validator, and reject anything that is not header-safe:
```python
@field_validator("gnews_api_key", mode="before")
@classmethod
def _normalise_key(cls, value):
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        if not value.isascii() or not value.isprintable():
            raise ValueError("GNEWS_API_KEY contains invalid characters")
    return value
```
In the fetcher, add `except (requests.exceptions.ConnectionError, requests.exceptions.SSLError)` for "unreachable" and a separate `except requests.exceptions.RequestException` that maps to 502 `upstream_bad_response`.

### WR-03: The copy guard misses the most obvious overclaim phrasings ("truth detection", "truth detector", "lie detector")

**Fix status:** fixed in 583903e. Added truth-claim-rev, lie-detector, fake-news-filter, misinformation-classifier, finds-fake-news and verdict-wording rules with tests (including the allow marker); README and OpenAPI still pass.

**File:** `scripts/copy_guard.py:39-60`
**Issue:** The `truth-claim` rule only matches the order "detect... truth". I ran `scan_text` on a set of phrases. These all returned no findings: "A truth detection tool.", "Our truth detector", "truth-detection engine", "lie detector for news", "finds fake news", "A fake news filter", "misinformation classifier". "truth detection" is the exact claim the project's honesty constraint forbids, so a README or OpenAPI description saying it ships green. `test_clean_samples_pass` pins only benign samples, so this gap is untested.
**Fix:** Add reversed and adjacent forms, with tests for each:
```python
("truth-claim-rev", re.compile(r"\btruth[\s-]+(detect\w*|verif\w*|check(er|ers|ing)?)\b", re.I)),
("lie-detector", re.compile(r"\blie[\s-]+detect\w*\b", re.I)),
("fake-news-filter", re.compile(r"\bfake[\s-]+news\s+(filter|finder|spotter|blocker)\w*\b", re.I)),
("misinfo-classifier", re.compile(r"\b(mis|dis)information\s+(classif\w*|identif\w*)\b", re.I)),
```
Also add an explicit rule for "verdict"-style wording ("true or false", "real or fake").

### WR-04: API description and README overstate what the endpoint does ("Ranks", "headlines", plural results)

**Fix status:** fixed in 42f3339. Copy now says the most recent matching headline, one article, nothing ranked (main.py CRLF preserved, README, adapter docstring); contract test fixes max=1 and the wording together.

**File:** `main.py:44-51` (also `README.md:8`, `gnews_fetcher.py:97`)
**Issue:** `APP_DESCRIPTION` says the service "Ranks recent news headlines with a keyword baseline so a human reviewer can decide what to look at first." Nothing is ranked or sorted. Each result is labelled independently, in provider order. Worse, `gnews_fetcher.py:97` hard-codes `"max": 1`, so the endpoint returns at most one article per query. A reviewer therefore never gets a prioritised list, only one label. The README opening says it "fetches recent headlines" in the plural. The copy guard cannot catch this because the wording is not on a banned list. This conflicts with the core value ("nothing fabricated is presented as analysis") and with D-13's intent.
**Fix:** Change the description to "Labels the most recent matching headline (the provider is asked for one article) with a keyword-baseline flag..." and the README to "fetches the most recent matching headline". Alternatively, raise `max` and sort by risk, which makes "Ranks" true. Either way, add a contract test that fixes `max` and the wording together.

### WR-05: `filterwarnings = error` combined with floating transitive dependencies makes CI fail randomly

**Fix status:** fixed in eca4967. Full transitive closure pinned in requirements.txt / requirements-dev.txt (starlette 1.8.0 etc.); a fresh venv from the pins is identical to .venv and passes the suite; D-18 note adjusted.

**File:** `pytest.ini:5-7`, `requirements.txt`, `requirements-dev.txt`
**Issue:** Only the top-level packages are pinned. Starlette, urllib3, anyio and others float. `pytest.ini` turns every warning into an error, with one hand-written ignore for the exact httpx/starlette message. Drift has already happened: D-18 is written against Starlette 1.7, and the venv resolved 1.8.0. Any new DeprecationWarning in a floating transitive dependency (urllib3, starlette, pydantic-settings internals) breaks the `tests` job with no change in this repo, and the same drift can break `copy-guard`, which imports the app. The failure is non-reproducible by design until the Phase 2 uv lockfile lands.
**Fix:** Pin the transitive set now (`pip freeze` into a `requirements.lock` used by CI), or make the filter targeted (`error::DeprecationWarning:main`, `error::DeprecationWarning:gnews_fetcher`, and so on) so third-party warnings do not fail the build.

### WR-06: The working-tree scan can silently scan zero files and still report clean (fail-open, against D-20)

**Fix status:** fixed in c5e932d. File list captured before use; failing ls-files, empty list or empty export exits 2. Selftest scenarios ls-files-failure and empty-working-tree fail against the old script.

**File:** `scripts/gitleaks_scan.sh:58-69`
**Issue:** The export loop reads from a process substitution, `done < <(git ls-files -z ...)`. `set -e` and `pipefail` do not see a failure of that inner command. If `git ls-files` fails or returns nothing, `count` stays 0, the export directory is empty, `gitleaks dir` finds nothing, and the script continues. The script prints "(0 git-visible files)" but does not fail. Today the earlier `git rev-parse` check makes this unlikely. A future change to that guard, or a CI checkout quirk (safe.directory, a sparse checkout), would turn the secret scan into a no-op while the job stays green. D-20 requires the scan to fail closed.
**Fix:**
```bash
if [ "$count" -eq 0 ]; then
  echo "gitleaks: working-tree export is empty; refusing to report clean" >&2
  exit 2
fi
```
Place it right after the loop. For stronger assurance, also compare `count` against `git ls-files | wc -l`.

## Info

### IN-01: Copy-guard allow-marker window is computed with mismatched line splitting

**Fix status:** fixed in f09d0e2. The allow-marker window is split on \n only; one test per exotic separator.

**File:** `scripts/copy_guard.py:94-102`
**Issue:** The line number comes from `text.count("\n")`, but the window is sliced from `text.splitlines()`. `splitlines` also splits on U+2028, U+0085, `\x0c`, `\x1c`-`\x1e` and lone `\r`. If any such character precedes the match, the slice is shifted and an allow marker that is too far away (two lines above) is accepted. I reproduced it: `"x\u2028y\n<marker>\nfiller\nIt detects the truth."` returns no finding, while the same text with plain `\n` correctly reports one. This is low impact (it needs a crafted file), but the guard is a control.
**Fix:** Use `lines = text.split("\n")` for the window so both computations use the same separator.

### IN-02: 500 responses have no CORS headers, and a broken demo fixture is not caught at startup

**Fix status:** deferred. Out of the requested scope for this fix pass; revisit when CORS is revisited in Phase 2.

**File:** `main.py:17-20, 38-41, 61-66`
**Issue:** The generic 500 handler runs in `ServerErrorMiddleware`, which sits outside `CORSMiddleware`. A browser frontend therefore sees an opaque network error instead of the problem+json body for every 500 (this is in tension with the "frontend never breaks" intent). Separately, `lifespan` validates only settings. With `DEMO_MODE=true` and a corrupt or hand-edited fixture, the service starts healthy and every request returns 500. D-08's fail-fast intent would extend naturally to calling `load_demo_fixture()` at startup when demo mode is on.
**Fix:** Call `load_demo_fixture()` in `lifespan` when `settings.demo_mode` is true. Consider an `Exception` middleware, or re-adding CORS headers in the 500 handler, when CORS is revisited in Phase 2.

### IN-03: `Retry-After: 0` is passed through to clients of a rate-limited provider

**Fix status:** deferred. Out of the requested scope for this fix pass (Retry-After: 0 passthrough).

**File:** `gnews_fetcher.py:75-80`
**Issue:** A provider `Retry-After: 0` (or `00`) yields `min(0, 3600) == 0`, which tells clients to retry immediately against an upstream that just throttled. The tests cover 7, 30, 99999 and an HTTP-date, but not 0.
**Fix:** `return max(1, min(int(value), MAX_RETRY_AFTER))`, with a test.

### IN-04: CI hygiene gaps

**Fix status:** fixed in 49ea955. persist-credentials: false on all checkouts, timeout-minutes: 10 on all jobs, selftest runs in the gitleaks job; unused direct pyyaml pin dropped (still installed transitively via responses).

**File:** `.github/workflows/ci.yml:21, 36, 66` (and `scripts/gitleaks_selftest.sh`)
**Issue:**
- `actions/checkout` is used without `persist-credentials: false`, so the token stays in `.git/config` while later steps run repo scripts. The permissions are read-only, which limits the impact.
- No job sets `timeout-minutes`.
- `gitleaks_selftest.sh` is the only proof of the range rules, but CI never runs it. A regression in `gitleaks_scan.sh` would only be noticed by hand.
- `pyyaml==6.0.3` in `requirements-dev.txt` has no consumer in `tests/` or `scripts/`. The summary says it was added for a workflow contract check that is not in the repo.

**Fix:** Add `persist-credentials: false` and `timeout-minutes: 10`. Add a step that runs the selftest after the install step in the gitleaks job. Drop `pyyaml`, or add the workflow-parse test that justified it.

### IN-05: Inconsistent line endings and loose typing in the models

**Fix status:** deferred. Out of the requested scope for this fix pass (.gitattributes / line endings, Literal[False]).

**File:** `models.py:1-13, 107`, repository root (no `.gitattributes`)
**Issue:**
- `main.py`, `models.py` and `gnews_fetcher.py` are CRLF, while `config.py` and `problems.py` are LF. There is no `.gitattributes`, so any contributor with `core.autocrlf` set will produce whole-file diffs and can break the "restore CRLF" fix (`fbaab50`) again.
- `models.py` has imports out of order and no blank lines around `Event`.
- `Problem.synthetic` is typed `bool` with a default of False, although the docstring says "Always false". It should be `Literal[False]` so a schema consumer sees the invariant.

**Fix:** Add a `.gitattributes` with `*.py text eol=lf` or an explicit per-file rule that records the intended CRLF files. Type `synthetic` as `Literal[False]`.

### IN-06: The query pattern blocks ASCII control characters only

**Fix status:** fixed in fc664e0. The query pattern also rejects \x7f-\x9f and U+2028/U+2029; tests added.

**File:** `main.py:23-25`
**Issue:** The comment says the pattern "blocks log injection". `^[^\x00-\x1f\x7f]+$` does not reject C1 controls (U+0080-U+009F, including U+0085 NEL) or U+2028/U+2029. The application itself logs no query text, so the exposure is limited to downstream log viewers and the provider `q` parameter.
**Fix:** Reject the Unicode control and separator categories as well, for example by validating with `str.isprintable()` in an `AfterValidator`, or extend the class to `\x00-\x1f\x7f-\x9f\u2028\u2029`.

---

_Reviewed: 2026-10-16_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
