"""Regression tests for an earlier fix (defect: 1 root-cause
defect, 1 manifestation) against HEAD
ac9d7cd -- an ALIGNMENT defect (a real coverage cut disguised as ADDED,
and an increase reported as REMOVED).

The defect: alignment similarity (policydiff/align.py) scored two clauses
by Jaccard overlap of their FULL lowercased token stream, including bare
numeric tokens pulled out of a dollar amount ("$1,000,000" -> "1"/"000"/
"000"). An amount is exactly the part of a schedule row a revision is
EXPECTED to change; the row's LABEL ("Each Occurrence Limit" / "General
Aggregate Limit") is its stable identity. When a routine revision moved
one row's OLD amount onto a DIFFERENT row (raise Each Occurrence to what
the Aggregate used to be, while cutting the Aggregate), the two rows that
merely shared a coincidental numeric literal outscored the two rows that
actually shared a label:

    OLD:  Each Occurrence Limit $1,000,000    NEW:  Each Occurrence Limit $2,000,000
          General Aggregate Limit $2,000,000        General Aggregate Limit $1,500,000

Old General Aggregate ($2,000,000) and new Each Occurrence ($2,000,000)
shared two 3-word shingles built out of the amount digits and cross-paired
as "[MODIFIED direction unclear]"; the two genuinely-related rows (each
sharing only its label, not its now-different amount) fell out unmatched
and were reported as a decoupled "[REMOVED] Each Occurrence ... $1,000,000"
+ "[ADDED] General Aggregate ... $1,500,000" -- losing both real direction
changes and disguising the (underwriting-critical) Aggregate CUT as a
brand-new clause.

Root fix (see policydiff/align.py's an earlier revision module docstring):
`_shingles`/`_word_set` now strip purely-numeric tokens out of the content
stream used for similarity scoring, via a shared `_content_words` helper.
A row's alignment score is now judged on its label words alone; the
changed amount can never out-vote the shared label, and can never cause a
false match between two DIFFERENT rows that happen to share one number.

None of these fixtures are copies of any reviewer probe/fixture file under
the audit fixtures
FORBIDDEN clause) -- they are original clauses built from the scenario
described in the task.
"""
from policydiff.align import align
from policydiff.report import diff_documents
from policydiff.segment import segment


def _non_suppressed(result):
    return [f for f in result.findings if f.kind not in ("unchanged", "cosmetic", "heading")]


# ---------------------------------------------------------------------
# (a) -- the live-reproduced collision: exactly BROADENED Each Occurrence
# + NARROWED General Aggregate, no REMOVED/ADDED/cross-pair MODIFIED.
# ---------------------------------------------------------------------


def test_amount_collision_schedule_rows_align_by_label_not_amount():
    old = "Each Occurrence Limit $1,000,000\nGeneral Aggregate Limit $2,000,000\n"
    new = "Each Occurrence Limit $2,000,000\nGeneral Aggregate Limit $1,500,000\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)

    kinds = sorted(f.kind for f in non_suppressed)
    assert kinds == ["broadened", "narrowed"], [(f.kind, f.detail) for f in non_suppressed]
    assert not any(f.kind in ("added", "removed") for f in non_suppressed)
    assert not any("direction unclear" in f.detail for f in non_suppressed)

    broadened = next(f for f in non_suppressed if f.kind == "broadened")
    narrowed = next(f for f in non_suppressed if f.kind == "narrowed")

    assert broadened.old is not None and broadened.new is not None
    assert "Each Occurrence" in broadened.old.text and "Each Occurrence" in broadened.new.text
    assert "1,000,000" in broadened.detail and "2,000,000" in broadened.detail

    assert narrowed.old is not None and narrowed.new is not None
    assert "General Aggregate" in narrowed.old.text and "General Aggregate" in narrowed.new.text
    assert "2,000,000" in narrowed.detail and "1,500,000" in narrowed.detail


def test_amount_collision_alignment_pairs_own_twins_directly():
    # Same scenario at the align() layer, independent of classification
    # (gate 3 style -- see tests/test_align.py's module docstring).
    old_clauses = segment("Each Occurrence Limit $1,000,000\nGeneral Aggregate Limit $2,000,000\n")
    new_clauses = segment("Each Occurrence Limit $2,000,000\nGeneral Aggregate Limit $1,500,000\n")
    result = align(old_clauses, new_clauses)

    assert result.unmatched_old == []
    assert result.unmatched_new == []
    assert len(result.pairs) == 2

    by_old = {p.old.text.split(" $")[0]: p for p in result.pairs}
    assert by_old["Each Occurrence Limit"].new.text.startswith("Each Occurrence Limit")
    assert by_old["General Aggregate Limit"].new.text.startswith("General Aggregate Limit")


# ---------------------------------------------------------------------
# (b) -- three schedule rows: two swap amounts (colliding), one is
# genuinely removed. Expect 2 directional findings + 1 removed, and the
# genuinely-removed row must never be swept into either swap pair.
# ---------------------------------------------------------------------


def test_three_row_schedule_two_swap_one_genuinely_removed():
    old = (
        "Each Occurrence Limit $1,000,000\n"
        "General Aggregate Limit $2,000,000\n"
        "Products/Completed Operations Aggregate $2,000,000\n"
    )
    new = (
        "Each Occurrence Limit $2,000,000\n"
        "General Aggregate Limit $1,500,000\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)

    kinds = sorted(f.kind for f in non_suppressed)
    assert kinds == ["broadened", "narrowed", "removed"], [(f.kind, f.detail) for f in non_suppressed]

    removed = next(f for f in non_suppressed if f.kind == "removed")
    assert "Products/Completed Operations Aggregate" in removed.old.text

    broadened = next(f for f in non_suppressed if f.kind == "broadened")
    assert "Each Occurrence" in broadened.old.text

    narrowed = next(f for f in non_suppressed if f.kind == "narrowed")
    assert "General Aggregate" in narrowed.old.text
    assert "Products" not in narrowed.old.text and "Products" not in narrowed.new.text


# ---------------------------------------------------------------------
# (c) -- a genuinely added schedule row (new label, no collision) ->
# ADDED; a genuinely removed row (old label, no collision) -> REMOVED.
# ---------------------------------------------------------------------


def test_genuinely_added_and_removed_schedule_rows_stay_added_and_removed():
    old = (
        "Each Occurrence Limit $1,000,000\n"
        "Fire Legal Liability $100,000\n"
    )
    new = (
        "Each Occurrence Limit $1,000,000\n"
        "Employee Benefits Liability $1,000,000\n"
    )
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)

    kinds = sorted(f.kind for f in non_suppressed)
    assert kinds == ["added", "removed"], [(f.kind, f.detail) for f in non_suppressed]

    removed = next(f for f in non_suppressed if f.kind == "removed")
    assert "Fire Legal Liability" in removed.old.text

    added = next(f for f in non_suppressed if f.kind == "added")
    assert "Employee Benefits Liability" in added.new.text


# ---------------------------------------------------------------------
# (d) -- colon-row variant of the same collision ("Each Occurrence
# Limit: $1,000,000") must resolve identically.
# ---------------------------------------------------------------------


def test_amount_collision_colon_row_variant():
    old = "Each Occurrence Limit: $1,000,000\nGeneral Aggregate Limit: $2,000,000\n"
    new = "Each Occurrence Limit: $2,000,000\nGeneral Aggregate Limit: $1,500,000\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)

    kinds = sorted(f.kind for f in non_suppressed)
    assert kinds == ["broadened", "narrowed"], [(f.kind, f.detail) for f in non_suppressed]
    assert not any("direction unclear" in f.detail for f in non_suppressed)


# ---------------------------------------------------------------------
# (e) GUARD -- near-duplicate prose clauses (no numeric collision) still
# pair to the correct twin; non-regression of ordinary content alignment.
# ---------------------------------------------------------------------


def test_near_duplicate_prose_clauses_still_pair_to_correct_twin():
    old_text = (
        "1. Water Damage. Coverage applies to sudden and accidental water damage.\n"
        "2. Mold Damage. Coverage applies to mold resulting from a covered cause of loss.\n"
    )
    new_text = (
        "1. Water Damage. Coverage applies to sudden and accidental water and sewer damage.\n"
        "2. Mold Damage. Coverage excludes mold resulting from a covered cause of loss.\n"
    )
    old_clauses = segment(old_text)
    new_clauses = segment(new_text)
    result = align(old_clauses, new_clauses)

    assert result.unmatched_old == []
    assert result.unmatched_new == []
    assert len(result.pairs) == 2

    by_old_heading = {p.old.heading.split(".")[0].strip(): p for p in result.pairs}
    water_pair = by_old_heading["Water Damage"]
    mold_pair = by_old_heading["Mold Damage"]
    assert "Water Damage" in water_pair.new.heading
    assert "Mold Damage" in mold_pair.new.heading
