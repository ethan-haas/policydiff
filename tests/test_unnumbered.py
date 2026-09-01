"""Regression tests for defect 1: the segmenter used to emit
ZERO clauses for any text block lacking a leading enumerator, so a real
change hiding in an unnumbered declarations/preamble/endorsement block --
or an entire unnumbered document -- silently vanished from the report.

These fixtures are original (not copied from the reviewer's probe/fixture
files) and exercise the GENERAL CLASS of the bug: unnumbered content must
always be segmented into diffable "paragraph" clauses, whether it's a
preamble before the first numbered header or the whole document.
"""
from policydiff.report import diff_documents
from policydiff.segment import segment


def test_unnumbered_preamble_change_is_reported():
    old = (
        "DECLARATIONS\n"
        "The named insured limit of liability is $1,000,000.\n"
        "\n"
        "1. Coverage A. The company pays covered losses.\n"
        "2. Exclusion -- War. This insurance does not apply to war.\n"
    )
    new = (
        "DECLARATIONS\n"
        "The named insured limit of liability is $750,000.\n"
        "\n"
        "1. Coverage A. The company pays covered losses.\n"
        "2. Exclusion -- War. This insurance does not apply to war.\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = [f for f in result.findings if f.kind not in ("unchanged", "cosmetic")]

    assert len(non_suppressed) == 1, (
        f"expected exactly the preamble limit change, got: "
        f"{[(f.kind, f.detail) for f in non_suppressed]}"
    )
    f = non_suppressed[0]
    assert f.kind == "narrowed", f.detail
    assert "1,000,000" in f.detail and "750,000" in f.detail


def test_unchanged_preamble_produces_no_finding():
    old = (
        "DECLARATIONS\n"
        "The named insured limit of liability is $1,000,000.\n"
        "\n"
        "1. Coverage A. The company pays covered losses.\n"
    )
    new = old  # byte-identical
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = [f for f in result.findings if f.kind not in ("unchanged", "cosmetic")]
    assert non_suppressed == []


def test_entirely_unnumbered_document_is_still_segmented_and_diffed():
    # No enumerators anywhere in either version -- the degenerate case
    # where the old segmenter returned an EMPTY clause list. an earlier revision's
    # sentence-atom fix means this two-sentence blob segments into TWO
    # clauses (one per sentence), not one -- see tests/test_sentence_atom
    # for the design rationale; what matters here is nothing is dropped
    # and the real change is still isolated to exactly one finding.
    old = "Coverage grant with no numbering. Loss is covered up to $500,000."
    new = "Coverage grant with no numbering. Loss is covered up to $250,000."

    old_clauses = segment(old)
    new_clauses = segment(new)
    assert len(old_clauses) == 2
    assert len(new_clauses) == 2
    assert all(c.id for c in old_clauses)  # a synthesized id must exist, never blank/None

    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = [f for f in result.findings if f.kind not in ("unchanged", "cosmetic")]
    assert len(non_suppressed) == 1
    assert non_suppressed[0].kind == "narrowed"


def test_unnumbered_document_with_multiple_paragraphs_segments_each_separately():
    old = "Paragraph one about coverage.\n\nParagraph two about exclusions.\n"
    new = "Paragraph one about coverage.\n\nParagraph two about exclusions and flood.\n"

    old_clauses = segment(old)
    new_clauses = segment(new)
    assert len(old_clauses) == 2
    assert len(new_clauses) == 2
    # Distinct synthesized ids -- not all collapsed into one blob.
    assert old_clauses[0].id != old_clauses[1].id

    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = [f for f in result.findings if f.kind not in ("unchanged", "cosmetic")]
    assert len(non_suppressed) == 1
    assert "flood" in (non_suppressed[0].new.text if non_suppressed[0].new else "")
