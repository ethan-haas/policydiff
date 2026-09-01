"""Regression tests for an earlier audit's defect: a NUMBERED heading line
rename ("4. EXCLUSIONS" -> "4. GENERAL EXCLUSIONS", "1. LIMITS OF
INSURANCE" -> "1. LIMITS OF LIABILITY") leaked as a fabricated coverage
finding. The tool already suppresses an UNNUMBERED heading rename via
the content-delta detector (report.py's _is_coverage_bearing /
_is_label_rename_only, an earlier fix) whenever neither side carries
coverage content -- but a numbered/roman/lettered clause's own heading
LINE was never routed through that same predicate, so renaming it
fabricated a [NARROWED]/[MODIFIED] coverage-direction finding even when
the clause's coverage body was byte-identical.

Root fix: report.py's _is_numbered_heading_rename_only routes a
numbered clause's heading PORTION (split out via
_numbered_heading_and_body) through the SAME _is_coverage_bearing
content-delta check the unnumbered path already uses -- see
report.py's module docstring for the full mechanism, including why the
heading portion must also pass segment.py's existing _is_bare_heading_line
shape gate first (a numbered clause's captured heading text is never
shape-filtered at segmentation time the way a bare/keyword section
heading is, so a genuine coverage assertion sitting directly on the
enumerator's own line must not reach the content check at all).

These fixtures reproduce the reviewer's excl_rename_* / head_rename_*
inputs (paraphrased here, not copied from the reviewer's own test files)
plus an author-written LIMITS OF INSURANCE -> LIMITS OF LIABILITY case
and the guard scenarios that must stay reported.
"""
from policydiff.report import diff_documents, human_report


def _non_suppressed(result):
    return [f for f in result.findings if f.kind not in ("unchanged", "cosmetic", "heading")]


def test_numbered_standalone_heading_rename_over_identical_body_is_empty():
    # (a) "4. EXCLUSIONS" -> "4. GENERAL EXCLUSIONS", body sentences
    # byte-identical: must be EMPTY, not a fabricated [NARROWED].
    old = (
        "4. EXCLUSIONS\n"
        "The company does not cover flood.\n"
        "The company does not cover war.\n"
    )
    new = (
        "4. GENERAL EXCLUSIONS\n"
        "The company does not cover flood.\n"
        "The company does not cover war.\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert non_suppressed == [], [(f.kind, f.detail) for f in non_suppressed]
    assert "No coverage-relevant changes found." in human_report(result, verbose=False)


def test_numbered_merged_heading_rename_over_identical_body_is_empty():
    # (b) "1. LIMITS OF INSURANCE" -> "1. LIMITS OF LIABILITY", body
    # (a single $ sentence merged into the same clause) byte-identical:
    # must be EMPTY, not a fabricated [MODIFIED (direction unclear)].
    old = "1. LIMITS OF INSURANCE\nThe aggregate limit is $1,000,000.\n"
    new = "1. LIMITS OF LIABILITY\nThe aggregate limit is $1,000,000.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert non_suppressed == [], [(f.kind, f.detail) for f in non_suppressed]
    assert "No coverage-relevant changes found." in human_report(result, verbose=False)


def test_guard_real_body_change_under_unchanged_numbered_title_is_still_caught():
    # (c) GUARD: title unchanged, coverage body genuinely broadens what's
    # excluded -- must still be reported (NARROWED), not swallowed by
    # the new heading-rename suppression just because the title matches.
    old = "4. EXCLUSIONS\nThe company does not cover flood.\n"
    new = "4. EXCLUSIONS\nThe company does not cover flood or war.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    assert non_suppressed[0].kind == "narrowed"


def test_guard_amount_change_under_unchanged_numbered_title_is_still_caught():
    # (d) GUARD: title unchanged, the $ limit itself changes -- must
    # still be reported (BROADENED), never suppressed.
    old = "1. LIMITS OF INSURANCE\nThe aggregate limit is $1,000,000.\n"
    new = "1. LIMITS OF INSURANCE\nThe aggregate limit is $2,000,000.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    assert non_suppressed[0].kind == "broadened"
    assert "1,000,000" in non_suppressed[0].detail and "2,000,000" in non_suppressed[0].detail


def test_guard_numbered_coverage_assertion_is_not_treated_as_a_heading():
    # (e) GUARD: the enumerator's own line IS the coverage assertion
    # itself ("4. The company does not cover flood."), not a title --
    # it must never be routed into heading-rename suppression just
    # because it happens to be the clause's whole "heading" group.
    old = "4. The company does not cover flood.\n"
    new = "4. The company does not cover flood or war.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    assert non_suppressed[0].kind != "heading"


def test_unnumbered_heading_rename_stays_empty_contrast():
    # CONTRAST: the pre-existing unnumbered-heading suppression path
    # (an earlier revision) must be completely unaffected by the earlier fix.
    old = "EXCLUSIONS\nThe company does not cover flood.\nThe company does not cover war.\n"
    new = "GENERAL EXCLUSIONS\nThe company does not cover flood.\nThe company does not cover war.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert non_suppressed == [], [(f.kind, f.detail) for f in non_suppressed]
    assert "No coverage-relevant changes found." in human_report(result, verbose=False)
