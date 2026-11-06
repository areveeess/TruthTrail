"""Jetstream generation details, in one place (D-05, D-06; RESEARCH Pattern 1, F-02, F-03, F-04).

Nothing else in the code base knows the connect URL and its parameters, the subprotocol, the v2
envelope, ``time`` versus ``time_us``, ``witnessedAt``, ``seq`` versus ``cursor`` or the control
frames. ``classify_frame`` turns one text frame into a closed set of frozen results and never
raises: a frame that is not JSON, not an object, too large or of the wrong shape becomes a
``BadFrame`` with a stable reason, counted by the caller.

* v2 (``/xrpc/network.bsky.jetstream.subscribeEvents``, subprotocol ``xrpc.v1.json``): an
  envelope ``{"$type":"message","payload":{"$type":"...#commit|#account|#sync|#identity|#info"}}``
  or a terminal ``{"$type":"error","error":"ConsumerTooSlow"}``. Stream time is ``witnessedAt``
  when present (the portable resume position across instances, F-03), else ``time``.
* v1 (``/subscribe``, no subprotocol, ``kinds`` not honoured): a bare object with ``kind``,
  ``did``, ``time_us`` and the per-instance ``cursor``.

``#info`` frames (``OutdatedCursor``, ``FutureCursor``) carry no ``seq`` and no time, and an error
frame ends the connection: neither ever moves a cursor (F-02), so their result types have no
cursor field at all. Standard library only.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlencode

Dialect = Literal["v2", "v1"]
DIALECTS: tuple[Dialect, ...] = ("v2", "v1")

POST_COLLECTION = "app.bsky.feed.post"
REPOST_COLLECTION = "app.bsky.feed.repost"
# Named explicitly: no wildcard and no likes (D-06).
COLLECTIONS: tuple[str, ...] = (POST_COLLECTION, REPOST_COLLECTION)
# identity is not requested (handles are never stored); account and sync honour deletions (D-16).
KINDS: tuple[str, ...] = ("commit", "account", "sync")
# Below the client's 2 MiB max_size so the server skips giants instead of the client closing the
# connection on them (F-04: an oversize frame would otherwise be a poison loop on reconnect).
SERVER_MAX_MESSAGE_BYTES = 1_048_576
MAX_FRAME_BYTES = 2 * 1024 * 1024

V2_PATH = "/xrpc/network.bsky.jetstream.subscribeEvents"
V1_PATH = "/subscribe"
V2_SUBPROTOCOL = "xrpc.v1.json"
_V2_TYPE_PREFIX = "network.bsky.jetstream.subscribeEvents#"

OPERATIONS = frozenset({"create", "update", "delete"})
BAD_FRAME_REASONS = ("not_json", "not_object", "too_large", "bad_shape", "unknown_type")

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_ONE_US = timedelta(microseconds=1)
_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_HOSTNAME = re.compile(rf"(?=.{{1,253}}\Z){_LABEL}(?:\.{_LABEL})*")
_DID = re.compile(r"did:(?:plc|web):[A-Za-z0-9._%:-]{1,2048}")
_RKEY = re.compile(r"[A-Za-z0-9._~:-]{1,512}")
_COLLECTION = re.compile(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+){2,}")


@dataclass(frozen=True, slots=True)
class CommitFrame:
    """A commit on a record: the identity (did, collection, rkey), its operation and stream time."""

    did: str
    time_us: int
    seq: int | None
    operation: str
    collection: str
    rkey: str
    record: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class AccountFrame:
    """An account status change; only ``deleted`` and ``takendown`` are acted on (D-16, F-18)."""

    did: str
    status: str | None
    active: bool | None
    time_us: int


@dataclass(frozen=True, slots=True)
class SyncFrame:
    """A sync divergence marker: removes every record of the account (D-16)."""

    did: str
    time_us: int


@dataclass(frozen=True, slots=True)
class InfoFrame:
    """An in-band ``#info`` notice such as OutdatedCursor or FutureCursor; never moves a cursor."""

    name: str


@dataclass(frozen=True, slots=True)
class ErrorFrame:
    """A terminal error frame such as ConsumerTooSlow; the connection ends, the cursor stays."""

    error: str


@dataclass(frozen=True, slots=True)
class IgnoredFrame:
    """A well-formed frame of a kind this collector does not use (identity)."""

    kind: str


@dataclass(frozen=True, slots=True)
class BadFrame:
    """A frame that could not be used; ``reason`` is one of ``BAD_FRAME_REASONS``."""

    reason: str


ParsedFrame = (
    CommitFrame | AccountFrame | SyncFrame | InfoFrame | ErrorFrame | IgnoredFrame | BadFrame
)
StreamFrame = CommitFrame | AccountFrame | SyncFrame


def build_connect_url(
    host: str,
    dialect: Dialect,
    *,
    cursor_us: int | None = None,
    scheme: str = "wss",
) -> str:
    """Connect URL for a bare hostname; the cursor is a unix-microsecond timestamp when given.

    A value with a scheme, path, port, userinfo or whitespace is not a bare hostname and raises
    ``ValueError`` (the message never echoes it).
    """
    if not isinstance(host, str) or _HOSTNAME.fullmatch(host) is None:
        raise ValueError("host must be a bare hostname")
    if scheme not in ("wss", "ws"):
        raise ValueError("scheme must be wss or ws")
    if cursor_us is not None and (isinstance(cursor_us, bool) or cursor_us < 0):
        raise ValueError("cursor must be a non-negative integer")
    params: list[tuple[str, str]]
    if dialect == "v2":
        params = [("kinds", kind) for kind in KINDS]
        params += [("collections", collection) for collection in COLLECTIONS]
        params.append(("maxMessageSizeBytes", str(SERVER_MAX_MESSAGE_BYTES)))
        path = V2_PATH
    elif dialect == "v1":
        params = [("wantedCollections", collection) for collection in COLLECTIONS]
        params.append(("maxMessageSizeBytes", str(SERVER_MAX_MESSAGE_BYTES)))
        path = V1_PATH
    else:
        raise ValueError("unknown dialect")
    if cursor_us is not None:
        params.append(("cursor", str(int(cursor_us))))
    return f"{scheme}://{host}{path}?{urlencode(params)}"


def subprotocols(dialect: Dialect) -> tuple[str, ...]:
    """WebSocket subprotocols to offer: ``xrpc.v1.json`` for v2, none for v1."""
    if dialect == "v2":
        return (V2_SUBPROTOCOL,)
    if dialect == "v1":
        return ()
    raise ValueError("unknown dialect")


def parse_stream_time(text: str) -> int:
    """Exact unix microseconds of an aware ISO-8601 timestamp; a naive value raises ValueError.

    Integer arithmetic on (datetime minus epoch) divided by one microsecond, never a float.
    """
    if not isinstance(text, str):
        raise ValueError("timestamp must be a string")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must carry a time zone")
    return (parsed - _EPOCH) // _ONE_US


def datetime_from_us(us: int) -> datetime:
    """Aware UTC datetime of unix microseconds (exact)."""
    return _EPOCH + timedelta(microseconds=us)


def resume_cursor(checkpoint_us: int, rewind_seconds: int) -> int:
    """The cursor to resume from: the checkpoint minus the rewind, never negative (D-09)."""
    return max(0, checkpoint_us - rewind_seconds * 1_000_000)


def _mapping(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return {str(k): v for k, v in value.items()}
    return None


def _int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _str(value: object, pattern: re.Pattern[str] | None = None) -> str | None:
    if not isinstance(value, str):
        return None
    if pattern is not None and pattern.fullmatch(value) is None:
        return None
    return value


def _time_us_v2(payload: dict[str, object]) -> int | None:
    # F-03: witnessedAt is the portable position; time may be operator-overridden.
    for name in ("witnessedAt", "time"):
        value = payload.get(name)
        if value is None:
            continue
        try:
            return parse_stream_time(value) if isinstance(value, str) else None
        except ValueError:
            return None
    return None


def _time_us_v1(frame: dict[str, object]) -> int | None:
    value = _int(frame.get("time_us"))
    return value if value is not None and value >= 0 else None


def _commit(
    did: str | None,
    time_us: int | None,
    seq: int | None,
    body: dict[str, object] | None,
) -> ParsedFrame:
    if body is None or did is None or time_us is None:
        return BadFrame("bad_shape")
    operation = _str(body.get("operation"))
    collection = _str(body.get("collection"), _COLLECTION)
    rkey = _str(body.get("rkey"), _RKEY)
    if operation not in OPERATIONS or collection is None or rkey is None:
        return BadFrame("bad_shape")
    raw_record = body.get("record")
    record = _mapping(raw_record)
    if raw_record is not None and record is None:
        return BadFrame("bad_shape")
    if operation in ("create", "update") and record is None:
        return BadFrame("bad_shape")
    return CommitFrame(did, time_us, seq, operation, collection, rkey, record)


def _account(did: str | None, time_us: int | None, body: dict[str, object] | None) -> ParsedFrame:
    if body is None or did is None or time_us is None:
        return BadFrame("bad_shape")
    status = body.get("status")
    active = body.get("active")
    if (status is not None and not isinstance(status, str)) or (
        active is not None and not isinstance(active, bool)
    ):
        return BadFrame("bad_shape")
    return AccountFrame(did, status, active, time_us)


def _classify_v2(frame: dict[str, object]) -> ParsedFrame:
    outer = frame.get("$type")
    if outer == "error":
        name = frame.get("error")
        return ErrorFrame(name) if isinstance(name, str) else BadFrame("bad_shape")
    if outer != "message":
        return BadFrame("unknown_type")
    payload = _mapping(frame.get("payload"))
    if payload is None:
        return BadFrame("bad_shape")
    ptype = payload.get("$type")
    if not isinstance(ptype, str) or not ptype.startswith(_V2_TYPE_PREFIX):
        return BadFrame("unknown_type")
    kind = ptype.removeprefix(_V2_TYPE_PREFIX)
    if kind == "info":
        name = payload.get("name")
        return InfoFrame(name) if isinstance(name, str) else BadFrame("bad_shape")
    if kind == "identity":
        return IgnoredFrame("identity")
    if kind not in ("commit", "account", "sync"):
        return BadFrame("unknown_type")
    did = _str(payload.get("did"), _DID)
    time_us = _time_us_v2(payload)
    seq = _int(payload.get("seq"))
    if kind == "commit":
        return _commit(did, time_us, seq, payload)
    if kind == "account":
        return _account(did, time_us, _mapping(payload.get("account")))
    if did is None or time_us is None:
        return BadFrame("bad_shape")
    return SyncFrame(did, time_us)


def _classify_v1(frame: dict[str, object]) -> ParsedFrame:
    kind = frame.get("kind")
    if not isinstance(kind, str):
        return BadFrame("bad_shape")
    if kind == "identity":
        return IgnoredFrame("identity")
    if kind not in ("commit", "account", "sync"):
        return BadFrame("unknown_type")
    did = _str(frame.get("did"), _DID)
    time_us = _time_us_v1(frame)
    if kind == "commit":
        # v1's ``cursor`` is per instance (F-03); only time_us is portable, so seq stays None.
        return _commit(did, time_us, None, _mapping(frame.get("commit")))
    if kind == "account":
        return _account(did, time_us, _mapping(frame.get("account")))
    if did is None or time_us is None:
        return BadFrame("bad_shape")
    return SyncFrame(did, time_us)


def classify_frame(
    text: str | bytes, dialect: Dialect, *, max_bytes: int = MAX_FRAME_BYTES
) -> ParsedFrame:
    """Classify one text frame; never raises for any frame. The byte length is checked first.

    ``dialect`` is configuration, not input: an unknown value raises ``ValueError``.
    """
    if dialect not in DIALECTS:
        raise ValueError("unknown dialect")
    try:
        size = len(text) if isinstance(text, bytes) else len(text.encode("utf-8"))
    except (AttributeError, TypeError, UnicodeError):
        return BadFrame("not_json")
    if size > max_bytes:
        return BadFrame("too_large")
    try:
        frame = json.loads(text)
    except (ValueError, RecursionError, TypeError):
        return BadFrame("not_json")
    if not isinstance(frame, dict):
        return BadFrame("not_object")
    return _classify_v2(frame) if dialect == "v2" else _classify_v1(frame)
