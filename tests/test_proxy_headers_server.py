"""A spoofed X-Forwarded-For never becomes the rate-limit key in a REAL uvicorn (D-10, T-02-21).

uvicorn's own proxy handling is on by default: ``--proxy-headers`` trusts 127.0.0.1, ::1 and
FORWARDED_ALLOW_IPS and replaces the client address with the X-Forwarded-For address before any
application code runs. TestClient never passes through that layer, so app-level tests cannot see
the hole. These tests start a real server in a subprocess. The supported start carries
``--no-proxy-headers`` (``SERVER_ARGS``), so the in-app middleware, enabled only by
TRUST_PROXY_HEADERS=true, is the single place proxy headers are trusted. The default-flags case is
a negative control: it shows the hole exists and that the first case is not vacuous. If a later
uvicorn bump makes the control fail, the premise changed: re-evaluate the start command, do not
delete the assertion. Plan 02-11's container test asserts the image CMD carries the same flag.
"""

import contextlib
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_ARGS = ["--no-proxy-headers"]
START_TIMEOUT = 30.0
REQUEST_TIMEOUT = 10.0
# Never go through a configured HTTP proxy for the loopback server.
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _status(url: str, headers: Mapping[str, str] | None = None) -> int:
    request = urllib.request.Request(url, headers=dict(headers or {}))
    try:
        with OPENER.open(request, timeout=REQUEST_TIMEOUT) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


@contextlib.contextmanager
def running_server(
    tmp_path: Path,
    subprocess_env: dict[str, str],
    case_env: Mapping[str, str],
    extra_args: Sequence[str],
) -> Iterator[str]:
    """Start ``uvicorn truthtrail.main:app`` and yield its base URL; always stop it."""
    port = _free_port()
    env = {
        **subprocess_env,
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "DEMO_MODE": "true",
        **case_env,
    }
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "truthtrail.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        *extra_args,
    ]
    process = subprocess.Popen(
        command,
        cwd=tmp_path,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + START_TIMEOUT
        while True:
            if process.poll() is not None:
                raise AssertionError("uvicorn exited before it became healthy")
            try:
                if _status(f"{base}/health") == 200:
                    break
            except OSError:
                pass
            if time.monotonic() > deadline:
                raise AssertionError("uvicorn did not become healthy in time")
            time.sleep(0.1)
        yield base
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def _spoofed(base: str, addresses: Sequence[str]) -> list[int]:
    return [
        _status(f"{base}/analyze?query=spoof", {"X-Forwarded-For": address})
        for address in addresses
    ]


DISTINCT = ["198.51.100.1", "198.51.100.2", "198.51.100.3"]


def test_spoofed_forwarded_for_is_not_the_key_with_no_proxy_headers(
    tmp_path: Path, subprocess_env: dict[str, str]
) -> None:
    """(a) Flag unset: three spoofed addresses from one loopback peer share one bucket."""
    with running_server(
        tmp_path, subprocess_env, {"RATE_LIMIT_ANALYZE": "2/minute"}, SERVER_ARGS
    ) as base:
        statuses = _spoofed(base, DISTINCT)

    assert statuses == [200, 200, 429]


def test_forwarded_for_from_a_trusted_peer_is_honoured_when_enabled(
    tmp_path: Path, subprocess_env: dict[str, str]
) -> None:
    """(b) TRUST_PROXY_HEADERS=true and a trusted peer: each address gets its own bucket."""
    case_env = {
        "RATE_LIMIT_ANALYZE": "1/minute",
        "TRUST_PROXY_HEADERS": "true",
        "FORWARDED_ALLOW_IPS": "127.0.0.1",
    }
    with running_server(tmp_path, subprocess_env, case_env, SERVER_ARGS) as base:
        statuses = _spoofed(base, DISTINCT)
        repeated = _spoofed(base, DISTINCT[:1])

    assert statuses == [200, 200, 200]
    assert repeated == [429]


def test_negative_control_uvicorn_default_flags_let_the_spoof_through(
    tmp_path: Path, subprocess_env: dict[str, str]
) -> None:
    """(c) Without --no-proxy-headers uvicorn trusts loopback and the spoof changes the key."""
    with running_server(tmp_path, subprocess_env, {"RATE_LIMIT_ANALYZE": "2/minute"}, []) as base:
        statuses = _spoofed(base, DISTINCT)

    assert statuses == [200, 200, 200]
