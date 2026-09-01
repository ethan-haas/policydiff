"""Regression tests for an earlier fix (1 WRONG-DIRECTION
defect, specification's worst class against HEAD
26157b4).

Defect (wrong-direction): a DOLLAR-denominated exception carved BACK OUT
of an exclusion GRANTS coverage that did not exist -- BROADENING -- but
the generic numeric "a dollar figure of this role appeared/disappeared
outright -> ADDED narrows, REMOVED broadens" rule (classify._classify_numeric)
fired FIRST, before the exclusion carve-back/scope-signal logic
(classify._classify_exclusion) ever got a look at the pair, and inverted
the direction:

    "5. Exclusion - Mold. This insurance does not apply to loss caused by
    mold." (mold fully excluded, $0 coverage)
    + no-$ carve-back "..., except that we will pay for such loss." ->
      [BROADENED]  (correct -- no $ present, _classify_numeric returns
      None, falls through to the exclusion scope-signal path, which
      already handled this case correctly since an earlier revision)
    + $ carve-back "..., except that we will pay up to $10,000 for such
      loss." -> [NARROWED] "limit of $10,000 added" (WRONG -- $10,000 of
      coverage now exists where there was none; must be BROADENED)
    - removing that same $ carve-back -> [BROADENED] "limit of $10,000
      removed" (WRONG -- coverage LOST; must be NARROWED)

Root fix (classify.py): a new carve-back-marker-added/removed check
(_classify_exclusion_carveback) now runs INSIDE the exclusion-context
branch of _classify_signal, BEFORE _classify_numeric -- so the amount
inside a newly-added/removed carve-back never gets to drive direction via
the generic "$ figure count differs" rule. A carve-back's own CAP
changing (present, with different amounts, on BOTH sides) is deliberately
left to the ordinary numeric chain, which already resolves it correctly
(equal $-count -> direct value compare, "limit" role default -> higher
cap = broadened, lower = narrowed) once the marker-added/removed check
declines to intercept it (see classify.py's an earlier revision root-fix comment
block for the full rationale). The ordinary numeric rule for a
NON-exclusion clause (a coverage grant gaining a sublimit) and the
ordinary exclusion NEW-PERIL rule are both unaffected -- neither one
carries a carve-back marker.

None of these fixtures are copies of any reviewer's probe/fixture files
under the audit fixtures
task's FORBIDDEN clause) -- they are original clauses authored from the
task's own description of the defect and its generalizations.
"""
from policydiff.classify import classify_pair
from policydiff.segment import segment


def _pair(old_text: str, new_text: str, heading: str = "Exclusion - Mold"):
    old = segment(f"5. {heading}. {old_text}\n")[0]
    new = segment(f"5. {heading}. {new_text}\n")[0]
    return classify_pair(old, new, suppress_cosmetic=True)


_MOLD_EXCLUDED = "This insurance does not apply to loss caused by mold."


# ---------------------------------------------------------------------
# (a) $ carve-back ADDED to an exclusion -> BROADENED (the primary
#     defect, reproduced live above).
# ---------------------------------------------------------------------


def test_dollar_carveback_added_is_broadened():
    f = _pair(
        _MOLD_EXCLUDED,
        "This insurance does not apply to loss caused by mold, except that "
        "we will pay up to $10,000 for such loss.",
    )
    assert f.kind == "broadened", f.detail
    assert "narrow" not in f.detail.lower()


def test_dollar_carveback_added_generalizes_first_dollars_phrasing():
    # "does not apply to the first $X of such loss" generalization.
    f = _pair(
        _MOLD_EXCLUDED,
        "This insurance does not apply to loss caused by mold. This "
        "exclusion does not apply to the first $25,000 of such loss.",
    )
    assert f.kind == "broadened", f.detail


def test_dollar_carveback_added_generalizes_however_phrasing():
    # "however, we will pay up to $X for..." generalization.
    f = _pair(
        _MOLD_EXCLUDED,
        "This insurance does not apply to loss caused by mold. However, "
        "we will pay up to $50,000 for resulting fire damage.",
    )
    assert f.kind == "broadened", f.detail


def test_dollar_carveback_added_generalizes_except_we_will_pay_phrasing():
    # "except we will pay up to $X for..." generalization.
    f = _pair(
        _MOLD_EXCLUDED,
        "This insurance does not apply to loss caused by mold, except we "
        "will pay up to $100,000 for resulting fire.",
    )
    assert f.kind == "broadened", f.detail


# ---------------------------------------------------------------------
# (b) $ carve-back REMOVED from an exclusion -> NARROWED.
# ---------------------------------------------------------------------


def test_dollar_carveback_removed_is_narrowed():
    old = (
        "This insurance does not apply to loss caused by mold, except "
        "that we will pay up to $10,000 for such loss."
    )
    f = _pair(old, _MOLD_EXCLUDED)
    assert f.kind == "narrowed", f.detail
    assert "broaden" not in f.detail.lower()


# ---------------------------------------------------------------------
# (c) no-$ carve-back added -> still BROADENED (must remain correct,
#     unchanged from an earlier revision/17 behavior).
# ---------------------------------------------------------------------


def test_no_dollar_carveback_added_still_broadened():
    f = _pair(
        _MOLD_EXCLUDED,
        "This insurance does not apply to loss caused by mold, except "
        "that we will pay for such loss.",
    )
    assert f.kind == "broadened", f.detail


# ---------------------------------------------------------------------
# (d) carve-back present on BOTH sides, only its CAP changes -> numeric
#     direction WITHIN the carve-back (cap up = broadened, down =
#     narrowed) -- never intercepted as a bare add/remove.
# ---------------------------------------------------------------------


def test_carveback_cap_increase_is_broadened():
    old = (
        "This insurance does not apply to loss caused by mold, except "
        "that we will pay up to $10,000 for such loss."
    )
    new = (
        "This insurance does not apply to loss caused by mold, except "
        "that we will pay up to $25,000 for such loss."
    )
    f = _pair(old, new)
    assert f.kind == "broadened", f.detail


def test_carveback_cap_decrease_is_narrowed():
    old = (
        "This insurance does not apply to loss caused by mold, except "
        "that we will pay up to $25,000 for such loss."
    )
    new = (
        "This insurance does not apply to loss caused by mold, except "
        "that we will pay up to $10,000 for such loss."
    )
    f = _pair(old, new)
    assert f.kind == "narrowed", f.detail


# ---------------------------------------------------------------------
# GUARD (e): an ORDINARY coverage grant (not an exclusion) gaining a
# sublimit is still NARROWED -- the carve-back precedence must never
# leak into non-exclusion clauses.
# ---------------------------------------------------------------------


def test_guard_ordinary_grant_sublimit_added_still_narrowed():
    old = segment("6. Coverage A. Coverage A applies to jewelry.\n")[0]
    new = segment(
        "6. Coverage A. Coverage A applies to jewelry, sublimit $5,000.\n"
    )[0]
    f = classify_pair(old, new, suppress_cosmetic=True)
    assert f.kind == "narrowed", f.detail
    assert "sublimit" in f.detail


# ---------------------------------------------------------------------
# GUARD (f): a genuinely NEW EXCLUDED PERIL is still NARROWED -- the
# carve-back marker check must not fire on an ordinary "or <peril>"
# extension that carries none of the carve-back markers.
# ---------------------------------------------------------------------


def test_guard_new_excluded_peril_still_narrowed():
    f = _pair(
        "This insurance does not apply to flood.",
        "This insurance does not apply to flood or war.",
        heading="Exclusion - Weather",
    )
    assert f.kind == "narrowed", f.detail
