"""The enrich and purge commands (D-10, D-16, D-18, D-22, OD-1).

Usage:

    python -m truthtrail.enrich run   [--as-of ISO] [--max-cascades N] [--force]
    python -m truthtrail.enrich purge [--as-of ISO] [--max-seconds S] [--dry-run]

``run`` resolves parents and rolls up every dirty cascade (``enrich.apply``); ``--as-of``
defaults to the stream time of the latest ingest checkpoint (``data_as_of``), ``--force``
re-enriches every cascade. ``purge`` applies the retention windows of the Policy
(``enrich.purge``); ``--as-of`` defaults to the current UTC time, because retention is kept in
real time even when ingestion stops, and ``--dry-run`` only counts. ``--as-of`` must carry a
UTC offset. Each command is idempotent and callable alone; Phase 3 ships them and Phase 6
schedules collect, then enrich, then purge.

Environment: ``DATABASE_URL`` (required) plus any Policy variable (``RETENTION_*``).
``PSEUDONYM_SECRET`` is never needed and never read, and the API's settings are never built.

Exit codes:

    0  ok (including nothing to do and a purge stopped by --max-seconds; rerun to finish)
    2  usage error (unknown subcommand or argument; the argument is never echoed)
    3  configuration error (the message names the variable, never the value)
    5  database failure (the exception class name only)
    6  another run is active (the enrich or purge advisory lock is held)

Output is one line of counts; nothing personal is ever printed. No signal handler is installed.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.engine import Engine
from sqlalchemy.exc import ArgumentError, SQLAlchemyError

from truthtrail.core.config import ConfigurationError, get_database_settings
from truthtrail.core.policy import Policy, get_policy
from truthtrail.db.engine import create_db_engine
from truthtrail.enrich.apply import DEFAULT_MAX_CASCADES, enrich_dirty
from truthtrail.enrich.purge import DEFAULT_MAX_SECONDS, purge

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_CONFIG = 3
EXIT_DATABASE = 5
EXIT_LOCKED = 6


class _Parser(argparse.ArgumentParser):
    """An argument parser whose errors never echo the offending argument."""

    def error(self, message: str) -> None:  # type: ignore[override]
        self.exit(EXIT_USAGE, f"{self.prog}: usage error (see --help)\n")


def _aware_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("--as-of needs a UTC offset")
    return parsed.astimezone(UTC)


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def _positive_float(value: str) -> float:
    number = float(value)
    if not number > 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="python -m truthtrail.enrich", description="TruthTrail enrich and purge")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    run = commands.add_parser("run", help="resolve parents and roll up the dirty cascades")
    run.add_argument("--as-of", type=_aware_timestamp, default=None)
    run.add_argument("--max-cascades", type=_positive_int, default=DEFAULT_MAX_CASCADES)
    run.add_argument("--force", action="store_true")
    retention = commands.add_parser("purge", help="apply the retention windows of the policy")
    retention.add_argument("--as-of", type=_aware_timestamp, default=None)
    retention.add_argument("--max-seconds", type=_positive_float, default=DEFAULT_MAX_SECONDS)
    retention.add_argument("--dry-run", action="store_true")
    return parser


def _say(text: str) -> None:
    print(text, file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the documented exit code."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    try:
        settings = get_database_settings()
        policy = get_policy()
        engine = create_db_engine(settings.database_url, role="jobs", pool_size=2)
    except ConfigurationError as exc:
        _say(f"configuration error: {exc}")
        return EXIT_CONFIG
    except (ValueError, ArgumentError) as exc:
        _say(f"configuration error: {type(exc).__name__}")
        return EXIT_CONFIG
    try:
        return _dispatch(engine, policy, args)
    except SQLAlchemyError as exc:
        _say(f"database error: {type(exc).__name__}")
        return EXIT_DATABASE
    finally:
        engine.dispose()


def _dispatch(engine: Engine, policy: Policy, args: argparse.Namespace) -> int:
    if args.command == "run":
        enriched = enrich_dirty(
            engine, as_of=args.as_of, max_cascades=args.max_cascades, force=args.force
        )
        print(enriched.line())
        return EXIT_LOCKED if enriched.locked else EXIT_OK
    as_of = args.as_of if args.as_of is not None else datetime.now(UTC)
    purged = purge(engine, policy, as_of=as_of, max_seconds=args.max_seconds, dry_run=args.dry_run)
    print(purged.line())
    return EXIT_LOCKED if purged.locked else EXIT_OK


if __name__ == "__main__":  # pragma: no cover - exercised through subprocess tests
    raise SystemExit(main())
