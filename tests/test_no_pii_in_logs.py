"""No personal data in any collector output (D-17, D-18, T-03-33).

Frames are CONSTRUCTED from real recorded shapes (a real allowlisted root with a link card, a real
reply shape, the real delete, account and identity shapes) whose DID, handle, rkey, post text,
tracking query parameters and URL fragment are distinctive markers. They go through
``classify_frame``, ``normalise``, the Decider and the writer inside ``run_ingest`` with logging
at DEBUG, and through the live source over a loopback server. Then no marker may appear in the
log text, the printed summary, ``ingest_runs.counters`` or ``ingest_runs.error_class``, or in any
text column of any table other than ``events.text`` and the claim's publisher title (the root
text legitimately holds the post text under a positive retention). The DID and handle markers
appear nowhere in the database at all, no pseudonym prefix longer than 8 characters reaches a
log line, and the secret never appears anywhere.

A non-tracking query parameter is part of the canonical link URL that D-13 and D-18 store on the
claim (an article id, for example), so the query markers here are tracking parameters, which
canonicalisation removes; the fragment is always removed. Patterned on
tests/test_upstream_errors.py (caplog, no key, no URL).
"""

import asyncio
import json
import logging
from copy import deepcopy
from typing import Any

import pytest
from conftest import (
    FAKE_PSEUDONYM_SECRET,
    ListSource,
    fixture_selection_policy,
    recorded_frames,
)
from loopback_server import Behaviour, LoopbackJetstream
from sqlalchemy import text

from truthtrail.ingest.dialect import classify_frame
from truthtrail.ingest.normalise import Dropped, normalise
from truthtrail.ingest.run import RunBounds, run_ingest
from truthtrail.ingest.source import DropCounter, JetstreamSource, SourceItem

MARKER_DID = "did:plc:" + "markerdidzqx" * 2
MARKER_DID_2 = "did:plc:" + "markerdidtwo" * 2
MARKER_HANDLE = "markerhandle-q7.bsky.social"
MARKER_RKEY = "markerrkeyq7xa"
MARKER_RKEY_2 = "markerrkeyq7xb"
MARKER_TEXT = "markertext of a constructed post q7"
MARKER_QUERY = "markerqueryq7"
MARKER_FRAGMENT = "markerfragmentq7"
MARKER_TITLE = "Constructed publisher title q7"
PERSONAL = (
    MARKER_DID,
    MARKER_DID_2,
    MARKER_HANDLE,
    MARKER_RKEY,
    MARKER_RKEY_2,
    MARKER_QUERY,
    MARKER_FRAGMENT,
    "markerdidzqx",
    "markerdidtwo",
)
EVERYWHERE = (*PERSONAL, MARKER_TEXT, FAKE_PSEUDONYM_SECRET)


def _real(predicate: Any) -> dict[str, Any]:
    return deepcopy(next(f for f in recorded_frames() if predicate(f["payload"])))


def _is_card_root(p: dict[str, Any]) -> bool:
    record = p.get("record") or {}
    embed = record.get("embed") or {}
    return (
        p.get("operation") == "create"
        and "reply" not in record
        and embed.get("$type") == "app.bsky.embed.external"
        and "en" in record.get("langs", [])
    )


def constructed_frames() -> list[dict[str, Any]]:
    domain = fixture_selection_policy()["allowlist_domains"][0]
    url = f"https://www.{domain}/2026/markers?utm_source={MARKER_QUERY}&fbclid={MARKER_QUERY}#{MARKER_FRAGMENT}"
    root = _real(_is_card_root)
    payload = root["payload"]
    payload["did"], payload["rkey"] = MARKER_DID, MARKER_RKEY
    record = payload["record"]
    record["text"] = MARKER_TEXT
    record["embed"]["external"] = {"uri": url, "title": MARKER_TITLE, "description": MARKER_TEXT}
    record.pop("facets", None)
    root_uri = f"at://{MARKER_DID}/app.bsky.feed.post/{MARKER_RKEY}"

    reply = _real(lambda p: "reply" in (p.get("record") or {}))
    rp = reply["payload"]
    rp["did"], rp["rkey"] = MARKER_DID_2, MARKER_RKEY_2
    rp["record"]["reply"] = {
        "parent": {"uri": root_uri, "cid": "x"},
        "root": {"uri": root_uri, "cid": "x"},
    }
    rp["record"]["text"] = MARKER_TEXT
    rp["witnessedAt"] = rp["time"] = payload["witnessedAt"]

    identity = deepcopy(_real(lambda p: "account" in p))
    identity["payload"] = {
        "$type": "network.bsky.jetstream.subscribeEvents#identity",
        "did": MARKER_DID,
        "identity": {"did": MARKER_DID, "handle": MARKER_HANDLE, "seq": 1, "time": payload["time"]},
        "seq": 1,
        "time": payload["time"],
        "witnessedAt": payload["witnessedAt"],
    }
    delete = _real(lambda p: p.get("operation") == "delete")
    dp = delete["payload"]
    dp["did"], dp["rkey"], dp["collection"] = MARKER_DID_2, MARKER_RKEY_2, "app.bsky.feed.post"
    dp["witnessedAt"] = dp["time"] = payload["witnessedAt"]
    account = _real(lambda p: "account" in p)
    ap = account["payload"]
    ap["did"] = ap["account"]["did"] = MARKER_DID_2
    ap["account"]["status"] = "deleted"
    ap["witnessedAt"] = ap["time"] = payload["witnessedAt"]
    return [root, reply, identity, delete, account]


class FrameSource(ListSource):
    """Raw constructed frames through the production classify and normalise, like ReplaySource."""

    def __init__(self, frames: list[dict[str, Any]], keyer: Any) -> None:
        super().__init__([])
        self._raw = [json.dumps(f) for f in frames]
        self._keyer = keyer

    async def items(self, resume_cursor_us: int | None, drops: Any = None) -> Any:
        for raw in self._raw:
            result = normalise(classify_frame(raw, "v2"), self._keyer)
            if isinstance(result, Dropped):
                if drops is not None:
                    drops.add(result.reason)
                continue
            yield SourceItem(result, getattr(result, "time_us", None))


def _bounds() -> RunBounds:
    return RunBounds(
        max_seconds=600, max_events=10_000, max_stored=10_000, batch_rows=2, batch_seconds=600
    )


def _assert_clean(where: str, value: str, markers: tuple[str, ...] = EVERYWHERE) -> None:
    for marker in markers:
        assert marker not in value, f"{marker[:6]}... found in {where}"


def _text_columns(connection: Any) -> list[tuple[str, str]]:
    rows = connection.execute(
        text(
            "SELECT table_name, column_name FROM information_schema.columns"
            " WHERE table_schema = 'public' AND data_type IN ('text', 'character varying', 'jsonb')"
            " AND table_name <> 'alembic_version' ORDER BY 1, 2"
        )
    ).all()
    return [(t, c) for t, c in rows]


@pytest.mark.requires_db
def test_no_marker_reaches_logs_counters_or_non_text_columns(
    clean_db: str, make_engine: Any, explicit_policy: Any, keyer: Any, caplog: Any
) -> None:
    engine = make_engine(clean_db, role="collector")
    policy = explicit_policy()
    with caplog.at_level(logging.DEBUG):
        summary = asyncio.run(
            run_ingest(
                engine,
                FrameSource(constructed_frames(), keyer),
                policy,
                bounds=_bounds(),
                source_name="pii-test",
            )
        )
    assert summary.status == "ok"
    assert summary.counters["accepted_root"] == 1
    assert summary.counters["accepted_reply"] == 1
    assert summary.counters["drop:identity_ignored"] == 1
    _assert_clean("logs", caplog.text)
    _assert_clean("summary", summary.line())
    with engine.connect() as connection:
        run = connection.execute(text("SELECT counters::text, error_class FROM ingest_runs")).one()
        _assert_clean("ingest_runs.counters", run[0])
        _assert_clean("ingest_runs.error_class", str(run[1]))
        for table, column in _text_columns(connection):
            values = connection.execute(
                text(f"SELECT coalesce(string_agg(\"{column}\"::text, ' '), '') FROM \"{table}\"")
            ).scalar_one()
            allowed = (table, column) in {("events", "text"), ("claims", "text")}
            _assert_clean(
                f"{table}.{column}",
                values,
                (*PERSONAL, FAKE_PSEUDONYM_SECRET) if allowed else EVERYWHERE,
            )
        whole = " ".join(
            connection.execute(
                text(f"SELECT coalesce(string_agg(t::text, ' '), '') FROM \"{table}\" t")
            ).scalar_one()
            for table in (
                "accounts",
                "claims",
                "cascades",
                "events",
                "ingest_checkpoints",
                "ingest_runs",
            )
        )
        stored_text = connection.execute(
            text("SELECT text FROM events WHERE edge_kind = 'root'")
        ).scalar_one()
        title = connection.execute(text("SELECT text FROM claims")).scalar_one()
        url = connection.execute(text("SELECT url_canonical FROM claims")).scalar_one()
        pseudonyms = connection.execute(text("SELECT pseudonym FROM accounts")).scalars().all()
    for marker in (MARKER_DID, MARKER_DID_2, MARKER_HANDLE, "did:", "at://"):
        assert marker not in whole
    assert stored_text == MARKER_TEXT
    assert title == MARKER_TITLE
    assert url.endswith("/2026/markers")
    assert pseudonyms
    for pseudonym in pseudonyms:
        for size in range(9, len(pseudonym) + 1):
            assert pseudonym[:size] not in caplog.text


@pytest.mark.requires_db
def test_a_failing_flush_records_only_an_exception_class_name(
    make_engine: Any, explicit_policy: Any, keyer: Any, caplog: Any
) -> None:
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    engine = make_engine(f"postgresql+psycopg://nobody@127.0.0.1:{port}/none", role="collector")
    with caplog.at_level(logging.DEBUG):
        summary = asyncio.run(
            run_ingest(
                engine,
                FrameSource(constructed_frames(), keyer),
                explicit_policy(),
                bounds=_bounds(),
                source_name="pii-test",
            )
        )
    assert summary.status == "db_failed"
    assert summary.error_class == "OperationalError"
    _assert_clean("logs", caplog.text)
    _assert_clean("summary", summary.line())


def test_the_live_source_logs_no_marker_on_a_reconnect(keyer: Any, caplog: Any) -> None:
    frames = constructed_frames()

    async def scenario() -> list[Any]:
        got: list[Any] = []
        behaviours = [Behaviour(send=2, close_code=1011), Behaviour(then="silent")]
        async with LoopbackJetstream(frames, behaviours) as server:

            async def no_sleep(_s: float) -> None:
                await asyncio.sleep(0)

            source = JetstreamSource(
                ("jetstream-a.loopback.test",),
                "v2",
                keyer,
                rewind_seconds=30,
                proxy=None,
                sleep=no_sleep,
                base_urls={"jetstream-a.loopback.test": server.base},
            )
            stream = source.items(None, DropCounter())
            try:
                async for item in stream:
                    got.append(item)
                    if len(got) >= 4:
                        break
            finally:
                await stream.aclose()
        return got

    with caplog.at_level(logging.DEBUG):
        got = asyncio.run(asyncio.wait_for(scenario(), 15))
    assert len(got) == 4
    assert "jetstream connection ended" in caplog.text
    _assert_clean("logs", caplog.text)
    for item in got:
        _assert_clean("item repr", repr(item.result), PERSONAL)


def test_control_the_marker_scan_is_not_blind() -> None:
    for marker in EVERYWHERE:
        with pytest.raises(AssertionError):
            _assert_clean("control", f"prefix {marker} suffix")
    frames = json.dumps(constructed_frames())
    for marker in (
        MARKER_DID,
        MARKER_HANDLE,
        MARKER_RKEY,
        MARKER_TEXT,
        MARKER_QUERY,
        MARKER_FRAGMENT,
    ):
        assert marker in frames
