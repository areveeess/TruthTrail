"""Pure selection functions: edges, URLs, allowlist, sampling and the seed decision (D-12, D-13).

Standard library only and strict-typed: plan 03-04 moved this file unchanged into the package (git
mv), so the yield measured by the spike is the yield that ships, and then extended it additively:
``sample_bucket`` lets the normaliser compute the sampling bucket once and discard the raw URI,
``load_allowlist`` reads the committed allowlist file, ``SeedCandidate`` and ``seed_decision_for``
decide on a normalised root candidate (the production path holds no raw record or URI), and the
optional OD-3 option B claim-URL match seeds a post whose canonical URL is a stored news headline
URL. No fetching, no resolving, no state.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlsplit

POST_COLLECTION = "app.bsky.feed.post"
REPOST_COLLECTION = "app.bsky.feed.repost"

EMBED_RECORD = "app.bsky.embed.record"
EMBED_RECORD_WITH_MEDIA = "app.bsky.embed.recordWithMedia"
EMBED_EXTERNAL = "app.bsky.embed.external"
FACET_LINK = "app.bsky.richtext.facet#link"

_AT_URI = re.compile(
    r"^at://(did:(?:plc|web):[A-Za-z0-9._%:-]+)/([A-Za-z0-9.]+)/([A-Za-z0-9._~:-]+)$"
)

ADULT_LABELS = frozenset({"porn", "sexual", "nudity", "graphic-media"})
NO_UNAUTHENTICATED_LABEL = "!no-unauthenticated"

SHORTENERS = frozenset(
    {
        "bit.ly",
        "t.co",
        "tinyurl.com",
        "ow.ly",
        "buff.ly",
        "is.gd",
        "goo.gl",
        "lnkd.in",
        "dlvr.it",
        "trib.al",
        "wapo.st",
        "nyti.ms",
        "apne.ws",
        "reut.rs",
        "cnn.it",
        "bbc.in",
    }
)

_TRACKING_EXACT = frozenset({"fbclid", "gclid", "msclkid", "mc_cid", "mc_eid", "igshid"})

LINK_CARD = "card"
LINK_FACET = "facet"

ALLOWLIST_MAX_ENTRIES = 60
SAMPLE_BUCKETS = 10000
_ALLOWLIST_DOMAIN = re.compile(
    r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+"
)


class AtUri(NamedTuple):
    """The three parts of an ``at://`` record URI."""

    authority: str
    collection: str
    rkey: str


@dataclass(frozen=True, slots=True)
class Edge:
    """A record's relation to another post: a fact of the record, not of what is stored."""

    kind: str  # root, reply, quote or repost
    parent: str | None = None
    reply_root: str | None = None
    quoted: str | None = None
    via: str | None = None


@dataclass(frozen=True, slots=True)
class SeedDecision:
    """Outcome of the seed policy for one post."""

    eligible: bool
    reason: str
    domain: str | None = None
    claim_url: str | None = None


def parse_at_uri(uri: object) -> AtUri | None:
    """Split an ``at://`` URI (did:plc or did:web authority); None when malformed."""
    if not isinstance(uri, str):
        return None
    match = _AT_URI.match(uri)
    if match is None:
        return None
    return AtUri(match.group(1), match.group(2), match.group(3))


def post_target(uri: object) -> str | None:
    """Return the URI only when it names an app.bsky.feed.post record (RESEARCH F-08)."""
    parsed = parse_at_uri(uri)
    if parsed is None or parsed.collection != POST_COLLECTION or not isinstance(uri, str):
        return None
    return uri


def _mapping(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return {str(k): v for k, v in value.items()}
    return None


def _uri_of(ref: object) -> object:
    mapping = _mapping(ref)
    return None if mapping is None else mapping.get("uri")


def _quote_target(record: dict[str, object]) -> str | None:
    embed = _mapping(record.get("embed"))
    if embed is None:
        return None
    etype = embed.get("$type")
    inner: object = None
    if etype == EMBED_RECORD:
        inner = embed.get("record")
    elif etype == EMBED_RECORD_WITH_MEDIA:
        outer = _mapping(embed.get("record"))
        inner = None if outer is None else outer.get("record")
    return post_target(_uri_of(inner))


def derive_edge(collection: str, record: object) -> Edge | None:
    """Derive the edge of a create record exactly as D-12 defines it; None when unusable."""
    rec = _mapping(record)
    if rec is None:
        return None
    if collection == REPOST_COLLECTION:
        subject = post_target(_uri_of(rec.get("subject")))
        if subject is None:
            return None
        via = _uri_of(rec.get("via"))
        return Edge("repost", subject, via=via if isinstance(via, str) else None)
    if collection != POST_COLLECTION:
        return None
    quoted = _quote_target(rec)
    reply = _mapping(rec.get("reply"))
    if reply is not None:  # reply wins over quote; the quote stays a secondary relation
        parent = post_target(_uri_of(reply.get("parent")))
        root = post_target(_uri_of(reply.get("root")))
        if parent is None and root is None:
            return None
        return Edge("reply", parent, reply_root=root, quoted=quoted)
    if quoted is not None:
        return Edge("quote", quoted)
    return Edge("root")


def link_urls(record: object) -> list[tuple[str, str]]:
    """Return (source, raw url) for the link card and every link facet; source is card or facet."""
    rec = _mapping(record)
    if rec is None:
        return []
    found: list[tuple[str, str]] = []
    embed = _mapping(rec.get("embed"))
    if embed is not None:
        etype = embed.get("$type")
        card: dict[str, object] | None = None
        if etype == EMBED_EXTERNAL:
            card = _mapping(embed.get("external"))
        elif etype == EMBED_RECORD_WITH_MEDIA:
            media = _mapping(embed.get("media"))
            if media is not None and media.get("$type") == EMBED_EXTERNAL:
                card = _mapping(media.get("external"))
        uri = None if card is None else card.get("uri")
        if isinstance(uri, str):
            found.append((LINK_CARD, uri))
    facets = rec.get("facets")
    if isinstance(facets, list):
        for facet in facets:
            fmap = _mapping(facet)
            features = None if fmap is None else fmap.get("features")
            if not isinstance(features, list):
                continue
            for feature in features:
                fe = _mapping(feature)
                if fe is not None and fe.get("$type") == FACET_LINK:
                    furi = fe.get("uri")
                    if isinstance(furi, str):
                        found.append((LINK_FACET, furi))
    return found


def _is_tracking_param(name: str) -> bool:
    lowered = name.lower()
    return lowered.startswith("utm_") or lowered in _TRACKING_EXACT


def canonicalise_url(url: str) -> str | None:
    """Canonical form of an http(s) URL; never fetches or resolves anything (D-13)."""
    try:
        parts = urlsplit(url.strip())
        host = parts.hostname
        port = parts.port
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not host:
        return None
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return None
    scheme = parts.scheme.lower()
    default_port = 443 if scheme == "https" else 80
    netloc = host if port in (None, default_port) else f"{host}:{port}"
    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/") or "/"
    kept = [p for p in parts.query.split("&") if p and not _is_tracking_param(p.split("=", 1)[0])]
    query = "?" + "&".join(kept) if kept else ""
    return f"{scheme}://{netloc}{path}{query}"


def url_host(canonical_url: str) -> str:
    """Host of a canonical URL (lowercase, no www.); empty string when unparseable."""
    try:
        return urlsplit(canonical_url).hostname or ""
    except ValueError:
        return ""


def match_domain(host: str, allowlist: Collection[str]) -> str | None:
    """Return the allowlist entry that matches by equality or dot-suffix (longest wins)."""
    if not host:
        return None
    best: str | None = None
    for entry in allowlist:
        matches = bool(entry) and (host == entry or host.endswith("." + entry))
        if matches and (best is None or len(entry) > len(best)):
            best = entry
    return best


def host_allowed(host: str, allowlist: Collection[str]) -> bool:
    """True when the host equals an allowlist entry or is a subdomain of one."""
    return match_domain(host, allowlist) is not None


def is_shortener(host: str) -> bool:
    """True for a known link shortener host or a subdomain of one."""
    return any(host == s or host.endswith("." + s) for s in SHORTENERS)


def sample_keep(raw_at_uri: str, per_10k: int) -> bool:
    """Deterministic hash sample over the RAW at-URI; independent of any secret (RESEARCH F-06)."""
    return sample_bucket(raw_at_uri) < per_10k


def sample_bucket(raw_at_uri: str) -> int:
    """The 0..9999 bucket that ``sample_keep`` compares with its threshold.

    The first 8 bytes of sha256 of the raw at-URI, big-endian, modulo 10000. The normaliser
    computes it once so the raw URI can be discarded (D-17).
    """
    digest = hashlib.sha256(raw_at_uri.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % SAMPLE_BUCKETS


def load_allowlist(path: Path | str) -> frozenset[str]:
    """Read ``domain  # category`` lines; blank and comment lines are ignored.

    Nothing is normalised silently: an uppercase entry, a ``www.`` entry, a malformed domain, a
    duplicate or more than ``ALLOWLIST_MAX_ENTRIES`` entries raise ``ValueError`` naming the line.
    """
    entries: list[str] = []
    text = Path(path).read_text(encoding="utf-8")
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        domain = stripped.partition("#")[0].strip()
        if domain != domain.lower():
            raise ValueError(f"allowlist line {number}: entries must be lowercase")
        if domain.startswith("www."):
            raise ValueError(f"allowlist line {number}: entries must not start with www.")
        if _ALLOWLIST_DOMAIN.fullmatch(domain) is None:
            raise ValueError(f"allowlist line {number}: not a registrable domain")
        if domain in entries:
            raise ValueError(f"allowlist line {number}: duplicate entry")
        entries.append(domain)
        if len(entries) > ALLOWLIST_MAX_ENTRIES:
            raise ValueError(f"allowlist has more than {ALLOWLIST_MAX_ENTRIES} entries")
    return frozenset(entries)


def record_labels(record: object) -> list[str]:
    """Self-label values of a post record (empty when none)."""
    rec = _mapping(record)
    labels = None if rec is None else _mapping(rec.get("labels"))
    values = None if labels is None else labels.get("values")
    out: list[str] = []
    if isinstance(values, list):
        for item in values:
            mapping = _mapping(item)
            val = None if mapping is None else mapping.get("val")
            if isinstance(val, str):
                out.append(val)
    return out


def record_langs(record: object) -> list[str]:
    """The ``langs`` strings of a post record (empty when absent)."""
    rec = _mapping(record)
    langs = None if rec is None else rec.get("langs")
    return [x for x in langs if isinstance(x, str)] if isinstance(langs, list) else []


@dataclass(frozen=True, slots=True)
class SeedCandidate:
    """What the seed decision reads from one post: no raw URI, DID or text (D-17).

    ``canonical_urls`` keeps the order of ``link_urls`` (card first, then facets) with the
    unparseable ones removed, so the first allowlisted URL is the same one the spike chose.
    """

    top_level: bool
    canonical_urls: tuple[str, ...]
    langs: tuple[str, ...]
    labels: frozenset[str]
    sample_bucket: int


def seed_candidate(
    record: object, raw_at_uri: str | None, *, bucket: int | None = None
) -> SeedCandidate:
    """Build the ``SeedCandidate`` of a post record; ``bucket`` replaces the raw URI when given."""
    if bucket is None:
        if raw_at_uri is None:
            raise ValueError("a raw at-URI or a sample bucket is required")
        bucket = sample_bucket(raw_at_uri)
    edge = derive_edge(POST_COLLECTION, record)
    canonical = tuple(
        c for _src, raw in link_urls(record) if (c := canonicalise_url(raw)) is not None
    )
    return SeedCandidate(
        top_level=edge is not None and edge.kind == "root",
        canonical_urls=canonical,
        langs=tuple(record_langs(record)),
        labels=frozenset(record_labels(record)),
        sample_bucket=bucket,
    )


def seed_decision_for(
    candidate: SeedCandidate,
    allowlist: Collection[str],
    *,
    require_lang: str = "en",
    sample_per_10k: int = 10000,
    require_top_level: bool = True,
    known_claim_urls: Collection[str] | None = None,
    seed_claim_url_match: bool = False,
) -> SeedDecision:
    """Decide whether a candidate seeds a tracked root; the reason string is stable (D-13).

    OD-3 option B: only when ``seed_claim_url_match`` is true, a canonical URL that is in
    ``known_claim_urls`` (the stored news headline URLs, supplied by the caller) makes a post
    eligible even when its host is not allowlisted; the reason is then ``claim_url_match`` and
    every other rule (top level only, shorteners never seed, language, labels, sampling) still
    applies. An allowlisted URL wins over a claim match.
    """
    if require_top_level and not candidate.top_level:
        return SeedDecision(False, "not_top_level")
    if not candidate.canonical_urls:
        return SeedDecision(False, "no_link")
    claim_set = known_claim_urls if seed_claim_url_match and known_claim_urls else None
    chosen: tuple[str, str] | None = None
    claim_match: tuple[str, str] | None = None
    saw_shortener = False
    for url in candidate.canonical_urls:
        host = url_host(url)
        if is_shortener(host):
            saw_shortener = True
            continue
        domain = match_domain(host, allowlist)
        if domain is not None and chosen is None:
            chosen = (domain, url)
        if claim_set is not None and claim_match is None and url in claim_set:
            claim_match = (host, url)
    eligible_reason = "eligible"
    if chosen is None and claim_match is not None:
        chosen, eligible_reason = claim_match, "claim_url_match"
    if chosen is None:
        return SeedDecision(False, "shortener" if saw_shortener else "not_allowlisted")
    domain, claim_url = chosen
    if require_lang and require_lang not in candidate.langs:
        return SeedDecision(False, "lang", domain, claim_url)
    if any(label in ADULT_LABELS for label in candidate.labels):
        return SeedDecision(False, "adult_label", domain, claim_url)
    if NO_UNAUTHENTICATED_LABEL in candidate.labels:
        return SeedDecision(False, "no_unauthenticated_label", domain, claim_url)
    if candidate.sample_bucket >= sample_per_10k:
        return SeedDecision(False, "sampled_out", domain, claim_url)
    return SeedDecision(True, eligible_reason, domain, claim_url)


def seed_decision(
    record: object,
    raw_at_uri: str | None,
    allowlist: Collection[str],
    *,
    require_lang: str = "en",
    sample_per_10k: int = 10000,
    require_top_level: bool = True,
    sample_bucket: int | None = None,
    known_claim_urls: Collection[str] | None = None,
    seed_claim_url_match: bool = False,
) -> SeedDecision:
    """Decide whether a post record seeds a tracked root; the reason string is stable (D-13).

    ``sample_bucket``, when given, is used instead of hashing ``raw_at_uri`` (the production
    path never holds a raw URI after normalisation). Option B arguments: see
    ``seed_decision_for``, which this function delegates to.
    """
    candidate = seed_candidate(record, raw_at_uri, bucket=sample_bucket)
    return seed_decision_for(
        candidate,
        allowlist,
        require_lang=require_lang,
        sample_per_10k=sample_per_10k,
        require_top_level=require_top_level,
        known_claim_urls=known_claim_urls,
        seed_claim_url_match=seed_claim_url_match,
    )


SEED_REASONS: Sequence[str] = (
    "eligible",
    "claim_url_match",
    "not_top_level",
    "no_link",
    "shortener",
    "not_allowlisted",
    "lang",
    "adult_label",
    "no_unauthenticated_label",
    "sampled_out",
)
