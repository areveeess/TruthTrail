"""Bounded, read-only, credential-free spike tool for the public Bluesky Jetstream (plan 03-01).

It records and measures the public live tail so the owner can ratify the Phase 3 decisions. It
never writes outside a git-ignored ``spike-output`` directory, never opens a database connection
from Python, never calls GNews, never reads or sends a Bluesky credential and never disables TLS
verification. On HTTP 401 or 403 it stops with exit code 3 and a clear message: it never retries
or substitutes data.

Owner quick guide (the tool needs only the ephemeral ``websockets`` install, nothing else).

Linux or macOS, from the repository root::

    uv run --no-project --python 3.13 --with websockets==17.2 python scripts/bluesky_spike.py probe
    uv run --no-project --python 3.13 --with websockets==17.2 \\
        python scripts/bluesky_spike.py record --seconds 300 --out spike-output
    uv run --no-project --python 3.13 python scripts/bluesky_spike.py analyze \\
        --in spike-output --summary

Windows 11 PowerShell, from the repository root (behind a corporate proxy set ``HTTPS_PROXY`` and
``SSL_CERT_FILE`` first; verification stays on). The backtick continues a line::

    uv run --no-project --python 3.13 --with websockets==17.2 `
        python scripts\\bluesky_spike.py probe
    uv run --no-project --python 3.13 --with websockets==17.2 `
        python scripts\\bluesky_spike.py record --seconds 300 --out spike-output
    uv run --no-project --python 3.13 `
        python scripts\\bluesky_spike.py analyze --in spike-output --summary

Paste the printed summary (counts and rates only: no account, post text or link) into the
"Windows result (S-12)" block of 03-SPIKE.md.

Subcommands: probe, record, cursor-test, reconnect-test, appview-check, storage-probe, analyze,
cut-fixture. Exit codes: 0 ok, 2 usage error or cap rejected, 3 stopped on HTTP 401 or 403,
4 unavailable (missing websockets or PostgreSQL binaries), 5 source failed after the retry budget.
Standard library plus ``websockets``; output is counts and rates only.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import gzip
import hashlib
import hmac
import importlib.metadata
import json
import math
import os
import platform
import random
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spike_lib import analysis, scrub
from spike_lib import selection as sel

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ALLOWLIST = REPO_ROOT / "src" / "truthtrail" / "data" / "seed_domains.txt"

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_AUTH = 3
EXIT_UNAVAILABLE = 4
EXIT_FAILED = 5

MAX_SECONDS_CAP = 7200
MAX_BYTES_CAP = 4 * 1024**3
SILENCE_SECONDS = 60.0
MAX_CONSECUTIVE_FAILURES = 8
BACKOFF_CAP_SECONDS = 60.0
APPVIEW_BASE = "https://public.api.bsky.app"
APPVIEW_SPACING_SECONDS = 1.1

V2_HOSTS = ("jetstream.us-east.bsky.network", "jetstream.us-west.bsky.network")
V1_HOSTS = ("jetstream2.us-east.bsky.network", "jetstream1.us-west.bsky.network")
V2_PATH = "/xrpc/network.bsky.jetstream.subscribeEvents"
V1_PATH = "/subscribe"
SUBPROTOCOL = "xrpc.v1.json"
USER_AGENT_BASE = "TruthTrail-spike/0.1 (+https://github.com/areveeess/TruthTrail)"
MAX_FRAME_BYTES = 2 * 1024 * 1024


class AuthStop(Exception):
    """HTTP 401 or 403 from the public service: stop, never retry, never substitute data."""


class Unavailable(Exception):
    """A required tool is missing (websockets or PostgreSQL binaries)."""


def user_agent() -> str:
    """The honest User-Agent: repository URL plus the optional operator contact."""
    contact = os.environ.get("COLLECTOR_CONTACT", "").strip()
    return f"{USER_AGENT_BASE} {contact}" if contact else USER_AGENT_BASE


# ----------------------------------------------------------------------------- dependencies


@dataclass
class Deps:
    """Injectable seams (connection factory, clock, sleep, HTTP): tests replace them."""

    connect: Callable[..., AbstractAsyncContextManager[Any]] | None = None
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    clock: Callable[[], float] = time.monotonic
    wall_ms: Callable[[], int] = lambda: int(time.time() * 1000)
    rng: Callable[[], float] = field(default_factory=lambda: random.SystemRandom().random)
    http_get: Callable[[str], tuple[int, bytes]] | None = None

    def get_connect(self) -> Callable[..., AbstractAsyncContextManager[Any]]:
        """The connection factory; imports websockets lazily and exits 4 when it is missing."""
        if self.connect is not None:
            return self.connect
        try:
            from websockets.asyncio.client import connect
        except ImportError as exc:
            raise Unavailable(
                "the websockets package is missing; run the tool with: uv run --no-project "
                "--python 3.13 --with websockets==17.2 python scripts/bluesky_spike.py ..."
            ) from exc
        return connect

    def get(self, url: str) -> tuple[int, bytes]:
        """HTTP GET returning (status, body); 4xx and 5xx are returned, not raised."""
        if self.http_get is not None:
            return self.http_get(url)
        request = urllib.request.Request(url, headers={"User-Agent": user_agent()})  # noqa: S310 - fixed https URLs
        try:
            with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - fixed https URLs
                return int(response.status), response.read(8 * 1024 * 1024)
        except urllib.error.HTTPError as exc:
            return int(exc.code), exc.read(65536)


def http_status(exc: BaseException) -> int | None:
    """HTTP status carried by a connection error (websockets, urllib or a test double)."""
    response = getattr(exc, "response", None)
    for candidate in (
        getattr(response, "status_code", None),
        getattr(exc, "status_code", None),
        getattr(exc, "status", None),
        getattr(exc, "code", None),
    ):
        if isinstance(candidate, int) and 100 <= candidate <= 599:
            return candidate
    return None


def close_code(exc: BaseException) -> int | None:
    """WebSocket close code carried by a ConnectionClosed (sent or received) or a double."""
    for holder in (getattr(exc, "sent", None), getattr(exc, "rcvd", None), exc):
        code = getattr(holder, "code", None)
        if isinstance(code, int) and 1000 <= code <= 4999:
            return code
    return None


def error_name(exc: BaseException) -> str:
    """The XRPC error name in an HTTP error body when there is one, else the class name."""
    body = getattr(getattr(exc, "response", None), "body", None)
    if isinstance(body, bytes | bytearray):
        try:
            data = json.loads(bytes(body))
            if isinstance(data, dict) and isinstance(data.get("error"), str):
                return str(data["error"])[:40]
        except ValueError:
            pass
    return type(exc).__name__


# ----------------------------------------------------------------------------- argparse types


def bounded_seconds(value: str) -> float:
    """argparse type: a positive number of seconds, at most 7200 (D-01)."""
    try:
        seconds = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a number: {value!r}") from exc
    if not 0 < seconds <= MAX_SECONDS_CAP:
        raise argparse.ArgumentTypeError(f"must be above 0 and at most {MAX_SECONDS_CAP}")
    return seconds


def bounded_bytes(value: str) -> int:
    """argparse type: a positive byte cap with a hard ceiling of 4 GiB."""
    try:
        count = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not an integer: {value!r}") from exc
    if not 0 < count <= MAX_BYTES_CAP:
        raise argparse.ArgumentTypeError(f"must be above 0 and at most {MAX_BYTES_CAP}")
    return count


def resolve_out(value: str) -> Path:
    """Resolve ``--out``; it must be (below) a directory named spike-output under the cwd."""
    cwd = Path.cwd().resolve()
    resolved = (cwd / value).resolve()
    try:
        relative = resolved.relative_to(cwd)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--out must be below the current directory") from exc
    if "spike-output" not in relative.parts:
        raise argparse.ArgumentTypeError(
            "--out must be or sit below a directory named spike-output"
        )
    return resolved


def resolve_fixture_out(value: str) -> Path:
    """``cut-fixture`` may also write the fixture directory itself (a directory named recorded)."""
    resolved = Path(value).resolve()
    if resolved.name == "recorded" or "spike-output" in resolved.parts:
        return resolved
    raise argparse.ArgumentTypeError(
        "--out must be a directory named recorded or below spike-output"
    )


# ----------------------------------------------------------------------------- URLs and streams


def build_url(
    host: str, dialect: str, cursor: int | str | None = None, extra: dict[str, str] | None = None
) -> str:
    """Subscription URL: v2 uses ``kinds`` and ``collections``, v1 ``wantedCollections``."""
    if dialect == "v2":
        query = [
            ("kinds", "commit"),
            ("kinds", "account"),
            ("kinds", "sync"),
            ("collections", sel.POST_COLLECTION),
            ("collections", sel.REPOST_COLLECTION),
            ("maxMessageSizeBytes", "1048576"),
        ]
        path = V2_PATH
    else:
        query = [
            ("wantedCollections", sel.POST_COLLECTION),
            ("wantedCollections", sel.REPOST_COLLECTION),
        ]
        path = V1_PATH
    if cursor is not None:
        query.append(("cursor", str(cursor)))
    for key, value in (extra or {}).items():
        query.append((key, value))
    return f"wss://{host}{path}?{urlencode(query)}"


def connect_kwargs(dialect: str, proxy: str | None) -> dict[str, Any]:
    """Keyword arguments for ``websockets.asyncio.client.connect`` (TLS verification stays on)."""
    kwargs: dict[str, Any] = {
        "open_timeout": 15,
        "max_size": MAX_FRAME_BYTES,
        "user_agent_header": user_agent(),
    }
    if dialect == "v2":
        kwargs["subprotocols"] = [SUBPROTOCOL]
    if proxy:
        kwargs["proxy"] = proxy
    return kwargs


def frame_time_us(text: str) -> int | None:
    """Stream time (microseconds) of a v2 or v1 frame; None for control frames."""
    try:
        obj = json.loads(text)
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    payload = obj.get("payload")
    if isinstance(payload, dict):
        return analysis.parse_time_us(payload.get("time") or payload.get("witnessedAt"))
    value = obj.get("time_us")
    return value if isinstance(value, int) else None


def frame_kind(text: str) -> str:
    """Kind of a frame for counting: commit, account, identity, sync, info, error or other."""
    try:
        obj = json.loads(text)
    except ValueError:
        return "other"
    if not isinstance(obj, dict):
        return "other"
    if obj.get("$type") == "error":
        return "error"
    payload = obj.get("payload")
    if isinstance(payload, dict):
        suffix = str(payload.get("$type", "")).rsplit("#", 1)[-1]
        return suffix if suffix in ("commit", "account", "identity", "sync", "info") else "other"
    kind = str(obj.get("kind", "other"))
    return kind if kind in ("commit", "account", "identity", "sync") else "other"


def frame_seq(text: str) -> int | None:
    """Jetstream ``seq`` of a v2 frame (None when absent)."""
    try:
        obj = json.loads(text)
        payload = obj.get("payload") if isinstance(obj, dict) else None
        seq = payload.get("seq") if isinstance(payload, dict) else None
    except ValueError:
        return None
    return seq if isinstance(seq, int) else None


def info_name(text: str) -> str | None:
    """Name of an ``#info`` frame (OutdatedCursor, FutureCursor, ...)."""
    try:
        obj = json.loads(text)
        payload = obj.get("payload") if isinstance(obj, dict) else None
    except ValueError:
        return None
    if isinstance(payload, dict) and str(payload.get("$type", "")).endswith("#info"):
        name = payload.get("name")
        return str(name)[:40] if isinstance(name, str) else "info"
    return None


def utc_iso(ms: int) -> str:
    """UTC ISO timestamp (seconds) from unix milliseconds."""
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def out(text: str = "") -> None:
    """Write one line to stdout (the tool prints counts and rates only)."""
    sys.stdout.write(text + "\n")


def err(text: str) -> None:
    """Write one line to stderr."""
    sys.stderr.write(text + "\n")


def git_sha() -> str:
    """Short git sha of the working tree (provenance for meta files)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607 - git on PATH, fixed arguments
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
            cwd=REPO_ROOT,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def websockets_version() -> str:
    """Installed websockets version, or ``missing``."""
    try:
        return importlib.metadata.version("websockets")
    except importlib.metadata.PackageNotFoundError:
        return "missing"


def save_sample(out_dir: Path, dialect: str, kind: str, text: str) -> None:
    """Keep one raw frame under the git-ignored output directory (scrubbed later by the cutter)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "samples.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"dialect": dialect, "kind": kind, "f": text}) + "\n")


# ----------------------------------------------------------------------------- reading a stream


@dataclass
class StreamSample:
    """What a bounded read of one connection saw (counts only)."""

    url_ok: bool = False
    handshake_s: float | None = None
    subprotocol: str | None = None
    frames: int = 0
    nbytes: int = 0
    elapsed: float = 0.0
    kinds: Counter[str] = field(default_factory=Counter)
    first_type: str | None = None
    first_time_us: int | None = None
    last_time_us: int | None = None
    first_seq: int | None = None
    last_seq: int | None = None
    seqs: list[tuple[int, int]] = field(default_factory=list)
    info: list[str] = field(default_factory=list)
    kept: list[tuple[str, str]] = field(default_factory=list)
    http_status: int | None = None
    error: str | None = None
    close: int | None = None


async def read_stream(
    deps: Deps,
    url: str,
    kwargs: dict[str, Any],
    *,
    seconds: float,
    max_bytes: int = 100 * 1024 * 1024,
    keep: tuple[str, ...] = (),
    collect_seqs: bool = False,
) -> StreamSample:
    """Read one connection for at most ``seconds`` or ``max_bytes``; 401/403 raise AuthStop."""
    sample = StreamSample()
    started = deps.clock()
    try:
        async with deps.get_connect()(url, **kwargs) as ws:
            sample.url_ok = True
            sample.handshake_s = deps.clock() - started
            sample.subprotocol = getattr(ws, "subprotocol", None)
            deadline = deps.clock() + seconds
            while sample.nbytes < max_bytes:
                remaining = deadline - deps.clock()
                if remaining <= 0:
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                except TimeoutError:
                    break
                text = raw if isinstance(raw, str) else bytes(raw).decode("utf-8", "replace")
                sample.frames += 1
                sample.nbytes += len(text.encode("utf-8"))
                kind = frame_kind(text)
                sample.kinds[kind] += 1
                if sample.first_type is None:
                    sample.first_type = kind
                name = info_name(text) if kind == "info" else None
                if name:
                    sample.info.append(name)
                    if "info" in keep:
                        sample.kept.append(("info", text))
                t = frame_time_us(text)
                if t is not None:
                    sample.first_time_us = sample.first_time_us or t
                    sample.last_time_us = t
                seq = frame_seq(text) if kind != "info" else None
                if seq is not None:
                    sample.first_seq = sample.first_seq or seq
                    sample.last_seq = seq
                    if collect_seqs and t is not None:
                        sample.seqs.append((seq, t))
                if kind in keep and not any(k == kind for k, _ in sample.kept):
                    sample.kept.append((kind, text))
    except Unavailable:
        raise
    except Exception as exc:
        status = http_status(exc)
        if status in (401, 403):
            raise AuthStop(f"HTTP {status} from the public service") from exc
        sample.http_status = status
        sample.error = error_name(exc)
        sample.close = close_code(exc)
    sample.elapsed = deps.clock() - started
    return sample


# ----------------------------------------------------------------------------- record


async def record_window(
    deps: Deps,
    *,
    host: str,
    dialect: str,
    seconds: float,
    max_bytes: int,
    label: str,
    out_dir: Path,
    proxy: str | None = None,
) -> tuple[int, dict[str, Any]]:
    """Record one bounded window to ``{label}.jsonl.gz``; returns (exit code, meta)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / f"{label}.jsonl.gz"
    started_ms = deps.wall_ms()
    deadline = deps.clock() + seconds
    frames = 0
    nbytes = 0
    reconnects = 0
    failures = 0
    last_us: int | None = None
    close_codes: Counter[str] = Counter()
    too_slow = 0
    stop: str | None = None
    exit_code = EXIT_OK
    kwargs = connect_kwargs(dialect, proxy)
    try:
        with gzip.open(raw_path, "wt", compresslevel=1, encoding="utf-8", newline="\n") as log:

            def control(event: str, detail: dict[str, Any]) -> None:
                log.write(json.dumps({"rx": deps.wall_ms(), "ev": event, "detail": detail}) + "\n")

            while stop is None:
                cursor = None if last_us is None else last_us - 5_000_000
                url = build_url(host, dialect, cursor)
                try:
                    async with deps.get_connect()(url, **kwargs) as ws:
                        control("connect", {"cursor": cursor})
                        while True:
                            remaining = deadline - deps.clock()
                            if remaining <= 0:
                                stop = "seconds"
                                break
                            try:
                                raw = await asyncio.wait_for(
                                    ws.recv(), timeout=min(SILENCE_SECONDS, remaining)
                                )
                            except TimeoutError:
                                if deps.clock() >= deadline:
                                    stop = "seconds"
                                    break
                                raise ConnectionError("silence") from None
                            text = (
                                raw
                                if isinstance(raw, str)
                                else bytes(raw).decode("utf-8", "replace")
                            )
                            failures = 0
                            frames += 1
                            nbytes += len(text.encode("utf-8"))
                            log.write(json.dumps({"rx": deps.wall_ms(), "f": text}) + "\n")
                            t = frame_time_us(text)
                            if t is not None:
                                last_us = t
                            elif (
                                text.startswith('{"$type":"error"')
                                and "ConsumerTooSlow" in text[:120]
                            ):
                                too_slow += 1
                            if nbytes >= max_bytes:
                                stop = "bytes"
                                break
                except asyncio.CancelledError:
                    stop = "interrupted"
                    raise
                except Unavailable:
                    stop = "unavailable"
                    raise
                except Exception as exc:
                    status = http_status(exc)
                    code = close_code(exc)
                    if code is not None:
                        close_codes[str(code)] += 1
                    control("error", {"class": type(exc).__name__, "status": status, "close": code})
                    if status in (401, 403):
                        stop, exit_code = "auth", EXIT_AUTH
                        err(f"stopped: HTTP {status}; no retry, no data substituted")
                    elif code == 1009:
                        stop, exit_code = "oversize_frame", EXIT_FAILED
                        err("stopped: close code 1009 (frame too large); a rewind would repeat it")
                    else:
                        failures += 1
                        reconnects += 1
                        if failures >= MAX_CONSECUTIVE_FAILURES:
                            stop, exit_code = "failures", EXIT_FAILED
                            err(f"stopped: {failures} consecutive failures")
                        else:
                            cap = min(BACKOFF_CAP_SECONDS, 2 ** (failures - 1))
                            await deps.sleep(
                                min(deps.rng() * cap, max(0.0, deadline - deps.clock()))
                            )
                            if deps.clock() >= deadline:
                                stop = "seconds"
                else:
                    if stop is None:  # the server closed the stream cleanly: reconnect
                        reconnects += 1
                        close_codes["clean"] += 1
                        await deps.sleep(1.0)
                        if deps.clock() >= deadline:
                            stop = "seconds"
            control("stop", {"reason": stop})
    finally:
        meta = {
            "label": label,
            "host": host,
            "dialect": dialect,
            "start_utc": utc_iso(started_ms),
            "end_utc": utc_iso(deps.wall_ms()),
            "bound_seconds": seconds,
            "max_bytes": max_bytes,
            "stop_reason": stop or "interrupted",
            "frames": frames,
            "bytes": nbytes,
            "reconnects": reconnects,
            "close_codes": dict(close_codes),
            "consumer_too_slow": too_slow,
            "tool_git_sha": git_sha(),
            "python": platform.python_version(),
            "websockets": websockets_version(),
            "user_agent": user_agent(),
        }
        (out_dir / f"{label}.meta.json").write_text(
            json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
    return exit_code, meta


# ----------------------------------------------------------------------------- commands


async def cmd_probe(args: argparse.Namespace, deps: Deps) -> int:
    """S-1 and S-12: four hosts, HTTPS status, upgrade, subprotocol, first frame, kinds honoured."""
    out_dir: Path = args.out
    rows = [
        "| host | dialect | https | upgrade | subprotocol | handshake_s | frames | commit | "
        "identity | account | first_frame | kinds_honoured |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for dialect, hosts in (("v2", V2_HOSTS), ("v1", V1_HOSTS)):
        for host in hosts:
            status, _body = deps.get(f"https://{host}/")
            if status in (401, 403):
                raise AuthStop(f"HTTP {status} from https://{host}/")
            extra = {"kinds": "commit"} if dialect == "v1" else None
            sample = await read_stream(
                deps,
                build_url(host, dialect, None, extra),
                connect_kwargs(dialect, args.proxy),
                seconds=args.seconds,
                keep=("commit",),
            )
            for kind, text in sample.kept:
                if kind == "commit":
                    save_sample(out_dir, dialect, "commit", text)
            honoured = (
                "yes"
                if sample.kinds["identity"] == 0 and sample.frames
                else ("n/a" if not sample.frames else "no")
            )
            upgrade = "ok" if sample.url_ok else f"fail:{sample.error}"
            rows.append(
                f"| {host} | {dialect} | {status} | {upgrade} | {sample.subprotocol or '-'} | "
                f"{sample.handshake_s or 0:.2f} | {sample.frames} | {sample.kinds['commit']} | "
                f"{sample.kinds['identity']} | {sample.kinds['account']} | "
                f"{sample.first_type or '-'} | {honoured} |"
            )
    out("\n".join(rows))
    return EXIT_OK


async def cmd_cursor_test(args: argparse.Namespace, deps: Deps) -> int:
    """S-3: timestamp cursors, a too-old cursor, seq 1 and a future seq."""
    out_dir: Path = args.out
    now_us = deps.wall_ms() * 1000
    cases: list[tuple[str, int, str]] = [
        ("now-10min", now_us - 600_000_000, "time"),
        ("now-2h", now_us - 7200_000_000, "time"),
        ("now-24h", now_us - 86_400_000_000, "time"),
        ("now-35h", now_us - 35 * 3600_000_000, "time"),
        ("now-37h", now_us - 37 * 3600_000_000, "time"),
        ("now-48h", now_us - 48 * 3600_000_000, "time"),
        ("seq=1", 1, "seq"),
        ("seq=900000000000000", 900_000_000_000_000, "seq"),
    ]
    out(
        "| cursor | result | first_event_minus_cursor_s | replay_events_per_s | "
        "info_frames | http |"
    )
    out("|---|---|---|---|---|---|")
    for name, value, kind in cases:
        sample = await read_stream(
            deps,
            build_url(args.host, "v2", value),
            connect_kwargs("v2", args.proxy),
            seconds=args.seconds,
            keep=("info",),
        )
        for _kind, text in sample.kept:
            save_sample(out_dir, "v2", "info", text)
        result = "accepted" if sample.url_ok else (sample.error or "failed")
        delta = ""
        if kind == "time" and sample.first_time_us is not None:
            delta = f"{(sample.first_time_us - value) / 1e6:.3f}"
        rate = f"{sample.frames / sample.elapsed:.0f}" if sample.elapsed and sample.frames else ""
        out(
            f"| {name} | {result} | {delta} | {rate} | "
            f"{','.join(sorted(set(sample.info))) or '-'} | {sample.http_status or '-'} |"
        )
    return EXIT_OK


async def cmd_reconnect_test(args: argparse.Namespace, deps: Deps) -> int:
    """S-11: deliberate disconnect and resume with a rewind, then a 90 s idle hold."""
    first = await read_stream(
        deps,
        build_url(args.host, "v2"),
        connect_kwargs("v2", args.proxy),
        seconds=args.seconds,
        collect_seqs=True,
    )
    if first.last_time_us is None:
        err("reconnect-test: no timed frame in the first read")
        return EXIT_FAILED
    rewind_us = 30_000_000
    cursor_us = first.last_time_us - rewind_us
    second = await read_stream(
        deps,
        build_url(args.host, "v2", cursor_us),
        connect_kwargs("v2", args.proxy),
        seconds=min(args.seconds, 10),
        collect_seqs=True,
    )
    seen = {seq for seq, _t in first.seqs}
    duplicates = sum(1 for seq, _t in second.seqs if seq in seen)
    expected = sum(1 for _seq, t in first.seqs if t >= cursor_us)
    out("| measure | value |")
    out("|---|---|")
    out(f"| first read frames | {first.frames} |")
    out("| resume cursor | last stream time minus 30 s |")
    out(f"| second read frames | {second.frames} |")
    out(f"| duplicates (seq seen in the first read) | {duplicates} |")
    out(f"| expected overlap (first-read frames with stream time >= cursor) | {expected} |")
    hold_url = f"wss://{args.host}{V2_PATH}?" + urlencode(
        [
            ("kinds", "commit"),
            ("collections", "org.user-intents.declaration"),
            ("maxMessageSizeBytes", "1048576"),
        ]
    )
    hold = await read_stream(
        deps, hold_url, connect_kwargs("v2", args.proxy), seconds=args.hold_seconds
    )
    out(f"| idle hold requested (s) | {args.hold_seconds} |")
    out(f"| idle hold elapsed (s) | {hold.elapsed:.1f} |")
    out(f"| idle hold frames (sparse filter) | {hold.frames} |")
    closed = hold.elapsed < args.hold_seconds - 1
    out(f"| closed by the server before the hold ended | {'yes' if closed else 'no'} |")
    out(f"| close code / error | {hold.close or '-'} / {hold.error or '-'} |")
    return EXIT_OK


def eligible_roots_for_appview(
    collector: analysis.Collector, min_age_s: float
) -> list[analysis.Cascade]:
    """Tracked roots with at least ``min_age_s`` of observation, in a fixed hash order."""
    eligible = [
        c for c in collector.all_tracked() if (c.window_end_us - c.time_us) / 1e6 >= min_age_s
    ]
    return sorted(eligible, key=lambda c: hashlib.sha256(c.uri.encode("utf-8")).hexdigest())


async def cmd_appview_check(args: argparse.Namespace, deps: Deps) -> int:
    """S-13: compare stream-reconstructed child counts with AppView getPosts counts."""
    refs = analysis.discover_logs(args.input, {args.label} if args.label else None)
    if not refs:
        err("appview-check: no raw log found")
        return EXIT_USAGE
    allowlist = analysis.load_allowlist(args.allowlist) if args.allowlist.exists() else []
    _results, collector, _stats = analysis.analyze_logs(refs, allowlist, keep_rows=True)
    roots = eligible_roots_for_appview(collector, 600.0)[: args.max_roots]
    stream_counts: dict[str, dict[str, int]] = {}
    for cas in roots:
        direct = {"reply": 0, "repost": 0, "quote": 0}
        for ev in cas.children:
            if ev.parent == cas.uri:
                direct[ev.kind] += 1
        stream_counts[cas.uri] = direct
    uris = list(stream_counts)
    pairs = {"reply": "replyCount", "repost": "repostCount", "quote": "quoteCount"}
    exact = Counter[str]()
    at_most = Counter[str]()
    hydrated = 0
    calls = 0
    for start in range(0, len(uris), 25):
        batch = uris[start : start + 25]
        url = f"{APPVIEW_BASE}/xrpc/app.bsky.feed.getPosts?" + urlencode(
            [("uris", u) for u in batch]
        )
        if calls:
            await deps.sleep(APPVIEW_SPACING_SECONDS)
        status, body = deps.get(url)
        calls += 1
        if status in (401, 403):
            raise AuthStop(f"HTTP {status} from the public AppView")
        if status != 200:
            err(f"appview-check: HTTP {status} on a batch; skipped")
            continue
        try:
            posts = json.loads(body).get("posts", [])
        except (ValueError, AttributeError):
            continue
        for post in posts:
            counts = stream_counts.get(post.get("uri"))
            if counts is None:
                continue
            hydrated += 1
            for kind, field_name in pairs.items():
                remote = post.get(field_name)
                if isinstance(remote, int):
                    exact[kind] += int(counts[kind] == remote)
                    at_most[kind] += int(counts[kind] <= remote)
    out("| measure | value |")
    out("|---|---|")
    out(f"| roots selected (observed >= 10 min) | {len(uris)} |")
    out(f"| AppView calls (25 URIs each, spaced >= 1.1 s) | {calls} |")
    out(f"| roots hydrated (others deleted or unavailable) | {hydrated} |")
    for kind in pairs:
        share_exact = f"{exact[kind] / hydrated:.3f}" if hydrated else "n/a"
        share_most = f"{at_most[kind] / hydrated:.3f}" if hydrated else "n/a"
        out(f"| {kind}: stream == AppView / stream <= AppView | {share_exact} / {share_most} |")
    return EXIT_OK


def load_allowlist_or_empty(path: Path) -> list[str]:
    """Allowlist entries, or an empty list when the draft file does not exist yet."""
    return analysis.load_allowlist(path) if path.exists() else []


def cmd_analyze(args: argparse.Namespace, _deps: Deps) -> int:
    """S-2, S-4, S-5, S-6, S-7, S-9 per window and combined, plus windows.json."""
    refs = analysis.discover_logs(args.input, {args.label} if args.label else None)
    if not refs:
        err("analyze: no raw log (*.jsonl.gz) found in the input directory")
        return EXIT_USAGE
    allowlist = load_allowlist_or_empty(args.allowlist)
    if args.domains_only:
        result = analysis.domains_only(refs, allowlist)
        out("| domain | posts | distinct authors |")
        out("|---|---|---|")
        for row in result["top_domains"]:
            out(f"| {row['domain']} | {row['posts']} | {row['authors']} |")
        return EXIT_OK
    results, _collector, _stats = analysis.analyze_logs(refs, allowlist)
    spans = analysis.window_spans(refs)
    analysis.ensure_no_identifiers(spans)
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "analysis.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (out_dir / "windows.json").write_text(
        json.dumps(spans, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    for label, window in {**results["windows"], "combined": results["combined"]}.items():
        (out_dir / f"summary-{label}.md").write_text(
            analysis.summary_markdown(window), encoding="utf-8", newline="\n"
        )
    if args.summary:
        out("## Windows")
        for span in spans:
            out(
                f"- {span['label']}: host={span['host']} "
                f"stream_seconds={span['stream_seconds']:.1f} "
                f"frames={span['frames']} bytes={span['bytes']} stop_reason={span['stop_reason']}"
            )
        out(f"- reader: {json.dumps(results['reader'], sort_keys=True)}")
        out()
        out(analysis.summary_markdown(results["combined"]))
    return EXIT_OK


def cmd_cut_fixture(args: argparse.Namespace, _deps: Deps) -> int:
    """Cut (or, with --check, re-cut and compare) the scrubbed real-data fixture."""
    refs = analysis.discover_logs(args.input)
    if not refs:
        err("cut-fixture: no raw log (*.jsonl.gz) found; the raw logs are deleted after the cut")
        return EXIT_USAGE
    allowlist = load_allowlist_or_empty(args.allowlist)
    if not allowlist:
        err("cut-fixture: the allowlist is empty or missing")
        return EXIT_USAGE
    _results, collector, _stats = analysis.analyze_logs(refs, allowlist, keep_rows=True)
    samples_path = args.samples or args.input.parent / "samples.jsonl"
    samples: list[dict[str, Any]] = []
    if samples_path.exists():
        for line in samples_path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict):
                samples.append(item)
    target = Path(tempfile.mkdtemp(prefix="tt-cut-")) if args.check else args.out
    try:
        manifest = scrub.cut(
            collector,
            allowlist=allowlist,
            out_dir=target,
            date=args.date,
            windows=analysis.window_spans(refs),
            samples=samples,
            max_bytes=args.max_bytes,
            min_children=args.min_children,
            small_sample=args.small_sample,
        )
        if args.check:
            same = True
            for entry in [*manifest["files"], {"name": f"bluesky-{args.date}.manifest.json"}]:
                committed = args.out / entry["name"]
                fresh = target / entry["name"]
                if not committed.exists() or committed.read_bytes() != fresh.read_bytes():
                    same = False
                    err(f"cut-fixture --check: {entry['name']} differs")
            out("cut-fixture --check: identical" if same else "cut-fixture --check: DIFFERENT")
            return EXIT_OK if same else EXIT_FAILED
    finally:
        if args.check:
            shutil.rmtree(target, ignore_errors=True)
    cov = manifest["coverage"]
    out(
        f"fixture: {sum(f['bytes'] for f in manifest['files'])} bytes, "
        f"trimmed={manifest['trimmed']}"
    )
    out(f"counts_by_kind: {json.dumps(manifest['counts_by_kind'], sort_keys=True)}")
    out(f"coverage: {json.dumps(cov, sort_keys=True)}")
    return EXIT_OK


# ----------------------------------------------------------------------------- storage probe


@dataclass
class PgBins:
    """Located PostgreSQL binaries and how to run them."""

    initdb: Path
    pg_ctl: Path
    psql: Path
    prefix: list[str]


def find_pg() -> PgBins:
    """Find initdb, pg_ctl and psql (TRUTHTRAIL_PG_BIN, the PATH, /usr/lib/postgresql/*/bin)."""
    candidates: list[Path] = []
    env = os.environ.get("TRUTHTRAIL_PG_BIN")
    if env:
        candidates.append(Path(env))
    for name in ("initdb", "pg_ctl"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found).parent)
    candidates.extend(sorted(Path("/usr/lib/postgresql").glob("*/bin"), reverse=True))
    for directory in candidates:
        initdb, pg_ctl = directory / "initdb", directory / "pg_ctl"
        if initdb.exists() and pg_ctl.exists():
            psql = directory / "psql"
            psql_path = psql if psql.exists() else Path(shutil.which("psql") or "")
            if not psql_path.name:
                continue
            prefix = (
                ["runuser", "-u", "postgres", "--"]
                if hasattr(os, "geteuid") and os.geteuid() == 0
                else []
            )
            return PgBins(initdb, pg_ctl, psql_path, prefix)
    raise Unavailable("PostgreSQL binaries (initdb, pg_ctl, psql) not found; set TRUTHTRAIL_PG_BIN")


def uri_key(secret: bytes, domain: bytes, value: str, length: int) -> str:
    """Throwaway keyed identifier (HMAC-SHA256, lowercase base32), as D-17 will store it."""
    digest = hmac.new(secret, domain + b"\0" + value.encode("utf-8"), hashlib.sha256).digest()
    return base64.b32encode(digest).decode("ascii").lower().rstrip("=")[:length]


SCRATCH_SCHEMA = """
-- Measurement scaffold only (D-01, S-8): NOT a schema, nothing here is committed or migrated.
CREATE TABLE accounts (id bigserial PRIMARY KEY, pseudonym text NOT NULL UNIQUE,
  first_observed_at timestamptz NOT NULL);
CREATE TABLE claims (id bigserial PRIMARY KEY,
  kind text NOT NULL CHECK (kind IN ('social_link', 'news_headline')), text text,
  text_hash text NOT NULL, url_canonical text, link_domain text, source_name text,
  published_at timestamptz, lang text, query_id int, created_at timestamptz NOT NULL);
CREATE UNIQUE INDEX claims_uq ON claims (kind, text_hash, coalesce(url_canonical, ''));
CREATE TABLE cascades (id bigserial PRIMARY KEY, root_uri text NOT NULL UNIQUE, claim_id bigint,
  tracking_ends_at timestamptz NOT NULL, first_event_at timestamptz, last_event_at timestamptz,
  event_count int, unique_accounts int, reply_count int, quote_count int, repost_count int,
  max_depth int, orphan_count int, disconnected_count int, deleted_count int,
  order_violation_count int, events_1h int, overflow_count int, root_deleted_at timestamptz,
  enrich_dirty boolean, rolled_up_at timestamptz, rollup_version int);
CREATE TABLE events (id bigserial PRIMARY KEY, uri text NOT NULL UNIQUE, edge_kind text NOT NULL,
  inferred boolean NOT NULL, parent_uri text, reply_root_uri text, quoted_uri text,
  parent_event_id bigint, parent_state text, cascade_id bigint, depth int, account_id bigint,
  observed_at timestamptz NOT NULL, occurred_at timestamptz, text text,
  text_purged_at timestamptz, claim_id bigint, lang text, deleted_at timestamptz);
CREATE INDEX events_cascade ON events (cascade_id, observed_at, uri);
CREATE INDEX events_orphans ON events (cascade_id) WHERE parent_state = 'orphan';
"""


def _ts(us: int | None) -> str:
    if us is None:
        return r"\N"
    return (datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=us)).isoformat()


def _record_text(frame: analysis.Frame) -> str:
    text = (frame.record or {}).get("text")
    return "x" * len(text) if isinstance(text, str) else ""


def _card_title_len(frame: analysis.Frame) -> int:
    embed = (frame.record or {}).get("embed")
    ext = embed.get("external") if isinstance(embed, dict) else None
    title = ext.get("title") if isinstance(ext, dict) else None
    return len(title) if isinstance(title, str) else 60


def tsv(*fields: object) -> str:
    """One COPY text row: tab-separated, None becomes the NULL marker."""
    return "\t".join(r"\N" if f is None else str(f) for f in fields)


def build_copy_blocks(collector: analysis.Collector, copies: int) -> dict[str, str]:
    """COPY text for the scratch tables: the recorded tracked rows replicated ``copies`` times."""
    secret = os.urandom(32)  # throwaway, held in memory only
    accounts: list[str] = []
    claims: list[str] = []
    cascades: list[str] = []
    events: list[str] = []

    def key(domain: bytes, value: str, length: int = 20) -> str:
        return uri_key(secret, domain, value, length)

    account_ids: dict[str, int] = {}
    claim_ids: dict[str, int] = {}

    def account_id(did: str | None, copy: int, first_us: int) -> int:
        name = f"{did}#{copy}"
        if name not in account_ids:
            account_ids[name] = len(account_ids) + 1
            accounts.append(tsv(key(b"acct", name, 16), _ts(first_us)))
        return account_ids[name]

    for copy in range(copies):
        for cas in collector.all_tracked():
            url = f"{cas.claim_url}#{copy}"
            if url not in claim_ids:
                claim_ids[url] = len(claim_ids) + 1
                title = "x" * _card_title_len(cas.root)
                claims.append(
                    tsv(
                        "social_link",
                        title,
                        key(b"claim", url, 16),
                        url,
                        cas.domain,
                        None,
                        None,
                        "en",
                        None,
                        _ts(cas.time_us),
                    )
                )
            cascade_id = len(cascades) + 1
            root_key = key(b"uri", f"{cas.uri}#{copy}")
            kinds = cas.kinds
            cascades.append(
                tsv(
                    root_key,
                    claim_ids[url],
                    _ts(cas.time_us + 48 * 3600 * 1_000_000),
                    _ts(cas.time_us),
                    _ts(cas.time_us),
                    cas.n_children + 1,
                    1,
                    kinds["reply"],
                    kinds["quote"],
                    kinds["repost"],
                    cas.max_depth,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    None,
                    "f",
                    None,
                    1,
                )
            )
            events.append(
                tsv(
                    root_key,
                    "root",
                    "f",
                    None,
                    None,
                    None,
                    None,
                    "none",
                    cascade_id,
                    0,
                    account_id(cas.root.did, copy, cas.time_us),
                    _ts(cas.time_us),
                    _ts(cas.time_us),
                    _record_text(cas.root),
                    None,
                    claim_ids[url],
                    "en",
                    None,
                )
            )
            for ev in cas.children:
                frame = ev.frame
                parent = key(b"uri", f"{ev.parent}#{copy}") if ev.parent else None
                events.append(
                    tsv(
                        key(b"uri", f"{frame.uri}#{copy}"),
                        ev.kind,
                        "t" if ev.kind == "repost" else "f",
                        parent,
                        root_key,
                        None,
                        None,
                        "orphan" if ev.orphan else "resolved",
                        cascade_id,
                        ev.depth,
                        account_id(frame.did, copy, frame.time_us or 0),
                        _ts(frame.time_us),
                        _ts(frame.time_us),
                        None,
                        None,
                        None,
                        None,
                        None,
                    )
                )
    return {
        "accounts": "\n".join(accounts),
        "claims": "\n".join(claims),
        "cascades": "\n".join(cascades),
        "events": "\n".join(events),
    }


COPY_COLUMNS = {
    "accounts": "pseudonym, first_observed_at",
    "claims": (
        "kind, text, text_hash, url_canonical, link_domain, source_name, published_at, lang, "
        "query_id, created_at"
    ),
    "cascades": (
        "root_uri, claim_id, tracking_ends_at, first_event_at, last_event_at, event_count, "
        "unique_accounts, reply_count, quote_count, repost_count, max_depth, orphan_count, "
        "disconnected_count, deleted_count, order_violation_count, events_1h, overflow_count, "
        "root_deleted_at, enrich_dirty, rolled_up_at, rollup_version"
    ),
    "events": (
        "uri, edge_kind, inferred, parent_uri, reply_root_uri, quoted_uri, parent_event_id, "
        "parent_state, cascade_id, depth, account_id, observed_at, occurred_at, text, "
        "text_purged_at, claim_id, lang, deleted_at"
    ),
}


def run_storage_probe(args: argparse.Namespace, _deps: Deps) -> int:
    """S-8: bytes per row in a throwaway local cluster and the days to fill the budget."""
    bins = find_pg()
    refs = analysis.discover_logs(args.input)
    if not refs:
        err("storage-probe: no raw log found")
        return EXIT_USAGE
    allowlist = load_allowlist_or_empty(args.allowlist)
    results, collector, _stats = analysis.analyze_logs(refs, allowlist, keep_rows=True)
    rows = sum(1 + len(c.children) for c in collector.all_tracked())
    if rows == 0:
        err("storage-probe: no tracked rows in the raw logs")
        return EXIT_FAILED
    copies = max(1, min(400, math.ceil(args.target_events / rows)))
    blocks = build_copy_blocks(collector, copies)
    base = Path(tempfile.mkdtemp(prefix="tt-pg-"))
    postgres_uid = None
    if bins.prefix:
        import pwd

        postgres_uid = pwd.getpwnam("postgres")
        os.chown(base, postgres_uid.pw_uid, postgres_uid.pw_gid)
    base.chmod(0o755)
    data, sock, port = base / "data", base / "sock", "55432"
    sock.mkdir()
    if postgres_uid is not None:
        os.chown(sock, postgres_uid.pw_uid, postgres_uid.pw_gid)

    def run(cmd: list[str], stdin: str | None = None) -> str:
        done = subprocess.run(  # noqa: S603 - fixed argument vector
            [*bins.prefix, *cmd],
            input=stdin,
            capture_output=True,
            text=True,
            check=True,
            timeout=900,
            cwd=base,
        )
        return done.stdout

    def psql(sql: str) -> str:
        return run(
            [
                str(bins.psql),
                "-X",
                "-q",
                "-A",
                "-t",
                "-v",
                "ON_ERROR_STOP=1",
                "-h",
                str(sock),
                "-p",
                port,
                "-U",
                "postgres",
                "-d",
                "postgres",
            ],
            sql,
        )

    started = False
    try:
        run(
            [
                str(bins.initdb),
                "-D",
                str(data),
                "-A",
                "trust",
                "-U",
                "postgres",
                "-E",
                "UTF8",
                "--locale=C",
                "--no-sync",
            ]
        )
        options = (
            f"-c listen_addresses='' -c unix_socket_directories={sock} -c port={port} -c fsync=off"
        )
        run(
            [
                str(bins.pg_ctl),
                "-D",
                str(data),
                "-o",
                options,
                "-w",
                "-l",
                str(base / "pg.log"),
                "start",
            ]
        )
        started = True
        psql(SCRATCH_SCHEMA)
        for table in ("accounts", "claims", "cascades", "events"):
            body = blocks[table]
            if body:
                psql(f"COPY {table} ({COPY_COLUMNS[table]}) FROM STDIN;\n{body}\n\\.\n")
        psql("ANALYZE;")
        sizes: dict[str, tuple[int, int]] = {}
        for table in ("accounts", "claims", "cascades", "events"):
            query = f"SELECT pg_total_relation_size('{table}'), count(*) FROM {table};"  # noqa: S608 - constant table names
            line = psql(query).strip()
            total, count = (int(x) for x in line.split("|"))
            sizes[table] = (total, count)
        report_storage(sizes, results["combined"], copies, rows, args.budget)
    finally:
        if started:
            subprocess.run(  # noqa: S603 - fixed argument vector
                [*bins.prefix, str(bins.pg_ctl), "-D", str(data), "-m", "immediate", "-w", "stop"],
                capture_output=True,
                check=False,
                timeout=120,
                cwd=base,
            )
        shutil.rmtree(base, ignore_errors=True)
    return EXIT_OK


def report_storage(
    sizes: dict[str, tuple[int, int]], combined: dict[str, Any], copies: int, rows: int, budget: int
) -> None:
    """Print measured bytes per row and the projection for each candidate bound set."""
    per = {t: (total / count if count else 0.0) for t, (total, count) in sizes.items()}
    out("| table | rows | total_bytes | bytes_per_row |")
    out("|---|---|---|---|")
    for table, (total, count) in sizes.items():
        out(f"| {table} | {count} | {total} | {per[table]:.1f} |")
    out(
        f"measurement scale: recorded tracked rows ({rows}) replicated {copies}x, "
        "identifiers re-keyed"
    )
    s5, s9 = combined["s5"], combined["s9"]
    roots = max(1, int(s5["eligible_roots"]))
    mean_children = s9["stored_children"] / roots
    shared = float(s9["roots_in_shared_url_groups_share"] or 0.0)
    per_root = (
        per["events"] * (1 + float(mean_children))
        + per["cascades"]
        + per["claims"] * (1 - shared / 2)
        + per["accounts"]
    )
    per_hour = float(s5["eligible_per_hour"] or 0.0)
    per_day = per_hour * 24
    out(
        f"all-in bytes per root (events x (1 + {float(mean_children):.2f} children) + cascade + "
        f"claim + account): {per_root:.0f}"
    )
    out(f"eligible roots per day (window-measured rate x 24): {per_day:.0f}")
    out(
        "| bound set | roots/day | retention_days | steady_state_MB | share_of_budget | "
        "days_to_fill_budget | days_to_fill_80pct |"
    )
    out("|---|---|---|---|---|---|---|")
    sets: list[tuple[str, float, int]] = [("cap 500 active / 48 h", min(per_day, 250.0), 90)]
    sets += [(f"all eligible, {d} d", per_day, d) for d in (7, 14, 30)]
    for k in (2, 4, 8, 16):
        sets += [(f"1-in-{k}, {d} d", per_day / k, d) for d in (30, 90)]
    for name, daily, retention in sets:
        grow = daily * per_root
        steady = grow * retention
        fill = budget / grow if grow else float("inf")
        out(
            f"| {name} | {daily:.0f} | {retention} | {steady / 1e6:.1f} | {steady / budget:.2f} | "
            f"{fill:.1f} | {0.8 * fill:.1f} |"
        )


# ----------------------------------------------------------------------------- main


def build_parser() -> argparse.ArgumentParser:
    """The argparse tree; every subcommand shares the caps and the ``--out`` rule."""
    parser = argparse.ArgumentParser(
        prog="bluesky_spike", description=__doc__.split("\n\n")[0] if __doc__ else ""
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser, *, out_default: str = "spike-output") -> None:
        p.add_argument("--out", type=resolve_out, default=resolve_out(out_default))
        p.add_argument(
            "--proxy", default=None, help="optional explicit proxy URL (default: environment)"
        )

    probe = sub.add_parser("probe", help="S-1/S-12: four hosts, upgrade, subprotocol, first frame")
    common(probe)
    probe.add_argument("--seconds", "--max-seconds", type=bounded_seconds, default=15.0)

    record = sub.add_parser("record", help="bounded raw-log recorder")
    common(record)
    record.add_argument("--host", default=V2_HOSTS[0])
    record.add_argument("--dialect", choices=("v2", "v1"), default="v2")
    record.add_argument("--seconds", "--max-seconds", type=bounded_seconds, required=True)
    record.add_argument("--max-bytes", type=bounded_bytes, default=800_000_000)
    record.add_argument("--label", default="window")

    cursor = sub.add_parser("cursor-test", help="S-3: cursor lookback and errors")
    common(cursor)
    cursor.add_argument("--host", default=V2_HOSTS[0])
    cursor.add_argument("--seconds", "--max-seconds", type=bounded_seconds, default=15.0)

    reconnect = sub.add_parser("reconnect-test", help="S-11: disconnect, resume, idle hold")
    common(reconnect)
    reconnect.add_argument("--host", default=V2_HOSTS[0])
    reconnect.add_argument("--seconds", "--max-seconds", type=bounded_seconds, default=20.0)
    reconnect.add_argument("--hold-seconds", type=bounded_seconds, default=90.0)

    appview = sub.add_parser("appview-check", help="S-13: compare child counts with getPosts")
    common(appview)
    appview.add_argument("--in", dest="input", type=Path, default=Path("spike-output/raw"))
    appview.add_argument("--label", default=None)
    appview.add_argument("--max-roots", type=int, default=100)
    appview.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)

    storage = sub.add_parser("storage-probe", help="S-8: bytes per row in a throwaway cluster")
    common(storage)
    storage.add_argument("--in", dest="input", type=Path, default=Path("spike-output/raw"))
    storage.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    storage.add_argument("--target-events", type=int, default=200_000)
    storage.add_argument("--budget", type=int, default=300_000_000)

    analyze = sub.add_parser("analyze", help="S-2/S-4/S-5/S-6/S-7/S-9 from the raw logs")
    common(analyze, out_default="spike-output/analysis")
    analyze.add_argument("--in", dest="input", type=Path, default=Path("spike-output"))
    analyze.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    analyze.add_argument("--domains-only", action="store_true")
    analyze.add_argument("--summary", action="store_true")
    analyze.add_argument("--label", default=None)

    cut = sub.add_parser("cut-fixture", help="scrub and cut the recorded real-data fixture")
    cut.add_argument("--in", dest="input", type=Path, default=Path("spike-output/raw"))
    cut.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    cut.add_argument(
        "--out",
        type=resolve_fixture_out,
        default=REPO_ROOT / "src" / "truthtrail" / "data" / "recorded",
    )
    cut.add_argument("--date", required=True)
    cut.add_argument("--max-bytes", type=int, default=1_500_000)
    cut.add_argument("--min-children", type=int, default=3)
    cut.add_argument("--small-sample", type=int, default=60)
    cut.add_argument("--samples", type=Path, default=None)
    cut.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None, deps: Deps | None = None) -> int:
    """Entry point; returns the documented exit code."""
    deps = deps or Deps()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else EXIT_USAGE
    try:
        if args.command == "record":
            code, meta = asyncio.run(
                record_window(
                    deps,
                    host=args.host,
                    dialect=args.dialect,
                    seconds=args.seconds,
                    max_bytes=args.max_bytes,
                    label=args.label,
                    out_dir=args.out,
                    proxy=args.proxy,
                )
            )
            out(
                f"record: label={meta['label']} stop_reason={meta['stop_reason']} "
                f"frames={meta['frames']} "
                f"bytes={meta['bytes']} reconnects={meta['reconnects']} exit={code}"
            )
            return code
        if args.command == "probe":
            return asyncio.run(cmd_probe(args, deps))
        if args.command == "cursor-test":
            return asyncio.run(cmd_cursor_test(args, deps))
        if args.command == "reconnect-test":
            return asyncio.run(cmd_reconnect_test(args, deps))
        if args.command == "appview-check":
            return asyncio.run(cmd_appview_check(args, deps))
        if args.command == "storage-probe":
            return run_storage_probe(args, deps)
        if args.command == "analyze":
            return cmd_analyze(args, deps)
        return cmd_cut_fixture(args, deps)
    except AuthStop as exc:
        err(f"stopped: {exc}; no retry, no data substituted (exit 3)")
        return EXIT_AUTH
    except Unavailable as exc:
        err(f"unavailable: {exc}")
        return EXIT_UNAVAILABLE
    except KeyboardInterrupt:
        err("interrupted")
        return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
