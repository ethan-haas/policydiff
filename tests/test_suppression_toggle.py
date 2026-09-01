"""Suppressor-can-fail test (gate 5).

With cosmetic suppression DISABLED, the noise test must go RED -- proving
the suppression step in normalize.py is actually doing work, not a no-op
that the report layer would produce the same output without.
"""
from policydiff.normalize import normalize
from policydiff.report import diff_documents


def test_noise_report_is_empty_with_suppression_on(old_text, old_noise_text):
    result = diff_documents(old_text, old_noise_text, suppress_cosmetic=True)
    non_suppressed = [f for f in result.findings if f.kind not in ("unchanged", "cosmetic")]
    assert non_suppressed == []


def test_noise_report_goes_red_with_suppression_off(old_text, old_noise_text):
    result = diff_documents(old_text, old_noise_text, suppress_cosmetic=False)
    non_suppressed = [f for f in result.findings if f.kind not in ("unchanged", "cosmetic")]
    assert non_suppressed != [], (
        "disabling cosmetic suppression should surface the reflow/renumber/"
        "recapitalization/quote-style noise as findings -- if this list is "
        "still empty, the toggle is a no-op and the suppressor is unproven"
    )
    # Sanity: still no crash / still produces a full finding set.
    assert len(result.findings) >= len(non_suppressed) > 0


def test_normalize_toggle_actually_changes_output():
    raw = 'The  "Insured"   is required to\ngive prompt written NOTICE.'
    on = normalize(raw, suppress_cosmetic=True)
    off = normalize(raw, suppress_cosmetic=False)
    assert on != off
    # Suppressed form must have collapsed whitespace and case-folded.
    assert "  " not in on
    assert on == on.casefold()
