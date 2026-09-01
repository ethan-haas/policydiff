"""Regression test for the alignment-pairing item in the an earlier audit fix
round: a SHORT clause with a small edit (e.g. a percentage or a single
antonym word swapped) can fall below the primary 3-word-shingle Jaccard
threshold -- on a 6-word clause a 2-word substitution flips most of its
4 total shingles -- and gets reported as an unrelated remove+add instead
of a paired "modified", losing direction and both-side citation.

These fixtures are original (a coinsurance percentage bump, an
including/excluding antonym swap), not copies of the reviewer's files.
The near-duplicate guard test proves the fix doesn't over-match: with
TWO short leftover clauses on each side, each must still pair to its
own right twin, not a similar-but-different one.
"""
from policydiff.align import align
from policydiff.report import diff_documents
from policydiff.segment import segment


def test_short_edited_clause_pairs_as_modified_not_remove_plus_add():
    old = "1. Coinsurance. An 80% coinsurance clause applies.\n"
    new = "1. Coinsurance. A 90% coinsurance clause applies.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)

    kinds = [f.kind for f in result.findings]
    assert kinds == ["modified"] or (len(kinds) == 1 and kinds[0] not in ("added", "removed")), kinds
    finding = result.findings[0]
    assert finding.old is not None and finding.new is not None, (
        "short edited clause must pair to its twin (both-side citation), "
        "not split into separate remove+add findings"
    )


def test_short_antonym_swap_pairs_and_narrows():
    old = "1. Territory. Coverage applies worldwide including offshore installations.\n"
    new = "1. Territory. Coverage applies worldwide excluding offshore installations.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)

    non_suppressed = [f for f in result.findings if f.kind not in ("unchanged", "cosmetic")]
    assert len(non_suppressed) == 1
    f = non_suppressed[0]
    assert f.old is not None and f.new is not None
    assert f.kind == "narrowed", f.detail


def test_near_duplicate_short_clauses_pair_to_the_right_twin_not_each_other():
    # Two SHORT, topically-similar-but-distinct clauses on each side.
    # The second-pass matcher must not cross-pair clause A's old text to
    # clause B's new text (or vice versa) just because they're both
    # short and share boilerplate words.
    old_text = (
        "1. Coinsurance. An 80% coinsurance clause applies.\n"
        "2. Valuation. A 50% valuation clause applies.\n"
    )
    new_text = (
        "1. Coinsurance. A 90% coinsurance clause applies.\n"
        "2. Valuation. A 60% valuation clause applies.\n"
    )
    old_clauses = segment(old_text)
    new_clauses = segment(new_text)
    result = align(old_clauses, new_clauses)

    assert len(result.unmatched_old) == 0
    assert len(result.unmatched_new) == 0
    assert len(result.pairs) == 2

    by_old_heading = {p.old.heading.split(".")[0].strip(): p for p in result.pairs}
    coinsurance_pair = by_old_heading["Coinsurance"]
    valuation_pair = by_old_heading["Valuation"]
    assert "coinsurance" in coinsurance_pair.new.text.lower()
    assert "90%" in coinsurance_pair.new.text
    assert "valuation" in valuation_pair.new.text.lower()
    assert "60%" in valuation_pair.new.text
