"""The collector CLI: a bounded batch job (D-10, D-11, D-16, D-17, D-30).

Usage:

    python -m truthtrail.ingest run [--max-seconds N] [--max-events N] [--max-stored N]
                                    [--replay MANIFEST|packaged] [--batch-rows N]
                                    [--batch-delay-seconds S] [--source-name NAME]
    python -m truthtrail.ingest erase        # DIDs on standard input, one per line

``run`` streams the public Jetstream (live) or replays a recorded-real manifest (``packaged`` is
the recording shipped in the package) and stops at the first bound; every default comes from the
Policy (environment-overridable, D-03). ``erase`` tombstones every stored row of the accounts
whose DIDs arrive on standard input; a DID is never accepted as an argument.

Environment: ``DATABASE_URL`` and ``PSEUDONYM_SECRET`` (required), ``COLLECTOR_CONTACT``
(optional, sent in the User-Agent), plus any Policy variable. The API's settings (and its news
key) are never read.

Exit codes:

    0  normal stop, including a reached bound, capacity_reached and an interrupted run
    2  usage error (unknown subcommand or argument; the argument is never echoed)
    3  configuration error (the message names the variable, never the value)
    4  source failure: reconnect budget spent, HTTP 401 or 403, an oversize frame, a rejection
    5  database failure
    6  another run is active (the ingest advisory lock is held)

No POSIX signal handler is installed; Ctrl+C ends the run as ``interrupted`` after the final
flush. Output is one line of counts; nothing personal is ever printed.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.exc import ArgumentError, SQLAlchemyError

from truthtrail.core.config import ConfigurationError, get_ingest_settings
from truthtrail.core.policy import Policy, get_policy
from truthtrail.db.engine import create_db_engine
from truthtrail.ingest.erase import EraseLocked, erase_dids
from truthtrail.ingest.pseudonym import Keyer, make_keyer
from truthtrail.ingest.run import (
    EXIT_CONFIG,
    EXIT_DATABASE,
    EXIT_LOCKED,
    EXIT_OK,
    LIVE_SOURCE_NAME,
    REPLAY_SOURCE_NAME,
    RunBounds,
    run_ingest,
)
from truthtrail.ingest.selection import load_allowlist
from truthtrail.ingest.source import (
    DEFAULT_MANIFEST,
    EventSource,
    JetstreamSource,
    ReplayRefused,
    ReplaySource,
)

EXIT_USAGE = 2
PACKAGED = "packaged"


class _Parser(argparse.ArgumentParser):
    """An argument parser whose errors never echo the offending argument (a DID, T-03-38)."""

    def error(self, message: str) -> None:  # type: ignore[override]
        self.exit(EXIT_USAGE, f"{self.prog}: usage error (see --help)\n")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="python -m truthtrail.ingest", description="TruthTrail collector")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    run = commands.add_parser("run", help="run the bounded collector once")
    run.add_argument("--max-seconds", type=float, default=None)
    run.add_argument("--max-events", type=int, default=None)
    run.add_argument("--max-stored", type=int, default=None)
    run.add_argument("--replay", default=None, help="a recording manifest, or 'packaged'")
    run.add_argument("--batch-rows", type=int, default=None)
    run.add_argument("--batch-delay-seconds", type=float, default=0.0)
    run.add_argument("--source-name", default=None)
    commands.add_parser("erase", help="tombstone the accounts whose DIDs arrive on stdin")
    return parser


def bounds_from_args(args: argparse.Namespace, policy: Policy) -> RunBounds:
    """Bounds: an argument when given, otherwise the Policy value."""
    return RunBounds.from_policy(
        policy,
        max_seconds=args.max_seconds,
        max_events=args.max_events,
        max_stored=args.max_stored,
        batch_rows=args.batch_rows,
        batch_delay_seconds=args.batch_delay_seconds,
    )


def _say(text: str) -> None:
    print(text, file=sys.stderr)


def _source(
    args: argparse.Namespace, policy: Policy, keyer: Keyer, contact: str | None
) -> EventSource:
    if args.replay is not None:
        manifest = DEFAULT_MANIFEST if args.replay == PACKAGED else Path(args.replay)
        return ReplaySource(manifest, keyer)
    return JetstreamSource(
        policy.ingest_hosts,
        policy.ingest_dialect,
        keyer,
        rewind_seconds=policy.ingest_rewind_seconds,
        contact=contact,
    )


def _invalid_bounds(args: argparse.Namespace) -> bool:
    values = (args.max_seconds, args.max_events, args.max_stored, args.batch_rows)
    return any(v is not None and v <= 0 for v in values) or args.batch_delay_seconds < 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the documented exit code."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    if args.command == "erase" and sys.stdin.isatty():
        _say("erase reads DIDs from standard input, one per line")
    try:
        settings = get_ingest_settings()
        keyer = make_keyer(settings.pseudonym_secret)
        policy = get_policy()
        if args.command == "run":
            if _invalid_bounds(args):
                raise ConfigurationError("run bounds must be positive numbers")
            load_allowlist(policy.track_allowlist_file)  # fail fast on a bad allowlist file
            source = _source(args, policy, keyer, settings.collector_contact)
        engine = create_db_engine(settings.database_url, role="collector", pool_size=2)
    except ConfigurationError as exc:
        _say(f"configuration error: {exc}")
        return EXIT_CONFIG
    except ReplayRefused as exc:
        _say(f"configuration error: {exc}")
        return EXIT_CONFIG
    except (OSError, ValueError, ArgumentError) as exc:
        _say(f"configuration error: {type(exc).__name__}")
        return EXIT_CONFIG
    try:
        if args.command == "erase":
            return _erase(engine, keyer)
        name = args.source_name or (
            REPLAY_SOURCE_NAME if source.mode == "replay" else LIVE_SOURCE_NAME
        )
        try:
            summary = asyncio.run(
                run_ingest(
                    engine, source, policy, bounds=bounds_from_args(args, policy), source_name=name
                )
            )
        except KeyboardInterrupt:  # the run row was finalised by the loop
            print("ingest status=interrupted")
            return EXIT_OK
        print(summary.line())
        return summary.exit_code
    finally:
        engine.dispose()


def _erase(engine: Engine, keyer: Keyer) -> int:
    try:
        result = erase_dids(engine, keyer, sys.stdin)
    except EraseLocked:
        _say("another ingest or erase run is active")
        return EXIT_LOCKED
    except ValueError as exc:
        _say(f"erase refused: {exc}")
        return EXIT_USAGE
    except SQLAlchemyError as exc:
        _say(f"database error: {type(exc).__name__}")
        return EXIT_DATABASE
    print(result.line())
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - exercised through subprocess tests
    raise SystemExit(main())
