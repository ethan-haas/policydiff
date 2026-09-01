"""Regression tests for an earlier audit's two defect families (fresh independent
independent reviewer, 7 defects:

Family 1 (SEVERE): an earlier revision's bare-heading shape ("MOLD DAMAGE IS COVERED",
no terminal period, ALL-CAPS) classified purely on SURFACE FORM, with no
regard for CONTENT -- so a real, already-computed coverage change (covered
-> excluded, deductible $ change, exclusion carve-in, added sublimit,
removed exclusion, whole-form limit change) got relabeled "heading" and
discarded from the default report even though report.py had the finding
sitting right there in Finding.detail. an earlier fix (segment.py's
_is_coverage_statement): a bare ALL-CAPS line is a heading only if it
carries NO coverage content of its own (no $/digit, and no coverage-domain
word combined with a copula/negation). Also: report.py's heading
relabeling must be gated on the SAME suppress_cosmetic toggle so
--no-suppress-cosmetic (gate 5's defect hatch) universally re-surfaces
anything any suppression path hid, heading path included.

Family 2: multi-level (dotted) clause numbers ("4.2", "5.1.3") were not
recognized as enumerators by segment.py's numbered-clause patterns (which
required a trailing period before the heading text, a shape real forms
don't use once a second level is present), so the whole number stayed
baked into the "unnumbered prose" text and a pure renumber read as a
phantom [MODIFIED]. an earlier fix: segment.py's numeric patterns and
normalize.py's leading-marker stripper both recognize multi-level dotted
numbering as the enumerator (a cosmetic anchor), not prose.

These fixtures are original (not copies of the reviewer's an earlier audit
fixture/probe files under the audit fixtures)
and exercise the general class.
"""
from policydiff.report import diff_documents, human_report
from policydiff.segment import segment


def _non_suppressed(result):
    return [f for f in result.findings if f.kind not in ("unchanged", "cosmetic", "heading")]


# ---------------------------------------------------------------------
# (a) ALL-CAPS coverage lines: all reported in the DEFAULT report.
# ---------------------------------------------------------------------


def test_all_caps_covered_to_not_covered_is_reported_by_default():
    old = "MOLD DAMAGE IS COVERED\n"
    new = "MOLD DAMAGE IS NOT COVERED\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    report = human_report(result, verbose=False)
    assert "No coverage-relevant changes found." not in report
    assert "MOLD DAMAGE" in report


def test_all_caps_deductible_dollar_change_is_reported_by_default():
    old = "DEDUCTIBLE IS $500\n"
    new = "DEDUCTIBLE IS $1000\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    assert non_suppressed[0].kind == "narrowed"
    assert "500" in non_suppressed[0].detail and "1,000" in non_suppressed[0].detail


def test_all_caps_removed_exclusion_is_reported_by_default():
    old = "NO COVERAGE FOR FLOOD\nCOVERAGE IS EXCLUDED FOR WAR\n"
    new = "COVERAGE IS EXCLUDED FOR WAR\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    assert non_suppressed[0].kind == "removed"
    assert "NO COVERAGE FOR FLOOD" in non_suppressed[0].old.text


def test_all_caps_added_sublimit_is_reported_by_default():
    old = "COVERAGE FOR JEWELRY IS PROVIDED\n"
    new = "COVERAGE FOR JEWELRY IS PROVIDED\nJEWELRY SUBLIMIT IS $1,500\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    assert non_suppressed[0].kind == "added"
    assert "SUBLIMIT" in non_suppressed[0].new.text


def test_all_caps_whole_form_limit_change_is_reported_by_default():
    # Whole-document all-caps form, multiple statement lines, only one
    # of which changes -- the surviving unchanged lines must stay
    # silent while the real change is reported cleanly (not merged into
    # one giant garbled sentence -- see group_prose_lines()).
    old = (
        "THIS POLICY INSURES THE DWELLING AGAINST FIRE\n"
        "FLOOD IS NOT COVERED\n"
        "THE POLICY LIMIT IS $300,000\n"
        "WINDSTORM DEDUCTIBLE IS $2,500\n"
    )
    new = (
        "THIS POLICY INSURES THE DWELLING AGAINST FIRE\n"
        "FLOOD IS NOT COVERED\n"
        "THE POLICY LIMIT IS $200,000\n"
        "WINDSTORM DEDUCTIBLE IS $2,500\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert f.kind == "narrowed", f.detail
    assert "300,000" in f.detail and "200,000" in f.detail
    assert f.old.text == "THE POLICY LIMIT IS $300,000"
    assert f.new.text == "THE POLICY LIMIT IS $200,000"


# ---------------------------------------------------------------------
# (b) --no-suppress-cosmetic universally re-surfaces a heading-
#     suppressed pair (gate-5's defect hatch must be universal).
# ---------------------------------------------------------------------


def test_no_suppress_cosmetic_resurfaces_heading_suppressed_rename():
    old = "SECTION A -- DEFINITIONS\nThe policy limit is $250,000.\n"
    new = "SECTION A -- TERMS\nThe policy limit is $250,000.\n"

    result_on = diff_documents(old, new, suppress_cosmetic=True)
    heading_on = [f for f in result_on.findings if f.kind == "heading"]
    assert heading_on, "expected the rename to be suppressed as 'heading' by default"

    result_off = diff_documents(old, new, suppress_cosmetic=False)
    heading_off = [f for f in result_off.findings if f.kind == "heading"]
    assert not heading_off, "the heading path must not bypass --no-suppress-cosmetic"
    # The rename must now show up in its original (non-suppressed) kind
    # -- "DEFINITIONS"/"TERMS" share no content so alignment (which is
    # deliberately toggle-independent) reports it as removed+added
    # rather than a paired modified; the point is that neither side gets
    # masked back into a suppressed "heading" finding.
    visible = [f for f in result_off.findings if f.kind not in ("unchanged", "cosmetic")]
    section_findings = [
        f for f in visible if any(c is not None and c.kind == "section" for c in (f.old, f.new))
    ]
    assert len(section_findings) == 2, [(f.kind, f.detail) for f in visible]
    assert {f.kind for f in section_findings} == {"removed", "added"}


# ---------------------------------------------------------------------
# (c) GUARD: a genuine bare heading rename with unchanged body -> empty,
#     in both directions (an earlier revision defects must stay fixed).
# ---------------------------------------------------------------------


def test_guard_bare_definitions_heading_rename_stays_suppressed():
    old = "DEFINITIONS\nThe insured means the named entity.\n"
    new = "TERMS\nThe insured means the named entity.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == []
    assert "No coverage-relevant changes found." in human_report(result, verbose=False)

    # Reverse direction.
    result_rev = diff_documents(new, old, suppress_cosmetic=True)
    assert _non_suppressed(result_rev) == []


def test_guard_bare_section_a_rename_stays_suppressed():
    old = "SECTION A\nThe deductible is $500.\n"
    new = "SECTION A (revised)\nThe deductible is $500.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == []

    result_rev = diff_documents(new, old, suppress_cosmetic=True)
    assert _non_suppressed(result_rev) == []


def test_guard_bare_single_word_labels_are_never_coverage_atoms():
    # Single-word topic labels that happen to share vocabulary with the
    # coverage-content ban list ("EXCLUSIONS" ~ "exclude") must still be
    # recognized as bare headings -- a shared word alone is not enough,
    # an ASSERTION (copula/negation, or a $/digit) is required.
    for word in ("DEFINITIONS", "EXCLUSIONS", "CONDITIONS"):
        clauses = segment(f"{word}\n")
        assert len(clauses) == 1 and clauses[0].kind == "section", (word, clauses)


# ---------------------------------------------------------------------
# (d) multi-level renumber, identical body -> empty.
# ---------------------------------------------------------------------


def test_multilevel_renumber_4_2_to_5_1_identical_body_is_empty():
    old = (
        "4.2 The policy covers fire and lightning.\n"
        "4.3 The insured must give prompt notice of loss.\n"
    )
    new = (
        "5.1 The policy covers fire and lightning.\n"
        "5.2 The insured must give prompt notice of loss.\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == []
    assert "No coverage-relevant changes found." in human_report(result, verbose=False)


def test_deep_multilevel_renumber_5_1_3_to_6_2_1_identical_body_is_empty():
    old = "5.1.3 The insured must give prompt notice of loss.\n"
    new = "6.2.1 The insured must give prompt notice of loss.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == []


def test_single_level_renumber_still_clean_non_regression():
    old = "3. Coverage applies to fire damage.\n"
    new = "9. Coverage applies to fire damage.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    assert _non_suppressed(result) == []


# ---------------------------------------------------------------------
# (e) a real edit inside a dotted-numbered clause is still caught.
# ---------------------------------------------------------------------


def test_real_edit_inside_dotted_clause_is_still_caught():
    old = "4.2 The deductible is $500.\n"
    new = "5.1 The deductible is $1,000.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert f.kind == "narrowed", f.detail
    assert "500" in f.detail and "1,000" in f.detail
    assert f.old.id == "4.2" and f.new.id == "5.1"


def test_multilevel_numbering_recognized_as_numeric_clause_kind():
    clauses = segment("4.2 The policy covers fire and lightning.\n")
    assert len(clauses) == 1
    assert clauses[0].kind == "numeric"
    assert clauses[0].id == "4.2"
    assert clauses[0].text == "The policy covers fire and lightning."
