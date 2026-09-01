"""Regression test for an earlier audit defect 1: an earlier revision's dash-CHARACTER folding
(em/en/minus/doubled-hyphen -> ASCII "-") left dash SPACING un-normalized,
so a compound hyphenated term with spaces added around the hyphen
("claims-made" -> "claims - made", "co-insurance" -> "co - insurance")
re-tokenized and leaked through as a false [BROADENED]/[MODIFIED] finding
-- the phrase-level marker check in classify.py matches the compound term
as a literal substring of the raw clause text, and that substring match
silently breaks the moment spacing around the hyphen changes.

These fixtures are original (not copies of the reviewer's probe files) and
exercise the general class: ANY compound hyphenated term, with or without
spaces around the hyphen, must normalize identically.
"""
from policydiff.report import diff_documents, human_report


def _claims_made(spacing: str) -> str:
    return f"1. This is a claims{spacing}made policy form.\n"


def _co_insurance(spacing: str) -> str:
    return f"1. A co{spacing}insurance clause of 80% applies to this policy.\n"


def test_dash_spacing_only_variant_of_compound_term_is_empty():
    for builder in (_claims_made, _co_insurance):
        old = builder("-")
        new = builder(" - ")
        result = diff_documents(old, new, suppress_cosmetic=True)
        non_suppressed = [f for f in result.findings if f.kind not in ("unchanged", "cosmetic")]
        assert non_suppressed == [], (
            f"dash-spacing-only variant leaked through: "
            f"{[(f.kind, f.detail) for f in non_suppressed]}"
        )
        report_text = human_report(result, verbose=False)
        assert "No coverage-relevant changes found." in report_text


def test_dash_doubled_hyphen_and_em_dash_spacing_variants_are_also_empty():
    old = _claims_made("-")
    for spacing in ("--", "—", " -- ", " — "):
        new = _claims_made(spacing)
        result = diff_documents(old, new, suppress_cosmetic=True)
        non_suppressed = [f for f in result.findings if f.kind not in ("unchanged", "cosmetic")]
        assert non_suppressed == [], (
            f"variant {spacing!r} leaked through: {[(f.kind, f.detail) for f in non_suppressed]}"
        )


def test_dash_spacing_normalization_is_load_bearing_when_suppression_disabled():
    old = _claims_made("-")
    new = _claims_made(" - ")
    result = diff_documents(old, new, suppress_cosmetic=False)
    non_suppressed = [f for f in result.findings if f.kind not in ("unchanged", "cosmetic")]
    assert non_suppressed != [], (
        "disabling cosmetic suppression should surface the dash-spacing "
        "difference -- if this list is empty, dash-spacing normalization "
        "isn't actually gated by the toggle"
    )
