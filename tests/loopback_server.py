"""A loopback Jetstream v2 server for the live-source tests (RESEARCH Pattern 12, F-20).

Not a test module. ``LoopbackJetstream`` serves chosen REAL recorded fixture frames, re-serialised
as v2 text frames, on 127.0.0.1 with an ephemeral port and the ``xrpc.v1.json`` subprotocol. Each
connection follows the next scripted ``Behaviour`` (the last one repeats): refuse the upgrade
with an HTTP status (optionally a JSON error such as CursorTooOld), send an in-band info frame
first, send N frames from the requested cursor, then close with a code, go silent, send an error
frame or send an oversize frame. Every requested path and User-Agent is recorded so tests can
assert the cursor parameter and the header. Clients must pass ``proxy=None`` (the container sets
proxy variables).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlsplit

from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.datastructures import Headers
from websockets.http11 import Request, Response

from truthtrail.ingest.dialect import parse_stream_time

INFO_TYPE = "network.bsky.jetstream.subscribeEvents#info"
REASONS = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    429: "Too Many Requests",
    503: "Service Unavailable",
}


@dataclass(frozen=True)
class Behaviour:
    """What one connection does; ``then`` is close, silent, error_frame or oversize."""

    status: int | None = None
    error_name: str | None = None
    info_first: str | None = None
    send: int | None = None
    then: str = "close"
    close_code: int = 1011


def frame_time_us(frame: dict[str, Any]) -> int:
    payload = frame["payload"]
    return parse_stream_time(payload.get("witnessedAt") or payload["time"])


def requested_cursor(path: str) -> int | None:
    values = parse_qs(urlsplit(path).query).get("cursor")
    return int(values[0]) if values else None


class LoopbackJetstream:
    """``async with LoopbackJetstream(frames, [Behaviour(...)]) as server`` (see module doc)."""

    def __init__(self, frames: Sequence[dict[str, Any]], behaviours: Sequence[Behaviour]) -> None:
        self._frames = [(frame_time_us(f), json.dumps(f)) for f in frames]
        self._behaviours = list(behaviours) or [Behaviour()]
        self.paths: list[str] = []
        self.user_agents: list[str | None] = []
        self._assigned: dict[int, Behaviour] = {}
        self._server: Server | None = None
        self.port = 0

    @property
    def base(self) -> str:
        return f"ws://127.0.0.1:{self.port}"

    @property
    def cursors(self) -> list[int | None]:
        return [requested_cursor(p) for p in self.paths]

    def _next(self) -> Behaviour:
        index = min(len(self.paths) - 1, len(self._behaviours) - 1)
        return self._behaviours[index]

    def _process_request(self, connection: ServerConnection, request: Request) -> Response | None:
        self.paths.append(request.path)
        self.user_agents.append(request.headers.get("User-Agent"))
        behaviour = self._next()
        self._assigned[id(connection)] = behaviour
        if behaviour.status is None:
            return None
        body = b""
        headers = Headers()
        if behaviour.error_name is not None:
            body = json.dumps({"error": behaviour.error_name, "message": "loopback"}).encode()
            headers["Content-Type"] = "application/json"
        headers["Content-Length"] = str(len(body))
        reason = REASONS.get(behaviour.status, "Error")
        return Response(behaviour.status, reason, headers, body)

    async def _handler(self, ws: ServerConnection) -> None:
        behaviour = self._assigned.pop(id(ws))
        cursor = requested_cursor(ws.request.path) if ws.request is not None else None
        frames = [text for t, text in self._frames if cursor is None or t >= cursor]
        if behaviour.send is not None:
            frames = frames[: behaviour.send]
        if behaviour.info_first is not None:
            info = {
                "$type": "message",
                "payload": {"$type": INFO_TYPE, "name": behaviour.info_first},
            }
            await ws.send(json.dumps(info))
        for text in frames:
            await ws.send(text)
        if behaviour.then == "silent":
            await ws.wait_closed()
        elif behaviour.then == "error_frame":
            await ws.send(json.dumps({"$type": "error", "error": "ConsumerTooSlow"}))
            await ws.close(1008)
        elif behaviour.then == "oversize":
            await ws.send("x" * (2 * 1024 * 1024 + 16))
            await ws.wait_closed()
        else:
            await ws.close(behaviour.close_code)

    async def __aenter__(self) -> LoopbackJetstream:
        self._server = await serve(
            self._handler,
            "127.0.0.1",
            0,
            subprotocols=["xrpc.v1.json"],  # type: ignore[list-item]
            process_request=self._process_request,
            max_size=None,
        )
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._server is not None:
            self._server.close()
            await asyncio.wait_for(self._server.wait_closed(), 5)
