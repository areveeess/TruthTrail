"""Tests for scripts/bluesky_spike.py (plan 03-01, D-01 and D-07).

The tool is loaded with importlib as tests/test_copy_guard.py loads its script. No test touches the
network: connections, the clock, sleeping and HTTP are injected. Every log and frame built here is
hand-made constructed data (``constructed_*``), never presented as recorded.
"""

import ast
import asyncio
import gzip
import importlib.util
import itertools
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
TOOL_PATH = SCRIPTS / "bluesky_spike.py"
sys.path.insert(0, str(SCRIPTS))

from spike_lib import analysis  # noqa: E402

TYPE = "network.bsky.jetstream.subscribeEvents#"
POST = "app.bsky.feed.post"
T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("bluesky_spike", TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["bluesky_spike"] = module
    spec.loader.exec_module(module)
    return module


def ts(sec: float) -> str:
    return (T0 + timedelta(seconds=sec)).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def frame_text(seq: int, sec: float, kind: str = "commit", **extra) -> str:
    payload = {"$type": TYPE + kind, "seq": seq, "time": ts(sec), "witnessedAt": ts(sec)}
    if kind == "commit":
        payload.update(
            {
                "did": f"did:plc:constructed{seq}",
                "operation": "create",
                "collection": POST,
                "rkey": f"k{seq}",
                "rev": f"r{seq}",
                "record": {"$type": POST, "createdAt": ts(sec), "text": "constructed words"},
            }
        )
    payload.update(extra)
    return json.dumps({"$type": "message", "payload": payload})


# ----------------------------------------------------------------------------- fakes


class StatusError(Exception):
    def __init__(self, status: int, body: bytes = b"") -> None:
        super().__init__(f"HTTP {status}")
        self.status = status
        self.response = type("R", (), {"status_code": status, "body": body})()


class ClosedError(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"closed {code}")
        self.sent = type("C", (), {"code": code})()


class FakeWS:
    subprotocol = "xrpc.v1.json"

    def __init__(self, frames, after, tick) -> None:
        self.frames = iter(frames)
        self.after = after
        self.tick = tick

    async def recv(self):
        try:
            frame = next(self.frames)
        except StopIteration:
            if self.after is not None:
                raise self.after from None
            await asyncio.sleep(3600)
            raise
        self.tick()
        return frame


class FakeCM:
    def __init__(self, plan, tick) -> None:
        self.plan = plan
        self.tick = tick

    async def __aenter__(self):
        if isinstance(self.plan, BaseException):
            raise self.plan
        frames, after = self.plan
        return FakeWS(frames, after, self.tick)

    async def __aexit__(self, *exc):
        return False


class FakeConnect:
    """Replays one plan per call: an exception to raise, or (frames, exception_after)."""

    def __init__(self, plans, tick=lambda: None) -> None:
        self.plans = list(plans)
        self.tick = tick
        self.urls: list[str] = []
        self.kwargs: list[dict] = []

    def __call__(self, url, **kwargs):
        self.urls.append(url)
        self.kwargs.append(kwargs)
        plan = self.plans.pop(0) if len(self.plans) > 1 else self.plans[0]
        return FakeCM(plan, self.tick)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def tick(self) -> None:
        self.now += 1.0


def make_deps(tool, connect=None, clock=None, sleeps=None, http=None):
    sleeps = sleeps if sleeps is not None else []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    kw = {"connect": connect, "sleep": fake_sleep, "rng": lambda: 0.5}
    if clock is not None:
        kw["clock"] = clock
    if http is not None:
        kw["http_get"] = http
    return tool.Deps(**kw)


def read_log(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


# ----------------------------------------------------------------------------- caps and safety


def test_seconds_cap_is_rejected_with_exit_2(tool, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert tool.main(["record", "--seconds", "7201", "--out", "spike-output"]) == 2
    assert tool.main(["record", "--max-seconds", "7201", "--out", "spike-output"]) == 2
    assert tool.main(["record", "--seconds", "0", "--out", "spike-output"]) == 2
    assert tool.main(["probe", "--seconds", "9999"]) == 2


def test_bytes_cap_has_a_hard_ceiling(tool, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert tool.main(["record", "--seconds", "5", "--max-bytes", str(5 * 1024**3)]) == 2
    assert tool.main(["record", "--seconds", "5", "--max-bytes", "0"]) == 2


def test_out_must_sit_below_spike_output(tool, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert tool.main(["record", "--seconds", "5", "--out", "somewhere-else"]) == 2
    assert tool.main(["record", "--seconds", "5", "--out", "../spike-output"]) == 2
    assert tool.main(["record", "--seconds", "5", "--out", "/tmp/spike-output-x"]) == 2


def test_cut_fixture_out_is_limited_to_the_fixture_directory(tool, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert (
        tool.main(["cut-fixture", "--date", "2026-01-01", "--out", str(tmp_path / "elsewhere")])
        == 2
    )


def test_tool_source_has_no_database_driver_no_key_reads_and_no_tls_bypass():
    text = TOOL_PATH.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imported = set()
    env_reads = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = node.func.value
            is_environ = isinstance(owner, ast.Attribute) and owner.attr == "environ"
            if is_environ and node.func.attr == "get" and node.args:
                arg = node.args[0]
                env_reads.add(arg.value if isinstance(arg, ast.Constant) else "<dynamic>")
    assert not imported & {"psycopg", "psycopg2", "sqlalchemy", "asyncpg", "sqlite3", "requests"}
    assert env_reads <= {"COLLECTOR_CONTACT", "TRUTHTRAIL_PG_BIN"}
    for needle in ("GNEWS_API_KEY", "BLUESKY_APP_PASSWORD", "BLUESKY_HANDLE", "createSession"):
        assert needle not in text
    for needle in ("verify=False", "CERT_NONE", "_create_unverified_context", "check_hostname"):
        assert needle not in text
    for path in (SCRIPTS / "spike_lib").glob("*.py"):
        assert "psycopg" not in path.read_text(encoding="utf-8")


def test_user_agent_names_the_repository_and_optional_contact(tool, monkeypatch):
    monkeypatch.delenv("COLLECTOR_CONTACT", raising=False)
    assert tool.user_agent() == "TruthTrail-spike/0.1 (+https://github.com/areveeess/TruthTrail)"
    monkeypatch.setenv("COLLECTOR_CONTACT", "ops@example.test")
    assert tool.user_agent().endswith("ops@example.test")


def test_urls_follow_the_two_dialects(tool):
    v2 = tool.build_url("h.example", "v2", 123)
    assert v2.startswith("wss://h.example/xrpc/network.bsky.jetstream.subscribeEvents?")
    for part in (
        "kinds=commit",
        "kinds=account",
        "kinds=sync",
        "maxMessageSizeBytes=1048576",
        "cursor=123",
    ):
        assert part in v2
    assert "wantedCollections" not in v2
    v1 = tool.build_url("h.example", "v1")
    assert v1.startswith("wss://h.example/subscribe?")
    assert "wantedCollections=app.bsky.feed.post" in v1
    kwargs = tool.connect_kwargs("v2", None)
    assert kwargs["subprotocols"] == ["xrpc.v1.json"]
    assert kwargs["max_size"] == 2 * 1024 * 1024
    assert "ssl" not in kwargs
    assert "proxy" not in kwargs
    assert (
        tool.connect_kwargs("v2", "http://proxy.example:8080")["proxy"]
        == "http://proxy.example:8080"
    )


# ----------------------------------------------------------------------------- record


def test_403_stops_after_one_attempt_without_retry(tool, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    connect = FakeConnect([StatusError(403)])
    sleeps: list[float] = []
    code = tool.main(
        ["record", "--seconds", "30", "--label", "w", "--out", "spike-output/raw"],
        make_deps(tool, connect, sleeps=sleeps),
    )
    assert code == 3
    assert len(connect.urls) == 1
    assert sleeps == []
    meta = json.loads((tmp_path / "spike-output/raw/w.meta.json").read_text(encoding="utf-8"))
    assert meta["stop_reason"] == "auth"
    err = capsys.readouterr().err
    assert "HTTP 403" in err
    assert "no retry" in err


def test_401_on_probe_http_stops_before_any_websocket(tool, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    connect = FakeConnect([([frame_text(1, 0)], None)])
    code = tool.main(
        ["probe", "--seconds", "1"], make_deps(tool, connect, http=lambda url: (401, b""))
    )
    assert code == 3
    assert connect.urls == []
    assert "no retry" in capsys.readouterr().err


def test_403_on_probe_websocket_stops_the_whole_probe(tool, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    connect = FakeConnect([StatusError(403)])
    code = tool.main(
        ["probe", "--seconds", "1"], make_deps(tool, connect, http=lambda url: (200, b""))
    )
    assert code == 3
    assert len(connect.urls) == 1


def test_transient_failures_are_retried_with_bounded_backoff(tool, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    connect = FakeConnect([ConnectionResetError("constructed")])
    sleeps: list[float] = []
    code = tool.main(
        ["record", "--seconds", "600", "--label", "f", "--out", "spike-output/raw"],
        make_deps(tool, connect, sleeps=sleeps),
    )
    assert code == 5
    assert len(connect.urls) == 8
    assert len(sleeps) == 7
    assert all(0 <= s <= 60 for s in sleeps)
    meta = json.loads((tmp_path / "spike-output/raw/f.meta.json").read_text(encoding="utf-8"))
    assert meta["stop_reason"] == "failures"
    assert meta["reconnects"] == 8


def test_record_writes_gzip_level_one_lines_and_stops_at_the_byte_cap(tool, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    frames = [frame_text(i, i) for i in range(1, 50)]
    size = len(frames[0].encode("utf-8"))
    connect = FakeConnect([(frames, None)])
    code = tool.main(
        [
            "record",
            "--seconds",
            "600",
            "--max-bytes",
            str(size * 3 + 5),
            "--label",
            "b",
            "--out",
            "spike-output/raw",
        ],
        make_deps(tool, connect),
    )
    assert code == 0
    path = tmp_path / "spike-output/raw/b.jsonl.gz"
    lines = read_log(path)
    frame_lines = [x for x in lines if "f" in x]
    assert len(frame_lines) == 4
    assert all(set(x) == {"rx", "f"} and isinstance(x["rx"], int) for x in frame_lines)
    assert json.loads(frame_lines[0]["f"])["payload"]["seq"] == 1
    assert path.read_bytes()[8] == 4  # gzip header XFL byte: 4 means fastest (level 1)
    meta = json.loads((tmp_path / "spike-output/raw/b.meta.json").read_text(encoding="utf-8"))
    assert meta["stop_reason"] == "bytes"
    assert meta["frames"] == 4
    assert meta["host"] == "jetstream.us-east.bsky.network"
    assert meta["dialect"] == "v2"
    assert connect.kwargs[0]["subprotocols"] == ["xrpc.v1.json"]


def test_record_stops_at_the_time_bound_with_an_injected_clock(tool, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    clock = Clock()
    connect = FakeConnect([((frame_text(i, i) for i in itertools.count(1)), None)], clock.tick)
    code = tool.main(
        ["record", "--seconds", "5", "--label", "s", "--out", "spike-output/raw"],
        make_deps(tool, connect, clock=clock),
    )
    assert code == 0
    meta = json.loads((tmp_path / "spike-output/raw/s.meta.json").read_text(encoding="utf-8"))
    assert meta["stop_reason"] == "seconds"
    assert 4 <= meta["frames"] <= 6
    assert meta["bound_seconds"] == 5.0


def test_reconnect_resumes_from_the_last_stream_time_minus_five_seconds(
    tool, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    clock = Clock()
    first = [frame_text(1, 10), frame_text(2, 20)]
    second = (frame_text(i, 20 + i) for i in itertools.count(3))
    connect = FakeConnect(
        [(first, ConnectionResetError("constructed")), (second, None)], clock.tick
    )
    code = tool.main(
        ["record", "--seconds", "8", "--label", "r", "--out", "spike-output/raw"],
        make_deps(tool, connect, clock=clock),
    )
    assert code == 0
    assert "cursor" not in connect.urls[0]
    expected = int((T0 + timedelta(seconds=20 - 5)).timestamp() * 1_000_000)
    assert f"cursor={expected}" in connect.urls[1]
    meta = json.loads((tmp_path / "spike-output/raw/r.meta.json").read_text(encoding="utf-8"))
    assert meta["reconnects"] == 1


def test_oversize_close_stops_loudly_with_exit_5(tool, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    connect = FakeConnect([([frame_text(1, 1)], ClosedError(1009))])
    code = tool.main(
        ["record", "--seconds", "60", "--label", "o", "--out", "spike-output/raw"],
        make_deps(tool, connect),
    )
    assert code == 5
    assert len(connect.urls) == 1
    meta = json.loads((tmp_path / "spike-output/raw/o.meta.json").read_text(encoding="utf-8"))
    assert meta["stop_reason"] == "oversize_frame"
    assert meta["close_codes"] == {"1009": 1}
    assert "1009" in capsys.readouterr().err


def test_sixty_seconds_of_silence_counts_as_a_dead_connection(tool, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tool, "SILENCE_SECONDS", 0.05)
    connect = FakeConnect([([], None)])
    code = tool.main(
        ["record", "--seconds", "0.3", "--label", "q", "--out", "spike-output/raw"],
        make_deps(tool, connect),
    )
    assert code == 0
    assert len(connect.urls) >= 2


def test_websockets_missing_exits_4(tool, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(sys.modules, "websockets", None)
    monkeypatch.setitem(sys.modules, "websockets.asyncio", None)
    monkeypatch.setitem(sys.modules, "websockets.asyncio.client", None)
    code = tool.main(["record", "--seconds", "5", "--out", "spike-output/raw"])
    assert code == 4
    assert "websockets==17.2" in capsys.readouterr().err


# ----------------------------------------------------------------------------- probes


def test_probe_prints_one_row_per_host(tool, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    frames = [frame_text(1, 1), frame_text(2, 2)]
    connect = FakeConnect([(frames, ClosedError(1000))])
    code = tool.main(
        ["probe", "--seconds", "2", "--out", "spike-output/p"],
        make_deps(tool, connect, http=lambda url: (200, b"")),
    )
    assert code == 0
    rows = [line for line in capsys.readouterr().out.splitlines() if line.startswith("| jetstream")]
    assert len(rows) == 4
    assert (tmp_path / "spike-output/p/samples.jsonl").exists()


def test_cursor_test_reports_accepted_and_exact_error_names(tool, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    old = json.dumps(
        {
            "$type": "message",
            "payload": {"$type": TYPE + "info", "name": "OutdatedCursor", "message": "x"},
        }
    )
    plans = [([frame_text(1, 0)], ClosedError(1000))] * 5 + [
        ([old, frame_text(2, 0)], ClosedError(1000)),
        StatusError(400, b'{"error":"CursorTooOld","message":"below floor"}'),
        (
            [
                json.dumps(
                    {
                        "$type": "message",
                        "payload": {"$type": TYPE + "info", "name": "FutureCursor"},
                    }
                )
            ],
            ClosedError(1000),
        ),
    ]
    connect = FakeConnect(plans)
    code = tool.main(
        ["cursor-test", "--seconds", "2", "--out", "spike-output/c"], make_deps(tool, connect)
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "CursorTooOld" in out
    assert "OutdatedCursor" in out
    assert "FutureCursor" in out
    assert "seq=1 | CursorTooOld" in out
    assert len(connect.urls) == 8


def test_reconnect_test_counts_duplicates_against_the_expected_overlap(
    tool, tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    first = [frame_text(i, i) for i in range(1, 61)]
    second = [frame_text(i, i) for i in range(31, 91)]
    connect = FakeConnect(
        [(first, ClosedError(1000)), (second, ClosedError(1000)), ([], ClosedError(1000))]
    )
    code = tool.main(
        ["reconnect-test", "--seconds", "20", "--hold-seconds", "1", "--out", "spike-output/r"],
        make_deps(tool, connect),
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "| duplicates (seq seen in the first read) | 30 |" in out
    assert "| expected overlap (first-read frames with stream time >= cursor) | 31 |" in out
    assert "kinds=commit" in connect.urls[2]
    assert "org.user-intents.declaration" in connect.urls[2]


# ------------------------------------------------------------------ analyze, cut, appview


MARKER_DID = "did:plc:MARKERDID"
MARKER_TEXT = "MARKERTEXT secret words"
MARKER_HANDLE = "marker.handle.example"


def write_constructed_raw(directory: Path, label: str = "m", extra_seconds: float = 0.0) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    root_uri = f"at://{MARKER_DID}/{POST}/rootkey"
    rows = [
        {
            "$type": POST,
            "createdAt": ts(0),
            "text": MARKER_TEXT,
            "langs": ["en"],
            "embed": {
                "$type": "app.bsky.embed.external",
                "external": {"uri": "https://example-news.test/a?x=1", "title": MARKER_TEXT},
            },
            "facets": [
                {
                    "index": {"byteStart": 0, "byteEnd": 3},
                    "features": [{"$type": "app.bsky.richtext.facet#mention", "did": MARKER_DID}],
                }
            ],
        },
        {
            "$type": POST,
            "createdAt": ts(60),
            "text": f"@{MARKER_HANDLE} {MARKER_TEXT}",
            "reply": {"parent": {"uri": root_uri}, "root": {"uri": root_uri}},
        },
    ]
    frames = []
    for seq, (sec, record, rkey, did) in enumerate(
        [(0, rows[0], "rootkey", MARKER_DID), (60, rows[1], "replykey", "did:plc:other")], start=1
    ):
        payload = {
            "$type": TYPE + "commit",
            "did": did,
            "seq": seq,
            "time": ts(sec),
            "operation": "create",
            "collection": POST,
            "rkey": rkey,
            "rev": "r",
            "record": record,
        }
        frames.append(json.dumps({"$type": "message", "payload": payload}))
    frames.append(frame_text(3, 700 + extra_seconds))
    with gzip.open(directory / f"{label}.jsonl.gz", "wt", encoding="utf-8") as handle:
        for i, frame in enumerate(frames):
            handle.write(json.dumps({"rx": i, "f": frame}) + "\n")
    (directory / f"{label}.meta.json").write_text(
        json.dumps(
            {
                "host": "constructed.example",
                "dialect": "v2",
                "bound_seconds": 700,
                "stop_reason": "seconds",
            }
        ),
        encoding="utf-8",
    )
    return root_uri


def test_analyze_output_never_carries_identifiers_or_text(tool, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_constructed_raw(tmp_path / "spike-output" / "raw")
    allow = tmp_path / "allow.txt"
    allow.write_text("example-news.test  # wire-service\n", encoding="utf-8")
    code = tool.main(
        [
            "analyze",
            "--in",
            "spike-output/raw",
            "--out",
            "spike-output/analysis",
            "--allowlist",
            str(allow),
            "--summary",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    outputs = [out] + [
        p.read_text(encoding="utf-8") for p in (tmp_path / "spike-output/analysis").iterdir()
    ]
    assert len(outputs) >= 4
    for text in outputs:
        for marker in ("MARKER", "marker.handle", "did:", "at://", "example-news.test/a"):
            assert marker not in text
    assert "### S-5" in out
    assert "eligible_roots | 1" in out
    windows = (tmp_path / "spike-output/analysis/windows.json").read_text(encoding="utf-8")
    assert windows.count("\n") == 1
    spans = json.loads(windows)
    assert spans[0]["label"] == "m"
    assert spans[0]["stream_seconds"] == 700.0


def test_ensure_no_identifiers_raises_on_a_did():
    with pytest.raises(ValueError, match="identifier"):
        analysis.ensure_no_identifiers({"x": ["fine", MARKER_DID]})


def test_domains_only_lists_domains_not_accounts(tool, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_constructed_raw(tmp_path / "spike-output" / "raw")
    assert tool.main(["analyze", "--in", "spike-output/raw", "--domains-only"]) == 0
    out = capsys.readouterr().out
    assert "| domain | posts | distinct authors |" in out
    assert "MARKER" not in out
    assert "did:" not in out


def test_cut_fixture_writes_files_and_check_detects_drift(tool, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_constructed_raw(tmp_path / "spike-output" / "raw")
    allow = tmp_path / "allow.txt"
    allow.write_text("example-news.test  # wire-service\n", encoding="utf-8")
    fixture = tmp_path / "recorded"
    base = [
        "--in",
        "spike-output/raw",
        "--allowlist",
        str(allow),
        "--out",
        str(fixture),
        "--date",
        "2026-01-01",
        "--min-children",
        "1",
    ]
    assert tool.main(["cut-fixture", *base]) == 0
    manifest = json.loads(
        (fixture / "bluesky-2026-01-01.manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["source_mode"] == "recorded-real"
    assert manifest["coverage"]["tracked_roots"] == 1
    body = (fixture / "bluesky-2026-01-01.jsonl").read_text(encoding="utf-8")
    assert "MARKER" not in body
    assert "marker.handle" not in body
    capsys.readouterr()
    assert tool.main(["cut-fixture", *base, "--check"]) == 0
    assert "identical" in capsys.readouterr().out
    (fixture / "bluesky-2026-01-01.jsonl").write_text(body + "\n", encoding="utf-8")
    assert tool.main(["cut-fixture", *base, "--check"]) == 5


def test_cut_fixture_without_raw_logs_says_so(tool, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "spike-output/raw").mkdir(parents=True)
    code = tool.main(
        [
            "cut-fixture",
            "--in",
            "spike-output/raw",
            "--date",
            "2026-01-01",
            "--out",
            str(tmp_path / "recorded"),
        ]
    )
    assert code == 2
    assert "raw logs are deleted" in capsys.readouterr().err


def test_appview_check_compares_counts_without_printing_uris(tool, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    root_uri = write_constructed_raw(tmp_path / "spike-output" / "raw")
    allow = tmp_path / "allow.txt"
    allow.write_text("example-news.test  # wire-service\n", encoding="utf-8")
    seen: list[str] = []

    def fake_http(url: str):
        seen.append(url)
        body = {"posts": [{"uri": root_uri, "replyCount": 1, "repostCount": 0, "quoteCount": 0}]}
        return 200, json.dumps(body).encode("utf-8")

    code = tool.main(
        ["appview-check", "--in", "spike-output/raw", "--allowlist", str(allow)],
        make_deps(tool, http=fake_http),
    )
    assert code == 0
    out = capsys.readouterr().out
    assert len(seen) == 1
    assert "getPosts" in seen[0]
    assert "MARKERDID" not in out
    assert "at://" not in out
    assert "| reply: stream == AppView / stream <= AppView | 1.000 / 1.000 |" in out
    assert "| roots hydrated (others deleted or unavailable) | 1 |" in out


def test_storage_probe_exits_4_without_postgres_binaries(tool, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TRUTHTRAIL_PG_BIN", str(tmp_path / "missing"))
    monkeypatch.setattr(tool.shutil, "which", lambda name: None)
    monkeypatch.setattr(tool.Path, "glob", lambda self, pattern: iter(()))
    code = tool.main(["storage-probe", "--in", "spike-output/raw"])
    assert code == 4
    assert "PostgreSQL binaries" in capsys.readouterr().err


def test_storage_copy_rows_have_matching_column_counts(tool, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    raw = tmp_path / "spike-output" / "raw"
    write_constructed_raw(raw)
    refs = analysis.discover_logs(raw)
    _results, collector, _stats = analysis.analyze_logs(refs, ["example-news.test"], keep_rows=True)
    blocks = tool.build_copy_blocks(collector, 2)
    for table, columns in tool.COPY_COLUMNS.items():
        width = len(columns.split(", "))
        rows = blocks[table].splitlines()
        assert rows
        assert all(len(row.split("\t")) == width for row in rows)
    assert "MARKER" not in "".join(blocks.values()) or "x" in blocks["events"]
    assert "did:" not in "".join(blocks.values())
