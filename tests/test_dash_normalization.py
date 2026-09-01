"""Regression test for defect 4: the README claims dash style
is normalized like quote style, but only em-dash/en-dash/minus-sign were
folded to a single ASCII "-" -- a doubled hyphen ("--", a common
markdown/typewriter em-dash stand-in) was left alone, so a clause typed
with "--" vs one typed with a real em-dash (or a single spaced hyphen)
compared unequal and leaked through as a cosmetic false positive.
"""
from policydiff.report import diff_documents, human_report


def _clause(dash: str) -> str:
    return f"1. Coverage {dash} Section A. The company pays for a covered loss.\n"


def test_all_dash_variants_normalize_identically_with_suppression_on():
    base = _clause("--")  # doubled hyphen
    variants = {
        "em_dash": _clause("—"),
        "en_dash": _clause("–"),
        "minus_sign": _clause("−"),
        "spaced_hyphen": _clause("-"),
        "identical_doubled_hyphen": _clause("--"),
    }
    for name, variant in variants.items():
        result = diff_documents(base, variant, suppress_cosmetic=True)
        non_suppressed = [f for f in result.findings if f.kind not in ("unchanged", "cosmetic")]
        assert non_suppressed == [], (
            f"dash variant {name!r} leaked through as a false positive: "
            f"{[(f.kind, f.detail) for f in non_suppressed]}"
        )
        report_text = human_report(result, verbose=False)
        assert "No coverage-relevant changes found." in report_text


def test_dash_normalization_is_load_bearing_when_suppression_disabled():
    # Mirrors tests/test_suppression_toggle.py: the toggle must actually
    # be doing work for dash style specifically, not just be a no-op.
    base = _clause("--")
    em_dash_variant = _clause("—")
    result = diff_documents(base, em_dash_variant, suppress_cosmetic=False)
    non_suppressed = [f for f in result.findings if f.kind not in ("unchanged", "cosmetic")]
    assert non_suppressed != [], (
        "disabling cosmetic suppression should surface the dash-style "
        "difference -- if this list is empty, dash normalization isn't "
        "actually gated by the toggle"
    )


def test_real_wording_change_next_to_a_dash_style_change_is_still_caught():
    # Suppression must not become so aggressive it swallows an actual
    # wording change that happens to sit next to a dash-style variant.
    old = "1. Coverage -- Section A. The company pays for a covered loss.\n"
    new = "1. Coverage — Section A. The company pays for an excluded loss.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = [f for f in result.findings if f.kind not in ("unchanged", "cosmetic")]
    assert len(non_suppressed) == 1
    assert non_suppressed[0].kind != "cosmetic"
