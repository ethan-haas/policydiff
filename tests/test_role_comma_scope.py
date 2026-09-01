"""Regression tests for an earlier fix, both
.

Defect 1 (role leak across a comma list): a role word ("deductible",
"sublimit", "limit"/"aggregate") only governed the amount in its OWN
comma segment. A second, keyword-less comma item in the same list (e.g.
"$800 for liability" in "Deductible $500 for property, $800 for
liability") had no role word of its own and defaulted to "limit" --
so a deductible increase on the second item was reported as a limit
increase, with the direction inverted too (narrowed exposure read as
"broadened"). Root fix: a role word now PROPAGATES to a later,
keyword-less comma segment in the same sentence/';'-clause; a ';' or a
sentence end is a stronger boundary that resets the propagation, and a
segment with its own role word is never overridden by propagation (see
policydiff/classify.py: _money_roles / _role_reset_boundaries).

Defect 2 (amount-formatting false positive): two clauses whose ONLY
difference was money-literal FORMATTING (thousands-separator commas
present/absent, a trailing ".00") were not suppressed as cosmetic --
they fell through into the generic word-set classifier (which ignores
digits entirely) and came out "modified (direction unclear)" or
"modified", even though the underlying value never changed. Root fix:
normalize.py's normalize() canonicalizes monetary amounts (strip
thousands commas, drop a trailing all-zero decimal tail) before the
cosmetic-equality comparison, so two amounts naming the same number
compare identical; a genuine value or fractional change still compares
different (policydiff/normalize.py: _canonicalize_amounts).

None of these fixtures are copies of the reviewer's probe/fixture files
under the audit fixtures (that
directory is -- they are
original clauses built from the same scenarios described in the task.
"""
from policydiff.classify import classify_pair
from policydiff.report import diff_documents
from policydiff.segment import segment


def _pair(old_text: str, new_text: str, suppress_cosmetic: bool = True):
    old = segment(f"1. {old_text}\n")[0]
    new = segment(f"1. {new_text}\n")[0]
    return classify_pair(old, new, suppress_cosmetic=suppress_cosmetic)


def _non_suppressed(result):
    return [f for f in result.findings if f.kind not in ("unchanged", "cosmetic", "heading")]


# ---------------------------------------------------------------------
# Defect 1 -- role propagation across a comma list.
# ---------------------------------------------------------------------


def test_second_comma_item_inherits_role_from_earlier_role_word():
    # (a) liability amount rises but has no role word of its own -- it
    # must inherit "deductible" from the earlier segment, and a
    # deductible INCREASE is a NARROWING, not a "broadened limit".
    f = _pair(
        "Deductible $500 for property, $800 for liability.",
        "Deductible $500 for property, $1,000 for liability.",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail
    assert "limit" not in f.detail
    assert "800" in f.detail and "1,000" in f.detail


def test_first_comma_item_decrease_inherited_role_is_broadened():
    # (b) property amount falls, liability unchanged -- a deductible
    # DECREASE is a broadening.
    f = _pair(
        "Deductible $500 for property, $800 for liability.",
        "Deductible $400 for property, $800 for liability.",
    )
    assert f.kind == "broadened", f.detail
    assert "deductible" in f.detail
    assert "500" in f.detail and "400" in f.detail


def test_role_word_does_not_propagate_backwards_across_a_role_word():
    # (c) a segment with its OWN role word is never overridden by
    # propagation from an earlier segment -- limit changes, deductible
    # (which has its own keyword) is untouched and produces no finding.
    f = _pair(
        "Limit $1,000,000, deductible $500",
        "Limit $2,000,000, deductible $500",
    )
    assert f.kind == "broadened", f.detail
    assert "limit" in f.detail
    assert "deductible" not in f.detail
    assert "1,000,000" in f.detail and "2,000,000" in f.detail


def test_sublimit_role_propagates_to_second_comma_item_cash_cut():
    # (d) jewelry sublimit named explicitly, cash sublimit inherits the
    # role -- a cash sublimit CUT is a narrowing.
    f = _pair(
        "Sublimit $2,500 for jewelry, $1,000 for cash.",
        "Sublimit $2,500 for jewelry, $500 for cash.",
    )
    assert f.kind == "narrowed", f.detail
    assert "sublimit" in f.detail
    assert "1,000" in f.detail and "500" in f.detail


def test_semicolon_resets_propagation_each_item_keeps_own_role():
    # A ';' is a stronger boundary than ',' -- propagation must NOT leak
    # across it. Each item already has its own role word here, so this
    # must keep behaving exactly as an earlier revision left it.
    findings = []
    old = "1. Limit $2,000,000; deductible $500; sublimit $50,000.\n"
    new = "1. Limit $3,000,000; deductible $500; sublimit $50,000.\n"
    result = diff_documents(old, new, suppress_cosmetic=True)
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    f = non_suppressed[0]
    assert f.kind == "broadened" and "limit" in f.detail and "deductible" not in f.detail


def test_control_and_clause_form_still_correct():
    # The "and" (no comma-list) form already worked before this fix and
    # must keep working.
    f = _pair(
        "The deductible is $500 for property and $800 for liability.",
        "The deductible is $500 for property and $1,000 for liability.",
    )
    assert f.kind == "narrowed", f.detail
    assert "deductible" in f.detail


# ---------------------------------------------------------------------
# Defect 2 -- amount formatting is a cosmetic-suppression axis.
# ---------------------------------------------------------------------


def test_amount_trailing_zero_decimal_is_cosmetic():
    result = diff_documents(
        "1. The general aggregate limit is $1,000,000.\n",
        "1. The general aggregate limit is $1,000,000.00.\n",
        suppress_cosmetic=True,
    )
    assert _non_suppressed(result) == []


def test_amount_missing_thousands_commas_is_cosmetic():
    result = diff_documents(
        "1. The general aggregate limit is $1,000,000.\n",
        "1. The general aggregate limit is $1000000.\n",
        suppress_cosmetic=True,
    )
    assert _non_suppressed(result) == []


def test_amount_bare_trailing_zeros_is_cosmetic():
    result = diff_documents(
        "1. The deductible is $500.\n",
        "1. The deductible is $500.00.\n",
        suppress_cosmetic=True,
    )
    assert _non_suppressed(result) == []


def test_real_amount_change_still_surfaces_as_broadened():
    result = diff_documents(
        "1. The general aggregate limit is $1,000,000.\n",
        "1. The general aggregate limit is $1,500,000.\n",
        suppress_cosmetic=True,
    )
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1
    f = non_suppressed[0]
    assert f.kind == "broadened"
    assert "1,000,000" in f.detail and "1,500,000" in f.detail


def test_real_fractional_change_is_not_suppressed():
    result = diff_documents(
        "1. The deductible is $500.50.\n",
        "1. The deductible is $500.00.\n",
        suppress_cosmetic=True,
    )
    non_suppressed = _non_suppressed(result)
    assert len(non_suppressed) == 1, [(f.kind, f.detail) for f in non_suppressed]
    assert non_suppressed[0].kind == "broadened"


def test_no_suppress_cosmetic_flag_surfaces_amount_formatting_change():
    # Amount-format normalization is gated by the same suppress_cosmetic
    # toggle as every other cosmetic axis -- with it OFF, a pure
    # formatting difference must NOT be suppressed.
    result = diff_documents(
        "1. The general aggregate limit is $1,000,000.\n",
        "1. The general aggregate limit is $1,000,000.00.\n",
        suppress_cosmetic=False,
    )
    non_suppressed = [f for f in result.findings if f.kind not in ("unchanged", "heading")]
    assert non_suppressed != []
