"""JetstreamSource against a loopback WebSocket server that serves real recorded frames (D-05,
D-06, D-07, D-09; RESEARCH Pattern 2, Pattern 12, F-02, F-04, F-20).

No test reaches the real Jetstream: every connection goes to 127.0.0.1 with ``proxy=None``, and
sleep, jitter and silence are injected, so nothing waits longer than milliseconds.
"""

import asyncio
import socket
from collections import Counter
from typing import Any

import pytest
from conftest import fixture_items, recorded_frames
from loopback_server import Behaviour, LoopbackJetstream, frame_time_us

from truthtrail.ingest.dialect import ErrorFrame, InfoFrame
from truthtrail.ingest.source import (
    GAP_CURSOR_TOO_OLD,
    GAP_OUTDATED_CURSOR,
    REPOSITORY_URL,
    DropCounter,
    GapNotice,
    JetstreamSource,
    SourceFailed,
    SourceForbidden,
    SourceRejected,
    connect_default,
    user_agent,
)

PRIMARY = "jetstream-a.loopback.test"
SECONDARY = "jetstream-b.loopback.test"
REWIND = 30


def _frames(n: int | None = None) -> list[dict[str, Any]]:
    """The first ``n`` real commit frames of the recording (each carries a stream time)."""
    found = []
    for frame in recorded_frames():
        if "operation" in frame["payload"]:
            found.append(frame)
            if n is not None and len(found) >= n:
                break
    return found


class Recorder:
    """Injected sleep: records the delays and yields to the loop without waiting."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)
        await asyncio.sleep(0)


def _source(
    keyer: Any,
    bases: dict[str, str],
    *,
    hosts: tuple[str, ...] = (PRIMARY,),
    sleep: Recorder | None = None,
    jitter: Any = None,
    **kwargs: Any,
) -> JetstreamSource:
    return JetstreamSource(
        hosts,
        "v2",
        keyer,
        rewind_seconds=REWIND,
        proxy=None,
        sleep=sleep or Recorder(),
        jitter=jitter or (lambda low, high: high),
        base_urls=bases,
        **kwargs,
    )


async def _collect(
    source: JetstreamSource, cursor: int | None, limit: int, drops: DropCounter | None = None
) -> tuple[list[Any], BaseException | None]:
    got: list[Any] = []
    stream = source.items(cursor, drops)
    try:
        async for item in stream:
            got.append(item)
            if len(got) >= limit:
                break
    except Exception as exc:  # the test inspects the exact type
        return got, exc
    finally:
        await stream.aclose()
    return got, None


def run(coro: Any) -> Any:
    """Run a scenario with a hard bound, so a regression fails fast instead of hanging."""

    async def bounded() -> Any:
        return await asyncio.wait_for(coro, 15)

    return asyncio.run(bounded())


def test_a_full_replay_arrives_as_the_same_items_as_replay_source(keyer: Any) -> None:
    frames = list(recorded_frames())
    expected = fixture_items(keyer)

    async def scenario() -> tuple[list[Any], DropCounter]:
        drops = DropCounter()
        async with LoopbackJetstream(frames, [Behaviour(then="silent")]) as server:
            got, error = await _collect(
                _source(keyer, {PRIMARY: server.base}), None, len(expected), drops
            )
        assert error is None
        return got, drops

    got, drops = run(scenario())
    assert Counter(type(i.result).__name__ for i in got) == Counter(
        type(i.result).__name__ for i in expected
    )
    assert [i.result for i in got] == [i.result for i in expected]
    assert drops.as_dict() == {"account_status_ignored": 12}


def test_a_reconnect_resumes_from_the_last_stream_time_minus_the_rewind(keyer: Any) -> None:
    frames = _frames(30)

    async def scenario() -> tuple[list[Any], LoopbackJetstream]:
        behaviours = [Behaviour(send=10, close_code=1011), Behaviour(then="silent")]
        resume = max(frame_time_us(f) for f in frames[:10]) - REWIND * 1_000_000
        again = sum(1 for f in frames if frame_time_us(f) >= resume)
        async with LoopbackJetstream(frames, behaviours) as server:
            got, error = await _collect(_source(keyer, {PRIMARY: server.base}), None, 10 + again)
        assert error is None
        return got, server

    got, server = run(scenario())
    last = max(frame_time_us(f) for f in frames[:10])
    assert server.cursors == [None, last - REWIND * 1_000_000]
    first_ten = [i.result for i in got[:10]]
    assert any(r in first_ten for r in (i.result for i in got[10:]))  # the overlap arrives again


@pytest.mark.parametrize("status", [401, 403])
def test_an_auth_refusal_is_fatal_after_one_attempt(keyer: Any, status: int) -> None:
    sleep = Recorder()

    async def scenario() -> tuple[BaseException | None, LoopbackJetstream]:
        async with LoopbackJetstream(_frames(3), [Behaviour(status=status)]) as server:
            _got, error = await _collect(
                _source(keyer, {PRIMARY: server.base}, sleep=sleep), None, 5
            )
        return error, server

    error, server = run(scenario())
    assert isinstance(error, SourceForbidden)
    assert len(server.paths) == 1
    assert sleep.delays == []


def test_cursor_too_old_continues_at_the_tip_and_yields_a_gap(keyer: Any) -> None:
    requested = frame_time_us(_frames(1)[0]) - 10**12

    async def scenario() -> tuple[list[Any], LoopbackJetstream]:
        behaviours = [
            Behaviour(status=400, error_name="CursorTooOld"),
            Behaviour(send=3, then="silent"),
        ]
        async with LoopbackJetstream(_frames(5), behaviours) as server:
            got, error = await _collect(_source(keyer, {PRIMARY: server.base}), requested, 4)
        assert error is None
        return got, server

    got, server = run(scenario())
    assert server.cursors == [requested, None]
    assert got[0].result == GapNotice(requested, None, GAP_CURSOR_TOO_OLD)
    assert got[0].cursor_us is None
    assert all(i.cursor_us is not None for i in got[1:])


def test_another_http_400_is_rejected_without_retry(keyer: Any) -> None:
    async def scenario() -> tuple[BaseException | None, LoopbackJetstream]:
        behaviours = [Behaviour(status=400, error_name="InvalidRequest")]
        async with LoopbackJetstream(_frames(3), behaviours) as server:
            _got, error = await _collect(_source(keyer, {PRIMARY: server.base}), 5, 5)
        return error, server

    error, server = run(scenario())
    assert isinstance(error, SourceRejected)
    assert len(server.paths) == 1


def test_an_outdated_cursor_frame_yields_a_gap_and_moves_no_cursor(keyer: Any) -> None:
    requested = frame_time_us(_frames(1)[0])

    async def scenario() -> list[Any]:
        behaviours = [Behaviour(info_first="OutdatedCursor", send=3, then="silent")]
        async with LoopbackJetstream(_frames(5), behaviours) as server:
            got, error = await _collect(_source(keyer, {PRIMARY: server.base}), requested, 5)
        assert error is None
        return got

    got = run(scenario())
    assert got[0].result == InfoFrame("OutdatedCursor")
    assert got[1].result == GapNotice(requested, None, GAP_OUTDATED_CURSOR)
    assert got[0].cursor_us is None
    assert got[1].cursor_us is None
    assert [i.cursor_us for i in got[2:]] == [frame_time_us(f) for f in _frames(3)]


def test_control_frames_never_carry_a_cursor(keyer: Any) -> None:
    async def scenario() -> list[Any]:
        behaviours = [
            Behaviour(info_first="FutureCursor", send=2, then="error_frame"),
            Behaviour(then="silent"),
        ]
        async with LoopbackJetstream(_frames(4), behaviours) as server:
            got, _error = await _collect(_source(keyer, {PRIMARY: server.base}), None, 5)
        return got

    got = run(scenario())
    controls = [i for i in got if isinstance(i.result, InfoFrame | ErrorFrame | GapNotice)]
    assert controls
    assert all(i.cursor_us is None for i in controls)


def test_backoff_has_full_jitter_bounds_grows_to_the_cap_and_fails_after_eight(
    keyer: Any,
) -> None:
    upper, lower = Recorder(), Recorder()

    async def scenario(sleep: Recorder, jitter: Any) -> tuple[BaseException | None, int]:
        async with LoopbackJetstream(_frames(1), [Behaviour(status=503)]) as server:
            source = _source(keyer, {PRIMARY: server.base}, sleep=sleep, jitter=jitter)
            _got, error = await _collect(source, None, 1)
        return error, len(server.paths)

    error, attempts = run(scenario(upper, lambda low, high: high))
    assert isinstance(error, SourceFailed)
    assert str(error) == "reconnect_budget"
    assert attempts == 8
    assert upper.delays == [1, 2, 4, 8, 16, 32, 60]
    run(scenario(lower, lambda low, high: low))
    assert lower.delays == [0] * 7


def test_backoff_resets_after_a_connection_that_delivered_an_event(keyer: Any) -> None:
    sleep = Recorder()

    async def scenario() -> None:
        behaviours = [
            Behaviour(status=503),
            Behaviour(status=503),
            Behaviour(send=2, close_code=1011),
            Behaviour(status=503),
            Behaviour(then="silent"),
        ]
        async with LoopbackJetstream(_frames(5), behaviours) as server:
            got, error = await _collect(
                _source(keyer, {PRIMARY: server.base}, sleep=sleep), None, 4
            )
        assert error is None
        assert len(got) == 4

    run(scenario())
    assert sleep.delays == [1, 2, 1, 2]


def test_a_silent_server_is_declared_dead_and_reconnected(keyer: Any) -> None:
    async def scenario() -> LoopbackJetstream:
        behaviours = [Behaviour(send=2, then="silent"), Behaviour(then="silent")]
        async with LoopbackJetstream(_frames(6), behaviours) as server:
            source = _source(keyer, {PRIMARY: server.base}, silence_seconds=0.05)
            got, error = await _collect(source, None, 4)
        assert error is None
        assert len(got) == 4
        return server

    server = run(scenario())
    assert len(server.paths) == 2
    assert server.cursors[1] == frame_time_us(_frames(2)[1]) - REWIND * 1_000_000


def test_a_consumer_too_slow_error_frame_leads_to_a_reconnect(keyer: Any) -> None:
    async def scenario() -> tuple[list[Any], LoopbackJetstream]:
        behaviours = [Behaviour(send=2, then="error_frame"), Behaviour(then="silent")]
        async with LoopbackJetstream(_frames(4), behaviours) as server:
            got, error = await _collect(_source(keyer, {PRIMARY: server.base}), None, 5)
        assert error is None
        return got, server

    got, server = run(scenario())
    assert ErrorFrame("ConsumerTooSlow") in [i.result for i in got]
    assert len(server.paths) == 2


def test_an_oversize_frame_close_is_fatal_without_a_reconnect_loop(keyer: Any) -> None:
    sleep = Recorder()

    async def scenario() -> tuple[BaseException | None, LoopbackJetstream]:
        async with LoopbackJetstream(_frames(2), [Behaviour(send=1, then="oversize")]) as server:
            _got, error = await _collect(
                _source(keyer, {PRIMARY: server.base}, sleep=sleep), None, 5
            )
        return error, server

    error, server = run(scenario())
    assert isinstance(error, SourceFailed)
    assert str(error) == "oversize_frame"
    assert len(server.paths) == 1
    assert sleep.delays == []


def test_failover_moves_to_the_second_host_with_the_timestamp_cursor(keyer: Any) -> None:
    frames = _frames(8)

    async def scenario() -> tuple[LoopbackJetstream, LoopbackJetstream, JetstreamSource]:
        first_behaviours = [Behaviour(send=3, close_code=1011), Behaviour(status=503)]
        async with (
            LoopbackJetstream(frames, first_behaviours) as first,
            LoopbackJetstream(frames, [Behaviour(then="silent")]) as second,
        ):
            source = _source(
                keyer, {PRIMARY: first.base, SECONDARY: second.base}, hosts=(PRIMARY, SECONDARY)
            )
            got, error = await _collect(source, None, 6)
        assert error is None
        assert len(got) == 6
        return first, second, source

    first, second, source = run(scenario())
    assert len(first.paths) == 2
    assert len(second.paths) == 1
    assert source.host == SECONDARY
    assert second.cursors == [frame_time_us(frames[2]) - REWIND * 1_000_000]


def test_the_user_agent_names_the_collector_and_carries_no_credential(keyer: Any) -> None:
    async def scenario() -> LoopbackJetstream:
        async with LoopbackJetstream(_frames(2), [Behaviour(then="silent")]) as server:
            source = _source(keyer, {PRIMARY: server.base}, contact="ops@example.org")
            await _collect(source, None, 1)
        return server

    server = run(scenario())
    agent = server.user_agents[0]
    assert agent is not None
    assert agent.startswith("TruthTrail/")
    assert REPOSITORY_URL in agent
    assert "ops@example.org" in agent
    assert agent == user_agent("ops@example.org")
    assert user_agent() == agent.replace("; ops@example.org", "")
    for marker in ("password", "token", "secret", "Bearer"):
        assert marker.lower() not in agent.lower()


def test_tls_verification_is_never_disabled(keyer: Any) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def recording_connect(uri: str, **kwargs: Any) -> Any:
        calls.append((uri, kwargs))
        return connect_default(uri, **kwargs)

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        closed_port = probe.getsockname()[1]
    source = JetstreamSource(
        (PRIMARY,),
        "v2",
        keyer,
        rewind_seconds=REWIND,
        failure_budget=1,
        proxy=None,
        connect=recording_connect,
        sleep=Recorder(),
        base_urls={PRIMARY: f"wss://127.0.0.1:{closed_port}"},
    )
    _got, error = run(_collect(source, None, 1))
    assert isinstance(error, SourceFailed)
    assert len(calls) == 1
    uri, kwargs = calls[0]
    assert uri.startswith("wss://")
    assert "ssl" not in kwargs
    assert "server_hostname" not in kwargs
    assert kwargs["max_size"] == 2 * 1024 * 1024
    assert kwargs["max_queue"] == 1024
    assert kwargs["open_timeout"] == 10
    assert kwargs["subprotocols"] == ["xrpc.v1.json"]


def test_a_source_needs_at_least_one_host(keyer: Any) -> None:
    with pytest.raises(ValueError, match="host"):
        JetstreamSource((), "v2", keyer, rewind_seconds=REWIND)


def test_the_live_source_reports_live_mode_and_its_dialect(keyer: Any) -> None:
    source = JetstreamSource((PRIMARY, SECONDARY), "v2", keyer, rewind_seconds=REWIND)
    assert source.mode == "live"
    assert source.dialect == "v2"
    assert source.host == PRIMARY
    assert [source.backoff_delay(n) <= min(60, 2 ** (n - 1)) for n in range(1, 10)] == [True] * 9
