"""Regression test for an earlier audit defect 4: a very short (2-token)
label+amount row -- "Deductible $500." -> "Deductible $1,000." -- is too
terse for either alignment pass in align.py to pair to its own twin (a
numeric edit changes every 3-word shingle, and the changed number itself
tokenizes to different unigrams -- "500" vs "1"/"000" -- pulling unigram
Jaccard below threshold too), so it degraded into a decoupled
REMOVED+ADDED instead of one directioned pair. Deductible/sublimit rows
are exactly the terse, coverage-critical lines where losing direction
matters most to an underwriter.

These fixtures are original (not copies of the reviewer's probe files) and
exercise the general class via align.py's third (label-based) pass.
"""
from policydiff.align import align
from policydiff.report import diff_documents
from policydiff.segment import segment


def _non_suppressed(result):
    return [f for f in result.findings if f.kind not in ("unchanged", "cosmetic")]


def test_terse_deductible_increase_pairs_as_one_narrowed_finding():
    old = "1. Deductible $500.\n"
    new = "1. Deductible $1,000.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert f.kind == "narrowed", f.detail
    assert f.old is not None and f.new is not None, "must carry both-side citation"
    assert "500" in f.detail and "1,000" in f.detail


def test_terse_limit_increase_pairs_as_one_broadened_finding():
    old = "1. Pay $200.\n"
    new = "1. Pay $250.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert f.kind == "broadened", f.detail
    assert f.old is not None and f.new is not None


def test_two_different_label_short_rows_do_not_cross_pair():
    # Guard: "Deductible $500" must never pair to "Sublimit $500" just
    # because both are short and share a dollar figure.
    old_clauses = segment("1. Deductible $500.\n2. Sublimit $500.\n")
    new_clauses = segment("1. Sublimit $600.\n2. Deductible $700.\n")
    result = align(old_clauses, new_clauses)

    by_old_label = {p.old.text.split()[0]: p for p in result.pairs}
    assert "Deductible" in by_old_label, "the deductible row failed to pair at all"
    assert "Sublimit" in by_old_label, "the sublimit row failed to pair at all"
    assert by_old_label["Deductible"].new.text.startswith("Deductible"), (
        "Deductible row cross-paired to the Sublimit row: "
        f"{by_old_label['Deductible'].new.text!r}"
    )
    assert by_old_label["Sublimit"].new.text.startswith("Sublimit"), (
        "Sublimit row cross-paired to the Deductible row: "
        f"{by_old_label['Sublimit'].new.text!r}"
    )
    assert result.unmatched_old == []
    assert result.unmatched_new == []
