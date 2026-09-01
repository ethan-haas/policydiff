"""Regression tests for an earlier fix (1 NOISE
FALSE-POSITIVE defect, gate 2, reproduced live against HEAD
ba243ba).

The defect: pure renumbering with a bare-letter ("A.", "a."),
lowercase-roman-dot ("i.", "ii.") or paren-roman ("(i)", "(I)")
enumerator style produced spurious "[MODIFIED (direction unclear)]"
findings, even though the clause bodies were byte-identical. Arabic
("1."), paren-arabic ("(1)"), paren-letter ("(a)"), uppercase-roman-dot
("I.") and dotted-decimal ("4.1") were already correctly recognized as
cosmetic clause-number anchors and suppressed -- these four sibling
styles were simply never taught to either the segmenter (segment.py) or
the normalizer (normalize.py).

Root fix: policydiff/enumerators.py adds shared recognition for BARE
(unparenthesized) single-letter/lowercase-roman markers and multi-letter
paren-roman markers. The paren-roman form is unconditional (parens
already make it unambiguous with ordinary prose, exactly like the
pre-existing paren-letter/paren-arabic forms). The BARE forms are gated
by policydiff.enumerators.confirmed_bare_alpha_line_indices(): a bare
"A."/"a."/"i." match is only trusted as a real clause label when some
OTHER enumerator label elsewhere in the same line set is its immediate
alphabet/roman successor or predecessor -- otherwise it is left as
ordinary content. This is what keeps a genuine sentence-internal-looking
abbreviation or initial ("No. 5", "U.S. law", "J. Smith") from being
mistaken for a clause anchor, while still recognizing a real "A. / B. /
C." (or "B. / C. / D." after relabeling) list.

None of these fixtures are copies of any reviewer's probe/fixture files
under the audit fixtures (forbidden per the
task) -- they are original clauses authored from the task's own
description of the defect and its generalizations.
"""
from policydiff.report import diff_documents


def _non_suppressed(result):
    return [f for f in result.findings if f.kind not in ("unchanged", "cosmetic", "heading")]


def _diff(old_text: str, new_text: str, suppress_cosmetic: bool = True):
    return diff_documents(old_text, new_text, suppress_cosmetic=suppress_cosmetic)


# ---------------------------------------------------------------------
# (a) Bare capital-letter-dot relabel, identical bodies -> EMPTY.
# ---------------------------------------------------------------------


def test_bare_capital_letter_relabel_identical_bodies_is_empty():
    old = (
        "A. Coverage A covers bodily injury and property damage.\n"
        "B. Coverage B covers personal and advertising injury.\n"
        "C. Coverage C covers medical payments.\n"
    )
    new = (
        "B. Coverage A covers bodily injury and property damage.\n"
        "C. Coverage B covers personal and advertising injury.\n"
        "D. Coverage C covers medical payments.\n"
    )
    result = _diff(old, new)
    assert _non_suppressed(result) == [], [(f.kind, f.detail) for f in _non_suppressed(result)]


def test_bare_capital_letter_relabel_with_real_change_is_exactly_one_finding():
    old = (
        "A. Coverage A covers bodily injury and property damage.\n"
        "B. Coverage B covers personal and advertising injury.\n"
        "C. Coverage C covers medical payments.\n"
    )
    new = (
        "B. Coverage A covers bodily injury, property damage, and theft.\n"
        "C. Coverage B covers personal and advertising injury.\n"
        "D. Coverage C covers medical payments.\n"
    )
    result = _diff(old, new)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert "theft" in f.new.text.lower()
    assert "bodily injury" in f.old.text.lower()


# ---------------------------------------------------------------------
# (b) Bare lowercase-letter-dot relabel, identical bodies -> EMPTY.
# ---------------------------------------------------------------------


def test_bare_lowercase_letter_relabel_identical_bodies_is_empty():
    old = "a. Coverage for fire.\nb. Coverage for theft.\n"
    new = "b. Coverage for fire.\nc. Coverage for theft.\n"
    result = _diff(old, new)
    assert _non_suppressed(result) == [], [(f.kind, f.detail) for f in _non_suppressed(result)]


# ---------------------------------------------------------------------
# (c) Lowercase-roman-dot relabel, identical bodies -> EMPTY.
# ---------------------------------------------------------------------


def test_lowercase_roman_dot_relabel_identical_bodies_is_empty():
    old = "i. Coverage for fire.\nii. Coverage for theft.\n"
    new = "ii. Coverage for fire.\niii. Coverage for theft.\n"
    result = _diff(old, new)
    assert _non_suppressed(result) == [], [(f.kind, f.detail) for f in _non_suppressed(result)]


def test_lowercase_roman_dot_three_item_relabel_identical_bodies_is_empty():
    old = "i. Coverage for fire.\nii. Coverage for theft.\niii. Coverage for flood.\n"
    new = "ii. Coverage for fire.\niii. Coverage for theft.\niv. Coverage for flood.\n"
    result = _diff(old, new)
    assert _non_suppressed(result) == [], [(f.kind, f.detail) for f in _non_suppressed(result)]


# ---------------------------------------------------------------------
# (d) Paren-roman relabel, identical bodies -> EMPTY.
# ---------------------------------------------------------------------


def test_paren_roman_relabel_identical_bodies_is_empty():
    old = "(i) Coverage for fire.\n(ii) Coverage for theft.\n"
    new = "(ii) Coverage for fire.\n(iii) Coverage for theft.\n"
    result = _diff(old, new)
    assert _non_suppressed(result) == [], [(f.kind, f.detail) for f in _non_suppressed(result)]


def test_paren_roman_uppercase_relabel_identical_bodies_is_empty():
    old = "(I) Coverage for fire.\n(II) Coverage for theft.\n"
    new = "(II) Coverage for fire.\n(III) Coverage for theft.\n"
    result = _diff(old, new)
    assert _non_suppressed(result) == [], [(f.kind, f.detail) for f in _non_suppressed(result)]


# ---------------------------------------------------------------------
# GUARDS -- pre-existing enumerator styles must still suppress a pure
# renumber exactly as before (unchanged baseline behavior).
# ---------------------------------------------------------------------


def test_guard_arabic_renumber_still_empty():
    old = "1. Coverage A applies.\n2. Coverage B applies.\n"
    new = "2. Coverage A applies.\n3. Coverage B applies.\n"
    result = _diff(old, new)
    assert _non_suppressed(result) == []


def test_guard_paren_arabic_renumber_still_empty():
    old = "(1) Coverage A applies.\n(2) Coverage B applies.\n"
    new = "(2) Coverage A applies.\n(3) Coverage B applies.\n"
    result = _diff(old, new)
    assert _non_suppressed(result) == []


def test_guard_paren_letter_renumber_still_empty():
    old = "(a) Coverage A applies.\n(b) Coverage B applies.\n"
    new = "(b) Coverage A applies.\n(c) Coverage B applies.\n"
    result = _diff(old, new)
    assert _non_suppressed(result) == []


def test_guard_uppercase_roman_renumber_still_empty():
    old = "I. Coverage A applies.\nII. Coverage B applies.\n"
    new = "II. Coverage A applies.\nIII. Coverage B applies.\n"
    result = _diff(old, new)
    assert _non_suppressed(result) == []


def test_guard_dotted_decimal_renumber_still_empty():
    old = "4.1 Coverage A applies.\n4.2 Coverage B applies.\n"
    new = "4.2 Coverage A applies.\n4.3 Coverage B applies.\n"
    result = _diff(old, new)
    assert _non_suppressed(result) == []


# ---------------------------------------------------------------------
# GUARDS -- abbreviations/initials and the bare article "A " must NOT be
# treated as enumerators; their content is compared normally, and a real
# change is still caught.
# ---------------------------------------------------------------------


def test_guard_us_abbreviation_not_treated_as_enumerator_unchanged():
    text = "U.S. Government agencies must comply with all state regulations for coverage."
    result = _diff(text, text)
    assert _non_suppressed(result) == []


def test_guard_us_abbreviation_real_change_is_caught():
    old = "U.S. Government agencies must comply with all state regulations for coverage."
    new = "U.S. Government agencies must comply with all state regulations for policy."
    result = _diff(old, new)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    assert "U.S. Government" in non_suppressed[0].new.text


def test_guard_no_abbreviation_not_treated_as_enumerator_unchanged():
    text = "No. 5 endorsement applies here to all listed properties in the schedule."
    result = _diff(text, text)
    assert _non_suppressed(result) == []


def test_guard_initial_j_smith_not_treated_as_enumerator_unchanged():
    text = "J. Smith is an additional insured under this policy for all claims filed."
    result = _diff(text, text)
    assert _non_suppressed(result) == []


def test_guard_initial_real_rename_is_caught_as_a_real_change():
    old = "J. Smith is an additional insured under this policy for all claims filed."
    new = "K. Jones is an additional insured under this policy for all claims filed."
    result = _diff(old, new)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    assert "K. Jones" in non_suppressed[0].new.text


def test_guard_bare_article_a_no_dot_not_treated_as_enumerator():
    text = "A additional endorsement applies to this policy for full coverage today."
    result = _diff(text, text)
    assert _non_suppressed(result) == []


def test_guard_bare_article_a_real_change_is_caught():
    old = "A additional endorsement applies to this policy for full coverage today."
    new = "A additional endorsement applies to this policy for full coverage tomorrow."
    result = _diff(old, new)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]


# ---------------------------------------------------------------------
# --no-suppress-cosmetic must surface the letter relabel -- proving the
# suppression is real and load-bearing, exactly like the pre-existing
# numeric-renumber toggle test (test_suppression_toggle.py).
# ---------------------------------------------------------------------


def test_letter_relabel_surfaces_with_suppression_off():
    old = (
        "A. Coverage A covers bodily injury and property damage.\n"
        "B. Coverage B covers personal and advertising injury.\n"
        "C. Coverage C covers medical payments.\n"
    )
    new = (
        "B. Coverage A covers bodily injury and property damage.\n"
        "C. Coverage B covers personal and advertising injury.\n"
        "D. Coverage C covers medical payments.\n"
    )
    result = _diff(old, new, suppress_cosmetic=False)
    non_suppressed = _non_suppressed(result)
    assert non_suppressed != [], (
        "disabling cosmetic suppression should surface the bare-letter "
        "renumber as a finding -- if this is still empty, the new "
        "suppression is a no-op"
    )
    for f in non_suppressed:
        assert "renumbered" in f.detail
