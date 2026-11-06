"""``ReplaySource``: the recorded-real guard and deterministic replay (D-04, D-11, T-03-26).

The packaged recording replays completely, in file order, through the production dialect and
normaliser. Anything that is not a recorded-real, hash-matching recording is refused before a
single item is produced, including the Phase 1 demo fixture. Tampered copies are built in a
temporary directory from the real files; the packaged files are never edited. Recordings built
here to exercise the drop counter are named ``constructed_*`` and are never presented as real.
"""

import ast
import asyncio
import hashlib
import json
import shutil
import socket
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from conftest import FIXTURE_MANIFEST, recorded_lines, sample_rows
from test_ingest_normalise import GOLDEN_TYPES

import truthtrail
from truthtrail.ingest import source as source_module
from truthtrail.ingest.dialect import InfoFrame, classify_frame, parse_stream_time
from truthtrail.ingest.normalise import Dropped, normalise
from truthtrail.ingest.pseudonym import Keyer
from truthtrail.ingest.source import (
    DEFAULT_MANIFEST,
    DropCounter,
    ReplayRefused,
    ReplaySource,
    SourceItem,
)

PACKAGE = Path(truthtrail.__file__).resolve().parent
DEMO_FIXTURE = PACKAGE / "data" / "demo_analyze.json"
SYNTHETIC_NAMES = frozenset({"demo_analyze", "load_demo_fixture", "FIXTURE_PATH"})
GUARDED_PACKAGES = ("ingest", "db", "enrich")


def collect(
    source: ReplaySource, cursor: int | None = None, drops: DropCounter | None = None
) -> list[SourceItem]:
    async def run() -> list[SourceItem]:
        return [item async for item in source.items(cursor, drops)]

    return asyncio.run(run())


def copy_recording(tmp_path: Path) -> Path:
    """Copy the packaged manifest and data file into ``tmp_path``; return the manifest copy."""
    for path in FIXTURE_MANIFEST.parent.iterdir():
        shutil.copy(path, tmp_path / path.name)
    return tmp_path / FIXTURE_MANIFEST.name


def edit_manifest(path: Path, change: Any) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def data_path_of(manifest: Path) -> Path:
    return manifest.with_name(manifest.name.removesuffix(".manifest.json") + ".jsonl")


def stream_time_of(line: str) -> int | None:
    payload = json.loads(line).get("payload", {})
    value = payload.get("witnessedAt") or payload.get("time")
    return parse_stream_time(value) if isinstance(value, str) else None


# ----------------------------------------------------------------------------- full replay


def test_default_manifest_is_the_packaged_recording() -> None:
    assert DEFAULT_MANIFEST.resolve() == FIXTURE_MANIFEST.resolve()


def test_the_recording_replays_completely_in_file_order(keyer: Keyer) -> None:
    source = ReplaySource(DEFAULT_MANIFEST, keyer)
    assert (source.mode, source.host, source.dialect) == ("replay", "recorded", "v2")
    drops = DropCounter()
    items = collect(source, None, drops)
    histogram = Counter(type(item.result).__name__ for item in items)
    histogram.update({"Dropped": drops.total()})
    assert dict(histogram) == GOLDEN_TYPES
    assert drops.as_dict() == {"account_status_ignored": GOLDEN_TYPES["Dropped"]}
    expected = [
        result
        for line in recorded_lines()
        if not isinstance(result := normalise(classify_frame(line, "v2"), keyer), Dropped)
    ]
    assert [item.result for item in items] == expected
    for item in items:
        assert item.cursor_us == item.result.time_us


def test_replay_is_deterministic(keyer: Keyer) -> None:
    first = collect(ReplaySource(DEFAULT_MANIFEST, keyer))
    second = collect(ReplaySource(DEFAULT_MANIFEST, keyer))
    assert first == second


def test_a_resume_cursor_skips_exactly_the_earlier_frames_and_includes_the_cursor(
    keyer: Keyer,
) -> None:
    times = [stream_time_of(line) for line in recorded_lines()]
    assert all(t is not None for t in times)
    middle = sorted(t for t in times if t is not None)[len(times) // 2]
    source = ReplaySource(DEFAULT_MANIFEST, keyer)
    drops = DropCounter()
    resumed = collect(source, middle, drops)
    everything_drops = DropCounter()
    everything = collect(source, None, everything_drops)
    expected = [
        item for item in everything if item.cursor_us is not None and item.cursor_us >= middle
    ]
    assert resumed == expected
    assert any(item.cursor_us == middle for item in resumed)
    assert all(item.cursor_us is not None and item.cursor_us >= middle for item in resumed)
    assert 0 < len(resumed) < len(everything)
    assert drops.total() <= everything_drops.total()


def test_cursor_edges(keyer: Keyer) -> None:
    source = ReplaySource(DEFAULT_MANIFEST, keyer)
    everything = collect(source)
    assert collect(source, 0) == everything
    last = max(item.cursor_us for item in everything if item.cursor_us is not None)
    assert [i.cursor_us for i in collect(source, last)] == [last] * sum(
        1 for i in everything if i.cursor_us == last
    )
    assert collect(source, last + 1) == []


def test_the_module_never_calls_replayed_data_synthetic() -> None:
    text = Path(source_module.__file__).read_text(encoding="utf-8")
    assert "synthetic" not in text.lower()


# ----------------------------------------------------------------------------- refusals


def test_a_synthetic_source_mode_is_refused(tmp_path: Path, keyer: Keyer) -> None:
    manifest = copy_recording(tmp_path)
    edit_manifest(manifest, lambda d: d.update(source_mode="synthetic"))
    with pytest.raises(ReplayRefused, match="recorded-real"):
        ReplaySource(manifest, keyer)


def test_a_missing_source_mode_is_refused(tmp_path: Path, keyer: Keyer) -> None:
    manifest = copy_recording(tmp_path)
    edit_manifest(manifest, lambda d: d.pop("source_mode"))
    with pytest.raises(ReplayRefused, match="recorded-real"):
        ReplaySource(manifest, keyer)


@pytest.mark.parametrize("mode", ["Recorded-Real", "recorded-real ", "replay", None, 1])
def test_only_the_exact_mode_string_passes(tmp_path: Path, keyer: Keyer, mode: object) -> None:
    manifest = copy_recording(tmp_path)
    edit_manifest(manifest, lambda d: d.update(source_mode=mode))
    with pytest.raises(ReplayRefused):
        ReplaySource(manifest, keyer)


def test_a_modified_sha256_in_the_manifest_is_refused(tmp_path: Path, keyer: Keyer) -> None:
    manifest = copy_recording(tmp_path)

    def tamper(data: dict[str, Any]) -> None:
        entry = data["files"][0]
        entry["sha256"] = hashlib.sha256(b"something else").hexdigest()

    edit_manifest(manifest, tamper)
    with pytest.raises(ReplayRefused, match="sha256"):
        ReplaySource(manifest, keyer)


def test_a_modified_data_file_is_refused(tmp_path: Path, keyer: Keyer) -> None:
    manifest = copy_recording(tmp_path)
    data = data_path_of(manifest)
    content = data.read_bytes()
    data.write_bytes(content.replace(b"app.bsky.feed.repost", b"app.bsky.feed.reposT", 1))
    with pytest.raises(ReplayRefused, match="sha256"):
        ReplaySource(manifest, keyer)


def test_a_missing_data_file_is_refused(tmp_path: Path, keyer: Keyer) -> None:
    manifest = copy_recording(tmp_path)
    data_path_of(manifest).unlink()
    with pytest.raises(ReplayRefused, match="does not exist"):
        ReplaySource(manifest, keyer)


def test_a_truncated_manifest_is_refused(tmp_path: Path, keyer: Keyer) -> None:
    manifest = copy_recording(tmp_path)
    text = manifest.read_text(encoding="utf-8")
    manifest.write_text(text[: len(text) // 2], encoding="utf-8")
    with pytest.raises(ReplayRefused, match="readable JSON"):
        ReplaySource(manifest, keyer)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.pop("files"), "files list"),
        (lambda d: d.update(files="x"), "files list"),
        (
            lambda d: d.update(
                files=[f for f in d["files"] if f["name"].endswith("samples.jsonl")]
            ),
            "not listed",
        ),
        (lambda d: d["files"][0].pop("sha256"), "no sha256"),
        (lambda d: d["files"][0].update(sha256="abc"), "no sha256"),
        (lambda d: d.update(dialects=["v1"]), "v2 dialect"),
    ],
    ids=["no-files", "files-not-list", "data-not-listed", "no-sha", "short-sha", "v1-dialect"],
)
def test_manifests_missing_what_the_guard_needs_are_refused(
    tmp_path: Path, keyer: Keyer, change: Any, message: str
) -> None:
    manifest = copy_recording(tmp_path)
    edit_manifest(manifest, change)
    with pytest.raises(ReplayRefused, match=message):
        ReplaySource(manifest, keyer)


def test_a_manifest_that_is_not_an_object_or_does_not_exist_is_refused(
    tmp_path: Path, keyer: Keyer
) -> None:
    manifest = tmp_path / "x.manifest.json"
    manifest.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ReplayRefused, match="JSON object"):
        ReplaySource(manifest, keyer)
    with pytest.raises(ReplayRefused, match="does not exist"):
        ReplaySource(tmp_path / "absent.manifest.json", keyer)


def test_the_phase1_synthetic_fixture_is_refused(tmp_path: Path, keyer: Keyer) -> None:
    assert DEMO_FIXTURE.is_file()
    with pytest.raises(ReplayRefused, match="not a recording manifest"):
        ReplaySource(DEMO_FIXTURE, keyer)
    # Even under a manifest-looking name its content is refused: no recorded-real mode.
    disguised = tmp_path / "demo.manifest.json"
    shutil.copy(DEMO_FIXTURE, disguised)
    with pytest.raises(ReplayRefused, match="recorded-real"):
        ReplaySource(disguised, keyer)


def test_refusal_messages_are_fixed_text(tmp_path: Path, keyer: Keyer) -> None:
    manifest = copy_recording(tmp_path)
    edit_manifest(manifest, lambda d: d.update(source_mode="MARKER-MODE"))
    with pytest.raises(ReplayRefused) as info:
        ReplaySource(manifest, keyer)
    assert "MARKER" not in str(info.value)
    assert str(tmp_path) not in str(info.value)
    assert isinstance(info.value, ValueError)


# ----------------------------------------------------------------------------- drop counter


def _constructed_recording(tmp_path: Path, lines: list[str]) -> Path:
    """A recording built from real lines plus the given extra lines, with a matching manifest."""
    data = ("\n".join(lines) + "\n").encode("utf-8")
    name = "constructed-recording"
    (tmp_path / f"{name}.jsonl").write_bytes(data)
    manifest = {
        "source_mode": "recorded-real",
        "dialects": ["v2"],
        "files": [{"name": f"{name}.jsonl", "sha256": hashlib.sha256(data).hexdigest()}],
    }
    path = tmp_path / f"{name}.manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_the_drop_counter_records_bad_frames_by_reason(tmp_path: Path, keyer: Keyer) -> None:
    real = list(recorded_lines())[:5]
    sync_line = next(line for line in recorded_lines() if "#sync" in line)
    constructed_identity = sync_line.replace("#sync", "#identity")
    lines = [*real, "not json", "[1]", '{"$type":"other"}', constructed_identity, "\xff"]
    source = ReplaySource(_constructed_recording(tmp_path, lines), keyer)
    drops = DropCounter()
    items = collect(source, None, drops)
    assert drops.as_dict()["bad_frame:not_json"] == 2
    assert drops.as_dict()["bad_frame:not_object"] == 1
    assert drops.as_dict()["bad_frame:unknown_type"] == 1
    assert drops.as_dict()["identity_ignored"] == 1
    assert len(items) + drops.total() == len(lines)
    # Without a counter the drops are discarded, never yielded.
    assert collect(source) == items


def test_control_frames_carry_no_cursor_and_keep_their_position(
    tmp_path: Path, keyer: Keyer
) -> None:
    info_frame = next(
        r["frame"]
        for r in sample_rows()
        if r["frame"].get("payload", {}).get("$type", "").endswith("#info")
    )
    timed: list[tuple[int, str]] = []
    for line in recorded_lines():
        moment = stream_time_of(line)
        if moment is not None and (not timed or moment > timed[-1][0]):
            timed.append((moment, line))
        if len(timed) == 3:
            break
    (t0, l0), (t1, l1), (t2, l2) = timed
    lines = [l0, l1, json.dumps(info_frame), l2]
    source = ReplaySource(_constructed_recording(tmp_path, lines), keyer)
    infos = [item for item in collect(source) if isinstance(item.result, InfoFrame)]
    assert len(infos) == 1
    assert infos[0].cursor_us is None
    # The info frame keeps the position of the frame before it: included when resuming at t1,
    # skipped when resuming at t2 (its predecessor is then before the cursor).
    assert any(isinstance(i.result, InfoFrame) for i in collect(source, t1))
    assert not any(isinstance(i.result, InfoFrame) for i in collect(source, t2))
    assert [i.cursor_us for i in collect(source, t2)] == [t2]
    assert t0 < t1 < t2


def test_replay_makes_no_network_call(keyer: Keyer, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def refuse(name: str) -> Any:
        def call(*args: Any, **kwargs: Any) -> Any:
            calls.append(name)
            raise AssertionError(name)

        return call

    monkeypatch.setattr(socket.socket, "connect", refuse("connect"))
    monkeypatch.setattr(socket, "getaddrinfo", refuse("getaddrinfo"))
    monkeypatch.setattr(socket, "create_connection", refuse("create_connection"))
    assert collect(ReplaySource(DEFAULT_MANIFEST, keyer))
    assert calls == []


# ----------------------------------------------------------------------------- synthetic fixture


def synthetic_references(source: str) -> list[str]:
    """Names, attributes, import names and string constants that refer to the demo fixture."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        candidates: list[str] = []
        if isinstance(node, ast.Name):
            candidates.append(node.id)
        elif isinstance(node, ast.Attribute):
            candidates.append(node.attr)
        elif isinstance(node, ast.alias):
            candidates.extend(part for part in node.name.split("."))
        elif isinstance(node, ast.ImportFrom) and node.module:
            candidates.extend(node.module.split("."))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            candidates.extend(n for n in SYNTHETIC_NAMES if n in node.value)
        found.extend(c for c in candidates if c in SYNTHETIC_NAMES)
    return found


def test_no_ingest_db_or_enrich_module_references_the_synthetic_fixture() -> None:
    files = [
        path
        for package in GUARDED_PACKAGES
        if (PACKAGE / package).is_dir()
        for path in sorted((PACKAGE / package).rglob("*.py"))
    ]
    assert len(files) >= 10
    offenders = {
        str(path.relative_to(PACKAGE)): hits
        for path in files
        if (hits := synthetic_references(path.read_text(encoding="utf-8")))
    }
    assert offenders == {}


def test_the_synthetic_reference_walker_is_not_blind() -> None:
    source = (
        "from truthtrail.api.analyze import load_demo_fixture, FIXTURE_PATH\n"
        "import truthtrail.api.analyze as a\n"
        "a.load_demo_fixture()\n"
        "path = 'data/demo_analyze.json'\n"
    )
    assert sorted(set(synthetic_references(source))) == sorted(SYNTHETIC_NAMES)
    assert synthetic_references("from truthtrail.ingest import source\nx = 'recorded'\n") == []
