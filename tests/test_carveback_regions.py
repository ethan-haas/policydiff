"""Regression tests for an earlier fix (1 WRONG-DIRECTION
defect, specification's worst class, with 2 mirror reproductions, reproduced live by
an independent review).

Defect (wrong-direction): an exclusion carve-back of the form
"does not apply to <BASE>, except <EXCEPTION>" has TWO regions with
OPPOSITE coverage polarity -- growing the BASE narrows coverage (more is
excluded) while growing the EXCEPTION broadens it (more loss is carved
back INTO coverage). an earlier revision fixed the case where the carve-back MARKER
itself is added or removed (ADD/REMOVE precedence over the numeric rule);
this is the DIFFERENT case of a change made INSIDE a carve-back that is
already present on BOTH sides -- classify._classify_exclusion applied the
BASE-exclusion "peril span added -> narrowed" / "peril span removed ->
broadened" reading uniformly to the whole clause, so a span landing
inside the EXCEPTION got exactly the wrong (inverted) answer:

    "This insurance does not apply to loss caused by pollution, except
    loss caused by a hostile fire."
    + exception ENLARGED ("...fire or by equipment used to heat the
      insured premises.") -> [NARROWED] "additional exclusionary
      language added" (WRONG -- more loss carved back INTO coverage;
      must be BROADENED)
    - exception SHRUNK (mirror: "...fire or by heat, smoke or fumes."
      -> "...fire.") -> [BROADENED] "excluded peril removed" (WRONG --
      less loss carved back, i.e. LESS coverage; must be NARROWED)

Root fix (classify.py): when the SAME carve-back marker (except/unless/
however/"but this exclusion does not apply"/"does not apply to the
first"/"we will pay up to") is present on BOTH old and new text, every
inserted/removed word span from the word-level diff is additionally
scoped to the BASE region (before the marker) or the EXCEPTION region
(at/after the marker) via _carveback_boundary_index/_carveback_region. A
span confined to the BASE keeps the ordinary base-exclusion reading; a
span confined to the EXCEPTION gets that reading INVERTED; a span that
itself straddles the boundary (or a clause with conflicting votes from
both regions) resolves honestly to "modified (direction unclear)" rather
than being guessed. an earlier revision's marker-added/removed precedence, and the
already-correct "carve-back cap changed with equal $-count on both
sides" numeric path, are both untouched -- neither carries a marker on
only one side, and the equal-count numeric case never reaches
_classify_exclusion at all.

None of these fixtures are copies of any reviewer's probe/fixture files
under the audit fixtures
task's FORBIDDEN clause) -- they are original clauses authored from the
task's own description of the defect and its generalizations, matching
the SAME pollution/hostile-fire carve-back scenario the live repro used.
"""
from policydiff.classify import classify_pair
from policydiff.segment import segment


def _pair(old_text: str, new_text: str, heading: str = "Exclusion - Pollution"):
    old = segment(f"1. {heading}. {old_text}\n")[0]
    new = segment(f"1. {heading}. {new_text}\n")[0]
    return classify_pair(old, new, suppress_cosmetic=True)


_POLLUTION_WITH_FIRE_CARVEBACK = (
    "This insurance does not apply to loss caused by pollution, except "
    "loss caused by a hostile fire."
)


# ---------------------------------------------------------------------
# (a) exception ENLARGED (more carved back into coverage) -> BROADENED.
#     The primary defect, reproduced live above.
# ---------------------------------------------------------------------


def test_exception_enlarged_is_broadened():
    f = _pair(
        _POLLUTION_WITH_FIRE_CARVEBACK,
        "This insurance does not apply to loss caused by pollution, except "
        "loss caused by a hostile fire or by equipment used to heat the "
        "insured premises.",
    )
    assert f.kind == "broadened", f.detail


def test_exception_enlarged_generalizes_other_carveback_markers():
    # "unless" carve-back, same shape: growing the carved-back exception
    # broadens.
    f = _pair(
        "This insurance does not apply to loss caused by wear and tear, "
        "unless the wear and tear results from a covered peril.",
        "This insurance does not apply to loss caused by wear and tear, "
        "unless the wear and tear results from a covered peril or from a "
        "hidden plumbing leak.",
    )
    assert f.kind == "broadened", f.detail


# ---------------------------------------------------------------------
# (b) exception SHRUNK (less carved back into coverage) -> NARROWED.
#     Mirror image of (a), reproduced live above.
# ---------------------------------------------------------------------


def test_exception_shrunk_is_narrowed():
    f = _pair(
        "This insurance does not apply to pollution, except loss caused by "
        "a hostile fire or by heat, smoke or fumes.",
        "This insurance does not apply to pollution, except loss caused by "
        "a hostile fire.",
    )
    assert f.kind == "narrowed", f.detail


# ---------------------------------------------------------------------
# (c) a BRAND-NEW carve-back (marker present on only one side) still
#     BROADENS -- an earlier revision's ADD/REMOVE precedence, must stay unchanged.
# ---------------------------------------------------------------------


def test_new_carveback_added_is_still_broadened():
    f = _pair(
        "This insurance does not apply to loss caused by pollution.",
        _POLLUTION_WITH_FIRE_CARVEBACK,
    )
    assert f.kind == "broadened", f.detail
    assert "carve-back added" in f.detail


def test_carveback_removed_is_still_narrowed():
    f = _pair(
        _POLLUTION_WITH_FIRE_CARVEBACK,
        "This insurance does not apply to loss caused by pollution.",
    )
    assert f.kind == "narrowed", f.detail


# ---------------------------------------------------------------------
# (d) BASE grows (more excluded) with the exception UNCHANGED ->
#     NARROWED, exactly like an ordinary exclusion -- must stay
#     unchanged (this is the base-region guard the fix must not break).
# ---------------------------------------------------------------------


def test_base_peril_added_before_except_is_narrowed():
    f = _pair(
        _POLLUTION_WITH_FIRE_CARVEBACK,
        "This insurance does not apply to loss caused by pollution or "
        "contamination, except loss caused by a hostile fire.",
    )
    assert f.kind == "narrowed", f.detail


def test_base_peril_removed_before_except_is_broadened():
    f = _pair(
        "This insurance does not apply to loss caused by pollution or "
        "contamination, except loss caused by a hostile fire.",
        _POLLUTION_WITH_FIRE_CARVEBACK,
    )
    assert f.kind == "broadened", f.detail


# ---------------------------------------------------------------------
# (e) a numeric cap INSIDE the exception raised/lowered -> BROADENED /
#     NARROWED (already correct via the equal-$-count numeric path, kept
#     consistent with the new region-scoping rule).
# ---------------------------------------------------------------------


def test_exception_cap_raised_is_broadened():
    f = _pair(
        "This insurance does not apply to loss caused by pollution, "
        "except we will pay up to $10,000 for such loss.",
        "This insurance does not apply to loss caused by pollution, "
        "except we will pay up to $25,000 for such loss.",
    )
    assert f.kind == "broadened", f.detail


def test_exception_cap_lowered_is_narrowed():
    f = _pair(
        "This insurance does not apply to loss caused by pollution, "
        "except we will pay up to $25,000 for such loss.",
        "This insurance does not apply to loss caused by pollution, "
        "except we will pay up to $10,000 for such loss.",
    )
    assert f.kind == "narrowed", f.detail


# ---------------------------------------------------------------------
# (f) BOTH the base and the exception are edited, in CONFLICTING
#     directions -> "modified (direction unclear)", never guessed.
# ---------------------------------------------------------------------


def test_conflicting_base_and_exception_edit_is_unclear():
    f = _pair(
        _POLLUTION_WITH_FIRE_CARVEBACK,
        # base peril added ("or contamination" -> narrows) AND exception
        # peril added ("or by equipment used to heat..." -> broadens) in
        # the same clause pair: the two spans disagree, so this must not
        # be guessed either way.
        "This insurance does not apply to loss caused by pollution or "
        "contamination, except loss caused by a hostile fire or by "
        "equipment used to heat the insured premises.",
    )
    assert f.kind == "modified", f.detail
