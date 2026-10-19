"""Tests tying the measurement template, the analyzer summary and 03-SPIKE.md (D-01c, D-17).

The template and the analyzer must agree on the S-n headings, the decision document must carry its
front matter and the three OWNER DECISION blocks, and the one-way D-17 section cannot be edited out
unnoticed.
"""

import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PHASE = REPO_ROOT / ".planning" / "phases" / "03-real-propagation-data"
TEMPLATE = PHASE / "03-SPIKE-REPORT-TEMPLATE.md"
SPIKE = PHASE / "03-SPIKE.md"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from spike_lib import analysis  # noqa: E402

FRONT_MATTER_KEYS = (
    "phase", "document", "ratified", "ratified_by", "ratified_on", "ratification_source",
    "ratification_quote", "od1_retention", "od2_merge", "od3_tracking", "schema_via_uri",
    "dependencies_approved", "pseudonym_scheme", "windows_result", "recommended_parameters",
    "recommended_options", "ratified_parameters", "run_windows",
)  # fmt: skip


@pytest.fixture(scope="module")
def gate():
    spec = importlib.util.spec_from_file_location(
        "check_spike_ratified", REPO_ROOT / "scripts" / "check_spike_ratified.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_spike_ratified"] = module
    spec.loader.exec_module(module)
    return module


def section(text: str, heading: str) -> str:
    """Body of the ``## heading`` section up to the next ``## `` heading."""
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    assert match, f"section {heading!r} missing"
    return match.group(1)


def test_every_summary_heading_exists_in_the_template():
    summary = analysis.summary_markdown(
        {"s2": {"a": 1}, "s4": {}, "s5": {}, "s6": {}, "s7": {}, "s9": {}}
    )
    emitted = re.findall(r"^### (S-\d+)", summary, flags=re.MULTILINE)
    assert emitted == ["S-2", "S-4", "S-5", "S-6", "S-7", "S-9"]
    template = TEMPLATE.read_text(encoding="utf-8")
    for heading in emitted:
        assert re.search(rf"^### {heading}\b", template, flags=re.MULTILINE)


def test_template_names_all_thirteen_measurements_in_order():
    template = TEMPLATE.read_text(encoding="utf-8")
    found = re.findall(r"^### (S-\d+)\b", template, flags=re.MULTILINE)
    assert found == [f"S-{n}" for n in range(1, 14)]
    assert "Windows result (S-12)" in template
    assert "double-bracket MEASURE marker" in template


def test_template_instructions_never_spell_the_marker_pattern():
    template = TEMPLATE.read_text(encoding="utf-8")
    instructions = template.split("\n## ", 1)[0]
    assert "MEASURE" in instructions
    assert "[[" not in instructions


def test_spike_front_matter_has_every_key_and_stays_parseable(gate):
    front = gate.parse_front_matter(SPIKE.read_text(encoding="utf-8"))
    assert set(FRONT_MATTER_KEYS) <= set(front)
    assert isinstance(front["recommended_parameters"], dict)
    assert isinstance(front["run_windows"], list)
    assert front["phase"] == "3"


def test_spike_has_three_owner_decision_blocks_with_the_required_parts():
    text = SPIKE.read_text(encoding="utf-8")
    blocks = re.findall(r"^## OWNER DECISION (OD-\d)", text, flags=re.MULTILINE)
    assert blocks == ["OD-1", "OD-2", "OD-3"]
    for heading in re.findall(r"^## (OWNER DECISION OD-\d[^\n]*)", text, flags=re.MULTILINE):
        body = section(text, heading)
        for part in (
            "**Options",
            "**Measured.**",
            "**Recommendation (PROVISIONAL)",
            "**What changes if you choose otherwise",
            "**Parameters that encode it",
        ):
            assert part in body, (heading, part)
    assert "RETENTION_TEXT_DAYS" in text
    assert "TRACK_SAMPLE_PER_10K" in text
    assert "CASCADE_MERGE_POLICY" in text


def test_the_one_way_door_section_cannot_be_edited_out():
    text = SPIKE.read_text(encoding="utf-8")
    body = section(text, "Pseudonymisation scheme (D-17, ONE-WAY DOOR)")
    for needle in ("HMAC-SHA256", "acct", "uri", "16", "20", "undo", "pseudonym=d17"):
        assert needle in body, needle
    for needle in (
        "Rejected alternatives",
        "What you give up",
        "Honesty limits",
        "Cost of undoing",
    ):
        assert needle.lower() in body.lower(), needle


def test_spike_carries_the_gate_rule_and_the_audit_table():
    text = SPIKE.read_text(encoding="utf-8")
    assert "check_spike_ratified.py" in section(
        text, "How this document is used and the gate rule (D-02)"
    )
    audit = section(text, "Package legitimacy audit")
    for package in ("sqlalchemy", "psycopg", "alembic", "websockets", "tzdata"):
        assert package in audit
    assert "Owner verdict" in audit


def test_ratification_block_lists_the_token_in_every_ratifying_reply():
    block = section(SPIKE.read_text(encoding="utf-8"), "Ratification block")
    replies = [line for line in block.splitlines() if line.startswith("- `ratify")]
    assert len(replies) == 2
    assert all("pseudonym=d17" in line or "pseudonym=d17" in block for line in replies)
    assert "does not confirm the one-way D-17 scheme" in block
