"""Deterministic scrubber and the stratified fixture cutter (D-04, RESEARCH F-01).

Scrubbing is a pure transform of a recorded frame: DIDs, rkeys and revs become SEQUENTIAL counter
tokens in the real field names (never random, never keyed); ``cid``, free text, link-card text and
thumbnails are dropped; URLs keep scheme, host and path. Nothing here uses ``random``; every
ordering is by sha256 of the raw URI, so two cuts of the same raw logs are byte-identical.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Collection, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from spike_lib import selection as sel
from spike_lib.analysis import Cascade, Collector, Frame, parse_time_us

TID = "234567abcdefghijklmnopqrstuvwxyz"
SCRUBBER_VERSION = "scrub-1"
SOURCE_MODE = "recorded-real"
DID_PREFIX = "did:plc:"
TYPE_PREFIX = "network.bsky.jetstream.subscribeEvents#"
LANG_RX = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
LABEL_RX = re.compile(r"^!?[a-z0-9-]{1,32}$")
TIME_RX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,9})?(Z|[+-]\d{2}:\d{2})?$")
KNOWN_STATUS = frozenset(
    {"active", "deleted", "takendown", "deactivated", "suspended", "desynchronized", "throttled"}
)
PLAIN_EMBEDS = frozenset(
    {"app.bsky.embed.images", "app.bsky.embed.video", "app.bsky.embed.gallery"}
)
INFO_NAMES = frozenset({"OutdatedCursor", "FutureCursor"})


def counter_token(i: int, width: int, pad: str) -> str:
    """Left-padded base32 counter: syntactically valid, low entropy, never random (F-01)."""
    text = ""
    while True:
        text = TID[i % 32] + text
        i //= 32
        if i == 0:
            break
    return pad * (width - len(text)) + text


class ScrubMaps:
    """First-seen-order counter maps for DIDs, rkeys and revs."""

    def __init__(self) -> None:
        self.dids: dict[str, str] = {}
        self.rkeys: dict[str, str] = {}
        self.revs: dict[str, str] = {}
        self.did_web = 0

    def did(self, original: str) -> str:
        """DID token: ``did:plc:`` plus 24 characters padded with ``a``."""
        if original not in self.dids:
            if original.startswith("did:web:"):
                self.did_web += 1
            self.dids[original] = DID_PREFIX + counter_token(len(self.dids), 24, "a")
        return self.dids[original]

    def rkey(self, original: str) -> str:
        """Record-key token: 13 characters padded with ``2``."""
        if original not in self.rkeys:
            self.rkeys[original] = counter_token(len(self.rkeys), 13, "2")
        return self.rkeys[original]

    def rev(self, original: str) -> str:
        """Revision token: 13 characters padded with ``2``."""
        if original not in self.revs:
            self.revs[original] = counter_token(len(self.revs), 13, "2")
        return self.revs[original]

    def at_uri(self, uri: object) -> str | None:
        """Rewrite an ``at://`` URI through the same maps; None when it is malformed."""
        parsed = sel.parse_at_uri(uri)
        if parsed is None:
            return None
        return f"at://{self.did(parsed.authority)}/{parsed.collection}/{self.rkey(parsed.rkey)}"


def strip_url(url: object) -> str | None:
    """Reduce an http(s) URL to scheme, host and path (no userinfo, port, query or fragment)."""
    if not isinstance(url, str):
        return None
    try:
        parts = urlsplit(url.strip())
        host = parts.hostname
        _ = parts.port  # an invalid port raises, exactly as in selection.canonicalise_url
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not host:
        return None
    return f"{parts.scheme.lower()}://{host.lower()}{parts.path}"


def _ref(maps: ScrubMaps, ref: object) -> dict[str, str] | None:
    uri = maps.at_uri(ref.get("uri") if isinstance(ref, dict) else None)
    return None if uri is None else {"uri": uri}


def _scrub_embed(embed: object, maps: ScrubMaps) -> dict[str, Any] | None:
    if not isinstance(embed, dict):
        return None
    etype = embed.get("$type")
    if etype == sel.EMBED_EXTERNAL:
        ext = embed.get("external")
        uri = strip_url(ext.get("uri") if isinstance(ext, dict) else None)
        return {"$type": etype, "external": {"uri": uri} if uri else {}}
    if etype == sel.EMBED_RECORD:
        ref = _ref(maps, embed.get("record"))
        return {"$type": etype, "record": ref or {}}
    if etype == sel.EMBED_RECORD_WITH_MEDIA:
        media = embed.get("media")
        mtype = media.get("$type") if isinstance(media, dict) else None
        out_media: dict[str, Any]
        if mtype == sel.EMBED_EXTERNAL and isinstance(media, dict):
            ext = media.get("external")
            uri = strip_url(ext.get("uri") if isinstance(ext, dict) else None)
            out_media = {"$type": mtype, "external": {"uri": uri} if uri else {}}
        else:
            out_media = {"$type": mtype if mtype in PLAIN_EMBEDS else "unknown"}
        inner = embed.get("record")
        ref = _ref(maps, inner.get("record") if isinstance(inner, dict) else None)
        return {
            "$type": etype,
            "media": out_media,
            "record": {"$type": sel.EMBED_RECORD, "record": ref or {}},
        }
    return {"$type": etype if etype in PLAIN_EMBEDS else "unknown"}


def _scrub_post(record: dict[str, Any], maps: ScrubMaps) -> dict[str, Any] | None:
    out: dict[str, Any] = {"$type": sel.POST_COLLECTION}
    created = record.get("createdAt")
    if isinstance(created, str) and TIME_RX.match(created):
        out["createdAt"] = created
    langs = record.get("langs")
    if isinstance(langs, list):
        kept = [x for x in langs if isinstance(x, str) and LANG_RX.match(x)][:3]
        if kept:
            out["langs"] = kept
    reply = record.get("reply")
    if isinstance(reply, dict):
        scrubbed = {k: r for k in ("parent", "root") if (r := _ref(maps, reply.get(k))) is not None}
        if not scrubbed:
            return None
        out["reply"] = scrubbed
    embed = _scrub_embed(record.get("embed"), maps)
    if embed is not None:
        out["embed"] = embed
    facets = []
    for facet in record.get("facets") or []:
        index = facet.get("index") if isinstance(facet, dict) else None
        for feature in (facet.get("features") or []) if isinstance(facet, dict) else []:
            if not (isinstance(feature, dict) and feature.get("$type") == sel.FACET_LINK):
                continue
            uri = strip_url(feature.get("uri"))
            if uri:
                start = index.get("byteStart") if isinstance(index, dict) else None
                end = index.get("byteEnd") if isinstance(index, dict) else None
                kept_index = (
                    {"byteEnd": end, "byteStart": start}
                    if isinstance(start, int) and isinstance(end, int)
                    else {}
                )
                facets.append(
                    {
                        "features": [{"$type": sel.FACET_LINK, "uri": uri}],
                        "index": kept_index,
                    }
                )
    if facets:
        out["facets"] = facets
    labels = sel.record_labels(record)
    kept_labels = [{"val": v} for v in labels if LABEL_RX.match(v)]
    if kept_labels:
        out["labels"] = {"$type": "com.atproto.label.defs#selfLabels", "values": kept_labels}
    return out


def _scrub_repost(record: dict[str, Any], maps: ScrubMaps) -> dict[str, Any] | None:
    subject = _ref(maps, record.get("subject"))
    if subject is None:
        return None
    out: dict[str, Any] = {"$type": sel.REPOST_COLLECTION, "subject": subject}
    created = record.get("createdAt")
    if isinstance(created, str) and TIME_RX.match(created):
        out["createdAt"] = created
    via = _ref(maps, record.get("via"))
    if via is not None:
        out["via"] = via
    return out


def scrub_record(collection: str, record: object, maps: ScrubMaps) -> dict[str, Any] | None:
    """Scrub a post or repost record; None when it cannot be scrubbed safely."""
    if not isinstance(record, dict):
        return None
    if collection == sel.POST_COLLECTION:
        return _scrub_post(record, maps)
    if collection == sel.REPOST_COLLECTION:
        return _scrub_repost(record, maps)
    return None


def _str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def scrub_frame(frame: dict[str, Any], maps: ScrubMaps) -> dict[str, Any] | None:
    """Scrub a v2 envelope; None means the frame is dropped (counted by the cutter)."""
    payload = frame.get("payload")
    if frame.get("$type") != "message" or not isinstance(payload, dict):
        return None
    suffix = str(payload.get("$type", "")).rsplit("#", 1)[-1]
    common: dict[str, Any] = {}
    for key in ("seq",):
        if isinstance(payload.get(key), int):
            common[key] = payload[key]
    for key in ("time", "witnessedAt"):
        if isinstance(payload.get(key), str) and TIME_RX.match(payload[key]):
            common[key] = payload[key]
    if suffix == "info":
        name = payload.get("name")
        message = _str(payload.get("message")) or ""
        clean = len(message) < 200 and "did:" not in message and "at://" not in message
        body: dict[str, Any] = {
            "$type": TYPE_PREFIX + "info",
            "name": name if name in INFO_NAMES else "other",
        }
        if clean:
            body["message"] = message
        return {"$type": "message", "payload": body}
    did = _str(payload.get("did"))
    if did is None:
        return None
    mapped = maps.did(did)
    if suffix == "commit":
        collection = payload.get("collection")
        operation = payload.get("operation")
        rkey, rev = _str(payload.get("rkey")), _str(payload.get("rev"))
        if collection not in (sel.POST_COLLECTION, sel.REPOST_COLLECTION) or rkey is None:
            return None
        body = {
            "$type": TYPE_PREFIX + "commit",
            "collection": collection,
            "did": mapped,
            "operation": operation,
            "rkey": maps.rkey(rkey),
            **common,
        }
        if rev is not None:
            body["rev"] = maps.rev(rev)
        if operation == "create":
            record = scrub_record(str(collection), payload.get("record"), maps)
            if record is None:
                return None
            body["record"] = record
        elif operation != "delete":
            return None
        return {"$type": "message", "payload": body}
    if suffix == "account":
        acct = payload.get("account")
        if not isinstance(acct, dict):
            return None
        status = acct.get("status")
        inner: dict[str, Any] = {
            "active": acct.get("active") is True,
            "did": mapped,
            "status": status if status in KNOWN_STATUS else "other",
        }
        for key in ("seq",):
            if isinstance(acct.get(key), int):
                inner[key] = acct[key]
        if isinstance(acct.get("time"), str) and TIME_RX.match(acct["time"]):
            inner["time"] = acct["time"]
        return {
            "$type": "message",
            "payload": {
                "$type": TYPE_PREFIX + "account",
                "account": inner,
                "did": mapped,
                **common,
            },
        }
    if suffix == "sync":
        inner = {"blocks": "dropped", "did": mapped}
        sync = payload.get("sync")
        if isinstance(sync, dict):
            if _str(sync.get("rev")) is not None:
                inner["rev"] = maps.rev(str(sync["rev"]))
            if isinstance(sync.get("seq"), int):
                inner["seq"] = sync["seq"]
            if isinstance(sync.get("time"), str) and TIME_RX.match(sync["time"]):
                inner["time"] = sync["time"]
        return {
            "$type": "message",
            "payload": {"$type": TYPE_PREFIX + "sync", "did": mapped, "sync": inner, **common},
        }
    return None  # identity frames are not requested and never kept


def scrub_v1_frame(frame: dict[str, Any], maps: ScrubMaps) -> dict[str, Any] | None:
    """Scrub a v1 (legacy wire) frame with the same functions; used only for the samples file."""
    did = _str(frame.get("did"))
    if did is None or not isinstance(frame.get("time_us"), int):
        return None
    out: dict[str, Any] = {
        "did": maps.did(did),
        "kind": frame.get("kind"),
        "time_us": frame["time_us"],
    }
    if isinstance(frame.get("cursor"), int):
        out["cursor"] = frame["cursor"]
    if frame.get("kind") == "commit":
        commit = frame.get("commit")
        if not isinstance(commit, dict):
            return None
        collection, operation = commit.get("collection"), commit.get("operation")
        rkey, rev = _str(commit.get("rkey")), _str(commit.get("rev"))
        if collection not in (sel.POST_COLLECTION, sel.REPOST_COLLECTION) or rkey is None:
            return None
        body: dict[str, Any] = {
            "collection": collection,
            "operation": operation,
            "rkey": maps.rkey(rkey),
        }
        if rev is not None:
            body["rev"] = maps.rev(rev)
        if operation == "create":
            record = scrub_record(str(collection), commit.get("record"), maps)
            if record is None:
                return None
            body["record"] = record
        elif operation != "delete":
            return None
        out["commit"] = body
        return out
    if frame.get("kind") == "account":
        acct = frame.get("account")
        if not isinstance(acct, dict):
            return None
        status = acct.get("status")
        out["account"] = {
            "active": acct.get("active") is True,
            "did": out["did"],
            "status": status if status in KNOWN_STATUS else "other",
        }
        return out
    return None


def dumps(obj: object) -> str:
    """Canonical one-line JSON: sorted keys, no spaces, ASCII only."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


# ----------------------------------------------------------------------------- coverage


def _frame_uri(payload: dict[str, Any]) -> str | None:
    if payload.get("did") and payload.get("collection") and payload.get("rkey"):
        return f"at://{payload['did']}/{payload['collection']}/{payload['rkey']}"
    return None


def compute_coverage(
    frames: Sequence[dict[str, Any]], allowlist: Collection[str], *, require_lang: str = "en"
) -> dict[str, Any]:
    """Replay the written (scrubbed) frames under the recorded policy and count what it sees."""
    stored: dict[str, tuple[int, int | None]] = {}  # uri -> (cascade index, depth)
    roots = 0
    children = {"reply": 0, "quote": 0, "repost": 0}
    with_kind: list[set[str]] = []
    with_depth2: set[int] = set()
    orphans = 0
    deletes = {"post": 0, "repost": 0}
    accounts: dict[str, int] = {}
    syncs = 0
    neg = {
        "total": 0,
        "near_miss_non_allowlisted": 0,
        "non_english_allowlisted": 0,
        "adult_labelled": 0,
        "shortener": 0,
        "reply_with_link": 0,
    }
    root_index: dict[str, int] = {}
    for env in frames:
        payload = env.get("payload", {})
        suffix = str(payload.get("$type", "")).rsplit("#", 1)[-1]
        if suffix == "account":
            status = str(payload.get("account", {}).get("status", "other"))
            accounts[status] = accounts.get(status, 0) + 1
            continue
        if suffix == "sync":
            syncs += 1
            continue
        if suffix != "commit":
            continue
        uri = _frame_uri(payload)
        collection = payload.get("collection")
        if payload.get("operation") == "delete":
            if uri in stored:
                deletes["post" if collection == sel.POST_COLLECTION else "repost"] += 1
            continue
        record = payload.get("record")
        edge = sel.derive_edge(str(collection), record)
        if uri is None or edge is None:
            continue
        if edge.kind == "root":
            decision = sel.seed_decision(
                record, uri, allowlist, require_lang=require_lang, sample_per_10k=10000
            )
            if decision.eligible:
                stored[uri] = (len(with_kind), 0)
                root_index[uri] = len(with_kind)
                with_kind.append(set())
                roots += 1
                continue
            neg["total"] += 1
            if decision.reason == "not_allowlisted" and sel.link_urls(record):
                neg["near_miss_non_allowlisted"] += 1
            elif decision.reason == "lang":
                neg["non_english_allowlisted"] += 1
            elif decision.reason in ("adult_label", "no_unauthenticated_label"):
                neg["adult_labelled"] += 1
            elif decision.reason == "shortener":
                neg["shortener"] += 1
            continue
        parent = stored.get(edge.parent) if edge.parent else None
        orphan = False
        if parent is None and edge.kind == "reply" and edge.reply_root in root_index:
            parent = (root_index[edge.reply_root or ""], None)
            orphan = True
        if parent is None:
            neg["total"] += 1
            if edge.kind == "reply" and sel.link_urls(record):
                neg["reply_with_link"] += 1
            continue
        index = parent[0]
        depth = None if orphan or edge.kind == "repost" or parent[1] is None else parent[1] + 1
        stored[uri] = (index, depth)
        children[edge.kind] += 1
        with_kind[index].add(edge.kind)
        if orphan:
            orphans += 1
        if edge.kind == "reply" and depth is not None and depth >= 2:
            with_depth2.add(index)
    return {
        "tracked_roots": roots,
        "children_by_kind": children,
        "cascades_with_replies": sum(1 for k in with_kind if "reply" in k),
        "cascades_with_quotes": sum(1 for k in with_kind if "quote" in k),
        "cascades_with_reposts": sum(1 for k in with_kind if "repost" in k),
        "cascades_with_depth2_replies": len(with_depth2),
        "orphan_replies": orphans,
        "deletes": deletes,
        "account_events_by_status": dict(sorted(accounts.items())),
        "sync_events": syncs,
        "negative_controls": neg,
    }


def counts_by_kind(frames: Sequence[dict[str, Any]]) -> dict[str, int]:
    """Frame counts by kind with every key present."""
    out = dict.fromkeys(
        ("post_create", "repost_create", "post_delete", "repost_delete", "account", "sync", "info"),
        0,
    )
    for env in frames:
        payload = env.get("payload", {})
        suffix = str(payload.get("$type", "")).rsplit("#", 1)[-1]
        if suffix == "commit":
            coll = "post" if payload.get("collection") == sel.POST_COLLECTION else "repost"
            out[f"{coll}_{payload.get('operation')}"] += 1
        elif suffix in ("account", "sync", "info"):
            out[suffix] += 1
    return out


# ----------------------------------------------------------------------------- cutter


def _git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607 - git on PATH, fixed arguments
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _root_key(cas: Cascade) -> str:
    return hashlib.sha256(cas.uri.encode("utf-8")).hexdigest()


def _group_orders(cas: Cascade) -> set[int]:
    return {
        cas.root.order,
        *(ev.frame.order for ev in cas.children),
        *(d.order for d in cas.deletes),
    }


def select_frames(
    collector: Collector, *, min_children: int, small_sample: int
) -> tuple[list[Frame], list[tuple[str, set[int]]], list[Frame]]:
    """Choose the fixture frames: (fixed frames, trimmable cascade groups, trimmable negatives)."""
    cascades = sorted(collector.all_tracked(), key=_root_key)
    big = [c for c in cascades if c.n_children >= min_children]
    rest = [c for c in cascades if c.n_children < min_children]
    chosen_small = rest[:small_sample]
    extras = rest[small_sample:]

    def has_quote(c: Cascade) -> bool:
        return any(ev.kind == "quote" for ev in c.children)

    def has_depth2(c: Cascade) -> bool:
        return any(ev.kind == "reply" and (ev.depth or 0) >= 2 for ev in c.children)

    included = big + chosen_small
    for cas in extras:
        quotes = sum(1 for c in included if has_quote(c))
        deep = sum(1 for c in included if has_depth2(c))
        if (quotes < 3 and has_quote(cas)) or (deep < 3 and has_depth2(cas)):
            chosen_small.append(cas)
            included.append(cas)
    fixed: list[Frame] = []
    for cas in big:
        fixed.append(cas.root)
        fixed.extend(ev.frame for ev in cas.children)
        fixed.extend(cas.deletes)
    groups = []
    for cas in chosen_small:
        orders = _group_orders(cas)
        groups.append((_root_key(cas), orders))
        fixed.append(cas.root)
        fixed.extend(ev.frame for ev in cas.children)
        fixed.extend(cas.deletes)
    picks = collector.cutter_picks
    negatives: list[Frame] = []
    seen: set[int] = set()
    for name, limit in (
        ("near:non_allowlisted", 10),
        ("near:non_english_allowlisted", 10),
        ("near:adult_labelled", 3),
        ("near:shortener", 3),
        ("near:reply_with_link", 5),
    ):
        for frame in picks[name].frames()[:limit]:
            if frame.order not in seen:
                seen.add(frame.order)
                negatives.append(frame)
    generic = [f for f in picks["neg"].frames() if f.order not in seen][:300]
    negatives.extend(generic)
    shapes: list[Frame] = []
    shapes.extend(picks["del:post"].frames()[:10])
    shapes.extend(picks["del:repost"].frames()[:5])
    for key, pick in sorted(picks.items()):
        if key.startswith("acct:"):
            shapes.extend(pick.frames()[:5])
    shapes.extend(picks["sync"].frames()[:3])
    return fixed + shapes, groups, negatives


def _line_sizes(frames: Sequence[Frame]) -> dict[int, int]:
    maps = ScrubMaps()
    sizes: dict[int, int] = {}
    for frame in sorted(frames, key=lambda f: f.order):
        scrubbed = scrub_frame(frame.obj or {}, maps)
        if scrubbed is not None:
            sizes[frame.order] = len(dumps(scrubbed)) + 1
    return sizes


def scrub_samples(samples: Sequence[dict[str, Any]]) -> list[str]:
    """Scrub the real probe frames (v1 dialect and control shapes) with a fresh set of maps."""
    maps = ScrubMaps()
    lines = []
    for sample in samples:
        try:
            frame = json.loads(sample["f"])
        except (KeyError, ValueError, TypeError):
            continue
        if not isinstance(frame, dict):
            continue
        if sample.get("dialect") == "v1":
            scrubbed = scrub_v1_frame(frame, maps)
        elif frame.get("$type") == "error":
            scrubbed = {"$type": "error", "error": str(frame.get("error"))[:40]}
        else:
            scrubbed = scrub_frame(frame, maps)
        if scrubbed is not None:
            lines.append(dumps({"dialect": sample.get("dialect", "v2"), "frame": scrubbed}))
    return lines


def cut(
    collector: Collector,
    *,
    allowlist: Sequence[str],
    out_dir: Path,
    date: str,
    windows: list[dict[str, Any]],
    samples: Sequence[dict[str, Any]] = (),
    max_bytes: int = 1_500_000,
    min_children: int = 3,
    small_sample: int = 60,
    tool_sha: str | None = None,
) -> dict[str, Any]:
    """Cut the fixture from an extraction (``keep_rows=True``); returns the manifest dictionary."""
    fixed, groups, negatives = select_frames(
        collector, min_children=min_children, small_sample=small_sample
    )
    sample_lines = scrub_samples(samples)
    sample_bytes = sum(len(line) + 1 for line in sample_lines)
    pool = {f.order: f for f in fixed}
    for frame in negatives:
        pool.setdefault(frame.order, frame)
    sizes = _line_sizes(list(pool.values()))
    total = sample_bytes + sum(sizes.values())
    trimmed = False
    live_groups = list(groups)  # hash order; trim from the end
    live_negatives = list(negatives)
    dropped_orders: set[int] = set()
    while total > max_bytes and (live_negatives or live_groups):
        trimmed = True
        if live_negatives:
            victim = live_negatives.pop()
            gone = {victim.order}
        else:
            _key, gone = live_groups.pop()
        for order in gone:
            if order not in dropped_orders:
                dropped_orders.add(order)
                total -= sizes.get(order, 0)
    keep = [f for o, f in sorted(pool.items()) if o not in dropped_orders]
    maps = ScrubMaps()
    lines: list[str] = []
    envelopes: list[dict[str, Any]] = []
    scrubber_dropped = 0
    for frame in keep:
        scrubbed = scrub_frame(frame.obj or {}, maps)
        if scrubbed is None:
            scrubber_dropped += 1
            continue
        envelopes.append(scrubbed)
        lines.append(dumps(scrubbed))
    out_dir.mkdir(parents=True, exist_ok=True)
    main_path = out_dir / f"bluesky-{date}.jsonl"
    samples_path = out_dir / f"bluesky-{date}.samples.jsonl"
    manifest_path = out_dir / f"bluesky-{date}.manifest.json"
    main_path.write_text("".join(line + "\n" for line in lines), encoding="utf-8", newline="\n")
    samples_path.write_text(
        "".join(line + "\n" for line in sample_lines), encoding="utf-8", newline="\n"
    )
    times = [
        t
        for env in envelopes
        if (t := parse_time_us(env.get("payload", {}).get("time"))) is not None
    ]
    files = []
    for path, count in ((main_path, len(lines)), (samples_path, len(sample_lines))):
        data = path.read_bytes()
        files.append(
            {
                "name": path.name,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "lines": count,
            }
        )
    manifest = {
        "source_mode": SOURCE_MODE,
        "date": date,
        "sources": sorted({str(w["host"]) for w in windows}),
        "dialects": sorted({str(w["dialect"]) for w in windows}),
        "collections": [sel.POST_COLLECTION, sel.REPOST_COLLECTION],
        "start_stream_us": min(times) if times else None,
        "end_stream_us": max(times) if times else None,
        "counts_by_kind": counts_by_kind(envelopes),
        "frames_dropped_by_scrubber": scrubber_dropped,
        "did_web_count": maps.did_web,
        "coverage": compute_coverage(envelopes, allowlist),
        "trimmed": trimmed,
        "size_budget_bytes": max_bytes,
        "tool_git_sha": tool_sha or _git_sha(),
        "scrubber_version": SCRUBBER_VERSION,
        "files": files,
        "selection_policy": {
            "require_lang": "en",
            "sample_per_10k": 10000,
            "max_active_roots": None,
            "root_ttl_hours": 48,
            "max_events_per_cascade": 5000,
            "allowlist_domains": sorted(allowlist),
        },
        "windows": windows,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return manifest
