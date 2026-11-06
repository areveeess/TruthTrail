"""Keyed pseudonymiser for accounts and record URIs (D-17, scheme ``d17-hmac-v1``).

Every identifier that leaves the normaliser is a keyed hash, never a raw DID, handle, rkey or
``at://`` URI:

* account pseudonym = lowercase base32 of ``HMAC-SHA256(secret, b"acct" NUL did)``, first 16
  characters (80 bits);
* URI key = lowercase base32 of ``HMAC-SHA256(secret, b"uri" NUL canonical at:// URI)``, first 20
  characters (100 bits); the URI is used exactly as received (no case folding).

The two domain prefixes keep the account and URI spaces apart, so the same text never yields the
same value in both.

Why a keyed HMAC and not a plain or salted hash: the DID space is enumerable from the public
directory, so an unkeyed hash or a hash with a published salt is reversible by a dictionary
attack; a random per-row salt would break the equality joins the cascade needs (parent lookup,
unique accounts, delete matching). One server-side secret keeps the joins and resists the
dictionary. Why not the raw DID: an ``at://`` URI contains the author's DID, a stable global
identifier that joins to a handle and a full public history, which would make the database an
index of who engaged with which claim.

Honest limits: this is pseudonymisation, not anonymisation. With stored stream times (and root
text during its retention window) a party holding a network archive can still re-link a record,
and a leaked secret together with a leaked database re-enables dictionary reversal. Rotating the
secret re-keys every identifier, which is a rebuild (the raw values are never stored).

The secret is never logged, never part of an exception text, a ``repr`` or a ``str``, and the
``Keyer`` has no method that returns it. Only ingest and erase processes hold it; the API process
never imports this module (least privilege).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import re
from dataclasses import dataclass, field

from pydantic import SecretStr

from truthtrail.core.config import ConfigurationError

SCHEME = "d17-hmac-v1"
MIN_SECRET_BYTES = 32
ACCOUNT_KEY_CHARS = 16
URI_KEY_CHARS = 20
_ACCOUNT_DOMAIN = b"acct"
_URI_DOMAIN = b"uri"

MISSING_MESSAGE = "PSEUDONYM_SECRET is required for this command"
INVALID_MESSAGE = "PSEUDONYM_SECRET must decode to at least 32 bytes (base64url or hex)"

_HEX = re.compile(r"[0-9A-Fa-f]+")
_BASE64URL = re.compile(r"[A-Za-z0-9_-]+={0,2}")


def parse_secret(text: str | None) -> bytes:
    """Decode the secret from hex or base64url (padding optional); at least 32 bytes.

    Hex is tried first for a string of hex digits with an even length, so a 64-digit hex value
    means its 32 bytes, never the base64 decoding of the same characters. Raises
    ``ConfigurationError`` with a fixed text that never contains any part of the value.
    """
    if text is None or not text.strip():
        raise ConfigurationError(MISSING_MESSAGE)
    value = text.strip()
    decoded: bytes | None = None
    if len(value) % 2 == 0 and _HEX.fullmatch(value):
        decoded = bytes.fromhex(value)
    elif _BASE64URL.fullmatch(value):
        unpadded = value.rstrip("=")
        try:
            decoded = base64.urlsafe_b64decode(unpadded + "=" * (-len(unpadded) % 4))
        except (binascii.Error, ValueError):
            decoded = None
    if decoded is None or len(decoded) < MIN_SECRET_BYTES:
        raise ConfigurationError(INVALID_MESSAGE) from None
    return decoded


def _encode(digest: bytes, chars: int) -> str:
    return base64.b32encode(digest).decode("ascii").lower().rstrip("=")[:chars]


@dataclass(frozen=True, slots=True)
class Keyer:
    """Computes account pseudonyms and URI keys under one secret; never exposes the secret.

    Build it with ``make_keyer``. The HMAC key schedule is computed once and copied per call.
    """

    _base: hmac.HMAC = field(repr=False, compare=False)

    def _key(self, domain: bytes, value: str, chars: int) -> str:
        mac = self._base.copy()
        mac.update(domain + b"\0" + value.encode("utf-8"))
        return _encode(mac.digest(), chars)

    def uri_key(self, at_uri: str) -> str:
        """URI key of a canonical ``at://`` URI (20 lowercase base32 characters, 100 bits)."""
        return self._key(_URI_DOMAIN, at_uri, URI_KEY_CHARS)

    def account_key(self, did: str) -> str:
        """Account pseudonym of a DID (16 lowercase base32 characters, 80 bits)."""
        return self._key(_ACCOUNT_DOMAIN, did, ACCOUNT_KEY_CHARS)

    def __repr__(self) -> str:
        return f"Keyer(scheme={SCHEME!r})"

    __str__ = __repr__


def make_keyer(secret: bytes | SecretStr) -> Keyer:
    """Return a ``Keyer`` for decoded bytes; a ``SecretStr`` is decoded by ``parse_secret``."""
    raw = parse_secret(secret.get_secret_value()) if isinstance(secret, SecretStr) else secret
    if not isinstance(raw, bytes) or len(raw) < MIN_SECRET_BYTES:
        raise ConfigurationError(INVALID_MESSAGE)
    return Keyer(hmac.new(raw, digestmod=hashlib.sha256))
