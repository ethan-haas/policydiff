"""Regression tests for an earlier fix (1 NOISE
FALSE-POSITIVE defect, gate 2, reproduced live against HEAD
1d656af).

The defect: adding/removing quotation marks around a defined term
produced a spurious "[MODIFIED (direction unclear)]" finding, even
though quote marks around a defined term are a formatting/marker
convention only -- `"insured"` and `insured` name the SAME defined term,
and dropping or adding the quotes changes NO coverage. Quote STYLE
(straight<->curly) and defined-term CAPITALIZATION were already folded
to cosmetic; quote PRESENCE was not.

Reproduced live at an earlier revision:
    `The "insured" must cooperate.` -> `The insured must cooperate.`
    produced `[MODIFIED (direction unclear)]` instead of staying EMPTY.

Root fix: policydiff/normalize.py's cosmetic normalization step
(normalize()) now also strips DOUBLE-quote characters entirely (after
quote-STYLE unification, so a curly `"..."` and a straight `"..."` both
fold identically) -- see normalize.py's `_strip_quote_presence` and its
an earlier revision docstring. Single quotes/apostrophes are deliberately left
untouched, so a possessive/contraction ("insured's", "it's") is never
mangled.

None of these fixtures are copies of any reviewer's probe/fixture files
under the audit fixtures (forbidden per the
task) -- they are original clauses authored from the task's own
description of the defect and its generalizations. (The task's prose
also names the an earlier audit `quotemark_old.txt`/`quotemark_new.txt`
fixture text verbatim as a reproduction case; test_quotemark_style_
multi_term_fixture_text_is_empty below re-authors that same clause text
directly in this file rather than reading the reviewer's fixture off
disk, so it stays self-contained and independent of that directory.)
"""
from policydiff.report import diff_documents


def _non_suppressed(result):
    return [f for f in result.findings if f.kind not in ("unchanged", "cosmetic", "heading")]


def _diff(old_text: str, new_text: str, suppress_cosmetic: bool = True):
    return diff_documents(old_text, new_text, suppress_cosmetic=suppress_cosmetic)


# ---------------------------------------------------------------------
# (a) Single-term quotes-only diff -- remove and add -- must be EMPTY.
# ---------------------------------------------------------------------


def test_single_term_quotes_removed_is_empty():
    old = 'The "insured" must cooperate with the investigation.\n'
    new = "The insured must cooperate with the investigation.\n"
    result = _diff(old, new)
    assert _non_suppressed(result) == [], [(f.kind, f.detail) for f in _non_suppressed(result)]


def test_single_term_quotes_added_is_empty():
    old = "The insured must cooperate with the investigation.\n"
    new = 'The "insured" must cooperate with the investigation.\n'
    result = _diff(old, new)
    assert _non_suppressed(result) == [], [(f.kind, f.detail) for f in _non_suppressed(result)]


# ---------------------------------------------------------------------
# (b) Multi-term quotes-only diff (mirrors the task's own reproduction
# text, re-authored here rather than read from the reviewer's fixture
# file) -- must be EMPTY.
# ---------------------------------------------------------------------


def test_quotemark_style_multi_term_fixture_text_is_empty():
    old = (
        "SECTION I - COVERAGES\n"
        "1. Coverage A - Bodily Injury and Property Damage Liability. We will "
        'pay those sums that the "insured" becomes legally obligated to pay as '
        'damages because of "bodily injury" or "property damage" to which this '
        "insurance applies.\n"
        "2. The General Aggregate Limit is $2,000,000.\n"
    )
    new = (
        "SECTION I - COVERAGES\n"
        "1. Coverage A - Bodily Injury and Property Damage Liability. We will "
        "pay those sums that the insured becomes legally obligated to pay as "
        "damages because of bodily injury or property damage to which this "
        "insurance applies.\n"
        "2. The General Aggregate Limit is $2,000,000.\n"
    )
    result = _diff(old, new)
    assert _non_suppressed(result) == [], [(f.kind, f.detail) for f in _non_suppressed(result)]


def test_quotemark_multi_term_fixture_text_reverse_add_is_empty():
    # Symmetric: adding quotes to the multi-term clause must also stay
    # EMPTY, not just removing them.
    old = (
        "1. We will pay those sums that the insured becomes legally "
        "obligated to pay as damages because of bodily injury or property "
        "damage to which this insurance applies.\n"
    )
    new = (
        '1. We will pay those sums that the "insured" becomes legally '
        'obligated to pay as damages because of "bodily injury" or '
        '"property damage" to which this insurance applies.\n'
    )
    result = _diff(old, new)
    assert _non_suppressed(result) == [], [(f.kind, f.detail) for f in _non_suppressed(result)]


# ---------------------------------------------------------------------
# (c) A REAL content change alongside a quote-presence change is STILL
# reported -- only the quote-presence delta itself is suppressed.
# ---------------------------------------------------------------------


def test_real_change_alongside_quote_removal_is_still_reported():
    old = 'The "insured" is covered for fire.\n'
    new = "The insured is covered for fire or flood.\n"
    result = _diff(old, new)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert f.kind != "unchanged" and f.kind != "cosmetic"
    assert "flood" in f.new.text.lower()
    assert "flood" not in f.old.text.lower()


def test_real_change_alongside_quote_addition_is_still_reported():
    old = "The insured is covered for fire.\n"
    new = 'The "insured" is covered for fire or flood.\n'
    result = _diff(old, new)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert "flood" in f.new.text.lower()


# ---------------------------------------------------------------------
# (d) --no-suppress-cosmetic must surface a quotes-only diff as a real
# finding -- proves the suppression step is load-bearing (gate 5
# discipline, same pattern as every other cosmetic axis).
# ---------------------------------------------------------------------


def test_no_suppress_cosmetic_surfaces_quotes_only_diff():
    old = 'The "insured" must cooperate.\n'
    new = "The insured must cooperate.\n"
    default_result = _diff(old, new, suppress_cosmetic=True)
    assert _non_suppressed(default_result) == [], (
        "default (suppression ON) must be fully suppressed"
    )
    off_result = _diff(old, new, suppress_cosmetic=False)
    non_suppressed = _non_suppressed(off_result)
    assert non_suppressed != [], (
        "--no-suppress-cosmetic must surface a quotes-only diff as a real "
        "finding, not silently stay empty"
    )


# ---------------------------------------------------------------------
# (e) GUARDS -- possessive/contraction apostrophes are never mangled by
# the quote-presence fold (which is scoped to DOUBLE quotes only).
# ---------------------------------------------------------------------


def test_possessive_apostrophe_unchanged_stays_empty():
    old = "The insured's obligations apply to every claim.\n"
    new = "The insured's obligations apply to every claim.\n"
    result = _diff(old, new)
    assert _non_suppressed(result) == [], [(f.kind, f.detail) for f in _non_suppressed(result)]


def test_possessive_apostrophe_real_change_still_reported():
    old = "The insured's obligations apply to every claim.\n"
    new = "The insured's duties apply to every claim.\n"
    result = _diff(old, new)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert "duties" in f.new.text.lower()
    assert "obligations" in f.old.text.lower()
    # The apostrophe itself must survive untouched on both sides -- the
    # possessive is not mangled into "insureds".
    assert "insured's" in f.old.text.lower()
    assert "insured's" in f.new.text.lower()


def test_contraction_apostrophe_unchanged_stays_empty():
    old = "It's understood that this policy applies to the named insured.\n"
    new = "It's understood that this policy applies to the named insured.\n"
    result = _diff(old, new)
    assert _non_suppressed(result) == [], [(f.kind, f.detail) for f in _non_suppressed(result)]


# ---------------------------------------------------------------------
# (f) Non-regression: quote-STYLE (straight<->curly) and defined-term
# recap normalization must still be EMPTY after this fix.
# ---------------------------------------------------------------------


def test_quote_style_straight_to_curly_still_empty():
    old = 'The "insured" is covered.\n'
    new = "The “insured” is covered.\n"
    result = _diff(old, new)
    assert _non_suppressed(result) == [], [(f.kind, f.detail) for f in _non_suppressed(result)]


def test_defined_term_recap_with_quotes_still_empty():
    old = 'The "Insured" is covered under this policy.\n'
    new = 'The "insured" is covered under this policy.\n'
    result = _diff(old, new)
    assert _non_suppressed(result) == [], [(f.kind, f.detail) for f in _non_suppressed(result)]


def test_defined_term_recap_quote_presence_combined_still_empty():
    # Recap AND quote-presence change together on the same term -- both
    # axes are cosmetic, so this must still be EMPTY.
    old = 'The "Insured" must cooperate.\n'
    new = "The insured must cooperate.\n"
    result = _diff(old, new)
    assert _non_suppressed(result) == [], [(f.kind, f.detail) for f in _non_suppressed(result)]
