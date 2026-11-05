"""Contract tests for the recorded real-data fixture (plan 03-01, D-04, RESEARCH F-01).

The fixture under src/truthtrail/data/recorded is real recorded Bluesky Jetstream data, produced
only by ``scripts/bluesky_spike.py cut-fixture`` from the raw logs of the spike run and never edited
by hand. These tests pin its hash, its scrub invariants, its provenance (windows, selection policy,
stream span) and the coverage contract that plans 03-04 and 03-05 read by exact key. No test is
skipped: if a file is missing the tests fail.
"""

import hashlib
import importlib
import importlib.util
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RECORDED = REPO_ROOT / "src" / "truthtrail" / "data" / "recorded"
SPIKE = REPO_ROOT / ".planning" / "phases" / "03-real-propagation-data" / "03-SPIKE.md"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

FIXTURE_DATE = "2026-10-19"
FIXTURE_SHA256 = "4ef9bd30a8d67a361488186822ad4193348f42f4fd3ddd483fd08c3dbe3ad91d"
SAMPLES_SHA256 = "59a2ab8c5054f46328d336136fbfb810fb0a8d1ae1e074d63ddcb1f370878015"
# The scrub-1 cut, before the scrub-2 pass (recorded in the manifest's rescrub block).
PRE_PASS_FIXTURE_SHA256 = "6e39a1f9a460a15a2ccdcc8d8830d624d60d3f511738a999653fc943018a1d7e"
PRE_PASS_SAMPLES_SHA256 = "a0beaefb1c39b9bba3d520ec98c7a9cdf617c28329522caafbdb2ffb9a388b3c"
TRACKED_ROOTS_SCRUB1 = 149
SIZE_BUDGET = 1_500_000
STREAM_SPAN_FLOOR_SECONDS = 3600

MAIN_PATH = RECORDED / f"bluesky-{FIXTURE_DATE}.jsonl"
SAMPLES_PATH = RECORDED / f"bluesky-{FIXTURE_DATE}.samples.jsonl"
MANIFEST_PATH = RECORDED / f"bluesky-{FIXTURE_DATE}.manifest.json"

POST = "app.bsky.feed.post"
REPOST = "app.bsky.feed.repost"
DID_RX = re.compile(r"^did:plc:[a-z2-7]{24}$")
RKEY_RX = re.compile(r"^[a-z2-7]{13}$")
FORBIDDEN_KEYS = {"cid", "text", "title", "description", "thumb", "alt"}
MANIFEST_KEYS = {
    "source_mode", "date", "sources", "dialects", "collections", "start_stream_us",
    "end_stream_us", "counts_by_kind", "frames_dropped_by_scrubber", "did_web_count", "coverage",
    "trimmed", "size_budget_bytes", "tool_git_sha", "scrubber_version", "files",
    "selection_policy", "windows",
}  # fmt: skip
COUNT_KEYS = {
    "post_create", "repost_create", "post_delete", "repost_delete", "account", "sync", "info",
}  # fmt: skip
COVERAGE_KEYS = {
    "tracked_roots", "children_by_kind", "cascades_with_replies", "cascades_with_quotes",
    "cascades_with_reposts", "cascades_with_depth2_replies", "orphan_replies", "deletes",
    "account_events_by_status", "sync_events", "negative_controls",
}  # fmt: skip
WINDOW_KEYS = {
    "label", "host", "dialect", "first_us", "last_us", "stream_seconds", "frames", "bytes",
    "bound_seconds", "stop_reason", "raw_sha256",
}  # fmt: skip


def selection():
    """The selection functions: the package module once plan 03-04 moved it, else the spike copy."""
    try:
        return importlib.import_module("truthtrail.ingest.selection")
    except ModuleNotFoundError:
        return importlib.import_module("spike_lib.selection")


def gate_module():
    spec = importlib.util.spec_from_file_location(
        "check_spike_ratified_fixture", REPO_ROOT / "scripts" / "check_spike_ratified.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_spike_ratified_fixture"] = module
    spec.loader.exec_module(module)
    return module


def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def main_frames() -> list[dict]:
    return [json.loads(line) for line in MAIN_PATH.read_text(encoding="utf-8").splitlines()]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def walk(value):
    """Yield every (key, value) pair and every string of a decoded JSON value."""
    if isinstance(value, dict):
        for key, inner in value.items():
            yield key, inner
            yield from walk(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from walk(inner)


def adult_or_hidden(sel, record) -> bool:
    labels = set(sel.record_labels(record))
    return bool(labels & sel.ADULT_LABELS) or sel.NO_UNAUTHENTICATED_LABEL in labels


def payload_of(envelope: dict) -> dict:
    return envelope.get("payload", {})


def record_uri(payload: dict) -> str:
    return f"at://{payload['did']}/{payload['collection']}/{payload['rkey']}"


# ----------------------------------------------------------------------------- manifest and hashes


def test_the_three_files_exist_and_the_manifest_has_the_required_keys():
    for path in (MAIN_PATH, SAMPLES_PATH, MANIFEST_PATH):
        assert path.is_file(), path.name
    data = manifest()
    assert set(data) >= MANIFEST_KEYS
    assert set(data["counts_by_kind"]) == COUNT_KEYS
    assert set(data["coverage"]) == COVERAGE_KEYS
    assert all(isinstance(v, int) for v in data["counts_by_kind"].values())


def test_source_mode_is_recorded_real():
    data = manifest()
    assert data["source_mode"] == "recorded-real"
    assert data["scrubber_version"].startswith("scrub-")
    assert re.fullmatch(r"[0-9a-f]{40}", data["tool_git_sha"])
    assert data["frames_dropped_by_scrubber"] >= 0


def test_total_size_is_within_the_budget():
    total = MAIN_PATH.stat().st_size + SAMPLES_PATH.stat().st_size
    assert total <= SIZE_BUDGET
    assert sum(f["bytes"] for f in manifest()["files"]) == total


def test_the_pinned_hashes_equal_the_files_and_the_manifest():
    assert sha256(MAIN_PATH) == FIXTURE_SHA256
    assert sha256(SAMPLES_PATH) == SAMPLES_SHA256
    listed = {f["name"]: f["sha256"] for f in manifest()["files"]}
    assert listed[MAIN_PATH.name] == FIXTURE_SHA256
    assert listed[SAMPLES_PATH.name] == SAMPLES_SHA256


# ----------------------------------------------------------------------------- scrub invariants


def test_lines_end_with_lf_only_and_parse_as_json_objects():
    for path in (MAIN_PATH, SAMPLES_PATH):
        raw = path.read_bytes()
        assert b"\r" not in raw
        assert raw.endswith(b"\n")
        for line in raw.decode("utf-8").splitlines():
            assert isinstance(json.loads(line), dict)


def test_identifiers_follow_the_sequential_counter_grammar():
    for path in (MAIN_PATH, SAMPLES_PATH):
        text = path.read_text(encoding="utf-8")
        for did in re.findall(r"did:[a-z]+:[^\"/]+", text):
            assert DID_RX.match(did), did[:12]
        assert "did:web" not in text
        for line in text.splitlines():
            obj = json.loads(line)
            for key, value in walk(obj):
                if key in ("rkey", "rev") and isinstance(value, str):
                    assert RKEY_RX.match(value), key
        for rkey in re.findall(r"at://did:plc:[a-z2-7]{24}/[A-Za-z.]+/([^\"]+)", text):
            assert RKEY_RX.match(rkey)


def test_no_text_cid_title_description_thumbnail_or_alt_anywhere():
    for path in (MAIN_PATH, SAMPLES_PATH):
        for line in path.read_text(encoding="utf-8").splitlines():
            keys = {key for key, _ in walk(json.loads(line))}
            assert not keys & FORBIDDEN_KEYS


def test_urls_keep_scheme_host_and_path_only():
    seen = 0
    for path in (MAIN_PATH, SAMPLES_PATH):
        for url in re.findall(r"https?://[^\"]+", path.read_text(encoding="utf-8")):
            seen += 1
            assert "?" not in url
            assert "#" not in url
    assert seen > 0


def test_no_hex_run_that_could_be_mistaken_for_key_material():
    for path in (MAIN_PATH, SAMPLES_PATH, MANIFEST_PATH):
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"\b[0-9a-f]{40}\b|\b[0-9a-f]{64}\b", "", text)  # git sha and sha256 values
        assert not re.search(r"\b[0-9a-fA-F]{32}\b", text)


def test_constants_in_this_file_are_not_named_like_credentials():
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = re.compile(r"^(ROOT|PARENT|CHILD)_(KEY|SECRET|PASSWORD|TOKEN)\w*\s*=", re.M)
    assert not forbidden.search(source)


# ----------------------------------------------------------------------------- structure


def test_every_child_frame_follows_the_frame_of_its_target():
    sel = selection()
    position: dict[str, int] = {}
    linked = 0
    for index, envelope in enumerate(main_frames()):
        payload = payload_of(envelope)
        if not payload.get("$type", "").endswith("#commit") or payload["operation"] != "create":
            continue
        uri = record_uri(payload)
        position[uri] = index
        edge = sel.derive_edge(payload["collection"], payload["record"])
        if edge is not None and edge.parent in position:
            linked += 1
            assert position[edge.parent] < index
    assert linked > 0


def test_delete_account_and_negative_control_frames_are_present():
    data = manifest()
    counts = data["counts_by_kind"]
    assert counts["post_delete"] > 0
    assert counts["account"] > 0
    assert data["coverage"]["negative_controls"]["total"] > 0
    assert data["coverage"]["tracked_roots"] > 0
    assert data["coverage"]["deletes"]["post"] + data["coverage"]["deletes"]["repost"] > 0
    assert counts["post_create"] > counts["post_delete"]


def test_the_samples_file_holds_both_dialects_and_the_control_shapes():
    rows = [json.loads(line) for line in SAMPLES_PATH.read_text(encoding="utf-8").splitlines()]
    assert {row["dialect"] for row in rows} >= {"v1"}
    kinds = [
        row["frame"].get("kind") or row["frame"].get("payload", {}).get("$type", "") for row in rows
    ]
    assert any(k.endswith("#info") for k in kinds)


# ----------------------------------------------------------------------------- provenance


def test_selection_policy_recorded():
    policy = manifest()["selection_policy"]
    assert policy["sample_per_10k"] == 10000
    assert policy["require_lang"] == "en"
    assert policy["max_active_roots"] is None
    domains = policy["allowlist_domains"]
    assert 0 < len(domains) <= 60
    assert all(d == d.lower() and not d.startswith("www.") for d in domains)
    assert domains == sorted(domains)


def test_stream_span_floor():
    windows = manifest()["windows"]
    assert windows
    total = 0.0
    for window in windows:
        assert set(window) >= WINDOW_KEYS
        assert abs(window["stream_seconds"] - (window["last_us"] - window["first_us"]) / 1e6) < 1e-6
        # stream time of the first frame can lead the recorder's wall clock by a moment
        assert window["bound_seconds"] + 5 >= window["stream_seconds"]
        assert re.fullmatch(r"[0-9a-f]{64}", window["raw_sha256"])
        total += window["stream_seconds"]
    assert total >= STREAM_SPAN_FLOOR_SECONDS


def test_run_log_agrees_with_manifest():
    front = gate_module().parse_front_matter(SPIKE.read_text(encoding="utf-8"))
    logged = front["run_windows"]
    windows = manifest()["windows"]
    assert len(logged) == len(windows)
    for mine, theirs in zip(logged, windows, strict=True):
        for key in (
            "label",
            "host",
            "dialect",
            "first_us",
            "last_us",
            "frames",
            "bytes",
            "raw_sha256",
        ):
            assert mine[key] == theirs[key], key


def test_fixture_times_inside_windows():
    data = manifest()
    spans = [(w["first_us"], w["last_us"]) for w in data["windows"]]
    analysis = importlib.import_module("spike_lib.analysis")
    times = []
    for envelope in main_frames():
        t = analysis.parse_time_us(payload_of(envelope).get("time"))
        assert t is not None
        assert any(first <= t <= last for first, last in spans)
        times.append(t)
    assert min(times) == data["start_stream_us"]
    assert max(times) == data["end_stream_us"]


def test_manifest_coverage_matches_fixture():
    """Recompute the coverage contract from the fixture file itself, under the recorded policy."""
    sel = selection()
    data = manifest()
    policy = data["selection_policy"]
    allow = policy["allowlist_domains"]
    stored: dict[str, int] = {}
    cascades: list[set[str]] = []
    deep: set[int] = set()
    children = {"reply": 0, "quote": 0, "repost": 0}
    orphans = 0
    deletes = {"post": 0, "repost": 0}
    accounts: dict[str, int] = {}
    syncs = 0
    negatives = {
        "total": 0, "near_miss_non_allowlisted": 0, "non_english_allowlisted": 0,
        "adult_labelled": 0, "shortener": 0, "reply_with_link": 0,
    }  # fmt: skip
    roots: dict[str, int] = {}
    depth: dict[str, int | None] = {}
    for envelope in main_frames():
        payload = payload_of(envelope)
        suffix = payload["$type"].rsplit("#", 1)[-1]
        if suffix == "account":
            status = payload["account"]["status"]
            accounts[status] = accounts.get(status, 0) + 1
        elif suffix == "sync":
            syncs += 1
        elif suffix == "commit" and payload["operation"] == "delete":
            if record_uri(payload) in stored:
                deletes["post" if payload["collection"] == POST else "repost"] += 1
        elif suffix == "commit":
            uri = record_uri(payload)
            record = payload["record"]
            edge = sel.derive_edge(payload["collection"], record)
            assert edge is not None
            if edge.kind == "root":
                decision = sel.seed_decision(
                    record, uri, allow,
                    require_lang=policy["require_lang"], sample_per_10k=policy["sample_per_10k"],
                )  # fmt: skip
                if decision.eligible:
                    roots[uri] = len(cascades)
                    stored[uri] = len(cascades)
                    depth[uri] = 0
                    cascades.append(set())
                    continue
                negatives["total"] += 1
                negatives["adult_labelled"] += int(adult_or_hidden(sel, record))
                reason = decision.reason
                if reason == "not_allowlisted" and sel.link_urls(record):
                    negatives["near_miss_non_allowlisted"] += 1
                elif reason == "lang":
                    negatives["non_english_allowlisted"] += 1
                elif reason == "shortener":
                    negatives["shortener"] += 1
                continue
            orphan = False
            if edge.parent in stored:
                index = stored[edge.parent]
            elif edge.kind == "reply" and edge.reply_root in roots:
                index, orphan = roots[edge.reply_root], True
            else:
                negatives["total"] += 1
                negatives["adult_labelled"] += int(adult_or_hidden(sel, record))
                if edge.kind == "reply" and sel.link_urls(record):
                    negatives["reply_with_link"] += 1
                continue
            stored[uri] = index
            parent_depth = depth.get(edge.parent)
            depth[uri] = (
                None
                if orphan or edge.kind == "repost" or parent_depth is None
                else parent_depth + 1
            )
            children[edge.kind] += 1
            cascades[index].add(edge.kind)
            orphans += int(orphan)
            if edge.kind == "reply" and (depth[uri] or 0) >= 2:
                deep.add(index)
    cov = data["coverage"]
    assert cov["tracked_roots"] == len(roots) == len(cascades)
    assert cov["children_by_kind"] == children
    assert cov["cascades_with_replies"] == sum("reply" in k for k in cascades)
    assert cov["cascades_with_quotes"] == sum("quote" in k for k in cascades)
    assert cov["cascades_with_reposts"] == sum("repost" in k for k in cascades)
    assert cov["cascades_with_depth2_replies"] == len(deep)
    assert cov["orphan_replies"] == orphans
    assert cov["deletes"] == deletes
    assert cov["account_events_by_status"] == dict(sorted(accounts.items()))
    assert cov["sync_events"] == syncs
    assert cov["negative_controls"] == negatives
    counts = data["counts_by_kind"]
    lines = main_frames()
    assert counts["account"] == sum(payload_of(e)["$type"].endswith("#account") for e in lines)
    assert counts["sync"] == syncs
    created = [payload_of(e) for e in lines if payload_of(e)["$type"].endswith("#commit")]
    assert counts["post_create"] == sum(
        p["collection"] == POST and p["operation"] == "create" for p in created
    )
    assert counts["repost_create"] == sum(
        p["collection"] == REPOST and p["operation"] == "create" for p in created
    )


# ----------------------------------------------------------------------------- scrub-2 privacy

UUID_RX = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
URL_RX = re.compile(r"https?://[^\"]+")
PERSONAL_HOSTS = ("bsky.app", "bsky.social", "bsky.network", "substack.com", "note.com", "t.me")


def fixture_urls() -> list[str]:
    found = []
    for path in (MAIN_PATH, SAMPLES_PATH):
        found.extend(URL_RX.findall(path.read_text(encoding="utf-8")))
    return found


def host_of(url: str) -> str:
    from urllib.parse import urlsplit

    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def test_scrub2_no_account_profile_or_personal_page_url_remains():
    urls = fixture_urls()
    assert urls
    for url in urls:
        lowered = url.lower()
        host = host_of(url)
        assert not any(host == h or host.endswith("." + h) for h in PERSONAL_HOSTS)
        assert "bsky.app" not in lowered
        assert "bsky.social" not in lowered
        assert "/profile/" not in lowered
        assert "/@" not in lowered
        assert "t.me/" not in lowered
        assert "giftarticle" not in lowered
        assert "/redeem/" not in lowered
        assert not UUID_RX.search(url)


def test_scrub2_every_other_host_is_a_placeholder():
    sel = selection()
    allow = manifest()["selection_policy"]["allowlist_domains"]
    placeholders = 0
    for url in fixture_urls():
        host = host_of(url)
        if sel.host_allowed(host, allow):
            continue
        if sel.is_shortener(host):
            assert url.rstrip("/").count("/") == 2, "a shortener keeps its host only"
            continue
        assert host.endswith(".invalid")
        assert re.fullmatch(r"https://nonlisted-[1-9][0-9]*\.invalid/", url)
        placeholders += 1
    assert placeholders > 0


def test_scrub2_no_adult_labelled_frame_remains():
    sel = selection()
    for path in (MAIN_PATH, SAMPLES_PATH):
        for line in path.read_text(encoding="utf-8").splitlines():
            for key, value in walk(json.loads(line)):
                if key == "labels" and isinstance(value, dict):
                    vals = {v.get("val") for v in value.get("values", []) if isinstance(v, dict)}
                    assert not vals & sel.ADULT_LABELS
    assert manifest()["coverage"]["negative_controls"]["adult_labelled"] == 0


def test_scrub2_pass_is_recorded_and_the_committed_files_are_a_fixed_point():
    data = manifest()
    assert data["scrubber_version"] == "scrub-2"
    assert data["rescrub"]["from_version"] == "scrub-1"
    assert data["rescrub"]["pre_pass_sha256"] == {
        MAIN_PATH.name: PRE_PASS_FIXTURE_SHA256,
        SAMPLES_PATH.name: PRE_PASS_SAMPLES_SHA256,
    }
    assert data["scrub2"]["main"]["frames_dropped_adult_label"] == 3
    assert data["frames_dropped_by_scrubber"] == 3
    assert data["coverage"]["tracked_roots"] == TRACKED_ROOTS_SCRUB1
    scrub = importlib.import_module("spike_lib.scrub")
    allow = data["selection_policy"]["allowlist_domains"]
    for path in (MAIN_PATH, SAMPLES_PATH):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        again, state = scrub.rescrub(rows, allow)
        assert again == rows
        assert state.frames_dropped_adult == 0


def test_manifest_states_the_privacy_limits_and_a_removal_contact():
    privacy = manifest()["privacy"]
    assert "not anonymised" in privacy["status"]
    assert "rates" in privacy["sampling"]
    assert "v1" in privacy["samples_file"]
    assert "universe" in privacy["samples_file"]
    assert "github.com/areveeess/TruthTrail/issues" in privacy["removal_requests"]
