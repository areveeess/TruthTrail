"""Characterization of risk_analyzer.analyze_risk (keyword baseline).

Stable rows pin today's behaviour. Known defects are strict xfails that assert
the DESIRED behaviour, so a later fix flips an XPASS (a red build by design) and
the fixing commit removes the marker.
"""

import pytest

from risk_analyzer import analyze_risk


@pytest.mark.parametrize(
    ("headline", "expected"),
    [
        ("Official statement confirms budget", "Low"),
        ("Study finds walking is good", "Low"),
        ("Police confirm death of suspect", "High"),
        ("Mayor dies after long illness", "High"),
        ("MAYOR DIES AT 90", "High"),
        ("Doctors cure patient with new treatment", "High"),
        ("Official statement confirms the death of a suspect", "High"),
        ("Breaking: storm approaching coast", "Medium"),
        ("Leaked memo shows plan", "Medium"),
        ("Trump to visit India", "Medium"),
        ("Local bakery wins award", "Medium"),
        ("Weather forecast for Tuesday", "Medium"),
        ("", "Medium"),
    ],
)
def test_analyze_risk_golden(headline: str, expected: str) -> None:
    assert analyze_risk(headline) == expected


def _defect(headline: str, reason: str) -> object:
    return pytest.param(
        headline,
        id=headline,
        marks=pytest.mark.xfail(strict=True, raises=AssertionError, reason=reason),
    )


@pytest.mark.parametrize(
    "headline",
    [
        _defect("Council approves new secure parking scheme", "substring 'secure' contains 'cure'"),
        _defect("New studies show coffee is healthy", "substring 'studies' contains 'dies'"),
        _defect("Couple wins lottery", "substring 'couple' contains 'coup'"),
        _defect("Officials say deadline extended", "substring 'deadline' contains 'dead'"),
        _defect("Dead heat in the polls", "idiom matched as a death"),
        _defect("Elon Musk opens a bakery", "hardcoded celebrity name (risk_analyzer.py line 14)"),
        _defect("Donald Trump signs bill", "hardcoded celebrity name (risk_analyzer.py line 14)"),
        _defect(
            "Prediction: market crash unlikely, analysts say",
            "negation is ignored: 'market crash' matches",
        ),
    ],
)
def test_analyze_risk_known_defects(headline: str) -> None:
    assert analyze_risk(headline) != "High"


def test_analyze_risk_none_raises() -> None:
    with pytest.raises(AttributeError):
        analyze_risk(None)  # type: ignore[arg-type]
