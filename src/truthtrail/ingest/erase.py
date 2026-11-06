"""The operator erase command: tombstone every stored row of an account (D-16, D-17, T-03-38).

It is the operator path for a delete the collector missed (an ingest gap) and the Bluesky
Developer Guidelines' "method for deleting content a user has requested to be deleted" (RESEARCH
Open Question 16). DIDs come from standard input only, one per line, so a DID never enters shell
history or a process listing; each line is validated against a did:plc or did:web pattern and an
invalid line is counted, never echoed. The DID is turned into its pseudonym with the collector's
Keyer and the account's rows are tombstoned through the writer's account-wide path (the same
minimal tombstone, root deletes unlink their claim), under the ingest advisory lock so it never
races a collector run. Only counts are returned and printed.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.engine import Engine

from truthtrail.db.locks import INGEST_LOCK_KEY, release_advisory_lock, try_advisory_lock
from truthtrail.ingest.pseudonym import Keyer
from truthtrail.ingest.writer import Batch, flush

ERASE_CAUSE = "erase"
ERASE_SOURCE = "erase"
MAX_LINES = 10_000
# did:plc identifiers are 24 lowercase base32 characters; did:web is a hostname with optional
# percent-encoded port and colon-separated path segments.
_DID = re.compile(
    r"did:plc:[a-z2-7]{24}|did:web:[A-Za-z0-9.-]{1,253}(?:%3[Aa][0-9]{1,5})?(?::[A-Za-z0-9._-]+)*"
)


class EraseLocked(RuntimeError):
    """Another ingest or erase run holds the ingest lock."""


@dataclass(frozen=True, slots=True)
class EraseResult:
    """Counts only (D-18)."""

    lines: int
    invalid: int
    accounts_matched: int
    accounts_unknown: int
    rows_tombstoned: int
    roots_deleted: int

    def line(self) -> str:
        return (
            f"erase lines={self.lines} invalid={self.invalid} matched={self.accounts_matched}"
            f" unknown={self.accounts_unknown} tombstoned={self.rows_tombstoned}"
            f" roots_deleted={self.roots_deleted}"
        )


def is_did(value: str) -> bool:
    """True when ``value`` is a well-formed did:plc or did:web identifier."""
    return _DID.fullmatch(value) is not None


def erase_dids(
    engine: Engine,
    keyer: Keyer,
    lines: Iterable[str],
    *,
    now: datetime | None = None,
) -> EraseResult:
    """Tombstone every stored row of each DID in ``lines``; raises ``EraseLocked``."""
    at = now or datetime.now(UTC)
    total = invalid = 0
    batch = Batch()
    for raw in lines:
        value = raw.strip()
        if not value:
            continue
        total += 1
        if total > MAX_LINES:
            raise ValueError(f"erase accepts at most {MAX_LINES} lines")
        if not is_did(value):
            invalid += 1
            continue
        batch.account_tombstones.setdefault(keyer.account_key(value), (ERASE_CAUSE, at))
    with engine.connect() as lock:
        if not try_advisory_lock(lock, INGEST_LOCK_KEY):
            raise EraseLocked("another ingest or erase run is active")
        try:
            result = flush(engine, batch, source=ERASE_SOURCE, dialect="v2", host="operator")
        finally:
            release_advisory_lock(lock, INGEST_LOCK_KEY)
    requested = len(batch.account_tombstones)
    return EraseResult(
        lines=total,
        invalid=invalid,
        accounts_matched=requested - result.account_actions_unmatched,
        accounts_unknown=result.account_actions_unmatched,
        rows_tombstoned=result.tombstoned,
        roots_deleted=result.roots_deleted,
    )
