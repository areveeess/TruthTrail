"""The autouse socket guard (D-28, T-03-12): loopback and unix sockets only.

Every address used here is either loopback or from the documentation ranges (RFC 5737
192.0.2.0/24 and 203.0.113.0/24), so even a broken guard sends nothing anywhere real.
"""

import socket
from pathlib import Path

import pytest
from conftest import LOOKUP_GUARD_MESSAGE, SOCKET_GUARD_MESSAGE, is_allowed_address

BLOCKED_HOST = "192.0.2.10"
BLOCKED_TCP = "203.0.113.5"


def test_connect_to_a_non_loopback_address_is_blocked() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        with pytest.raises(RuntimeError) as info:
            sock.connect((BLOCKED_HOST, 80))
    assert str(info.value) == SOCKET_GUARD_MESSAGE
    assert BLOCKED_HOST not in str(info.value)


def test_connect_ex_is_blocked_too() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        with pytest.raises(RuntimeError, match="socket guard"):
            sock.connect_ex((BLOCKED_HOST, 443))


def test_create_connection_to_a_non_loopback_address_is_blocked() -> None:
    with pytest.raises(RuntimeError) as info:
        socket.create_connection((BLOCKED_TCP, 80), timeout=0.2)
    assert str(info.value) == SOCKET_GUARD_MESSAGE
    assert BLOCKED_TCP not in str(info.value)


def test_loopback_listener_accepts_a_connection() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
            accepted, _peer = server.accept()
            with accepted:
                client.sendall(b"ping")
                assert accepted.recv(4) == b"ping"


def test_localhost_name_connects_through_create_connection() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        with socket.create_connection(("localhost", port), timeout=2):
            pass


def test_socketpair_works() -> None:
    left, right = socket.socketpair()
    with left, right:
        left.sendall(b"ok")
        assert right.recv(2) == b"ok"


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="no AF_UNIX on this platform")
def test_unix_socket_path_works(tmp_path: Path) -> None:
    path = str(tmp_path / "s")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(path)
        server.listen(1)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(path)
            accepted, _peer = server.accept()
            accepted.close()


def test_localhost_lookup_works_and_other_names_are_blocked() -> None:
    assert socket.getaddrinfo("localhost", 80)
    assert socket.getaddrinfo("127.0.0.1", 80)
    with pytest.raises(RuntimeError) as info:
        socket.getaddrinfo("example.com", 443)
    assert str(info.value) == LOOKUP_GUARD_MESSAGE
    assert "example.com" not in str(info.value)


@pytest.mark.parametrize(
    ("family", "address", "allowed"),
    [
        (socket.AF_INET, ("127.0.0.1", 1), True),
        (socket.AF_INET, ("127.255.0.9", 1), True),
        (socket.AF_INET, ("localhost", 1), True),
        (socket.AF_INET6, ("::1", 1, 0, 0), True),
        (socket.AF_INET6, ("::ffff:127.0.0.1", 1, 0, 0), True),
        (socket.AF_INET, ("0.0.0.0", 1), False),
        (socket.AF_INET, ("10.0.0.1", 1), False),
        (socket.AF_INET, ("192.0.2.1", 1), False),
        (socket.AF_INET6, ("2001:db8::1", 1, 0, 0), False),
        (socket.AF_INET, ("example.org", 1), False),
        (socket.AF_INET, "/tmp/tt-pg-x/.s.PGSQL.5432", True),  # a unix-socket path
    ],
)
def test_address_policy(family: int, address: object, allowed: bool) -> None:
    assert is_allowed_address(family, address) is allowed
