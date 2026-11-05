"""Machine gate for plans 03-02 to 03-12: has the owner ratified 03-SPIKE.md? (D-02, D-03, D-17).

Usage::

    python scripts/check_spike_ratified.py [--file PATH] [--json]

Exit codes: 0 ratified and consistent; 1 not ratified (or a required field or owner token is
missing); 2 the file or its front matter is malformed, a field holds a value outside its allowed
set, a ratified parameter is unknown or has the wrong type or range, a chosen option contradicts a
parameter value, or the parameters break the storage coupling (see ``check_capacity``); 3 ratified,
but the owner chose something the plans do not build (OD-2 M2, OD-3 C or a different identifier
scheme): the planner must revise plans 03-03 to 03-07, plus 03-02 (OD-3 C) and 03-10 (docs),
before they run.

Storage coupling (exit 2 when broken, a warning above the 60 percent design line)::

    TRACK_SAMPLE_PER_10K / 10000 x eligible_roots_per_day x RETENTION_CASCADE_DAYS x bytes_per_root
        <= 0.8 x DB_BUDGET_BYTES
    TRACK_MAX_ACTIVE_ROOTS >= ceil(1.5 x TRACK_ROOT_TTL_HOURS / 24 x eligible_roots_per_day
                                   x TRACK_SAMPLE_PER_10K / 10000)

``eligible_roots_per_day`` and ``bytes_per_root`` are measured front-matter keys of the spike.

Standard library only, so it runs anywhere (including Windows). The script cannot tell who typed
the file: an agent, subagent or workflow must NEVER set ``ratified: true`` itself. Ratification
comes only from the owner's own message (copied verbatim into ``ratification_quote``) or the
owner's own edit of 03-SPIKE.md (D-02).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

DEFAULT_FILE = (
    Path(__file__).resolve().parent.parent
    / ".planning"
    / "phases"
    / "03-real-propagation-data"
    / "03-SPIKE.md"
)

EXIT_OK = 0
EXIT_NOT_RATIFIED = 1
EXIT_MALFORMED = 2
EXIT_REPLAN = 3

REMINDER = (
    "reminder: an agent must never set `ratified: true` itself; only the owner's own message "
    "or the owner's own edit of 03-SPIKE.md ratifies (D-02)"
)

JSON_MAP_KEYS = ("recommended_parameters", "recommended_options", "ratified_parameters")
JSON_LIST_KEYS = ("run_windows",)
OD_BOUND_KEYS = (
    "RETENTION_TEXT_DAYS",
    "RETENTION_CASCADE_DAYS",
    "CASCADE_MERGE_POLICY",
    "TRACK_SEED_CLAIM_URL_MATCH",
)
ALLOWED = {
    "od1_retention": {"", "RT-1", "RT-2", "RT-3", "recommended-defaults"},
    "od2_merge": {"", "M0", "M1", "M2", "recommended-defaults"},
    "od3_tracking": {"", "A", "B", "C", "recommended-defaults"},
    "schema_via_uri": {"", "true", "false"},
    "dependencies_approved": {"", "true", "false"},
    "pseudonym_scheme": {"", "d17-hmac-v1", "other"},
    "ratification_source": {"", "owner-message", "owner-edit"},
    "ratified": {"", "true", "false"},
}
CONCRETE = {
    "od1": {"RT-1", "RT-2", "RT-3"},
    "od2": {"M0", "M1", "M2"},
    "od3": {"A", "B", "C"},
}
FIELD_OF = {"od1": "od1_retention", "od2": "od2_merge", "od3": "od3_tracking"}
MERGE_VALUES = {"none", "claim_group", "derived"}
PSEUDONYM_TOKEN = re.compile(
    r"pseudonym\s*=\s*d17\b|pseudonym_scheme\s*=\s*d17-hmac-v1", re.IGNORECASE
)
DEPENDENCIES_TOKEN = re.compile(r"\bdependencies\s*=\s*approved\b", re.IGNORECASE)
VIA_URI_TOKEN = {
    "true": re.compile(r"\bvia_uri\s*=\s*true\b", re.IGNORECASE),
    "false": re.compile(r"\bvia_uri\s*=\s*false\b", re.IGNORECASE),
}
REPLAN_MESSAGE = (
    "the planner must revise plans 03-03 to 03-07, plus 03-02 (OD-3 C) and 03-10 (docs), first"
)

# Inclusive ranges of the numeric parameters; any other integer parameter must be >= 0.
PARAM_RANGES: dict[str, tuple[int, int]] = {
    "TRACK_SAMPLE_PER_10K": (1, 10000),
    "TRACK_MAX_ACTIVE_ROOTS": (1, 10_000_000),
    "TRACK_ROOT_TTL_HOURS": (1, 24 * 30),
    "TRACK_MAX_EVENTS_PER_CASCADE": (1, 10_000_000),
    "STORE_MAX_EVENTS_TOTAL": (1, 1_000_000_000),
    "DB_BUDGET_BYTES": (1, 10**13),
    "RETENTION_TEXT_DAYS": (0, 3650),
    "RETENTION_CASCADE_DAYS": (1, 3650),
    "RETENTION_TOMBSTONE_DAYS": (0, 3650),
    "RETENTION_DORMANT_DAYS": (0, 3650),
    "RETENTION_NEWS_DAYS": (0, 3650),
    "INGEST_REWIND_SECONDS": (30, 86_400),
}
CAPACITY_KEYS = (
    "TRACK_SAMPLE_PER_10K",
    "TRACK_MAX_ACTIVE_ROOTS",
    "TRACK_ROOT_TTL_HOURS",
    "RETENTION_CASCADE_DAYS",
    "DB_BUDGET_BYTES",
)
MEASURED_KEYS = ("eligible_roots_per_day", "bytes_per_root")
STOP_SHARE = 0.8
DESIGN_SHARE = 0.6

# What each OD option the plans build enacts. ``sets`` are parameter values the option implies
# (RT-3 is relative: the text window equals the effective cascade window). ``rule`` is the
# predicate the final values must satisfy; ``check_od_consistency`` enforces it.
OD_IMPLICATIONS: dict[str, dict[str, Any]] = {
    "RT-1": {
        "sets": {"RETENTION_TEXT_DAYS": 0, "RETENTION_CASCADE_DAYS": 30},
        "rule": "RETENTION_TEXT_DAYS == 0",
    },
    "RT-2": {"sets": {}, "rule": "0 < RETENTION_TEXT_DAYS < RETENTION_CASCADE_DAYS"},
    "RT-3": {
        "sets": {"RETENTION_TEXT_DAYS": "=RETENTION_CASCADE_DAYS"},
        "rule": "RETENTION_TEXT_DAYS == RETENTION_CASCADE_DAYS",
    },
    "M0": {"sets": {"CASCADE_MERGE_POLICY": "none"}, "rule": "CASCADE_MERGE_POLICY == none"},
    "M1": {
        "sets": {"CASCADE_MERGE_POLICY": "claim_group"},
        "rule": "CASCADE_MERGE_POLICY == claim_group",
    },
    "A": {
        "sets": {"TRACK_SEED_CLAIM_URL_MATCH": False},
        "rule": "TRACK_SEED_CLAIM_URL_MATCH is false",
    },
    "B": {
        "sets": {"TRACK_SEED_CLAIM_URL_MATCH": True},
        "rule": "TRACK_SEED_CLAIM_URL_MATCH is true",
    },
}


class GateError(Exception):
    """A malformed document or an inconsistent ratification (exit code 2)."""


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        if value[0] == '"':
            try:
                decoded = json.loads(value)
            except ValueError:
                return value[1:-1]
            return decoded if isinstance(decoded, str) else value[1:-1]
        return value[1:-1]
    return value


def _reject_constant(name: str) -> Any:
    """``json.loads`` hook: NaN and Infinity are not valid parameter values."""
    raise ValueError(f"{name} is not a valid JSON value")


def parse_front_matter(text: str) -> dict[str, Any]:
    """Parse the flat ``key: value`` front matter between the first two ``---`` lines."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise GateError("front matter missing: the file must start with a --- line")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise GateError("front matter is not closed by a second --- line") from None
    result: dict[str, Any] = {}
    for number, line in enumerate(lines[1:end], start=2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise GateError(f"front matter line {number} is not `key: value`")
        key, raw = line.split(":", 1)
        key = key.strip()
        if key in JSON_MAP_KEYS or key in JSON_LIST_KEYS:
            try:
                parsed = json.loads(raw.strip() or "null", parse_constant=_reject_constant)
            except ValueError as exc:
                raise GateError(f"{key} is not valid JSON") from exc
            expected = dict if key in JSON_MAP_KEYS else list
            if not isinstance(parsed, expected):
                raise GateError(f"{key} must be a JSON {'object' if expected is dict else 'list'}")
            result[key] = parsed
        else:
            result[key] = _unquote(raw)
    return result


def load_document(path: Path) -> dict[str, Any]:
    """Read and parse the front matter of the decision document."""
    try:
        text = path.read_text(encoding="utf-8-sig")  # a BOM from a Windows editor is accepted
    except (OSError, UnicodeDecodeError) as exc:
        raise GateError(f"cannot read {path.name}: {type(exc).__name__}") from exc
    return parse_front_matter(text)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def check_od_consistency(resolved: dict[str, str], parameters: dict[str, Any]) -> list[str]:
    """Violations of the chosen options against a parameter mapping (empty list: consistent).

    ``resolved`` maps od1, od2 and od3 to concrete option ids. Used by the gate and by plan
    03-02's policy tests so the shipped defaults are checked by the same rule.
    """
    problems: list[str] = []
    text, cascade = parameters.get("RETENTION_TEXT_DAYS"), parameters.get("RETENTION_CASCADE_DAYS")
    merge, match = (
        parameters.get("CASCADE_MERGE_POLICY"),
        parameters.get("TRACK_SEED_CLAIM_URL_MATCH"),
    )
    for key in ("RETENTION_TEXT_DAYS", "RETENTION_CASCADE_DAYS"):
        value = parameters.get(key)
        if not _is_int(value) or value < 0:
            problems.append(f"OD-1: {key} must be a non-negative integer (found {value!r})")
    if merge not in MERGE_VALUES:
        problems.append("OD-2: CASCADE_MERGE_POLICY must be none, claim_group or derived")
    if not isinstance(match, bool):
        problems.append("OD-3: TRACK_SEED_CLAIM_URL_MATCH must be true or false")
    if problems:
        return problems
    rt, md, tr = resolved.get("od1"), resolved.get("od2"), resolved.get("od3")
    if rt == "RT-1" and text != 0:
        problems.append(f"OD-1 RT-1: RETENTION_TEXT_DAYS is {text}, RT-1 requires 0")
    if rt == "RT-2" and not 0 < text < cascade:
        problems.append(
            f"OD-1 RT-2: RETENTION_TEXT_DAYS {text} must be above 0 and below "
            f"RETENTION_CASCADE_DAYS {cascade}"
        )
    if rt == "RT-3" and text != cascade:
        problems.append(
            f"OD-1 RT-3: RETENTION_TEXT_DAYS {text} must equal RETENTION_CASCADE_DAYS {cascade}"
        )
    if md == "M0" and merge != "none":
        problems.append(f"OD-2 M0: CASCADE_MERGE_POLICY is {merge}, M0 requires none")
    if md == "M1" and merge != "claim_group":
        problems.append(f"OD-2 M1: CASCADE_MERGE_POLICY is {merge}, M1 requires claim_group")
    if tr == "A" and match is not False:
        problems.append("OD-3 A: TRACK_SEED_CLAIM_URL_MATCH is true, A requires false")
    if tr == "B" and match is not True:
        problems.append("OD-3 B: TRACK_SEED_CLAIM_URL_MATCH is false, B requires true")
    return problems


def _type_name(value: object) -> str:
    if isinstance(value, bool):
        return "bool"
    if _is_int(value):
        return "int"
    return type(value).__name__


def validate_ratified_parameters(front: dict[str, Any]) -> None:
    """Owner overrides must name a recommended parameter, keep its type and stay in range."""
    recommended = front.get("recommended_parameters", {})
    for key, value in front.get("ratified_parameters", {}).items():
        if key not in recommended:
            raise GateError(f"ratified_parameters.{key} is not a recommended parameter")
        want, got = _type_name(recommended[key]), _type_name(value)
        if want != got:
            raise GateError(f"ratified_parameters.{key} must be {want}, found {got}")


def validate_ranges(parameters: dict[str, Any]) -> None:
    """Every integer parameter lies in its range (exit 2 otherwise)."""
    for key, value in parameters.items():
        if not _is_int(value):
            continue
        low, high = PARAM_RANGES.get(key, (0, 10**15))
        if not low <= value <= high:
            raise GateError(f"{key} is {value}, outside its range {low}..{high}")


def _measured(front: dict[str, Any], key: str) -> int:
    raw = str(front.get(key, "")).strip()
    if not raw.isdigit() or int(raw) <= 0:
        raise GateError(f"front matter {key} must be a positive integer (measured by the spike)")
    return int(raw)


def check_capacity(front: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    """The storage coupling of sampling, retention, the active-root cap and the budget.

    The effective cascade days are ``RETENTION_CASCADE_DAYS``: the dormant rule's saving is not
    credited because it is an unmeasured extrapolation. Raises GateError (exit 2) above 80 percent
    of ``DB_BUDGET_BYTES`` or when the cap is below the sampled active set times 1.5; returns the
    figures and a warning above the 60 percent design line.
    """
    roots_per_day = _measured(front, "eligible_roots_per_day")
    bytes_per_root = _measured(front, "bytes_per_root")
    for key in CAPACITY_KEYS:
        if not _is_int(parameters.get(key)):
            raise GateError(f"{key} must be an integer parameter (storage coupling)")
    sample = parameters["TRACK_SAMPLE_PER_10K"]
    days = parameters["RETENTION_CASCADE_DAYS"]
    budget = parameters["DB_BUDGET_BYTES"]
    ttl = parameters["TRACK_ROOT_TTL_HOURS"]
    cap = parameters["TRACK_MAX_ACTIVE_ROOTS"]
    numerator = sample * roots_per_day * days * bytes_per_root  # bytes x 10,000
    steady_bytes = numerator / 10000
    share = steady_bytes / budget
    # exact integer form of ceil(1.5 x ttl / 24 x roots x sample / 10000)
    required_cap = -(-(3 * ttl * roots_per_day * sample) // (2 * 24 * 10000))
    if numerator * 10 > 8 * budget * 10000:
        raise GateError(
            f"storage coupling: TRACK_SAMPLE_PER_10K {sample} x {roots_per_day} roots/day x "
            f"{days} days x {bytes_per_root} B = {steady_bytes / 1e6:.1f} MB, above "
            f"{STOP_SHARE:.0%} of DB_BUDGET_BYTES {budget}"
        )
    if cap < required_cap:
        raise GateError(
            f"storage coupling: TRACK_MAX_ACTIVE_ROOTS {cap} is below the required {required_cap} "
            f"(1.5 x {ttl} h / 24 x {roots_per_day} roots/day x {sample} / 10000)"
        )
    warnings = []
    if share > DESIGN_SHARE:
        warnings.append(
            f"warning: steady state {steady_bytes / 1e6:.1f} MB is {share:.0%} of the budget, "
            f"above the {DESIGN_SHARE:.0%} design line"
        )
    return {
        "steady_state_bytes": round(steady_bytes),
        "budget_share": round(share, 4),
        "required_max_active_roots": required_cap,
        "warnings": warnings,
    }


def resolve_options(front: dict[str, Any]) -> dict[str, str]:
    """Concrete option ids; ``recommended-defaults`` resolves through ``recommended_options``."""
    recommended = front.get("recommended_options", {})
    resolved: dict[str, str] = {}
    for od, field in FIELD_OF.items():
        choice = front.get(field, "")
        if choice == "recommended-defaults":
            choice = recommended.get(od, "")
            if choice not in CONCRETE[od]:
                raise GateError(
                    f"{field} is recommended-defaults but recommended_options.{od} is missing "
                    "or not a concrete option"
                )
        resolved[od] = choice
    return resolved


def compute_effective_parameters(front: dict[str, Any]) -> dict[str, Any]:
    """Resolved options, the OD-implied overlay and the effective parameters (D-03).

    Order: recommended_parameters, then the OD-implied overlay, then the owner's
    ratified_parameters (an explicit number wins over an option default but may not contradict
    the option). Raises GateError (exit 2) when the result is inconsistent.
    """
    resolved = resolve_options(front)
    validate_ratified_parameters(front)
    parameters: dict[str, Any] = dict(front.get("recommended_parameters", {}))
    implied: dict[str, Any] = {}
    for option in resolved.values():
        for key, value in OD_IMPLICATIONS.get(option, {}).get("sets", {}).items():
            if isinstance(value, str) and value.startswith("="):
                continue  # relative: filled after the overrides
            implied[key] = value
            parameters[key] = value
    overrides = front.get("ratified_parameters", {})
    parameters.update(overrides)
    if resolved["od1"] == "RT-3":
        text_days = parameters.get("RETENTION_CASCADE_DAYS")
        if "RETENTION_TEXT_DAYS" not in overrides:
            parameters["RETENTION_TEXT_DAYS"] = text_days
            implied["RETENTION_TEXT_DAYS"] = text_days
    problems = check_od_consistency(resolved, parameters)
    if problems:
        raise GateError("; ".join(problems))
    validate_ranges(parameters)
    capacity = check_capacity(front, parameters)
    effective = dict(parameters)
    for key in OD_BOUND_KEYS:
        effective.setdefault(key, None)
    return {"resolved": resolved, "implied": implied, "effective": effective, "capacity": capacity}


def validate_sets(front: dict[str, Any]) -> None:
    """Every enumerated field must hold a value from its allowed set (exit 2 otherwise)."""
    for key, allowed in ALLOWED.items():
        if front.get(key, "") not in allowed:
            raise GateError(f"{key} holds a value outside its allowed set")


def not_ratified_reasons(front: dict[str, Any]) -> list[str]:
    """Reasons the document is not (fully) ratified; empty means the exit-1 checks pass."""
    reasons: list[str] = []
    if front.get("ratified") != "true":
        reasons.append("ratified is not true")
    if front.get("ratified_by") != "owner":
        reasons.append("ratified_by is not owner")
    try:
        date.fromisoformat(str(front.get("ratified_on", "")))
    except ValueError:
        reasons.append("ratified_on is blank or not an ISO date (YYYY-MM-DD)")
    source = front.get("ratification_source", "")
    if source not in ("owner-message", "owner-edit"):
        reasons.append("ratification_source is not owner-message or owner-edit")
    if source == "owner-message" and not str(front.get("ratification_quote", "")).strip():
        reasons.append("ratification_quote is blank (the owner's own words are required)")
    if front.get("dependencies_approved") != "true":
        reasons.append("dependencies_approved is not true")
    for field in ("od1_retention", "od2_merge", "od3_tracking", "schema_via_uri"):
        if not front.get(field):
            reasons.append(f"{field} is blank")
    scheme = front.get("pseudonym_scheme", "")
    if not scheme:
        reasons.append("pseudonym_scheme is blank (the one-way D-17 scheme is unconfirmed)")
    quote = str(front.get("ratification_quote", ""))
    if scheme == "d17-hmac-v1" and source == "owner-message" and not PSEUDONYM_TOKEN.search(quote):
        reasons.append("the owner message lacks the explicit token pseudonym=d17")
    if source == "owner-message":
        if front.get("dependencies_approved") == "true" and not DEPENDENCIES_TOKEN.search(quote):
            reasons.append("the owner message lacks the explicit token dependencies=approved")
        via = str(front.get("schema_via_uri", ""))
        if via in VIA_URI_TOKEN and not VIA_URI_TOKEN[via].search(quote):
            reasons.append(f"the owner message lacks the explicit token via_uri={via}")
    return reasons


def replan_reasons(front: dict[str, Any], resolved: dict[str, str]) -> list[str]:
    """Choices the plans do not build (exit 3)."""
    reasons = []
    if resolved["od2"] == "M2":
        reasons.append("OD-2 M2 (derived merge) is outside the plans")
    if resolved["od3"] == "C":
        reasons.append("OD-3 C (engagement promotion) is outside the plans")
    if front.get("pseudonym_scheme") == "other":
        reasons.append("a different identifier scheme than D-17 was chosen")
    return reasons


def evaluate(path: Path) -> tuple[int, list[str], dict[str, Any] | None]:
    """Run the gate: (exit code, messages, JSON payload for exit 0)."""
    try:
        front = load_document(path)
        validate_sets(front)
        reasons = not_ratified_reasons(front)
        if reasons:
            return EXIT_NOT_RATIFIED, reasons, None
        resolved = resolve_options(front)
        replan = replan_reasons(front, resolved)
        if replan:
            return EXIT_REPLAN, [*replan, REPLAN_MESSAGE], None
        computed = compute_effective_parameters(front)
    except GateError as exc:
        return EXIT_MALFORMED, [str(exc)], None
    except TypeError:  # an unhashable or mistyped JSON value where a scalar was expected
        return EXIT_MALFORMED, ["a front matter value has the wrong JSON type"], None
    payload = {
        "od1_retention": front["od1_retention"],
        "od2_merge": front["od2_merge"],
        "od3_tracking": front["od3_tracking"],
        "resolved_od1": computed["resolved"]["od1"],
        "resolved_od2": computed["resolved"]["od2"],
        "resolved_od3": computed["resolved"]["od3"],
        "od_implied_parameters": computed["implied"],
        "schema_via_uri": front["schema_via_uri"],
        "pseudonym_scheme": front["pseudonym_scheme"],
        "effective_parameters": computed["effective"],
        "capacity": computed["capacity"],
    }
    return EXIT_OK, list(computed["capacity"]["warnings"]), payload


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; see the module docstring for the exit codes."""
    parser = argparse.ArgumentParser(description="Gate: is 03-SPIKE.md ratified by the owner?")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--json", action="store_true", help="print the effective values on exit 0")
    args = parser.parse_args(argv)
    code, messages, payload = evaluate(args.file)
    if code == EXIT_OK:
        if args.json:
            sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
        else:
            sys.stdout.write("spike ratified by the owner; options consistent\n")
        for message in messages:
            sys.stderr.write(f"- {message}\n")
        sys.stderr.write(REMINDER + "\n")
        return code
    label = {
        EXIT_NOT_RATIFIED: "NOT RATIFIED",
        EXIT_MALFORMED: "MALFORMED OR INCONSISTENT",
        EXIT_REPLAN: "REPLAN REQUIRED",
    }[code]
    sys.stderr.write(f"spike gate: {label}\n")
    for message in messages:
        sys.stderr.write(f"- {message}\n")
    sys.stderr.write(REMINDER + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
