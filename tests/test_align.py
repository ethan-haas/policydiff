"""Alignment tested independently of classification (gate 3).

A wrong alignment with a right classification is a coincidence -- assert
the clause PAIRING itself, separately from what each pair is classified
as.
"""
from policydiff.align import align
from policydiff.segment import segment


def test_moved_clause_pairs_to_its_content_twin(old_text, new_planted_text):
    old_clauses = segment(old_text)
    new_clauses = segment(new_planted_text)
    result = align(old_clauses, new_clauses)

    old_occurrence = next(c for c in old_clauses if c.text.startswith('"Occurrence" means'))
    new_occurrence = next(c for c in new_clauses if c.text.startswith('"Occurrence" means'))

    # Confirm it really did move: different id and different order_index.
    assert old_occurrence.id != new_occurrence.id or old_occurrence.order_index != new_occurrence.order_index

    pair = next((p for p in result.pairs if p.old is old_occurrence), None)
    assert pair is not None, "the Occurrence definition clause did not align at all"
    assert pair.new is new_occurrence, (
        f"Occurrence definition aligned to the wrong clause: "
        f"got new id={pair.new.id!r} heading={pair.new.heading!r}"
    )


def test_removed_and_added_clauses_are_unmatched(old_text, new_planted_text):
    old_clauses = segment(old_text)
    new_clauses = segment(new_planted_text)
    result = align(old_clauses, new_clauses)

    unmatched_old_texts = {c.text for c in result.unmatched_old}
    unmatched_new_texts = {c.text for c in result.unmatched_new}

    assert any("Medical Payments" in t for t in unmatched_old_texts)
    assert any("Bail Bonds" in t for t in unmatched_old_texts)
    assert any("Cyber Incident" in t for t in unmatched_new_texts)
    assert any("Duties in the Event of Occurrence" in t for t in unmatched_new_texts)
    assert len(result.unmatched_old) == 2
    assert len(result.unmatched_new) == 2


def test_renumbered_but_unchanged_clauses_all_align_by_content(old_text, old_noise_text):
    old_clauses = segment(old_text)
    new_clauses = segment(old_noise_text)
    result = align(old_clauses, new_clauses)

    assert len(result.unmatched_old) == 0
    assert len(result.unmatched_new) == 0
    assert len(result.pairs) == len(old_clauses) == len(new_clauses)

    # Every NUMBERED clause shifted by +100 in the noise fixture, so if
    # alignment were secretly number-based (not content-based) these
    # pairs could never form at all. Section headers keep the same roman
    # numeral on both sides, so they're excluded from this check.
    numeric_pairs = [p for p in result.pairs if p.old.kind == "numeric"]
    assert numeric_pairs, "expected at least one numbered-clause pair"
    for pair in numeric_pairs:
        assert pair.old.id != pair.new.id, (
            "pairing looks number-based, not content-based "
            f"(old id {pair.old.id} == new id {pair.new.id})"
        )
