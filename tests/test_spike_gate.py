"""Tests for scripts/check_spike_ratified.py, the machine gate for plans 03-02 to 03-12 (D-02).

Documents are constructed front-matter strings written to tmp_path. Nothing here ratifies the real
03-SPIKE.md: one test only proves that the real file parses and stays unratified until the owner
acts (exit codes 0, 1 or 3 are all valid there, so the test stays correct after the owner ratifies).
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE_PATH = REPO_ROOT / "scripts" / "check_spike_ratified.py"
REAL_SPIKE = REPO_ROOT / ".planning" / "phases" / "03-real-propagation-data" / "03-SPIKE.md"

RECOMMENDED = {
    "RETENTION_TEXT_DAYS": 14,
    "RETENTION_CASCADE_DAYS": 90,
    "RETENTION_TOMBSTONE_DAYS": 7,
    "CASCADE_MERGE_POLICY": "claim_group",
    "TRACK_SEED_CLAIM_URL_MATCH": False,
}


@pytest.fixture(scope="module")
def gate():
    spec = importlib.util.spec_from_file_location("check_spike_ratified", GATE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_spike_ratified"] = module
    spec.loader.exec_module(module)
    return module


def make_doc(**overrides) -> str:
    """A fully valid constructed ratified document; overrides replace single fields."""
    fields = {
        "phase": "3",
        "ratified": "true",
        "ratified_by": "owner",
        "ratified_on": "2026-10-20",
        "ratification_source": "owner-message",
        "ratification_quote": json.dumps("ratify recommended pseudonym=d17"),
        "od1_retention": "RT-2",
        "od2_merge": "M1",
        "od3_tracking": "A",
        "schema_via_uri": "true",
        "dependencies_approved": "true",
        "pseudonym_scheme": "d17-hmac-v1",
        "windows_result": "pending",
        "recommended_parameters": json.dumps(RECOMMENDED),
        "recommended_options": json.dumps({"od1": "RT-2", "od2": "M1", "od3": "A"}),
        "ratified_parameters": "{}",
        "run_windows": "[]",
    }
    fields.update(dict(overrides.items()))
    lines = (
        ["---"] + [f"{k}: {v}" for k, v in fields.items() if v is not None] + ["---", "", "body"]
    )
    return "\n".join(lines) + "\n"


def run(gate, tmp_path, text, capsys, *extra):
    path = tmp_path / "spike.md"
    path.write_text(text, encoding="utf-8")
    code = gate.main(["--file", str(path), *extra])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def run_json(gate, tmp_path, text, capsys):
    code, out, err = run(gate, tmp_path, text, capsys, "--json")
    return code, (json.loads(out) if out.strip() else None), err


# ------------------------------------------------------------ shape and sources


def test_valid_document_exits_0_and_prints_the_reminder(gate, tmp_path, capsys):
    code, out, err = run(gate, tmp_path, make_doc(), capsys)
    assert code == 0
    assert "ratified" in out
    assert "never set `ratified: true` itself" in err


def test_scaffold_shape_exits_1(gate, tmp_path, capsys):
    text = make_doc(
        ratified="false",
        ratified_by='""',
        ratified_on='""',
        ratification_source='""',
        ratification_quote='""',
        od1_retention='""',
        od2_merge='""',
        od3_tracking='""',
        schema_via_uri='""',
        dependencies_approved='""',
        pseudonym_scheme='""',
        recommended_parameters="{}",
        recommended_options="{}",
    )
    code, _out, err = run(gate, tmp_path, text, capsys)
    assert code == 1
    assert "ratified is not true" in err


def test_ratified_by_claude_exits_1(gate, tmp_path, capsys):
    assert run(gate, tmp_path, make_doc(ratified_by="claude"), capsys)[0] == 1


def test_owner_message_without_a_quote_exits_1(gate, tmp_path, capsys):
    assert run(gate, tmp_path, make_doc(ratification_quote='""'), capsys)[0] == 1


def test_bad_or_blank_date_exits_1(gate, tmp_path, capsys):
    assert run(gate, tmp_path, make_doc(ratified_on='""'), capsys)[0] == 1
    assert run(gate, tmp_path, make_doc(ratified_on="20-10-2026"), capsys)[0] == 1


@pytest.mark.parametrize(
    "field", ["od1_retention", "od2_merge", "od3_tracking", "schema_via_uri", "pseudonym_scheme"]
)
def test_blank_choice_exits_1(gate, tmp_path, capsys, field):
    assert run(gate, tmp_path, make_doc(**{field: '""'}), capsys)[0] == 1


def test_dependencies_not_approved_exits_1(gate, tmp_path, capsys):
    assert run(gate, tmp_path, make_doc(dependencies_approved="false"), capsys)[0] == 1
    assert run(gate, tmp_path, make_doc(dependencies_approved='""'), capsys)[0] == 1


def test_invalid_values_exit_2(gate, tmp_path, capsys):
    assert run(gate, tmp_path, make_doc(od1_retention="RT-9"), capsys)[0] == 2
    assert run(gate, tmp_path, make_doc(od3_tracking="D"), capsys)[0] == 2
    assert run(gate, tmp_path, make_doc(ratification_source="agent"), capsys)[0] == 2
    assert run(gate, tmp_path, make_doc(ratified="True"), capsys)[0] == 2


def test_missing_file_and_missing_front_matter_exit_2(gate, tmp_path, capsys):
    assert gate.main(["--file", str(tmp_path / "absent.md")]) == 2
    capsys.readouterr()
    assert run(gate, tmp_path, "no front matter here\n", capsys)[0] == 2
    assert run(gate, tmp_path, "---\nratified: true\n", capsys)[0] == 2


def test_malformed_json_maps_and_lists_exit_2(gate, tmp_path, capsys):
    assert run(gate, tmp_path, make_doc(recommended_parameters="{not json"), capsys)[0] == 2
    assert run(gate, tmp_path, make_doc(ratified_parameters="[1, 2]"), capsys)[0] == 2
    assert run(gate, tmp_path, make_doc(run_windows="{}"), capsys)[0] == 2
    assert run(gate, tmp_path, make_doc(run_windows="[{broken"), capsys)[0] == 2


# ------------------------------------------------------------ the one-way D-17 door


def test_owner_message_without_the_d17_token_exits_1(gate, tmp_path, capsys):
    quote = json.dumps("ratify recommended")
    code, _out, err = run(gate, tmp_path, make_doc(ratification_quote=quote), capsys)
    assert code == 1
    assert "pseudonym=d17" in err


@pytest.mark.parametrize(
    "quote",
    [
        "ratify recommended pseudonym=d17",
        "ratify OD-1=RT-1 pseudonym = D17 thanks",
        "ok, and pseudonym_scheme=d17-hmac-v1",
    ],
)
def test_the_explicit_token_confirms_the_scheme(gate, tmp_path, capsys, quote):
    assert run(gate, tmp_path, make_doc(ratification_quote=json.dumps(quote)), capsys)[0] == 0


def test_owner_edit_needs_no_token(gate, tmp_path, capsys):
    text = make_doc(ratification_source="owner-edit", ratification_quote='""')
    assert run(gate, tmp_path, text, capsys)[0] == 0


def test_blank_pseudonym_scheme_exits_1_even_when_everything_else_is_valid(gate, tmp_path, capsys):
    code, _out, err = run(gate, tmp_path, make_doc(pseudonym_scheme='""'), capsys)
    assert code == 1
    assert "one-way D-17 scheme is unconfirmed" in err


# ------------------------------------------------------------ exit 3


@pytest.mark.parametrize(
    "override",
    [{"od2_merge": "M2"}, {"od3_tracking": "C"}, {"pseudonym_scheme": "other"}],
)
def test_choices_outside_the_plans_exit_3(gate, tmp_path, capsys, override):
    code, _out, err = run(gate, tmp_path, make_doc(**override), capsys)
    assert code == 3
    assert "revise plans 03-04 to 03-07" in err


def test_recommended_defaults_resolving_to_m2_exit_3(gate, tmp_path, capsys):
    text = make_doc(
        od2_merge="recommended-defaults",
        recommended_options=json.dumps({"od1": "RT-2", "od2": "M2", "od3": "A"}),
    )
    assert run(gate, tmp_path, text, capsys)[0] == 3


# ------------------------------------------------------------ OD table


OD_CASES = [
    ("od1_retention", "RT-1", {"RETENTION_TEXT_DAYS": 0, "RETENTION_CASCADE_DAYS": 30}),
    ("od1_retention", "RT-2", {"RETENTION_TEXT_DAYS": 14, "RETENTION_CASCADE_DAYS": 90}),
    ("od1_retention", "RT-3", {"RETENTION_TEXT_DAYS": 90, "RETENTION_CASCADE_DAYS": 90}),
    ("od2_merge", "M0", {"CASCADE_MERGE_POLICY": "none"}),
    ("od2_merge", "M1", {"CASCADE_MERGE_POLICY": "claim_group"}),
    ("od3_tracking", "A", {"TRACK_SEED_CLAIM_URL_MATCH": False}),
    ("od3_tracking", "B", {"TRACK_SEED_CLAIM_URL_MATCH": True}),
]


@pytest.mark.parametrize(("field", "option", "expected"), OD_CASES)
def test_every_option_changes_the_effective_parameters_by_itself(
    gate, tmp_path, capsys, field, option, expected
):
    code, payload, _err = run_json(gate, tmp_path, make_doc(**{field: option}), capsys)
    assert code == 0
    assert payload[f"resolved_od{field[2]}"] == option
    for key, value in expected.items():
        assert payload["effective_parameters"][key] == value


def test_regression_rt1_m0_b_without_any_numeric_override(gate, tmp_path, capsys):
    text = make_doc(od1_retention="RT-1", od2_merge="M0", od3_tracking="B")
    code, payload, _err = run_json(gate, tmp_path, text, capsys)
    assert code == 0
    eff = payload["effective_parameters"]
    assert eff["RETENTION_TEXT_DAYS"] == 0
    assert eff["RETENTION_CASCADE_DAYS"] == 30
    assert eff["CASCADE_MERGE_POLICY"] == "none"
    assert eff["TRACK_SEED_CLAIM_URL_MATCH"] is True
    assert payload["od_implied_parameters"]["TRACK_SEED_CLAIM_URL_MATCH"] is True
    assert payload["pseudonym_scheme"] == "d17-hmac-v1"


CONTRADICTIONS = [
    ("RT-1 with 14 text days", {"od1_retention": "RT-1"}, {"RETENTION_TEXT_DAYS": 14}, "OD-1 RT-1"),
    ("RT-2 with 0 text days", {"od1_retention": "RT-2"}, {"RETENTION_TEXT_DAYS": 0}, "OD-1 RT-2"),
    (
        "RT-2 with text days equal to cascade days",
        {"od1_retention": "RT-2"},
        {"RETENTION_TEXT_DAYS": 90},
        "OD-1 RT-2",
    ),
    ("RT-3 with 14 text days", {"od1_retention": "RT-3"}, {"RETENTION_TEXT_DAYS": 14}, "OD-1 RT-3"),
    (
        "M0 with claim_group",
        {"od2_merge": "M0"},
        {"CASCADE_MERGE_POLICY": "claim_group"},
        "OD-2 M0",
    ),
    ("M1 with none", {"od2_merge": "M1"}, {"CASCADE_MERGE_POLICY": "none"}, "OD-2 M1"),
    ("A with true", {"od3_tracking": "A"}, {"TRACK_SEED_CLAIM_URL_MATCH": True}, "OD-3 A"),
    ("B with false", {"od3_tracking": "B"}, {"TRACK_SEED_CLAIM_URL_MATCH": False}, "OD-3 B"),
]


@pytest.mark.parametrize(("label", "choice", "override", "named"), CONTRADICTIONS)
def test_a_contradicting_override_exits_2_and_names_the_od(
    gate, tmp_path, capsys, label, choice, override, named
):
    text = make_doc(**choice, ratified_parameters=json.dumps(override))
    code, _out, err = run(gate, tmp_path, text, capsys)
    assert code == 2, label
    assert named in err
    assert next(iter(override)) in err


def test_consistent_overrides_win_over_option_defaults(gate, tmp_path, capsys):
    text = make_doc(
        od1_retention="RT-1", ratified_parameters=json.dumps({"RETENTION_CASCADE_DAYS": 45})
    )
    code, payload, _err = run_json(gate, tmp_path, text, capsys)
    assert code == 0
    assert (
        payload["effective_parameters"]["RETENTION_TEXT_DAYS"],
        payload["effective_parameters"]["RETENTION_CASCADE_DAYS"],
    ) == (0, 45)
    text = make_doc(
        od1_retention="RT-3", ratified_parameters=json.dumps({"RETENTION_CASCADE_DAYS": 60})
    )
    code, payload, _err = run_json(gate, tmp_path, text, capsys)
    assert code == 0
    assert (
        payload["effective_parameters"]["RETENTION_TEXT_DAYS"],
        payload["effective_parameters"]["RETENTION_CASCADE_DAYS"],
    ) == (60, 60)


def test_unrelated_numeric_overrides_are_merged(gate, tmp_path, capsys):
    text = make_doc(ratified_parameters=json.dumps({"TRACK_SAMPLE_PER_10K": 1250}))
    _code, payload, _err = run_json(gate, tmp_path, text, capsys)
    assert payload["effective_parameters"]["TRACK_SAMPLE_PER_10K"] == 1250
    assert payload["effective_parameters"]["RETENTION_TOMBSTONE_DAYS"] == 7


def test_recommended_defaults_resolve_through_recommended_options(gate, tmp_path, capsys):
    text = make_doc(
        od1_retention="recommended-defaults",
        od2_merge="recommended-defaults",
        od3_tracking="recommended-defaults",
    )
    code, payload, _err = run_json(gate, tmp_path, text, capsys)
    assert code == 0
    assert (payload["resolved_od1"], payload["resolved_od2"], payload["resolved_od3"]) == (
        "RT-2",
        "M1",
        "A",
    )
    assert payload["effective_parameters"]["RETENTION_TEXT_DAYS"] == 14
    assert payload["od_implied_parameters"] == {
        "CASCADE_MERGE_POLICY": "claim_group",
        "TRACK_SEED_CLAIM_URL_MATCH": False,
    }


def test_recommended_defaults_with_b_requires_matching_recommended_parameters(
    gate, tmp_path, capsys
):
    options = json.dumps({"od1": "RT-2", "od2": "M1", "od3": "B"})
    good = dict(RECOMMENDED, TRACK_SEED_CLAIM_URL_MATCH=True)
    text = make_doc(
        od3_tracking="recommended-defaults",
        recommended_options=options,
        recommended_parameters=json.dumps(good),
    )
    code, payload, _err = run_json(gate, tmp_path, text, capsys)
    assert code == 0
    assert payload["resolved_od3"] == "B"
    # the OD table enacts B even when the recommended number said false: it is the same entry
    text = make_doc(od3_tracking="recommended-defaults", recommended_options=options)
    code, payload, _err = run_json(gate, tmp_path, text, capsys)
    assert code == 0
    assert payload["effective_parameters"]["TRACK_SEED_CLAIM_URL_MATCH"] is True


@pytest.mark.parametrize(
    "options",
    [
        "{}",
        '{"od1": "RT-2", "od2": "M1"}',
        '{"od1": "RT-2", "od2": "M1", "od3": "recommended-defaults"}',
    ],
)
def test_missing_or_non_concrete_recommended_option_exits_2(gate, tmp_path, capsys, options):
    text = make_doc(od3_tracking="recommended-defaults", recommended_options=options)
    assert run(gate, tmp_path, text, capsys)[0] == 2


def test_recommended_parameters_lacking_an_od_bound_key_exits_2(gate, tmp_path, capsys):
    broken = {k: v for k, v in RECOMMENDED.items() if k != "RETENTION_CASCADE_DAYS"}
    text = make_doc(recommended_parameters=json.dumps(broken))
    code, _out, err = run(gate, tmp_path, text, capsys)
    assert code == 2
    assert "RETENTION_CASCADE_DAYS" in err


def test_bad_parameter_types_exit_2(gate, tmp_path, capsys):
    bad = dict(RECOMMENDED, RETENTION_TEXT_DAYS="fourteen")
    assert run(gate, tmp_path, make_doc(recommended_parameters=json.dumps(bad)), capsys)[0] == 2
    bad = dict(RECOMMENDED, CASCADE_MERGE_POLICY="merge-everything")
    assert (
        run(
            gate,
            tmp_path,
            make_doc(od2_merge="RT-2", recommended_parameters=json.dumps(bad)),
            capsys,
        )[0]
        == 2
    )


def test_the_four_od_bound_keys_are_always_present_on_exit_0(gate, tmp_path, capsys):
    minimal = {"RETENTION_TEXT_DAYS": 14, "RETENTION_CASCADE_DAYS": 90}
    text = make_doc(recommended_parameters=json.dumps(minimal))
    code, payload, _err = run_json(gate, tmp_path, text, capsys)
    assert code == 0
    assert set(gate.OD_BOUND_KEYS) <= set(payload["effective_parameters"])


def test_check_od_consistency_is_importable_for_the_policy_tests(gate):
    resolved = {"od1": "RT-2", "od2": "M1", "od3": "A"}
    assert gate.check_od_consistency(resolved, RECOMMENDED) == []
    bad = dict(RECOMMENDED, RETENTION_TEXT_DAYS=0)
    assert any("RT-2" in p for p in gate.check_od_consistency(resolved, bad))
    assert set(gate.OD_IMPLICATIONS) == {"RT-1", "RT-2", "RT-3", "M0", "M1", "A", "B"}


def test_front_matter_parser_is_importable_and_unquotes(gate):
    parsed = gate.parse_front_matter(
        make_doc(ratification_quote=json.dumps('say "yes" pseudonym=d17'))
    )
    assert parsed["ratification_quote"] == 'say "yes" pseudonym=d17'
    assert parsed["recommended_parameters"]["RETENTION_TEXT_DAYS"] == 14
    assert parsed["run_windows"] == []


# ------------------------------------------------------------ the real document


def test_the_real_document_parses_and_the_gate_answers_with_a_known_code(gate, capsys):
    assert REAL_SPIKE.exists()
    code = gate.main(["--file", str(REAL_SPIKE)])
    capsys.readouterr()
    assert code in {0, 1, 3}


def test_no_agent_ratifiable_path_the_script_never_writes(gate):
    source = GATE_PATH.read_text(encoding="utf-8")
    assert "write_text" not in source
    assert "open(" not in source
