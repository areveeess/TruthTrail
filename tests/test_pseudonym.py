"""The keyed pseudonymiser (D-17, scheme d17-hmac-v1, ONE-WAY: confirmed by the owner).

The expected values are recomputed here independently with hashlib, hmac and base64, never by
calling the module under test, so a change of prefix, length, alphabet or encoding fails. Every
secret is generated at runtime; no key material is written in this file. Failure texts are checked
with a marker so no message, repr or str can ever carry the secret or the input.
"""

import base64
import hashlib
import hmac
import re
import secrets

import pytest
from conftest import FAKE_PSEUDONYM_SECRET
from pydantic import SecretStr

from truthtrail.core.config import ConfigurationError
from truthtrail.ingest.pseudonym import (
    ACCOUNT_KEY_CHARS,
    INVALID_MESSAGE,
    MISSING_MESSAGE,
    SCHEME,
    URI_KEY_CHARS,
    Keyer,
    make_keyer,
    parse_secret,
)

BASE32_LOWER = re.compile(r"[a-z2-7]+")
HEX32 = re.compile(r"[0-9a-f]{32}")
ROOT_URI_1 = "at://did:plc:aaaaaaaaaaaaaaaaaaaaaaa4/app.bsky.feed.post/2222222222223"
ROOT_URI_2 = "at://did:web:example.invalid/app.bsky.feed.repost/2222222222222"
DID_1 = "did:plc:aaaaaaaaaaaaaaaaaaaaaaa2"
DID_2 = "did:web:example.invalid"


def expected(secret: bytes, domain: bytes, value: str, chars: int) -> str:
    """Independent recomputation of the D-17 scheme."""
    digest = hmac.new(secret, domain + b"\x00" + value.encode("utf-8"), hashlib.sha256).digest()
    return base64.b32encode(digest).decode("ascii").lower().rstrip("=")[:chars]


def fresh_secret() -> bytes:
    return secrets.token_bytes(32)


def test_scheme_name_and_lengths_are_the_ratified_ones() -> None:
    assert SCHEME == "d17-hmac-v1"
    assert (URI_KEY_CHARS, ACCOUNT_KEY_CHARS) == (20, 16)


@pytest.mark.parametrize("value", [ROOT_URI_1, ROOT_URI_2, "at://did:plc:x/app.bsky.feed.post/y"])
def test_uri_key_known_answer(value: str) -> None:
    secret = fresh_secret()
    assert make_keyer(secret).uri_key(value) == expected(secret, b"uri", value, 20)


@pytest.mark.parametrize("value", [DID_1, DID_2, "did:plc:zzzzzzzzzzzzzzzzzzzzzzzz"])
def test_account_key_known_answer(value: str) -> None:
    secret = fresh_secret()
    assert make_keyer(secret).account_key(value) == expected(secret, b"acct", value, 16)


def test_known_answer_under_the_session_fake_secret(keyer: Keyer) -> None:
    secret = parse_secret(FAKE_PSEUDONYM_SECRET)
    assert keyer.uri_key(ROOT_URI_1) == expected(secret, b"uri", ROOT_URI_1, 20)
    assert keyer.account_key(DID_1) == expected(secret, b"acct", DID_1, 16)


def test_outputs_are_lowercase_base32_of_the_stated_lengths_never_hex(keyer: Keyer) -> None:
    for index in range(200):
        uri = f"at://did:plc:{index:024d}/app.bsky.feed.post/{index:013d}"
        uri_key = keyer.uri_key(uri)
        account = keyer.account_key(f"did:plc:{index:024d}")
        assert len(uri_key) == 20
        assert BASE32_LOWER.fullmatch(uri_key)
        assert len(account) == 16
        assert BASE32_LOWER.fullmatch(account)
        assert not HEX32.fullmatch(uri_key)
        assert not HEX32.fullmatch(account)


def test_determinism_and_a_rebuilt_keyer_agree() -> None:
    secret = fresh_secret()
    first, second = make_keyer(secret), make_keyer(secret)
    assert first.uri_key(ROOT_URI_1) == first.uri_key(ROOT_URI_1) == second.uri_key(ROOT_URI_1)
    assert first.account_key(DID_1) == second.account_key(DID_1)


def test_domain_separation(keyer: Keyer) -> None:
    text = DID_1
    assert keyer.uri_key(text)[:16] != keyer.account_key(text)


def test_different_secrets_give_different_keys() -> None:
    first, second = make_keyer(fresh_secret()), make_keyer(fresh_secret())
    assert first.uri_key(ROOT_URI_1) != second.uri_key(ROOT_URI_1)
    assert first.account_key(DID_1) != second.account_key(DID_1)


def test_one_flipped_character_changes_the_key(keyer: Keyer) -> None:
    flipped = ROOT_URI_1[:-1] + "4"
    assert keyer.uri_key(flipped) != keyer.uri_key(ROOT_URI_1)
    assert keyer.account_key(DID_1[:-1] + "3") != keyer.account_key(DID_1)


def test_the_uri_is_keyed_exactly_as_received_without_case_folding(keyer: Keyer) -> None:
    assert keyer.uri_key(ROOT_URI_1.upper()) != keyer.uri_key(ROOT_URI_1)


def test_make_keyer_accepts_a_secretstr_and_agrees_with_bytes() -> None:
    raw = fresh_secret()
    text = base64.urlsafe_b64encode(raw).decode("ascii")
    assert make_keyer(SecretStr(text)).uri_key(ROOT_URI_1) == make_keyer(raw).uri_key(ROOT_URI_1)


def test_make_keyer_rejects_short_bytes_without_echoing_them() -> None:
    short = secrets.token_bytes(31)
    with pytest.raises(ConfigurationError) as info:
        make_keyer(short)
    assert str(info.value) == INVALID_MESSAGE
    assert short.hex() not in str(info.value)


# ----------------------------------------------------------------------------- parse_secret


def _b64url(raw: bytes, *, padded: bool) -> str:
    text = base64.urlsafe_b64encode(raw).decode("ascii")
    return text if padded else text.rstrip("=")


def test_parse_secret_accepts_base64url_with_and_without_padding_and_hex() -> None:
    # 32 bytes make a padded base64 form, so the unpadded variant is a real difference.
    raw = secrets.token_bytes(32)
    padded, unpadded = _b64url(raw, padded=True), _b64url(raw, padded=False)
    assert padded != unpadded
    assert parse_secret(padded) == raw
    assert parse_secret(unpadded) == raw
    assert parse_secret(raw.hex()) == raw
    assert parse_secret(raw.hex().upper()) == raw
    assert parse_secret(f"  {unpadded}\n") == raw


def _marker_value() -> str:
    """A distinctive base64url value of 31 decoded bytes (one too few)."""
    return _b64url(b"MARKER" + secrets.token_bytes(25), padded=False)


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda: None, MISSING_MESSAGE),
        (lambda: "", MISSING_MESSAGE),
        (lambda: "   \t", MISSING_MESSAGE),
        (_marker_value, INVALID_MESSAGE),
        (lambda: secrets.token_bytes(31).hex(), INVALID_MESSAGE),
        (lambda: "MARKER" + "!" * 40, INVALID_MESSAGE),
        (lambda: "MARKER" + "a" * 40 + "=" * 3, INVALID_MESSAGE),
        (lambda: "MARKER" + "a" * 39, INVALID_MESSAGE),
        (lambda: "MARKER é" * 8, INVALID_MESSAGE),
    ],
    ids=[
        "none",
        "blank",
        "whitespace",
        "31-bytes-base64url",
        "31-bytes-hex",
        "invalid-characters",
        "too-much-padding",
        "impossible-base64-length",
        "non-ascii",
    ],
)
def test_parse_secret_rejects_with_a_fixed_text_that_never_echoes_the_input(make, message) -> None:  # type: ignore[no-untyped-def]
    value = make()
    with pytest.raises(ConfigurationError) as info:
        parse_secret(value)
    assert str(info.value) == message
    assert "MARKER" not in str(info.value)
    if value and value.strip():
        assert value.strip() not in str(info.value)
    assert info.value.__cause__ is None


def test_messages_name_the_variable_and_never_contain_a_value() -> None:
    assert "PSEUDONYM_SECRET" in MISSING_MESSAGE
    assert "PSEUDONYM_SECRET" in INVALID_MESSAGE


def test_keyer_repr_and_str_hide_the_secret() -> None:
    raw = fresh_secret()
    keyer = make_keyer(raw)
    shown = repr(keyer) + str(keyer)
    for form in (raw.hex(), _b64url(raw, padded=False), _b64url(raw, padded=True)):
        assert form not in shown
    assert shown == "Keyer(scheme='d17-hmac-v1')" * 2
    public = {name for name in dir(keyer) if not name.startswith("_")}
    assert public == {"uri_key", "account_key"}


def test_keyer_is_frozen() -> None:
    keyer = make_keyer(fresh_secret())
    with pytest.raises(AttributeError):
        keyer.uri_key = lambda value: value  # type: ignore[method-assign]
