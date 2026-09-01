"""Regression test for an earlier audit defects 2 & 3: an earlier revision's blank-line
paragraph segmentation (segment.py) made the NUMBER of blank lines
between sentences of unnumbered content a STRUCTURAL axis -- re-grouping
identical text at different blank-line boundaries changed the clause SET,
so:

  * inserting blank lines between existing sentences (a "split") read as
    one MODIFIED pair plus spurious ADDED clauses whose text was already
    verbatim present on the old side;
  * removing a blank line between two sentences (a "merge") read as a
    false REMOVED clause whose exact text was still present on the new
    side, just folded into a sibling -- a wrong-side coverage citation.

These fixtures are original (not copies of the reviewer's probe files) and
exercise the general class via policydiff.reconcile: a pure blank-line
re-partition of IDENTICAL content must be empty, but a real edit hiding
inside one of the re-partitioned pieces must still be caught, correctly
directioned, with a citation on both sides.
"""
from policydiff.report import diff_documents, human_report


def _non_suppressed(result):
    return [f for f in result.findings if f.kind not in ("unchanged", "cosmetic")]


def test_pure_split_of_identical_text_is_empty():
    old = "Alpha clause text.\nBeta clause text.\nGamma clause text.\n"
    new = "Alpha clause text.\n\nBeta clause text.\n\nGamma clause text.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert non_suppressed == [], (
        f"pure blank-line split of identical text leaked findings: "
        f"{[(f.kind, f.detail) for f in non_suppressed]}"
    )
    assert "No coverage-relevant changes found." in human_report(result, verbose=False)


def test_pure_merge_of_identical_text_is_empty():
    old = (
        "PREAMBLE\n"
        "\n"
        "The named insured is Acme Corp.\n"
        "\n"
        "The policy period is one year.\n"
        "\n"
        "The premium is $5,000.\n"
    )
    new = (
        "PREAMBLE\n"
        "\n"
        "The named insured is Acme Corp.  The policy period is one year.\n"
        "\n"
        "The premium is $5,000.\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert non_suppressed == [], (
        f"pure blank-line merge of identical text leaked findings: "
        f"{[(f.kind, f.detail) for f in non_suppressed]}"
    )
    assert "No coverage-relevant changes found." in human_report(result, verbose=False)


def test_split_with_one_genuinely_edited_piece_is_not_suppressed():
    # Same shape as the pure-split case, but the middle sentence's dollar
    # figure actually changed -- this must NOT get coalesced away by the
    # split/merge reconciliation; it must surface as exactly one finding,
    # correctly directioned, with a citation on both sides.
    old = "Alpha clause text.\nThe sublimit is $500.\nGamma clause text.\n"
    new = "Alpha clause text.\n\nThe sublimit is $1,000.\n\nGamma clause text.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, (
        f"expected exactly one finding for the edited piece, got: "
        f"{[(f.kind, f.detail) for f in non_suppressed]}"
    )
    f = non_suppressed[0]
    # Not a "deductible", so classify.py treats a rising numeric limit as
    # more coverage available -- broadened.
    assert f.kind == "broadened", f.detail
    assert "500" in f.detail and "1,000" in f.detail
    assert f.old is not None and f.new is not None, "edited piece must carry both-side citation"
    assert "$1,000" in f.new.text


def test_unrelated_real_edit_outside_any_split_or_merge_is_still_caught():
    # Sanity guard: an ordinary same-count paragraph edit (no blank-line
    # restructuring at all) must be completely unaffected by the
    # reconciliation pass -- an earlier revision's win must not regress.
    old = "DECLARATIONS\nThe limit of liability is $1,000,000.\n"
    new = "DECLARATIONS\nThe limit of liability is $750,000.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1
    assert non_suppressed[0].kind == "narrowed"
    assert "1,000,000" in non_suppressed[0].detail and "750,000" in non_suppressed[0].detail
