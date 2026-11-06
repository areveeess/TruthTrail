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
socket. The live ``JetstreamSource`` (plan 03-05) implements the same protocol.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import Counter
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from truthtrail.ingest.dialect import (
    AccountFrame,
    CommitFrame,
    Dialect,
    ErrorFrame,
    InfoFrame,
    SyncFrame,
    classify_frame,
)
from truthtrail.ingest.normalise import (
    AccountAction,
    DeleteEvent,
    Dropped,
    NormalizedEvent,
    normalise,
)
from truthtrail.ingest.pseudonym import Keyer

SourceMode = Literal["live", "replay"]
SourceResult = NormalizedEvent | DeleteEvent | AccountAction | InfoFrame | ErrorFrame

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
    if isinstance(result, InfoFrame | ErrorFrame):
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
