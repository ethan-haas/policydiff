"""Regression tests for an earlier audit's defects: unnumbered prose was being
segmented at BLANK-LINE PARAGRAPH granularity (segment.py), which is
itself a cosmetic axis -- when a re-partitioned block also contained one
real edit, the earlier all-or-nothing paragraph-run reconciliation
(reconcile.py, since REMOVED) collapsed: surviving sibling sentences
surfaced as phantom ADDED/REMOVED findings, and the real change was
mis-directioned and mis-cited.

an earlier fix: the stable atom for unnumbered prose is the SENTENCE
(policydiff/sentence.py), not the blank-line block, so paragraph
regrouping is a no-op on the atom set and ordinary content alignment
(align.py) + classification (classify.py) handle every shape uniformly.

These fixtures are original (not copies of the reviewer's an earlier audit
fixture/probe files) and exercise the general class.
"""
from policydiff.report import diff_documents, human_report
from policydiff.segment import segment
from policydiff.sentence import split_sentences


def _non_suppressed(result):
    return [f for f in result.findings if f.kind not in ("unchanged", "cosmetic", "heading")]


def test_one_paragraph_split_into_three_sentences_with_two_real_narrowings():
    # (a) one blank-line paragraph -> three separately-punctuated
    # sentences, TWO of which carry a real (narrowing) edit. Must be
    # exactly two NARROWED findings, no phantom ADDED/REMOVED/MODIFIED.
    old = (
        "The aggregate limit of insurance is $1,000,000. "
        "Notice of occurrence must be given promptly. "
        "The deductible for each claim is $500.\n"
    )
    new = (
        "The aggregate limit of insurance is $500,000.\n"
        "\n"
        "Notice of occurrence must be given promptly.\n"
        "\n"
        "The deductible for each claim is $1,000.\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 2, [(f.kind, f.detail) for f in non_suppressed]
    kinds = {f.kind for f in non_suppressed}
    assert kinds == {"narrowed"}, [(f.kind, f.detail) for f in non_suppressed]
    details = " ".join(f.detail for f in non_suppressed)
    assert "1,000,000" in details and "500,000" in details
    assert "500" in details and "1,000" in details
    for f in non_suppressed:
        assert f.old is not None and f.new is not None, "both-side citation required"


def test_merge_that_drops_one_coverage_sentence_reports_exactly_one_removed():
    # (b) a merge across a blank line that DROPS one whole coverage
    # sentence -- surviving siblings must stay silent (matched to their
    # own twin), not surface as phantom REMOVED/ADDED.
    old = (
        "Coverage A pays for bodily injury liability up to the limit shown.\n"
        "\n"
        "Coverage B pays for medical expenses regardless of fault up to $5,000.\n"
        "\n"
        "Coverage C pays for property damage liability up to the limit shown.\n"
    )
    new = (
        "Coverage A pays for bodily injury liability up to the limit shown. "
        "Coverage C pays for property damage liability up to the limit shown.\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert f.kind == "removed", f.detail
    assert "Coverage B" in f.old.text
    assert f.new is None


def test_sentence_moved_across_a_header_is_empty():
    # (c) a sentence physically relocated from under one SECTION header
    # to under another, with byte-identical text -- must align by
    # content and produce an EMPTY report (no phantom removed/added/
    # broadened, and the bare headings themselves are not findings).
    old = (
        "SECTION I - PROPERTY\n"
        "\n"
        "The insured location includes all buildings described in the declarations.\n"
        "\n"
        "SECTION II - LIABILITY\n"
        "\n"
        "The company will defend the insured against covered suits.\n"
    )
    new = (
        "SECTION I - PROPERTY\n"
        "\n"
        "SECTION II - LIABILITY\n"
        "\n"
        "The company will defend the insured against covered suits.\n"
        "\n"
        "The insured location includes all buildings described in the declarations.\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert non_suppressed == [], [(f.kind, f.detail) for f in non_suppressed]
    assert "No coverage-relevant changes found." in human_report(result, verbose=False)


def test_pure_sentence_regroup_is_empty():
    # (d) a pure blank-line regroup of identical sentences (no real
    # edit anywhere) -- must be completely empty regardless of which
    # side is more/less blank-line-fragmented.
    old = (
        "This policy provides coverage for direct physical loss to the "
        "insured premises. Coverage applies only to losses occurring "
        "during the policy period stated in the declarations. The maximum "
        "amount payable for any single occurrence is $500,000 under this "
        "endorsement.\n"
    )
    new = (
        "This policy provides coverage for direct physical loss to the "
        "insured premises.\n"
        "\n"
        "Coverage applies only to losses occurring during the policy "
        "period stated in the declarations.\n"
        "\n"
        "The maximum amount payable for any single occurrence is $500,000 "
        "under this endorsement.\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert non_suppressed == [], [(f.kind, f.detail) for f in non_suppressed]
    assert "No coverage-relevant changes found." in human_report(result, verbose=False)

    # And the reverse direction (new is more merged than old) too.
    result2 = diff_documents(new, old, suppress_cosmetic=True)
    non_suppressed2 = _non_suppressed(result2)
    assert non_suppressed2 == [], [(f.kind, f.detail) for f in non_suppressed2]


def test_sentence_splitter_does_not_break_on_money_abbreviations_or_initials():
    # (e) the sentence splitter must not fragment a real sentence at a
    # decimal-money period, a common abbreviation, or an initial.
    text = (
        "The premium is $1,000.00 due at inception. "
        "This policy is governed by U.S. law and applicable state statutes. "
        "XYZ Inc. will administer all claims. "
        "See Endorsement No. 5 for details, e.g. flood and earthquake. "
        "Notice may be sent to J. Smith at the address on file."
    )
    sentences = split_sentences(text)
    assert sentences == [
        "The premium is $1,000.00 due at inception.",
        "This policy is governed by U.S. law and applicable state statutes.",
        "XYZ Inc. will administer all claims.",
        "See Endorsement No. 5 for details, e.g. flood and earthquake.",
        "Notice may be sent to J. Smith at the address on file.",
    ], sentences


def test_bare_heading_rename_and_bare_heading_added_are_not_coverage_findings():
    # A SECTION heading that's genuinely renamed, and one that's newly
    # inserted with no body under it, must not surface as a coverage
    # added/removed/broadened/narrowed/modified finding (point 4 of the
    # fix spec) -- but a real coverage change elsewhere must still be
    # fully reported.
    old = (
        "SECTION I - PROPERTY\n"
        "\n"
        "1. Coverage A. The limit is $100,000.\n"
    )
    new = (
        "SECTION I - REAL PROPERTY\n"
        "\n"
        "SECTION II - RESERVED\n"
        "\n"
        "1. Coverage A. The limit is $50,000.\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    assert non_suppressed[0].kind == "narrowed"
    assert "100,000" in non_suppressed[0].detail and "50,000" in non_suppressed[0].detail
    heading_findings = [f for f in result.findings if f.kind == "heading"]
    assert heading_findings, "expected the renamed/added headings to be classified as 'heading', not silently vanish from findings entirely"
