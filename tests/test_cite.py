"""Citation-resolves test (gate 4).

For every finding, the cited clause id must exist on the stated side and
the quoted text must be a literal substring of that clause's text.
"""
from policydiff.cite import quote_is_substring
from policydiff.report import diff_documents


def _clause_by_id(clauses, clause_id):
    matches = [c for c in clauses if c.id == clause_id]
    assert matches, f"cited clause id {clause_id!r} does not exist in this document"
    return matches


def test_every_citation_resolves_on_both_sides(old_text, new_planted_text):
    result = diff_documents(old_text, new_planted_text, suppress_cosmetic=True)
    assert result.citations, "expected at least one citation to check"

    checked = 0
    for c in result.citations:
        if c.old_clause_id is not None:
            candidates = _clause_by_id(result.old_clauses, c.old_clause_id)
            assert any(quote_is_substring(c.old_quote, cl.text) for cl in candidates), (
                f"old_quote for {c.kind} finding does not resolve on the old side: "
                f"id={c.old_clause_id!r} quote={c.old_quote!r}"
            )
            checked += 1
        if c.new_clause_id is not None:
            candidates = _clause_by_id(result.new_clauses, c.new_clause_id)
            assert any(quote_is_substring(c.new_quote, cl.text) for cl in candidates), (
                f"new_quote for {c.kind} finding does not resolve on the new side: "
                f"id={c.new_clause_id!r} quote={c.new_quote!r}"
            )
            checked += 1
    assert checked > 0


def test_added_finding_has_new_side_only(old_text, new_planted_text):
    result = diff_documents(old_text, new_planted_text, suppress_cosmetic=True)
    added = [c for c in result.citations if c.kind == "added"]
    assert added, "expected at least one 'added' finding"
    for c in added:
        assert c.old_clause_id is None
        assert c.old_quote is None
        assert c.new_clause_id is not None
        assert c.new_quote is not None


def test_removed_finding_has_old_side_only(old_text, new_planted_text):
    result = diff_documents(old_text, new_planted_text, suppress_cosmetic=True)
    removed = [c for c in result.citations if c.kind == "removed"]
    assert removed, "expected at least one 'removed' finding"
    for c in removed:
        assert c.new_clause_id is None
        assert c.new_quote is None
        assert c.old_clause_id is not None
        assert c.old_quote is not None


def test_ten_random_findings_resolve(old_text, new_planted_text):
    import random

    result = diff_documents(old_text, new_planted_text, suppress_cosmetic=True)
    rng = random.Random(1234)
    sample = rng.sample(result.citations, k=min(10, len(result.citations)))
    for c in sample:
        if c.old_clause_id is not None:
            cl = _clause_by_id(result.old_clauses, c.old_clause_id)[0]
            assert quote_is_substring(c.old_quote, cl.text)
        if c.new_clause_id is not None:
            cl = _clause_by_id(result.new_clauses, c.new_clause_id)[0]
            assert quote_is_substring(c.new_quote, cl.text)
