"""Event sources for the collector: the ``EventSource`` protocol and ``ReplaySource`` (D-04, D-11).

A source yields ``SourceItem`` values: a keyed, normalised result (or a control result) plus the
stream-time cursor in microseconds when the item carries stream time. ``mode`` is ``live`` or
``replay``. Replayed data is real recorded data, but not live: the run records ``replay`` and the
API surfaces it as ``source_mode``.

``ReplaySource`` reads the packaged recording through exactly the production dialect and
normaliser. Before it yields anything it checks that the manifest says ``source_mode`` is
``recorded-real`` and that the sha256 of the data file equals the manifest's ``files`` entry, and
it iterates the very bytes it hashed, so a file changed after the check cannot be replayed. Any
other file, including the Phase 1 demo fixture, raises ``ReplayRefused``. It never opens a
socket.

``JetstreamSource`` (D-05, D-06, D-07, D-09; RESEARCH Pattern 2, F-02, F-04, F-20) is the live
source and the only module that imports websockets. It owns connect, reconnect and backoff:
full-jitter exponential backoff from 1 to 60 s, at most 8 consecutive failures, 60 s of silence
is a dead connection, resume by the TIMESTAMP cursor of the last stream time minus the rewind
(never a per-instance seq, also on failover to the next host after two consecutive failures on
one host). HTTP 401 or 403 on the upgrade is fatal with no retry (no credential exists anywhere);
a close with code 1009 is an oversize frame and stops the run loudly instead of looping; an
in-band ``OutdatedCursor`` or an HTTP 400 ``CursorTooOld`` continues at the tip and yields a
``GapNotice``. TLS verification is websockets' default and is never overridden; proxy handling
is websockets' default unless a caller passes ``proxy`` (loopback tests pass ``None``).
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import json
import logging
import random
import time
from collections import Counter
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, aclosing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidStatus, WebSocketException
from websockets.typing import Subprotocol

from truthtrail.ingest.dialect import (
    AccountFrame,
    CommitFrame,
    Dialect,
    ErrorFrame,
    InfoFrame,
    SyncFrame,
    build_connect_url,
    classify_frame,
    resume_cursor,
    subprotocols,
)
from truthtrail.ingest.normalise import (
    AccountAction,
    DeleteEvent,
    Dropped,
    NormalizedEvent,
    normalise,
)
from truthtrail.ingest.pseudonym import Keyer

logger = logging.getLogger(__name__)

SourceMode = Literal["live", "replay"]


@dataclass(frozen=True, slots=True)
class GapNotice:
    """Data between ``from_us`` and ``to_us`` was not delivered (D-09); ``to_us`` None means the
    gap is closed by the stream time of the next event."""

    from_us: int | None
    to_us: int | None
    reason: str


SourceResult = NormalizedEvent | DeleteEvent | AccountAction | InfoFrame | ErrorFrame | GapNotice

RECORDED_REAL = "recorded-real"
REPLAY_HOST = "recorded"
REPLAY_DIALECT: Dialect = "v2"
MANIFEST_SUFFIX = ".manifest.json"
# The packaged recording (D-04): inside the package so the image can seed a demo by replay.
RECORDED_DIR = Path(__file__).resolve().parents[1] / "data" / "recorded"
DEFAULT_MANIFEST = RECORDED_DIR / "bluesky-2026-10-19.manifest.json"
_YIELD_EVERY = 256


class ReplayRefused(ValueError):
    """The file is not a recorded-real, hash-matching recording; the message is fixed text."""


@dataclass(frozen=True, slots=True)
class SourceItem:
    """One result of a source and its stream-time cursor (None for control results)."""

    result: SourceResult
    cursor_us: int | None


class DropCounter:
    """Counts the frames a source dropped, by stable reason (``Dropped.reason``)."""

    def __init__(self) -> None:
        self._counts: Counter[str] = Counter()

    def add(self, reason: str) -> None:
        self._counts[reason] += 1

    def as_dict(self) -> dict[str, int]:
        return dict(sorted(self._counts.items()))

    def total(self) -> int:
        return sum(self._counts.values())


class EventSource(Protocol):
    """A stream of keyed items; dropped frames go to the caller's ``DropCounter``, never out."""

    @property
    def mode(self) -> SourceMode: ...

    @property
    def dialect(self) -> Dialect: ...

    @property
    def host(self) -> str: ...

    def items(
        self, resume_cursor_us: int | None, drops: DropCounter | None = None
    ) -> AsyncIterator[SourceItem]: ...


def _stream_time(parsed: object) -> int | None:
    if isinstance(parsed, CommitFrame | AccountFrame | SyncFrame):
        return parsed.time_us
    return None


def _cursor_of(result: SourceResult) -> int | None:
    if isinstance(result, InfoFrame | ErrorFrame | GapNotice):
        return None
    return result.time_us


def _refuse(message: str) -> ReplayRefused:
    return ReplayRefused(message)


def _load_manifest(manifest_path: Path) -> Mapping[str, object]:
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise _refuse("replay refused: the manifest does not exist") from None
    except (OSError, UnicodeError, ValueError, RecursionError):
        raise _refuse("replay refused: the manifest is not readable JSON") from None
    if not isinstance(data, dict):
        raise _refuse("replay refused: the manifest is not a JSON object")
    return data


def _data_entry(manifest: Mapping[str, object], data_name: str) -> str:
    files = manifest.get("files")
    if not isinstance(files, list):
        raise _refuse("replay refused: the manifest has no files list")
    for entry in files:
        if isinstance(entry, dict) and entry.get("name") == data_name:
            digest = entry.get("sha256")
            if not isinstance(digest, str) or len(digest) != 64:
                raise _refuse("replay refused: the data file has no sha256 in the manifest")
            return digest
    raise _refuse("replay refused: the data file is not listed in the manifest")


class ReplaySource:
    """Replays a packaged recording through the production dialect and normaliser.

    Construction refuses (``ReplayRefused``) a manifest whose ``source_mode`` is not exactly
    ``recorded-real``, a manifest without the keys the guard needs, a missing data file and a
    data file whose sha256 differs from the manifest. Items come in file order; frames with a
    stream time before ``resume_cursor_us`` are skipped and frames at or after it are yielded
    (the cursor is inclusive, as on the live tail). A frame without stream time (a control or
    unparseable frame) keeps the position of the frame before it.
    """

    def __init__(self, manifest_path: Path | str, keyer: Keyer) -> None:
        path = Path(manifest_path)
        if not path.name.endswith(MANIFEST_SUFFIX):
            raise _refuse("replay refused: not a recording manifest")
        manifest = _load_manifest(path)
        if manifest.get("source_mode") != RECORDED_REAL:
            raise _refuse("replay refused: the manifest is not marked recorded-real")
        dialects = manifest.get("dialects")
        if dialects is not None and dialects != [REPLAY_DIALECT]:
            raise _refuse("replay refused: the recording is not in the v2 dialect")
        data_name = path.name.removesuffix(MANIFEST_SUFFIX) + ".jsonl"
        expected = _data_entry(manifest, data_name)
        data_path = path.with_name(data_name)
        try:
            data = data_path.read_bytes()
        except OSError:
            raise _refuse("replay refused: the data file does not exist") from None
        if hashlib.sha256(data).hexdigest() != expected:
            raise _refuse("replay refused: the data file does not match the manifest sha256")
        self._data = data
        self._keyer = keyer

    @property
    def mode(self) -> SourceMode:
        return "replay"

    @property
    def dialect(self) -> Dialect:
        return REPLAY_DIALECT

    @property
    def host(self) -> str:
        return REPLAY_HOST

    async def items(
        self, resume_cursor_us: int | None, drops: DropCounter | None = None
    ) -> AsyncIterator[SourceItem]:
        """Yield the recording's items in file order from ``resume_cursor_us`` (inclusive)."""
        reached = resume_cursor_us is None
        for index, raw_line in enumerate(self._data.split(b"\n")):
            if index and index % _YIELD_EVERY == 0:
                await asyncio.sleep(0)
            if not raw_line:
                continue
            parsed = classify_frame(raw_line, REPLAY_DIALECT)
            stream_us = _stream_time(parsed)
            if stream_us is not None and resume_cursor_us is not None:
                reached = stream_us >= resume_cursor_us
            if not reached:
                continue
            result = normalise(parsed, self._keyer)
            if isinstance(result, Dropped):
                if drops is not None:
                    drops.add(result.reason)
                continue
            yield SourceItem(result, _cursor_of(result))


# --- Live Jetstream source (D-05, D-06, D-07, D-09) ---------------------------------------------
REPOSITORY_URL = "https://github.com/areveeess/TruthTrail"
MAX_SIZE_BYTES = 2 * 1024 * 1024  # client bound, above the server's maxMessageSizeBytes (F-04)
MAX_QUEUE = 1024
OPEN_TIMEOUT_SECONDS = 10
SILENCE_SECONDS = 60.0
FAILURE_BUDGET = 8
BACKOFF_CAP_SECONDS = 60.0
FAILURES_BEFORE_FAILOVER = 2
CLOSE_MESSAGE_TOO_BIG = 1009
OUTDATED_CURSOR = "OutdatedCursor"
CURSOR_TOO_OLD = "CursorTooOld"
GAP_CURSOR_TOO_OLD = "cursor_too_old"
GAP_OUTDATED_CURSOR = "outdated_cursor"


class SourceError(RuntimeError):
    """Base of the live source's fatal errors; the message is a fixed reason, never a URL."""


class SourceForbidden(SourceError):
    """The service answered HTTP 401 or 403 on the upgrade: stop, never retry (D-07)."""


class SourceRejected(SourceError):
    """The service rejected the request (an HTTP 400 other than CursorTooOld)."""


class SourceFailed(SourceError):
    """The reconnect budget is spent, or a frame was too large (a poison loop otherwise)."""


class _Transient(Exception):
    """A connection ended for a reason a reconnect can cure; ``kind`` is a class-like name."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


ConnectFactory = Callable[..., AbstractAsyncContextManager[Any]]


def collector_version() -> str:
    try:
        return importlib.metadata.version("truthtrail")
    except importlib.metadata.PackageNotFoundError:  # pragma: no cover - source checkout
        return "0"


def user_agent(contact: str | None = None) -> str:
    """``TruthTrail/{version} (+repository; contact)``: no credential, no identifier (D-07)."""
    detail = f"+{REPOSITORY_URL}" + (f"; {contact}" if contact else "")
    return f"TruthTrail/{collector_version()} ({detail})"


def _error_name(body: object) -> str | None:
    """The JSON ``error`` name of an HTTP rejection body, or None."""
    if not isinstance(body, bytes | bytearray):
        return None
    try:
        data = json.loads(bytes(body).decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError):
        return None
    name = data.get("error") if isinstance(data, dict) else None
    return name if isinstance(name, str) else None


def _full_jitter(low: float, high: float) -> float:
    return random.uniform(low, high)  # noqa: S311 - jitter, not security


class JetstreamSource:
    """The live Jetstream source; see the module docstring for the failure model.

    ``connect``, ``sleep``, ``monotonic`` and ``jitter`` are seams for tests; ``base_urls`` maps a
    host to a ``ws://`` base URL and exists only so tests can point a host at a loopback server.
    """

    def __init__(
        self,
        hosts: Sequence[str],
        dialect: Dialect,
        keyer: Keyer,
        *,
        rewind_seconds: int,
        silence_seconds: float = SILENCE_SECONDS,
        failure_budget: int = FAILURE_BUDGET,
        contact: str | None = None,
        proxy: str | Literal[True] | None = True,
        connect: ConnectFactory | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        jitter: Callable[[float, float], float] = _full_jitter,
        base_urls: Mapping[str, str] | None = None,
    ) -> None:
        if not hosts:
            raise ValueError("at least one host is required")
        self._hosts = tuple(hosts)
        self._dialect: Dialect = dialect
        self._keyer = keyer
        self._rewind = rewind_seconds
        self._silence = silence_seconds
        self._budget = failure_budget
        self._contact = contact
        self._proxy = proxy
        self._connect: ConnectFactory = connect if connect is not None else connect_default
        self._sleep = sleep
        self._monotonic = monotonic
        self._jitter = jitter
        self._base_urls = dict(base_urls or {})
        self._host_index = 0

    @property
    def mode(self) -> SourceMode:
        return "live"

    @property
    def dialect(self) -> Dialect:
        return self._dialect

    @property
    def host(self) -> str:
        return self._hosts[self._host_index]

    def _url(self, host: str, cursor_us: int | None) -> str:
        url = build_connect_url(host, self._dialect, cursor_us=cursor_us)
        base = self._base_urls.get(host)
        if base is not None:  # tests only: same path and query on a loopback server
            url = base.rstrip("/") + url[len("wss://") + len(host) :]
        return url

    def _connect_kwargs(self) -> dict[str, Any]:
        return {
            "subprotocols": [Subprotocol(p) for p in subprotocols(self._dialect)] or None,
            "max_size": MAX_SIZE_BYTES,
            "max_queue": MAX_QUEUE,
            "open_timeout": OPEN_TIMEOUT_SECONDS,
            "user_agent_header": user_agent(self._contact),
            "proxy": self._proxy,
        }

    def backoff_delay(self, failures: int) -> float:
        """Full jitter: uniform(0, min(60, 2 ** (failures - 1))) seconds, so 1 s to 60 s caps."""
        return self._jitter(0.0, min(BACKOFF_CAP_SECONDS, float(2 ** (failures - 1))))

    async def items(
        self, resume_cursor_us: int | None, drops: DropCounter | None = None
    ) -> AsyncIterator[SourceItem]:
        """Yield keyed items from ``resume_cursor_us`` (None is the tip) until the consumer
        stops; raises ``SourceForbidden``, ``SourceRejected`` or ``SourceFailed``."""
        cursor = resume_cursor_us
        last_time: int | None = None
        failures = 0
        host_failures = 0
        while True:
            host = self.host
            delivered = False
            try:
                async with (
                    self._connect(self._url(host, cursor), **self._connect_kwargs()) as ws,
                    aclosing(self._read(ws, cursor, drops)) as frames,
                ):
                    async for item in frames:
                        if item.cursor_us is not None:
                            delivered = True
                            if last_time is None or item.cursor_us > last_time:
                                last_time = item.cursor_us
                        yield item
            except InvalidStatus as exc:
                status = exc.response.status_code
                if status in (401, 403):
                    raise SourceForbidden(f"http_{status}") from None
                if status == 400:
                    if cursor is not None and _error_name(exc.response.body) == CURSOR_TOO_OLD:
                        yield SourceItem(GapNotice(cursor, None, GAP_CURSOR_TOO_OLD), None)
                        cursor = None  # continue at the tip; the gap is recorded
                        continue
                    raise SourceRejected("http_400") from None
                kind = f"http_{status}"
            except ConnectionClosed as exc:
                # 1009 is sent by the client when a frame exceeds max_size (or echoed back)
                codes = {frame.code for frame in (exc.rcvd, exc.sent) if frame is not None}
                if CLOSE_MESSAGE_TOO_BIG in codes:
                    raise SourceFailed("oversize_frame") from None
                kind = type(exc).__name__
            except _Transient as exc:
                kind = exc.kind
            except (OSError, TimeoutError, WebSocketException) as exc:
                kind = type(exc).__name__
            else:  # pragma: no cover - a server-side clean end without a close frame
                kind = "ended"
            if delivered:
                failures = 0
                host_failures = 0
            failures += 1
            host_failures += 1
            logger.warning(
                "jetstream connection ended: attempt=%d error=%s host=%s", failures, kind, host
            )
            if failures >= self._budget:
                raise SourceFailed("reconnect_budget")
            if host_failures >= FAILURES_BEFORE_FAILOVER and len(self._hosts) > 1:
                self._host_index = (self._host_index + 1) % len(self._hosts)
                host_failures = 0
            if last_time is not None:
                cursor = resume_cursor(last_time, self._rewind)
            await self._sleep(self.backoff_delay(failures))

    async def _read(
        self, ws: ClientConnection, requested: int | None, drops: DropCounter | None
    ) -> AsyncGenerator[SourceItem]:
        """One connection: frames to items until the connection ends (raises on the end)."""
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), self._silence)
            except TimeoutError:
                raise _Transient("silence") from None
            parsed = classify_frame(raw, self._dialect)
            if isinstance(parsed, InfoFrame):
                yield SourceItem(parsed, None)
                if parsed.name == OUTDATED_CURSOR:
                    yield SourceItem(GapNotice(requested, None, GAP_OUTDATED_CURSOR), None)
                continue
            if isinstance(parsed, ErrorFrame):
                yield SourceItem(parsed, None)
                raise _Transient("error_frame")
            result = normalise(parsed, self._keyer)
            if isinstance(result, Dropped):
                if drops is not None:
                    drops.add(result.reason)
                continue
            yield SourceItem(result, _cursor_of(result))


def connect_default(uri: str, **kwargs: Any) -> AbstractAsyncContextManager[ClientConnection]:
    """websockets' client connect with its default TLS verification and proxy handling."""
    return connect(uri, **kwargs)
