"""Regression tests for an earlier audit's defect class: a heading line with NO
terminal sentence punctuation ("SECTION A -- DEFINITIONS", "SECTION A",
a bare "DEFINITIONS") was not recognized as its own atom by segment.py,
so sentence.py's splitter glued it onto the following coverage sentence
("SECTION A -- DEFINITIONS The deductible is $500."). Any edit to the
heading then contaminated the coverage atom and surfaced as a phantom
[MODIFIED], even though the coverage text itself never changed.

an earlier fix: heading detection runs BEFORE sentence atomization and
is robust (accepts letter/digit/roman ids, "--"/em-dash/en-dash/colon
separators, a bare title-only line) and symmetric (the same shape
parses the same way regardless of side), so a heading is always its
own zero-body "section" clause -- never glued to the prose beneath it
-- and a heading-only edit (rename/add/remove/move) is suppressed via
report.py's existing "heading" finding kind, exactly like a moved-but-
unchanged clause.

These fixtures are original (not copies of the reviewer's an earlier audit
fixture/probe files) and exercise the general class.
"""
from policydiff.report import diff_documents, human_report
from policydiff.segment import segment


def _non_suppressed(result):
    return [f for f in result.findings if f.kind not in ("unchanged", "cosmetic", "heading")]


def test_heading_rename_over_identical_body_is_empty():
    # (a) A SECTION heading rename with the coverage sentence beneath it
    # byte-identical must produce an empty report -- not a phantom
    # [MODIFIED] built out of "<old heading> <sentence>" vs
    # "<new heading> <sentence>".
    old = "SECTION A -- DEFINITIONS\nThe policy limit is $250,000.\n"
    new = "SECTION A -- TERMS\nThe policy limit is $250,000.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert non_suppressed == [], [(f.kind, f.detail) for f in non_suppressed]
    assert "No coverage-relevant changes found." in human_report(result, verbose=False)


def test_bare_heading_added_above_unchanged_sentence_is_empty():
    # (b) Adding a bare "SECTION A" line above an otherwise-unchanged
    # sentence must not surface as a phantom modified/added finding.
    old = "The insured must report a loss within 60 days.\n"
    new = "SECTION A\nThe insured must report a loss within 60 days.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert non_suppressed == [], [(f.kind, f.detail) for f in non_suppressed]
    assert "No coverage-relevant changes found." in human_report(result, verbose=False)

    # Same shape with a blank line between header and body.
    new_blank = "SECTION A\n\nThe insured must report a loss within 60 days.\n"
    result_blank = diff_documents(old, new_blank, suppress_cosmetic=True)
    non_suppressed_blank = _non_suppressed(result_blank)
    assert non_suppressed_blank == [], [(f.kind, f.detail) for f in non_suppressed_blank]


def test_sentence_moved_across_bare_headers_bodies_unchanged_is_empty():
    # (c) Two coverage sentences swap which bare-heading section they
    # sit under; both bodies are byte-identical -- specification gate-1
    # moved-but-unchanged, must stay silent, not report two phantom
    # [MODIFIED] pairs.
    old = (
        "SECTION A\n"
        "The building limit is $400,000.\n"
        "SECTION B\n"
        "The contents limit is $100,000.\n"
    )
    new = (
        "SECTION A\n"
        "The contents limit is $100,000.\n"
        "SECTION B\n"
        "The building limit is $400,000.\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert non_suppressed == [], [(f.kind, f.detail) for f in non_suppressed]
    assert "No coverage-relevant changes found." in human_report(result, verbose=False)


def test_section_n_renamed_shape_is_symmetric_and_suppressed():
    # (d) "SECTION 1" vs "SECTION 1 (renamed)" must parse SYMMETRICALLY
    # (both recognized as a heading, neither glued to the following
    # sentence, no stray split-number leak) -- and the heading-only
    # diff itself must be a suppressed "heading" finding, never a
    # phantom coverage [MODIFIED].
    old = "SECTION 1\nThe deductible is $500.\n"
    new = "SECTION 1 (renamed)\nThe deductible is $500.\n"

    old_clauses = segment(old)
    new_clauses = segment(new)
    old_section = next(c for c in old_clauses if c.kind == "section")
    new_section = next(c for c in new_clauses if c.kind == "section")
    assert old_section.kind == new_section.kind == "section"
    # The body sentence must be its OWN atom on both sides, not glued
    # to the heading text.
    old_body = next(c for c in old_clauses if c.kind == "paragraph")
    new_body = next(c for c in new_clauses if c.kind == "paragraph")
    assert old_body.text == "The deductible is $500."
    assert new_body.text == "The deductible is $500."

    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert non_suppressed == [], [(f.kind, f.detail) for f in non_suppressed]
    heading_findings = [f for f in result.findings if f.kind == "heading"]
    assert heading_findings, "expected the renamed heading to surface as a suppressed 'heading' finding"


def test_double_dash_heading_separator_cites_clean_title_not_a_fragment():
    # The citation-fragment bug: "SECTION 4 -- EXCLUSIONS" must cite the
    # clean heading text "EXCLUSIONS", never a dash fragment like
    # "- EXCLUSIONS" (a single-char separator regex only ate one of the
    # two dashes in "--").
    clauses = segment("SECTION 4 -- EXCLUSIONS\nFlood damage is excluded.\n")
    section = next(c for c in clauses if c.kind == "section")
    assert section.heading == "EXCLUSIONS", repr(section.heading)
    assert not section.heading.startswith("-"), repr(section.heading)
    assert not section.text.startswith("-"), repr(section.text)


def test_guard_short_real_coverage_sentences_are_not_swallowed_as_headings():
    # GUARD: a short, unpunctuated-looking but ACTUALLY terminally
    # punctuated coverage sentence must remain a coverage atom, and an
    # edit to it must still be caught -- heading detection must never
    # cause a recall failure.
    old = "No coverage for flood.\nDeductible $500.\n"
    new = "No coverage for flood or earthquake.\nDeductible $750.\n"

    old_clauses = segment(old)
    new_clauses = segment(new)
    assert all(c.kind == "paragraph" for c in old_clauses)
    assert all(c.kind == "paragraph" for c in new_clauses)

    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 2, [(f.kind, f.detail) for f in non_suppressed]
    details = " ".join(f.detail for f in non_suppressed)
    assert "500" in details and "750" in details


def test_bare_all_caps_heading_with_no_keyword_is_its_own_atom():
    # The generic (no SECTION/ARTICLE keyword) bare-heading shape: a
    # short ALL-CAPS line with no terminal punctuation, sitting on its
    # own line above prose, must be its own zero-body heading atom, not
    # glued onto the sentence beneath it.
    clauses = segment("DEFINITIONS\nThe insured means the named entity.\n")
    kinds = [c.kind for c in clauses]
    assert kinds == ["section", "paragraph"], clauses
    assert clauses[0].text == "DEFINITIONS"
    assert clauses[1].text == "The insured means the named entity."
