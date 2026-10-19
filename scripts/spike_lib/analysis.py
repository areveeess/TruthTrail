"""Raw-log reader, one extraction pass and the S-n measurement functions (D-01, D-18).

The raw log (gzip, one JSON object per line) holds frames as ``{"rx": unix_ms, "f": frame_text}``
and control lines ``{"rx": ..., "ev": ..., "detail": ...}``. Every measurement is computed by ONE
pass (``Collector.feed``) so the analyzer, ``storage-probe`` and ``cut-fixture`` share the same
tracked-row pipeline. Results are counts, rates, percentiles and domain names only;
``ensure_no_identifiers`` is called before anything is written or printed.
"""

from __future__ import annotations

import bisect
import gzip
import hashlib
import json
import math
import re
from array import array
from collections import Counter
from collections.abc import Collection, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from spike_lib import selection as sel

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
ONE_US = timedelta(microseconds=1)
TTL_US = 48 * 3600 * 1_000_000
MAX_EVENTS_PER_CASCADE = 5000
MAX_ACTIVE_ROOTS = 500
KNOWN_STATUSES = frozenset(
    {"active", "deleted", "takendown", "deactivated", "suspended", "desynchronized", "throttled"}
)
KNOWN_INFO = frozenset({"OutdatedCursor", "FutureCursor"})
KNOWN_EMBEDS = {
    "app.bsky.embed.images": "images",
    "app.bsky.embed.video": "video",
    "app.bsky.embed.external": "external",
    "app.bsky.embed.record": "record",
    "app.bsky.embed.recordWithMedia": "recordWithMedia",
    "app.bsky.embed.gallery": "gallery",
}
SAMPLE_RATES = (10000, 5000, 2500, 1250, 625)
HORIZONS = (("15m", 900), ("1h", 3600), ("6h", 21600))
URL_RX = re.compile(r"https?://\S+|\b[\w.-]+\.(?:com|org|net|co|uk|ca|au)\S*", re.IGNORECASE)
WORD_RX = re.compile(r"[A-Za-z0-9]{2,}")
HANDLE_RX = re.compile(r"@[A-Za-z0-9_.-]+\.[A-Za-z]{2,}")


# ----------------------------------------------------------------------------- parsing


def parse_time_us(value: object) -> int | None:
    """Parse an ISO-8601 timestamp to unix microseconds (naive means UTC); None when invalid."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return (parsed - EPOCH) // ONE_US
    except (ValueError, OverflowError):
        return None


@dataclass(slots=True)
class Frame:
    """One parsed frame; ``obj`` is the full envelope and is only kept for tracked rows."""

    window: str
    host: str
    rx_ms: int
    size: int
    kind: str  # commit, account, identity, sync, info, error, other
    time_us: int | None
    seq: int | None
    order: int
    operation: str | None = None
    collection: str | None = None
    did: str | None = None
    rkey: str | None = None
    record: dict[str, Any] | None = None
    status: str | None = None
    info_name: str | None = None
    obj: dict[str, Any] | None = field(default=None, repr=False)

    @property
    def uri(self) -> str | None:
        """Raw at-URI of the record this commit frame touches."""
        if self.did and self.collection and self.rkey:
            return f"at://{self.did}/{self.collection}/{self.rkey}"
        return None


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def parse_frame(text: str, *, window: str, host: str, rx_ms: int, order: int) -> Frame | None:
    """Parse a v2 (envelope) or v1 (legacy wire) frame; None when it is not a JSON object."""
    try:
        obj = json.loads(text)
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    size = len(text.encode("utf-8"))
    payload = obj.get("payload")
    if obj.get("$type") == "message" and isinstance(payload, dict):
        suffix = str(payload.get("$type", "")).rsplit("#", 1)[-1]
        kind = suffix if suffix in ("commit", "account", "identity", "sync", "info") else "other"
        frame = Frame(
            window,
            host,
            rx_ms,
            size,
            kind,
            parse_time_us(payload.get("time") or payload.get("witnessedAt")),
            _int_or_none(payload.get("seq")),
            order,
            obj=obj,
        )
        frame.did = payload.get("did") if isinstance(payload.get("did"), str) else None
        if kind == "commit":
            frame.operation = str(payload.get("operation"))
            frame.collection = str(payload.get("collection"))
            frame.rkey = payload.get("rkey") if isinstance(payload.get("rkey"), str) else None
            rec = payload.get("record")
            frame.record = rec if isinstance(rec, dict) else None
        elif kind == "account":
            acct = payload.get("account")
            status = acct.get("status") if isinstance(acct, dict) else None
            active = acct.get("active") if isinstance(acct, dict) else None
            frame.status = status if isinstance(status, str) else ("active" if active else "other")
        elif kind == "info":
            name = payload.get("name")
            frame.info_name = name if isinstance(name, str) else "other"
        return frame
    if obj.get("$type") == "error":
        return Frame(window, host, rx_ms, size, "error", None, None, order, obj=obj)
    if "kind" in obj and "time_us" in obj:  # v1 legacy wire
        kind = str(obj.get("kind"))
        frame = Frame(
            window,
            host,
            rx_ms,
            size,
            kind if kind in ("commit", "account", "identity", "sync") else "other",
            (_int_or_none(obj.get("time_us"))),
            _int_or_none(obj.get("cursor")),
            order,
            obj=obj,
        )
        frame.did = obj.get("did") if isinstance(obj.get("did"), str) else None
        commit = obj.get("commit")
        if frame.kind == "commit" and isinstance(commit, dict):
            frame.operation = str(commit.get("operation"))
            frame.collection = str(commit.get("collection"))
            frame.rkey = commit.get("rkey") if isinstance(commit.get("rkey"), str) else None
            rec = commit.get("record")
            frame.record = rec if isinstance(rec, dict) else None
        return frame
    return None


@dataclass(frozen=True, slots=True)
class LogRef:
    """A recorded window: label, raw log path and its meta file."""

    label: str
    path: Path
    meta_path: Path


def discover_logs(raw_dir: Path, labels: Collection[str] | None = None) -> list[LogRef]:
    """Find ``*.jsonl.gz`` raw logs (optionally only some labels), ordered by label."""
    refs = []
    for path in sorted(raw_dir.glob("*.jsonl.gz")):
        label = path.name[: -len(".jsonl.gz")]
        if labels is None or label in labels:
            refs.append(LogRef(label, path, raw_dir / f"{label}.meta.json"))
    return refs


def read_meta(ref: LogRef) -> dict[str, Any]:
    """Read the recorder's meta file (empty dict when absent or unreadable)."""
    try:
        data = json.loads(ref.meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def iter_lines(path: Path, stats: Counter[str] | None = None) -> Iterator[tuple[int, str | None]]:
    """Yield (rx_ms, frame_text) for frame lines; malformed and control lines are only counted."""
    with gzip.open(path, "rt", encoding="utf-8", newline="\n") as handle:
        try:
            for line in handle:
                try:
                    item = json.loads(line)
                except ValueError:
                    if stats is not None:
                        stats["malformed_lines"] += 1
                    continue
                if not isinstance(item, dict) or not isinstance(item.get("rx"), int):
                    if stats is not None:
                        stats["malformed_lines"] += 1
                    continue
                frame_text = item.get("f")
                if isinstance(frame_text, str):
                    yield item["rx"], frame_text
                elif stats is not None:
                    stats["control_lines"] += 1
        except EOFError:  # a log that is still being written (or was killed) ends mid-stream
            if stats is not None:
                stats["truncated_log"] += 1


def iter_frames(refs: Iterable[LogRef], stats: Counter[str] | None = None) -> Iterator[Frame]:
    """Yield frames of every log in order, deduplicating commit frames on (host, seq)."""
    order = 0
    for ref in refs:
        meta = read_meta(ref)
        host = str(meta.get("host", "unknown"))
        seen: set[tuple[str, int]] = set()
        for rx_ms, text in iter_lines(ref.path, stats):
            frame = parse_frame(text, window=ref.label, host=host, rx_ms=rx_ms, order=order)
            if frame is None:
                if stats is not None:
                    stats["unparseable_frames"] += 1
                continue
            if frame.kind == "commit" and frame.seq is not None:
                key = (host, frame.seq)
                if key in seen:
                    if stats is not None:
                        stats["duplicate_frames"] += 1
                    continue
                seen.add(key)
            order += 1
            yield frame


def load_allowlist(path: Path) -> list[str]:
    """Read ``domain  # category`` lines (comments and blanks skipped, lowercased)."""
    domains: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = line.split("#", 1)[0].strip().lower()
        if entry:
            domains.append(entry)
    return domains


def sha256_file(path: Path) -> str:
    """Hex sha256 of a file, streamed."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def window_spans(refs: Iterable[LogRef]) -> list[dict[str, Any]]:
    """Per raw log: label, host, dialect, first and last stream time, frames, bytes, hash."""
    spans = []
    for ref in refs:
        meta = read_meta(ref)
        first: int | None = None
        last: int | None = None
        frames = 0
        nbytes = 0
        for frame in iter_frames([ref]):
            frames += 1
            nbytes += frame.size
            if frame.time_us is not None:
                first = frame.time_us if first is None else min(first, frame.time_us)
                last = frame.time_us if last is None else max(last, frame.time_us)
        spans.append(
            {
                "label": ref.label,
                "host": str(meta.get("host", "unknown")),
                "dialect": str(meta.get("dialect", "v2")),
                "first_us": first,
                "last_us": last,
                "stream_seconds": 0.0 if first is None or last is None else (last - first) / 1e6,
                "frames": frames,
                "bytes": nbytes,
                "bound_seconds": meta.get("bound_seconds"),
                "max_bytes": meta.get("max_bytes"),
                "stop_reason": meta.get("stop_reason"),
                "raw_sha256": sha256_file(ref.path),
                "raw_bytes": ref.path.stat().st_size,
            }
        )
    return spans


# ----------------------------------------------------------------------------- helpers


def pct(sorted_values: list[float] | list[int], p: float) -> float | None:
    """Nearest-rank percentile of a sorted list; None when empty."""
    if not sorted_values:
        return None
    idx = max(0, min(len(sorted_values) - 1, math.ceil(p / 100 * len(sorted_values)) - 1))
    return float(sorted_values[idx])


def _round(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def _share(num: int, den: int) -> float | None:
    return None if den == 0 else round(num / den, 4)


def ensure_no_identifiers(obj: object) -> None:
    """Raise ValueError when any string inside ``obj`` holds a DID, an at-URI or a handle."""
    if isinstance(obj, str):
        if "did:" in obj or "at://" in obj or HANDLE_RX.search(obj):
            raise ValueError("identifier-like string in analysis output")
    elif isinstance(obj, dict):
        for key, value in obj.items():
            ensure_no_identifiers(str(key))
            ensure_no_identifiers(value)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for value in obj:
            ensure_no_identifiers(value)


def _embed_record_uri(record: dict[str, Any]) -> str | None:
    embed = record.get("embed")
    if not isinstance(embed, dict):
        return None
    inner: Any = None
    if embed.get("$type") == sel.EMBED_RECORD:
        inner = embed.get("record")
    elif embed.get("$type") == sel.EMBED_RECORD_WITH_MEDIA:
        outer = embed.get("record")
        inner = outer.get("record") if isinstance(outer, dict) else None
    uri = inner.get("uri") if isinstance(inner, dict) else None
    return uri if isinstance(uri, str) else None


def _embed_name(record: dict[str, Any]) -> str:
    embed = record.get("embed")
    if not isinstance(embed, dict):
        return "none"
    etype = embed.get("$type")
    return KNOWN_EMBEDS.get(etype, "other") if isinstance(etype, str) else "other"


def has_commentary(record: dict[str, Any]) -> bool:
    """True when the post text holds words besides links (the text itself is never kept)."""
    text = record.get("text")
    return isinstance(text, str) and WORD_RX.search(URL_RX.sub(" ", text)) is not None


class BoundedPick:
    """Keep the ``limit`` frames with the smallest sha256 key: deterministic, no ``random``."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.items: list[tuple[str, int, Frame]] = []

    def offer(self, key_source: str, frame: Frame) -> None:
        """Offer a frame; the hash of ``key_source`` orders the pick."""
        key = hashlib.sha256(key_source.encode("utf-8")).hexdigest()
        entry = (key, frame.order, frame)
        if len(self.items) < self.limit:
            bisect.insort(self.items, entry, key=lambda e: (e[0], e[1]))
        elif (key, frame.order) < (self.items[-1][0], self.items[-1][1]):
            bisect.insort(self.items, entry, key=lambda e: (e[0], e[1]))
            self.items.pop()

    def frames(self) -> list[Frame]:
        """Picked frames in hash order."""
        return [item[2] for item in self.items]


@dataclass(slots=True)
class TrackedEvent:
    """A stored child event (reply, quote or repost) of a tracked cascade."""

    frame: Frame
    kind: str
    depth: int | None
    orphan: bool
    parent: str | None = None


@dataclass(slots=True)
class Cascade:
    """One tracked root and what was stored under it in the recorded window."""

    root: Frame
    uri: str
    time_us: int
    domain: str
    claim_url: str
    bucket: int
    author: int
    window_end_us: int = 0
    children: list[TrackedEvent] = field(default_factory=list)
    n_children: int = 0
    kinds: Counter[str] = field(default_factory=Counter)
    first_us: dict[str, int] = field(default_factory=dict)
    overflow: int = 0
    max_depth: int = 0
    deletes: list[Frame] = field(default_factory=list)

    def note_child(self, kind: str, time_us: int) -> None:
        """Account one stored child."""
        self.n_children += 1
        self.kinds[kind] += 1
        for key in (kind, "any"):
            if key not in self.first_us or time_us < self.first_us[key]:
                self.first_us[key] = time_us


@dataclass(frozen=True, slots=True)
class TrackedRow:
    """A row of the shared pipeline: root, child or delete of a tracked cascade."""

    kind: str  # root, child, delete
    frame: Frame
    cascade_index: int
    depth: int | None = None
    orphan: bool = False
    edge_kind: str | None = None


class Collector:
    """Single-pass accumulator for S-2, S-4, S-5, S-6, S-7 and S-9 plus the tracked rows."""

    def __init__(self, allowlist: Collection[str], *, label: str, keep_rows: bool = False) -> None:
        self.allowlist = frozenset(allowlist)
        self.label = label
        self.keep_rows = keep_rows
        self.counts: Counter[str] = Counter()
        self.sizes: array[int] = array("I")
        self.per_second: Counter[int] = Counter()
        self.spans: list[tuple[int, int]] = []
        self.cur_first: int | None = None
        self.cur_last: int | None = None
        self.max_t = 0
        self.inversions = 0
        self.largest_inversion_us = 0
        self.last_seq: dict[str, int] = {}
        self.seq_backwards = 0
        self.skew: array[float] = array("d")
        self.skew_future = 0
        self.skew_old_1h = 0
        self.skew_absurd = 0
        self.created_us: dict[int, int] = {}
        self.repost_subject: dict[int, int] = {}
        self.pair_both = 0
        self.pair_child_first = 0
        self.post_shapes: Counter[str] = Counter()
        self.embeds: Counter[str] = Counter()
        self.unknown_embed_names: set[str] = set()
        self.link_sources: Counter[str] = Counter()
        self.shortener_posts = 0
        self.reposts: Counter[str] = Counter()
        self.quote_nonpost = 0
        self.reply_quote = 0
        self.did_web_authors = 0
        self.did_web_targets = 0
        self.deletes: Counter[str] = Counter()
        self.delete_latency: dict[str, list[float]] = {"post": [], "root": [], "child": []}
        self.accounts: Counter[str] = Counter()
        self.unknown_statuses: set[str] = set()
        self.syncs = 0
        self.infos: Counter[str] = Counter()
        self.other_frames = 0
        self.decisions: Counter[str] = Counter()
        self.cand = Counter[str]()
        self.domain_roots: Counter[str] = Counter()
        self.domain_authors: dict[str, set[int]] = {}
        self.link_domains: Counter[str] = Counter()
        self.link_domain_authors: dict[str, set[int]] = {}
        self.eligible_times: list[int] = []
        self.eligible_buckets: list[int] = []
        self.eligible_authors: set[int] = set()
        self.claim_groups: Counter[str] = Counter()
        self.quote_seed_eligible = 0
        self.cross_cascade_children = 0
        self.stored_children = 0
        self.orphans = 0
        self.depth_counts: Counter[str] = Counter()
        self.cascades: list[Cascade] = []
        self.finished: list[Cascade] = []
        self.stored: dict[str, tuple[Cascade, int | None, str]] = {}
        self.roots: dict[str, Cascade] = {}
        self.refs: Counter[tuple[int, int]] = Counter()
        self.c_buckets: list[tuple[int, Counter[int]]] = []
        self.window_first_us: int | None = None
        self.cutter_picks = _make_picks() if keep_rows else {}
        self.all_cascades: list[Cascade] = []
        self.events_before_root = 0
        self.late_children = 0
        self.dropped_overflow = 0
        self.dropped_ttl = 0
        self.cap_fill_us: list[int | None] = []
        self.cur_roots_eligible = 0
        self.cur_cap_fill: int | None = None
        self.windows_seen = 0

    # ------------------------------------------------------------------ window management

    def new_window(self) -> None:
        """Close the current window: freeze its span and cascades, reset per-window state."""
        if self.cur_first is not None and self.cur_last is not None:
            self.spans.append((self.cur_first, self.cur_last))
            for cas in self.cascades:
                cas.window_end_us = self.cur_last
            self._close_refs()
        self.all_cascades.extend(self.cascades)
        self.cap_fill_us.append(self.cur_cap_fill)
        self.cascades = []
        self.stored = {}
        self.roots = {}
        self.created_us = {}
        self.repost_subject = {}
        self.cur_first = None
        self.cur_last = None
        self.max_t = 0
        self.last_seq = {}
        self.cur_roots_eligible = 0
        self.cur_cap_fill = None
        self.windows_seen += 1

    def _close_refs(self) -> None:
        first = self.cur_first or 0
        last = self.cur_last or 0
        full = (last - first) // 3_600_000_000
        by_bucket: dict[int, Counter[int]] = {}
        for (bucket, subject), n in self.refs.items():
            by_bucket.setdefault(bucket, Counter())[subject] = n
        use = [b for b in by_bucket if b < full] or ([0] if by_bucket else [])
        width = 3600 if full >= 1 else max(1, (last - first) // 1_000_000)
        for bucket in use:
            self.c_buckets.append((width, by_bucket[bucket]))
        self.refs = Counter()

    # ------------------------------------------------------------------ feed

    def feed(self, frame: Frame) -> None:
        """Consume one frame (already deduplicated)."""
        self.sizes.append(frame.size)
        t = frame.time_us
        if t is not None:
            self.cur_first = t if self.cur_first is None else min(self.cur_first, t)
            self.cur_last = t if self.cur_last is None else max(self.cur_last, t)
            if self.window_first_us is None:
                self.window_first_us = t
            self.per_second[t // 1_000_000] += 1
            if t < self.max_t:
                self.inversions += 1
                self.largest_inversion_us = max(self.largest_inversion_us, self.max_t - t)
            else:
                self.max_t = t
        if frame.seq is not None and frame.kind == "commit":
            previous = self.last_seq.get(frame.host)
            if previous is not None and frame.seq < previous:
                self.seq_backwards += 1
            self.last_seq[frame.host] = frame.seq
        if frame.kind == "commit":
            self.counts[f"commit/{frame.operation}/{frame.collection}"] += 1
            self._commit(frame)
        elif frame.kind == "account":
            self.counts["account"] += 1
            status = frame.status or "other"
            if status in KNOWN_STATUSES:
                self.accounts[status] += 1
            else:
                self.accounts["other"] += 1
                self.unknown_statuses.add(hashlib.sha256(status.encode()).hexdigest()[:8])
            if self.keep_rows and status in ("deleted", "takendown", "active", "deactivated"):
                self.cutter_picks["acct:" + status].offer(f"{frame.host}:{frame.seq}", frame)
            elif self.keep_rows:
                self.cutter_picks["acct:other"].offer(f"{frame.host}:{frame.seq}", frame)
        elif frame.kind == "sync":
            self.counts["sync"] += 1
            self.syncs += 1
            if self.keep_rows:
                self.cutter_picks["sync"].offer(f"{frame.host}:{frame.seq}", frame)
        elif frame.kind == "identity":
            self.counts["identity"] += 1
        elif frame.kind == "info":
            self.counts["info"] += 1
            name = frame.info_name or "other"
            self.infos[name if name in KNOWN_INFO else "other"] += 1
        else:
            self.other_frames += 1

    # ------------------------------------------------------------------ commits

    def _commit(self, frame: Frame) -> None:
        coll = frame.collection
        if coll not in (sel.POST_COLLECTION, sel.REPOST_COLLECTION):
            self.other_frames += 1
            return
        uri = frame.uri
        if uri is None:
            self.other_frames += 1
            return
        if frame.operation == "delete":
            self._delete(frame, uri)
        elif frame.operation == "create" and frame.record is not None:
            if frame.did and frame.did.startswith("did:web:"):
                self.did_web_authors += 1
            self.created_us[hash(uri)] = frame.time_us or 0
            if coll == sel.POST_COLLECTION:
                self._post(frame, uri, frame.record)
            else:
                self._repost(frame, uri, frame.record)
        # updates and records without a body are counted in ``counts`` only

    def _skew(self, frame: Frame, record: dict[str, Any]) -> None:
        created = parse_time_us(record.get("createdAt"))
        if created is None or frame.time_us is None:
            self.skew_absurd += 1
            return
        delta = (created - frame.time_us) / 1e6
        if created < 0 or created > frame.time_us + 366 * 86_400 * 1_000_000:
            self.skew_absurd += 1
            return
        self.skew.append(delta)
        if delta > 60:
            self.skew_future += 1
        if delta < -3600:
            self.skew_old_1h += 1

    def _post(self, frame: Frame, uri: str, record: dict[str, Any]) -> None:
        self._skew(frame, record)
        edge = sel.derive_edge(sel.POST_COLLECTION, record)
        embed = _embed_name(record)
        self.embeds[embed] += 1
        if embed == "other":
            etype = (
                record.get("embed", {}).get("$type")
                if isinstance(record.get("embed"), dict)
                else None
            )
            if isinstance(etype, str):
                self.unknown_embed_names.add(hashlib.sha256(etype.encode()).hexdigest()[:8])
        qraw = _embed_record_uri(record)
        if qraw is not None and sel.post_target(qraw) is None:
            self.quote_nonpost += 1
        shape = "invalid"
        if edge is not None:
            if edge.kind == "reply":
                shape = "reply_quote" if edge.quoted else "reply"
                if edge.quoted:
                    self.reply_quote += 1
            else:
                shape = {"root": "top_level", "quote": "quote"}[edge.kind]
        self.post_shapes[shape] += 1
        parsed = sel.parse_at_uri(qraw) if qraw else None
        if parsed is not None and parsed.authority.startswith("did:web:"):
            self.did_web_targets += 1
        author = hash(frame.did)
        if edge is None:
            return
        if edge.kind == "root":
            self._root_candidate(frame, uri, record, author)
            return
        if edge.kind == "quote" and self._seed(record, uri, require_top_level=False) is not None:
            self.quote_seed_eligible += 1
        self._reference(frame, uri, edge)
        self._pair(frame, edge.parent or edge.reply_root)
        stored = self._attach(frame, uri, edge)
        if not stored and self.keep_rows:
            self._negative(frame, uri, record, edge)

    def _seed(
        self, record: dict[str, Any], uri: str, *, require_top_level: bool = True
    ) -> sel.SeedDecision | None:
        decision = sel.seed_decision(
            record, uri, self.allowlist, require_top_level=require_top_level
        )
        return decision if decision.eligible else None

    def _root_candidate(self, frame: Frame, uri: str, record: dict[str, Any], author: int) -> None:
        links = sel.link_urls(record)
        sources = {src for src, _ in links}
        if links:
            self.link_sources["both" if len(sources) == 2 else f"{next(iter(sources))}_only"] += 1
        else:
            self.link_sources["neither"] += 1
        canon = [c for _s, raw in links if (c := sel.canonicalise_url(raw)) is not None]
        for url in canon:
            host = sel.url_host(url)
            self.link_domains[host] += 1
            self.link_domain_authors.setdefault(host, set()).add(author)
        if any(sel.is_shortener(sel.url_host(u)) for u in canon):
            self.shortener_posts += 1
        decision = sel.seed_decision(record, uri, self.allowlist)
        self.decisions[decision.reason] += 1
        if decision.domain is not None:
            self.cand["allowlisted"] += 1
            if "en" in sel.record_langs(record):
                self.cand["en"] += 1
            labels = sel.record_labels(record)
            if any(x in sel.ADULT_LABELS for x in labels):
                self.cand["adult"] += 1
            if has_commentary(record):
                self.cand["commentary"] += 1
        if not decision.eligible or decision.domain is None or decision.claim_url is None:
            if self.keep_rows:
                self._negative_root(frame, uri, record, decision)
            return
        t = frame.time_us or 0
        self.eligible_times.append(t)
        self.eligible_buckets.append(sel.sample_bucket(uri))
        self.eligible_authors.add(author)
        self.domain_roots[decision.domain] += 1
        self.domain_authors.setdefault(decision.domain, set()).add(author)
        self.claim_groups[decision.claim_url] += 1
        self.cur_roots_eligible += 1
        if self.cur_roots_eligible == MAX_ACTIVE_ROOTS and self.window_first_us is not None:
            self.cur_cap_fill = t - (self.cur_first or t)
        cas = Cascade(
            frame, uri, t, decision.domain, decision.claim_url, self.eligible_buckets[-1], author
        )
        self.cascades.append(cas)
        self.roots[uri] = cas
        self.stored[uri] = (cas, 0, "root")

    def _reference(self, frame: Frame, uri: str, edge: sel.Edge) -> None:
        """Count references to untracked-or-tracked subjects (OD-3 option C counters)."""
        target = edge.parent if edge.kind != "reply" else (edge.parent or edge.reply_root)
        if target is None or frame.time_us is None or self.cur_first is None:
            return
        bucket = (frame.time_us - self.cur_first) // 3_600_000_000
        self.refs[(bucket, hash(target))] += 1

    def _pair(self, frame: Frame, target: str | None) -> None:
        """Count a (child, parent) pair whose parent frame is also in the window (S-4)."""
        if target is None or frame.time_us is None:
            return
        target_time = self.created_us.get(hash(target))
        if target_time is not None:
            self.pair_both += 1
            if target_time > frame.time_us:
                self.pair_child_first += 1

    def _attach(self, frame: Frame, uri: str, edge: sel.Edge) -> bool:
        """Store the event under a tracked cascade when its parent or root is stored."""
        t = frame.time_us or 0
        parent_info = self.stored.get(edge.parent) if edge.parent else None
        cas: Cascade | None = None
        depth: int | None = None
        orphan = False
        if parent_info is not None:
            cas = parent_info[0]
            depth = None if parent_info[1] is None else parent_info[1] + 1
            other = self.roots.get(edge.reply_root) if edge.reply_root else None
            if edge.kind == "reply" and other is not None and other is not cas:
                self.cross_cascade_children += 1
        elif edge.kind == "reply" and edge.reply_root in self.roots:
            cas = self.roots[edge.reply_root]
            orphan = True
        if cas is None:
            return False
        if t - cas.time_us > TTL_US:
            self.dropped_ttl += 1
            return False
        if cas.n_children >= MAX_EVENTS_PER_CASCADE:
            cas.overflow += 1
            self.dropped_overflow += 1
            return False
        cas.note_child(edge.kind, t)
        if edge.kind == "repost":
            depth = None
            self.reposts["tracked_subject"] += 1
        elif orphan:
            depth = None
            cas.max_depth = max(cas.max_depth, 0)
            self.orphans += 1
        elif depth is not None:
            cas.max_depth = max(cas.max_depth, depth)
        if edge.kind == "reply":
            if orphan:
                self.depth_counts["orphan"] += 1
            elif depth is None:
                self.depth_counts["disconnected"] += 1
            else:
                self.depth_counts[str(depth) if depth < 4 else "4+"] += 1
        self.stored_children += 1
        self.stored[uri] = (cas, depth, edge.kind)
        if self.keep_rows:
            cas.children.append(TrackedEvent(frame, edge.kind, depth, orphan, edge.parent))
        return True

    def _repost(self, frame: Frame, uri: str, record: dict[str, Any]) -> None:
        edge = sel.derive_edge(sel.REPOST_COLLECTION, record)
        self.reposts["total"] += 1
        if edge is None:
            self.reposts["non_post_subject"] += 1
            return
        parsed = sel.parse_at_uri(edge.parent)
        if parsed is not None and parsed.authority.startswith("did:web:"):
            self.did_web_targets += 1
        subject_hash = hash(edge.parent)
        self.repost_subject[hash(uri)] = subject_hash
        if edge.via is not None:
            self.reposts["via"] += 1
            via_hash = hash(edge.via)
            if via_hash in self.repost_subject:
                self.reposts["via_seen"] += 1
                if self.repost_subject[via_hash] == subject_hash:
                    self.reposts["via_same_subject"] += 1
        self._reference(frame, uri, edge)
        stored = self._attach(frame, uri, edge)
        if not stored:
            self.reposts["untracked_subject"] += 1
            if self.keep_rows:
                self._negative(frame, uri, record, edge)
        else:
            parent = self.stored.get(edge.parent or "")
            if parent is not None and parent[2] == "root":
                self.reposts["root_subject"] += 1
        self._pair(frame, edge.parent)

    def _delete(self, frame: Frame, uri: str) -> None:
        coll = "post" if frame.collection == sel.POST_COLLECTION else "repost"
        self.deletes[coll] += 1
        created = self.created_us.get(hash(uri))
        latency = None
        if created is not None and frame.time_us is not None:
            latency = (frame.time_us - created) / 1e6
            if coll == "post":
                self.delete_latency["post"].append(latency)
        info = self.stored.get(uri)
        if info is not None:
            if latency is not None:
                self.delete_latency["root" if info[2] == "root" else "child"].append(latency)
            info[0].deletes.append(frame)
        elif self.keep_rows:
            self.cutter_picks[f"del:{coll}"].offer(uri, frame)

    def _negative(self, frame: Frame, uri: str, record: dict[str, Any], edge: sel.Edge) -> None:
        self.cutter_picks["neg"].offer(uri, frame)
        if edge.kind == "reply" and sel.link_urls(record):
            self.cutter_picks["near:reply_with_link"].offer(uri, frame)

    def _negative_root(
        self, frame: Frame, uri: str, record: dict[str, Any], decision: sel.SeedDecision
    ) -> None:
        self.cutter_picks["neg"].offer(uri, frame)
        reason = decision.reason
        if reason == "not_allowlisted" and sel.link_urls(record):
            self.cutter_picks["near:non_allowlisted"].offer(uri, frame)
        elif reason == "lang":
            self.cutter_picks["near:non_english_allowlisted"].offer(uri, frame)
        elif reason in ("adult_label", "no_unauthenticated_label"):
            self.cutter_picks["near:adult_labelled"].offer(uri, frame)
        elif reason == "shortener":
            self.cutter_picks["near:shortener"].offer(uri, frame)

    # ------------------------------------------------------------------ results

    def finish(self) -> dict[str, Any]:
        """Close the last window and return the measurement dictionary (identifier-free)."""
        self.new_window()
        results = {
            "label": self.label,
            "s2": self._s2(),
            "s4": self._s4(),
            "s5": self._s5(),
            "s6": self._s6(),
            "s7": self._s7(),
            "s9": self._s9(),
        }
        ensure_no_identifiers(results)
        return results

    def total_seconds(self) -> float:
        """Sum of the measured stream spans (last minus first frame time, per window)."""
        return sum(last - first for first, last in self.spans) / 1e6

    def _s2(self) -> dict[str, Any]:
        secs = self.total_seconds()
        hours = secs / 3600 if secs else 0.0
        sizes = sorted(self.sizes)
        per_sec: list[int] = []
        per_min: list[int] = []
        for first, last in self.spans:
            s0, s1 = first // 1_000_000, last // 1_000_000
            counts = [self.per_second.get(s, 0) for s in range(s0, s1 + 1)]
            per_sec.extend(counts)
            per_min.extend(sum(counts[i : i + 60]) for i in range(0, len(counts) - 59, 60))
        per_sec.sort()
        per_min.sort()
        total = sum(self.sizes)
        by_op = {
            k: {"count": v, "per_second": _round(v / secs if secs else None)}
            for k, v in sorted(self.counts.items())
        }
        shapes = {
            k: _share(v, sum(self.post_shapes.values()))
            for k, v in sorted(self.post_shapes.items())
        }
        return {
            "stream_seconds": _round(secs, 1),
            "frames": len(self.sizes),
            "bytes": total,
            "events_per_second": _round(len(self.sizes) / secs if secs else None, 2),
            "bytes_per_second": _round(total / secs if secs else None, 1),
            "by_kind": by_op,
            "frame_bytes": {
                "p50": pct(sizes, 50),
                "p95": pct(sizes, 95),
                "p99": pct(sizes, 99),
                "max": float(sizes[-1]) if sizes else None,
            },
            "per_second_events": {
                "p50": pct(per_sec, 50),
                "p95": pct(per_sec, 95),
                "max": pct(per_sec, 100),
            },
            "per_minute_events": {
                "p50": pct(per_min, 50),
                "p95": pct(per_min, 95),
                "max": pct(per_min, 100),
                "n": len(per_min),
            },
            "post_create_shares": shapes,
            "hours": _round(hours, 3),
        }

    def _s4(self) -> dict[str, Any]:
        skew = sorted(self.skew)
        return {
            "arrival_inversions": self.inversions,
            "largest_inversion_seconds": _round(self.largest_inversion_us / 1e6, 3),
            "seq_backwards": self.seq_backwards,
            "created_minus_stream_seconds": {
                "n": len(skew),
                "p1": pct(skew, 1),
                "p50": pct(skew, 50),
                "p99": pct(skew, 99),
                "min": float(skew[0]) if skew else None,
                "max": float(skew[-1]) if skew else None,
            },
            "created_future_gt_60s": self.skew_future,
            "created_older_than_1h": self.skew_old_1h,
            "created_absurd_or_unparseable": self.skew_absurd,
            "parent_child_pairs_in_log": self.pair_both,
            "child_before_parent": self.pair_child_first,
        }

    def _outcomes(self) -> dict[str, Any]:
        cascades = self.all_cascades
        out: dict[str, Any] = {}
        for name, seconds in (*HORIZONS, ("observed", 0)):
            horizon_us = seconds * 1_000_000
            eligible = [
                c for c in cascades if seconds == 0 or c.window_end_us - c.time_us >= horizon_us
            ]
            entry: dict[str, Any] = {"n": len(eligible)}
            for kind in ("any", "reply", "quote", "repost"):
                hits = sum(
                    1
                    for c in eligible
                    if kind in c.first_us
                    and (seconds == 0 or c.first_us[kind] - c.time_us <= horizon_us)
                )
                entry[kind] = _share(hits, len(eligible))
            out[name] = entry
        return out

    def _s5(self) -> dict[str, Any]:
        secs = self.total_seconds()
        hours = secs / 3600 if secs else 0.0
        n = len(self.eligible_times)
        cascades = self.all_cascades
        sizes = sorted(c.n_children for c in cascades)
        total_events = sum(c.n_children + 1 for c in cascades)
        top_n = max(1, math.ceil(0.01 * len(cascades))) if cascades else 0
        top_events = sum(
            c.n_children + 1 for c in sorted(cascades, key=lambda c: -c.n_children)[:top_n]
        )
        stored_replies = sum(self.depth_counts.values())
        fills = [f for f in self.cap_fill_us if f is not None]
        domains = [
            {"domain": d, "roots": r, "authors": len(self.domain_authors[d])}
            for d, r in sorted(self.domain_roots.items(), key=lambda kv: (-kv[1], kv[0]))[:15]
        ]
        allow = self.cand["allowlisted"]
        sampling = {
            str(rate): {
                "roots": (k := sum(1 for b in self.eligible_buckets if b < rate)),
                "share": _share(k, n),
                "per_hour": _round(k / hours if hours else None, 1),
            }
            for rate in SAMPLE_RATES
        }
        c_stats: dict[str, Any] = {}
        for threshold in (10, 25, 100):
            subj = [sum(1 for v in c.values() if v >= threshold) for _w, c in self.c_buckets]
            width = [w for w, _c in self.c_buckets]
            c_stats[str(threshold)] = {
                "subjects_per_bucket_mean": _round(sum(subj) / len(subj) if subj else None, 1),
                "lost_before_promotion_per_bucket_mean": _round(
                    sum((threshold - 1) * s for s in subj) / len(subj) if subj else None, 1
                ),
                "buckets": len(subj),
                "bucket_seconds_mean": _round(sum(width) / len(width) if width else None, 0),
            }
        distinct_subjects = [len(c) for _w, c in self.c_buckets]
        return {
            "eligible_roots": n,
            "eligible_per_hour": _round(n / hours if hours else None, 1),
            "decisions": dict(sorted(self.decisions.items())),
            "allowlisted_link_roots": allow,
            "english_share": _share(self.cand["en"], allow),
            "commentary_share": _share(self.cand["commentary"], allow),
            "adult_label_share": _share(self.cand["adult"], allow),
            "distinct_domains": len(self.domain_roots),
            "distinct_authors": len(self.eligible_authors),
            "top_domains": domains,
            "cap_500_fill_seconds_per_window": fills,
            "cap_500_accepted_share": _share(
                min(n, MAX_ACTIVE_ROOTS * max(1, self.windows_seen)), n
            ),
            "sampling": sampling,
            "outcomes": self._outcomes(),
            "cascade_children": {
                "n": len(sizes),
                "median": pct(sizes, 50),
                "p90": pct(sizes, 90),
                "p99": pct(sizes, 99),
                "max": float(sizes[-1]) if sizes else None,
                "with_children": sum(1 for s in sizes if s > 0),
            },
            "reply_depth": dict(sorted(self.depth_counts.items())),
            "orphan_rate": _share(self.orphans, stored_replies),
            "top1pct_event_share": _share(top_events, total_events),
            "option_c_distinct_subjects_per_bucket_mean": _round(
                sum(distinct_subjects) / len(distinct_subjects) if distinct_subjects else None, 1
            ),
            "option_c_thresholds": c_stats,
            "dropped_ttl": self.dropped_ttl,
            "dropped_overflow": self.dropped_overflow,
        }

    def _s6(self) -> dict[str, Any]:
        top = max(1, self.post_shapes["top_level"])
        return {
            "reply_quote_posts": self.reply_quote,
            "embed_types": dict(sorted(self.embeds.items())),
            "unknown_embed_types_distinct": len(self.unknown_embed_names),
            "top_level_link_sources": dict(sorted(self.link_sources.items())),
            "top_level_with_shortener": self.shortener_posts,
            "top_level_with_shortener_share": _share(self.shortener_posts, top),
            "reposts": dict(sorted(self.reposts.items())),
            "repost_via_share": _share(self.reposts["via"], self.reposts["total"]),
            "repost_via_target_seen_share": _share(self.reposts["via_seen"], self.reposts["via"]),
            "quote_targets_not_posts": self.quote_nonpost,
            "did_web_authors": self.did_web_authors,
            "did_web_targets": self.did_web_targets,
        }

    def _s7(self) -> dict[str, Any]:
        secs = self.total_seconds()
        hours = secs / 3600 if secs else 0.0

        def lat(values: list[float]) -> dict[str, Any]:
            v = sorted(values)
            return {
                "n": len(v),
                "p50": _round(pct(v, 50), 1),
                "p90": _round(pct(v, 90), 1),
                "max": _round(pct(v, 100), 1),
            }

        creates = {
            c: self.counts.get(f"commit/create/app.bsky.feed.{c}", 0) for c in ("post", "repost")
        }
        return {
            "deletes": dict(sorted(self.deletes.items())),
            "delete_per_hour": {
                c: _round(self.deletes[c] / hours if hours else None, 1) for c in ("post", "repost")
            },
            "delete_share_of_creates": {
                c: _share(self.deletes[c], creates[c]) for c in ("post", "repost")
            },
            "delete_latency_seconds_all_posts": lat(self.delete_latency["post"]),
            "delete_latency_seconds_tracked_roots": lat(self.delete_latency["root"]),
            "delete_latency_seconds_tracked_children": lat(self.delete_latency["child"]),
            "censoring_horizon_seconds": _round(secs, 0),
            "tracked_roots_deleted_in_window": len(self.delete_latency["root"]),
            "account_events_by_status": dict(sorted(self.accounts.items())),
            "unknown_status_values_distinct": len(self.unknown_statuses),
            "sync_events": self.syncs,
            "sync_per_hour": _round(self.syncs / hours if hours else None, 2),
            "info_frames": dict(sorted(self.infos.items())),
            "other_frames": self.other_frames,
        }

    def _s9(self) -> dict[str, Any]:
        groups = sorted(self.claim_groups.values(), reverse=True)
        n = sum(groups)
        shared = sum(g for g in groups if g > 1)
        return {
            "children_whose_parent_is_in_another_cascade": self.cross_cascade_children,
            "stored_children": self.stored_children,
            "roots": n,
            "distinct_canonical_urls": len(groups),
            "roots_in_shared_url_groups": shared,
            "roots_in_shared_url_groups_share": _share(shared, n),
            "largest_url_group": groups[0] if groups else 0,
            "url_groups_of_2_or_more": sum(1 for g in groups if g > 1),
            "quote_posts_seed_eligible": self.quote_seed_eligible,
        }

    # ------------------------------------------------------------------ rows

    def all_tracked(self) -> list[Cascade]:
        """Every cascade of every window (after ``finish``)."""
        return self.all_cascades


def _make_picks() -> dict[str, BoundedPick]:
    picks = {
        "neg": BoundedPick(400),
        "near:non_allowlisted": BoundedPick(14),
        "near:non_english_allowlisted": BoundedPick(14),
        "near:adult_labelled": BoundedPick(6),
        "near:shortener": BoundedPick(6),
        "near:reply_with_link": BoundedPick(8),
        "del:post": BoundedPick(14),
        "del:repost": BoundedPick(8),
        "sync": BoundedPick(5),
    }
    for status in ("deleted", "takendown", "active", "deactivated", "other"):
        picks[f"acct:{status}"] = BoundedPick(8)
    return picks


def iter_tracked_rows(collector: Collector) -> Iterator[TrackedRow]:
    """Yield roots, children and deletes of every tracked cascade in stream order."""
    rows: list[tuple[int, TrackedRow]] = []
    for index, cas in enumerate(collector.all_tracked()):
        rows.append((cas.root.order, TrackedRow("root", cas.root, index, 0, False, "root")))
        for ev in cas.children:
            rows.append(
                (ev.frame.order, TrackedRow("child", ev.frame, index, ev.depth, ev.orphan, ev.kind))
            )
        for dele in cas.deletes:
            rows.append((dele.order, TrackedRow("delete", dele, index)))
    rows.sort(key=lambda item: item[0])
    for _order, row in rows:
        yield row


# ----------------------------------------------------------------------------- drivers


def analyze_logs(
    refs: list[LogRef], allowlist: Collection[str], *, keep_rows: bool = False
) -> tuple[dict[str, Any], Collector, Counter[str]]:
    """Run every window and the combined view in one pass; returns results, combined, stats."""
    stats: Counter[str] = Counter()
    per_window = {ref.label: Collector(allowlist, label=ref.label) for ref in refs}
    combined = Collector(allowlist, label="combined", keep_rows=keep_rows)
    previous: str | None = None
    for frame in iter_frames(refs, stats):
        if previous is not None and frame.window != previous:
            combined.new_window()
        previous = frame.window
        per_window[frame.window].feed(frame)
        combined.feed(frame)
    results = {
        "windows": {label: coll.finish() for label, coll in per_window.items()},
        "combined": combined.finish(),
        "reader": dict(sorted(stats.items())),
    }
    ensure_no_identifiers(results)
    return results, combined, stats


def domains_only(
    refs: list[LogRef], allowlist: Collection[str], top: int = 100, min_authors: int = 3
) -> dict[str, Any]:
    """Top link domains among top-level posts with distinct-author counts (allowlist curation).

    Domains used by fewer than ``min_authors`` accounts are left out: a personal site is not a
    news domain and its name could identify its owner.
    """
    collector = Collector(allowlist, label="domains")
    for frame in iter_frames(refs):
        collector.feed(frame)
    collector.new_window()
    ranked = sorted(
        (
            kv
            for kv in collector.link_domains.items()
            if len(collector.link_domain_authors[kv[0]]) >= min_authors
        ),
        key=lambda kv: (-kv[1], kv[0]),
    )[:top]
    rows = [
        {"domain": d, "posts": n, "authors": len(collector.link_domain_authors[d])}
        for d, n in ranked
    ]
    result = {"top_domains": rows}
    ensure_no_identifiers(result)
    return result


# ----------------------------------------------------------------------------- markdown


def _fmt(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4g}" if abs(value) < 1000 else f"{value:,.1f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _flatten(prefix: str, value: object, rows: list[tuple[str, str]]) -> None:
    if isinstance(value, dict):
        for key, inner in value.items():
            _flatten(f"{prefix}.{key}" if prefix else str(key), inner, rows)
    elif isinstance(value, list) and value and all(isinstance(x, dict) for x in value):
        for item in value:
            label = ",".join(f"{k}={_fmt(v)}" for k, v in item.items())
            rows.append((prefix, label))
    else:
        rows.append((prefix, _fmt(value)))


def _section_table(data: object) -> list[str]:
    rows: list[tuple[str, str]] = []
    _flatten("", data, rows)
    lines = ["| Measure | Value |", "|---|---|"]
    lines.extend(f"| {name} | {value} |" for name, value in rows)
    return lines


MEASUREMENTS = (
    ("s2", "S-2 Volume"),
    ("s4", "S-4 Time"),
    ("s5", "S-5 Seed yield and cascades"),
    ("s6", "S-6 Shapes"),
    ("s7", "S-7 Deletes and account events"),
    ("s9", "S-9 Merge frequency"),
)


def summary_markdown(results: dict[str, Any]) -> str:
    """Markdown with exactly one ``### S-n`` heading per measurement (S-2, 4, 5, 6, 7, 9)."""
    ensure_no_identifiers(results)
    lines: list[str] = []
    for key, title in MEASUREMENTS:
        lines.append(f"### {title}")
        lines.append("")
        lines.extend(_section_table(results.get(key, {})))
        lines.append("")
    return "\n".join(lines)
