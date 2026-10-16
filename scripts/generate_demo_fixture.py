"""Generate the committed synthetic demo fixture from the unmodified simulator.

Usage (from the repository root):

    python scripts/generate_demo_fixture.py            # (re)write fixtures/demo_analyze.json
    python scripts/generate_demo_fixture.py --check    # exit 1 if the file is stale or hand-edited
    python scripts/generate_demo_fixture.py --path X   # use another file (with or without --check)

The output is deterministic: the global random state is seeded and restored, and
``uuid.uuid4`` inside the simulator is replaced by a seeded generator for the
duration of the build. Timestamps are re-based so no child event is earlier than
its parent, and every timestamp is written as UTC ISO-8601 with a Z suffix. The
simulator, user pools and keyword baseline are called as they are and never edited.
"""

import argparse
import json
import random
import sys
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import spread_simulator  # noqa: E402
from models import AnalyzeResponse  # noqa: E402
from risk_analyzer import analyze_risk  # noqa: E402
from spread_simulator import create_root_event, simulate_spread  # noqa: E402

SEED = 20261011
FIXTURE_PATH = REPO_ROOT / "fixtures" / "demo_analyze.json"
FIXTURE_DATA_AS_OF = "2026-10-11T12:00:00Z"
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

DEMO_ARTICLES = [
    {
        "title": "Example claim: miracle cure circulates in Example Town (synthetic demo)",
        "source": "Example News (synthetic demo)",
        "publishedAt": "2026-10-01T09:00:00Z",
    },
    {
        "title": "Example Town library extends weekend opening hours (synthetic demo)",
        "source": "Example News (synthetic demo)",
        "publishedAt": "2026-10-02T14:30:00Z",
    },
    {
        "title": "Example Town council statement on road repairs (synthetic demo)",
        "source": "Example News (synthetic demo)",
        "publishedAt": "2026-10-03T08:15:00Z",
    },
]


def _seeded_uuid4(rng: random.Random) -> Callable[[], uuid.UUID]:
    """Return a zero-argument callable yielding reproducible version-4 UUIDs."""

    def make() -> uuid.UUID:
        return uuid.UUID(int=rng.getrandbits(128), version=4)

    return make


def _parse_utc(value: str) -> datetime:
    """Parse a Z-suffixed or naive ISO timestamp, treating naive values as UTC."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _monotone_utc(events: list[dict]) -> list[dict]:
    """Re-base child timestamps on their parent's new time and format all as UTC Z.

    Each child keeps its original offset from the root, but is placed after its
    parent's new time, so every child is strictly later than its parent.
    """
    root_time = _parse_utc(events[0]["timestamp"])
    new_times: dict[str, datetime] = {events[0]["event_id"]: root_time}
    result = [{**events[0], "timestamp": root_time.strftime(TIME_FORMAT)}]
    for event in events[1:]:
        offset = _parse_utc(event["timestamp"]) - root_time
        parent_time = new_times[event["parent_event_id"]]
        child_time = parent_time + offset
        new_times[event["event_id"]] = child_time
        result.append({**event, "timestamp": child_time.strftime(TIME_FORMAT)})
    return result


def build_fixture() -> dict:
    """Build the fixture dict deterministically and validate it as an AnalyzeResponse."""
    saved_state = random.getstate()
    try:
        random.seed(SEED)
        fake_uuid4 = _seeded_uuid4(random.Random(SEED))
        results = []
        with mock.patch.object(spread_simulator.uuid, "uuid4", fake_uuid4):
            for article in DEMO_ARTICLES:
                risk = analyze_risk(article["title"])
                root = create_root_event(article)
                events = _monotone_utc(simulate_spread(root, risk))
                results.append(
                    {
                        "headline": article["title"],
                        "source": article["source"],
                        "published_at": article["publishedAt"],
                        "risk": risk,
                        "risk_method": "keyword_baseline",
                        "events": events,
                    }
                )
    finally:
        random.setstate(saved_state)
    fixture = {
        "results": results,
        "meta": {
            "synthetic": True,
            "data_as_of": FIXTURE_DATA_AS_OF,
            "source_status": "fixture",
        },
    }
    AnalyzeResponse.model_validate(fixture)
    return fixture


def render(fixture: dict) -> str:
    """Serialise the fixture exactly as it is committed (2-space JSON, trailing newline)."""
    return json.dumps(fixture, indent=2, ensure_ascii=False) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    """Write the fixture, or with --check compare it to the file on disk."""
    parser = argparse.ArgumentParser(description="Generate the synthetic demo fixture.")
    parser.add_argument("--check", action="store_true", help="fail if the file differs from a fresh build")
    parser.add_argument("--path", type=Path, default=FIXTURE_PATH, help="fixture file to write or check")
    args = parser.parse_args(argv)

    rendered = render(build_fixture())
    if args.check:
        try:
            current = args.path.read_text(encoding="utf-8")
        except OSError:
            current = None
        if current == rendered:
            sys.stdout.write("demo fixture is up to date\n")
            return 0
        sys.stderr.write(
            "demo fixture is stale or was edited by hand; "
            "regenerate with python scripts/generate_demo_fixture.py\n"
        )
        return 1

    args.path.parent.mkdir(parents=True, exist_ok=True)
    args.path.write_text(rendered, encoding="utf-8")
    sys.stdout.write("wrote demo fixture\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
